import asyncio
import sys
from pathlib import Path

from langchain_core.messages import AIMessageChunk, ToolMessage

from LangChain.Context import get_history


# LangChain 等业务包位于仓库根目录的 pyScripts/ 下，
# 从任意目录运行本脚本前，先把它加入模块搜索路径
_PYSCRIPTS = Path(__file__).resolve().parents[2] / "pyScripts"
if str(_PYSCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PYSCRIPTS))

from Core.Action import call_tool, call_tool_by_langChain
from LangChain.Agent import agentMgr
from LangChain.Chain import chainMgr

MAIN_AGENT = "momo_test"
INTERNAL_AGENT = "momo_internal"

main_agent = agentMgr.get_agent(agent_name=MAIN_AGENT)
assert main_agent is not None, "agent 'momo_test' 未注册，请检查 LangChain/Agent.py"

for question in [
    "我们要开始读书了。",
    """阅读原文：【“也许我们不认为自己的谈话方式是“暴力的”，但我们的语言确实
常常引发自己和他人的痛苦。”
运用非暴力沟通聆听彼此心灵深处的需要，我们将以全新的眼光看
待人际关系。
当我们真诚助人时，我们丰富他人生命的愿望得到了满足。我们的
行为，是出于由衷的喜悦。
非暴力沟通的四个要素：观察，感受，需要，请求。它鼓励倾听，
培育尊重与爱。】根据当前状态，看看有没有感想发表，有则发表，没有则静默。""",
]:
    res = main_agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": MAIN_AGENT}},
    )
    print(res["messages"][-1].content)
    print("=" * 20)

# print(agentMgr.get_agent_message("momo_test","momo_test"))
# messages = agentMgr.get_agent_message("momo_test","momo_test")
# if messages:
#     for message in messages:
#         print(message.type)


async def _after_response():
    agent = agentMgr.get_agent("momo_internal")
    if not agent:
        raise Exception("momo internal agent not found")

    global main_agent

    main_messages = agentMgr.get_agent_message("momo", "momo")
    if not main_messages:
        return
    astream = agent.astream(
        {"messages": main_messages},
        config={"configurable": {"thread_id": "momo_internal"}},
        stream_mode=["messages", "updates"],
    )
    try:
        async for chunk in astream:
            mode, data = chunk
            if mode == "messages":
                message_chunk, metadata = data
                if metadata.get("langgraph_node", "") != "model":
                    continue
                if not isinstance(message_chunk, AIMessageChunk):
                    continue

                if message_chunk.tool_calls:
                    for tool_call in message_chunk.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        print(f"momo_internal 尝试调用工具:{tool_name}:{tool_args}")

                content = message_chunk.content
                print(content, end="", flush=True)
            elif mode == "updates":
                print(f"\nMomo的内心做出了行动：{data}")
                pass
    except Exception as e:
        print(e)


last_reaction_index = 0  # 为了方便计算，运行时的表示的idx是从1开始的


async def _after_response_by_chain():
    chain = chainMgr.get_chain(INTERNAL_AGENT)
    if not chain:
        raise Exception("momo internal chain not found")

    main_messages = agentMgr.get_agent_message(MAIN_AGENT, MAIN_AGENT)
    if not main_messages:
        return

    global last_reaction_index
    history_text = "\n".join(
        f"{msg.type}: {msg.content}" for msg in main_messages[last_reaction_index:]
    )
    last_reaction_index = len(main_messages)
    print(f"\n 内心分析的上下文：\n{history_text}")

    res = await chain.ainvoke(
        {"analysis_messages": history_text},
        config={"configurable": {"session_id": INTERNAL_AGENT}},
    )

    print("\n【Momo内心活动记录】")
    if res.content:
        print(res.content)

    if res.tool_calls:
        history = get_history(INTERNAL_AGENT)
        # 手动调用tool
        results = call_tool_by_langChain(res.tool_calls)

        for tool_call in res.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            print(f"momo_internal_test 尝试调用工具:{tool_name}:{tool_args}")

            # 手动把tool结果加入上下文
            result = results.get("tool_id", "")
            history.add_message(ToolMessage(content=result, tool_call_id=tool_id))

        print(history)


asyncio.run(_after_response_by_chain())
