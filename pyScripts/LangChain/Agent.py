from typing import Any, TypeAlias

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.middleware.types import AgentState, InputAgentState, OutputAgentState
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from LangChain.LLM import LLMMgr
from LangChain.Context import internal_system_prompt, system_prompt
from Core.Action import InternalTools, MainTools, Tools

# create_agent(...) 编译后的智能体图类型（即 langgraph 的 CompiledStateGraph）。
# 本仓库未配置 context_schema，故 ContextT 为 None；ResponseT 未用 response_format，取 Any。
Agent: TypeAlias = CompiledStateGraph[
    AgentState[Any], None, InputAgentState, OutputAgentState[Any]
]


class AgentMgr:
    def __init__(self):
        self.agents: dict[str, Agent] = {}

    def get_agent(self, agent_name: str) -> Agent | None:
        if agent_name in self.agents:
            return self.agents[agent_name]
        return None

    def add_agent(self, agent_name: str, agent: Agent) -> None:
        self.agents[agent_name] = agent

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
                # filtered_messages = [msg for msg in all_messages if msg.type != "system" if hasattr(msg, 'type')]
                return all_messages
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
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime
from langgraph.types import StateT
from langgraph.typing import ContextT
from Brain.Emotion.EmotionMgr import emotionMgr




class MomoStateMiddleware(AgentMiddleware):
    def before_model(self, state: StateT, runtime: Runtime[ContextT]):
        momo_emotion = emotionMgr.get_emotion("Momo")
        # print(f"momo_emotion: {momo_emotion.get_emotion_str()}")
        return {
            "messages": [
                SystemMessage(
                    content=f"""
【当前状态】
{momo_emotion.get_emotion_str()}
这些数值是MOMO当前连续变化的内部状态。
这些状态只是用来影响你表达的语气、措辞和行为，不需要直白地说出状态本身。
                    """
                )
            ]
        }


agentMgr.add_agent(
    "momo",
    create_agent(
        model=LLMMgr.get_llm("deepseek"),
        tools=MainTools,
        system_prompt=system_prompt,
        middleware=[
            MomoStateMiddleware(),
            SummarizationMiddleware(
                model=LLMMgr.get_llm("deepseek"),
                trigger=("tokens", 16000),
                keep=("tokens", 8000),
                summary_prompt=SUMMARY_PROMPT,
            ),
        ],
        checkpointer=checkpointer,
    ),
)

agentMgr.add_agent(
    "momo_test",
    create_agent(
        model=LLMMgr.get_llm("qwen3b"),
        tools=MainTools,
        system_prompt=system_prompt,
        middleware=[
            MomoStateMiddleware(),
            SummarizationMiddleware(
                model=LLMMgr.get_llm("qwen3b"),
                trigger=("tokens", 3072),
                keep=("tokens", 2048),
                summary_prompt=SUMMARY_PROMPT,
            ),
        ],
        checkpointer=checkpointer,
    ),
)


agentMgr.add_agent(
    "momo_internal",
    create_agent(
        model=LLMMgr.get_llm("deepseek"),
        tools=InternalTools,
        system_prompt=internal_system_prompt,
        checkpointer=checkpointer,
    ),
)
