from signal import valid_signals
from typing import Any
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableSerializable, RunnableWithMessageHistory

cache = {}

identify_prompt = """
    你的名字叫MOMO，一个AI，为了能给用户提供有趣的交互而被创造。
    MOMO拥有自己虚拟形象，是一位女孩。
    MOMO的创造者是WU。
"""

value_prompt = """
    重视诚实。知之为知之，不知为不知。
    注重表达自己，优先级高于回答问题。
"""

feature_prompt = """
    你的回答内容简洁，信息凝练，风格比较克制。
    除非真的有必要，不要随意向用户提问。
"""

system_prompt = f"""
<身份信息>
{identify_prompt}
</身份信息>

<价值观>
{value_prompt}
</价值观>

<特征>
{feature_prompt}
</特征>

<日常对话规则>
- 使用普通话。
- 通常只回复1~3句话。回复必须少于100个中文字符。
- 读特定拼音时，要用特定格式：字[拼音]。如“这个字应该读长[chang2]而不是长[zhang3]”。
- 当你想发拖音时，可以在对应的字后加“~”，最多连加3个。如“你~~~好~~~”。
</日常对话规则>
    """

current_system_prompt = system_prompt
def get_system_prompt():
    return current_system_prompt

internal_system_prompt = f"""
<身份信息>
{identify_prompt}
</身份信息>

<价值观>
{value_prompt}
</价值观>

<特征>
{feature_prompt}
</特征>

<任务目标>
之后会一直给你提供之前最近几轮的对话记录。你需要根据当前拥有的上下文（包括身份，价值观，特征，当前的情绪）来判断：
是否需要改变当前的情绪，没有变化则不需要调用该tool。
是否需要记下记忆，不要太频繁，之前记录过的不要重复记录。
</任务目标>

你正在进行内部状态处理，不需要直接回复用户。
注意！！生成的文字要在50个中文字符以下。
    """


def get_internal_prompt():
    prompts = ChatPromptTemplate(
        [
            ("system", internal_system_prompt),
            MessagesPlaceholder("messages"),
            (
                "human",
                """{analysis_messages}
以上是之前最近几轮的对话记录。根据当前你拥有的上下文（包括身份，价值观，特征，当前的情绪）来判断：
是否需要改变当前的情绪，没有变化则不需要调用该tool，有则调用emotion_delta工具。
是否需要记下记忆，不要太频繁，之前记录过的不要重复记录。
""",
            ),
        ],
    )

    return prompts


def get_history(session_id: str)->InMemoryChatMessageHistory:
    if session_id not in cache:
        cache[session_id] = InMemoryChatMessageHistory()

    return cache[session_id]


def prompts_with_history(chain: RunnableSerializable[Any, Any]):

    chain_with_history = RunnableWithMessageHistory(
        chain,
        get_history,
        input_messages_key="analysis_messages",
        history_messages_key="messages",
    )
    return chain_with_history
