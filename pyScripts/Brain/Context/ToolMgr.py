from dataclasses import dataclass
from enum import Enum

from langchain.tools import tool
from langchain_core.tools.base import BaseTool


@dataclass
class ToolData:
    key: str
    tools: list[BaseTool]

    def __post_init__(self):
        if not self.key:
            raise Exception("key is empty")


class ToolPiecer:
    def __init__(self):
        self.name = ""
        self.datas: dict[str, ToolData] = {}

    def add(self, data: ToolData):
        if data.key in self.datas:
            print(f"key {data.key} is already exists")
            return

        self.datas[data.key] = data

    def remove(self, key: str):
        if key in self.datas:
            self.datas.pop(key)
        

    def get_full_tool(self):
        result:list[BaseTool] = []
        for v in self.datas.values():
            result += v.tools

        return result
