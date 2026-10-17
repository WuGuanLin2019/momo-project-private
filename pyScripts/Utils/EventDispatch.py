
from collections import defaultdict
from typing import Callable, Any


class EventDispatch:
    def __init__(self):
        self._listeners = defaultdict(list)

    def register(self, event: str, callback: Callable):
        """注册事件"""
        if callback not in self._listeners[event]:
            self._listeners[event].append(callback)
            
    def unregister(self, event: str, callback: Callable):
        """移除事件"""
        if callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def dispatch(self, event: str, data: Any = None):
        """派发事件"""
        for callback in self._listeners[event]:
            callback(data)



eventDispatch = EventDispatch()

# async def on_tts_finish(data):
#     print("TTS结束:", data)

# events.on("TTS_FINISH", on_tts_finish)

# await events.emit("TTS_FINISH", {
#     "type": "original"
# })

