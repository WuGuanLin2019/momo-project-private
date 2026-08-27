import queue
import threading
from Core.State import GenerationState
from Listener import loop as listener_loop
from Brain import loop as brain_loop
from Express import loop as express_loop

class AssistantPipeline:
    def __init__(self):
        # 主线程创建所有队列，成为唯一的数据流管理者
        self.input_text_queue = queue.Queue()  # listen -> think
        self.to_speak_queue = queue.Queue()  # think -> speak
        
        self.control_queue = queue.Queue()  # 一个控制队列,处理打断

        self.event_is_talking = threading.Event()
        
        self.threads = []

        self.state = GenerationState()

    def start(self):
        # 将队列作为参数显式传递给各线程
        listen_thread = threading.Thread(
            target=listener_loop, args=(self.input_text_queue,self.state,self.event_is_talking)
        )

        think_thread = threading.Thread(
            target=brain_loop, args=(self.input_text_queue, self.to_speak_queue,self.state)
        )
        speak_thread = threading.Thread(
            target=express_loop, args=(self.to_speak_queue,self.state,self.event_is_talking)
        )
        self.threads = [listen_thread, think_thread, speak_thread]

        for t in self.threads:
            t.daemon = True  # 建议设为守护线程，主线程退出时自动结束
            t.start()

    def shut_down(self):
        for t in self.threads: 
            t.join()
