import asyncio
from contextlib import asynccontextmanager
import threading
from typing import Any

from fastapi import FastAPI, WebSocket
import uvicorn

from DrawBridge.DrawBridgeEvent import DrawBridgeEvent
from Utils.EventDispatch import eventDispatch

clients_list: dict[str, WebSocket] = {}

async def _send_message(unique_name: str, data: dict[str, Any]):
    if unique_name not in clients_list:
        print(unique_name + "连接不存在")
        return

    ws = clients_list[unique_name]
    try:
        await ws.send_json(data)
    except Exception:
        # 单个连接发送失败（如已断开）不应中断对其余客户端的广播
        clients_list.pop(unique_name)


def send_message(unique_name: str, data: dict[str, Any],is_sync:bool=False):
    if event_loop is None:
        print("DrawBridge Server event loop 不存在")
        return

    future = asyncio.run_coroutine_threadsafe(
        _send_message(unique_name, data),
        event_loop
    )
    if is_sync:
         future.result()


async def test_input():
    import msvcrt

    while True:
        # getwch() 是阻塞调用，放进线程池执行，避免卡住事件循环
        ch = await asyncio.to_thread(msvcrt.getwch)
        if ch == " ":  # 空格
            pass
            # await send_message(
            #     "momo_subtitle",
            #     {"action": "display", "text": "我知道你的可能不会的", "duration": 5},
            # )
            # await asyncio.to_thread(
            # send_message_sync,
            # "momo_subtitle",
            # {
            #     "action": "display",
            #     "text": "10秒到了！",
            #     "duration": 5
            # }
    # )



event_loop: asyncio.AbstractEventLoop|None = None

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global event_loop 
    event_loop = asyncio.get_running_loop()

    # task = asyncio.create_task(test_input())
    yield
    # task.cancel()


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    unique_name = None

    try:
        # 第一次消息用于注册
        data = await websocket.receive_json()
        unique_name = data["unique_name"]

        print(f"{unique_name} 已连接")
        if unique_name in clients_list:
            print(f"{unique_name} 已存在，新连接将覆盖旧连接")

        clients_list[unique_name] = websocket

        while True:
            data = await websocket.receive_json()
            # print("收到:", data)
            eventDispatch.dispatch(
                DrawBridgeEvent.on_receive_message,
                {
                    "unique_name": unique_name,
                    "data": data,
                },
            )
    except Exception as e:
        print(e)
    finally:
        if unique_name is not None:
            if clients_list.get(unique_name) is websocket:
                clients_list.pop(unique_name)


def start_draw_bridge_server():
    uvicorn.run(app, host="127.0.0.1", port=5050)


threading.Thread(target=start_draw_bridge_server, daemon=True).start()
# if __name__ == "__main__":
#     start_mcp_server()