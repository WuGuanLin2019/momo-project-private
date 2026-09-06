
from Memory.MemoryDB import MemoryData
from Memory.MemoryMgr import RecallData, memory_mgr
from MCP.WebSearch import WebSearchMgr
from MCP.ReadFile import ReadString
from langchain.tools import tool


@tool
def note_memory(content: str, summary: list[str]) -> str:
    """
    有要记下的东西的时去调用，以下事情你可以主动去记下：
    仅当出现具有长期价值、未来可能影响互动的重要新信息时调用。
    一些你作为AI“自我”的信息，比如名称，兴趣，爱好，状态信息等；
    关于你创造者Wu的信息，比如名称，兴趣，爱好，性格，状态信息等；
    一些你与Wu互动的信息，比如令你印象深刻的对话或者互动的场景等；

    宁可漏记，也不要记录普通闲聊。

    Args:
        content (str): 完整的事实描述，保留核心信息（时间、人物、事件、结果），不超过50字。
        summary (list[str]): 多角度概要短语(建议按核心事件，物体，角色，情绪，场景去拆分)，每个元素不超过10字，用于向量检索。



    示例：

    当你听到：今天我度过了难忘的一天，今天在家里吃苹果很开心
    调用：
        note_memory(
            content="用户在家里吃苹果，很开心。",
            summary=["在家吃苹果", "苹果","用户（Wu）","心情愉悦","家里"],
        )
    """

    # print(f"content:{content}\nsummary{summary}\n events{events}\nobject{object}\n emotion{emotion}\n environment{environment}")
    # data = MemoryData(content,summary,actors,objects=objects,emotions=emotions,environment=environment)
    data = MemoryData()
    data.content = content
    data.summary = summary

    result = False
    result = memory_mgr.note(data)
    if result:
        return "已成功记下记忆"
    else:
        return "记忆失败，你没能记住记忆"


@tool
def remind(searchKey: list[str]) -> str:
    """
    在你需要回忆，或者当信息不足时使用

    Args:
        searchKey (list[str]): 搜索关键词，必须是简短的关键词组合，如"用户给AI起的名字"，不超过15字

    Returns:
        str:查询到的记忆字符串

    示例：

    当你想知道你的名字时
    调用：
        remind(
            searchKey=["AI", "名字"],
        )

    """
    results: list[RecallData] | None = memory_mgr.remind(searchKey)
    result_strs = []
    idx = 1
    if not results:
        return "没有找到相关记忆"
    for cur in results:
        mid = cur.mid
        timeStr = cur.timeStr
        content = cur.content
        resultStr = f"mid：{mid}。保存时间：{timeStr}。记忆片段：{content}"
        result_strs.append(resultStr)
        idx += 1
    return "\n".join(result_strs)


@tool
def change_thought(mid: str, content: str, summary: list[str]) -> str:
    """
    当发现与之前记忆不一致时，可以修改记忆。
    一次只能修改一条，如需修改多条请多次调用。

    Args:
        mid (str): 最相关的记忆的唯一id（必须是一个ID，不能是多个）。
        content (str): 完整的事实描述，保留核心信息（时间、人物、事件、结果），不超过50字。
        summary (list[str]): 多角度概要短语(建议按核心事件，物体，角色，情绪，场景去拆分)，每个元素不超过10字，用于向量检索。

    示例：

    当你听到Wu说：给你重新改个名字，叫MOMO。
    然后你发现和之前的记忆“mid:xxx。记忆我的名字叫JOJO”相冲突时，
    调用：
        change_thought(
            mid = "xxx",
            content="WU重新为我取名为MOMO",
            summary=["改名", "MOMO","用户（Wu）"],
        )
    """
    mData = MemoryData()
    mData.content = content
    mData.summary = summary
    result = memory_mgr.rewrite(mid, mData)
    if result:
        return "已成功修改记忆"
    else:
        return "重写记忆失败"


