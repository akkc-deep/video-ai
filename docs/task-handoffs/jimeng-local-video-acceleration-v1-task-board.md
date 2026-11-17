# Jimeng Local Video Acceleration v1 Project Task Board

## Project

- **Project ID:** `jimeng-local-video-acceleration-v1`，任务前缀 `LVA`。
- **Goal:** 提高质量验收通过的本地有效视频秒数 / 从选图完成到本地成片的墙钟时间；优先消除没有新增保护作用的重复全局校验，断点恢复正确性不得退化。
- **Scope:** 适用分支 `v1`、生产策略 `paragraph_jimeng_v1`，从即梦图片已经人工选定开始，覆盖本地 ComfyUI / Wan2.2 视频生成、片段处理、超分、合成和交付检查。保留原始输入、选中图片、全部视频帧、连续性及人工审核机制、最终 1080P 输出要求。禁止修改 `src/video_ai/adapters/jimeng.py`、`src/video_ai/runtime/jimeng_candidates.py`、`src/video_ai/runtime/jimeng_reference_candidates.py` 和任何即梦提交、候选、下载、选图协议；上游问题仅记未来事项。
- **Completion condition:** 原六项任务分别交付其范围内的代码、针对性单元/集成验证、benchmark JSON 和 Markdown 报告，其完成记录保留。LVA-07 各子任务按自身边界交付审查、CPU证据、投入决定、实现或真实实验，不要求只读审查先写产品代码或跑GPU。真实实验按固定输入完成可复现对照，区分局部、端到端、正常生成和恢复结果，保留质量、失败和未验证限制。加速实验未通过时保留原质量路径及明确的拒绝推广结论，不以软件测试代替真实质量验收；需要的真实实验未获授权或未执行时，不登记对应任务已完成。
- **Overall design:** `docs/task-designs/jimeng-local-video-acceleration-v1.md`，原六项一一对应第 8 节 A–F；后续 LVA-07 专项按其已有设计拆为六个执行任务，不扩展到生产迁移。
- **Existing results:** `docs/task-designs/video-generation-performance-results.md` 记录已完成的能力缓存、轮询、提帧/PNG 证明批处理、媒体复制批次校验、合成解码合并等。先对照现状，不能重复实施或把历史收益登记为本板新收益。
- **Authorization evidence:** 2026-11-15 用户要求“docs\task-designs\jimeng-local-video-acceleration-v1.md 按照这个设计拆分任务”。本次只授权任务拆分和建板；真实 GPU 推理、付费 API、恢复暂停生产须另有明确授权。
- **Subsequent experiment authorization:** 2026-11-15 用户在知悉三组选材、新实验run冷1/热3和人工质量确认要求后明确回复“同意，按这个做吧”。授权自行挑选已选素材及新的本地GPU实验；未授权付费调用或恢复旧生产，不代表已经人工接受新视频质量。

- **Original six-task state:** `COMPLETED`。Order6 LVA-06于 `2026-11-16T19:23:23.328032+00:00` 完成真实矩阵、全部质量与原ID恢复证据收尾；原六项既定任务均已完成。结果为保持原质量默认并明确不推广未通过候选，不是恢复暂停生产或证明全片加速。
- **LVA-07 split evidence (2026-11-17):** 用户要求完整读取三份设计/任务文档后拆分，先做环境兼容审查，不急于安装，先确认此前失败的两组 LoRA 能否被 Wrapper 正确处理，再决定 GPU 投入。原 LVA-07 的 NOT_STARTED 聚合行由 LVA-07-01～06 执行行取代，LVA-07 保留为专项总称而非另一个待执行任务；这是范围拆分，不是完成/启动状态迁移。LVA-07-01 初始化 READY，其余 NOT_STARTED，Handoff 均 None。仅拆分与设计已交付，未执行环境审查、安装或新 GPU；原六项状态/历史证据不变。

## Workflow

- **Execution:** Order 是默认实施顺序，串行安排由用户负责；建板不启动实现、不派发执行，也不改变其他项目任务状态。
- **Next-task selection:** 当前任务完成后，选择 Order 更大且未完成的最小 Order 任务。Dependencies 仅列直接消费的任务输入，不代替顺序。
- **Successor preparation:** 先记录当前任务完成证据，再完成并关联所选后继的详细设计，随后写 next-task 交接并准备为 READY；后继设计或前提不足，不回滚前项完成状态，不改后继状态及 Handoff，不写部分交接。
- **Allowed transitions:** `NOT_STARTED -> READY`、`READY -> IN_PROGRESS`、`IN_PROGRESS -> PAUSED`、`PAUSED -> IN_PROGRESS`、`READY -> BLOCKED`、`IN_PROGRESS -> BLOCKED`、`BLOCKED -> READY`、`IN_PROGRESS -> COMPLETED`。
- **Initialization:** `LVA-01` 为 `READY`，其余为 `NOT_STARTED`，Handoff 均为 `None`；READY 不表示已开始实现。各任务设计引用均先记 `None`，总体方案作为共同来源，不充当每项已完成的详细实施设计。
- **Design documents:** 开始实施前完成任务专项设计，并回填确切路径；后续交接使用同一路径。专项设计应明确接口、输入输出、失败与恢复规则、针对性验证及真实实验授权边界。
- **Validation budget:** 遵守根目录 `AGENTS.md`“生成视频的过程中不要过度校验”。先证明重复调用是否有独立拦截价值，再合并/删除；稳定阶段使用受保护的内容证明，缺少强保护时严格回退。必要提交、证据持久化、晋升和发布边界保留；回归使用隔离 fixture，不在正常生成中增加重复全库扫描。
- **Experiment boundary:** 既有 run 只读；真实推理只在明确允许的新实验 run 运行。固定已选图片、prompt、seed、帧数和尺寸；不自动恢复暂停生产、不重发未知任务、不把冷/热启动或局部微基准混算为整片收益。
- **Evidence:** 每项记录变更、验证命令/结果、输入和工具身份及 JSON/Markdown 报告确切路径；未运行项明确记未验证。后续产物尚未建立路径时不得伪造引用。完成证据写入对应任务详情后才转为 COMPLETED。

## Tasks

| Order | Task ID | Title | Status | Dependencies | Design document | Handoff |
|---:|---|---|---|---|---|---|
| 1 | LVA-01 | P0 / A：本地基线、耗时观测与校验调用台账 | COMPLETED | None | docs/task-designs/LVA-01-design.md | None |
| 2 | LVA-02 | P0 / B：重复校验精简与断点恢复正确性 | COMPLETED | LVA-01 | docs/task-designs/LVA-02-design.md | docs/task-handoffs/LVA-02-handoff.md |
| 3 | LVA-03 | P1 / C：Comfy 模型生命周期与依赖感知准备重叠 | COMPLETED | LVA-01, LVA-02 | docs/task-designs/LVA-03-design.md | docs/task-handoffs/LVA-03-handoff.md |
| 4 | LVA-04 | P1 实验 / D：独立 Wan 高速配置与质量验证 | COMPLETED | LVA-01, LVA-02 | docs/task-designs/LVA-04-design.md | docs/task-handoffs/LVA-04-handoff.md |
| 5 | LVA-05 | P2 / E：超分模型复用、受限流水线与编码实验 | COMPLETED | LVA-01, LVA-02, LVA-03 | docs/task-designs/LVA-05-design.md | docs/task-handoffs/LVA-05-handoff.md |
| 6 | LVA-06 | P2 / F：端到端复测、收益归因与性能回归 | COMPLETED | LVA-01, LVA-02, LVA-03, LVA-04, LVA-05 | docs/task-designs/LVA-06-design.md | docs/task-handoffs/LVA-06-handoff.md |
| 7 | LVA-07-01 | 环境与 Wrapper 加载路径只读审查 | COMPLETED | LVA-04 | docs/task-designs/LVA-07-01-design.md | None |
| 8 | LVA-07-02 | 两专家 mixed-delta LoRA CPU 兼容性验证 | NOT_STARTED | LVA-07-01, LVA-04 | None | None |
| 9 | LVA-07-03 | 是否投入的决策与具体环境/GPU资源清单 | NOT_STARTED | LVA-07-01, LVA-07-02, LVA-01 | None | None |
| 10 | LVA-07-04 | 隔离 worker、workflow 与恢复 harness | NOT_STARTED | LVA-07-03, LVA-07-02, LVA-02 | None | None |
| 11 | LVA-07-05 | 最小低运动真实 GPU 对照与人工质量门槛 | NOT_STARTED | LVA-07-04, LVA-07-03, LVA-01 | None | None |
| 12 | LVA-07-06 | 条件扩展冷/热及父子矩阵与实验结论 | NOT_STARTED | LVA-07-05, LVA-07-04, LVA-01 | None | None |

