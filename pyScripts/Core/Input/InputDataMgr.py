from dataclasses import dataclass
from enum import Enum
from functools import cmp_to_key
from queue import Queue
import threading
import time


class InputSource(Enum):
    Normal = 0
    Microphone = 1
    ReadBook = 2
    BulletChat = 3
    
    SYSTEM = -1
    
class InputType(Enum):
    TEXT = 0


@dataclass
class InputData:
    source: InputSource = InputSource.Normal
    content: str = ""
    dataType: InputType = InputType.TEXT
    priority: int = -1  #越大优先级越高
    timeStamp: float = 0

    PRIORITY_MAP = {
        InputSource.Microphone: 100,
        InputSource.BulletChat: -2,
    }

    def __post_init__(self):
        # 优先级为-1则表示未进行赋值
        if self.priority == -1:
            self.priority = self.PRIORITY_MAP.get(self.source, 0)

        self.timeStamp = time.time()


class InputDataMgr:
    def __init__(self):
        self.datas: list[InputData] = []
        self.condition = threading.Condition()

    def _sort_datas(self, a: InputData, b: InputData) -> bool:
        if a.priority != b.priority:
            return a.priority > b.priority
        return a.timeStamp < b.timeStamp

    def _handle_data(self):
        #排序
        self.datas.sort(key=cmp_to_key(self._sort_datas))

    def add_data(self, data: InputData):
        with self.condition:
            self.datas.append(data)
            self._handle_data()
            self.condition.notify()

    def get_data(self) -> InputData:
        with self.condition:
            while not self.datas:
                self.condition.wait()
            return self.datas.pop(0)

    def clear_data(self):
        with self.condition:
            # todo 改成只把wu的消息清除
            self.datas.clear()
