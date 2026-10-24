from dataclasses import dataclass
from enum import Enum

class PriorityType(Enum):
    system = 100
    mcp = 50
    user = 0

@dataclass
class PromptData:
    key: str
    text: str
    priority: PriorityType = PriorityType.user

    def __post_init__(self):
        if not self.key:
            raise Exception("key is empty")


class PromptPiecer:
    def __init__(self):
        self.datas: dict[str, PromptData] = {}

    def add(self, data: PromptData):
        if data.key in self.datas:
            print(f"key {data.key} is already exists")
            return

        self.datas[data.key] = data

    def remove(self, key: str):
        self.datas.pop(key, None)

    def get_full_text(self):
        ordered_datas = sorted(self.datas.values(), key=lambda d: d.priority.value, reverse=False)
        return "\n".join(d.text for d in ordered_datas if d.text)
