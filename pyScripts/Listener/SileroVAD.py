from dataclasses import dataclass
from queue import Empty, Queue
import threading
import keyboard
from numpy.typing import NDArray
import sounddevice as sd
import numpy as np
from silero_vad import load_silero_vad
import torch
from collections import deque

from Core.State import GenerationState
import time


# 音频参数
FS = 16000
CHANNELS = 1
BLOCK_SIZE = 512  # Silero VAD 标准块大小（32ms @ 16kHz）

# VAD 参数
SPEECH_THRESHOLD = 0.5  # 语音概率阈值
SILENCE_DURATION = 0.6  # 静音持续多少秒后停止录音（容忍停顿）
MIN_SPEECH_DURATION = 0.3  # 最短有效语音时长，避免误触发

# 音量阈值（RMS）
VOLUME_THRESHOLD = 0.015

# RingBuffer 预留 ms 数
RING_MS = 800  # 缓存最近
RING_SIZE = int(FS * (RING_MS / 1000))  # 计算 samples 数

# 加载 Silero VAD 模型
print("⏳ 正在加载 VAD 模型...")
model = load_silero_vad()
print("✅ 模型加载完成，开始监听...")


SILENCE_BLOCKS_MAX = int(SILENCE_DURATION * FS / BLOCK_SIZE)
SPEECH_BLOCKS_MIN = int(MIN_SPEECH_DURATION * FS / BLOCK_SIZE)


@dataclass
class AudioBufferData:
    audio_buffer: NDArray[np.float32]
    gen_id: int
    is_done: bool = False


class AudioListener:
    def __init__(
        self, pipelineState: GenerationState, event_is_talking: threading.Event
    ):
        self.result_queue = Queue()
        self.pipelineState = pipelineState
        self.event_is_talking = event_is_talking

        # 状态变量
        self.audio_buffer = []  # 录音数据累积
        self.is_speaking = False  # 当前是否在说话
        self.silence_blocks = 0  # 连续静音块计数
        self.speech_blocks = 0  # 连续语音块计数

        # 创建并启动输入流
        self.stream = sd.InputStream(
            channels=CHANNELS,
            samplerate=FS,
            blocksize=BLOCK_SIZE,
            callback=self.callback,
            dtype=np.float32,  # Silero VAD 需要 float32 格式
        )

        print("🔇 保持安静，说话时将自动开始录音...\n")
        self.stream.start()

        # 初始化环形缓冲
        self.ring_buffer = deque(maxlen=RING_SIZE)

    def callback(self, indata, frames, time, status):
        if status:
            print(f"⚠️ 状态异常: {status}")
            return

        # 提取单声道音频
        audio_chunk = indata[:, 0].copy()

        self.ring_buffer.extend(audio_chunk)

        # 检测响度
        rms = np.sqrt(np.mean(audio_chunk**2))

        if rms > VOLUME_THRESHOLD:
            # ---- 转换为 Tensor 后再送入 VAD ----
            audio_tensor = torch.from_numpy(audio_chunk)
            speech_prob = model(audio_tensor, FS).item()
        else:
            speech_prob = 0.0

        if speech_prob > SPEECH_THRESHOLD and rms > VOLUME_THRESHOLD:
            self.speech_blocks += 1
            self.silence_blocks = 0
            if not self.is_speaking and self.speech_blocks >= SPEECH_BLOCKS_MIN:
                # 这时候打断所有流程，重新开始，注意记录已经表达的上下文
                self.pipelineState.add_generation()

                print("🎤 检测到语音，开始录音...")
                self.is_speaking = True
                self.audio_buffer.extend(list(self.ring_buffer))
                self.ring_buffer.clear()

            if self.is_speaking:
                self.audio_buffer.extend(audio_chunk)

        else:
            self.silence_blocks += 1
            self.speech_blocks = 0

            if self.is_speaking:
                self.audio_buffer.extend(audio_chunk)
                if self.silence_blocks >= SILENCE_BLOCKS_MAX:
                    self.is_speaking = False
                    print("🛑 检测到持续静音，录音结束")
                    if len(self.audio_buffer) > 0:
                        audio_np = np.array(self.audio_buffer, dtype=np.float32)
                        self.result_queue.put(audio_np)

                        self.audio_buffer.clear()
                        self.silence_blocks = 0

    def auto_record(self):
        try:
            while True:
                try:
                    audio_np = self.result_queue.get(timeout=0.2)  # 0.2 秒醒一次
                except Empty:
                    continue  # 没数据就回到循环顶部，重新检查 Esc

                duration = len(audio_np) / FS
                if duration < MIN_SPEECH_DURATION:
                    print(f"⚠️ 录音 {duration:.1f} 秒过短，跳过\n")
                    continue

                print(f"📝 录音时长: {duration:.1f} 秒，输出音频数组...")

                print("-" * 40 + "\n")
                return audio_np

        except KeyboardInterrupt:
            print("\n👋 退出")
            self.stream.stop()
            self.stream.close()


