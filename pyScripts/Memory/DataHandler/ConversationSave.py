#每轮对话保存一次
#保存前记得备份

from __future__ import annotations

import atexit
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from Brain.BrainEvent import BrainEvent
from Brain.Context.AgentStatusMgr import AGENT_STATUS_KEY
from Data.config import CONVERSATION_DIR
from LangChain.Agent import MOMO_AGENT_NAME, MOMO_INTERNAL_AGENT_NAME, agentMgr
from LangChain.SummarizationArchive import (
    SummarizationArchived,
    SummarizationArchiveEvent,
)
from Utils.EventDispatch import eventDispatch

# 静默超时则开启新会话
SESSION_GAP_SECONDS = 30 * 60
# 每会话最多保留几份备份
BACKUP_KEEP = 3
# 注入的状态消息，非对话内容，跳过
_STATUS_MARKER = f"<{AGENT_STATUS_KEY}>"

# --------------------------- 上下文快照构建
# 以下由 DebugSender 搬迁，两侧共用


def _json_safe(value: Any) -> Any:
    """不可 JSON 序列化的值降级为字符串"""
    try:
        # 借序列化探测能否 dump
        _ = json.dumps(value)
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v) for v in value]
        return repr(value)
    return value


def _content_to_str(content: Any) -> str:
    """content 可能是 str 或多模态 list"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # 思考过程另提，正文跳过
                if block.get("type") in ("reasoning", "thinking"):
                    continue
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                else:
                    parts.append(f"[{block.get('type', 'unknown')}]")
        return "".join(parts)
    return str(content)


def _extract_thinking(msg: Any) -> str:
    """提取思考过程，兼容各家字段位置"""
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
            # OpenAI Responses 风格
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

    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for t in found:
        if t not in seen:
            seen.add(t)
            uniq.append(t)

    return "\n".join(uniq)


def _message_to_dict(msg: Any) -> dict[str, Any]:
    """message 转 JSON 安全 dict，调试页与保存共用"""
    data: dict[str, Any] = {
        "id": getattr(msg, "id", None),
        "role": getattr(msg, "type", None),
        "class": type(msg).__name__,
        "content": _content_to_str(getattr(msg, "content", "")),
    }

    # 工具消息名，非空才带
    name = getattr(msg, "name", None)
    if name:
        data["name"] = name

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
    """取该 agent 当前生效的 system prompt"""
    ins = agentMgr.get_agent_ins(agent_name)
    if ins is None:
        return ""

    piecer = getattr(ins, "promptPiecer", None)
    if piecer is None:
        return ""

    try:
        return piecer.get_full_text() or ""
    except Exception as e:
        print(f"[ConversationSave] 读取 {agent_name} 的 system prompt 失败: {e}")
        return ""


def build_context_snapshot(agent_name: str, thread_id: str) -> dict[str, Any] | None:
    """读 agent 当前上下文；无 agent 返 None"""
    agent = agentMgr.get_agent(agent_name)
    if agent is None:
        return None

    values: dict[str, Any] = {}
    try:
        state = agent.get_state({"configurable": {"thread_id": thread_id}})
        if state and state.values:
            values = state.values
    except Exception as e:
        print(f"[ConversationSave] 读取 {agent_name}/{thread_id} 状态失败: {e}")

    system_prompt = _get_system_prompt(agent_name)

    raw_messages = values.get("messages", [])
    messages = [_message_to_dict(m) for m in raw_messages if hasattr(m, "type")]

    # 其余 channel 供调试页排查，保存器不用
    extras: dict[str, Any] = {}
    for key, value in values.items():
        if key == "messages":
            continue
        extras[key] = _json_safe(value)

    last = messages[-1] if messages else None
    # 末条长度 + prompt 哈希，感知内容变化
    prompt_hash = hash(system_prompt)
    # 带目标本身，避免跨会话误判
    scope = f"{agent_name}/{thread_id}"
    signature = (
        f"{scope}|{len(messages)}|{last['id']}|{last['role']}|{len(last['content'])}|{prompt_hash}"
        if last
        else f"{scope}|{len(messages)}|empty|{prompt_hash}"
    )

    total_tokens = 0
    if messages:  # 空列表取末条会越界
        m = messages[-1]
        usage = m.get("usage")
        if isinstance(usage, dict):
            total_tokens = int(usage.get("total_tokens") or 0)
        

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


# ------------------------------------------------------------ 保存的数据结构


@dataclass
class SingleChat:
    """一条消息；可选栏位空则序列化时省略"""

    role: str = ""
    content: str = ""
    note: str = ""  # 人工备注
    thinking: str = ""  # 思考过程
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # 工具调用
    tool_call_id: str = ""  # 对应调用 id
    tool_name: str = ""  # 工具名
    usage: dict[str, Any] = field(default_factory=dict)  # token 用量

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.note:
            data["note"] = self.note
        if self.thinking:
            data["thinking"] = self.thinking
        if self.tool_calls:
            data["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.tool_name:
            data["tool_name"] = self.tool_name
        if self.usage:
            data["usage"] = self.usage
        return data


@dataclass
class ConversationData:
    content: list[SingleChat] = field(default_factory=list)  # json数据
    agent_name: str = ""
    thread_id: str = ""
    start_time_stamp: int = 0  # 对话开始时间戳
    end_time_stamp: int = 0  # 对话结束时间戳
    system_prompt: str = ""  # 保存时的 system prompt
    total_tokens: int = 0  # 末条消息 token 总量


@dataclass
class _SessionState:
    """当前会话写入状态，重启后重置"""

    start_time_stamp: int
    end_time_stamp: int
    file_path: str | None = None  # 当前会话文件，用于备份上一版


def _dict_to_single_chat(m: dict[str, Any]) -> SingleChat:
    """快照 dict 转 SingleChat，两个入口共用"""
    usage = m.get("usage") or {}
    if not isinstance(usage, dict):
        # 降级字符串包一层，保持栏位类型
        usage = {"raw": usage}
    return SingleChat(
        role=str(m.get("role") or ""),
        content=str(m.get("content") or ""),
        thinking=str(m.get("thinking") or ""),
        tool_calls=list(m.get("tool_calls") or []),
        tool_call_id=str(m.get("tool_call_id") or ""),
        tool_name=str(m.get("name") or ""),
        usage=usage,
    )


class ConversationSaver:
    def __init__(self):
        self.save_cd = 2  # 保存最小间隔秒数
        self._lock = threading.RLock()
        self._sessions: dict[str, _SessionState] = {}
        self._last_save_times: dict[str, float] = {}
        # 完整记录：重启后重新累计
        self._history: dict[str, list[SingleChat]] = {}
        self._logged_ids: dict[str, set[str]] = {}  # 已入记录的 id，用于去重
        self._summary_ids: dict[str, set[str]] = {}  # 总结消息 id 黑名单
        self._init_event()
        # 退出前强制补存最后一轮
        atexit.register(self._flush_at_exit)

    def _init_event(self):
        # 监听对话结束
        eventDispatch.register(BrainEvent.after_content_respone, self.save_all_conversation)
        # 监听总结裁剪，捞回被裁消息
        eventDispatch.register(
            SummarizationArchiveEvent.archived, self._on_summarization_archived
        )

    def save_all_conversation(self, data: Any = None, force: bool = False):
        # 保存当前momo以及momo-internal的所有上下文信息，
        self.save_agent_content(MOMO_AGENT_NAME, force)
        self.save_agent_content(MOMO_INTERNAL_AGENT_NAME, force)

    def save_agent_content(self, agent_name: str, force: bool = False):
        # 提取包括：
        # 正常对话；
        # 思考过程
        # 工具调用；
        # 最终token使用情况
        # 数据最终保存为json格式，路径为Data/Conversation/agent_name/start_time_stamp-end_time_stamp.json
        try:
            with self._lock:
                now = time.time()
                if not force and now - self._last_save_times.get(agent_name, 0.0) < self.save_cd:
                    return

                # thread_id 与 agent_name 同名
                snapshot = build_context_snapshot(agent_name, agent_name)
                if snapshot is None:  # agent 未注册
                    return
                if not snapshot.get("messages"):  # 无内容可存
                    return

                # 快照新消息灌入完整记录
                self._ingest_messages(agent_name, snapshot.get("messages", []))

                session = self._get_or_create_session(agent_name, now)
                data = ConversationData(
                    content=list(self._history.get(agent_name, [])),
                    agent_name=agent_name,
                    thread_id=str(snapshot.get("thread_id") or agent_name),
                    start_time_stamp=session.start_time_stamp,
                    end_time_stamp=session.end_time_stamp,
                    system_prompt=str(snapshot.get("system_prompt") or ""),
                    total_tokens=int(snapshot.get("total_tokens") or 0),
                )
                self._write_snapshot(agent_name, data)
                self._last_save_times[agent_name] = now
        except Exception as e:
            # 保存失败不连带主循环
            print(f"【对话保存失败】{agent_name}: {e}")

    def _ingest_messages(self, agent_name: str, msg_dicts: list[dict[str, Any]]) -> None:
        """灌入完整记录：按 id 去重，跳过总结/status 消息"""
        history = self._history.setdefault(agent_name, [])
        logged = self._logged_ids.setdefault(agent_name, set())
        summary_ids = self._summary_ids.setdefault(agent_name, set())

        for m in msg_dicts:
            mid = m.get("id")
            if mid is not None and (mid in logged or mid in summary_ids):
                continue
            if _STATUS_MARKER in str(m.get("content") or ""):
                continue
            history.append(_dict_to_single_chat(m))
            if mid is not None:
                logged.add(mid)

    def _get_or_create_session(self, agent_name: str, now: float) -> _SessionState:
        session = self._sessions.get(agent_name)
        if session is not None and now - session.end_time_stamp > SESSION_GAP_SECONDS:
            session = None  # 静默太久，开启新会话
        if session is None:
            now_stamp = int(now)
            session = _SessionState(start_time_stamp=now_stamp, end_time_stamp=now_stamp)
            self._sessions[agent_name] = session
        session.end_time_stamp = int(now)
        return session

    def _write_snapshot(self, agent_name: str, data: ConversationData) -> None:
        agent_dir = os.path.join(CONVERSATION_DIR, agent_name)
        os.makedirs(agent_dir, exist_ok=True)

        new_path = os.path.join(
            agent_dir, f"{data.start_time_stamp}-{data.end_time_stamp}.json"
        )
        session = self._sessions[agent_name]

        # 旧版轮转进备份槽位
        old_path = session.file_path
        if old_path and os.path.exists(old_path):
            bak_path = self._rotate_backups(agent_dir, data.start_time_stamp)
            os.replace(old_path, bak_path)

        # 临时文件原子替换；空栏位不落键
        tmp_path = new_path + ".tmp"
        payload = {
            "agent_name": data.agent_name,
            "thread_id": data.thread_id,
            "start_time_stamp": data.start_time_stamp,
            "end_time_stamp": data.end_time_stamp,
            "system_prompt": data.system_prompt,
            "total_tokens": data.total_tokens,
            "content": [chat.to_dict() for chat in data.content],
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, new_path)

        session.file_path = new_path
        # print(f"【保存对话】{agent_name}: {os.path.basename(new_path)}")

    def _rotate_backups(self, agent_dir: str, start_time_stamp: int) -> str:
        """备份槽位后移一格，返回 .bak.1 路径"""
        base = os.path.join(agent_dir, str(start_time_stamp))

        # 删最旧，腾位置
        oldest = f"{base}.bak.{BACKUP_KEEP}"
        if os.path.exists(oldest):
            os.remove(oldest)
        # 其余后移一格
        for i in range(BACKUP_KEEP - 1, 0, -1):
            src = f"{base}.bak.{i}"
            if os.path.exists(src):
                os.replace(src, f"{base}.bak.{i + 1}")

        return f"{base}.bak.1"

    def _on_summarization_archived(self, data: Any) -> None:
        """裁剪事件监听，单参数 data"""
        if not isinstance(data, SummarizationArchived):
            return
        self.archive_summarized(
            data.agent_name, data.cropped_messages, data.summary_message
        )

    def archive_summarized(
        self,
        agent_name: str,
        cropped_messages: list[Any],
        summary_message: Any = None,
    ) -> None:
        """被裁消息灌入记录；总结只记 id 不进记录"""
        try:
            with self._lock:
                # 先记黑名单再灌消息
                if summary_message is not None:
                    mid = getattr(summary_message, "id", None)
                    if mid:
                        self._summary_ids.setdefault(agent_name, set()).add(mid)

                cropped_dicts = [_message_to_dict(m) for m in cropped_messages]
                self._ingest_messages(agent_name, cropped_dicts)

                if cropped_dicts:
                    print(
                        f"【归档裁剪】{agent_name}: 被裁{len(cropped_dicts)}条"
                        "并入完整记录，总结不计入"
                    )
        except Exception as e:
            # 归档失败不影响主流程
            print(f"【归档失败】{agent_name}: {e}")

    def _flush_at_exit(self) -> None:
        try:
            self.save_all_conversation(force=True)
        except Exception:
            pass


conversation_saver = ConversationSaver()
