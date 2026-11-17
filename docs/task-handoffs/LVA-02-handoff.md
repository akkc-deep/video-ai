# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`
- **Completed task:** `LVA-01`，任务板已记录 `COMPLETED`，验收映射为 `docs/task-designs/LVA-01-completion.json`。
- **Next task:** `LVA-02`，按预定义 Order=2 选中，交接创建前观察为 `NOT_STARTED`。
- **Design document:** `docs/task-designs/LVA-02-design.md`，已完整设计、独立builder核对、关联任务板。
- **Expected next status:** `READY`；先写本交接、关联路径，再执行 `NOT_STARTED -> READY`。本交接不启动实施。

## Next Task

**LVA-02 — P0 / B：重复校验精简与断点恢复正确性。** 在默认 `paragraph_jimeng_v1` 路径减少有相同保护证明的重复工作，同时保留原ID、完整媒体、人工接受和恢复/异常拒绝。

实施范围及接口以已完成专项设计为准：增加有界、线程内、单次同步guard的 `scene_validation_pass`，只复用现存原生lease保护的Artifact证明及同次目录检查；保留每次所有权、执行/连续性、模型/tool、请求/图谱、父片、socket和落盘/晋升边界。最外scene scope必须使用 `protected_read_pass(fresh=True)` 并在返回前flush；strict模式关闭全部新复用；CaptureLimit不能修复被污染的外层证明。

验收要求：每项复用可追溯到台账及scope/key/失效/回退；normal/recovery真实媒体对照有严格调用、实际哈希/解码、墙钟与输出身份；故障矩阵不增加POST或producer；未知任务只恢复原请求、已完成媒体先验真再复用。保留既有媒体探测优化和质量参数，不改持久化schema、即梦、服务调度或用户冷准入代码。交付针对性验证及 `docs/task-designs/LVA-02-results.json` / `.md` 后才能完成本项。

## Dependencies

### LVA-01 / 调用台账与离线证据

- **Artifact:** `docs/task-designs/LVA-01-validation-ledger.md`；`docs/task-designs/LVA-01-results.json`；`docs/task-designs/LVA-01-results.md`。
- **Decision:** 区分逻辑校验入口、真正文件SHA/字节和完整解码进程；保持所有必要提交、证据和晋升边界，历史优化不认领新收益。
- **Rationale:** 离线真实生产fixture正常hash入口13,545、实际SHA6,704、媒体进程79；恢复分别1,383、1,771、34。global闭包6,030次Artifact入口和send guard 6,270次是候选重复，不能等同于全量文件重读。完整profiler已有约2.5倍扰动。
- **Constraint:** `_technical` 已有 `inspection_reuse()`；提帧PNG证明、复制批次、合成解码合并、能力/轮询缓存已有实现，不重做。model stamp是metadata，不是模型全文哈希。
- **Usage:** 将台账候选映射到设计中的窄scope，分别比较无profiler墙钟与单独调用诊断，记录默认fixture及放大样本各自的减少量与未支持形式。
- **Readiness evidence:** LVA-01任务板已完成；历史主观测/隔离恢复/HTTP专项27通过，新实验/Comfy/后处理17通过；既有媒体22通过、1项具名无关fixture错误记录。原始事件细节超限明确标注，完整调用聚合未丢失。此处复述已有结果，没有重跑测试。

### LVA-01 / 原质量与实机时间边界

- **Artifact:** `docs/task-designs/LVA-01-completion.json`；`docs/task-designs/LVA-01-gpu-results.json` / `.md`；`docs/task-designs/LVA-01-timing-evidence.json`；`docs/task-designs/LVA-01-gpu-experiments.json`。
- **Decision:** 保留原40步、CFG3.5、全部生成/保留帧、父片真实末帧与人工接受依赖；不把局部验证收益当整片加速。
- **Rationale:** 低/高/父/子各冷1热3共16次原生、1424帧真实超分和12份1080P已技术通过；三类最终内容已实际人工接受，重复样本明确使用相同字节观察关联。主要原生时间仍在high/low采样。
- **Constraint:** 实验T0为本实验在既有已选/已适配输入上完成选材的记录，2026-11-15T04:28:50.660Z；观察完成包络保留排队、审核及通知延迟，样本重叠，不能相加成为吞吐。原生产上游适配和连续整片吞吐未测。
- **Usage:** 用作原质量、帧预算、环境和计时口径基线；本任务不重跑这些GPU样本或修改其已接受证据。新实验仅在另有授权时创建独立root。
- **Readiness evidence:** 最后用户“没问题，继续吧”于2026-11-15T09:50:34.724Z接受完整父子1080P；最终父子SHA `0d2d4e0eae5a87f34b3c5b14de74230a714f859cb4fb56064b07ae37436118c9` 已核对，四份一致。全部8个owned服务关闭，除初始low保留checkpoint外，后续7个exit0/finalized=true；无付费调用，旧生产未恢复。

