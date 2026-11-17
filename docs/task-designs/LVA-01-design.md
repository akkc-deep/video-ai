# LVA-01 本地基线与校验台账设计

## Goal

为 `paragraph_jimeng_v1` 建立可复现的本地耗时、正常/恢复校验调用证据，区分历史优化与仍存在的热点。不把离线媒体测量当作 Wan GPU 或整片基线。

## Scope

观测从已选图片到本地交付的服务、片段、超分、合成边界及公共校验；提供独立离线 benchmark、固定输入实验协议和 JSON/Markdown。保留生产参数、不可变记录、原任务恢复、人工接受及所有现有检查。即梦模块不修改，原 run 只读；本任务不删校验、不优化采样或调度。

## Approach

采用显式 `with LocalVideoMetrics(mode='normal'|'recovery')` 的旁路函数调用观测，关闭时生产路径完全不变。相较在每个校验入口插入日志，此方案不修改生成代码、冻结身份或日志格式；相较仅静态计数，它可测调用者位置、嵌套耗时、实际哈希和媒体进程。仅跟踪当前线程，拒绝覆盖已有 profiler；新 worker/Comfy 子进程内部不伪报计时。

`runtime/local_video_metrics.py` 使用 `sys.setprofile` 跟踪明确的代码位置，不序列化参数、局部变量、异常消息、prompt、HTTP body、路径原文或命令行。来源仅保存包内文件/函数/行号；文件标识为路径的 SHA256。嵌套事件保存父 ID、起点及 inclusive/self 秒数。每个校验事件累计子调用的文件访问次数、独立文件数、已知引用字节、实际 SHA 计算/字节、媒体 probe/完整解码进程；缺失字节明确为未知，不额外 stat/read/hash。哈希入口与实际 `_hash_open_file`/`_read_open_bytes` 分开。FFprobe `-count_frames`、`-show_frames` 和 FFmpeg null/rawvideo/framehash 解码分别计数，次数是进程调用而非逐帧遍历估计。事件有上限，截断则报告不完整；函数异常退出不从 profile 的 return 猜测成功。

阶段覆盖 `_OwnedService.ensure/close`、`_input/_technical`、`inspect_video/trim_scene_video/extract_native_frame`、`recover_or_submit_scene_clip/frame`、超分提帧/复制、合成物化/编码/交付。Comfy 内部模型 load/unload、文本编码、high/low、VAE、逐帧 GPU 和资源峰值没有当前进程证据时使用 null 和 missing 列表，不能用外部提交等待冒充采样。后续授权 GPU 实验须结合 Comfy 原始计时和 GPU 采样；本轮先交付缺失项可见的采集与汇总接口。

另提供仅在**新的实验 Comfy 子进程**中启用的 `ComfyNodeMetrics`。启动器通过可恢复的 import hook 在 native main 完成其 allocator/device 初始化后接入，等待 `init_extra_nodes` 完成再包装实际节点 FUNCTION/V3 execute；同步、异步、static/class/inherited descriptor 均保持。只记录固定阶段标签、起止墙钟、成功/失败布尔量，不记录参数。KSamplerAdvanced 的 high/low 根据当前原质量图的 start/end/steps 数字分类；LoadedModel.model_load/unload 是实际方法调用计数，不宣称物理权重全量装卸次数。可选 nvidia-smi 每2秒记录设备级使用量与利用率，属于采样峰值，不能当本进程独占显存或 CUDA kernel 时长。

`scripts/observe_local_comfy.py` 只创建 scratch/benchmarks 下的新目录，loopback独立端口、显式模型/输入/输出/temp/user/database路径、禁用付费节点和自定义节点。它不提交graph、不恢复生产；只启动并停止自己持有的子进程。Windows超时强停会跳过Python finally，因此每个完成节点和GPU采样都刷新聚合checkpoint，父进程明确记录 metrics_finalized；只有优雅退出的summary才标记finalized。强停时最后合法checkpoint是部分证据，在途节点不能计完成。

