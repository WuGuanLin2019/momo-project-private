from queue import Queue
from threading import Thread
import threading
from typing import Any, TypeAlias
from langchain_core.runnables import RunnableSerializable
from LangChain.LLM import LLMMgr
from LangChain.Context import get_internal_prompt, prompts_with_history
from Core.Action import InternalTools

Chain: TypeAlias = RunnableSerializable[Any, Any]


class ChainMgr:
    def __init__(self):
        self.chains: dict[str, Chain] = {}

    def get_chain(self, name: str) -> Chain | None:
        if name in self.chains:
            return self.chains[name]
        return None

    def add_chain(self, name: str, chain: Chain) -> None:
        self.chains[name] = chain

    
    

chainMgr = ChainMgr()


def _init_momo_internal_chain():
    prompts = get_internal_prompt()
    llm = LLMMgr.get_llm("deepseek")
    llm = llm.bind_tools(InternalTools)

    chain = prompts | llm
    chain = prompts_with_history(chain)
    chainMgr.add_chain("momo_internal", chain)

# _init_momo_internal_chain()

def _init_momo_internal_test_chain():
    prompts = get_internal_prompt()
    llm = LLMMgr.get_llm("qwen3b")
    llm = llm.bind_tools(tools=InternalTools)

    chain = prompts | llm
    chain = prompts_with_history(chain)
    chainMgr.add_chain("momo_internal_test", chain)

# _init_momo_internal_test_chain()


# if __name__ == "__main__":
#     # _llm_stream("苹果好吃吗？", lambda:True,lambda x:x)
#     # _llm_stream("它是什么颜色的？", lambda:True,lambda x:print(x))

#     if main_chain:
#         try:
#             print(main_chain.invoke({"input": "苹果好吃吗？"}, config={"configurable": {"session_id": "momo"}}))
#         except Exception as e:
#             print(e)
