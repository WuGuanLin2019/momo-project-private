from LangChain.Agent import Agent
from LangChain.AgentMeta import AgentMetaContext


from queue import Queue
import threading

from langchain_core.messages import ToolMessage
from Core.Action import call_tool_by_langChain
from LangChain.Agent import agentMgr
from LangChain.Chain import chainMgr
from LangChain.Context import get_history

INTERNAL_AGENT = "momo_internal"


class MomoInternalTask:
    def __init__(self, message):
        self.message = message


_momo_internal_task_list = Queue[MomoInternalTask]()

last_reaction_index = 0


def _momo_internal_chain_fun(task: MomoInternalTask):
    chain = chainMgr.get_chain(INTERNAL_AGENT)
    if not chain:
        raise Exception("momo internal chain not found")

    main_messages = task.message
    if not main_messages:
        return

    global last_reaction_index
    history_text = "\n".join(
        f"{msg.type}: {msg.content}" for msg in main_messages[last_reaction_index:]
    )
    last_reaction_index = len(main_messages)
    # print(f"\n 内心分析的上下文：\n{history_text}")

    try:
        res = chain.invoke(
            {"analysis_messages": history_text},
            config={"configurable": {"session_id": INTERNAL_AGENT}},
        )
    except Exception as e:
        history = get_history(INTERNAL_AGENT)
        for i, msg in enumerate(history.messages):
            print(f"\n[{i}] {type(msg).__name__}")
            print("id:", getattr(msg, "id", None))
            print("content:", msg.content)
            print("tool_calls:", getattr(msg, "tool_calls", None))
            print("tool_call_id:", getattr(msg, "tool_call_id", None))
        print(e)
        return

    # print("\n【Momo内心活动记录】")
    if res.content:
        print(f"\n【Momo内心活动记录:{res.content}】")

    if res.tool_calls:
        history = get_history(INTERNAL_AGENT)
        # 手动调用tool
        results = call_tool_by_langChain(res.tool_calls)

        for tool_call in res.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            if tool_name == "note_memory":
                print(f"momo_internal 尝试调用工具:{tool_name}:{tool_args}")

            # 手动把tool结果加入上下文
            result = results.get(tool_id) or ""
            history.add_message(ToolMessage(content=result, tool_call_id=tool_id))


def _momo_internal_agent_fun(task: MomoInternalTask):
    agent: Agent | None = agentMgr.get_agent(INTERNAL_AGENT)
    if not agent:
        raise Exception("momo internal agent not found")

    main_messages = task.message
    if not main_messages:
        return

    global last_reaction_index
    history_text = "\n".join(
        f"{msg.type}: {msg.content}" for msg in main_messages[last_reaction_index:]
    )
    last_reaction_index = len(main_messages) - 1
    # print(f"\n 内心分析的上下文：\n{history_text}")
    try:
        res = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"""<之前的上下文>{history_text}</之前的上下文>""",
                    }
                ]
            },
            config={"configurable": {"thread_id": INTERNAL_AGENT}},
            context=AgentMetaContext(INTERNAL_AGENT),
        )
        st = agent.get_state({"configurable": {"thread_id": INTERNAL_AGENT}})
        # print("momo_internal 历史条数:", len(st.values.get("messages", [])),
        #     "| 末条内容:", repr(res["messages"][-1].content))

    except Exception as e:
        print(e)
        return

    # print("\n【Momo内心活动记录】")
    if res:
        mind = res["messages"][-1]
        print(f"\n【Momo内心活动记录:{mind.content}】")


def _momo_internal_loop():
    while True:
        task = _momo_internal_task_list.get()
        _momo_internal_agent_fun(task)


threading.Thread(target=_momo_internal_loop, daemon=True).start()


def add_momo_internal_task(message):
    task = MomoInternalTask(message)
    _momo_internal_task_list.put(task)
