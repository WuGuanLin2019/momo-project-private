from dataclasses import dataclass
from ollama import chat

@dataclass
class input_data:
    role: str = ""
    content: str = ""
    tool_name: str = ""


conversation = []

system_prompt = {
    "role": "system",
    "content": """
      你的名字叫MOMO，一个有点毒舌的AI。你的创造者是WU。

      日常对话：
      用普通话来回答。
      只能输出文字和标点。
      语句需要简短精炼，偏向生活对话的口语化表达，一次表达不要超过3句话。
      """,
}

MAX_CHAT_TURN =20  # 最大对话轮次
SUMMARY_CHAT_TURN = 8  # 总结对话轮次


def get_full_conversation():
    #todo 后续用token数来计算
    if len(conversation) > MAX_CHAT_TURN + 1:
        summary_str = _summary_conversation(conversation[:SUMMARY_CHAT_TURN])
        del conversation[:SUMMARY_CHAT_TURN]
        if summary_str:
            summary_con = {"role": "system", "content": summary_str}
            conversation.insert(0, summary_con)
        

    return [system_prompt]  + conversation


def add_to_conversation(input_data:input_data):
    content = input_data.content
    role = input_data.role
    
    tem_con = {"role": role, "content": content}
    if role == "tool":
        tem_con["tool_name"] = input_data.tool_name
      
    conversation.append(tem_con)

    return get_full_conversation()


def _simple_think(inputStr):
    con = [{"role":"user", "content":inputStr}]
    res = chat(
        model="gemma3:1b",
        messages=con,
        think=False,
        options={
            "num_predict": 350,
            "repeat_penalty": 1.5,
            "temperature": 1,
            "top_k": 40,
            "top_p": 0.9,
            "num_ctx": 1024,
        },
    )

    return res.message.content


def _summary_conversation(cons):
    con_str = "\n".join(f"{m['role']}: {m['content']}" for m in cons)
    sys_prompt = """
    请总结下面这段对话中值得长期保留的信息。

    要求：
    1. 保留重要信息，比如：人物、物品、事实、重要决定。
    2. 不要记录无意义的闲聊。
    3. 不要添加原对话中不存在的信息。
    4. 简洁一些，字数在300字以下。

    对话：\n"""
    # print(sys_prompt+con_str)

    sum = _simple_think(sys_prompt + con_str)

    print(  f"\n\n总结对话：\n{sum}\n\n")

    return sum


