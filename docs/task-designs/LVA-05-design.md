# LVA-05 超分模型复用、受限流水线与编码实验设计

## Goal

完成任务板 `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md` 的 LVA-05：在保持全部原生帧、1920×1080 输出、严格恢复和真实人工验收的前提下，测量 RealESRGAN 模型复用、CPU I/O 重叠和实验编码的实际收益或否决原因。该设计只准备实施入口，不授权 GPU、不恢复生产。

## Scope

- 直接输入仅 LVA-01 的已接受原生/超分/合成基线、LVA-02 的严格事务规则、LVA-03 的 owned 阶段和只读准备边界。LVA-04 仅为顺序前驱，不是技术依赖，不启用其被否决的 fast 配置。
- 第一版交付独立 `LVA-05-*` 新实验；不改旧 production options/schema、原 upscale workflow/mapping、旧 intent/accepted、生产默认和人工门槛。原生视频使用已完成并接受的 LVA-01 quality 输出，不重跑 Wan 或下载新模型。
- 实测 serial → prefetch-only → writeback-only → pipeline，每次只改变一项 I/O 因子。一个 Comfy 进程、一个 RealESRGAN 实例、同一时刻一个 GPU 请求。已存在的同阶段服务/model-node 缓存只审计，不作为新增收益。
- NVENC 单列编码实验，不与 I/O 候选混在一项数据内。像素或既有验收契约不满足则明确拒绝替换；原 libx264 medium/CRF18 路径保留。
- 不重复实现已有批量提帧、PNG 全像素证明、复制批次证明或合成单次解码；不减少生成/贡献帧，不改旁白/字幕/颜色/帧率要求，不触及即梦链路。

## Approach

### 已有行为与固定素材

`production_scene_upscale._produce` 已懒创建一个 `_OwnedService`，逐帧复用 capability cache，并在 finally 关闭；`upscale_api.json` 的 node2=UpscaleModelLoader、node3=ImageUpscaleWithModel、node4=Lanczos 1920×1080、node5=SaveImage。模型名/节点不变时原生 Comfy 可能缓存 node2，不应另造常驻 manager 或宣称 loader 方法次数就是物理装载次数。

实验基线复用 `scripts/postprocess_local_gpu.py::require_native_review/upscale_trial/compose_trial` 的原素材、全帧提取和处理规则。来源从 `LVA-01-gpu-results.json` 的 cases/postprocess 解析，逐一绑定原请求、native retained SHA、观察接受 SHA、extraction 和全帧序列；父/子必须按 `requires_new_parent` 与 source clip ID 区分，不能被共同 fixture_id 覆盖。只消费已有接受的真实父/子素材，不读取尚未接受的新尾帧。

准备时生成 `LVA-05-experiment-manifest.json`：原生来源和接受记录、RealESRGAN_x4plus.pth 完整 Artifact、workflow/mapping/脚本、Comfy/Python/Torch/CUDA/driver、FFmpeg/FFprobe、字体和旁白素材完整身份，以及 factor/预算/请求图和参数。大模型首次在受保护阶段完整准入，后续使用现有 native 租约；弱平台严格回退。不得以 size/mtime 代替 SHA。原 workflow SHA 为 `a647f05940ce6b59de9bde8d5d53b9300bfe6b5174d900b3324eb6cd01680533`。

### 新实验接口与资源预算

新建 `src/video_ai/experiments/upscale_pipeline.py`，仅被本项实验脚本调用：

