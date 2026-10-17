from supertonic import TTS

# 初始化，首次运行会自动下载模型 (~400MB)
tts = TTS(auto_download=True)

# 1. 选择一种语音风格
style = tts.get_voice_style(voice_name="F1") # 选择女性声音 F1

# 2. 生成中文语音
wav_zh, duration_zh = tts.synthesize(
    text="你好，欢迎使用 Supertonic 语音合成。",
    voice_style=style,
    lang="zh"  # 指定中文
)

# 3. 生成英文语音（使用同一种风格）
wav_en, duration_en = tts.synthesize(
    text="Hello, welcome to Supertonic text-to-speech.",
    voice_style=style,
    lang="en"  # 指定英文
)

# 4. 保存为音频文件
tts.save_audio(wav_zh, "output_zh.wav")
tts.save_audio(wav_en, "output_en.wav")