"""通过 MCP WebSocket 服务器，从外部进程把弹幕文字输入到 momo。

运行方式（用项目所在的 Python 解释器）：
    python -m DrawBridge.BulletChat.BulletChatInputTest

前提：
    1. momo 主进程已启动 DrawBridge 服务器（DrawBridgeServer，端口 5050）。
    2. momo 主进程内需注册一个 on_receive_message 处理，把 action=="bullet_chat"
       的消息转成 send_bullet_chat(text)。示例（放进主进程任意会被 import 的模块）：

           from DrawBridge.DrawBridgeEvent import DrawBridgeEvent
           from Utils.EventDispatch import eventDispatch
           from DrawBridge.BulletChat.BulletChatTest import send_bullet_chat

           def _on_external_bullet_chat(message):
               if message.get("unique_name") != UNIQUE_NAME:
                   return
               data = message.get("data") or {}
               if data.get("action") != "bullet_chat":
                   return
               text = (data.get("text") or "").strip()
               if text:
                   send_bullet_chat(text)

           eventDispatch.register(DrawBridgeEvent.on_receive_message, _on_external_bullet_chat)

数据流：
    本脚本 --WebSocket(ws://127.0.0.1:5050/ws, unique_name=bullet_chat_external)-->
    DrawBridgeServer --eventDispatch(DrawBridgeEvent.on_receive_message)--> 主进程 handler
    --> send_bullet_chat(text) --> ListernEvent.push_input_data --> momo 流水线
"""
import json
import threading

import websocket  # websocket-client，项目已依赖（见 VTube）

MCP_WS_URL = "ws://127.0.0.1:5050/ws"
UNIQUE_NAME = "mcp_bullet_chat"


def _pump(ws, closed):
    """后台线程：持续读取服务器帧，自动应答 ping/pong。

    否则服务器（Starlette/websockets）默认每 ~20s 发一次 ping 并等待 pong，
    本端只 send 不 recv 就不会回 pong，服务器 ping 超时后会以 1006 异常关闭连接。
    """
    try:
        while True:
            ws.recv()
    except Exception:
        pass
    finally:
        closed.set()


def main():
    ws = websocket.create_connection(MCP_WS_URL, enable_multithread=True)
    closed = threading.Event()
    threading.Thread(target=_pump, args=(ws, closed), daemon=True).start()

    # 首条消息必须是注册用的 unique_name，否则服务器会因缺少该字段直接断开连接
    ws.send(json.dumps({"unique_name": UNIQUE_NAME}))
    print(
        f"已连接 DrawBridge 服务器 (unique_name={UNIQUE_NAME})，"
        "输入文字回车发送给 momo（exit 退出）"
    )

    try:
        while True:
            if closed.is_set():
                print("连接已断开。")
                break
            text = input("弹幕> ")
            text = text.strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit", "q"):
                break
            try:
                ws.send(json.dumps({"action": "bullet_chat", "text": text}))
            except Exception as e:
                print(f"发送失败（连接可能已断开）: {e}")
                break
            print("已发送")
    except (EOFError, KeyboardInterrupt):
        print("\n已退出。")
    finally:
        try:
            ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
