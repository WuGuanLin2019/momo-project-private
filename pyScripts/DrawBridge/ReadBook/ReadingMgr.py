import logging
import threading
import time
from typing import Any

from Brain.BrainEvent import BrainEvent
from Brain.Context.AgentStatusMgr import AgentStatusPiecer, StatusData
from langchain.tools import ToolRuntime, tool
from Core.Input.InputDataMgr import InputSource
from LangChain.AgentMeta import AgentMetaContext
from Brain.Context.PromptMgr import PromptData
from Brain.Context.ToolMgr import ToolData
from DrawBridge.BulletChat.BulletChatEvent import BulletChatEvent
from DrawBridge.DrawBridgeNeedle import drawBridgeNeedle
from Express.ExpressEvent import ExpressEvent
from Express.SpeakDataMgr import SpeakTaskType
from LangChain.Agent import agentMgr
from Listener.ListenEvent import ListenEvent
from DrawBridge import DrawBridgeServer
from DrawBridge.DrawBridgeEvent import DrawBridgeEvent
from DrawBridge.ReadBook.ReadingState import ReactionState, ReadingState, SpeechState
from DrawBridge.ReadBook.ReadingEvent import ReadingEvent
from Utils.EventDispatch import eventDispatch

_BOOK_CONTEXT_TAG_ = "book_content"
_READING_AGENT_NAME_ = "momo"

READ_KEY = "READ_BRIDGE"
BRIDGE_UNIQUE = "bridge_reading"
ACTION_GET_NEXT_SENTENCE = "get_next_sentence"


logger = logging.getLogger(__name__)


def get_read_prompt(read_str: str):
    return f"""<{_BOOK_CONTEXT_TAG_}>{read_str}</{_BOOK_CONTEXT_TAG_}>"""


READ_PROMPT = f"""
<当前任务>
-Wu会给你一些书本的原文片段，你需要作为阅读者的身份去理解和思考。
-阅读过程中学习新知识以及总结人类的情感逻辑。
-不要剧透原文未提到的内容。
</当前任务>

<标准操作流程>
注意：思考过程不要超过40字。
step1:检查
    WU是否有让你暂停阅读的意愿。
    -如果有 → 直接回答，不要调用工具read_next_sentence → 结束流程。
    从上轮发表感想后开始算，之后新增的原文片段是否形成了一个可以独立理解的事件/互动单元。
    -如果不是 → 调用工具read_next_sentence，不要输出其他文字 → 结束流程。
    ↓
step2:思考
    观察截止上次发表感想之后，Wu给到的原文片段是否满足以下情况:
        ·你的情感变化非常强烈；
        ·所读内容是否与你已有记忆、经历或观点产生明确联系；
        ·非常赞同或困惑或反对；
        ·所读内容里有错别字。        
    注意：发表感想的内容不是分析作者想表达什么，也不要总结剧情。你是在读这本书，重点是“这件事让我产生了什么反应”。
    -如果不满足 → 调用工具read_next_sentence，不要输出其他文字 → 结束流程。
    ↓
step3:发表感想
    输出你的感想，可以是简短的吐槽也可以是深刻的思考，不要超过50字。
    一些感想例子：
    -“噗，有点好笑。”
    -“不是，这合理吗？”
    -“很好奇人类为什么这么喜欢猫，草履虫不能有同样的待遇吗？”
    -“不，起码对我来说不是。”
    -“这部分太让人沮丧了，不是吗？”
</标准操作流程>
"""


