
from typing import Any


from fastapi import FastAPI
import uvicorn
from funasr import AutoModel
from pydantic import BaseModel
from numpy.typing import NDArray
import numpy as np
from fastapi.responses import JSONResponse, Response

BACKEND_PORT = 5003

chunk_size = [16,16,8]
encoder_chunk_look_back = 4 #number of chunks to lookback for encoder self-attention
decoder_chunk_look_back = 1 #number of encoder chunks to lookback for decoder cross-attention

class Request(BaseModel):
    audio_buffer :list[float]
    is_done: bool = False


class FunasrAudioToText:
    def __init__(self):
        self.cache_data = {}
        self.cache_str = ""
        self.model = AutoModel(
            model="iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
        )

        #damo/punc_ct-transformer_cn-en-common-vocab471067-large
        #iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
        self.punc_model = AutoModel(model ="damo/punc_ct-transformer_cn-en-common-vocab471067-large")

    def clear_cache(self):
        print(f"[FunasrAudioToText] clear_cache")
        self.cache_data = {}
        self.cache_str = ""

    def stream_audio_to_text(self, data, is_done: bool):
        if not isinstance(data, np.ndarray):
            data = np.array(data, dtype=np.float32)

        print(f"data size:{data.size}")
        res = self.model.generate(
            input=data,
            cache=self.cache_data,
            is_final=is_done,
            chunk_size = chunk_size,
            encoder_chunk_look_back = encoder_chunk_look_back,
            decoder_chunk_look_back = decoder_chunk_look_back,
        )

        print(f"is_done:{is_done}")
        str = res[0]["text"]
        self.cache_str = self.cache_str + str
        if is_done:
            
            print(f"[FunasrAudioToText] cache_str:{self.cache_str}")
            punc_res: list[Any] | Any = self.punc_model.generate(input=self.cache_str)
            print(f"[FunasrAudioToText] punc_res:{punc_res}")
            str = punc_res[0]["text"]

            self.clear_cache()


        print(f"[FunasrAudioToText] res:{res}")
        return str, is_done


FunasrAudioToTexter = FunasrAudioToText()
app = FastAPI()

@app.post("/stt/fun")
async def stt(request: Request):
    txt,is_done = FunasrAudioToTexter.stream_audio_to_text(request.audio_buffer, request.is_done)
    return JSONResponse([txt,is_done])

@app.post("/stt/interage")
async def interage():
    FunasrAudioToTexter.clear_cache()


if __name__ == "__main__":
    print(f"[main] 启动 uvicorn: http://127.0.0.1:{BACKEND_PORT}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=BACKEND_PORT)
