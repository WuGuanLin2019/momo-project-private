"""把 agent 的实时上下文推送给外部调试页面（third_party/Debug/debugViewer.html）。

数据流：

    LangGraph checkpointer 中的 state
        -> build_context_snapshot()            取当前 state 并序列化成 JSON 安全的结构
        -> DrawBridgeServer.send_message_sync()       经 WebSocket 发给已注册的客户端
        -> debugViewer.html 渲染

两种推送时机：

1. 后台线程轮询：检测到上下文变化才推送，内容没变则一帧都不发。
   注意 LangGraph 的 checkpointer 是按 superstep 落地的，AI 消息要等整个 turn 结束后
   才会出现在 state 里，所以刷新粒度是「每轮结束」而非逐 token。要看 token 级流式
   得接 astream_events 的钩子，不属于本模块的职责。
2. 前端主动请求：收到 {"action": "request_context"} 立刻回推一帧，用于手动刷新和
   切换 agent。

推送目标（agent/thread）是运行时共享状态，不是启动参数：调试页切到哪个 agent，
后台轮询就跟着看哪个。原因见 switch_debug_target 处的注释。

接入：在主流程中调用一次即可（DrawBridgeServer 会在 import 时自行启动）

    from Debug import DebugSender
    DebugSender.start_debug_sender()

然后用浏览器打开 third_party/Debug/debugViewer.html。
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from LangChain.Agent import MOMO_AGENT_NAME, agentMgr
from DrawBridge import DrawBridgeServer
from DrawBridge.DrawBridgeEvent import DrawBridgeEvent
from Utils.EventDispatch import eventDispatch

# 调试页面在 DrawBridgeServer 里注册的 unique_name，必须与 debugViewer.html 保持一致
DEBUG_VIEWER = "debug_viewer"

DEFAULT_INTERVAL = 0.3

_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()
_last_signature: str | None = None
# 轮询线程与「前端主动请求」回调都会读写 _last_signature
_signature_lock = threading.Lock()

# 当前推送目标 (agent_name, thread_id)。必须是运行时可改的共享状态：
# 若像启动参数那样在线程里固化，前端切到别的 agent 后，轮询线程仍按 momo
# 取快照，而 force 推送已经把 _last_signature 刷成了新 agent 的签名，于是
# 下一帧 momo 就被判定为「内容有变化」而重新推出去，把刚切过去的画面顶掉
# ——这就是「切换 agent 后还是显示 momo 上下文」的直接原因。
_target_lock = threading.Lock()
_target: tuple[str, str] = (MOMO_AGENT_NAME, MOMO_AGENT_NAME)


def switch_debug_target(agent_name: str, thread_id: str | None = None) -> tuple[str, str]:
    """切换后台轮询正在盯的会话，前端 request_context 到达时会调用它。"""
    global _target

    target = (agent_name, thread_id or agent_name)
    with _target_lock:
        _target = target
    return target


def _get_target() -> tuple[str, str]:
    with _target_lock:
        return _target


def _json_safe(value: Any) -> Any:
    """把不可 JSON 序列化的值降级为可读字符串。

    这一步是必要的：ws.send_json 一旦失败会被 DrawBridgeServer 当作断连并踢掉客户端，
    任何孤立的非序列化字段（如某些厂商返回的 usage 对象）都会让调试页面掉线。
    """
    try:
        # 返回值无关紧要，这里只是借它做「能否序列化」的探测
        _ = json.dumps(value)
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v) for v in value]
        return repr(value)
    return value


def _content_to_str(content: Any) -> str:
    """LangChain 的 content 既可能是 str，也可能是多模态的 list[dict]。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # 思考过程由 _extract_thinking 单独提取展示，正文里跳过：
                # 否则会被下面那行降级成 "[reasoning]" 占位符，等于把思考内容丢了
                if block.get("type") in ("reasoning", "thinking"):
                    continue
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                else:
                    parts.append(f"[{block.get('type', 'unknown')}]")
        return "".join(parts)
    return str(content)


