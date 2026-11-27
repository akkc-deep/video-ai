# TTS-VOX-03 本地 API 服务

## Goal

在现有独立 VoxCPM2 环境提供仅 loopback 的异步 TTS API，持久化提交/查询、幂等、明确失败及取消；阶段内单模型串行生成。02 已获用户明确放行，实测限制保留。

## Scope

实现服务、受控输出、任务恢复、启动/停止入口及真实 GPU API 样本。04 才连接生产适配器，06 才扩展音色资产，07 才接生产编排恢复。沿用 VIDEO_AI_RUNTIME_ROOT、VideoStorage、safe_path、storage_lock、write_record、stop_process；不改旧 ServiceManager 的三服务契约，不增加 GPU 采样或租约。

## Approach

采用 Python 标准库 ThreadingHTTPServer + SQLite（不额外安装 FastAPI），一个推理线程加载一次模型，无推理子进程；直接终止本服务进程不会遗留 CUDA 子进程。调用方传入既有 work 修订音频目录内的 state-dir，独立验收可用 scratch/benchmarks。启动持有 state-dir 的 OS 文件锁，同目录禁止双服务。每次启动读取既有生产 voice.json，校验一次小参考文件身份并复制到 state-dir；固定 voice_id 为 existing-reference，GET /voices 返回它。暂不实现设计型音色管理。

接口：GET /health（503=loading/failed/stopping，200=ready，含 session_id、模型版本）；GET /voices；POST /tts/generate（新请求 202、同身份原请求 200、相同 ID 不同冻结输入 409）；GET /tts/tasks/{request_id}（不存在 404）；GET /tts/tasks/{request_id}/audio（仅 completed 可读）；POST /tts/tasks/{request_id}/cancel（返回实际状态）；POST /shutdown（仅匹配启动者 secret token，可请求退出）。只绑定 127.0.0.1，默认 9881。请求不接受参考/输出路径，拒绝未知字段及非法 JSON，正文上限 64 KiB。

请求字段：request_id（ASCII 字母数字、_、-，最长 96），text（1–250 字符、非空），voice_id（仅 existing-reference），emotion（设计中 12 种，默认 narrative），emotion_intensity（0–1，默认 .3），instruction（0–300 字符），seed（0–2^63-1，默认 42），cfg_value（.1–10，默认 2），inference_timesteps（1–50，默认 10）。固定 normalize/denoise/retry_badcase=false，max_len=1024。情绪强度只映射自然语言，不声称模型原生强度；不做自动导演或分段。语音合成前缀与参数写入冻结请求。

SQLite 以 request_id 为主键，冻结输入包括模型规格和参考 SHA256，规范化 JSON 指纹用于幂等；任务路径由 request_id 的 SHA256 派生，避免 Windows 文件名别名。状态 queued→running→completed/failed；queued 取消立即 cancelled，running 取消先 cancel_requested，推理真正返回并丢弃产物后才 cancelled。内部不自动重试，重复原失败 ID 返回原失败。

WAV 先写 partial，核对一次头/样本数，原子发布，再用既有 write_record 写带请求指纹和结果的完成回执，最后提交 DB completed。重启只对 DB 非终态对账：已取消请求置 cancelled；running 有匹配完成回执且合法 WAV 则复用；无回执置 failed/interrupted，不擅自重生成；queued 原样保留，启动后验证冻结绑定再执行。相同状态目录的模型/参考改变时，旧请求返回旧记录，新同 ID 不同输入拒绝，旧 queued 明确失败 input_changed。

stop 拒绝新提交，取消 queued，标记 running 取消已请求，等当前有限段推理退出后关闭 DB/锁。拥有者控制器只保存本次 Popen 对象，先带 secret 请求 graceful shutdown，超时才复用 stop_process 终止自身进程；端口占用直接冲突，不接管/停止外来服务。重启后取消未决请求可确认为 cancelled，因为旧服务锁已释放。无 GPU 租约、ASR、权重重复哈希或全量产物扫描。

## Files

- `src/video_ai/voxcpm/{contracts,store,engine,service,server,process}.py`：契约、SQLite/回执、懒加载 CUDA、串行执行、HTTP、拥有者生命周期。
- `scripts/run_voxcpm2_service.ps1`：bootstrap 后用独立解释器启动。
- `tests/unit/test_voxcpm_service.py`：真实 SQLite/文件/HTTP，只有慢 GPU 边界替身。
- `scripts/experiments/voxcpm2_api_smoke.py`：真实服务启动、提交、重复/冲突、查询/下载、取消、重启保留、退出。
- `docs/voxcpm2-service.md`、`docs/research/TTS-VOX-03-result.json`：使用和实测。

## Tests

`. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment 'vox03-tests'; & $VideoAiPython -B -m pytest tests/unit/test_voxcpm_service.py -q`：幂等并发提交、不同参数冲突、queued/running 取消、推理异常、恢复回执/中断、绑定变更、路径/非法请求、HTTP 实际路由与受控音频、shutdown token/外部端口不接管。预期全部通过。

同一 bootstrap 下执行 `& $VideoAiPython -B -m pytest -q`，要求完整套件通过，已有失败如实报告。GPU smoke 使用 shared/envs/voxcpm2 解释器，预期真实 PCM16 48 kHz、请求持久化、重复不重算、取消状态明确、重启复用 completed、正常清理。只生成必要短样本，不重跑 02。

## Acceptance

上述 API 在真实 GPU 服务可用；有原始任务记录和音频；单线程模型常驻、同输入幂等、不同输入冲突、失败可查询、取消不冒充停止、重启不重算已完成结果；仅停止拥有进程。旧生产链路不变。用户放行不等于 02 指标被改写。

## Risks

官方同步 generate 不能安全中断线程，取消须等待当前段结束；强制停止由拥有者结束单一服务进程。标准库 HTTP 仅供本机内部服务使用。文件系统与 SQLite 不能跨介质原子事务，靠完成回执对账；WAV 发布至回执之间崩溃判定明确失败，不能猜测成功。03 不保证文本发音或情绪效果改善。
