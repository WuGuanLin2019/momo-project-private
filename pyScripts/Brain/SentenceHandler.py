from typing import Any

TEXT_CUT = ["！","、", "。", "？", "，", "!", "：", "~", ",", ":"]


class SentenceHandler:
    def __init__(self) -> None:
        self.content = ""

        self.thinking = ""
        self.done_thinking = False

        self.current_sentence = ""
        self.last_cut_str_tail = None

        self.tool_calls = []

    def judge_cut_text(self, s):
        for punct in TEXT_CUT:
            if punct in s:
                parts = s.split(punct)
                tail_str = None
                if len(parts) > 1:
                    tail_str = parts[-1]

                    pos = tail_str.find("”")
                    if pos > -1:
                        tail_str = tail_str[pos + 1 :]
                return True, tail_str

        return False, None

    def handleStreamingText(self, chunk: dict[str, Any]):
        message: dict[str, Any] = chunk.get("message", "")
        content = message.get("content", "")
        isDone = chunk.get("done", False)
        thinking = message.get("thinking", "")

        if thinking:
            self.thinking += thinking
            print(thinking, end="", flush=True)

        if content:
            if self.thinking and not self.done_thinking:
                # print(":\n回答:\n")
                self.done_thinking = True
                self.thinking = ""

            text = content
            if self.last_cut_str_tail:
                text = self.last_cut_str_tail + text
                self.last_cut_str_tail = None

            is_cut, self.last_cut_str_tail = self.judge_cut_text(text)
            if is_cut and self.last_cut_str_tail:
                text = text[: -len(self.last_cut_str_tail)]

            self.current_sentence += str(text)

            if (is_cut and len(self.current_sentence)>=10 ) or isDone:
                output = self.current_sentence
                self.content += self.current_sentence
                self.current_sentence = ""
                # print(output)
                return output

        if message.get("tool_calls"):
            self.tool_calls.extend(message["tool_calls"])
            print(f"想去调用Tool:{message['tool_calls']}")

        # 流结束时，若还有剩余句子，强制输出
        if isDone and self.current_sentence:
            output = self.current_sentence
            self.content += self.current_sentence
            self.current_sentence = ""
            return output

        return None
