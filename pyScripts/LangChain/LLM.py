from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import BaseCallbackHandler
from langchain_ollama import ChatOllama
from langchain_deepseek import ChatDeepSeek
import os
import time

api_key = os.getenv("DEEPSEEK_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")


class LLMStatusCallback(BaseCallbackHandler):
    """实时把 LLM 调用状态打到终端：区分「调用中 / 重试 / 失败」。

    方案 A：仅终端打印，不接前端。with_retry（LangChain 层）每次重试都会
    再触发一次 on_llm_start，所以从「开始」反复出现可判断正在重试；最终
    失败会触发 on_llm_error（如代理 10061 拒绝）。注意：底层 SDK 的
    max_retries 内部重试对 LangChain 透明，看不到中间过程，但最终失败会打印。
    """

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        print(f"[LLM] ▶ 开始调用 run={run_id} t={time.strftime('%H:%M:%S')}")

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        print(f"[LLM] ✅ 调用完成 run={run_id}")

    def on_llm_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        print(f"[LLM] ❌ 调用失败: {error} run={run_id}")


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




if not api_key:
    raise ValueError("请设置环境变量 DEEPSEEK_API_KEY")
else:
    LLMMgr.add_llm(
        "main_agent",
        llm=ChatDeepSeek(
            model="deepseek-flash",
            api_key=api_key,
            temperature=1.3,
            max_tokens=500,
            reasoning_effort="low",
            top_p=0.9,
            extra_body={
                "thinking": {"type": "enabled"},
            },
            timeout=3,  # 流式
            max_retries=3,  # 失败后重试次数
            # callbacks=[LLMStatusCallback()],
        ),
    )
    LLMMgr.add_llm(
        "internal_agnet",
        llm=ChatDeepSeek(
            model="deepseek-flash",
            api_key=api_key,
            temperature=1,
            max_tokens=None,
            top_p=0.9,
            extra_body={
                "thinking": {"type": "disabled"},
            },
            timeout=60,  # 非流式
            max_retries=1,  # 失败后重试次数
        ),
    )
    LLMMgr.add_llm(
        "summary",
        llm=ChatDeepSeek(
            model="deepseek-flash",
            api_key=api_key,
            temperature=1,
            max_tokens=None,
            reasoning_effort="low",
            extra_body={
                "thinking": {"type": "adaptive"},
            },
            # 超时和重试配置
            timeout=60,  # 连接超时（秒），默认可能较短
            max_retries=1,  # 失败后重试次数
        ),
    )
