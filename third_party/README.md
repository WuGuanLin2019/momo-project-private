# third_party 依赖说明

本目录存放项目运行所需的第三方依赖，**大部分不纳入 git 仓库**（体积大、上游可追溯、LICENSE 各异）。
克隆/恢复环境时请从各上游仓库获取，建议记录所使用的 commit 以保证可复现。

其中 **Submit/ 与 Debug/ 为自研插件，纳入 git 跟踪**（规则见根目录 `.gitignore`）。

| 目录 | 用途 | 上游项目 |
|---|---|---|
| `Funasr/` | 流式语音识别（ASR） | https://github.com/modelscope/FunASR |
| `Funasr/Funasr_server.py` | **自研**：FunASR 流式识别 HTTP 服务封装（此文件受 git 跟踪） | — |
| `MeloTTS-main/` | TTS 语音合成（中英混合、速度快） | https://github.com/myshell-ai/MeloTTS |
| `CosyVoice-main/` | TTS 语音合成（有语气、中英混合、速度较慢） | https://github.com/FunAudioLLM/CosyVoice |
| `kokoro-main/` | TTS 语音合成（速度快、单一语种） | https://github.com/hexgrad/kokoro |
| `MOSS-TTS-Nano-main/` | TTS 语音合成（实验性） | https://github.com/OpenMOSS/MOSS-TTS |
| `mem0/` | 记忆系统框架（实验性，项目自研记忆见 pyScripts/Memory） | https://github.com/mem0ai/mem0 |
| `blivedm-dev/` | B 站直播弹幕接入 | https://github.com/xfgryujk/blivedm |
| `ffmpeg-8.1.2-full_build-shared/` | FFmpeg 运行时（音频处理） | https://ffmpeg.org/ |
| `PDF/` | PDF.js 相关资源 | https://github.com/mozilla/pdf.js |
| `Debug/` | **自研**：LLM 上下文调试查看器（debugViewer.html / debugViewer.js） | 纳入 git 跟踪；`context/` 为运行时快照，不入库 |
| `Submit/` | **自研**：OBS/直播字幕插件（WebSocket 接收 + 时间轴逐字渲染，抗浏览器后台节流） | 纳入 git 跟踪 |

## 环境隔离

各模块使用 conda 进行环境隔离（Python 版本与依赖冲突，如 FunASR 与 MeloTTS），
详见根目录 README.md 的说明。
