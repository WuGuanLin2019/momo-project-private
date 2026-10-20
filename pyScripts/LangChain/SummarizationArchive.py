"""裁剪时派发事件：上报被裁消息与总结消息。

被裁内容只存在于移除前一刻；子类化父中间件，
解析出被裁集合后经 EventDispatch 派发。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.middleware.types import AgentState
from langchain.chat_models import BaseChatModel
from langchain_core.messages import AnyMessage, RemoveMessage
from langgraph.runtime import Runtime
from typing_extensions import override

from LangChain.AgentMeta import AgentMetaContext
from Utils.EventDispatch import eventDispatch


class SummarizationArchiveEvent:
    # 与 BrainEvent 等同级的事件常量
    archived = "SummarizationArchiveEvent.archived"


@dataclass
class SummarizationArchived:
    """一次裁剪事件的载荷"""

    agent_name: str
    cropped_messages: list[AnyMessage]
    summary_message: Any = None


def _is_summary_message(msg: Any) -> bool:
    kwargs = getattr(msg, "additional_kwargs", None)
    return isinstance(kwargs, dict) and kwargs.get("lc_source") == "summarization"


# 泛型显式标注，参数为 (ResponseT, ContextT)
class ArchivingSummarizationMiddleware(
    SummarizationMiddleware[Any, AgentMetaContext | None]
):
    """总结裁剪的同一时刻派发被裁消息与总结消息"""

    def __init__(self, agent_name: str, model: str | BaseChatModel, **kwargs: Any) -> None:
        super().__init__(model, **kwargs)
        self.agent_name = agent_name

    @override
    def before_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        messages = state["messages"]
        # 父类逻辑原样执行，行为不变
        update = super().before_model(state, runtime)
        self._archive_from_update(messages, update)
        return update

    @override
    async def abefore_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        messages = state["messages"]
        update = await super().abefore_model(state, runtime)
        self._archive_from_update(messages, update)
        return update

    def _archive_from_update(
        self, messages: list[Any], update: dict[str, Any] | None
    ) -> None:
        if not update:
            return

        new_messages = update.get("messages") or []
        # 去掉删除指令，余下是写回的消息
        kept = [m for m in new_messages if not isinstance(m, RemoveMessage)]
        kept_ids = {m.id for m in kept}

        cropped = [m for m in messages if m.id not in kept_ids]
        summary_message = next((m for m in kept if _is_summary_message(m)), None)

        if not cropped and summary_message is None:
            return
        if summary_message is None:
            print(
                f"[SummarizationArchive] {self.agent_name}: 未识别到总结消息(lc_source)，"
                "仅归档被裁消息"
            )

        # 总结消息无 id，先补一个（reducer 会尊重），
        # 消费方靠它在后续快照里认出并跳过
        if summary_message is not None and getattr(summary_message, "id", None) is None:
            summary_message.id = str(uuid.uuid4())

        try:
            eventDispatch.dispatch(
                SummarizationArchiveEvent.archived,
                SummarizationArchived(self.agent_name, cropped, summary_message),
            )
        except Exception as e:
            # 任何异常不许冒泡进模型调用
            print(f"[SummarizationArchive] {self.agent_name}: 派发归档事件失败: {e}")
