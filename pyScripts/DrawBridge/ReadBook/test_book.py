import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
import uvicorn

pdf_clients: set[WebSocket] = set()

async def pdf_goto_page(page: int):
    # 先拷贝一份，避免发送过程中集合被其它协程修改
    for ws in list(pdf_clients):
        try:
            await ws.send_json({
                "action": "goto",
                "page": page
            })
        except Exception:
            # 单个连接发送失败（如已断开）不应中断对其余客户端的广播
            pdf_clients.discard(ws)

async def test_fun(fun_idx: int):
    # 先拷贝一份，避免发送过程中集合被其它协程修改
    for ws in list(pdf_clients):
        try:
            if fun_idx == 1:
                await ws.send_json({
                "action": "get_next_sentence",
                # "page": page
            })
            elif fun_idx == 2:
                await ws.send_json({
                "action": "focus_on_selection",
            })
        except Exception:
            # 单个连接发送失败（如已断开）不应中断对其余客户端的广播
            pdf_clients.discard(ws)


async def keyboard_listener():
    """后台协程：监听按键，按空格让页面跳到第 6 页"""
    import msvcrt
    while True:
        # getwch() 是阻塞调用，放进线程池执行，避免卡住事件循环
        ch = await asyncio.to_thread(msvcrt.getwch)
        if ch == "a":             # 空格
            await test_fun(1)
        if ch == "b":             # 空格
            await test_fun(2)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 服务启动时拉起按键监听，服务关闭时随之取消
    task = asyncio.create_task(keyboard_listener())
    yield
    _ = task.cancel()


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    pdf_clients.add(websocket)
    print("PDF.js 已连接")
    try:
        while True:
            data = await websocket.receive_text()
            print("收到:", data)
    except Exception:
        pass
    finally:
        # 无论正常还是异常断开都要清理；discard 避免重复移除抛 KeyError
        pdf_clients.discard(websocket)


@app.get("/test_page/{page}")
async def test_page(page: int):
    await pdf_goto_page(page)
    return {"page": page}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5050)