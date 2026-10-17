from Brain.conversation import add_to_conversation
from Brain.SentenceHandler import SentenceHandler
from Core.Action import call_tool
from Core.State import GenerationState
# from Utils.Timer import SmallTimer
from ollama import chat
from Brain.conversation import input_data

_check_is_current_generation = None

def when_think_end(
    sh: SentenceHandler, add_to_input_queue
):
    print("Brain end")

    if not sh.content and not sh.tool_calls:
        print(",but no content")
        add_to_input_queue(input_data("tool", "刚刚你恍惚了一下，没有任何输出"))
        return


    data = input_data("assistant", sh.content)

    if not sh.tool_calls:
        # 普通回答
        add_to_conversation(data)
    else:
        # 调用工具
        try:
            results = call_tool(
                sh.tool_calls, add_to_input_queue
            )
            handle_results(results, add_to_input_queue)
        except Exception as e:
            print(f"call_tool error:{e}")


def handle_results(results, add_to_input_queue):
    for k, v in results.items():
        print(k, v)
        tem_data = input_data("Tool", v, k)
        add_to_input_queue(tem_data)


def think(
    inputStr,
    add_to_speak_queue,
    add_to_input_queue,
    myGen: GenerationState,
    pipeGen: GenerationState,
):

    stream = chat(
        # gemma3:1b,
        # qwen2.5:3b-instruct-q4_K_M
        # llama3.1
        # qwen2.5:14b-instruct-q4_K_M
        # deepseek-r1:8b
        # qwen3.5:9b
        model="qwen3.5:9b",
        messages=inputStr,
        # tools=Tools,
        stream=True,
        think=False,
        keep_alive=-1,  #常驻显存
        options={
            # "num_predict": 256,
            "repeat_penalty": 1.3,
            "temperature": 1,
            "top_k": 40,
            "top_p": 0.9,
            "num_ctx": 4096,
        },
    )

    def check_is_current_generation():
        return pipeGen.check_is_current_generation(myGen)
    _check_is_current_generation = check_is_current_generation

    sentenceHandler = SentenceHandler()

    try:
        for chunk in stream:
            if not pipeGen.check_is_current_generation(myGen):
                print("思考中断")
                when_think_end(
                    sentenceHandler, add_to_input_queue
                )
                break

            currentSteamingText = sentenceHandler.handleStreamingText(chunk)
            if currentSteamingText:
                add_to_speak_queue(currentSteamingText)
    except Exception as e:
        error_str = f"stream error:{e}"
        print(error_str)
        add_to_input_queue(input_data("assistant", error_str))

    if pipeGen.check_is_current_generation(myGen):
        print("思考正常结束")
        when_think_end(sentenceHandler, add_to_input_queue)


# if __name__ == "__main__":
#     think("介绍一下你自己")