- 不可变 `PipelineConfig(prefetch=False, writeback=False, max_prefetch_bytes=64*1024**2, max_writeback_bytes=32*1024**2)`；默认 serial。总预留 payload 上限沿用前项 96MiB，必须同时计入源字节、图谱和待写回字节，不等同 RSS 上限。
- `UpscaleFrameJob(frame_id, source, graph_bytes, parameters_sha256, profile_sha256)` 是纯数据；source 是完整 Artifact。key 包含帧序号/源路径/bytes/SHA/图/参数/实验身份。只接收已接受 native clip 的已证明提取帧，不含 store、reader、logger、服务或 ContextVars。
- `UpscalePipeline(config)`：`prepare(job)->bool`、`consume(job)->PreparedSceneInput|None`、`stage_output(job, captured_output, staging_path)->bool`、`finish_output(job)->StagedFrame|None`、`close()`。最多一个未消费预读、一个未完成写回；预读和写回各至多一个 CPU worker。没有 worker GPU/HTTP。
- 预读复用 LVA-03 `PreparationJob/ScenePreparationPool`，显式配置 source≤48MiB、graph≤16MiB，使二者合计≤64MiB；读取每块≤1MiB、最多声明 bytes+1，完整 SHA 和打开前后身份一致才返回。失败、超限或 miss 回原协调线程串行读取，不能制造准入证明。
- 写回只复制原 Comfy 已完成且由协调线程捕获的 PNG 到 caller 预先指定的本项唯一 private staging 文件。声明 bytes≤32MiB，源字节完整 SHA 匹配，写入独占打开、flush/fsync 后返回纯数据；不做晋升、不写 JSON/日志/accepted，不调用 store。任何扩长最多读声明 bytes+1即拒绝。
- 协调线程只在原 history-completed 已持久化、输出 Artifact 捕获后排写回。可以在前一帧 private staging 复制期间等待下一帧 GPU，但同一时刻只有一个 GPU 请求；写回槽位未清空时禁止开始第三帧请求。取回时重新验证源、当前 job key、PNG 全尺寸/内容，原子晋升并写本实验 frame receipt；所有 durable JSON 和提交仍在协调线程。
- `close` 取消排队、最多等待2秒并丢弃 late 结果；尚未结束的 OS I/O 只能落在唯一 private staging，不得后台晋升/提交或跨审核驻留。异常首先保留原错误，诊断/关闭错误只能附注。未被证明的 staging 绝不冒充已完成帧。

活动 GPU 张量、当前帧的必要媒体缓冲和 allocator overhead 不包含在上述预取 payload 内，另报进程峰值/RSS与限制。磁盘峰值记录实际 stage/raw/accepted PNG 文件；不删原 history 引用的输出或完整帧证据来伪造存储收益。

### Durable 协议与恢复

新 `scripts/benchmark_upscale_pipeline.py` 包装 LVA-01 ExperimentClient 的原 durable intent/queue/history/accepted 协议；帧 job 使用原 upscale 类型 ID，不使用仅接受 Wan cold/warm ID 的 FastExperimentClient。新增 `frozen/manifest.json`、实验 request 和每帧 profile-binding，在每次提交/恢复/证据写入前验证完整 factor/graph/model/tool/source 身份，不给 Comfy POST 添加未知字段。

serial 与候选只改变后台 I/O 安排；提帧、PNG 验证、最终 frame_rgb_sha256 和目标尺寸复用原实现。已有已证明 frame receipt 先验真跳过 GPU和本地 producer；unknown 只找原 ID，不开新请求或替换历史服务。部分 staging 只能按同源、同 job、同工具和完整原 accepted/history 重建，未证明或冲突则拒绝，不能盲收现成 PNG。重启后池/内存证明清空。

覆盖 accepted 后、GPU 完成未捕获、staging 写到一半、fsync 完未记 receipt、晋升前后、第 N 帧后和最终合成中断；完整帧计数/顺序/像素证据保持。只在同一调用、同源/参数/工具和强内容保护成立时复用现有证明，不开启 LVA-02 被否决的默认候选，也不跨独立 HTTP guard 继承 memo。

### 编码研究

从 `_scene_composition_commands.encode_args` 复制原字幕/音轨/16fps/映射/颜色等所有参数到新的实验 request，基线继续 `libx264 -preset medium -crf 18 -pix_fmt yuv420p`。独立 NVENC 候选只将视频编码段换为 `h264_nvenc -preset p4 -rc constqp -qp 18 -pix_fmt yuv420p`，保留其他参数，明确 QP 与 CRF 不等价。

先只读 `ffmpeg -encoders` 和 `ffmpeg -h encoder=h264_nvenc`，缺编码器/参数/驱动能力则 unsupported，不安装包、不改 flags 猜替代。真正硬编属于另行明确授权的 GPU 实验。相同完整 materialized 1080P PNG/字幕/旁白输入，独立比较编码墙钟、输出大小、完整帧/PTS、颜色元数据和解码逐帧 RGB SHA；每份编码视频只完整解码一次并复用所得证据。编码因子不重新跑 RealESRGAN。

逐帧像素不一致判 `rejected_pixel_contract`，保持原 FFmpeg 默认；即使主观接近也不自动放宽契约。仅技术契约全满足时再请求完整人工观看并记录独立质量判断。不存在可用数据不填0秒或预设提速。

### 基准与采用

