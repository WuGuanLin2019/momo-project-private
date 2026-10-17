import queue
import threading
import time
from Body.VTube.VTube import VTubeClient
import numpy as np
from Core.State import GenerationState
import simpleaudio as sa

from Express.SpeakDataMgr import SpeakDataMgr, SpeakTask, SpeakTaskType

from .ExpressEvent import ExpressEvent
from DrawBridge.ReadBook.ReadingEvent import ReadingEvent
from Utils.EventDispatch import eventDispatch
from Utils.Timer import SmallTimer
from Utils.Tool import remove_from_queue
from .TTSMgr import ttsData

import logging

logger = logging.getLogger(__name__)

MomoVTube = VTubeClient()
MomoVTube.start()


def _init_event(speak_data_mgr: SpeakDataMgr, pipelineState: GenerationState):
    def _on_reccept_message(data):
        message_str = data.get("content")
        speed = data.get("speed", 0.95)
        task = SpeakTask(
            generation_id=pipelineState.generation,
            text=message_str,
            taskType=SpeakTaskType.reading,
            speed=speed,
        )
        speak_data_mgr.add_data(task)

    def _on_continue_read(_=None):
        speak_data_mgr.keep_data(SpeakTaskType.reading)

    eventDispatch.register(ReadingEvent.read_text, _on_reccept_message)
    eventDispatch.register(ReadingEvent.read_next_sentence, _on_continue_read)

    def _to_trigger_vtube_hot_key(hot_key_name):
        MomoVTube.to_trigger_hot_key(hot_key_name)
        # import traceback
        # traceback.print_stack()

    eventDispatch.register(
        ExpressEvent.trigger_vtube_hot_key, _to_trigger_vtube_hot_key
    )


def _normalize_audio(audio_data):
    # 1) RMS 响度归一化（听感一致），替代峰值归一化
    rms = float(np.sqrt(np.mean(audio_data**2)))
    # logger.info(f"rms: {rms}")
    TARGET_RMS = 0.04  # 目标响度，可微调
    if rms > 1e-6:
        gain = TARGET_RMS / rms
        gain = min(gain, 8.0)  # 限制增益上限，避免极静片段被推爆/底噪放大
        audio_data = audio_data * gain

    # 2) 软限幅：超过阈值的瞬态平滑压住，避免硬裁剪爆音
    ceiling = 0.99
    over = np.abs(audio_data) > ceiling
    if over.any():
        mag = np.abs(audio_data[over])
        audio_data[over] = np.sign(audio_data[over]) * (
            ceiling + (1 - ceiling) * np.tanh((mag - ceiling) / (1 - ceiling))
        )
    return audio_data


def playVoice(audio_data, sample_rate):
    if audio_data is None:
        return

    audio_data = np.clip(audio_data, -1.0, 1.0)

    # 音量归一化
    audio_data = _normalize_audio(audio_data)

    if audio_data.dtype != np.int16:
        audio_data = (audio_data * 32767).astype(np.int16)

    playObject = sa.play_buffer(audio_data, 1, 2, sample_rate)
    return playObject


def _only_play_voice(audio_data, sample_rate, check_generate_break):
    playObject = playVoice(audio_data, sample_rate)
    # todo
    if playObject:
        while playObject.is_playing():
            if check_generate_break():
                playObject.stop()
                return 0
            time.sleep(0.1)
    return True


def loop(
    speak_data_mgr: SpeakDataMgr,
    pipelineState: GenerationState,
    event_is_talking: threading.Event,
):
    _init_event(speak_data_mgr, pipelineState)

    while True:
        speak_task = speak_data_mgr.get_data()
        if not pipelineState.check_is_current_generation(speak_task.generation_id):
            continue

        if speak_task.text.strip() == "":
            # 有可能是句尾的空字符串
            eventDispatch.dispatch(ExpressEvent.on_tts_end, speak_task)
            continue

        try:
            audio_data, sample_rate = ttsData(speak_task.text, speak_task.speed)
        except Exception as e:
            print(f"tts错误：{e}")
            eventDispatch.dispatch(
                ExpressEvent.on_tts_error, {"task": speak_task, "error": e}
            )
            continue

        def check_generate_break():
            return not pipelineState.check_is_current_generation(
                speak_task.generation_id
            )

        event_is_talking.set()
        # logging.info("set talking event!")
        duration = 0
        if audio_data is not None and sample_rate:
            duration = len(audio_data) / sample_rate

        eventDispatch.dispatch(
            ExpressEvent.on_tts_start,
            {
                "task": speak_task,
                "duration": duration,
            },
        )
        try:
            result = None
            if MomoVTube.connected:
                result = MomoVTube.drive_mouth(
                    audio_data, sample_rate, playVoice, check_generate_break
                )
            else:
                result = _only_play_voice(audio_data, sample_rate, check_generate_break)
        finally:
            event_is_talking.clear()

        is_interrupt = result == 0
        eventDispatch.dispatch(
            ExpressEvent.on_tts_end,
            {
                "task": speak_task,
                "is_interrupt": is_interrupt,
            },
        )
