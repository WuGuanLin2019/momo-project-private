from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from LangChain.Context import system_prompt
from LangChain.LLM import LLMMgr

conversation = [
    HumanMessage(content="苹果好吃吗？"),
    AIMessage(content="好吃的。"),
]

# llm = ChatOllama(
#     model="gemma3:1b",
#     temperature=0.7,
# )

llm = LLMMgr.get_llm("deepseek")

prompts = ChatPromptTemplate(
    [
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="conversation"),
        ("human", "{input}"),
    ],
)

chain = prompts | llm

cache = {}


def get_history(s_id):
    if s_id not in cache:
        cache[s_id] = InMemoryChatMessageHistory()

    return cache[s_id]


chain_with_history = RunnableWithMessageHistory(
    chain, get_history, input_messages_key="input", history_messages_key="conversation"
)

res = chain_with_history.invoke({"input": "苹果好吃吗？"}, config={"configurable": {
    "session_id":"momo"
}})
print(res.content)
print("=" *20)

# res = chain_with_history.invoke({"input": "它是什么颜色的？"}, config={"configurable": {
#     "session_id":"momo1"
# }})
# print(res.content)
# print("=" *20)

res = chain_with_history.invoke({"input": "它是什么颜色的？"}, config={"configurable": {
    "session_id":"momo"
}})
print(res.content)
print("=" *20)

print(get_history("momo"))