"""把 agent 的实时上下文推送给外部调试页面（third_party/Debug/debugViewer.html）。

数据流：

    LangGraph checkpointer 中的 state
        -> build_context_snapshot()   取当前 state 并序列化成 JSON 安全的结构
                                   （实现位于 Memory/DataHandler/ConversationSave.py，
                                     与对话保存器共用，保证调试页与落盘内容同源）
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

import threading
from typing import Any

from LangChain.Agent import MOMO_AGENT_NAME, agentMgr
from DrawBridge import DrawBridgeServer
from DrawBridge.DrawBridgeEvent import DrawBridgeEvent
from Memory.DataHandler.ConversationSave import build_context_snapshot
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