## Task Details

以下 Sources 均为仓库根目录下的相对路径，按所列顺序阅读；“本板任务交付”在前项完成后以其实际证据为准，不表示文件已存在。各项在初始化时均无实现或完成证据。每项详细设计需沿用总体方案全文的共同约束。LVA-07 是原六项完成后的独立后续实验扩展。

### LVA-01

- **Goal:** 建立可复现本地性能基线，识别 GPU、服务、媒体处理和校验的实际瓶颈，为每项校验去留提供证据。
- **Scope:** 对应设计第 3、4.1 节。新增不含密钥、提示词原文的结构化阶段耗时；覆盖 Comfy 启停/冷热点装载/卸载、峰值显存和 GPU 利用率，Wan 图像准备/文本编码/high 与 low 采样/VAE/编码，片段 probe/trim/末帧、单列父片接受等待，超分推理/批次/I/O/证明，合成编码/音轨字幕/交付。审计指定全局、局部、HTTP 和公共校验，区分正常生成与恢复，记录每调用的文件数、字节数、哈希及完整解码次数、耗时、独立拦截价值。准备低运动、高运动、父子续接三类新实验 fixture 与对照报告；不在本项实施批量删校验或切换快速模型。
- **Acceptance:** ① 有可定位调用台账，能区分仍存在的热点与 2026-11-05 已优化项目。② 计时从选图完成开始，汇总本地片段 P50/P95、每可用视频秒成本、失败/重做率，人工接受等待单列，日志不泄露敏感内容。③ 三类 fixture 固定输入，获授权后执行冷启动 1 次、热运行至少 3 次，JSON/Markdown 记录环境、输入身份、样本与缺失项；真实 GPU 未运行不能登记本机基线完成。④ 离线观测验证不改变生成参数、持久化任务身份和旧 run 内容；不外推整片加速倍数。
- **Dependencies:** `None`；已完成优化报告是历史输入，不另建任务。
- **Sources:** ① `docs/task-designs/jimeng-local-video-acceleration-v1.md`；② `docs/task-designs/video-generation-performance-results.md`；③ `src/video_ai/runtime/scene_clip_records.py`；④ `src/video_ai/runtime/production_scene_clips.py`；⑤ `src/video_ai/runtime/production_scene_upscale.py`；⑥ `src/video_ai/runtime/production_scene_composition.py`；⑦ `src/video_ai/runtime/scene_comfy_transactions.py`；⑧ `src/video_ai/runtime/verification.py`；⑨ `src/video_ai/runtime/scene_revision_records.py`；⑩ `scripts/benchmark_scene_extraction.py`、`scripts/benchmark_scene_frame_copy.py`。
- **First action:** 对照已完成报告，梳理上述运行模块中正常生成与恢复的校验入口及计时点，形成本项详细设计的调用清单。
- **State evidence:** 2026-11-15 用户明确要求“完成任务 LVA-01”；读完总体设计与现状后关联 `docs/task-designs/LVA-01-design.md`，执行 `READY -> IN_PROGRESS`。无前驱交接。当时真实GPU基线尚未执行；后续执行与剩余验收见下文。
- **Partial delivery:** `src/video_ai/runtime/local_video_metrics.py`、`scripts/benchmark_local_video.py`、`docs/task-designs/LVA-01-validation-ledger.md`；实测汇总 `docs/task-designs/LVA-01-results.md`、`docs/task-designs/LVA-01-results.json`。正常/恢复隔离验证及 HTTP 定向测试27通过（120.07s）；既有媒体性能22通过、1项已知 fixture 错误单独复现并在报告具名记录。FFmpeg开关对照各4次产物字节一致；追踪扰动2.524/2.688倍，只作调用诊断。全调用聚合无观测错误；正常原始事件细节超限明确披露。未改生产生成代码、即梦协议和原run，未触碰用户原有冷准入改动。
- **Experiment preparation:** 已新增 `src/video_ai/runtime/local_comfy_metrics.py`、`scripts/observe_local_comfy.py` 供新的独立诊断服务采集节点/模型方法墙钟和设备级GPU采样。已用于真实实验；针对性实验/观测/后处理测试最近17通过（2.27s），后处理集成为3帧合成fixture，并非真实神经超分验收。未为本次统计刷新重复运行测试。
- **Authorized execution:** 新owned实验完成low/parent/high/child各冷1热3，共16次原生；1424帧真实全帧超分、12份1080P技术通过，组内内容一致，技术失败/重做0。父片372帧只超分一次，子片308帧复用原父帧形成4份170帧最终链。用户已接受全部原生/连续性及三类最终成片；最后父子确认已绑定四份相同输出。全部8个owned服务关闭：初始low仅保留checkpoint，后续7个均合作退出exit0/finalized=true。确切原ID、阶段数据、审核及恢复证据见 `docs/task-designs/LVA-01-gpu-results.json` / `.md`；原生产未恢复、无付费调用。
- **Remaining acceptance:** None。最终用户“没问题，继续吧”于2026-11-15T09:50:34.724Z确认完整父子1080P，所有本项验收已建立；连续整片吞吐保留为LVA-06范围，不外推本项加速倍数。

- **Completion evidence:** 2026-11-15执行 `IN_PROGRESS -> COMPLETED`。`docs/task-designs/LVA-01-completion.json`映射全部验收：可定位台账及原始哈希/解码计数；历史主链27通过、新观测/后处理17通过、既有媒体22通过及1项无关fixture错误明确记录；三类固定素材各冷1热3（父/子分阶段共16原生），1424帧真实超分、12份1080P技术/人工质量全部接受；选材声明T0和交付/审核时间、可用秒成本及0失败/0重做见时间证据。当前最终候选SHA已核对；不为收尾重复生成/全库校验。所有owned服务关闭，原生产/即梦协议/用户已有冷准入增量保持。

### LVA-02

- **Goal:** 删除或复用没有新增保护价值的重复计算，降低验证开销，同时保证恢复不重复生成已完成视频/超分帧、不盲目重发未知请求。
- **Scope:** 对应第 4.2–4.4 节及第 5.1 节。按 LVA-01 台账分离首次准入、稳定阶段、单片段和必要边界；优先处理重复 `verify_global`、模型 stamp、相同媒体重复完整探测、逐帧共同依赖扫描和合成来源检查。仅对内容身份、工具/规则身份一致且处于有效保护作用域的结果复用。审查 `_technical` 的 `generated_producer`/`source_producer`，若仍有独立重复则在同事务传递已验证 `source_info`；历史优化已覆盖的路径仅验证不重做。不改持久化结果格式或旧记录兼容性，不动高速采样和服务调度。
- **Acceptance:** ① 每项删除/合并有调用台账依据与前后调用数、真实媒体墙钟对照；保留输出晋升、外部提交和证据落盘所需的独立检查。② 新生成复用探测，恢复时 producer 未运行仍执行完整 `inspect_video`；trim 核验、原媒体身份、SHA/帧数/PTS/证据等价。③ 进程重启清空进程内证明，从 durable intent → accepted ID → 状态 → 产物 → 最终提交重建可信链；已有媒体先验真再复用，未知提交仅恢复原请求。④ 覆盖提交前、发送后未记 ID、执行中、成功未验收、晋升前后、超分 N 帧后、最终合成中断；服务重启重审 queue/history，不承诺恢复未持久化的扩散中间步。⑤ 覆盖同大小替换/改回 mtime、符号链接与文件身份、模型/父片变化、锁失效、重复/冲突 accepted、未知状态、新旧格式混合及父片观察/尾帧/子片依赖重绑；异常仍拒绝，弱保护平台严格回退。
- **Dependencies:** `LVA-01` 的基线、正常/恢复调用台账和独立拦截价值分析。
- **Sources:** ① 总体设计第 4、5.1 节；② 本板 LVA-01 的实际交付与本项详细设计；③ `src/video_ai/runtime/scene_clip_records.py`；④ `src/video_ai/runtime/production_scene_clips.py`；⑤ `src/video_ai/runtime/production_scene_upscale.py`；⑥ `src/video_ai/runtime/production_scene_composition.py`；⑦ `src/video_ai/runtime/scene_comfy_transactions.py`；⑧ `src/video_ai/runtime/verification.py`、`src/video_ai/runtime/scene_revision_records.py`；⑨ `tests/unit/test_scene_clip_records.py`、`tests/unit/test_scene_comfy_transactions.py`、`tests/unit/test_scene_comfy_send_checks.py`；⑩ `tests/integration/test_production_comfy_recovery.py`。
- **First action:** 按已完成专项设计在 `tests/unit/test_scene_validation_pass.py` 建立受保护Artifact复用、fresh read-pass退出及strict覆盖的失败用例，再实现新helper；不用再次选择方案。
- **State evidence:** 2026-11-15 初始化为 `NOT_STARTED`；没有本板认可的精简或恢复验证结果。

