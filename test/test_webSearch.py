import ollama


result = ollama.web_search(
    "天安门事件是什么"
)

print(result)