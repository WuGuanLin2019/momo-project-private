from faster_whisper import WhisperModel
from Utils.Tool import getAudioFloatFromWav
from Utils.Timer import SmallTimer

# 配置
FS = 16000  # 采样率
CHANNELS = 1  # 单声道

with SmallTimer("加载Whisper模型"):
    print("加载Whisper模型...")
    model = WhisperModel(
        "large-v3",
        # "medium",
        # "small",
        # device="cuda",
        compute_type="float16"
    )
    print("模型加载完成。")


def audio_to_text(audio_float):
    if audio_float is None:
        return None,True
    
    segments, info = model.transcribe(
        audio_float,
        language="zh",
        beam_size=9,
        vad_filter=True,
        initial_prompt="以下内容是普通话或者粤语。"
    )
    text = ""

    text = "".join(segment.text for segment in segments)

    text = text.strip()
    print("识别结果:", text)
    if "明镜与点点" in text:
        text = ""
    # print("\n——下一次录音——\n")
    return text,True

# if __name__ == "__main__":
#     audio_float = getAudioFloatFromWav("Temp/inputWords.wav")
#     audio_to_text(audio_float)