- **Start evidence:** 2026-11-15 用户明确要求“完成任务- LVA-02”；完整读取本项设计与交接，执行 `READY -> IN_PROGRESS`。实施计划 `docs/task-designs/LVA-02-plan.md`；保留旧生产暂停及用户已有改动。

- **Preparation evidence:** LVA-01完成后按Order选择本项，观察NOT_STARTED；已完成并关联 `docs/task-designs/LVA-02-design.md`，独立builder提出的fresh退出、CaptureLimit外层证明及strict对照三项已明确解决，复核“Nothing important left before planning”。写入并关联 `docs/task-handoffs/LVA-02-handoff.md` 后执行 `NOT_STARTED -> READY`。未启动实施、未运行LVA-02测试或benchmark，无生产代码修改。

- **Completion evidence:** 2026-11-15 用户“完成任务- LVA-02”授权的实现/测量已交付，执行 `IN_PROGRESS -> COMPLETED`。`docs/task-designs/LVA-02-results.json` / `.md` 与 `LVA-02-plan.md` 记录：214定向测试通过、5真实媒体/超分恢复通过、22媒体性能通过（1项既知fixture排除）、原恢复64通过/6失败/6排除及补充50通过/3旧路径fixture失败均具名披露。四次strict/candidate正常严格工作12876→8982，但墙钟18.908746→20.756011秒、实际SHA/解码不减，依设计无收益分支保持生产默认strict，候选仅离线显式启用；强保护放大128→32、目录4→2，弱保护原样。原ID/全部帧/实际PTS/SHA及无重复POST/prefix恢复证据齐备，不认领生产/GPU/整片加速。无持久化schema、即梦、底层verification或用户冷准入修改；原生产保持暂停。既有legacy模型路径、无效run入口、continuity路径及output reclaim清理问题未越界修复，详细限制见报告。

### LVA-03

- **Completion evidence (2026-11-16):** 用户已明确接受子片及连续性并授权实际同字节候选绑定；32/32原生样本技术与质量接受（四类×两侧×冷1热3），新父片真实末帧和人工门槛保持。88项定向单元通过（6.85s），修正后2项真实媒体阶段测试及此前5项恢复测试通过；四对离线及所有GPU方法/设备/实际帧PTS证据完整引用 `docs/task-designs/LVA-03-results.json` / `.md`。各对应trial方法次数相同，热P50候选观察差：低+2.58%、高+1.20%、父+0.015%、子+0.003%，未证明可重复墙钟收益，明确否决默认采用，保持串行/strict；物理装载次数未测得。正常28POST直接计数+首组4原回执分列，8阶段完成恢复HTTP/媒体调用均0。8测量owned阶段+1提交前失败setup均已关闭，8189无监听；该setup无intent/POST/子片推理，未重做完成媒体。遗留全库缺陷、模型SHA复用、首组缺直接计数和已加载buffered版本/最终无缓冲资源修正的证据边界如实披露。完整读完专项设计后执行 IN_PROGRESS -> COMPLETED；原生产未恢复，旧run未写、未付费、未commit/push。

- **Start evidence:** 2026-11-15 用户要求“完成任务LVA-03”；读完设计/交接后 READY -> IN_PROGRESS。计划 `docs/task-designs/LVA-03-plan.md`。用户另明确回复“授权运行本次本地 GPU 对照”：沿用LVA-01固定素材和原质量，仅新建LVA-03实验目录；原生产暂停、父子人工审核保持。
- **Implementation evidence (in progress):** `scene_stage_preparation.py` 单worker/单槽只读候选默认关闭、阶段计量及已有handle身份核验已接线；原 `_input`/receipt/网络/strict不变。86定向单元通过；修正后2项真实阶段正常/恢复通过，原组合中5项既有恢复通过。Windows ctime误判已RED→GREEN修复；原离线回退数据保留，修正候选四对另采。独立审查4项GPU脚本问题以回归修正。结果 `docs/task-designs/LVA-03-results.json` / `.md`，GPU状态 `docs/task-designs/LVA-03-gpu-run-state.json`。真实对照与人工质量仍进行中，未登记完成、未准备后继或恢复旧生产。
- **Current review gate (2026-11-16):** 低/高/父片baseline/candidate共6阶段24次原生技术完成，6个owned服务均正常关闭、8189无监听，已有probe/frames整理实际93帧/PTS且未再解码。低/高/父片热P50候选观察差分别+2.58%/+1.20%/+0.015%，对应模型方法次数相同，未证明可重复墙钟收益，候选继续默认关闭；物理装载次数未测得。用户已接受低运动基线4份、高运动基线及同字节候选8份，共12份。低运动候选4份同字节绑定及父片基线观看/同字节候选授权仍待回复；子片0次，不预读未接受父片未来尾帧。继续入口、确切child源和剩余工作见GPU状态与结果报告。任务保持IN_PROGRESS，未准备LVA-04。
- **Review resolved / child execution:** 用户随后回复“没问题”，对应两项待确认已落实12份实际同字节接受记录，前24份均接受。新子片阶段使用已接受新父片真实末帧，保留81生成/77贡献帧。提交前一次准备目录约定错误未产生intent/POST，owned服务正常关闭；RED→GREEN修正新driver与原helper衔接及parent-bound恢复后88项定向单元通过，实际配对使用 `child-20261116-02` 新root。子片两侧冷1/热3串行运行，尚需子片/连续性质量结论；任务仍IN_PROGRESS。

- **Goal:** 减少同一授权生成阶段的重复模型装载与 GPU 空转，在连续性依赖不变的前提下重叠 CPU 准备和 GPU 工作。
- **Scope:** 对应第 5.2、5.3 节。实测 owned Comfy 进程的阶段归属和重复装载；在同一阶段复用模型驻留，有限预准备独立场景的图像适配、图谱和磁盘输入。明确资源预算和协调线程职责。单连续链串行、单 GPU 不盲目并发 Wan 采样；不跨人工审核无限驻留，不让 worker 并行持久化不可变证据。
- **Acceptance:** ① 冷/热装载次数、准备/采样时间及 GPU 空闲有与 LVA-01 可比的 JSON/Markdown。② 父片尾帧与人工观察依赖保持；未满足依赖的子片不提交，所有证据写入仍在持锁协调线程。③ 资源预算、停止/退出和恢复有针对性验证；owned 服务归属及阶段结束释放正确，旧 accepted/unknown 仍恢复原任务。④ 真实授权实验验证减少装载/空转的程度和限制，不将仅离线调度测试记为真实吞吐通过。
- **Dependencies:** `LVA-01` 的分阶段基线；`LVA-02` 的保护作用域、失效和恢复约束。
- **Sources:** ① 总体设计第 3、4.3、5.2、5.3 节；② 本板 LVA-01、LVA-02 的实际交付；③ `src/video_ai/runtime/production_comfy.py`；④ `src/video_ai/runtime/production_scene_clips.py`；⑤ `src/video_ai/runtime/scene_comfy_transactions.py`；⑥ `src/video_ai/adapters/scene_comfy.py`、`src/video_ai/adapters/comfyui.py`；⑦ `src/video_ai/planning/scene_clip_continuation.py`；⑧ `tests/integration/test_comfy_tracking.py`、`tests/integration/test_production_comfy_recovery.py`。
- **First action:** 按 `docs/task-designs/LVA-03-design.md`，在 `tests/unit/test_scene_stage_preparation.py` 建立单worker/单槽/预算、parent拒绝和已有handle退出/PID复用拒绝的失败用例，再实现规定的数据对象与只读pool。
- **State evidence:** 2026-11-15 初始化为 `NOT_STARTED`；未验证驻留或调度收益。

- **Preparation evidence:** LVA-02按实测无收益分支完成后，按Order选择本项，观察NOT_STARTED。已完成并关联 `docs/task-designs/LVA-03-design.md`，写入 `docs/task-handoffs/LVA-03-handoff.md` 后执行 `NOT_STARTED -> READY`。直接输入保持LVA-01原质量及LVA-02默认strict；现有一次启动/关闭不重做，单worker只读准备默认关闭、实际GPU采用需授权/实测。不启动实施、不运行GPU、不认领吞吐收益。

### LVA-04

