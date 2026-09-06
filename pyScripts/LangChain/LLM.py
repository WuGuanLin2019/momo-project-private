from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_deepseek import ChatDeepSeek
import os

api_key = os.getenv("DEEPSEEK_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")


class llmMgr:
    def __init__(self) -> None:
        self.llms: dict[str, BaseChatModel] = {}

    def get_llm(self, llm_name: str) -> BaseChatModel:
        if llm_name in self.llms:
            return self.llms[llm_name]

        print(f"llm {llm_name} not found, use fallBack llm.")
        # return self.llms["fallBack"]

    def add_llm(self, llm_name: str, llm: BaseChatModel) -> None:
        self.llms[llm_name] = llm


LLMMgr = llmMgr()
LLMMgr.add_llm(
    "momo_9b",
    ChatOllama(
        # gemma3:1b,
        # qwen2.5:3b-instruct-q4_K_M
        # llama3.1
        # qwen2.5:14b-instruct-q4_K_M
        # deepseek-r1:8b
        # qwen3.5:9b
        model="qwen3.5:9b",
        reasoning=False,  # 等价原 think=False，关闭思考过程
        keep_alive=-1,  # 模型常驻内存
        repeat_penalty=1.3,
        temperature=1,
        top_k=40,
        top_p=0.9,
        num_ctx=4096,
        num_predict=1024,
    ),
)

LLMMgr.add_llm(
    "qwen3b",
    ChatOllama(
        # gemma3:1b,
        # qwen2.5:3b-instruct-q4_K_M
        # llama3.1
        # qwen2.5:14b-instruct-q4_K_M
        # deepseek-r1:8b
        # qwen3.5:9b
        model="qwen2.5:3b-instruct-q4_K_M",
        reasoning=False,  # 等价原 think=False，关闭思考过程
        keep_alive=-1,  # 模型常驻内存
        repeat_penalty=1.3,
        temperature=1,
        top_k=40,
        top_p=0.9,
        num_ctx=4096,
        num_predict=1024,
    ),
)

LLMMgr.add_llm(
    "fallBack",
    ChatOllama(
        # gemma3:1b,
        # qwen2.5:3b-instruct-q4_K_M
        # llama3.1
        # qwen2.5:14b-instruct-q4_K_M
        # deepseek-r1:8b
        # qwen3.5:9b
        model="gemma3:1b",
        reasoning=False,  # 等价原 think=False，关闭思考过程
        repeat_penalty=1.3,
        temperature=1,
        top_k=40,
        top_p=0.9,
        num_ctx=2048,
    ),
)

from langchain_google_genai import ChatGoogleGenerativeAI

LLMMgr.add_llm(
    "google",
    ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=0.7,
        api_key=gemini_api_key,
    ),
)

LLMMgr.add_llm(
    "summary",
    ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=0,
        api_key=gemini_api_key,
    ),
)

if not api_key:
    raise ValueError("请设置环境变量 DEEPSEEK_API_KEY")
else:
    LLMMgr.add_llm(
        "deepseek",
        llm=ChatDeepSeek(
            model="deepseek-v4-flash",
            api_key=api_key,
            temperature=1.3,
            max_tokens=None,
            reasoning=None,
            top_p=0.9,
            extra_body={
                "thinking": {"type": "disabled"},
            },
            # 超时和重试配置
            timeout=5,  # 连接超时（秒），默认可能较短
            max_retries=3,  # 失败后重试次数
        ),
    )