先 CPU/fake transport + 真实小 PNG/FFmpeg夹具验证 normal/completed/partial recovery，离线绝不加载真实模型或 GPU。然后列出本项精确 manifest、新 root、命令和最大样本，再取得 LVA-05 GPU 授权；LVA-04 授权不外推。

真实每个可执行 `(factor, fixture)` 组合用一个新 owned process，低/高/父/子各使用已接受素材的全部保留帧，每组冷1/同进程热3；cold指进程冷而非清空OS磁盘缓存。阶段串行，先关闭服务再审核。先 serial 与单因子，只有技术/质量通过的因子才组合；组合与单因子完全相同则引用数据、不重复生成填表。无可重复改善保持默认 serial，交付否决也属明确实验结果。

分别记录单帧/整批墙钟、I/O与校验、loader/model方法次数、实际原生 backend、设备采样峰值/低利用区间、逻辑队列峰值/取消和磁盘峰值；物理装载/独占 GPU 空闲未测就单列未测。normal/recovery、超分/编码、局部/整片分开，不能相加成全片吞吐。最终质量接受前不报告每可用视频秒成本。

## Files

- 新 `src/video_ai/experiments/upscale_pipeline.py`：纯数据、有界预读/写回和 coordinator drain；不改既有准备池默认。
- 新 `scripts/benchmark_upscale_pipeline.py`、`scripts/observe_upscale_comfy.py`：独立manifest、原协议包装、bounded owned服务和计量，复用现有 observer/postprocess工具。
- 新 `scripts/benchmark_scene_encoding.py`：encoder capability、独立固定命令、原素材绑定和完整像素/PTS报告。
- 新 `tests/unit/test_upscale_pipeline.py`、`test_scene_encoding_experiment.py`、`tests/integration/test_upscale_pipeline_recovery.py`。
- 新 `docs/task-designs/LVA-05-results.json/.md` 和本项GPU manifest；原 workflow/mapping、生产 schema/事务及旧产物只读。

## Tests

第一动作：在 `test_upscale_pipeline.py` 写 `test_single_write_slot_backpressure_and_completed_replay` 及 same-size/mtime 回滚、64+32MiB共享预算、worker无HTTP/store/ContextVars、late staging不晋升的 RED 用例，然后实现上述数据类/池和协调接口。不能先跑GPU、改原图或重复设计。

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_upscale_pipeline.py tests/unit/test_scene_encoding_experiment.py tests/unit/test_scene_stage_preparation.py tests/unit/test_scene_upscale_transactions.py tests/unit/test_scene_upscale_service_preparation.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/integration/test_upscale_pipeline_recovery.py tests/integration/test_scene_upscale_flow.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --offline --repeats 4 --output E:/VideoAI/scratch/benchmarks/LVA-05-offline-results.json
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --offline --output E:/VideoAI/scratch/benchmarks/LVA-05-encoding-offline-results.json
```

期望：单GPU请求串行、槽位/预算有界；协调线程写全部不可变证据；完成恢复0POST/0producer，unknown只原GET；源/模型/工具/参数/owner变化在POST前拒绝；完整输出帧/像素序列与serial相同。编码缺能力或像素不等明确拒绝，不能伪造 passed。已知前项 legacy-model/无效run/continuity/delivery夹具问题单列，不扩修。

## Acceptance

1. baseline/单因子/组合有真实阶段/单帧吞吐、I/O/校验、方法次数、设备采样和峰值存储证据；已存在模型复用不冒充新收益。
2. 至多一个预读/一个写回、logical payload≤96MiB，全部持久化在coordinator；重启/漂移/异常恢复符合原intent协议，已有完整帧不重做。
3. 原输入、全部frame/RGB证明、1920×1080/16fps及人工门槛保持；编码有能力/像素/PTS/颜色/视觉结论，不兼容则原libx264保留。
4. 单元/集成/离线和另获授权的真实实验 JSON/Markdown 具名分层，未测项不记通过；采用另行决定、默认/旧任务/原生产保持。

## Risks

已有阶段复用可能已足够；预读/写回未必改善GPU利用率，可能增加内存/磁盘峰值，故仅实验且允许否决。NVENC常见有损输出可能无法满足像素等价，明确拒绝比放松契约优先。late OS I/O不能当作完全取消；只能隔离为不可晋升的private staging。真实环境模型方法不是物理搬运证据，未支持和未测应直报，不换引擎/安装包。无未解决的材料/结构/协议选择；尚待实验的性能/质量有确定失败分支。
