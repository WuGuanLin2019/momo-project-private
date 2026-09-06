import websocket
import json
import uuid
import time
import numpy as np
import threading

from Utils.Timer import SmallTimer

# ----------------------------
# 配置部分
# ----------------------------
VTUBE_WS_URL = "ws://127.0.0.1:8001"
PLUGIN_NAME = "Momo"
PLUGIN_DEVELOPER = "W_____u"
FRAME_RATE = 60  # 每秒更新嘴型次数


class VTubeClient:
    def __init__(self):
        self.ws = None
        self.token = None
        self.connected = False

    def start(self):
        self._connect()

        threading.Thread(target=self.reconnect_loop, daemon=True).start()

    def _connect(self):
        self.ws = websocket.WebSocketApp(
            VTUBE_WS_URL,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def send_request(self, messageType, data):
        """发送到 VTube Studio"""
        request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": str(uuid.uuid4()),
            "messageType": messageType,
            "data": data,
        }
        self.ws.send(json.dumps(request))

    def request_token(self):
        self.send_request(
            "AuthenticationTokenRequest",
            {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEVELOPER,
            },
        )

    def request_authentication(self, token):
        # 发送认证请求
        self.send_request(
            "AuthenticationRequest",
            {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEVELOPER,
                "authenticationToken": token,
            },
        )

    def send_mouth_param(self, current_volume):
        """发送嘴型参数到 VTube Studio"""
        self.send_request(
            "InjectParameterDataRequest",
            {
                "faceFound": False,
                "mode": "add",
                "parameterValues": [{"id": "MouthOpen", "value": current_volume}],
            },
        )

    def on_open(self, ws):
        print("✅ WebSocket 已连接，请求🔑 Token")
        self.request_token()

    def on_message(self, ws, message):
        data = json.loads(message)
        msg_type = data.get("messageType")
        # print("\n收到消息:")
        # print(json.dumps(data, indent=4, ensure_ascii=False))

        if msg_type == "AuthenticationTokenResponse":
            self.token = data["data"]["authenticationToken"]
            print("🔑 拿到 Token:", self.token)
            self.request_authentication(self.token)

        elif msg_type == "AuthenticationResponse":
            if data["data"].get("authenticated", False):
                print("✅ VTube认证成功")
                self.connected = True
            else:
                print("❌ 认证失败")

    def on_error(self, error):
        self.connected = False
        print("❌ WebSocket 错误:", error)

    def on_close(self, code, msg):
        self.connected = False
        print("🔒 WebSocket 已关闭", code, msg)

    # ----------------------------
    # 口型驱动
    # ----------------------------
    def cal_volumes(self, audio_data, sample_rate):
        if audio_data is None:
            return

        # print("👄 计算口型数据...")
        # 确保是 float32 且归一化到 [-1, 1]
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data /= max_val

        frame_size = int(sample_rate / FRAME_RATE)
        if frame_size == 0:
            return False

        volumes = []
        for i in range(0, len(audio_data), frame_size):
            frame = audio_data[i : i + frame_size]
            # 平均绝对值音量
            vol = float(np.mean(np.abs(frame)))
            volumes.append(vol)

        return volumes


    def drive_mouth(self, audio_data, sample_rate, startCB, check_generate_break):
        if not self.connected:  
            return

        volumes = []
        # with SmallTimer("cal_volumes"):
        volumes = self.cal_volumes(audio_data, sample_rate)
        if volumes is None:
            return 

        playObject = startCB(audio_data,sample_rate)
        
        start_time = time.perf_counter()
        total_frames = len(volumes)
        last_frame_idx = -1
        while True:
            if check_generate_break():
                if playObject and playObject.is_playing():
                    playObject.stop()
                self.send_mouth_param(0)
                return

            elapsed = time.perf_counter() - start_time
            frame_idx = int(elapsed * FRAME_RATE)

            if frame_idx >= total_frames:
                break

            if frame_idx != last_frame_idx:
                self.send_mouth_param(min(max(volumes[frame_idx] * 1.5, 0), 1))
                last_frame_idx = frame_idx

            time.sleep(1 / FRAME_RATE)


        # print("✅ 嘴型结束")
        self.send_mouth_param(0)
        return True

    def reconnect_loop(self):
        while True:
            time.sleep(3)
            if self.connected:
                return

            if not self.ws:
                self._connect()
                return

            print("尝试连接VTube Studio...")
            try:
                self.request_token()
            except Exception as e:
                print(e)
