from dataclasses import dataclass
from typing_extensions import override
from Utils.noob_math import push_to


@dataclass
class EmotionAttr:
    name: str
    value: float
    init_value: float
    desc: str


class BaseEmotion:
    def __init__(self, name: str):
        self.name: str = name
        self.attrs: list[EmotionAttr] = []

        self._init_attr()

    def _init_attr(self):
        pass

    def update(self):
        """周期性情绪更新钩子，子类按需覆写。"""
        pass

    def get_emotion_str(self) -> str:
        if len(self.attrs) == 0:
            return "当前没有情绪。"

        result = "状态值均为float，范围0~1\n"
        for attr in self.attrs:
            result += f"{attr.name}: {attr.value}({attr.desc})\n"

        return result

    def change_attr(self, name: str, value: float):
        if value == 0:
            return
        for attr in self.attrs:
            if attr.name == name:
                origin_value = attr.value
                new_value = min(1, max(0, attr.value + value))
                attr.value = round(new_value, 2)
                print(f"emotion attr【{attr.name}】{origin_value}->{attr.value}")
                    


class MomoEmotion(BaseEmotion):
    def __init__(self):
        super().__init__("Momo")


    def _init_attr(self):
        def register_attr(name: str, init_value: float, desc: str):
            self.attrs.append(EmotionAttr(name, init_value, init_value, desc))

        register_attr("愉悦", 0, "0是无愉悦之感，1是很开心")
        register_attr("沮丧", 0, "0是无沮丧之感，1是很失落")
        register_attr("兴奋", 0.5, "0是很无聊，1是很兴致勃勃")
        register_attr("紧张", 0.5, "0是很放松，1是很谨慎")

    
    @override
    def update(self):
        for attr in self.attrs:
            attr.value = push_to(attr.value, attr.init_value, 0.1)
