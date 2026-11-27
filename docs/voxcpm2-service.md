# TTS-VOX-03 本地 API 服务

03 已完成独立服务实现和真实 GPU API 验证。02 依据用户明确授权放行，原始情绪/性能结论保留。本服务是显式选择的独立入口，04 才连接生产双后端。

## 启动与退出

```powershell
# 演示目录位于既有 runtime scratch；生产阶段由调用方传入 work 修订音频目录。
.\scripts\run_voxcpm2_service.ps1 -StateDirectory 'E:/VideoAI/scratch/tts-api-demo' -Port 9881
```

沿用 `VIDEO_AI_RUNTIME_ROOT`，默认 `E:/VideoAI`，独立解释器为 `shared/envs/voxcpm2/Scripts/python.exe`，离线模型在 `shared/models/VoxCPM2`。服务仅绑定 `127.0.0.1`，不安装额外 Web 依赖。需要 01 的固定环境/部署规格及现有 `shared/config/production.json` 和 voice.json。参考文件在启动时校验一次小型 SHA256 并冻结到当前状态目录；不扫描或重新哈希模型权重。

前台入口使用 Ctrl+C 请求退出。程序调用者先运行既有 bootstrap，再用 `video_ai.voxcpm.process.VoxServiceProcess(runtime_root, state_dir, port=9881)` 的 `start()` / `stop()` 管理本次 Popen。`start()` 端口冲突直接拒绝，不接管现有进程。`stop()` 使用独立 secret 请求优雅退出，默认等待最多 120 秒，超时仅终止自己保存的 Popen 对象。服务只有一个进程和一个推理线程，没有遗留模型子进程。

state-dir 必须位于该 runtime 的 `work/` 或 `scratch/` 内，不能是这两个根本身。正常集成时应位于现有视频修订的音频目录；独立实验可使用 scratch。目录持有 OS 文件锁，禁止两服务同时写入同一 SQLite。状态目录不要在任务存续期间清理；scratch 是实验存储，不保证跨人工清理保留。

## HTTP 契约

| 方法与路径 | 结果 |
|---|---|
| GET /health | ready 时 200；loading、failed、stopping 时 503，含 session_id / model_revision / error |
| GET /voices | 当前固定参考音色 `existing-reference` 及身份 |
| POST /tts/generate | 首次接受 202；同 ID 同冻结输入 200 返回原任务；不同输入 409 |
| GET /tts/tasks/{request_id} | 原任务、冻结请求、状态、错误、result；不存在 404 |
| GET /tts/tasks/{request_id}/audio | completed 的受控 WAV；未完成 409，产物缺失 410 |
| POST /tts/tasks/{request_id}/cancel | 返回真实当前状态，不把请求取消当成已经停止 |
| POST /shutdown | 需拥有者 `X-Vox-Stop-Token`；202 表示请求退出，不能当作进程已退出 |

POST 使用 `Content-Type: application/json`，取消和退出正文为 `{}`。只接受 JSON 对象，最大 64 KiB；拒绝非有限数字、未知字段、浏览器 Origin 和 Transfer-Encoding。请求无法指定模型、参考或输出路径。文件仅能按已完成任务 ID 获取。

```powershell
$voxBody = @{request_id='demo_0001'; text='旅行者二号正在遥远的星际空间航行。'; voice_id='existing-reference'; emotion='narrative'; emotion_intensity=0.3; seed=42} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:9881/tts/generate' -Method Post -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($voxBody))
Invoke-RestMethod 'http://127.0.0.1:9881/tts/tasks/demo_0001'
```

允许字段与默认值：`request_id` 为 1–96 个 ASCII 字母数字/_/-，首字符字母数字；`text` 非空且最多 250 字符；`voice_id=existing-reference`；`emotion=narrative`，枚举见总设计 12 种；`emotion_intensity=0.3`，范围 0–1；`instruction=''`，最多 300 字符；`seed=42`，范围 0–2^63−1；`cfg_value=2`，范围 .1–10；`inference_timesteps=10`，范围 1–50。整数参数拒绝布尔值。强度仅映射轻微/适度/明显自然语言，不声称模型原生数值控制，也不声称解决 02 的情绪区分问题。

模型默认 normalize/denoise/retry_badcase=false、max_len=1024、optimize=false，来源为现有固定部署规格。03 不做自动分段、情绪规划、设计型音色管理或生产安装迁移。调用者需要查询原任务再处理响应丢失，不能换 ID 自动补单。失败任务同 ID 返回原失败，本服务不自动重试。

