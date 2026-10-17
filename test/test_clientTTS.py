import numpy as np
import simpleaudio as sa

from pyScripts.Data.config import BACKEND_PORT

def playVoice(audio_data, sample_rate):
    if audio_data is None:
        return

    # ✅ 加调试：打印实际情况
    print(f"[playVoice] shape={audio_data.shape}, dtype={audio_data.dtype}, sr={sample_rate}")

    # ✅ 处理多声道：转单声道
    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=1)

    if audio_data.dtype != np.int16:
        audio_data = (audio_data * 32767).astype(np.int16)

    playObject = sa.play_buffer(audio_data, 1, 2, sample_rate)        
    return playObject


import requests
import io
import soundfile as sf

def cosy_tts(text):
    resp = requests.post(f"http://127.0.0.1:{BACKEND_PORT}/tts", json={"text": text}, timeout=180)
    if resp.status_code == 200:
        audio_data, sample_rate = sf.read(io.BytesIO(resp.content))
        
        # return audio_data, sample_rate
        pO = playVoice(audio_data, sample_rate)
        if pO:
            pO.wait_done()
    return None, None


cosy_tts("这个project对我们部门来说，太pro了。")