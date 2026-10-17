from dataclasses import dataclass
from enum import Enum
import threading


class SpeakTaskType(Enum):
    normal = 1,
    reading = 2,
    reading_thought = 3,    #读后感想
    bulletChatRespone = 4,


@dataclass
class SpeakTask:
    generation_id: int
    text: str
    taskType: SpeakTaskType = SpeakTaskType.normal
    speed:float = 0.89
    is_tail:bool = False
    is_head:bool = False

class SpeakDataMgr:
    def __init__(self):
        self.datas: list[SpeakTask] = []
        self.datas_cache:list[SpeakTask] = []

        self.condition = threading.Condition()
    

    def add_data(self, data: SpeakTask):
        with self.condition:
            if data.taskType == SpeakTaskType.reading:                
                if not self.datas or self.datas[-1].is_tail:
                    self.datas.append(data)
                    if data.is_tail:
                        self.datas = self.datas + self.datas_cache
                        self.datas_cache.clear()
                else:
                    self.datas_cache.append(data)
            else:
                self.datas.append(data)

            self.condition.notify()

    def get_data(self) -> SpeakTask:
        with self.condition:
            while not self.datas:
                self.condition.wait()
            return self.datas.pop(0)

    def keep_data(self, data_type: SpeakTaskType):
        with self.condition:
            self.datas = [d for d in self.datas if d.taskType == data_type]

    def clear_data(self, data_type: SpeakTaskType):
        with self.condition:
            self.datas = [d for d in self.datas if d.taskType != data_type]