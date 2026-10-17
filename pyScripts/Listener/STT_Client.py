import time
import requests
from Core.Input.InputDataMgr import InputData, InputDataMgr, InputSource
from Listener.ListenEvent import ListenEvent
from Listener.SileroVAD import AudioBufferData
from Utils.EventDispatch import eventDispatch


data_collect_when_interrupt = []
def _on_collect_interrupt_content(data):
    data_collect_when_interrupt.append(data)

eventDispatch.register(ListenEvent.collect_interrupt_content,_on_collect_interrupt_content)

STT_PORT = 5003
_tts_session = requests.Session()
def request_audio_text(audio_data: AudioBufferData) -> tuple[str | None, bool | None]:
    abData = audio_data.audio_buffer
    if abData.size == 0 and not audio_data.is_done:
        return None, None

    try:
        resp = _tts_session.post(
            f"http://127.0.0.1:{STT_PORT}/stt/fun",
            json={"audio_buffer": abData.tolist(), "is_done": audio_data.is_done},
            timeout=60,
        )
    except Exception as e:
        print(f"[stt_client] 语音识别失败: {e}")
        return None, None

    if resp.status_code != 200:
        print(f"[stt_client] 服务端错误: {resp.text[:200]}")
        return None, None

    try:
        data = resp.json()
        txt, is_done = data[0], data[1]
        return txt, is_done
    except Exception as e:
        print(f"[stt_client] 语音识别失败: {e}")
        print(f"[stt_client] 前200字节: {resp.content}")
        return None, None


def interrupt_audio_text():
    resp = _tts_session.post(f"http://127.0.0.1:{STT_PORT}/stt/interage", timeout=10)
    print(
        f"[stt_client] 语音识别中断 status={resp.status_code}, content-type={resp.headers.get('content-type')}, len={len(resp.content)}"
    )

def handle_interrupt_data(audio_str:str | None):
    if len(data_collect_when_interrupt) > 0:
        collect_data = "\n".join(data_collect_when_interrupt)
        data_collect_when_interrupt.clear()
        if audio_str:
            audio_str = f"<被打断对话前的补充内容>{collect_data}</被打断对话前的补充内容>\n{audio_str}"
    
    return audio_str

def STT_Loop(abDatas, input_data_mgr: InputDataMgr, check_generate_break):
    # current_input_txt = ""
    while True:
        if check_generate_break():
            input_data_mgr.clear_data()
            interrupt_audio_text()
            time.sleep(0)
            continue

        abData = abDatas.get()
        audio_str, is_done = request_audio_text(abData)

        # if audio_str and not is_done:
        #     current_input_txt = current_input_txt + audio_str

        if not is_done:
            continue

        # if is_done:
        #     current_input_txt = ""

        print(f"语音流式识别结果：{audio_str}")

        input_str = handle_interrupt_data(audio_str)            
        tem_data = InputData(InputSource.Microphone, input_str or "")
        input_data_mgr.add_data(tem_data)
