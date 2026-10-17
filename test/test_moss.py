from random import sample
import subprocess
import os
import numpy as np
import simpleaudio as sa

def tts_synthesize(text, output_path="output.wav"):
    moss_dir = r"D:\Program Files\MindProject\third_party\MOSS-TTS-Nano-main"
    ref_audio = os.path.join(moss_dir, "assets/audio/zh_6.wav")
    output_path = r"D:\Program Files\MindProject\third_party\MOSS-TTS-Nano-main\generated_audio\output.wav"

    # 直接使用 conda 环境中的 python 解释器
    python_exe = r"E:\ProgramData\miniconda3\envs\moss_tts\python.exe"  # 根据实际路径调整

    generate_script = os.path.join(moss_dir, "infer.py")

# python infer.py --prompt-audio-path assets/audio/zh_1.wav --text "你好，我是AI主播" --output-audio-path output.wav
    cmd = [
        python_exe,  generate_script,
        "--prompt-audio-path", ref_audio,
        "--text", text,
        "--output-audio-path", output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=moss_dir)

    if result.stderr:
        print("合成失败:", result.stderr)
        return None

    if result.returncode == 0:
        print("语音合成成功"+output_path)
        return output_path
    else:
        print("合成失败:", result.stderr)
        return None

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

if __name__ == "__main__":
    # tts_synthesize("我————爱————你！")
    output_path = r"D:\Program Files\MindProject\third_party\MOSS-TTS-Nano-main\generated_audio\output.wav"
    import soundfile as sf
    audio_data, sample_rate = sf.read(output_path)
    play_obj = playVoice(audio_data,sample_rate)
    play_obj.wait_done()   