- **Completion evidence (2026-11-16):** 用户“同意，继续吧”授权固定下载/新GPU后，双LoRA完整验真。真实quality低运动cold1/warm3共4份93帧技术通过，热墙钟P50=470.598s，保留视频/末帧均与既有基线同字节但不虚造新人工接受。第1次fast原请求 `66cd1918-4276-4ee6-ac84-8d6235b70ba3` 在LVA04LoraPair原子准入拒绝混合diff/diff_b/diff_m，未进采样、0fast视频；高权重41个diff_m未加载，严格普通rank64适配无法完整接纳该recipe。按设计停止余下矩阵，不忽略权重或换引擎。distill否决，Sage/cache/compile/combination明确unsupported/rejected，fast人工质量无产物不可评，非fast validated、无提速结论、默认quality不变。两owned服务code0退出且metrics finalized；真实完成/失败ID恢复0HTTP/0producer，79定向通过（5.00s）。证据 `docs/task-designs/LVA-04-completion.json`、`LVA-04-gpu-results.json`、`LVA-04-native-rejection-evidence.json` 及结果报告。作为实际不兼容的否决实验结论执行IN_PROGRESS -> COMPLETED，未将候选记为可用高速模式；原生产继续暂停。后文实现/离线记录为授权前历史快照。
- **Start evidence (2026-11-16):** 用户明确要求“完成任务LVA-04”；已全文读取关联设计及交接，READY -> IN_PROGRESS。按 `docs/task-designs/LVA-04-plan.md` 先实现与离线验证，再准备本项下载/GPU授权的具体manifest和命令；尚无真实fast质量结论。
- **Implementation/offline evidence (2026-11-16):** 独立fast三件套、不可变profile、原生双LoRA原子准入/sigma/有限值检查、新client的原intent恢复/完整产物与同profile父片绑定已实现。79定向测试通过（4.90s），fake-HTTP离线通过，独立审查3项身份缺口均RED→GREEN修正；原quality workflow/mapping SHA不变。结果 `docs/task-designs/LVA-04-results.json` / `.md`，审查 `LVA-04-review.md`。固定manifest `docs/task-designs/LVA-04-gpu-manifest.json` 与 `LVA-04-gpu-commands.md` 已备妥：双LoRA共1,374,118,048 bytes，最多32次串行新原生对照，父片验收后才启动同profile子链。当前未下载/安装/执行新GPU，Sage/Triton缺失和未核验cache明确拒绝；真实兼容性、媒体/性能及人工质量未验证，因此保留IN_PROGRESS、未准备LVA-05。下一步按设计取得这份具体下载/GPU授权；原生产继续暂停。
- **Goal:** 建立独立、可回退且经过实测的 Wan 高速实验模式，保持原 40 步质量路径和旧任务生成身份。
- **Scope:** 对应第 6 节。新增计划产物 `workflows/wan22_i2v_14b_fast_api.json` 及配套 mapping/provenance，原 `wan22_i2v_14b_api.json` 字节不变。严格逐项实验：匹配 Wan2.2 I2V 14B high/low 双专家的蒸馏/LightX2V LoRA → 本机 SageAttention → 双专家兼容缓存 → `torch.compile`/驻留与组合。定义 `quality` 和 `fast_experimental`，将模型/LoRA SHA、workflow hash、节点/Comfy 版本、backend/cache、步数/CFG 纳入新任务冻结与恢复证据。不直接开启原图未验证的 4 步开关，不改旧 pending/accepted/unknown 或重新 POST。
- **Acceptance:** ① 独立图、mapping、来源身份及路径/强度/参数可复现，原图哈希保持不变，实验配置不自动成为默认。② Windows RTX 5090D V2 的具体 CUDA/PyTorch/Comfy 组合有单变量记录，编译冷成本单列。③ 黑帧/NaN、闪烁、角色/纹理、颜色、运动、尾帧接缝、完整帧数/PTS、显存和失败重试均有技术及质量结论。④ 新模式身份漂移拒绝，旧任务恢复不变；质量显著下降不得自动推广。⑤ JSON/Markdown 明确每项支持、失败、未验证或拒绝启用结论；没有真实实验不能宣称高速模式验证通过。
- **Dependencies:** `LVA-01` 的质量/耗时基线和 fixture；`LVA-02` 的冻结证明、必要边界和恢复规则。LVA-03 仅决定默认顺序，不是本项直接输入。
- **Sources:** ① 总体设计第 1、4.3、6 节；② 本板 LVA-01、LVA-02 的实际交付；③ `workflows/wan22_i2v_14b_api.json`、`workflows/wan22_i2v_14b_api.mapping.json`；④ `src/video_ai/planning/scene_clip_continuation.py`；⑤ `src/video_ai/runtime/scene_clip_records.py`；⑥ `src/video_ai/runtime/production_scene_clips.py`；⑦ `src/video_ai/adapters/scene_comfy.py`；⑧ `src/video_ai/runtime/scene_comfy_transactions.py`。LoRA/节点的正式来源在研究确认后写入专项设计，不预造引用。
- **First action:** 按 `docs/task-designs/LVA-04-design.md` 在 `tests/unit/test_wan_fast_profiles.py` 写缺LoRA/错SHA/high-low调换、quality原图SHA不变、新profile漂移拒绝的RED用例，然后实现规定的不可变profile与freeze/verify接口；不先下载、打开4步开关或重新设计。
- **State evidence:** 2026-11-15 初始化为 `NOT_STARTED`；不存在本板认可的蒸馏、attention、缓存或编译实测结论。
- **Preparation evidence (2026-11-16):** LVA-03完成及32份实际接受结果先登记后，按Order=4选择本项，观察NOT_STARTED。专项设计 `docs/task-designs/LVA-04-design.md` 已完整完成并关联，官方来源研究 `LVA-04-source-research.json` 固定1022 I2V A14B双LoRA版本/bytes/SHA及参考sigma，明确官方Wrapper图不代表本机native兼容、原4步开关没有LoRA、不允许静默回退。直接输入LVA-01原质量及LVA-02严格恢复约束无冲突。写入并关联 `docs/task-handoffs/LVA-04-handoff.md` 后执行 NOT_STARTED -> READY。当前无loras目录、sageattention/triton，缓存/编译未验证按设计拒绝；只有研究和设计，没有下载权重、安装包、启动实现或LVA-04 GPU。新实验授权必须在具体工作准备好后另行取得，原生产仍暂停。

### LVA-05