def _extract_thinking(msg: Any) -> str:
    """提取模型返回的思考过程。各家存放位置不统一，这里做兼容。

    - additional_kwargs["reasoning_content"]：DeepSeek / Ollama / XAI / Groq
      （langchain_core.messages.base._extract_reasoning_from_additional_kwargs
      读的也是这个字段，见 chat_models.py:316 的写入处）
    - content 中的 reasoning / thinking block：Gemini / Anthropic，经 block
      translator 归一后形如 {"type": "reasoning", "reasoning": "..."}
    - additional_kwargs["reasoning"]：OpenAI Responses API 风格
    """
    found: list[str] = []

    def _add(value: Any) -> None:
        if isinstance(value, str) and value:
            found.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    found.append(item)

    kwargs = getattr(msg, "additional_kwargs", None)
    if isinstance(kwargs, dict):
        _add(kwargs.get("reasoning_content"))

        reasoning = kwargs.get("reasoning")
        if isinstance(reasoning, dict):
            # OpenAI Responses 风格：正文在 text，压缩摘要在 summary[].text
            _add(reasoning.get("text"))
            summary = reasoning.get("summary")
            if isinstance(summary, list):
                for s in summary:
                    if isinstance(s, dict):
                        _add(s.get("text"))
        else:
            _add(reasoning)

    content = getattr(msg, "content", None)
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "reasoning":
                _add(block.get("reasoning"))
            elif btype == "thinking":
                _add(block.get("thinking") or block.get("text"))

    # 去重保序：同一份思考可能同时出现在 additional_kwargs 和 content 里
    seen: set[str] = set()
    uniq: list[str] = []
    for t in found:
        if t not in seen:
            seen.add(t)
            uniq.append(t)

    return "\n".join(uniq)


def _message_to_dict(msg: Any) -> dict[str, Any]:
    """把任意 LangChain message 转成前端可直接渲染的 dict。"""
    data: dict[str, Any] = {
        "id": getattr(msg, "id", None),
        "role": getattr(msg, "type", None),
        "class": type(msg).__name__,
        "content": _content_to_str(getattr(msg, "content", "")),
    }

    thinking = _extract_thinking(msg)
    if thinking:
        data["thinking"] = thinking

    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = [
            {
                "name": tc.get("name"),
                "args": tc.get("args"),
                "id": tc.get("id"),
            }
            for tc in tool_calls
            if isinstance(tc, dict)
        ]

    tool_call_id = getattr(msg, "tool_call_id", None)
    if tool_call_id:
        data["tool_call_id"] = tool_call_id

    usage = getattr(msg, "usage_metadata", None)
    if usage:
        data["usage"] = _json_safe(usage)

    return _json_safe(data)


def _get_system_prompt(agent_name: str) -> str:
    """取该 agent 当前生效的 system prompt。

    system prompt 不在 state 里，所以只能从源头读：MomoSystemPromptMiddleware 是
    用 request.override(system_message=...) 在每次模型调用前动态注入的，这个覆盖只
    存在于传给模型的 ModelRequest 上，checkpointer 落地的 state 中不会留下
    SystemMessage。这里读的正是该中间件自己拼接时用的那个 PromptPiecer
    （Agent.py:268），拿到的就是此刻实际会发给模型的文本。

    注意这是「此刻」的快照，而非历史上某次请求真正发出的那份——prompt 被中途
    add/remove 过的话，两者会有差异。
    """
    ins = agentMgr.get_agent_ins(agent_name)
    if ins is None:
        return ""

    piecer = getattr(ins, "promptPiecer", None)
    if piecer is None:
        return ""

    try:
        return piecer.get_full_text() or ""
    except Exception as e:
        print(f"[DebugSender] 读取 {agent_name} 的 system prompt 失败: {e}")
        return ""


