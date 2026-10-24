# MCP 接入层：把外部 MCP server 的工具接进 momo 的工具池（ToolPiecer）
#
# 两个关键设计：
# 1. 专用事件循环线程：MCP 会话（stdio 子进程 / HTTP）与所有 tools/call 都发生在这个
#    常驻 loop 里，与 brain 的同步管线隔离；loop 不退出，会话不会失效。
# 2. 异步工具 → 同步桥：langchain-core 1.x 的同步 invoke 没有异步兜底（invoke → run →
#    _run 直接抛 NotImplementedError），而 brain 线程走的是 agent.stream() 同步路径，
#    所以 MCP 异步工具必须包成同步 StructuredTool，调用时经 run_coroutine_threadsafe
#    提交到 mcp 线程执行。
import asyncio
import threading

from langchain_core.tools import BaseTool, StructuredTool

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection

from Brain.Context.PromptMgr import PriorityType, PromptData
from Brain.Context.ToolMgr import ToolData
from LangChain.Agent import MomoInternalToolPiecer, MomoPromptPiecer, MomoToolPiecer

# ---- 配置 ----
# 启动时连接的 MCP server。stdio 的子进程用主 venv 的 python 绝对路径，避免环境错乱。
MCP_SERVERS: dict[str, Connection] = {
    "engram": {
        "transport": "stdio",
        "command": "e:\\Study\\GitProject\\engram-main\\.venv\\Scripts\\python.exe",
        "args": [
            "-m",
            "engram.mcp_server",
            "--db",
            "e:\\Study\\GitProject\\engram-main\\momo.engram",
        ],
    },
    # "websearch": {
    #     "url": "http://127.0.0.1:8931/mcp",
    #     "transport": "streamable_http",
    # },
}

MCP_TOOL_KEY = "mcp"  # 在 ToolPiecer 里的 key
MCP_LOAD_TIMEOUT = 60  # 启动时拉取工具清单的超时（秒）
MCP_CALL_TIMEOUT = 120  # 单次工具调用超时（秒）

# 各 agent 的 MCP 工具分配：主 agent 只能"记"，internal agent 全量
MCP_MOMO_WHITELIST: set[str] = {"recall","why",}
MCP_INTERNAL_WHITELIST: set[str] | None = None  # None=全部

# 宿主专用工具：只在启动流程里由代码调用一次，不进任何 agent 的工具池
MCP_HOST_ONLY_TOOLS: set[str] = {"boot_context"}

# 记忆预热：engram 的 boot_context 工具 → 注入 MomoPromptPiecer 的 key
MCP_BOOT_TOOL = "boot_context"
MOMO_MEMORY_PROMPT_KEY = "momo_memory"


def _pick(tools: list[BaseTool], whitelist: set[str] | None) -> list[BaseTool]:
    tools = [t for t in tools if t.name not in MCP_HOST_ONLY_TOOLS]
    return tools if whitelist is None else [t for t in tools if t.name in whitelist]

mcp_client = MultiServerMCPClient(MCP_SERVERS)

# ---- 专用事件循环线程（daemon：主进程退出自动结束）----
_mcp_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
threading.Thread(target=_mcp_loop.run_forever, daemon=True, name="mcp-loop").start()


def _to_sync_tool(tool: BaseTool) -> StructuredTool:
    """把 MCP 异步工具包成同步工具：每次调用提交到 mcp 线程的常驻 loop 执行。"""

    def _run(**kwargs):
        future = asyncio.run_coroutine_threadsafe(tool.ainvoke(kwargs), _mcp_loop)
        return future.result(timeout=MCP_CALL_TIMEOUT)

    return StructuredTool.from_function(
        func=_run,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )


def _result_to_text(result) -> str:
    """MCP 工具返回值 → 纯文本。

    适配器不同版本对文本结果的形状不一致：有的直接给 str，
    有的给内容块列表（TextContent 对象或 dict），这里统一抹平。
    """
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts: list[str] = []
        for block in result:
            if isinstance(block, str):
                parts.append(block)
                continue
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)
    return str(result) if result is not None else ""


def _load_boot_context(tools: list[BaseTool]) -> None:
    """拉取 engram 的记忆预热片段并注入 momo 的 system prompt。

    走已建立的 MCP 会话调用 boot_context（宿主专用工具，不在任何 agent 的
    工具池里），返回的文本以 key="momo_memory" 进入 MomoPromptPiecer——
    MomoSystemPromptMiddleware 每次模型调用都会重读 PromptPiecer，所以
    brain 线程启动后的第一次推理即可见。任何失败只打印日志，不阻断启动。
    """
    boot = next((t for t in tools if t.name == MCP_BOOT_TOOL), None)
    if boot is None:
        print(f"[MCP] engram 未提供 {MCP_BOOT_TOOL} 工具，跳过记忆预热")
        return
    try:
        text = _result_to_text(_to_sync_tool(boot).invoke({}))
        if text and text.strip():
            MomoPromptPiecer.add(
                PromptData(MOMO_MEMORY_PROMPT_KEY, text, PriorityType.mcp)
            )
            print(f"[MCP] 记忆预热片段已注入（{len(text)} 字符）")  
        else:
            print("[MCP] 记忆预热片段为空，跳过注入")
    except Exception as e:
        print(f"[MCP] 记忆预热获取失败（不影响启动）：{e}")


def load_mcp_tools_sync() -> int:
    """阻塞式连接所有 MCP server、拉取工具清单并注入 MomoToolPiecer。

    在主线程启动流程里、brain 线程 start 之前调用。
    任何失败只打印日志，不阻断 momo 启动。返回接入的工具数量。
    """
    future = asyncio.run_coroutine_threadsafe(mcp_client.get_tools(), _mcp_loop)
    try:
        tools: list[BaseTool] = future.result(timeout=MCP_LOAD_TIMEOUT)
    except Exception as e:
        print(f"[MCP] 工具加载失败（不影响启动）：{e}")
        return 0

    sync_tools: list[BaseTool] = [_to_sync_tool(t) for t in tools]

    # 必须注入同步桥接版（sync_tools）：主 agent 走 agent.stream() 同步路径，
    # 原始 MCP 工具只有 coroutine，同步 invoke 会直接抛
    # "does not support sync invocation"。同步 StructuredTool 在异步调用
    # （internal agent 的 ainvoke 路径）下也能正常工作（自动进 executor）。
    for piecer, whitelist in (
        (MomoToolPiecer, MCP_MOMO_WHITELIST),
        (MomoInternalToolPiecer, MCP_INTERNAL_WHITELIST),
    ):
        picked = _pick(sync_tools, whitelist)
        piecer.remove(MCP_TOOL_KEY)
        if picked:
            piecer.add(ToolData(MCP_TOOL_KEY, picked))

    print(f"[MCP] momo: {[t.name for t in _pick(sync_tools, MCP_MOMO_WHITELIST)]} / "
          f"internal: {[t.name for t in _pick(sync_tools, MCP_INTERNAL_WHITELIST)]}")

    _load_boot_context(tools)
    return len(sync_tools)