- **Completion evidence:** 用户“同意”授权具体GPU清单后，完成12个独立owned测量阶段（四类×serial/prefetch/writeback，各冷1热3）、48完整样本、4272唯一POST/帧；全序列1920×1080 RGB均与已真实接受来源相同。低/高/父/子批次serial为501.412/521.555/503.410/410.453s；prefetch观察差+0.16/-0.59/-0.26/+0.62%，writeback +0.34/-0.54/-1.56/-0.19%。父片写回有局部改善，其它配对/素材方向不一，未建立稳定通用收益，否决默认采用、保留serial；组合未执行、未验证且未越过质量门槛。实际独立NVENC对照0.650898s vs新libx264 1.083664s，但93/93帧RGB不同，按rejected_pixel_contract拒绝，后11组未执行；帧/PTS/尺寸/fps/颜色一致，新软件视频与原已接受视频逐字节相同。1408预读/1424写回全成功，实测payload最大2634989 bytes；12实际完成批次恢复0HTTP/0媒体命令/0GPU。98定向通过（9.51s），5旧fixture路径初始化失败具名保留；7项独立审查/真实启动缺口已回归修正。12测量服务均exit0/finalized，原PID均不存活且8189无监听；另2次失败setup无推理intent、1个import阶段子进程已关闭。物理权重搬运未测，不把loader=1当新增收益；保留原真实来源接受、无新观看/人工决定或quality-accepted，不推广候选、不报可用成本。结果 `docs/task-designs/LVA-05-results.json` / `.md`、`LVA-05-gpu-results.json`、`LVA-05-gpu-recovery.json`、`LVA-05-completion.json`；完整读完专项设计，按明确否决分支执行 IN_PROGRESS -> COMPLETED。原生产暂停，旧schema/intent/accepted/原图未变、无下载/新Wan/commit/push。下方授权及离线进展为历史快照。
- **GPU authorization evidence:** 用户对已具体呈现的本地GPU清单（最多5696逐帧超分＋12组编码对照）回复“同意”。授权绑定 `LVA-05-experiment-manifest.json` SHA `9cef6989ed1133e41e8ed5151a7f04414c7a629f39c510a26fb52e4bf658cd96`；开始串行/单因子真实测量，组合仍保留单因子真实技术与人工验收门槛。状态保持IN_PROGRESS，原生产暂停。
- **Start evidence (2026-11-16):** 用户明确要求“完成任务LVA-05”；已完整读取关联设计、交接和直接来源，执行 READY -> IN_PROGRESS，保留交接为入口。计划 `docs/task-designs/LVA-05-plan.md`。先RED/离线实现再准备具体GPU清单；未启动本项GPU、未恢复生产。
- **Implementation/offline evidence (2026-11-16):** 独立单预读/单private写回（64+32MiB）、原ID恢复/完成0HTTP、全帧RGB、固定编码对照及pinned owned生命周期已实现。独立审查5项I/O/启动/关闭问题均RED→GREEN修正，含真实CPU进程Job关闭测试；最终96定向通过（9.36s）。四因子×四重复CPU/fake-HTTP共48帧及真实1080P软件编码离线通过，NVENC仅编码器/flags存在，驱动/GPU/质量未验证。原超分集成5项在既有隔离夹具path-policy初始化失败，具名披露不扩修。结果 `docs/task-designs/LVA-05-results.json` / `.md`，清单 `LVA-05-experiment-manifest.json`（SHA `9cef6989ed1133e41e8ed5151a7f04414c7a629f39c510a26fb52e4bf658cd96`）/`LVA-05-gpu-commands.md` 已具体准备：最多16串行owned阶段/5696逐帧超分请求，另12组libx264/NVENC配对；0新Wan/下载，组合需单因子真实验收。待本项具体GPU授权及真实技术/性能/人工质量证据；保留IN_PROGRESS，不准备LVA-06、不恢复生产，不宣称提速。
- **Preparation evidence (2026-11-16):** LVA-04实际不兼容的否决结论先登记COMPLETED后，按Order=5选取本项，观察NOT_STARTED；已完成并关联 `docs/task-designs/LVA-05-design.md`。LVA-01已接受超分/合成来源、LVA-02 strict/原ID恢复、LVA-03 owned阶段/资源与协调证据边界无冲突。写入并关联 `docs/task-handoffs/LVA-05-handoff.md` 后执行NOT_STARTED -> READY。第一动作已明确为RED测试及有界接口实施；尚未实施、未跑本项GPU，原生产不恢复。
- **Goal:** 提高超分与合成的本地吞吐，在保留全部帧和可追溯恢复证据的前提下降低模型重载、I/O 等待与峰值存储。
- **Scope:** 对应第 7 节。测量 RealESRGAN 单帧运行的常驻、读写与 GPU 空闲，先实施同阶段模型复用和受限预取/写回队列；禁止多个实例争抢显存。对同源/参数/工具身份且完整校验的输出，仅在同运行事务内安全复用。研究 NVENC 等硬件编码为实验可选项；与全像素一致性证明冲突则保持原 FFmpeg。避免重复实施既有提帧/合成解码优化，不删帧、不降最终输出要求。
- **Acceptance:** ① 单帧 GPU 时间、批次吞吐、I/O/校验开销、模型装载次数、GPU 空闲及峰值存储有前后对照。② 预取/写回预算受控，证据与恢复状态仍可追溯；中断后验真并复用已完成帧，不重做，不改变不可变写入规则。③ 硬件编码对视觉质量、像素/PTS/帧数/颜色元数据和现有验收契约给出实验结论；不兼容时明确拒绝替换且原编码仍可用。④ 有针对性单元/集成及真实授权媒体实验的 JSON/Markdown，区分超分与编码各自收益和未验证项。
- **Dependencies:** `LVA-01` 的超分/合成基线；`LVA-02` 的事务证明与恢复规则；`LVA-03` 的 owned 阶段生命周期、资源预算和协调写入边界。
- **Sources:** ① 总体设计第 4.3、7 节；② `docs/task-designs/video-generation-performance-results.md`；③ 本板 LVA-01、LVA-02、LVA-03 的实际交付；④ `workflows/upscale_api.json`、`workflows/upscale_api.mapping.json`；⑤ `src/video_ai/runtime/production_scene_upscale.py`；⑥ `src/video_ai/runtime/production_scene_composition.py`；⑦ `src/video_ai/runtime/scene_comfy_transactions.py`；⑧ `scripts/benchmark_scene_extraction.py`、`scripts/benchmark_scene_frame_copy.py`。
- **First action:** 按 `docs/task-designs/LVA-05-design.md` 在 `tests/unit/test_upscale_pipeline.py` 写单写回槽反压/完成恢复及96MiB预算、源漂移、worker隔离的RED用例，再实现规定的数据类和有界接口；不先启动GPU或重新设计。
- **State evidence:** 2026-11-15 初始化为 `NOT_STARTED`；未运行本板超分或硬件编码实验。

### LVA-06

- **Completion evidence (2026-11-16T19:23:23.328032+00:00):** 用户“视频没问题”已真实接受最后4份170帧连续1080P成片，7个阶段性group决定和3个最终group决定均绑定当前实际媒体。新鲜只读审计核对16native＋1424frame共1440唯一原ID、12完整1080P/16fps成片、全部帧/RGB/PTS/AV证明和7owned exit0/finalized/原进程退出。三个原根完成恢复均0HTTP/producer/decode/model-start（必要真实性SHA读取非0）；实施77定向通过，代码与授权源身份仍一致，未为统计重做媒体。最终非人工批次包络低/高/链2496.446/2475.110/4470.562s，对应每可用视频秒107.374/106.456/105.190s，均为固定队列观察，baseline/final同profile只一矩阵，不相加trial包络、不报因果倍数或107场景全片吞吐。全部报告及接受/恢复/资源/归因台账 `docs/task-designs/LVA-06-results.json` / `.md`、`LVA-06-gpu-results.json` / `.md`、`LVA-06-evidence-audit.json`、完成记录 `LVA-06-completion.json`。按5项Acceptance实际齐备执行IN_PROGRESS -> COMPLETED。原quality/strict/serial/libx264默认保持，0下载/付费/NVENC/fast，原生产仍暂停。Order=6之后无预定义后继，不造新任务或交接；下方阶段记录为历史。

- **Actual chain delivery / technical matrix complete:** 用户“没问题”接受明确展示的4份170帧父子原生预览及约5.8秒接缝，决定绑定 `chain/reviews/child-continuity-user-decision.json`。同一chain根复用全部native/预览，完成680唯一逐帧超分及4份170帧1080P/16fps原旁白字幕/libx264连续成片，完整RGB/PTS/AV证明通过，4成片逐字节相同；owned exit0/finalized，原PID身份已退出。chain技术wall=6498.514s、人工并集=2027.951s、non-human=4470.562s，累计688POST=8native+680frame，0已知失败/重做。`LVA-06-chain-delivery-results.json` 为当前部分证据。至此全部16Wan/1424超分/12成片技术完成，低/高最终及父子原生/连续性已接受；仅chain最终质量待确认，成本null，任务保持IN_PROGRESS，未宣称项目完成。

- **Actual chain child / continuity preview:** 用户“没问题，继续吧”接受明确展示的4份实际新父片，已绑定 `chain/reviews/parent-user-decision.json`。随后4个child实际新原ID均使用对应新父片的真实末帧与接受SHA，各81生成/77贡献完整技术通过，未重做parent；冷380.536s，热局部P50=377.478s/P95=377.492s（child新进程冷样本不冒充parent热）。owned exit0/finalized且原PID身份已退出；4份170帧native父子预览为精确93+77的无重编码拼接，完整PTS/帧数通过、逐字节相同。4child POST/497GET；本调用含4预览合计12producer/12decode/24probe。`LVA-06-child-native-results.json` 保存全部新父子绑定和预览证明。当前child/连续性等待真实决定，680链超分/4链成片尚未执行；累计16Wan/744超分/8成片，任务IN_PROGRESS。

- **Actual chain parent stage:** 在原已授权chain根完成4新parent实际原ID（cold1/warm3），各93完整生成/保留帧，全技术检查通过；冷480.872s，热局部P50=477.964s/P95=477.981s。4保留视频SHA均 `e2a51e55e702967a3ca88c2a4d1161c7294024560799c21a0970216d2af24e27`，真实末帧SHA均 `606b69269c64164aedec402c3f9e91423cab4fa7e1ee6fc09b60e219bc000c92`；4generated原始SHA各自保留。4POST/629GET，8producer/8decode/16probe；owned exit0/finalized、原PID身份已退出。`LVA-06-parent-native-results.json` 为部分证据。parent真实质量待确认，native_child根尚未创建，不预造父片接受或子片绑定。累计12Wan/744超分/8成片（低/高均已最终接受），任务IN_PROGRESS。

