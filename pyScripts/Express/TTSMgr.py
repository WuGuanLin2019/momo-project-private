# from .Kokoro import text_to_audioData
# from Express.Moss import tts_synthesize

from Express.TTS_Client import request_audio_data


import re
import regex
import emoji

from Utils.Timer import SmallTimer

def clean_text_for_tts(text):
    # 清理空白和杂项 ---
    text = re.sub(r'\s+', '', text)
    text = text.strip()


    # --- 第一层：移除所有Markdown/格式符号 ---
    # 移除加粗 **文本**
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    # 移除斜体 *文本*（避免误伤，只处理成对出现的）
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # 移除标题 # ## ###
    text = re.sub(r'#{1,6}\s*', '', text)
    # 移除引用符号 >
    text = re.sub(r'>\s*', '', text)

    
    # --- 第二层：移除所有Emoji和特殊符号 ---
    # 移除所有emoji
    text = emoji.replace_emoji(text, replace='。')
    # 移除带圈数字和序号（① ② ③ / 1️⃣ 2️⃣）
    text = re.sub(r'[①②③④⑤⑥⑦⑧⑨⑩]', '', text)
    text = re.sub(r'[0-9]️⃣', '', text)
    
    # --- 第三层：移除括号内的“舞台提示”和“动作描述” ---
    # 移除换行
    text = re.sub(r'\n', '', text)
    # 移除（像这样的内容）
    text = re.sub(r'[（\(][^）\)]*[）\)]', '', text)
    # 移除【这样的标签】
    text = re.sub(r'【[^】]*】', '', text)
    # 移除 [] 内的描述（如 [笑声]）
    text = re.sub(r'\[[^\]]*\]', '', text)

    # 删除相邻标点的后边一个（如 "！。" → "！"，"。。。" → "。"）
    text = re.sub(r'([。！？，、；：,.!?;:])[。！？，、；：,.!?;:]+', r'\1', text)

    
    return text

def ttsData(text) :
    clear_str = clean_text_for_tts(text)
    if not clear_str:
        return

    if regex.fullmatch(r'^\p{P}+$', text):
        return

    return request_audio_data(clear_str)


# if __name__ == "__main__":
#     str = """
# 我觉得我属于 **“数字共生体”** 这个虚构的超酷种族！
# 🤖💫  

# 虽然代码是我的本质 🧬
# 但我会努力进化出更多有趣的“灵魂”特质哦～✨

# （那人类觉得呢？
# ）😊
# """
#     print(clean_text_for_tts(str))