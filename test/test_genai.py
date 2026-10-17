from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    temperature=0.7,
    api_key = "AQ.Ab8RN6KxWXwd3wJmg0wWGhZ065cS1ofV68vlzVYTuvyHDiJkhg",
)

response = llm.invoke("你好，请介绍一下你自己")

print(response.content)