- **High accepted / chain parent start:** 用户“没问题”已真实接受明确展示的4份同字节高运动1080P成片（画面/声音/字幕），绑定 `high/reviews/final-user-decision.json`。原high完成恢复0HTTP/0producer/0decode（必要真实性SHA读取仍执行）；接受23.25秒，non-human2475.110s、每可用秒106.456s，非历史因果收益。`LVA-06-high-completion-state.json` 保存完成/恢复证据。现进入同一已授权chain根，先parent冷1热3；对应实际新父片未接受前不准备/提交child。累计低/高8成片已最终接受，任务仍IN_PROGRESS。

- **Actual high delivery stage:** 用户“没问题”已接受明确展示的4份实际高运动原生视频，绑定 `high/reviews/native-user-decision.json`。同一high根完成372唯一逐帧超分和4份93帧1080P/16fps原旁白字幕/libx264成片，完整RGB/PTS/AV证明保存；4成片SHA均 `cec21ce29f4da3406ba7aefe013efda1a3d2567cfa0e04f33889357621ce8b97`。owned exit0/finalized且原PID身份已退出。high批次wall=3818.370s，实际人工并集=1343.260s，non-human包络=2475.110s；376POST=4native+372frame，0已知失败/重做，最终质量待确认，成本null。结果 `docs/task-designs/LVA-06-high-delivery-results.json`；累计8Wan/744超分/8成片，仅低运动已最终接受，父子未开始，保持IN_PROGRESS。

- **Actual high native stage:** 在原已授权high新根完成4实际原ID（cold1/warm3），各93生成/保留帧，完整技术检查通过；冷472.653s，热局部P50=469.471s/P95=469.606s。4份保留视频SHA均 `7ea297409b2be49252483b861458c30afb665ce3ccd1070cece2cb153e2a36d9`，generated原始SHA各异且保留；当前高运动质量尚未接受。4POST/617GET，8producer/8decode/16probe，owned exit0/finalized且原PID身份已退出。结果 `docs/task-designs/LVA-06-high-native-results.json`。累计8原生、372超分、4成片（仅低运动已最终接受）；父子未开始、high未超分，成本/矩阵未完成，保持IN_PROGRESS。

- **Low accepted / high start:** 用户“没问题”对明确展示的4份同字节1080P低运动成片及画面/声音/字幕问题给予真实最终接受，已绑定 `low/reviews/final-user-decision.json`。原low完成恢复0HTTP/0producer/0decode（必要完成验真SHA仍执行，非0IO）；完整接受贡献23.25秒，批次non-human2496.446s / 每可用秒107.374s，未将重叠trial包络相加，非历史因果提速或全片吞吐。`LVA-06-low-completion-state.json` 为原根完成/恢复证据。开始同一已授权清单的high冷1热3；任务继续IN_PROGRESS。

- **Actual low delivery stage:** 用户“没问题，继续吧”已接受上轮明确展示的4份实际同字节原生视频，决定绑定 `low/reviews/native-user-decision.json`。同一low根复用已完成原生，无新Wan；完成372唯一逐帧超分及4份93帧1080P/16fps原旁白字幕/libx264成片，完整RGB/PTS/AV证明均保存，4份成片SHA均 `6c141c85511b18c62ff298f893e28ad4aaa7658ec49283ab0ca6d2d85c56a337`。超分owned exit0/finalized、原PID身份已退出。批次T0→Tend=9407.449s，其中真实人工等待并集6911.003s，non-human包络2496.446s；不是各trial重叠包络之和。总376POST=4native+372frame，0已知失败/重做；等待本组最终成片质量，成本保持null，高运动/父子未开始；状态IN_PROGRESS，不再重复请求既有GPU授权。

- **Actual low native stage:** 本项授权后完成4实际原ID（cold1/warm3），各93完整帧；冷472.225s，热局部P50=469.185s/P95=469.473s。4份保留视频SHA均 `b9466c910edf6452bda2c8e9320fbcfccb24a25110476ff5fe19ea7128236f71`，全帧/PTS技术检查通过；generated原始文件SHA各异，保留记录，不推断新的质量接受。stage直接4POST/617GET、8producer/8decode/16probe；模型首次全准入与完成重放验真读取范围另述。owned服务exit0/finalized，原进程身份已退出。`docs/task-designs/LVA-06-gpu-results.json` 为具名部分结果；等待当前实际新原生媒体审核，尚未超分/成片、高运动或父子矩阵，成本/端到端/全片收益均未成立，保持IN_PROGRESS。

- **GPU authorization evidence:** 用户对已呈现的本项具体16Wan/1424帧/12成片清单回复“同意”；授权文件 `docs/task-designs/LVA-06-authorization.json` 绑定manifest文件SHA `ba88dfc0950e905e527d73e11e8ddc660593540c78502588065403b35c779d26` 和canonical SHA `c9f66424f4316c210a96d826f27b63c0c3f31986fcd3a62e52803a4c752953a8`。开始按low→high→chain串行测量，真实新视频仍需阶段性质量决定；状态IN_PROGRESS，原生产不恢复。下方待授权段为历史快照。

- **Implementation/offline evidence (2026-11-16):** 固定quality/strict/serial/libx264的一矩阵plan、UTC/perf事件链、人工等待并集、真实父子绑定、原ID恢复、owned退出、成功命令与单次AV/RGB证明、跨调用计数和JSON/Markdown已交付。77项定向通过（26.24s）；真实CPU/假HTTP三fixture共16假native、48假帧、12真实x264，完成重放HTTP/producer/decode/probe增量均0（stage操作内SHA增量0，必要完成验真SHA仍执行、不计作0物理读取），模拟决定不作真实质量。独立审查material缺口已修复并回归。结果 `docs/task-designs/LVA-06-results.json` / `.md`，审查 `LVA-06-review.md`；具体 `LVA-06-experiment-manifest.json` 文件SHA `ba88dfc0950e905e527d73e11e8ddc660593540c78502588065403b35c779d26` / canonical SHA `c9f66424f4316c210a96d826f27b63c0c3f31986fcd3a62e52803a4c752953a8`、命令 `LVA-06-gpu-commands.md` 已准备：最多16Wan、1424串行超分、12成片、7owned；0下载/fast/NVENC/付费/生产恢复。三个确切新根未创建，未启动本项GPU。等待本项具体清单许可及后续真实原生/父子/最终质量，不宣称新收益或项目完成，保持IN_PROGRESS。

- **Start evidence (2026-11-16):** 用户明确要求“完成任务LVA-06”；已全文读取本项设计和关联交接，READY -> IN_PROGRESS。按 `docs/task-designs/LVA-06-plan.md` 实施既定接口，先 prescribed RED，再离线/定向及具体manifest。真实本项GPU/质量尚未执行，不继承LVA-05授权，生产仍暂停。

- **Preparation evidence:** LVA-05实际测量及不默认采用结论先登记COMPLETED后，按Order=6选择本项，观察NOT_STARTED。已完成并关联 `docs/task-designs/LVA-06-design.md`；独立fresh builder复核“nothing important left”。五项直接依赖质量/strict/serial/libx264及人工/owned/原ID约束一致，最终与baseline同profile只实测一矩阵，真实batch端到端、人工区间并集和局部冷/热分别计量，不加重叠包络。完整阅读关联设计，写入并关联 `docs/task-handoffs/LVA-06-handoff.md` 后执行NOT_STARTED -> READY。未启动本项实现/测试/GPU，LVA-05授权不继承，原生产保持暂停。
- **Goal:** 以可复现端到端对照确认本轮收益、质量和失败表现，形成可采用配置及性能回归依据。
- **Scope:** 对应第 8 节 F，汇总 A–E 实际交付。沿用同一 fixture/身份和计时边界，复测最终组合、正常生成与恢复，分别列出质量基线、实验配置和不支持项；执行相关最终回归，交付 benchmark JSON 和 Markdown 总报告。不把局部节省相加为整片收益，不擅自推广实验模式、发布或恢复生产。
- **Acceptance:** ① 低运动、高运动、父子续接固定输入的冷/热端到端对照可复现；计时从选图完成至本地成片，人工等待单列。② 报告完整阶段耗时、本地片段 P50/P95、每可用视频秒成本、失败/重做率、显存、质量与帧数/PTS/连续性结果，披露环境和样本限制。③ LVA-02 恢复/异常拒绝在最终组合下不退化，已完成产物不重复生成、未知请求不盲重发，旧格式兼容和冻结身份保持。④ 原质量路径和回退可用；区分各优化独立收益与组合收益，真实实验缺失项不记通过，不承诺未经测量的倍数。⑤ 总报告链接各项确切产物与验证结果，列出可采用、仅实验、拒绝和待验证项；全部任务的自身验收满足后方可项目收尾。
- **Dependencies:** `LVA-01` 的原始基线/fixture；`LVA-02` 的精简与恢复交付；`LVA-03` 的生命周期/调度交付；`LVA-04` 的独立实验配置及 QA 结论；`LVA-05` 的超分/编码交付与兼容结论。各项都作为最终组合和归因的直接输入。
- **Sources:** ① 总体设计全文；② 本板 LVA-01 至 LVA-05 的实际设计、代码交付、验证与基准报告；③ `docs/task-designs/video-generation-performance-results.md`。最终复测使用前项实际建立的脚本与产物路径，在专项设计及完成证据中回填。
- **First action:** 按 `docs/task-designs/LVA-06-design.md` 在 `tests/unit/test_final_local_video_benchmark.py` 写 `test_identical_final_profile_reuses_one_matrix_and_never_sums_trial_envelopes` RED；T0=0/Tend=100与重叠人工区间断言并集30、non-human70、未全部质量接受cost=null、同profile只一矩阵，再实施已规定plan/session/summarizer，不先跑GPU或重做设计。
- **State evidence:** 2026-11-15 初始化为 `NOT_STARTED`；没有本板端到端收益或质量通过证据。