def build_context_snapshot(agent_name: str, thread_id: str) -> dict[str, Any] | None:
    """读取某个 agent 在某个会话 thread 下的当前上下文。

    只有 agent 本身不存在才返回 None。agent 存在但该 thread 还没跑过
    （checkpointer 里没有 checkpoint）时要返回「空帧」而不是 None：否则前端
    切到一个尚未产生会话的 agent 会因为一帧都收不到而停在原画面上，看上去
    就是切换没生效。
    """
    agent = agentMgr.get_agent(agent_name)
    if agent is None:
        return None

    values: dict[str, Any] = {}
    try:
        state = agent.get_state({"configurable": {"thread_id": thread_id}})
        if state and state.values:
            values = state.values
    except Exception as e:
        print(f"[DebugSender] 读取 {agent_name}/{thread_id} 状态失败: {e}")

    system_prompt = _get_system_prompt(agent_name)

    raw_messages = values.get("messages", [])
    messages = [_message_to_dict(m) for m in raw_messages if hasattr(m, "type")]

    # messages 之外的自定义 channel（如中间件写入的字段），同样展示出来便于排查
    extras: dict[str, Any] = {}
    for key, value in values.items():
        if key == "messages":
            continue
        extras[key] = _json_safe(value)

    last = messages[-1] if messages else None
    # 签名里带上末条消息的内容长度，这样「同一条消息正在流式增长」也能被感知。
    # 再带上 system prompt 的哈希：否则 prompt 被动态增删（如 ReadingMgr）而消息
    # 没变时，这一帧会被判定为「无变化」而不推送。hash 只在同进程内稳定，
    # 这里仅用于本进程内的变化检测，够用。
    prompt_hash = hash(system_prompt)
    # 带上目标本身：_last_signature 是所有会话共用的一个变量，不带上 agent/thread
    # 的话，A 会话的签名会被拿去和 B 会话比，切换目标时必然被误判成「有变化」。
    scope = f"{agent_name}/{thread_id}"
    signature = (
        f"{scope}|{len(messages)}|{last['id']}|{last['role']}|{len(last['content'])}|{prompt_hash}"
        if last
        else f"{scope}|{len(messages)}|empty|{prompt_hash}"
    )

    total_tokens = 0
    for m in messages:
        usage = m.get("usage")
        if isinstance(usage, dict):
            total_tokens += int(usage.get("total_tokens") or 0)

    return {
        "agent_name": agent_name,
        "thread_id": thread_id,
        "system_prompt": system_prompt,
        "messages": messages,
        "extras": extras,
        "message_count": len(messages),
        "total_tokens": total_tokens,
        "signature": signature,
        "timestamp": time.time(),
    }


def send_context(agent_name: str, thread_id: str, *, force: bool = False) -> bool:
    """构建并推送一帧上下文。force=False 时若内容无变化则跳过。"""
    if DEBUG_VIEWER not in DrawBridgeServer.clients_list:
        return False

    snapshot = build_context_snapshot(agent_name, thread_id)
    if snapshot is None:
        return False

    global _last_signature
    with _signature_lock:
        if not force and snapshot["signature"] == _last_signature:
            return False
        _last_signature = snapshot["signature"]

    try:
        DrawBridgeServer.send_message(
            DEBUG_VIEWER, {"action": "context", "snapshot": snapshot}
        )
    except Exception as e:
        print(f"[DebugSender] 推送上下文失败: {e}")
        return False
    return True


def _poll_loop(interval: float) -> None:
    while not _stop_event.is_set():
        try:
            # 没有 viewer 连接时就不做任何快照计算，避免空转和刷屏
            if DEBUG_VIEWER in DrawBridgeServer.clients_list:
                # 每轮都重取目标：前端切换 agent 后轮询要跟着走过去
                send_context(*_get_target())
        except Exception as e:
            print(f"[DebugSender] 轮询异常: {e}")
        _stop_event.wait(interval)


def _on_receive_message(data: dict[str, Any]) -> None:
    """响应调试页面的主动请求。"""
    if data.get("unique_name") != DEBUG_VIEWER:
        return

    payload = data.get("data") or {}
    action = payload.get("action")

    if action == "request_context":
        agent_name = payload.get("agent_name") or MOMO_AGENT_NAME
        thread_id = payload.get("thread_id") or agent_name
        # 先把轮询目标切过去再推：顺序反了的话，这一帧发出后下一轮轮询仍在盯
        # 旧目标，会立刻把刚切好的画面覆盖回去
        switch_debug_target(agent_name, thread_id)
        send_context(agent_name, thread_id, force=True)
    elif action == "list_agents":
        DrawBridgeServer.send_message(
            DEBUG_VIEWER,
            {"action": "agent_list", "agents": sorted(agentMgr.agents.keys())},
        )


eventDispatch.register(DrawBridgeEvent.on_receive_message, _on_receive_message)


def start_debug_sender(
    agent_name: str = MOMO_AGENT_NAME,
    thread_id: str = MOMO_AGENT_NAME,
    interval: float = DEFAULT_INTERVAL,
) -> threading.Thread:
    """启动后台推送线程，重复调用只会启动一次。

    agent_name/thread_id 只是初始值，之后可以在调试页里随时切换。
    """
    global _poll_thread

    switch_debug_target(agent_name, thread_id)

    if _poll_thread is not None and _poll_thread.is_alive():
        return _poll_thread

    _stop_event.clear()
    _poll_thread = threading.Thread(
        target=_poll_loop,
        args=(interval,),
        name="DebugSender",
        daemon=True,
    )
    _poll_thread.start()
    print(
        f"[DebugSender] 已启动: {agent_name}/{thread_id}, 每 {interval}s 检测一次变化"
        + " (打开 third_party/Debug/debugViewer.html 查看)"
    )
    return _poll_thread


def stop_debug_sender() -> None:
    _stop_event.set()