@tool
def get_now_time():
    """
    当你想获取当前时间，调用此函数。
    返回的数据中的时间是24小时制的，格式：YYYY年MM月DD日 HH时MM分SS秒 的本地时间字符串。
    """
    from datetime import datetime

    return "当前系统时间是" + datetime.now().strftime("%Y年%m月%d日 %H时%M分%S秒")


@tool
def web_search(query: str) -> str:
    """
    当你需要获取当前不存在于知识库中的外部信息时调用。

    适用：
    - 最新新闻
    - 当前事件
    - 不确定的事实
    - 需要互联网资料的问题

    不适用：
    - 已知知识回答

    Args:
        query: 搜索关键词
    """
    return WebSearchMgr.web_search(query)


@tool
def web_fetch(url: str) -> str:
    """
    当你需要访问特定网页时调用。

    Args:
        url: 网页链接
    """
    return WebSearchMgr.web_fetch(url)


@tool
def read_file():
    """
    当用户需要你读取附件时调用。
    """
    return ReadString.read_memo()


@tool
def emotion_delta(
    reason:str,
    happy_delta: float = 0,
    sad_delta: float = 0,
    excited_delta: float = 0,
    nervous_delta: float = 0,
):
    """
    根据当前你拥有的上下文（包括身份，价值观，特征，当前的情绪）来判断是否需要改变当前的情绪。
    若需要改变，才调用此函数。

    Args:
        reason(str): 改变情绪的原因，简洁明了，不要超过80字
        happy_delta(float): 愉悦的变化值
        sad_delta(float): 沮丧的变化值
        excited_delta(float): 兴奋的变化值
        nervous_delta(float): 紧张的变化值
        以上参数范围均为-0.3~0.3。-0.3=明显降低，0=不改变,+0.3=明显增加.
    """
    from Brain.Emotion.EmotionMgr import emotionMgr

    momo_emotion = emotionMgr.get_emotion("Momo")
    momo_emotion.change_attr("愉悦", happy_delta)
    momo_emotion.change_attr("沮丧", sad_delta)
    momo_emotion.change_attr("兴奋", excited_delta)
    momo_emotion.change_attr("紧张", nervous_delta)


Tools = [web_search, note_memory, remind, change_thought, get_now_time, read_file,emotion_delta]
ToolsMap = {func.name: func for func in Tools}

MainTools = [web_search,  remind, get_now_time, read_file]
InternalTools = [emotion_delta, note_memory, remind, change_thought]

def call_tool(tool_calls, add_to_input_queue):
    from Brain.conversation import input_data

    if not tool_calls:
        return

    results = {}
    for call in tool_calls:
        fun_name = call.function.name
        tool = ToolsMap.get(fun_name)
        if not tool:
            print("没找到对应tool：" + fun_name)

            tem_data = input_data("Tool", "Tool {fun_name} not found", fun_name)
            add_to_input_queue(tem_data)
            continue

        try:
            result = tool(**call.function.arguments)
            results[fun_name] = result
        except Exception as e:
            print(f"执行函数 {fun_name} 时出错: {e}")
            tem_data = input_data("Tool", f"Tool {fun_name} errer:{e}", fun_name)
            add_to_input_queue(tem_data)

    return results

def call_tool_by_langChain(tool_calls, fun= lambda x: print(x)):
    if not tool_calls:
        return

    results = {}
    for call in tool_calls:
        fun_name = call["name"]
        args = call.get("args", {})
        tool_id = call["id"]
        tool = ToolsMap.get(fun_name)
        if not tool:
            # print("没找到对应tool：" + fun_name)
            fun(f"Tool {fun_name} not found")
            continue

        try:
            result = tool.invoke(args)
            results[tool_id] = result

            fun(result)
        except Exception as e:
            print(f"执行函数 {fun_name} 时出错: {e}")
            fun(f"Tool {fun_name} errer:{e}")


    return results