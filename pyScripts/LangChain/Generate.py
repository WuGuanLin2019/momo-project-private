import asyncio
import threading
import time

from langchain.agents import AgentState
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from numba.cloudpickle import instance
from Core.Action import InternalTools, call_tool_by_langChain
from LangChain.LLM import LLMMgr
from collections.abc import Callable

from Core.State import GenerationState
from LangChain.Context import get_history, get_internal_prompt, prompts_with_history
from Brain.SentenceHandler import SentenceHandler
from LangChain.OutputParser import get_output_parser
from LangChain.Agent import agentMgr
from LangChain.Chain import chainMgr


MAIN_AGENT = "momo"
INTERNAL_AGENT = "momo_internal"


def _agent_stream(inputData: str, check_is_current_generation, add_to_speak_queue):
    main_agent = agentMgr.get_agent(MAIN_AGENT)
    runable = main_agent
    if not runable:
        raise Exception("runable not found")

    start_time = time.time()
    end_time = 0

    sentenceHandler = SentenceHandler()
    stream = runable.stream(
        {"messages": [{"role": "user", "content": inputData}]},
        config={"configurable": {"thread_id": MAIN_AGENT}},
        stream_mode=["messages", "updates"],
    )

    try:
        for chunk in stream:
            if end_time == 0:
                end_time = time.time()
                print(f"首句生成耗时：{end_time - start_time}秒")

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
                        print(f"momo 尝试调用工具:{tool_name}:{tool_args}")
                content = message_chunk.content
                print(content, end="", flush=True)
                if not check_is_current_generation():
                    break

                info = {"done": False, "message": {"content": content}}
                currentSteamingText = sentenceHandler.handleStreamingText(info)
                if currentSteamingText:
                    add_to_speak_queue(currentSteamingText)
            elif mode == "updates":
                print(f"\nMomo做出了行动：{data}")
                pass
    except Exception as e:
        print(e)

    info = {"done": True, "message": {"content": ""}}
    currentSteamingText = sentenceHandler.handleStreamingText(info)
    if currentSteamingText:
        print(currentSteamingText)
        add_to_speak_queue(currentSteamingText)


last_reaction_index = 0  # 为了方便计算，运行时的表示的idx是从1开始的


def _after_response_by_chain():
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
    # print(f"\n 内心分析的上下文：\n{history_text}")

    res = chain.invoke(
        {"analysis_messages": history_text},
        config={"configurable": {"session_id": INTERNAL_AGENT}},
    )

    print("\n【Momo内心活动记录】")
    if res.content:
        print(res.content)

    if res.tool_calls:
        history = get_history(INTERNAL_AGENT)
        #手动调用tool
        results = call_tool_by_langChain(res.tool_calls)

        for tool_call in res.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            print(f"momo_internal_test 尝试调用工具:{tool_name}:{tool_args}")

            #手动把tool结果加入上下文
            result = results.get("tool_id", "")
            history.add_message(ToolMessage(content=result, tool_call_id=tool_id))


def think(
    inputData: str,
    add_to_speak_queue: Callable[[str], object],
    myGen: GenerationState,
    pipeGen: GenerationState,
) -> None:
    def check_is_current_generation():
        return pipeGen.check_is_current_generation(myGen)

    # 本轮回答生成
    _agent_stream(inputData, check_is_current_generation, add_to_speak_queue)

    # 回答后内心活动，包括情绪变化和记忆改动
    threading.Thread(target=_after_response_by_chain, daemon=True).start()
