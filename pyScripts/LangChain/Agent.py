from collections.abc import Awaitable
from re import A
from typing import Any, Callable, TypeAlias
from langchain.tools import BaseTool
from dataclasses import dataclass
from langgraph.pregel.main import Input, Output
from typing_extensions import override

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelRequest,
    ModelResponse,
    SummarizationMiddleware,
)
from langchain.agents.middleware.types import (
    AgentState,
    InputAgentState,
    OutputAgentState,
)

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph, Runnable
from Brain.Context.AgentStatusMgr import AgentStatusPiecer, StatusData, AGENT_STATUS_KEY
from Brain.Context.PromptMgr import PromptData, PromptPiecer
from Brain.Context.ToolMgr import ToolData, ToolPiecer
from LangChain.LLM import LLMMgr
from LangChain.Context import internal_system_prompt, system_prompt
from Core.Action import (
    InternalTools,
    MainTools,
    ToolsWithKeepMessage,
    get_all_tools_for_agent,
)
from LangChain.AgentMeta import AgentMetaContext


Agent: TypeAlias = CompiledStateGraph[
    AgentState[Any], AgentMetaContext | None, InputAgentState, OutputAgentState[Any]
]


@dataclass
class AgentIns:
    name: str
    agent: Agent
    promptPiecer: PromptPiecer = PromptPiecer()
    toolPiecer: ToolPiecer = ToolPiecer()
    agentStatusPiecer: AgentStatusPiecer | None = None


class AgentMgr:
    def __init__(self):
        self.agents: dict[str, AgentIns] = {}

    def get_agent(self, agent_name: str) -> Agent | None:
        if agent_name in self.agents:
            return self.agents[agent_name].agent
        return None

    def get_agent_ins(self, agent_name: str) -> AgentIns | None:
        if agent_name in self.agents:
            return self.agents[agent_name]
        return None

    def add_agent_ins(
        self,
        agent_name: str,
        agent: Agent,
        prompt_piecer: PromptPiecer,
        tool_piecer: ToolPiecer,
        status_piecer: AgentStatusPiecer | None = None,
    ) -> None:
        agent_ins = AgentIns(
            agent_name, agent, prompt_piecer, tool_piecer, status_piecer
        )
        self.agents[agent_name] = agent_ins

    def get_agent_message(self, agent_name: str, thread_id: str):
        agent = self.get_agent(agent_name)
        if not agent or not agent.config:
            return None
        try:
            state = agent.get_state({"configurable": {"thread_id": thread_id}})
            if state and state.values:
                # 提取消息列表（过滤掉系统消息，因为 momo_internal 有自己的系统提示）
                all_messages = state.values.get("messages", [])
                # 过滤掉 role 为 system 的消息
                filtered_messages = [
                    msg
                    for msg in all_messages
                    if msg.type != "system"
                    if hasattr(msg, "type")
                ]
                return filtered_messages
        except Exception as e:
            print(f"获取状态失败: {e}")


agentMgr = AgentMgr()
checkpointer = InMemorySaver()
SUMMARY_PROMPT = """ 
你是一个对话上下文总结器。

你的任务是压缩历史对话，以便后续模型继续自然地进行对话。

请使用中文总结。

请重点保留：

1. 用户明确表达的长期目标
2. 用户明确告诉模型的个人偏好、事实和重要信息
3. 已经完成的任务和已经确定的结论
4. 当前正在进行的任务
5. 尚未解决的问题
6. 对后续回答非常重要的上下文关系

不要记录：
- 无意义的寒暄
- 重复内容
- 与当前任务无关的细节
- 对用户意图的无根据推测

总结应简洁，但必须保留后续继续对话所需要的信息。

请按照以下格式输出：

## 会话目标
...

## 重要上下文
...

## 已完成
...

## 未完成
...

## 下一步
...

<messages>
Messages to summarize:
{messages}
</messages>
"""

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from Brain.Emotion.EmotionMgr import emotionMgr

MomoContextEditorMiddleware = ContextEditingMiddleware(
    edits=[
        ClearToolUsesEdit(
            trigger=1000,  # 当对话 Token 数达到 2000 时触发
            keep=3,  # 保留最近 3 条工具结果，更早的会被清理
            clear_tool_inputs=True,  # 不清理 AI 消息中的工具调用参数
            # exclude_tools=[func.name for func in ToolsWithKeepMessage],      # 不排除任何工具
            placeholder="[cleared]",  # 被清理的内容用此占位符替换
        ),
    ],
)


class MomoSystemPromptMiddleware(AgentMiddleware[AgentState[Any], ContextT, Any]):
    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name

    @override
    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        ins = agentMgr.get_agent_ins(self.agent_name)
        if ins:
            p = ins.promptPiecer.get_full_text()
            s_m = SystemMessage(p)
            return handler(request.override(system_message=s_m))
        return handler(request)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        ins = agentMgr.get_agent_ins(self.agent_name)
        if ins:
            p = ins.promptPiecer.get_full_text()
            s_m = SystemMessage(p)
            return await handler(request.override(system_message=s_m))
        return await handler(request)


