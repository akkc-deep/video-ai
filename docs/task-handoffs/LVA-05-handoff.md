# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`
- **Completed task:** LVA-04，已按不兼容的实际否决实验登记 COMPLETED，证据 `docs/task-designs/LVA-04-completion.json`。它只是顺序前驱，不是本项技术依赖。
- **Next task:** LVA-05，按预定义 Order=5 选取，观察 NOT_STARTED。
- **Design document:** `docs/task-designs/LVA-05-design.md`，已完成并关联任务板。
- **Expected next status:** READY；本交接写入并关联后执行 NOT_STARTED -> READY，不启动实施或 GPU。

## Next Task

LVA-05 — P2 / E：超分模型复用、受限流水线与编码实验。使用原已接受 quality native 素材，审计既有同阶段模型复用，建立独立 serial/prefetch/writeback/pipeline 实验和单独 NVENC 编码对照；单GPU、同请求原ID恢复、全部帧/1080P和人工门槛保持。

专项设计固定一个预读槽、一个写回槽、64+32MiB payload预算；CPU worker仅传纯数据或写唯一 private staging，协调线程完成全部 durable evidence/HTTP/晋升。硬编能力缺失或逐帧像素/PTS/颜色/既有契约不满足即拒绝，原libx264默认保留。完成以设计四条Acceptance为准：真实可重复计量或明确否决、受限资源和0重复提交恢复、完整帧/质量/编码结论、具名分层报告；无真实授权实验不得填通过或宣称收益。

## Dependencies

### LVA-01 / 已接受原生、超分与合成基线

- **Artifact:** `docs/task-designs/LVA-01-completion.json`、`LVA-01-gpu-results.json` / `.md`、`LVA-01-gpu-experiments.json`；`scripts/postprocess_local_gpu.py`、`scripts/observe_local_comfy.py`、`src/video_ai/runtime/local_comfy_metrics.py`。
- **Decision:** 保留已接受 quality native 的每一保留帧、原种子/输入和实际父子绑定，原 RealESRGAN_x4plus + Lanczos 1920×1080、16fps和原旁白/字幕。观察方法次数不等于物理装载次数。
- **Rationale:** 已有真实超分/成片和技术/人工接受，适合作为固定素材，避免为了本项重复Wan生成；既有T0包络不能相加成整片吞吐。
- **Constraint:** 旧root只读，未接受的未来父片不能作为子源；父/子虽共享fixture_id也必须按来源绑定区分。新GPU授权不继承LVA-01或LVA-04。
- **Usage:** 从原results cases/postprocess和接受记录冻结素材；复用require_native_review、全帧提取/像素证明及compose规则，分开测超分与编码。
- **Readiness evidence:** 已供completion明确16 native、1424超分帧、12份final1080p接受；原owned服务关闭，原生产未恢复。不得把新LVA-04未重新接受的对照替代这些已接受来源。

### LVA-02 / 严格默认和断点恢复

- **Artifact:** `docs/task-designs/LVA-02-design.md`、`LVA-02-results.json` / `.md`；`src/video_ai/runtime/scene_upscale_transactions.py`、`scene_validation_pass.py`、`tests/integration/test_scene_validation_recovery.py`。
- **Decision:** strict默认保留，不开启被否决候选；完成媒体验真后复用，unknown仅恢复原GET。输入/模型/工具漂移和冲突accepted仍拒绝。
- **Rationale:** 减少逻辑调用未证明正常墙钟收益；独立HTTP/intent/accepted/晋升边界仍有保护作用。
- **Constraint:** 不跨独立HTTP guard共享memo，不由worker继承协调线程证明，不变旧intent/receipt/schema，异常未知不创建第二POST。
- **Usage:** 新实验包装既有durable协议；测试完成恢复0POST/0producer、部分staging/晋升/第N帧/最终合成中断和强身份漂移。
- **Readiness evidence:** LVA-02已COMPLETED并具名提供定向事务/HTTP和真实媒体恢复证据；已披露legacy-model/无效run/continuity/delivery问题不当作本项已修复。

### LVA-03 / owned阶段与有界CPU准备

- **Artifact:** `docs/task-designs/LVA-03-design.md`、`LVA-03-results.json` / `.md`；`src/video_ai/runtime/scene_stage_preparation.py`、`production_scene_clips.py`、`tests/unit/test_scene_stage_preparation.py`。
- **Decision:** 已有每phase一次owned服务复用只审计，不重复实现；默认准备候选仍关闭。CPU准备为纯数据、强SHA、有限槽位；协调线程负责证据和请求，服务不跨审核。
- **Rationale:** 原候选没有可重复GPU墙钟收益，物理权重搬运未测，默认不推广；资源和取消边界已具名验证。
- **Constraint:** 只在本项新实验显式启用；不得把writer/store/HTTP/ContextVars交给worker，不并行GPU，不后台晋升late结果。
- **Usage:** 复用只读PreparationJob/Pool与阶段计量，按设计48+16MiB预读和32MiB写回预算封顶；新private staging写回是本项实验，不改变前项worker默认行为。
- **Readiness evidence:** LVA-03已COMPLETED，结果供88定向通过、修正真实媒体阶段/恢复证据及32次native实际接受；候选默认关闭、原服务退出。

上述输入无冲突：原接受quality和全帧约束相同；strict/协调写证据/owned phase保持；实验worker预算不放松前项默认，NVENC只进入新的实验身份，旧生产命令不变。

## Start Here

按序读：① `docs/task-designs/LVA-05-design.md` 全文；② 本板LVA-05与本交接；③ LVA-01实际postprocess/接受来源；④ LVA-02严格恢复及LVA-03资源/生命周期结论；⑤ `workflows/upscale_api.json` / `.mapping.json`、`production_scene_upscale.py`、`scene_upscale_transactions.py`、`postprocess_local_gpu.py`、`_scene_composition_commands.py`、`scene_stage_preparation.py`。

第一动作：在新 `tests/unit/test_upscale_pipeline.py` 写 `test_single_write_slot_backpressure_and_completed_replay`，以及 same-size/mtime回滚、共享96MiB预算、worker无HTTP/store/ContextVars、late staging不晋升的RED用例，然后实现设计规定的数据对象和有界协调接口。不要先启动GPU、改原图或重新设计。

## Risks

已有模型缓存可能已足够，I/O重叠可能无收益或增加峰值；NVENC有损像素差可能导致拒绝。late OS I/O不能宣称全部取消，只能隔离为不可晋升的private staging。方法调用/设备采样不是物理装载/独占空闲；原生/超分/编码/整片分开报告，不猜倍数。LVA-05尚未实施、未获本项GPU授权，本交接与READY均不启动执行。
