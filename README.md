# momo-project

尝试做个AI主播，MOMO是猫咪的名字。

一些要点记录：

主流程使用项目外层独立 venv（`E:/PythonVenv/venv`），ASR/TTS/弹幕等第三方服务各自用 conda 环境隔离，避免依赖冲突。

## 目录结构（pyScripts）

- `Core/`：主流程编排（`Pipeline.py` 三线程）与代际状态（`State.py` 的 GID）
- `Listener/`：`SileroVAD.py` 语音活动检测、`STT_Client.py` 语音识别客户端
- `Brain/`：上下文拼装（Prompt / Tool / Status）、情绪等状态
- `LangChain/`：`LLM.py` 模型注册、`Agent.py` Agent 与中间件、`MCPClient.py` MCP 接入、`Chain.py` 轻量链
- `Memory/`：`MemoryDB.py`（SQLite）、`Embedding.py`（FAISS）、`Mem0Mgr.py`（mem0 客户端）
- `Express/`：`TTS_Client.py` 语音合成客户端
- `Body/VTube/`：VTube Studio 协议控制
- `DrawBridge/`：`ReadBook/` 读书、`BulletChat/` 直播弹幕、`WebSearch/` 联网检索
- `third_party/`：FunASR、MeloTTS、blivedm、mem0、PDF 阅读、字幕插件等外部服务

## 核心逻辑

三个主线程：

- 侦听：语音唤醒、识别
- 思考：大模型输入输出、MCP 工具调用
- 表达：TTS、虚拟形象控制

拆分线程的原因：为了支持说话可中断当前表达；模型一边思考，TTS 一边播放语音。

公用变量：输入文字队列、输出文字队列。主流程入口为 `pyScripts/main.py`，启动后由 `Core/Pipeline.py` 拉起三个线程。

## AI 大模型与 Agent

早期方案：ollama 千问 7B，靠约定函数名让模型输出 toolCall。7B 模型参数一多（大于 6 个）就容易格式出错，函数名相近也会混用（比如 remind_memory 和 note_memory），最终只保留少数几个参数极简的函数（查/改/删记忆、当前时间、网络搜索）。网络搜索返回结果过长时会挤占上下文，模型会忘记一开始的提问。

现在的实现已经换成 LangChain + LangGraph：

- `create_agent` 构建 Agent，`InMemorySaver` 做会话检查点
- 主 agent `momo`：对外对话，`deepseek-flash` 流式输出，开启 thinking，低延迟优先
- 内部 agent `momo_internal`：同一模型，关闭 thinking，超时更宽松，负责内部任务
- 摘要模型：对话超过 3 万 token 时归档到 5 千 token，避免上下文无限增长
- 备用模型：Ollama 的 `gemma3:1b`，主模型不可用时兜底（`LangChain/LLM.py`）
- 中间件：系统提示替换、状态注入、动态工具注入（`wrap_model_call` 提供工具清单，`wrap_tool_call` 负责执行时解析），两者缺一不可

## 工具与 MCP

工具不再直接写死在 Agent 里，而是通过 `LangChain/MCPClient.py` 用 `MultiServerMCPClient` 接入 MCP server（当前是 engram，stdio 方式）：

- MCP 会话跑在专用 `mcp-loop` 线程，和主流程的同步管线隔离
- 异步 MCP 工具包装成同步 `StructuredTool`，调用时提交回 mcp 线程执行
- 工具按角色分配：主 agent `momo` 只开放 `recall` / `why`；`momo_internal` 开放全部；`boot_context` 仅宿主启动时调用，不进任何 Agent 的工具池
- 启动时用 engram 的 `boot_context` 预热记忆，注入到系统提示

## 记忆系统

目前三套记忆并存，用途不同：

1. engram（MCP 接入，主力）：事实、实体、矛盾记录；抽取与摘要提示词统一中文，自我统一为「我」、创造者统一为「wu」；启动预热分三段——自我相关、最近一周、行为准则
2. mem0（自托管 REST 服务，`Mem0Mgr.py`）：通用记忆读写
3. 本地 SQLite + FAISS（`MemoryDB.py` / `Embedding.py`）：SQLite 存完整记忆（uid、时间、内容、摘要），FAISS 存向量索引，embedding 用 ollama 的 `nomic-embed-text`

本地 FAISS 方案的原理：向量库存 `<记忆总结片段, 记忆UID>`，SQL 存 `<记忆UID, 完整记忆>`。检索时比较向量相似度取前 x 条，再按 UID 取回完整内容。

写入记忆的演进：

- 方案一：模型直接传时间、场景、人物、事物、核心事件，参数过多，格式容易错
- 方案二：要求模型输出 JSON，仍经常解析失败
- 方案三：只传两个参数（完整记忆字符串、记忆总结字符串），时间由系统获取；注意不能用完整记忆片段直接做向量索引

修改/删除记忆的难点是让模型正确索引到特定片段。uid 由时间构成（如 20260501132211），但大数字容易被幻觉；把检索结果临时编号（m1、m2……）后明显改善。

## 语音识别

Silero VAD：判断是否在说话，动圈麦能按距离衰减响度，从而隔绝回声和噪音。ringBuffer 缓存开头语音，避免句子开头被忽略；静音块判断说话结束。

FunASR 流式识别：按单位时间送入音频，模型支持回溯修正。当前以本地 HTTP 服务方式运行（`127.0.0.1:5253`），由 `start_all.bat` 拉起。

过往方案：

- Whisper：速度不如 FasterWhisper
- FasterWhisper：模型被污染，输入音频过少或为空时会出现「明镜与点点」
- 以上均不支持流式，音频越长识别越慢

## 文字转语音

当前走本地 HTTP 服务（`127.0.0.1:5254`，由 `start_all.bat` 拉起），客户端在 `Express/TTS_Client.py`，音频用 soundfile 解码后播放。

方案对比：

- MeloTTS：快，中英文混合发音，但音色和语气不可调
- Kokoro：速度快，单一语种
- CosyVoice：有语气、中英混合，但速度较慢
- MOSS-TTS：作为备选保留在 `third_party/`

## 虚拟形象

通过 VTube Studio 的 WebSocket API（`ws://127.0.0.1:8001`）接入：完成 Token 认证后，按音频响度计算嘴巴开合，发送 `InjectParameterDataRequest` 修改 `MouthOpen`；需要时用 `HotkeyTriggerRequest` 触发动画。

## 中断机制

以 generation ID（GID）进行管理，每个线程维护自己的 GID。上游传递参数时会把最新 GID 一并带到下游；当线程发现自己的 GID 与传入值不同时，LLM 流式输出、音频播放、VTube 参数传输都会中断，LLM 重新接收新输入思考。

每次检测到开始说话时，GID 加一（`Core/State.py`）。

## 运行

- `start_all.bat`：并行启动 MeloTTS、FunASR 和主流程
- `start.bat`：只启动主流程（`pyScripts/main.py`）
- `start_server.bat`：启动 PDF 阅读、直播弹幕、字幕等辅助服务

启动前需要：

- 环境变量 `DEEPSEEK_API_KEY`（主模型）与 `HF_TOKEN`（模型下载）
- VTube Studio 已开启 API 并完成插件授权
- engram MCP server 与记忆库路径在 `LangChain/MCPClient.py` 中配置

运行中可用快捷键：空格开始读书、`q` 结束读书、`m` 切换麦克风、`b` 切换弹幕监听（`pyScripts/main.py`）。