class AudioStreamListener:
    def __init__(
        self, pipelineState: GenerationState, event_is_talking: threading.Event
    ):
        self.result_queue = Queue()
        self.pipelineState = pipelineState
        # self.event_is_talking = event_is_talking

        # 状态变量
        self.audio_buffer = []  # 录音数据累积
        self.is_speaking = False  # 当前是否在说话
        self.silence_blocks = 0  # 连续静音块计数
        self.speech_blocks = 0  # 连续语音块计数
               
        self.ring_buffer = deque(maxlen=RING_SIZE)  # 初始化环形缓冲

        # 创建并启动输入流
        self.stream = sd.InputStream(
            channels=CHANNELS,
            samplerate=FS,
            blocksize=BLOCK_SIZE,
            callback=self.callback,
            dtype=np.float32,  # Silero VAD 需要 float32 格式
        )

        print("🔇 保持安静，说话时将自动开始录音...\n")
        self.stream.start()

        self.audio_record_chunks = []
        self.to_send_last_audio_chunk = False

    def callback(self, indata, frames, time, status):
        if status:
            print(f"⚠️ 状态异常: {status}")
            # return

        # 提取单声道音频
        audio_chunk = indata[:, 0].copy()
        self.audio_record_chunks.extend(audio_chunk)

        
    def handle_audio_chunk(self):
        if len(self.audio_record_chunks) == 0:
            return

        audio_chunk = np.array(self.audio_record_chunks, dtype=np.float32)
        self.audio_record_chunks.clear()

        if audio_chunk.size == 0:
            return

        # 取最后一个 512 块
        last_512 = audio_chunk[-512:]

        self.ring_buffer.extend(audio_chunk)

        # 检测响度
        rms = np.sqrt(np.mean(last_512**2))

        speech_prob = 0.0
        if rms > VOLUME_THRESHOLD:
            # ---- 转换为 Tensor 后再送入 VAD ----
            audio_tensor = torch.from_numpy(last_512)
            speech_prob = model(audio_tensor, FS).item()

        if speech_prob > SPEECH_THRESHOLD:
            self.speech_blocks += 1
            self.silence_blocks = 0
            if not self.is_speaking and self.speech_blocks >= SPEECH_BLOCKS_MIN:
                # 这时候打断所有流程，重新开始，注意记录已经表达的上下文
                self.pipelineState.add_generation()

                print("🎤 检测到语音，开始录音...")
                self.is_speaking = True
                self.audio_buffer.extend(list(self.ring_buffer))
                self.ring_buffer.clear()

            if self.is_speaking:
                self.audio_buffer.extend(audio_chunk)

        else:
            self.silence_blocks += 1
            self.speech_blocks = 0

            if self.is_speaking:
                self.audio_buffer.extend(audio_chunk)
                if self.silence_blocks >= SILENCE_BLOCKS_MAX:
                    self.is_speaking = False
                    self.to_send_last_audio_chunk = True
                    print("🛑 检测到持续静音，录音结束")
                    if len(self.audio_buffer) > 0:
                        self.audio_buffer.clear()
                        self.silence_blocks = 0


    def auto_record(self):
        try:
            while True:
                self.handle_audio_chunk()

                duration = len(self.audio_buffer) / FS      
                                
                if duration < 0.25 and not self.to_send_last_audio_chunk:
                    time.sleep(0.01)
                    continue
            
                # print(f"duration:{duration}, isDone:{self.to_send_last_audio_chunk}")
                try:
                    audio_np = np.array(self.audio_buffer, dtype=np.float32)
                    self.audio_buffer.clear()
                except Empty:
                    continue  # 没数据就回到循环顶部，重新检查 Esc

                abData = AudioBufferData(
                    audio_buffer=audio_np,
                    gen_id=self.pipelineState.generation,
                    is_done=self.to_send_last_audio_chunk,
                )
                self.to_send_last_audio_chunk = False

                # print("-" * 40 + "\n")
                return abData

        except KeyboardInterrupt:
            print("\n👋 退出")
            self.stream.stop()
            self.stream.close()
