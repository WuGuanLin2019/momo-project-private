
from queue import Empty
import threading
from Brain.BrainEvent import BrainEvent
from Core.Input.InputDataMgr import InputDataMgr, InputSource
from Express.SpeakDataMgr import SpeakDataMgr, SpeakTask, SpeakTaskType
from LangChain.Generate import think
from Core.State import GenerationState
from Utils.EventDispatch import eventDispatch


def brain_loop(input_data_mgr:InputDataMgr, speak_data_mgr:SpeakDataMgr, pipelineState: GenerationState,event_is_talking:threading.Event):

    generate_state = GenerationState()

    respone_type_map = {
        InputSource.BulletChat:SpeakTaskType.bulletChatRespone,
        InputSource.ReadBook:SpeakTaskType.reading_thought,
    }

    def add_to_speak_queue(str:str, is_end:bool = False, is_head:bool = False, input_source:InputSource = InputSource.Normal ):
        if str.strip() != "":
            speak_source = respone_type_map.get(input_source, SpeakTaskType.normal)
            task = SpeakTask(generate_state.generation,str, is_tail = is_end, is_head = is_head, taskType = speak_source)
            speak_data_mgr.add_data(task)
            return task

    while True:
        try:
            #阻塞
            inputData = input_data_mgr.get_data()
        except Empty:
            print("inputData 是空")
            continue

        pipelineState.update_newest_generation(generate_state)
        think(inputData,input_data_mgr, add_to_speak_queue, generate_state, pipelineState,event_is_talking)
        eventDispatch.dispatch(BrainEvent.after_content_respone)


