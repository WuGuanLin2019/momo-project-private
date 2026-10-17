import queue
from typing import Any
import soundfile as sf
import numpy as np

def clearQueue(q):
    try:
        while True:
            q.get_nowait()
    except queue.Empty:
        pass

def remove_from_queue(q: queue.Queue[Any], predicate):
    """删除队列中满足 predicate 的所有元素"""
    kept = []
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
        if not predicate(item):
            kept.append(item)
    for item in kept:
        q.put(item)

def getAudioFloatFromWav(path):
        # 读取 WAV 文件，soundfile 会自动处理格式和采样率
    audio_float, sr = sf.read(path, dtype="float32")
    
    # 如果是立体声，取一个声道
    if audio_float.ndim > 1:
        audio_float = audio_float.mean(axis=1)  # 或 audio_float[:, 0]
    
    # 如果采样率不是 16k，重采样到 16k（Faster-Whisper 需要）
    if sr != 16000:
        import librosa
        audio_float = librosa.resample(audio_float, orig_sr=sr, target_sr=16000)
        sr = 16000
    
    # 保证是 float32 且在 [-1, 1] 范围（soundfile 默认已如此）
    audio_float = audio_float.astype(np.float32)
    
    return audio_float