`summarize_samples(samples)` 接受明确的 `wall_seconds`、`human_wait_seconds`、`usable_video_seconds`、`accepted`、`failed`、`redone`、`mode`、`temperature`，分组汇总 P50/P95、每可用视频秒墙钟成本、失败/重做率；无样本/无可用秒时为 null。人工等待单列，绝不把事件 inclusive 时间相加为整片时间。

`scripts/benchmark_local_video.py` 只创建全新 scratch fixture，使用本机 FFmpeg 和明确禁网作用域，运行同内容视频的正常路径和已有产物读取路径各 4 次，分别输出 profiler 开/关墙钟及内容身份，测量观测器扰动。不启动模型或修改现有 run。三类真实实验协议单列为待执行，低运动/高运动/父子续接固定选图、prompt 摘要、seed、尺寸和完整帧预算；实际图片/prompt 必须由已选输入冻结，不能把合成测试图登记为质量样本。真实实验需明确许可的新 run，不能消费或恢复旧生产。

## Files

- `src/video_ai/runtime/local_video_metrics.py`：有界脱敏观测、报告和样本汇总。
- `src/video_ai/runtime/local_comfy_metrics.py`、`scripts/observe_local_comfy.py`：独立实验节点/模型/GPU采样及有归属、有时限的启动入口，不修改现有Comfy文件。
- `scripts/benchmark_local_video.py`：独立真实媒体离线复现与观测扰动测量。
- `tests/unit/test_local_video_metrics.py`：实际哈希与缓存、脱敏、清理、分位数和样本边界。
- `tests/unit/test_local_comfy_metrics.py`：方法描述符、异步/异常原义、启动顺序、硬停前checkpoint；全部使用stub，不导入真实Comfy/torch。
- `tests/integration/test_local_video_metrics_flow.py`：真实 FFmpeg probe/decode、隔离生产 fixture 与已有媒体只读重放。
- `docs/task-designs/LVA-01-validation-ledger.md`：逐调用点价值及历史优化分类。
- `docs/task-designs/LVA-01-results.md` 及配套 JSON：实测、环境、限制和真实实验协议。

## Tests

使用 `E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_local_video_metrics.py tests/integration/test_local_video_metrics_flow.py tests/unit/test_scene_comfy_send_checks.py -q -p no:cacheprovider`；期待通过，观测前后媒体 SHA 一致、恢复无新增提交/服务启动或媒体生成（仍重建媒体真实性）、退出后 profiler 恢复，敏感测试字符串不进入 JSON。另运行 `tests/unit/test_scene_media_performance.py`，已有 fixture 失败独立记录，不为了此观测改写无关业务实现。

使用同一 Python 执行 `scripts/benchmark_local_video.py --output E:/VideoAI/scratch/logs/LVA-01-offline.json`；期待 JSON 和 Markdown，normal/recovery 独立，实际媒体结果及开关扰动实测；GPU、人工质量及整片耗时明确未验证。

`python -X utf8 -m pytest tests/unit/test_local_comfy_metrics.py -q -p no:cacheprovider` 期待6项通过。`python scripts/observe_local_comfy.py --help` 只解析帮助，不启动Comfy/GPU；真实启动不作为离线检查运行。

## Acceptance

1. 台账每项有确切源码位置、正常/恢复入口、独立拦截价值及可复用条件，历史优化不登记新收益。
2. 有界结构化计时无敏感文本，无新增验证读取，给出真实 hash/decode 计数而非入口次数。
3. 离线单元/集成和媒体基准通过；生产调用参数和证据不修改。
4. 三类真实 fixture 各冷 1 次、热至少 3 次，固定身份、完整帧、质量人工确认，GPU 阶段和资源数据齐备后，才可登记本机基线完成。在此之前任务保留 IN_PROGRESS，LVA-02 不自动准备。

## Risks

- `sys.setprofile` 会扰动 Python 密集路径，必须报告开关对照，不能把观测耗时直接当无扰动耗时。
- 当前线程无法看到 Comfy 内部阶段或已有网络 worker；缺失显式列出，不推算。
- 三类真实输入、冷/热技术实验及最终人工质量现已完成；连续整片吞吐和优化收益尚不能由本基线外推。