返回值顶层有 `request_id/engine/fingerprint/request/status/result/error/created_at/updated_at`。completed 的 `result` 包含 `audio_path`（相对 state-dir 的受控路径）、`sample_rate/sample_count/channels/sample_width/duration_ms/generation_time_ms`。路径由 ID 的 SHA256 派生，避免 Windows 保留文件名及大小写别名；不是任意路径写入接口。

## 取消与恢复

- queued 取消立即变 cancelled；running 取消先变 cancel_requested。官方同步 generate 不支持安全抢占线程，因此要等当前有限片段实际返回、丢弃临时产物后才 cancelled。取消后不能下载产物。
- 一个模型在阶段内加载一次，串行推理。正常退出拒绝新提交、取消排队并等待当前生成结束。强制结束由拥有者终止单一服务进程。
- WAV 写 partial，单次检查 48 kHz/单声道/PCM16 和真实样本数，再原子发布；完成回执用既有 write_record 落盘，最后提交 SQLite completed。
- 重启只对非终态对账：running 有合法匹配回执则复用，否则 failed/interrupted；cancel_requested 变 cancelled；queued 保留并检查原冻结模型/参考绑定，改变时 failed/input_changed。completed 不重算，不进行全量文件扫描。
- 崩溃发生在 WAV 发布与完成回执之间时无法确认原请求完成，明确标为失败；不猜测成功。恢复/生产更全面的故障注入属于 07。

## 验证结果

[设计](task-designs/TTS-VOX-03-design.md)、[原始 API 实测](research/TTS-VOX-03-result.json)。真实输出位于 `E:/VideoAI/scratch/benchmarks/TTS-VOX-03/20261125-100042-747664/`，SQLite、输入副本、回执与服务日志在其 `state/` 目录内。

- 真实 CUDA 服务就绪：13.556 秒；短样本 3.52 秒，48 kHz、PCM16、单声道，168,960 个样本；本次同步推理 6.937 秒。这是功能验收短样本，不是新的稳态性能基准。
- 验证了首次 202、运行中重复 200、不同 seed 冲突 409、实际 WAV 下载、queued→cancelled、running→cancel_requested→cancelled、取消产物不可下载、重启后原 completed 记录精确复用。
- 两次拥有者服务都退出码 0，完整 smoke 38.658 秒。只生成一个交付短样本及一个用于取消的短片段，没有重跑 02 或生成视频。
- 独立审查发现并修复 worker 异常后健康状态未失败、partial/DB/lock 实际路径约束问题；使用回归测试验证 worker 丢失会拒绝新提交。另修复 Windows 空端口短连接探测超时、启动失败日志句柄，以及只读文件描述符 fsync 导致的 Bad file descriptor。失败实验目录保留，没有覆盖证据。
- 新服务与旧服务/TTS 相关测试的最终结果见实测归档 `verification`。三个真实文件符号链接测试因 Windows 缺少创建符号链接权限跳过；路径约束已实现，不声称这三种实景在本机跑过。
- **全套回归未通过**：默认全量收集有 unit/integration 同名 `test_scene_stage_preparation` 冲突；使用 importlib 和显式 tests/helpers 路径后，首个实际失败是 `tests/integration/test_candidate_performance_flow.py::test_two_ordinary_tasks_are_accepted_before_polling[2]`（期望 submit/submit/query/query，实际 submit/query/submit/query），单独运行同样失败。该测试不导入 Vox 模块，相关业务代码没有修改。完整套件不能声称全绿；一次非 fail-fast 运行在前部已出现多项 F/E 后中止，未得到逐项完整结果。

复现功能测试：bootstrap 后执行 `python -m pytest tests/unit/test_voxcpm_service.py tests/unit/test_services.py tests/unit/test_tts.py -q`；按仓库约定将 `src` 和 `tests` 加入进程 PYTHONPATH、临时/缓存目录置于 runtime scratch。真实 GPU 验证用 bootstrap 后的 `$VideoAiPython -B -u scripts/experiments/voxcpm2_api_smoke.py`，它自行拥有、停止并重启独立服务。非本任务回归失败日志保存在 `E:/VideoAI/scratch/logs/vox03-regression-first-real.txt` 与 `vox03-existing-candidate-failure.txt`。
