import logging
from typing import Any, Callable

# 跨模块依赖收敛到本中立模块；needle 会把多余参数原样转发给被注册的函数
from Utils.EventDispatch import eventDispatch


class DrawBridgeNeedle:
    def __init__(self, config: dict[str, Callable[..., Any]]):
        self.needles: dict[str, Callable[..., Any]] = config

    def needle(self, intention: str, *args) -> Any|None:
        fn = self.needles.get(intention)
        if fn is None:
            logging.warning(f"未找到意图：{intention}")
            return None
        return fn(*args)


def _get_new_input_after_reading_thought():
    from DrawBridge.BulletChat.BulletChatEvent import BulletChatEvent
    from DrawBridge.BulletChat.BulletChatMgr import bullet_chat_mgr
    if bullet_chat_mgr.has_new_data:
        eventDispatch.dispatch(BulletChatEvent.receive_current_bullet_chat)
        return True
    return False

config: dict[str, Callable[..., Any]] = {
    "get_new_input_after_reading_thought": _get_new_input_after_reading_thought,
}

drawBridgeNeedle = DrawBridgeNeedle(config)

