from Core.Input.InputDataMgr import InputData, InputDataMgr, InputSource
from Core.State import GenerationState
import queue
from Express.ExpressEvent import ExpressEvent
from Listener.ListenEvent import ListenEvent
from DrawBridge.ReadBook.ReadingEvent import ReadingEvent
from Utils.EventDispatch import eventDispatch
from Listener.SileroVAD import AudioBufferData, AudioStreamListener
from Listener.STT_Client import STT_Loop
import threading

def _init_event(input_data_mgr:InputDataMgr):
    def _on_read_text(text:str):
        data = InputData(InputSource.ReadBook,text)
        input_data_mgr.add_data(data)

    def _on_tts_error(data):
        _error = data["error"]
        # data = InputData(InputSource.Normal,f"语音系统刚刚出了点问题:{_error}")
        # input_data_mgr.add_data(data)

    def _push_input_data(data:InputData):
        if data:
            input_data_mgr.add_data(data)

    eventDispatch.register(ReadingEvent.consider_text,_on_read_text)
    eventDispatch.register(ExpressEvent.on_tts_error,_on_tts_error)
    eventDispatch.register(ListenEvent.push_input_data,_push_input_data)

def listen_loop(
    input_data_mgr: InputDataMgr, pipelineState: GenerationState, event_is_talking
):
    _init_event(input_data_mgr)
    audioListener = AudioStreamListener(pipelineState, event_is_talking)
    eventDispatch.register(ListenEvent.mic_switch, audioListener.on_mic_switch)
    my_generate_state: GenerationState = GenerationState()

    def check_generate_break():
        return not pipelineState.check_is_current_generation(my_generate_state)

    abDatas = queue.Queue()
    threading.Thread(
        target=STT_Loop,
        args=(abDatas, input_data_mgr, check_generate_break),
        daemon=True,
    ).start()

    while True:
        try:
            abData: AudioBufferData | None = audioListener.auto_record()
            if abData is None:
                continue
        except Exception as e:
            print(f"音频录制异常:{e}")
            continue

        pipelineState.update_newest_generation(my_generate_state)
        abDatas.put(abData)

