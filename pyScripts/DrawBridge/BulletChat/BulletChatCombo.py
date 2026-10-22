# 处理回复弹幕的频率问题，主要兼容频繁点赞，弹幕非常多的情况
# 期待效果：用户互动的成本和momo的反馈能成正比。
# 比如：用户的第一次点赞会较快反馈，之后的频繁点赞反馈会变慢

import time
from typing import Any

COMBO_KIND_CD: dict[str, int] = {
    "like": 10,
}

class BulletChatComboData:


    def __init__(self,user_name) -> None:
        self.user_name: str = user_name
        self.next_allow_to_push_time: dict[str, float] = {}
        self.handle_kind:set[str] = set()

    def judge(self, kind: str) -> bool:
        cur_time = time.time()
        if cur_time < self.next_allow_to_push_time.get(kind, 0):
            print(f"暂时冻结弹幕 {self.user_name:} ： {self.next_allow_to_push_time.get(kind, 0) - cur_time}")
            return False

        self.handle_kind.add(kind)
        return True

    def update_push_time(self):
        cur_time = time.time()
        for kind in self.handle_kind:
            print(f"update push time: {self.user_name}")
            self.next_allow_to_push_time[kind] = cur_time + COMBO_KIND_CD.get(
                kind, 10
            )
        self.handle_kind.clear()


class BulletChatComboHanlder:
    def __init__(self) -> None:
        self.combo_data: list[BulletChatComboData] = []
        self.cache_bullet_chat_data = []


    def _filter(self, data) -> bool:
        kind = data.get("kind")
        if kind not in COMBO_KIND_CD.keys():
            return True

        user_name = data.get("user")
        user_combo_data = next(
            (c for c in self.combo_data if c.user_name == user_name),
            None,
        )
        if not user_combo_data:
            user_combo_data = BulletChatComboData(user_name)
            self.combo_data.append(user_combo_data)

        can_send = user_combo_data.judge(kind)
        return can_send


    def handle(self, data):
        if not isinstance(data, list):
            return []

        handle_data = self.cache_bullet_chat_data + data
        self.cache_bullet_chat_data.clear()

        output_data = []
        push_flag = False
        for v in handle_data:
            result = self._filter(v)
            #有一个可以推送，就推当前已有的
            push_flag = push_flag or result

        if not push_flag:
            self.cache_bullet_chat_data.extend(handle_data)
        else:
            output_data = handle_data

        return output_data

    def handle_cache(self):
        if self.cache_bullet_chat_data:
            return self.handle([])
        return []

    def update_push_time(self):
        for c in self.combo_data:
            c.update_push_time()

