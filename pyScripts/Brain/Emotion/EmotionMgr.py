import threading
import time
from Brain.Emotion.Emotion import BaseEmotion, MomoEmotion


class EmotionMgr:
    def __init__(self):
        self.emotion_list:dict[str,BaseEmotion] = {}

    def get_emotion(self, emotion_name: str)->BaseEmotion:
        if emotion_name not in self.emotion_list:
            print(f"未找到情绪：{emotion_name}，直接创建。")
            self.emotion_list[emotion_name] = BaseEmotion(emotion_name)

        return self.emotion_list[emotion_name]

    def add_emotion(self,emotion:BaseEmotion):
        if emotion.name in self.emotion_list:
            print(f"已存在情绪：{emotion.name}，直接覆盖。")
        self.emotion_list[emotion.name] = emotion
    
    def update(self):
        for emotion in self.emotion_list.values():
            emotion.update()
            

emotionMgr = EmotionMgr()

last_update_time = time.time()
def emotion_update():
    global last_update_time
    if time.time() - last_update_time > 600:
        last_update_time = time.time()
        emotionMgr.update()

emotionMgr.add_emotion(emotion=MomoEmotion())


def _emotion_loop():
    while True:
        emotion_update()
        time.sleep(10)

threading.Thread(target = _emotion_loop, daemon = True).start()