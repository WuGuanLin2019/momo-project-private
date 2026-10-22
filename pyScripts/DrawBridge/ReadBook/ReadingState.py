from dataclasses import dataclass
from enum import Enum
import traceback

class ReactionState(Enum):
    NotYet = 0
    Silence = 1
    Finish = 2

class SpeechState(Enum):
    NotYet = 0
    Finish = 2

class ReadingState:
    def __init__(self) -> None:
        self.readSpeed = 0.95
        self.ResetState()

    def SetState(self, react:ReactionState|None=None, speech:SpeechState|None=None):
        if react:
            self.reactionState = react
        if speech:
            self.speechState = speech

    def ResetState(self):
        self.reactionState = ReactionState.NotYet
        self.speechState = SpeechState.NotYet
        self.focusCharCount = 0
        self.focusSentenceCount = 0
        self.focusContent = ""
        self.allowCommentCharCount = 50
        self.extraCommentCharCount = self.allowCommentCharCount
        self.isPageEnd = False
        self.isChapterEnd = False
        self.isPause = False


    def IsFinish(self) -> bool:
        if self.speechState == SpeechState.Finish and (
            self.reactionState == ReactionState.Finish
            or self.reactionState == ReactionState.Silence
        ):
            return True
        return False

    def AllowComment(self) -> bool:
        #尝试识别章节末尾
        if self.isChapterEnd:
            return True

        # print(f"focusCharCount: {self.focusCharCount}, allowCommentCharCount: {self.allowCommentCharCount}")
        if self.focusCharCount > self.allowCommentCharCount:
            return True

        return False

@dataclass
class ReadingMark():
    cur_page:int
    start_char:int
    end_char:int