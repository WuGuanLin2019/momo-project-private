import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"   # <-- 添加这一行，必须在所有 import 之前

from Core.Pipeline import AssistantPipeline
import sys
import logging

logging.basicConfig(level=logging.INFO)
mainP = AssistantPipeline()
mainP.start()

print("Assistant running... 按 Ctrl+C 退出")


def start_read():
    from Utils.EventDispatch import eventDispatch
    from DrawBridge.ReadBook.ReadingEvent import ReadingEvent
    print("阅读开始")
    # 只作为「开发期触发源」之一：派发命令事件，不直接依赖 ReadingMgr
    eventDispatch.dispatch(ReadingEvent.start_read, mainP.event_is_talking)


def end_read():
    from Utils.EventDispatch import eventDispatch
    from DrawBridge.ReadBook.ReadingEvent import ReadingEvent
    print("阅读结束")
    eventDispatch.dispatch(ReadingEvent.finish_read)

def switch_mic():
    from Utils.EventDispatch import eventDispatch
    from Listener.ListenEvent import ListenEvent
    eventDispatch.dispatch(event=ListenEvent.mic_switch)

def switch_bullet_chat():
    from DrawBridge.BulletChat.BulletChatMgr import bullet_chat_mgr
    bullet_chat_mgr.switch_listening()


import msvcrt 
try:
    while True:
        ch = msvcrt.getwch()      # 阻塞等一个按键
        if ch == " ":             # 空格
            start_read()
        elif ch =="q":
            end_read()
        elif ch =="m":
            switch_mic()
        elif ch =="b":
            switch_bullet_chat()
        # time.sleep(1)

except KeyboardInterrupt:
    # mainP.shut_down()
    print("\n用户手动退出，程序结束")
     
    sys.exit(0)
