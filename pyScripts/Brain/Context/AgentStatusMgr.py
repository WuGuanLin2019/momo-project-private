from dataclasses import dataclass
from enum import Enum
from typing import Callable


AGENT_STATUS_KEY = "agent_status"

@dataclass
class StatusData:
    key: str
    fun: Callable[[], str]

    def __post_init__(self):
        if not self.key:
            raise Exception("key is empty")


class AgentStatusPiecer:
    def __init__(self):
        self.name = ""
        self.datas: dict[str, StatusData] = {}

    def add(self, data: StatusData):
        if data.key in self.datas:
            print(f"key {data.key} is already exists")
            return

        self.datas[data.key] = data

    def remove(self, key: str):
        if key in self.datas:
            self.datas.pop(key)
        

    def get_full_status(self):
        if len(self.datas) == 0:
            return None

        result:str = f"<{AGENT_STATUS_KEY}>"
        for v in self.datas.values():
            result += v.fun()
            result += "\n"

        result += f"</{AGENT_STATUS_KEY}>"

        return result
