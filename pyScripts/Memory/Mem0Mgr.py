"""mem0 自托管服务封装。

用法参考 third_party/mem0/test/input_test.py。
注意：自托管 server 不支持官方 MemoryClient（它的路径带 /v1 前缀），
这里直接用 urllib 调 REST API，不引入任何第三方依赖。

运行前提：
  1) 本地 embedding 服务 localhost:4242
  2) docker compose up -d（mem0 server，默认 localhost:8888）
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
import os

from langchain.tools import tool

MEM0_BASE_URL = "http://localhost:8888"
MEM0_API_KEY = os.getenv("MEM0_LOCAL_API_KEY")

# add 要走 LLM 抽取 + 本地 embedding，很慢；检索相对快
ADD_TIMEOUT = 120
SEARCH_TIMEOUT = 30
# 服务连不上时，这段时间内不再尝试，避免每次请求都干等超时
OFFLINE_COOLDOWN = 60


class Mem0Mgr:
    """mem0 记忆的读写封装。

    user_id 表示「这条记忆属于谁」。默认 "momo"，
    若记忆主体是人类用户，接入时改成对应的用户标识即可。
    """

    user_id: str
    base_url: str
    api_key: str
    _lock: threading.Lock
    _offline_until: float
    _tools: list[Any]

    def __init__(
        self,
        user_id: str = "momo",
        base_url: str = MEM0_BASE_URL,
        api_key: str = MEM0_API_KEY,
    ):
        self.user_id = user_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

        self._lock = threading.Lock()
        self._offline_until = 0.0
        # 只构建一次：多处引用 mem0_mgr.tools 时必须是同一批对象，
        # 否则 Action.remove_main_llm_tools() 的 list.remove() 按身份比较会失败
        self._tools = self._build_tools()

    # ------------------------------------------------------------ 底层请求

    def _is_offline(self) -> bool:
        with self._lock:
            return time.time() < self._offline_until

    def _mark_offline(self) -> None:
        with self._lock:
            self._offline_until = time.time() + OFFLINE_COOLDOWN

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timeout: int = ADD_TIMEOUT,
        skip_offline_check: bool = False,
    ) -> dict[str, Any] | None:
        """发请求，返回解析后的 dict；失败返回 None（不抛异常，保证不打断主流程）。"""
        if not skip_offline_check and self._is_offline():
            return None

        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        data = None
        headers = {"X-API-Key": self.api_key}
        if body is not None:
            data = json.dumps(obj=body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload: Any = json.loads(resp.read().decode("utf-8"))
                return payload
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            print(f"[mem0] 请求失败 {e.code} {method} {path}: {detail[:200]}")
        except urllib.error.URLError as e:
            print(f"[mem0] 连不上服务 {self.base_url}：{e.reason}")
            self._mark_offline()
        except Exception as e:
            print(f"[mem0] 请求异常 {method} {path}：{e}")
        return None

    def is_available(self) -> bool:
        """服务是否可用（不受离线冷却影响，用于主动探活）。"""
        return (
            self._request(
                "GET",
                "/auth/setup-status",
                timeout=SEARCH_TIMEOUT,
                skip_offline_check=True,
            )
            is not None
        )

    # ------------------------------------------------------------ 写

    def add(self, text: str, infer: bool = True, block: bool = False) -> list[str] | None:
        """存入一段记忆。

        infer=True  ：交给 LLM 抽取事实（慢，但记得干净）
        infer=False ：原文原样存
        block=False ：丢后台线程，不卡主流程（默认）；True 则同步等待并返回结果
        """
        text = (text or "").strip()
        if not text:
            return None

        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": text}],
            "user_id": self.user_id,
        }
        if not infer:
            body["infer"] = False

        if not block:
            threading.Thread(target=self._add_sync, args=(body,), daemon=True).start()
            return None
        return self._add_sync(body)

    def _add_sync(self, body: dict[str, Any]) -> list[str]:
        result = self._request("POST", "/memories", body=body, timeout=ADD_TIMEOUT)
        if result is None:
            return []

        created: list[dict[str, Any]] = result.get("results", [])
        memories = [str(item.get("memory", "")) for item in created if item.get("memory")]
        if not memories:
            print("[mem0] 没有抽取出新记忆（可能重复，或这段话没有值得记住的信息）")
            return []

        print(f"[mem0] 已写入 {len(memories)} 条记忆")
        for m in memories:
            print(f"  - {m}")
        return memories

    # ------------------------------------------------------------ 读

    def search(self, query: str, top_k: int = 5) -> list[str]:
        """语义检索，返回记忆文本列表（按相关度降序）。"""
        query = (query or "").strip()
        if not query:
            return []

        result = self._request(
            "POST",
            "/search",
            body={
                "query": query,
                "filters": {"user_id": self.user_id},
                "top_k": top_k,
            },
            timeout=SEARCH_TIMEOUT,
        )
        if result is None:
            return []

        hits: list[dict[str, Any]] = result.get("results", [])
        print(f"[mem0] 检索「{query}」命中 {len(hits)} 条")
        return [str(item.get("memory", "")) for item in hits if item.get("memory")]

    def search_detail(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """同上，但保留 id / score，便于溯源或删除。"""
        query = (query or "").strip()
        if not query:
            return []

        result = self._request(
            "POST",
            "/search",
            body={
                "query": query,
                "filters": {"user_id": self.user_id},
                "top_k": top_k,
            },
            timeout=SEARCH_TIMEOUT,
        )
        if result is None:
            return []

        hits: list[dict[str, Any]] = result.get("results", [])
        return [
            {
                "id": item.get("id"),
                "memory": str(item.get("memory", "")),
                "score": item.get("score"),
            }
            for item in hits
            if item.get("memory")
        ]

    def get_all(self, top_k: int = 100) -> list[str]:
        """列出该用户的全部记忆。"""
        result = self._request(
            "GET",
            "/memories",
            params={"user_id": self.user_id, "top_k": top_k},
            timeout=SEARCH_TIMEOUT,
        )
        if result is None:
            return []

        items: list[dict[str, Any]] = result.get("results", [])
        return [str(item.get("memory", "")) for item in items if item.get("memory")]

    def recall_str(self, query: str, top_k: int = 5) -> str:
        """检索并拼成可直接塞进 prompt 的文本，没命中返回空串。"""
        memories = self.search(query, top_k)
        if not memories:
            return ""
        return "\n".join(f"- {m}" for m in memories)
 
    # ------------------------------------------------------------ 删

    def delete(self, memory_id: str) -> bool:
        return (
            self._request(
                "DELETE", f"/memories/{memory_id}", timeout=SEARCH_TIMEOUT
            )
            is not None
        )

    @property
    def tools(self):
        return self._tools

    def _build_tools(self):
        @tool
        def note_memory(content: str):
            """
            有要记下的东西的时去调用，以下事情你可以主动去记下：
            仅当出现具有长期价值、未来可能影响互动的重要新信息时调用。
            一些你作为AI“自我”的信息，比如名称，兴趣，爱好，状态信息等；
            关于你创造者Wu的信息，比如名称，兴趣，爱好，性格，状态信息等；
            一些你与Wu互动的信息，比如令你印象深刻的对话或者互动的场景等；

            宁可漏记，也不要记录普通闲聊。

            Args:
                content (str): 完整的事实描述，保留核心信息（时间、人物、事件、结果），不超过50字。
            
            示例：

            当你听到：今天我度过了难忘的一天，今天在家里吃苹果很开心
            调用：
                note_memory(
                    content="用户在家里吃苹果，很开心。",
                   
                )
            """

            memories = self.add(content, block=True)
            if memories:
                return "已记下：" + "；".join(memories)
            return "没有抽出可记住的内容（可能重复，或这段话没有值得记住的信息）"

        @tool
        def remind(query: str):
            """
            在你需要回忆，或者当信息不足时使用

            Args:
                query (str): 搜索字符串，如"用户给我起的名字是什么？"，不超过15字

            Returns:
                str:查询到的记忆字符串

            示例：

            当你想知道你的名字时
            调用：
                remind(
                    query="用户给我起的名字是什么？"
                )

            """
            block = self.recall_str(query)
            if not block:
                return "没有找到相关记忆"
            return f"\n<相关记忆>\n{block}\n</相关记忆>"

        return [note_memory, remind]


mem0_mgr = Mem0Mgr()