## LVA-07 Task Details

LVA-07 总体设计为 `docs/task-designs/LVA-07-wrapper-backend-design.md`。以下范围均从该设计拆出；不得把本轮任务拆分视为已执行环境审查。父专项不再另列执行状态；子任务状态只见本板。后续专项设计为 None 的任务需在准备交接前完成设计并回填，不能直接据此启动实现。

此前失败的“两组”在已提供证据中是同一套1022权重的 high/low 专家：high=1500 tensors（810普通weight/447 diff_b/202 diff/41 diff_m），low=1749（974/531/244/0）。这些是 header 计数，不是 applied patch 数；high 原生失败，low 运行时未到达。逐组核对不能相互代替。若还指另一套版本，需补充其身份后另行纳入，不能自行换权重。

### LVA-07-01

- **Goal:** 在零安装、零GPU前提下确定当前环境冲突和 Wrapper mixed-delta 支持路径，决定是否值得进入CPU验证。
- **Scope:** 固定候选 Wrapper 完整 commit，审阅 README、依赖、节点注册、converter/loader/patch及采样路径；核对 Windows/Python ABI/torch/CUDA、FP8、merge/unmerge、模型结构与可选加速依赖。不导入节点，不修改生产或下载模型。
- **Acceptance:** 环境与依赖兼容矩阵有固定版本依据；普通LoRA/diff/diff_b/diff_m均有处理函数和目标映射或明确拒绝证据；high/low分别记录；输出“进入CPU验证/停止/证据不足”，无实际加载或速度主张，0安装/服务/生成POST/GPU。
- **Dependencies:** LVA-04 的历史环境、权重身份与原生拒绝证据。
- **Sources:** ① docs/task-designs/LVA-07-01-design.md；② docs/task-designs/LVA-07-wrapper-backend-design.md；③ docs/task-designs/LVA-04-results.md、LVA-04-source-research.json、LVA-04-native-rejection-evidence.json；④ https://github.com/kijai/ComfyUI-WanVideoWrapper 的固定commit源码与依赖声明。
- **Deliverables:** `docs/task-designs/LVA-07-environment-review.json` / `.md`，已交付固定源码、环境/依赖矩阵、两专家与四类patch路径、停止结论及解除条件；原始只读取证在 `E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit/`。
- **First action:** 只读查询 Wrapper 候选完整 commit，之后绑定该SHA阅读README及实际LoRA转换/patch路径，先定位41个diff_m的目标及应用方式。
- **State evidence:** 2026-11-17 拆分初始化READY，已关联本项审查设计；无前驱交接。用户明确要求“完成任务LVA-07-01”，完整读取专项设计和历史证据后执行 `READY -> IN_PROGRESS`；本次仅只读审查，不安装、不导入节点、不启动服务或GPU。Handoff=None。
- **Completion evidence (2026-11-17):** 完整重读本项设计后执行 `IN_PROGRESS -> COMPLETED`。Wrapper候选固定为 `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`（1.4.8），18份固定源码文本有SHA256；审阅其版本提交与父提交、实际converter/loader/merged/unmerged路径，分别记录high1500/low1749历史tensor分类（非应用计数）。源码显示diff_m→modulation.diff有转换，但unmerged只查CustomLinear.weight，遗漏bias/norm/modulation；merged的非叶模块遍历也有block/head自有modulation跳过缺口，随后patches被清空。high41个diff_m不能据转换成功认领已应用；low无diff_m亦未证明完整兼容。结论停止当前候选安装/推理准备，非宣称Wrapper普遍不支持。
- **Environment/verification evidence:** `python.exe -I -S`查询Python3.13.14；只读version.py/METADATA/WHEEL确认torch2.14.1+cu130/CUDA13.0、Comfy0.44.0，本轮Comfy HEAD `2c75dc1b379a59e0880619d029607af5169a62ef`；nvidia-smi查询RTX5090Dv2/610.88/24455MiB。当前缺8项声明依赖，PyPI只读索引/wheel标签不作联合运行兼容证明。两个base各仅读180728字节header及8字节长度，结构/scale有候选路径，未发现必须换Kijai base的强制条件，未完整load/重哈希。实际命令：JSON ConvertFrom-Json解析exit0，报告rg覆盖exit0，stdlib文档核对18/18文本SHA、两专家计数/零操作边界通过，git diff --check exit0；diff范围只有原有设计/任务板和新审查文档，没有产品代码/模型/workflow修改。不跑产品测试或GPU；0安装/模型下载/节点导入/服务启动/生成POST/GPU采样/远程源码执行，旧生产仍暂停。CPU数值、全部tensor映射、完整模型应用、媒体质量及提速均未验证。
- **Successor preparation:** 按Order选中LVA-07-02，观察NOT_STARTED。其“前项支持进入CPU验证”的进入条件未成立；本项完成状态保留，后继Status/Design document/Handoff原值保持，不写部分交接。后续若另行决定CPU负向复现，须先完成该项具体隔离环境与设计，安装按已列具体命令另获授权；当前不自动投入或绕过mixed-delta门槛。

### LVA-07-02

- **Goal:** 用真实 Wrapper 处理函数确认两组权重的映射和混合delta数学语义，先排除“忽略不支持项仍显示成功”的假兼容。
- **Scope:** 在前项支持进入CPU验证时，读取锁定high/low全部key/shape/dtype，逐项映射到base结构；针对普通LoRA、diff、diff_b、diff_m验证实际converter/patch函数的CPU数值行为、strength、merge/unmerge及FP8边界。使用小张量/局部参数副本时明确覆盖范围，不把模拟函数当真实Wrapper。若缺依赖，先给出最小独立CPU环境及命令，取得该项安装授权；不污染生产、不启动GPU或服务。
- **Acceptance:** 每个输入tensor都有消费/目标或拒绝原因；41个high diff_m与两侧全部bias/diff不被遗漏；数学结果与声明语义一致、未识别/shape/dtype/NaN/Inf及单专家失败导致pair原子拒绝。输出源码、CPU实际执行与完整模型未验证项的分层结论；缺依赖/映射不完整不得记通过。unsupported可形成明确否决结论，不能制造GPU候选。
- **Dependencies:** LVA-07-01 的固定源码、依赖及支持路径；LVA-04 的两权重锁定身份与header证据。
- **Sources:** ① docs/task-designs/LVA-07-wrapper-backend-design.md 的兼容准入与身份表；② LVA-07-01实际审查交付；③ docs/task-designs/LVA-04-source-research.json、LVA-04-native-rejection-evidence.json；④ 固定commit实际converter/loader/patch函数。自身详细设计在准备时完成并关联。
- **Deliverables:** CPU兼容验证代码/定向用例和逐tensor JSON、Markdown结论；确切实现及报告路径在本项设计中确定，当前不伪造已有文件。
- **First action:** 依据已固定源码，为high diff_m和low diff_b建立调用真实Wrapper函数的最小CPU失败复现，并扩展至全部映射；不先实现完整服务adapter。
- **State evidence:** NOT_STARTED；没有CPU加载、应用或数值验证结果；不会因前项源码存在某个节点就自动宣称兼容。

### LVA-07-03

