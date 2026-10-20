#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
submit_input_test.py —— 模拟 Momo MCP Server 的字幕测试服务端。

作用：在 127.0.0.1:5050 起一个 WebSocket 服务，充当“服务器”，
     你在终端手打字幕文本，回车即发送给浏览器源（sub.html）显示。
     协议与 momo_subtitle.js 完全一致，可用于脱离真实 MCP 单独调试字幕。

依赖：pip install websockets

用法：
  1) 确保 5050 端口没被真实的 Momo MCP Server 占用（否则会冲突，脚本会提示）。
  2) 在直播姬里刷新浏览器源（让它连到我们这个假服务器）。
  3) 运行：python submit_input_test.py  （请在 cmd / PowerShell 等真实终端里运行）
  4) 终端出现 “字幕> ” 后，输入文本回车发送；特殊命令见下方。

终端命令：
  直接输入文本            作为“新字幕”显示，时长按字数自动估算
  /clear                 清空字幕
  /d 秒数 文本            指定时长（秒）显示文本，例如 /d 5 你好世界
  /head 文本             作为新字幕（清掉上一句）
  /tail 文本             追加到当前字幕后面，并在显示完后自动清屏
  /quit                  退出
"""

import asyncio
import json
import sys
import threading
from typing import Any

import websockets

HOST = "127.0.0.1"
PORT = 5050

# 当前已连接的字幕客户端（浏览器源）
CONNECTIONS: set[Any] = set()
# 事件循环引用，供输入线程回调（由 main_async 在 loop 线程内赋值）
_loop: asyncio.AbstractEventLoop | None = None
# 用于通知主协程退出的事件
_shutdown: asyncio.Event | None = None
# 服务启动状态（主线程据此判断是否成功绑定端口）
_started = threading.Event()
_start_error: str | None = None


async def handler(websocket):
    """处理一个浏览器源的连接。"""
    CONNECTIONS.add(websocket)
    print(f"[客户端连上] 当前连接数={len(CONNECTIONS)}", flush=True)
    try:
        # 客户端连上后会先发 {"unique_name": "momo_subtitle"} 注册，这里只回显
        async for message in websocket:
            print(f"[客户端→] {message}", flush=True)
    finally:
        CONNECTIONS.discard(websocket)
        print(f"[客户端断开] 当前连接数={len(CONNECTIONS)}", flush=True)


def _auto_duration(text: str) -> float:
    """按字数自动估算字幕显示时长（秒）：中文约 6 字/秒，最少 2 秒。"""
    return max(2.0, len(text) / 6.0)


async def _broadcast(payload: dict[str, Any]):
    msg = json.dumps(payload, ensure_ascii=False)
    if CONNECTIONS:
        await asyncio.gather(*(ws.send(msg) for ws in list(CONNECTIONS)))
        print(f"[已发送] {msg}", flush=True)
    else:
        print("(暂无已连接客户端，消息已生成但未发送)", flush=True)


def send_display(text: str, duration: float | None = None, is_head: bool = True, is_tail: bool = False):
    if duration is None:
        duration = _auto_duration(text)
    assert _loop is not None, "事件循环尚未初始化"
    asyncio.run_coroutine_threadsafe(
        _broadcast(
            {
                "action": "display",
                "text": text,
                "duration": duration,
                "is_head": is_head,
                "is_tail": is_tail,
            }
        ),
        _loop,
    )


def send_clear():
    assert _loop is not None, "事件循环尚未初始化"
    asyncio.run_coroutine_threadsafe(_broadcast({"action": "clear"}), _loop)


def _request_shutdown():
    """由输入线程调用，安全地在事件循环里置位退出事件。"""
    if _shutdown is not None and _loop is not None:
        _loop.call_soon_threadsafe(_shutdown.set)


def console():
    """在独立线程里读取 stdin，避免部分环境下 asyncio 读 stdin 失败。"""
    while True:
        try:
            line = input("字幕> ")
        except (EOFError, KeyboardInterrupt):
            _request_shutdown()
            break

        line = line.strip()
        if not line:
            continue

        if line == "/quit":
            _request_shutdown()
            break

        if line == "/clear":
            send_clear()
            continue

        if line.startswith("/d "):
            # /d 5 文本内容
            parts = line[3:].split(" ", 1)
            if len(parts) == 2:
                try:
                    send_display(parts[1], duration=float(parts[0]))
                    continue
                except ValueError:
                    pass
            print("用法: /d 5 文本内容", flush=True)
            continue

        if line.startswith("/head "):
            send_display(line[6:], is_head=True)
            continue

        if line.startswith("/tail "):
            send_display(line[6:], is_head=False, is_tail=True)
            continue

        # 默认：作为新字幕发送，时长自动估算
        send_display(line, is_head=True)


async def main_async():
    global _loop, _shutdown, _start_error
    # 在事件循环线程内捕获 loop，供输入线程回调
    _loop = asyncio.get_running_loop()
    _shutdown = asyncio.Event()

    # async with 会在退出时自动关闭服务，避免手动 wait_closed 死锁
    try:
        async with websockets.serve(handler, HOST, PORT):
            _started.set()
            await _shutdown.wait()
    except OSError as e:
        _start_error = str(e)
        _started.set()


if __name__ == "__main__":
    if not sys.stdin.isatty():
        print(
            "警告：当前 stdin 不是交互终端，键盘输入可能无效。"
            "请在 cmd / PowerShell 中直接运行本脚本。",
            flush=True,
        )

    # 事件循环跑在后台线程；主线程专门负责 input()，保证键盘输入可靠
    server_thread = threading.Thread(
        target=lambda: asyncio.run(main_async()), daemon=True
    )
    server_thread.start()

    _started.wait()  # 等端口绑定结果
    if _start_error:
        print(f"启动失败（端口 {PORT} 可能已被占用）：{_start_error}", flush=True)
        print("请先关闭占用 5050 的真实 Momo MCP Server，再重新运行本脚本。", flush=True)
        sys.exit(1)

    print(f"模拟服务器已启动 ws://{HOST}:{PORT}/ws", flush=True)
    print("直播姬刷新浏览器源以连上来。出现 “字幕> ” 即可输入。", flush=True)
    print("命令：/clear | /d 秒数 文本 | /head 文本 | /tail 文本 | /quit", flush=True)

    try:
        console()  # 主线程读键盘
    except KeyboardInterrupt:
        _request_shutdown()
    server_thread.join(timeout=5)
