import logging
import threading
import time
from langchain_core.messages import AIMessageChunk
from Brain.BrainEvent import BrainEvent
from Core.Input.InputDataMgr import InputData, InputDataMgr, InputSource
from Express.ExpressEvent import ExpressEvent
from LangChain.Internal.MomoInternal import add_momo_internal_task
from collections.abc import Callable

from Core.State import GenerationState
from Brain.SentenceHandler import SentenceHandler
from LangChain.Agent import MOMO_AGENT_NAME, agentMgr
from LangChain.AgentMeta import AgentMetaContext
from Utils.EventDispatch import eventDispatch


MAIN_AGENT = MOMO_AGENT_NAME
INTERNAL_AGENT = "momo_internal_test"

is_answering = False

def is_brain_answering():
    return is_answering

def _handle_anim(event_is_talking):
    # logging.info(f"event_is_talking {event_is_talking.is_set()}")
    # logging.info(f"_handle_anim  {event_is_talking.is_set()} | {is_answering}" )
    if not event_is_talking.is_set():
        if not is_answering:
            eventDispatch.dispatch(ExpressEvent.trigger_vtube_hot_key,"思考")

def _agent_stream(inputData: InputData, input_data_mgr:InputDataMgr, check_is_current_generation, add_to_speak_queue,event_is_talking:threading.Event):
    main_agent = agentMgr.get_agent(MAIN_AGENT)
    runable = main_agent
    if not runable:
        raise Exception("runable not found")

    start_time = time.time()
    end_time = 0

    global is_answering
    is_answering = False

    anim_timer = threading.Timer(2, function = _handle_anim,args = [event_is_talking])
    anim_timer.daemon = True
    anim_timer.start()

    sentenceHandler = SentenceHandler()
    stream = runable.stream(
        {"messages": [{"role": "user", "content": inputData.content}]},
        config={"configurable": {"thread_id": MAIN_AGENT}},
        stream_mode=["messages", "updates"],
        context=AgentMetaContext(MAIN_AGENT,inputData)
    )

    current_speak_task = None
    try:
        only_tool_flag = False
        only_tool_list = ["read_next_sentence"] #若调用了这些tool，直接舍弃掉文字输出

        head_flag = True

        print_think_title = False
        print_think_end = False
        print_answer_title = False
        reason_time = 0
        for chunk in stream:
            mode, data = chunk
            if mode == "messages":
                message_chunk, metadata = data
                if metadata.get("langgraph_node", "") != "model":
                    continue
                if not isinstance(message_chunk, AIMessageChunk):
                    continue

                reasoning = message_chunk.additional_kwargs.get("reasoning_content")
                
                if reasoning:
                    if not print_think_title:
                        print_think_title = True
                        reason_time = time.time()
                        print(f"\n【思考开始】")
                    # print(reasoning, end="", flush=True)
                elif print_think_title:
                    if not print_think_end:
                        print_think_end = True
                        print(f"【思考结束({round(time.time() - reason_time, 3) }s)】\n")

                #tool打印
                if message_chunk.tool_calls:
                    is_answering = True
                    for tool_call in message_chunk.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        if tool_name:
                            print(f"momo 尝试调用工具:{tool_name}:{tool_args}")
                        if tool_name in only_tool_list:
                            only_tool_flag = True

                if only_tool_flag:
                    continue

                #流式消息打印
                content = message_chunk.content
                if not print_answer_title:
                    print_answer_title = True
                    print(f"\n【回答】")
                print(content, end="", flush=True)
                if content:
                    is_answering = True

                #todo 中断时可能会在tool_call和tool_message之间，需要处理（注意一条消息多个工具调用）
                if not check_is_current_generation():
                    break

                #计时打印
                if end_time == 0:
                    end_time = time.time()
                    print(f"首句生成耗时：{round(end_time - start_time, 3) }秒")                    

                #流式句子按标点拆分直接传给TTS
                info = {"done": False, "message": {"content": content}}
                currentStreamingText = sentenceHandler.handleStreamingText(info)
                if currentStreamingText:
                    current_speak_task = add_to_speak_queue(currentStreamingText,is_head = head_flag, input_source = inputData.source)
                    head_flag = False
            elif mode == "updates":
                # print(f"\nMomo做出了行动：{data}")
                if data.get("model",""):
                    token_data = data["model"]["messages"][-1].usage_metadata
                    # print(f"\ntoken统计：{token_data}")
                
                pass

    except Exception as e:
        import traceback
        print(f"\n[{threading.current_thread().name}] 生成过程异常：{e}", flush=True)
        traceback.print_exc()

        input_data_mgr.add_data(InputData(source = InputSource.SYSTEM, content= str(e)))


    info = {"done": True, "message": {"content": ""}}
    currentStreamingText = sentenceHandler.handleStreamingText(info)
    if currentStreamingText:
        add_to_speak_queue(currentStreamingText,is_end = True, input_source = inputData.source)
    else:
        #设置speak_queue最后一个元素的末尾标记
        if current_speak_task:
            current_speak_task.is_tail = True

    if not is_answering:
        eventDispatch.dispatch(BrainEvent.on_empty_content_respone,inputData.source)


def _after_response():
    main_messages = agentMgr.get_agent_message(MAIN_AGENT, MAIN_AGENT)
    if not main_messages:
        return

    add_momo_internal_task( main_messages)


def think(
    inputData: InputData,
    input_data_mgr:InputDataMgr,
    add_to_speak_queue: Callable[[str], object],
    myGen: GenerationState,
    pipeGen: GenerationState,
    event_is_talking:threading.Event
) -> None:
    def check_is_current_generation():
        return pipeGen.check_is_current_generation(myGen)

    # 本轮回答生成
    _agent_stream(inputData,input_data_mgr, check_is_current_generation, add_to_speak_queue,event_is_talking)
    

    # 派发任务：回答后内心活动，包括情绪变化和记忆改动
    _after_response()
