import sys
import os
ffmpeg_bin_path = r"D:\\Program Files\\MindProject\\third_party\\ffmpeg-8.1.2-full_build-shared\\bin" 
os.add_dll_directory(ffmpeg_bin_path)

# 直接从项目根目录的相对路径
sys.path.append("../third_party/CosyVoice-main")

from cosyvoice.cli.cosyvoice import AutoModel
import torchaudio

cosyvoice = AutoModel(model_dir="FunAudioLLM/Fun-CosyVoice3-0.5B-2512")

for i, j in enumerate(
    cosyvoice.inference_zero_shot(
        "你要离开，我知道很简单。",
        "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。",
        "./asset/zero_shot_prompt.wav",
        stream=False,
    )
):
    torchaudio.save(
        "zero_shot_{}.wav".format(i), j["tts_speech"], cosyvoice.sample_rate
    )
