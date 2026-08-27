import numpy as np
import simpleaudio as sa
import requests
import io
import soundfile as sf

from Utils.Timer import SmallTimer

TTS_PORT = 5004

_tts_session = requests.Session()

def request_audio_data(text):
    #使用melo
    # with SmallTimer("request melo"):
    resp = _tts_session.post(f"http://127.0.0.1:{TTS_PORT}/tts", json={"text": text}, timeout=180)
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