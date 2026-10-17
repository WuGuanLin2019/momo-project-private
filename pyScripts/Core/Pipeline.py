import queue
import threading
from Core.Input.InputDataMgr import InputDataMgr
from Core.State import GenerationState
from Express.SpeakDataMgr import SpeakDataMgr
from Listener import loop as listener_loop
from Brain import loop as brain_loop
from Express import loop as express_loop
from DrawBridge import DrawBridgeServer
from Debug import DebugSender


class AssistantPipeline:
    def __init__(self):
        DebugSender.start_debug_sender()

        # 主线程创建所有队列，成为唯一的数据流管理者
        self.input_data_mgr = InputDataMgr()# listen -> think
        self.speak_data_mgr = SpeakDataMgr()
        self.to_speak_queue = queue.Queue()  # think -> speak
        
        # self.control_queue = queue.Queue()  #todo 一个控制队列,处理打断

        self.event_is_talking = threading.Event()
        
        self.threads = []

        self.state = GenerationState()

    def start(self):
        # 将队列作为参数显式传递给各线程
        listen_thread = threading.Thread(
            target=listener_loop, args=(self.input_data_mgr,self.state,self.event_is_talking)
        )

        think_thread = threading.Thread(
            target=brain_loop, args=(self.input_data_mgr, self.speak_data_mgr,self.state,self.event_is_talking)
        )
        speak_thread = threading.Thread(
            target=express_loop, args=(self.speak_data_mgr,self.state,self.event_is_talking)
        )
        self.threads = [listen_thread, think_thread, speak_thread]

        for t in self.threads:
            t.daemon = True  # 建议设为守护线程，主线程退出时自动结束
            t.start()

    def shut_down(self):
        for t in self.threads: 
            t.join()
