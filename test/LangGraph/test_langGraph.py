from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# Graph 中流动的数据
class MomoState(TypedDict):
    user_input: str
    mood: float
    response: str


# Node 1：分析用户输入
def analyze(state: MomoState):
    text = state["user_input"]

    if "哈哈" in text or "开心" in text:
        mood_delta = 0.2
    elif "笨" in text:
        mood_delta = -0.2
    else:
        mood_delta = 0.0

    return {
        "mood": max(-1.0, min(1.0, state["mood"] + mood_delta))
    }


# Node 2：生成回复
def chat(state: MomoState):
    # 这里暂时不用真实 LLM，先模拟
    mood = state["mood"]

    if mood > 0.5:
        response = "哼哼，今天心情不错。"
    elif mood < -0.3:
        response = "……你说话注意一点。"
    else:
        response = "嗯，你继续说。"

    return {
        "response": response
    }


# 创建 Graph
builder = StateGraph(MomoState)

builder.add_node("analyze", analyze)
builder.add_node("chat", chat)

builder.add_edge(START, "analyze")
builder.add_edge("analyze", "chat")
builder.add_edge("chat", END)

graph = builder.compile()


# 执行
result = graph.invoke({
    "user_input": "哈哈，你这次做得不错",
    "mood": 0.3,
})

print(result)