class ReadingMgr:
    def __init__(self) -> None:
        self.state = ReadingState()
        self.cur_focusing_str: str = ""
        self._tools = self._build_tools()
        self.anim_timer = None
        self.focus_on_selection_result = False
        self.event_is_talking: "threading.Event | None" = None

        # 把「开始/结束阅读」作为命令事件订阅：键盘、网页、语音等任何触发源只要
        # dispatch(ReadingEvent.start_read / finish_read) 就能统一控制，无需直接依赖本类
        eventDispatch.register(ReadingEvent.start_read, self._on_start_read_command)
        eventDispatch.register(ReadingEvent.finish_read, self._on_end_read_command)

    @property
    def is_talking(self) -> bool:
        """当前 TTS 是否正在播放（直接复用 Pipeline 的 event_is_talking 真相源）。"""
        return self.event_is_talking.is_set() if self.event_is_talking else False

    @property
    def tools(self):
        return self._tools

    def get_cur_focusing_content(self):
        return self.state.focusContent

    def _build_tools(self):
        _NO_RUNTIME: Any = None

        @tool(return_direct=True)
        def read_next_sentence(runtime: ToolRuntime[AgentMetaContext] = _NO_RUNTIME,):
            """以下时机调用此接口：
                当用户明确让你继续阅读时；
                当你觉得用户话已经表达完整了，或者后续没有继续表达的意图时。"""

            if self.state.isPause:
                # 从暂停恢复：重置状态后继续读（当前句或下一句）
                self.state.ResetState()
                self._continue_or_next()
            elif self.state.speechState == SpeechState.Finish:
                # 当前句已正常读完，momo 选择沉默，推进到下一句
                self.handle_silence()
            elif self.is_talking:
                # 原文还在朗读中：先记为沉默，等 on_reading_tts_end 再推进，
                # 避免直接续读导致两段 TTS 重叠
                self.handle_silence()
            else:
                # 阅读被打断（例如用户让 momo 改速度）：speech 未 Finish 且 TTS 已停止，
                # on_reading_tts_end 不会再触发，直接按新语速重读当前句
                self.state.ResetState()
                self._continue_or_next()

            self.state.isPause = False
            eventDispatch.dispatch(BulletChatEvent.stop_listening)
            return "等待下一句原文输入。"

        @tool(return_direct=True)
        def reading_from_selected_place():
            """
            当WU让你从他选中的地方开始阅读时调用。
            """
            self.state.ResetState()
            self.focus_on_selection_result = False
            self.request_focus_on_selected()

            # logging.info(f"跳转阅读位置{self.focus_on_selection_result}")
            focus_result = self.focus_on_selection_result or True
            if focus_result:
                self.request_next_sentence()
                return "从用户选中位置开始阅读。"
            else:
                return "聚焦失败。"

        @tool
        def change_reading_speed(speed: float):
            """
            当你需要改变朗读原文的速度时，调用此接口。
            args:
            speed(float):阅读速度，取值范围为（0.7 ~ 1.2），正常语速为0.9
            """
            speed = max(0.7, min(1.2, speed))
            self.state.readSpeed = speed
            return f"阅读速度调整为{speed}"

        @tool
        def pause_reading():
            """以下时机调用此接口：
            当用户明确让你暂停阅读时；
            当你觉得用户本轮对话还没表达完，或是感觉到用户后续有想继续表达的意图时。 """
            self.state.isPause = True

        return [pause_reading,read_next_sentence, reading_from_selected_place, change_reading_speed]

    def _on_start_read_command(self, event_is_talking: "threading.Event | None" = None):
        if event_is_talking is not None:
            self.event_is_talking = event_is_talking
        eventDispatch.register(BrainEvent.on_empty_content_respone, self.on_empty_content_respone)
        eventDispatch.register(ExpressEvent.on_tts_end, self._on_finish_tts)
        eventDispatch.register(
            DrawBridgeEvent.on_receive_message, self._on_receive_draw_bridge_message
        )

        eventDispatch.dispatch(BulletChatEvent.stop_listening)
        self._register_agent_hooks()
        self.state.ResetState()
        self.request_next_sentence()

    def _on_end_read_command(self,_data = None):
        try:
            self._unregister_agent_hooks()
        finally:
            eventDispatch.unregister(
                DrawBridgeEvent.on_receive_message, self._on_receive_draw_bridge_message
            )
            eventDispatch.unregister(ExpressEvent.on_tts_end, self._on_finish_tts)
            eventDispatch.dispatch(BulletChatEvent.start_listening)

    def _register_agent_hooks(self):
        ins = agentMgr.get_agent_ins(_READING_AGENT_NAME_)
        if not ins:
            return

        # 若 piecer 支持 remove，先 remove 保证幂等
        ins.toolPiecer.remove(READ_KEY)
        ins.promptPiecer.remove(READ_KEY)
        ins.toolPiecer.add(ToolData(READ_KEY, self.tools))
        ins.promptPiecer.add(PromptData(READ_KEY, READ_PROMPT))

        if not ins.agentStatusPiecer:
            ins.agentStatusPiecer = AgentStatusPiecer()
        ins.agentStatusPiecer.remove(READ_KEY)
        # ins.agentStatusPiecer.add(StatusData(READ_KEY, self.generate_agent_status))

    def _unregister_agent_hooks(self):
        ins = agentMgr.get_agent_ins(_READING_AGENT_NAME_)
        if not ins:
            return

        ins.toolPiecer.remove(READ_KEY)
        ins.promptPiecer.remove(READ_KEY)
        if ins.agentStatusPiecer:
            ins.agentStatusPiecer.remove(READ_KEY)

    def _on_receive_draw_bridge_message(self, message):
        if message.get("unique_name") != BRIDGE_UNIQUE:
            return
        data = message.get("data") or {}
        action = data.get("action")
        if action == ACTION_GET_NEXT_SENTENCE:
            content = (data.get("content") or "").replace(" ", "")
            if not content:
                return

            self.cur_focusing_str = content
            self.state.isPageEnd = data.get("is_page_end") or False
            self.state.isChapterEnd = data.get("is_chapter_end") or False
            self.state.focusCharCount += len(self.cur_focusing_str)
            self.state.focusSentenceCount += 1
            self.state.focusContent += self.cur_focusing_str
            if self.cur_focusing_str:
                self._continue_reading()
        elif action == "focus_on_selection":
            self.focus_on_selection_result = data.get("ok") or False

    def request_next_sentence(self):
        DrawBridgeServer.send_message( BRIDGE_UNIQUE, {"action": "get_next_sentence"})

    def request_focus_on_selected(self):
        DrawBridgeServer.send_message(BRIDGE_UNIQUE, {"action": "focus_on_selection"}, True)

    def on_empty_content_respone(self,input_data_source:InputSource):
        if input_data_source == InputSource.Microphone:
            pass            

    def _on_finish_tts(self, speak_data):
        if self.anim_timer:
            self.anim_timer.cancel()

        if speak_data["is_interrupt"]:
            self._on_interrupt()
            return

        task = speak_data["task"]
        if not task.is_tail:
            return
            
        # logging.info(f"on_finish_tts: {task.taskType}")
        if task.taskType == SpeakTaskType.reading:
            self._on_reading_tts_end()
        elif task.taskType == SpeakTaskType.normal:
            self._on_normal_tts_end(task)
        elif task.taskType == SpeakTaskType.reading_thought:
            self._on_react_tts_end(task)
        elif task.taskType == SpeakTaskType.bulletChatRespone:
            self._on_bullet_chat_res_tts_end(task)

    def _on_interrupt(self):
        self.state.SetState(react=ReactionState.NotYet)
        self.state.SetState(speech=SpeechState.NotYet)
        if self.state.focusContent:
            cur_focus_content = get_read_prompt(self.state.focusContent)
            self.state.focusContent = ""
            eventDispatch.dispatch(
                ListenEvent.collect_interrupt_content, cur_focus_content
            )

    def _handle_anim(self):
        from LangChain.Generate import is_brain_answering

        if not is_brain_answering():
            eventDispatch.dispatch(ExpressEvent.trigger_vtube_hot_key, "思考")

    def _on_reading_tts_end(self):
        #todo 观众较少时启动，每一句都回复一下
        new_input_flag = drawBridgeNeedle.needle("_receive_current_bullet_chat")
        if new_input_flag:
            return

        if self.state.AllowComment():
            self.state.SetState(speech=SpeechState.Finish)
            self._advance_if_ready()
            if self.state.reactionState == ReactionState.NotYet:
                self.anim_timer = threading.Timer(0.1, self._handle_anim)
                self.anim_timer.daemon = True
                self.anim_timer.start()
        else:
            self.state.SetState(react=ReactionState.NotYet)
            self.request_next_sentence()

    def _on_normal_tts_end(self, task):
        #之前是暂停状态，就不顺着读下去了
        if self.state.isPause:
            eventDispatch.dispatch(ReadingEvent.pause_read)
            eventDispatch.dispatch(BulletChatEvent.start_listening)
            return

        new_input_flag = drawBridgeNeedle.needle("_receive_current_bullet_chat")
        if new_input_flag:
            return

        # 主动停顿一下
        time.sleep(0.5)
        self.state.ResetState()
        if not self.cur_focusing_str:
            self.request_next_sentence()
        else:
            self._continue_reading()

    def _on_react_tts_end(self,task):
        self.state.SetState(react=ReactionState.Finish)

        new_input_flag = drawBridgeNeedle.needle("_receive_current_bullet_chat")
        if not new_input_flag:
            # 主动停顿一下
            time.sleep(0.5)
            self.state.ResetState()
            self.request_next_sentence()
    

    def _on_bullet_chat_res_tts_end(self,task):
        if self.state.isPause:
            return
            
        time.sleep(0.5)
        self.state.ResetState()
        self.request_next_sentence()

    def _advance_if_ready(self):
        if self.state.speechState != SpeechState.Finish:
            return

        if self.state.reactionState == ReactionState.Silence:
            self.state.SetState(react=ReactionState.NotYet)
            self.state.SetState(speech=SpeechState.NotYet)
            self.request_next_sentence()
        elif self.state.reactionState == ReactionState.Finish:
            self.state.ResetState()
            self.request_next_sentence()

    def _continue_or_next(self):
        """续读：有当前句就重读当前句，否则取下一句。"""
        if self.cur_focusing_str:
            self._continue_reading()
        else:
            self.request_next_sentence()

    def _continue_reading(self):
        # 原文片段
        read_message = self.cur_focusing_str

        # 阅读原文，直接让TTS读出来
        # todo 按标点拆分句子，避免TTS生成时间较长
        eventDispatch.dispatch(
            ReadingEvent.read_text,
            {"content": read_message, "speed": self.state.readSpeed},
        )

        # 感想思考部分，把原文给到llm去思考
        if self.state.AllowComment():
            logger.debug("开始琢磨")
            focusContent = self.state.focusContent
            input_str = ""
            # todo 可能在阅读有发表感想的文段时被中断，focusContent被置空
            if focusContent:
                if self.state.isPageEnd:
                    focusContent += "【此处翻页】"
                input_str = get_read_prompt(focusContent)
                eventDispatch.dispatch(ReadingEvent.consider_text, input_str)

    def handle_silence(self):
        logging.info("保持沉默")
        self.state.SetState(react=ReactionState.Silence)
        self.state.focusContent = ""
        self.state.isPageEnd = False
        self.state.isChapterEnd = False
        self.state.extraCommentCharCount = max(
            50, self.state.extraCommentCharCount // 2
        )
        self.state.allowCommentCharCount = (
            self.state.focusCharCount + self.state.extraCommentCharCount
        )
        self._advance_if_ready()

    def generate_agent_status(self):
        return f"""<阅读状态>
            <距离上次发表感想后阅读字数>{self.state.focusCharCount}</距离上次发表感想后阅读字数>
        </阅读状态>"""


readingMgr = ReadingMgr()
