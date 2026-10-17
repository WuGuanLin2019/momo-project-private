import ollama
from typing import Union
from rich import print
from ollama import WebFetchResponse, WebSearchResponse,chat

def _simple_think(inputStr):

    stream = chat(
        # gemma3:1b,
        # qwen2.5:3b-instruct-q4_K_M
        # llama3.1
        # qwen2.5:14b-instruct-q4_K_M
        # deepseek-r1:8b
        # qwen3.5:9b
        model="qwen3.5:9b",
        messages=inputStr,
        stream=True,
        think=False,
        options={
            # "num_predict": 256,
            "repeat_penalty": 1.3,
            "temperature": 1,
            "top_k": 40,
            "top_p": 0.9,
            "num_ctx": 32768,
        },
    )

    def check_is_current_generation():
        return True

    output = ""
    try:
        for chunk in stream:
            if not check_is_current_generation():
                print("思考中断")
                return None

            if chunk.message.content:
                output = output + chunk.message.content
    except Exception as e:
        print(f"stream error:{e}")

    return output


def web_search(query: str):
    result = ollama.web_search(query)
    formatted_tool_results = format_tool_results(result, user_search=query)

    print(formatted_tool_results[:300])
    # input_str = [{"role": "system", "content":f"你是一个信息提取工具，把下面众多网络搜索的信息中提取出与【{query}】相关的信息。最多500字。"},
    # {"role": "tool", "content":formatted_tool_results[: 10000]}]
    # output = _simple_think(input_str)
    # print(f"output:{output}")

    # return str(output)
    return str(formatted_tool_results[: 500])


def web_fetch(url: str):
    result = ollama.web_fetch(url)
    formatted_tool_results = format_tool_results(result, user_search="")
    print(formatted_tool_results[:300])

    return str(formatted_tool_results[: 2000])


def format_tool_results(
    results: Union[WebSearchResponse, WebFetchResponse],
    user_search: str,
):
    output = []
    if isinstance(results, WebSearchResponse):
        output.append(f'Search results for "{user_search}":')
        for result in results.results:
            output.append(f"{result.title}" if result.title else f"{result.content}")
            output.append(f"   URL: {result.url}")
            output.append(f"   Content: {result.content}")
            output.append("")
        return "\n".join(output).rstrip()

    elif isinstance(results, WebFetchResponse):
        output.append(f'Fetch results for "{user_search}":')
        output.extend(
            [
                f"Title: {results.title}",
                f"URL: {user_search}" if user_search else "",
                f"Content: {results.content}",
            ]
        )
        if results.links:
            output.append(f'Links: {", ".join(results.links)}')
        output.append("")
        return "\n".join(output).rstrip()


# if __name__ == "__main__":
#     import os
#     result = ollama.web_search("怎么缓解焦虑？",10)
#     out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "search_result.txt")
#     with open(out_path, "w", encoding="utf-8-sig") as f:
#         f.write(str(result))
#     print("result saved to file")