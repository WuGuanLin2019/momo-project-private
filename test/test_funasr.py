from funasr import AutoModel
import os
ffmpeg_bin_path = r"D:\\Program Files\\MindProject\\third_party\\ffmpeg-8.1.2-full_build-shared\\bin" 
os.add_dll_directory(ffmpeg_bin_path)

model = AutoModel(
    model="iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
    # device="cpu"  # 强制用 CPU
)

input=r"D:\Program Files\MindProject\test\output.wav",

res = model.generate(
    input=input,
    cache={},
    is_final=True
)


print(res)

# import torch

# print(torch.__version__)
# print(torch.version.cuda)
# print(torch.cuda.get_arch_list())
# print(torch.cuda.get_device_name())