class MomoStateMiddleware(AgentMiddleware[AgentState[Any], ContextT, Any]):
    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name

    @override
    def before_model(
        self, state: AgentState[Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:

        ownAgent = agentMgr.get_agent_ins(self.agent_name)
        if not ownAgent:
            print(f"agent {self.agent_name} not found")
            return None
        if not ownAgent.agentStatusPiecer:
            return None
            
        status_str = ownAgent.agentStatusPiecer.get_full_status()
        if not status_str:
            return None

        # print(f"\nstatus_str: {status_str}\n")
            
        state_mes = HumanMessage(content=status_str)
        remove_mes_ids = [
            m.id
            for m in state["messages"]
            if isinstance(m, HumanMessage)
            and isinstance(m.content, str)
            and f"<{AGENT_STATUS_KEY}>" in m.content
        ]

        return {
            "messages": [
                *[RemoveMessage(id=i) for i in remove_mes_ids if i is not None],
                state_mes,
            ]
        }


class MomoDynamicToolMiddleware(AgentMiddleware[AgentState[Any], ContextT, Any]):
    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name

    @override
    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        ins = agentMgr.get_agent_ins(self.agent_name)
        if ins:
            tools = list[BaseTool | dict[str, Any]](ins.toolPiecer.get_full_tool())
            return handler(request.override(tools=tools))
        return handler(request)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        ins = agentMgr.get_agent_ins(self.agent_name)
        if ins:
            tools = list[BaseTool | dict[str, Any]](ins.toolPiecer.get_full_tool())
            return await handler(request.override(tools=tools))
        return await handler(request)


MOMO_INTERNAL_AGENT_NAME = "momo_internal"
MOMO_AGENT_NAME = "momo"
MomoPromptPiecer = PromptPiecer()
MomoPromptPiecer.add(PromptData("system", system_prompt))
MomoToolPiecer = ToolPiecer()
MomoToolPiecer.add(ToolData("main", MainTools))

MomoAgentStatusPiecer = AgentStatusPiecer()
MomoAgentStatusPiecer.add(
    StatusData("Emotion", emotionMgr.get_emotion(MOMO_INTERNAL_AGENT_NAME).get_emotion_str)
)

agentMgr.add_agent_ins(
    agent_name=MOMO_AGENT_NAME,
    agent=create_agent(
        model=LLMMgr.get_llm("main_agent"),
        tools=get_all_tools_for_agent(),
        system_prompt=MomoPromptPiecer.get_full_text(),
        middleware=[
            MomoSystemPromptMiddleware(MOMO_AGENT_NAME),
            MomoDynamicToolMiddleware(MOMO_AGENT_NAME),
            MomoStateMiddleware(MOMO_AGENT_NAME),
            SummarizationMiddleware(
                model=LLMMgr.get_llm("summary"),
                trigger=("tokens", 10000),
                keep=("tokens", 4000),
                summary_prompt=SUMMARY_PROMPT,
            ),
        ],
        checkpointer=checkpointer,
        context_schema=AgentMetaContext,
    ),
    tool_piecer=MomoToolPiecer,
    prompt_piecer=MomoPromptPiecer,
    status_piecer=MomoAgentStatusPiecer,
)


MOMO_TEST_AGENT_NAME = "momo_test"
agentMgr.add_agent_ins(
    "momo_test",
    create_agent(
        model=LLMMgr.get_llm("fallBack"),
        tools=get_all_tools_for_agent(),
        system_prompt=MomoPromptPiecer.get_full_text(),
        middleware=[
            MomoSystemPromptMiddleware(MOMO_TEST_AGENT_NAME),
            MomoStateMiddleware(MOMO_TEST_AGENT_NAME),
            MomoDynamicToolMiddleware(MOMO_TEST_AGENT_NAME),
            SummarizationMiddleware(
                model=LLMMgr.get_llm("fallBack"),
                trigger=("tokens", 4096),
                keep=("tokens", 3500),
                summary_prompt=SUMMARY_PROMPT,
            ),
        ],
        checkpointer=checkpointer,
        context_schema=AgentMetaContext,
    ),
    MomoPromptPiecer,
    MomoToolPiecer,
)

# 显式标注 ContextT 与该 agent 的 context_schema 对齐：
# 中间件若在模块级预先构造，ContextT 会落到默认值 None（见 langgraph.typing），
# 而 create_agent 求解出的是 `AgentMetaContext | None`，泛型不变会判定不兼容。
MomoInternalContextEditorMiddleware: ContextEditingMiddleware[
    Any, AgentMetaContext | None
] = ContextEditingMiddleware(
    edits=[
        ClearToolUsesEdit(
            trigger=4000,  # 当对话 Token 数达到 2000 时触发
            keep=10,  # 保留最近 3 条工具结果，更早的会被清理
            clear_tool_inputs=False,  # 不清理 AI 消息中的工具调用参数
            exclude_tools=[
                func.name for func in ToolsWithKeepMessage
            ],  # 不排除任何工具
            placeholder="[cleared]",  # 被清理的内容用此占位符替换
        ),
    ],
)

internalCheckpointer = InMemorySaver()
temPromptPiecer = PromptPiecer()
temPromptPiecer.add(PromptData("system", internal_system_prompt))
temToolPiecer = ToolPiecer()
temToolPiecer.add(ToolData("main", InternalTools))
agentMgr.add_agent_ins(
    MOMO_INTERNAL_AGENT_NAME,
    create_agent(
        model=LLMMgr.get_llm("internal_agnet"),
        tools=temToolPiecer.get_full_tool(),
        system_prompt=temPromptPiecer.get_full_text(),
        middleware=[
            MomoInternalContextEditorMiddleware,
            SummarizationMiddleware(
                model=LLMMgr.get_llm("summary"),
                trigger=("messages", 35),
                keep=("messages", 10),
                summary_prompt=SUMMARY_PROMPT,
            ),
        ],
        checkpointer=internalCheckpointer,
        context_schema=AgentMetaContext,
    ),
    temPromptPiecer,
    temToolPiecer,
)