- **Goal:** 基于环境与CPU证据，判断是否值得投入隔离环境和真实GPU实验，并使后续投入具体可审阅。
- **Scope:** 汇总继续/停止/证据不足的理由；继续时固定目标runtime/commit、base与LoRA复用或下载身份、字节数/SHA、FP8/offload策略、预计磁盘/RAM/VRAM和命令；列出CPU证据未覆盖的完整模型实际准入，以及先少量后扩展的GPU预算。此项只写清单，不执行安装/下载/GPU。
- **Acceptance:** 不支持mixed delta或关键依赖无解时明确停止；证据不足列解除条件而不冒充通过。继续决定只能说明值得尝试，不能证明模型已应用或质量通过；具体安装/下载/GPU授权范围可逐项审阅，最小计划原则上1个40步低运动control及通过后的1个4步候选，W3替代模型需单列而不自动投入。
- **Dependencies:** LVA-07-01 环境/源码审查；LVA-07-02 CPU实际证据与局限；LVA-01 固定素材及原生质量/计时边界。
- **Sources:** ① docs/task-designs/LVA-07-wrapper-backend-design.md；② LVA-07-01/02实际交付；③ docs/task-designs/LVA-01-gpu-results.md、LVA-04-results.md；④ 原模型与workflow身份记录。自身详细设计在准备时完成并关联。
- **Deliverables:** docs/task-designs/LVA-07-environment-manifest.json 和投入决策/命令文档（拟交付）；未核定值显式未验证，不伪造commit或资源数字。
- **First action:** 按两项实际证据逐条判定混合delta、环境和模型结构是否具备继续条件，再汇总具体资源与剩余风险。
- **State evidence:** NOT_STARTED；尚无继续决定或具体新安装/GPU授权。原任务拆分不构成这些操作授权。

### LVA-07-04

- **Goal:** 在决定值得投入后，准备独立可恢复的Wrapper实验路径，使真实测试有确定接口和失败边界。
- **Scope:** 按已获具体授权的清单准备独立checkout/runtime/owned worker；实现wan_wrapper_backend、观察/benchmark入口和独立workflow/mapping/provenance，复用原ID恢复和媒体契约。离线覆盖身份漂移、缺节点、双专家原子准入、unknown不重发、完成媒体复用及owned退出；不执行视频采样、不改生产默认。需要启动服务的节点能力探测按具体清单授权执行。
- **Acceptance:** 固定环境/源码/模型身份，/object_info实际探测与离线模拟区分；40步/4步图映射、sigma/split/seed/完整帧约束固定；完整模型LoRA实际应用门槛可在fast POST前执行，任意未应用项拒绝。原quality图、即梦代码和旧run不变，离线针对性测试/恢复记录可复现，所有owned服务有退出证据。
- **Dependencies:** LVA-07-03 的继续决定/固定环境清单及具体授权；LVA-07-02 的真实映射与数学验证；LVA-02 的身份/恢复契约。
- **Sources:** ① docs/task-designs/LVA-07-wrapper-backend-design.md 的Architecture/Tests；② LVA-07-02/03实际交付；③ docs/task-designs/LVA-02-design.md；④ workflows/wan22_i2v_14b_api.json及mapping；⑤ src/video_ai/runtime/scene_comfy_transactions.py、production_scene_clips.py。自身详细设计在准备时完成并关联。
- **Deliverables:** 总体设计已有的 src/video_ai/experiments/wan_wrapper_backend.py、scripts/observe_wan_wrapper_comfy.py、scripts/benchmark_wan_wrapper.py、Wrapper工作流三件套及定向测试；具体接口在本项专项设计完成，不宣称当前已有实现。
- **First action:** 按已完成专项设计先建立缺失mixed-delta/节点身份与unknown恢复的定向失败用例，再实现隔离profile及adapter；安装只执行已经具体授权的命令。
- **State evidence:** NOT_STARTED；尚无隔离环境、服务、workflow或实现验证结果。缺少继续决定不得自动准备为READY。

### LVA-07-05

- **Goal:** 用最小真实样本确认完整双专家应用和Wrapper视频契约，决定是否值得扩展矩阵。
- **Scope:** 在本项具体GPU授权下，先完成实际base和high/low完整加载/应用准入，记录每tensor目标和实际patch证据；然后1个低运动93帧/768×432/16fps的40步control，技术与人工质量通过后才运行同输入4步候选。实际调用数、sigma/CFG/split、offload/VRAM和计时分层记录；不直接执行全矩阵。
- **Acceptance:** 完整模型准入不能由CPU fixture代替，未应用/未知key/shape冲突在fast POST前拒绝；control与fast分别有完整帧/PTS及人工质量结论，任何失败停止。若base或scheduler不等价明确报告，W1不兼容不自动换W3；恢复原ID、不重发unknown、服务退出可核对。仅有1样本不宣布P50/P95或稳定加速。
- **Dependencies:** LVA-07-04 可执行隔离harness及针对性验证；LVA-07-03 固定资源/最小GPU清单与具体授权；LVA-01 素材/质量基线。
- **Sources:** ① docs/task-designs/LVA-07-wrapper-backend-design.md 的Model gate/Experiment matrix/Real media；② LVA-07-03/04实际manifest、命令及离线证据；③ docs/task-designs/LVA-01-gpu-results.md。自身详细设计在准备时完成并关联。
- **Deliverables:** 实际应用准入、原始请求/输出/技术及人工质量/资源证据和最小对照结果；结果追加至 docs/task-designs/LVA-07-results.json / .md（拟交付）。
- **First action:** 在获授权的独立worker执行完整双专家模型/LoRA应用准入；失败不发fast生成POST，成功后才进入最小control。
- **State evidence:** NOT_STARTED；没有GPU实际准入、采样、媒体或人工质量结果；不得承接旧LVA-04/06授权自动运行。

### LVA-07-06

- **Goal:** 在最小候选通过后，完成可复现性能/质量/恢复结论，给出是否值得后续另行设计生产接入的建议。
- **Scope:** 按已获扩展授权补齐低/高运动和父子链各冷1热3，只有profile、owned服务和计时边界相容时复用最小样本；父片真实人工接受后才生成同profile子片。汇总阶段/端到端、冷/热、GPU/VRAM/offload、失败率及人工等待；验证原ID恢复和完成产物不重做。若前项否决不启动本矩阵，保留未执行事实与专项否决报告。
- **Acceptance:** 全部实际完成样本的完整帧/PTS、质量与连续性可追溯，恢复无重复生成/unknown重发；冷1热3缺样不虚报完成、局部收益不冒充整片加速，更换base不归因纯后端。结论区分可继续研究/不支持/无收益/质量失败/未验证；负面结果可按自身实验停止分支收尾，未执行的后续任务不伪装COMPLETED。不恢复生产或自动推广。
- **Dependencies:** LVA-07-05 的最小样本实际技术/人工质量及是否扩展决定；LVA-07-04 的恢复/服务/媒体接口；LVA-01 的完整fixture和原生比较边界。
- **Sources:** ① docs/task-designs/LVA-07-wrapper-backend-design.md 的Performance/Tests；② LVA-07-05实际结果及扩展清单；③ docs/task-designs/LVA-01-gpu-results.md；④ LVA-07-04实际恢复/输出证据。自身详细设计在准备时完成并关联。
- **Deliverables:** docs/task-designs/LVA-07-results.json / .md 的最终兼容、性能、恢复、质量与拒绝/未验证报告，链接实际原始证据。
- **First action:** 核对最小样本的真实技术/人工质量、扩展授权和可复用计时边界，计算尚缺样本后再运行；不为填表重做已有视频。
- **State evidence:** NOT_STARTED；没有扩展矩阵、加速或生产推广结论。前置失败时不能按Order自动绕过门槛。

## Risks

- **授权与实测缺口：** 设计明确真实推理需新实验 run 和明确许可。建板不具备该许可；未完成真实测量时仅能记录已交付部分，不能把整项记完成。
- **校验去重与信任：** 同函数名不代表同检查价值；路径、大小、mtime 不能代替内容身份。运行锁/原生保护失效、依赖变化或重启必须使作用域证明失效，非强保护平台保留严格路径。
- **恢复与重复提交：** Comfy 服务重启可能使旧 queue/history 不可信；未持久化扩散中间步不可承诺恢复，未知提交不得自动重发，父片观察和尾帧绑定不得跨内容复用。
- **模型与质量：** 4 步开关不证明 LoRA 正确；SageAttention、缓存和编译的社区经验不能替代本机双专家实测。加速失败或质量下降保留原 40 步路径，不降低帧数、连续性或最终画质来达标。
- **资源与并行：** 同连续链必须串行，单 GPU 盲目并发或多个超分模型可造成换入换出/OOM；所有不可变任务证据仍由持锁协调线程写入。
- **重复工作与归因：** 既有性能结果只作历史输入；实际源码已覆盖的优化不重做，微基准和历史收益不计成本轮整片收益。
- **工作区保全：** 建板时工作区已有其他源码、测试和报告改动；本板不覆盖它们，不改变既有任务状态或生产锁。
- **Wrapper证据层次：** 源码支持、CPU验证、完整模型实际应用与真实视频质量分别验收；前置不支持或证据不足时停止后续投入，不因任务顺序自动安装/推理。
