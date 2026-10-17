import numpy as np
import simpleaudio as sa
import requests
import io
import soundfile as sf

from Utils.Timer import SmallTimer
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from langchain.tools import tool

TTS_PORT = 5004

_tts_session = requests.Session()
_retry = Retry(
    connect=3, read=3, status=0, backoff_factor=0.5, allowed_methods=frozenset(["POST"])
)
_tts_session.mount("http://", HTTPAdapter(max_retries=_retry))


def request_audio_data(text, speed):
    # 使用melo
    # with SmallTimer("request melo"):
    resp = _tts_session.post(
        f"http://127.0.0.1:{TTS_PORT}/tts",
        json={"text": text, "speed": speed},
        timeout=180,
        headers={"Connection": "close"},   #不复用旧连接
    )
    # print(f"[tts_client] status={resp.status_code}, content-type={resp.headers.get('content-type')}, len={len(resp.content)}")

    if resp.status_code != 200:
        print(f"[tts_client] 服务端错误: {resp.text[:200]}")
        return None, None

    content = resp.content
    try:
        # with SmallTimer("read res data"):
        audio_data, sample_rate = sf.read(io.BytesIO(content))
        return audio_data, sample_rate
    except Exception as e:
        print(f"[tts_client] 解码音频失败: {e}")
        print(f"[tts_client] 前200字节: {resp.content[:200]}")
        return None, None

@tool
def learn_polyphonic(data:str):
    """ 
    当WU指出你多音字不正确的时候，请使用这个工具来学习多音字。
    拼音用数字声调：1 2 3 4，轻声用 5
    '-' 表示该字沿用默认读音，只改需要改的那个字
    args:
        data: 多音字的数据，格式为"多音字 读音1 读音2 读音3"

    几个例子：
    learn_polyphonic("变长 bian4 chang2")
    learn_polyphonic("生长 - zhang3")
    learn_polyphonic("睡不着觉 - - - jiao4")
    """
    resp = _tts_session.post(
        f"http://127.0.0.1:{TTS_PORT}/learn_polyphonic",
        json={"polyphonic_data": data, },
        timeout=180,
        headers={"Connection": "close"},   #不复用旧连接
    )
    # print(f"[tts_client] status={resp.status_code}, content-type={resp.headers.get('content-type')}, len={len(resp.content)}")

    if resp.status_code != 200:
        print(f"[tts_client] 服务端错误: {resp.text[:200]}")
        return "多音字学习失败，语音系统服务器错误。"
    
    if resp.text == "True":
        return "多音字学习成功。"
    else:
        return "多音字学习失败，请检查格式。"

# if __name__ == "__main__":
#     texts = [
#         "我来报个数目：",
#         "1,2,3,4,5,",
#         "额，接下来是什么来着？",
#         "哦，记起来了。",
#         "是6,7,8,9"
#     ]
#     def playVoice(audio_data, sample_rate):
#         if audio_data is None:
#             return

#         if audio_data.dtype != np.int16:
#             audio_data = (audio_data * 32767).astype(np.int16)

#         playObject = sa.play_buffer(audio_data, 1, 2, sample_rate)
#         return playObject

#     for text in texts:
#         audio_data, sample_rate = request_audio_data(text)
#         playObject = playVoice(audio_data, sample_rate)
#         if playObject is not None:
#             playObject.wait_done()