### LVA-01 / 可复用测量工具与恢复证明

- **Artifact:** `src/video_ai/runtime/local_video_metrics.py`；`scripts/benchmark_local_video.py`；`tests/integration/test_local_video_metrics_flow.py`；`E:/VideoAI/scratch/benchmarks/LVA-01-gpu-low-20261115-01/completed-recovery-proof.json`；`E:/VideoAI/scratch/benchmarks/LVA-01-upscale-low-20261115-01/completed-recovery-proof.json`。
- **Decision:** normal/recovery分开、有界脱敏、只观察已有调用；恢复延迟不冒充新生成；原有产物不能因进程缓存失效而重做。
- **Rationale:** 已完成原生只读恢复约0.004秒、93帧真实超分/1080P恢复约0.129秒；原ID及源/PNG/候选身份保持，禁止client/media producer时仍成功，新增请求和媒体进程0。
- **Constraint:** 主线程profiler不覆盖任意HTTP worker或CUDA kernel；真实socket发送边界使用既有定向测试独立验证。不能把入口计数直接相减推断缓存命中，也不能把恢复路径免POST误报为不再验真。
- **Usage:** 建立新LVA-02隔离fixture与spy计数；复用现有prepared_wan/OfflineWan/generate方法及真实FFmpeg测试材料，保留所有恢复/内容断言。
- **Readiness evidence:** 相关实现、JSON/Markdown与原始恢复证明已存在；完成记录明确未修改生产生成代码、即梦协议或用户冷准入增量。

## Start Here

按顺序阅读：

1. `docs/task-designs/LVA-02-design.md`。
2. 本任务板LVA-02行及上述LVA-01台账/离线报告。
3. `docs/task-designs/jimeng-local-video-acceleration-v1.md` 第4节、第5.1节；`docs/task-designs/video-generation-performance-results.md`。
4. `src/video_ai/runtime/scene_clip_records.py`、`scene_media_records.py`、`production_scene_composition.py`。
5. `src/video_ai/runtime/_continuity_byte_guard.py`、`_protected_continuity_inputs.py`、`verification.py`、`scene_comfy_transactions.py`。
6. `tests/unit/test_scene_clip_records.py`、`test_scene_media_performance.py`、`test_scene_comfy_send_checks.py`、`tests/integration/test_local_video_metrics_flow.py` 及设计列出的恢复测试。

具体第一步：在 `tests/unit/test_scene_validation_pass.py` 写“已有强lease的同Artifact在同scope内strict一次、外层已有native pass时guard自己的fresh pass在返回前flush、reuse=False跨窗口传播”的失败用例，确认新接口缺失/行为不满足后再实现 `scene_validation_pass.py`。无需重新设计scope或另选缓存方案。实施仍须显式启动LVA-02，READY不是已开始。

## Risks

- native lease覆盖有限；无可靠证明时保持strict，不能扩大immutable roots或保护可写输出来满足命中率。
- 目录变化必须在实际socket写/证据落盘之前被guard自己的退出检查捕获；外层capture失败不得被局部fallback隐藏。
- 默认fixture收益可能远小于人工放大样本；采样仍是GPU主要耗时，不能承诺整片倍数。
- 已知 `tests/unit/test_scene_media_performance.py::test_owned_service_cache_identity_rejects_pid_reuse` fixture缺 `process_identity`；按设计具名排除/记录，不改无关生产实现绕过。
- 工作区保留用户 `reference_image_records.py`、`test_cold_admission_performance.py` 及既有cold-admission报告改动。不得reset/clean/整体暂存，不恢复旧生产、删除原锁、调用付费API或重发unknown。
