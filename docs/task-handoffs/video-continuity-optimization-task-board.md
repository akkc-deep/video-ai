# Video Continuity Optimization Project Task Board

## Project

- **Project ID:** `video-continuity-optimization`，任务前缀 `VCO`。
- **Goal:** 建立模型无关的视频连续性诊断与质量控制层，减少无剧情依据的色彩、主体、动作和镜头变化；生成策略必须经过真实验证才能生产启用。
- **Scope:** 按 `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 11 节拆分八项交付，覆盖版本化视觉提示、色彩链诊断、连续性分析、观察与恢复、20 秒隔离验证、可选校色、整段生产模式和原生跨窗续写。沿用 `docs/task-designs/JIM-08-color-repair-design.md` 阶段 A/B/C 的已有契约，不另建冲突协议。排除题材特判、全局强制保色、自动重试推理、未经验证的后端替换，以及用切镜、插帧、变速或截短代替连续镜头。
- **Completion condition:** 各任务按自身验收保留可定位证据；软件、技术视频、资源、自动诊断、完整动态观察和最终交付分别记账。实际启用的模式须通过对应真实样片与完整成片验收；原生 16fps、精确帧映射、完整 PCM/字幕和旧冻结 run 恢复保持正确。单次整段通过不能代表多窗续写或任意时长通过；尚未满足前提的任务保持未完成，不能以本板收尾改写原 JIM-08 验收结果。
- **Overall design:** [视频连续性与色彩稳定性通用优化方案](video-continuity-optimization-proposal.md)，以用户指定的现有路径为准，不使用文中尚未落地的“拟存放位置”。
- **Authorization evidence:** 2026-10-23 用户要求“按照这个设计拆任务”。本次授权为任务拆分和建板，不启动实现、GPU 推理、付费试验或发布。
- **Board boundary:** 本板只管理上述优化项目；`docs/task-handoffs/jimeng-scenes-task-board.md` 及 `JIM-08` 原定义、状态、设计与交接保持原记录。本板不登记历史试验重新通过，也不代替原任务的完成判定。

## Workflow

- **Execution:** 按 Order 提供默认实施顺序，串行执行安排由用户决定；建板不启动首项，不派发实现，也不自动改变其他任务状态。
- **Next-task selection:** 当前任务完成后，选择 Order 更大且未完成的最小 Order 任务。Dependencies 仅表示直接消费的输入，不替代预定义顺序。
- **Successor preparation:** 先记录当前任务的完成证据，再完成并关联所选后继的详细设计，最后写入 next-task 交接并准备为 READY。后继设计或前提不足时保留前任务完成状态，后继状态和 Handoff 不变，不生成部分交接。
- **Allowed transitions:** `NOT_STARTED -> READY`、`READY -> IN_PROGRESS`、`IN_PROGRESS -> PAUSED`、`PAUSED -> IN_PROGRESS`、`READY -> BLOCKED`、`IN_PROGRESS -> BLOCKED`、`BLOCKED -> READY`、`IN_PROGRESS -> COMPLETED`。
- **Initialization:** `VCO-01` 为 `READY`，其余为 `NOT_STARTED`，所有 Handoff 为 `None`。READY 表示可推进设计，不表示实现已开始。
- **Design documents:** 本次仅拆任务，各任务 Design document 初始化为 `None`；共同方案和既有 A/B/C 设计按 Sources 阅读。后续任务设计须冻结输入输出、schema、准确源码路径、失败规则、测试与验收，以及恢复和真实推理边界，并回填确切路径。不得把总体方案直接当作八项均已完成的实施契约。
- **Evidence:** 本次只验证任务板结构、依赖和引用，不登记代码测试、GPU 或观看通过。实现阶段按既有设计先做必要的 RED/GREEN，再运行对应定向与集成检查；集成完成执行要求的裸全库，测试与 GPU 推理串行，保存命令、退出码和输入身份。
- **Conditional work:** `VCO-05` 的隔离试验须有明确执行授权；单次失败应完整交付失败证据并停止，不能自动追加试验。`VCO-07` 另须实际通过证据；`VCO-08` 另须新的真实时序协议及独立验证。缺少这些前提不能自动启用模式或准备后继，也不在建板时预先记成 BLOCKED。

## Tasks

| Order | Task ID | Title | Status | Dependencies | Design document | Handoff |
|---:|---|---|---|---|---|---|
| 1 | VCO-01 | P0-A：版本化片段视觉提示契约落地 | COMPLETED | None | docs/task-designs/VCO-01-design.md | None |
| 2 | VCO-02 | P0-B：原生色彩元数据与编码链诊断 | READY | None | docs/task-designs/VCO-02-design.md | docs/task-handoffs/VCO-02-handoff.md |
| 3 | VCO-03 | P1-A：色彩与动作连续性分析器 | NOT_STARTED | VCO-02 | None | None |
| 4 | VCO-04 | P1-B：诊断接入观察门槛与版本化恢复 | NOT_STARTED | VCO-03 | None | None |
| 5 | VCO-05 | P1-C：单次 20 秒隔离生成与跨题材验证 | NOT_STARTED | VCO-01 | None | None |
| 6 | VCO-06 | P2-A：轻度非破坏性校色与修订血缘 | NOT_STARTED | VCO-03, VCO-04 | None | None |
| 7 | VCO-07 | P2-B：经实测准入的版本化整段生产模式 | NOT_STARTED | VCO-04, VCO-05 | None | None |
| 8 | VCO-08 | P3：原生跨窗口续写后端验证与接入 | NOT_STARTED | VCO-01, VCO-04 | None | None |

## Task Details

以下 Sources 均为仓库根目录 `D:/code/py/video-ai` 下的确切相对路径，按列出顺序阅读；Scope 中的“新增”文件为计划产物，不表示已经存在。表中直接依赖说明：VCO-07 同时消费 VCO-05 的实测证据和 VCO-04 的诊断准入/恢复能力；VCO-08 消费视觉提示与诊断契约，不把整段生成成功当作跨窗后端可用的证据。

### VCO-01

- **Goal:** 将模型视觉指令与审计材料分离，使每个 clip 的动作、运镜和光照符合当前场景、原图姿态与延续阶段。
- **Scope:** 落地既有 A 阶段的 `scene_rendering.prompt_policy=visual_v2`、契约 schema_version=1、SHA/来源绑定、文本审查和修订失效。新增 `src/video_ai/planning/scene_video_prompts.py`、`src/video_ai/runtime/scene_video_prompt_records.py`，接入配置、冻结输入、续片规划、scene_context 和 revision/recovery。保留 comparison_images 的审计身份，未经工作流支持和实验验证不得把它当模型参考图。不在本任务增加整段生成模式或真实 GPU 验证。
- **Acceptance:** ① 精确字段、完整且唯一的 clip 覆盖、内容与审查 SHA、原文 changes 引用均可验证；未知字段/policy、部分配置、漂移或未通过文本审查在提交前拒绝。② positive 只包含本 scene 的稳定视觉字段、已审查风格及本 clip 的 motion/camera/lighting，不混入审计 JSON、来源坐标或其他 scene 动作；原文明示的变化保留，续片不伪造未来父片姿态。③ 无新配置时旧 options、inputs、parameters、graph、请求重建与恢复保持原值。④ 提示变化建立新修订，使相关视频及后代观察/超分/合成/交付失效，合法继承原文、PCM、字幕、语义计划和选图，不额外出图。⑤ 精确 schema、多题材渲染、旧请求兼容、漂移零提交、修订与恢复用例有实测结果；不据此宣布视频颜色通过。
- **Dependencies:** `None`；复用现有已书面确定的 A 阶段设计。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 2、4、9、10 节；② `docs/task-designs/JIM-08-color-repair-design.md` 全文，重点 A 和软件检查；③ `src/video_ai/planning/scene_clip_continuation.py`；④ `src/video_ai/runtime/scene_clip_records.py`；⑤ `src/video_ai/config.py`；⑥ `src/video_ai/runtime/production_inputs.py`；⑦ `src/video_ai/planning/scene_revision.py`；⑧ `src/video_ai/runtime/scene_revision_records.py`；⑨ `tests/unit/test_scene_clip_continuation.py`；⑩ `tests/integration/test_scene_revision_flow.py`。
- **First action:** 对照 A 阶段设计与当前配置/渲染/修订接口，完成本任务实施设计，逐项确认沿用字段与旧请求兼容检查，并回填 Design document。
- **State evidence:** 2026-10-23 按用户“完成任务 VCO-01”明确启动，`READY -> IN_PROGRESS`；实施设计为 `docs/task-designs/VCO-01-design.md`，步骤与验证账本为 `docs/task-designs/VCO-01-plan.md`；无前驱交接。
- **Completion evidence:** 2026-10-23 `IN_PROGRESS -> COMPLETED`。visual_v2 的精确契约、文本审查/原文与来源 SHA、逐片纯视觉渲染、冻结/发送守卫和修订恢复已落地；提示变化保留通用输入与选图，仅失效相关视频后代，未配置时旧请求保持兼容。最终裸全库 3715 passed、退出 0，耗时 19118.06 秒；测试后 13/13 源码/测试身份与启动快照一致，git diff --check 通过。逐项验收、RED/GREEN、审查修复及完整命令/日志见 `docs/task-designs/VCO-01-verification.md`。未执行真实 GPU/付费推理，未登记视频颜色或动态观看通过；原 JIM-08 记录不变，.git 只读，改动留在本地工作区。

### VCO-02

- **Goal:** 能将颜色差异定位到模型原始输出、解码、裁片、超分或最终编码的具体阶段。
- **Scope:** 新增 `src/video_ai/media/colorimetry.py`，为 generated.mp4、原生尾帧 PNG、source.mp4、超分帧和最终成片提供独立色彩诊断 sidecar。记录 ffprobe 色彩字段、pix_fmt、编码器及实际解码/转换规则，明确统一分析空间；审查 video、frames、composition_video 的转换路径。初期保持 `validate_video_probe()` 严格返回字段契约，不以改标签冒充颜色转换，不盲目强制 Rec.709。
- **Acceptance:** ① 各阶段诊断能追溯媒体身份与处理步骤，包含 color_space/color_primaries/color_transfer/color_range，缺失或冲突明确保留 unknown 与风险。② 比较使用实际解码帧及明确分析空间，区分压缩差异与颜色解释差异；源解释不明时不强猜矩阵或范围。③ Rec.709、不同色彩标记、full/limited、未标记和解码/编码往返样例均有可复核诊断结果。④ 处理前后原生 16fps、PTS、帧数、尺寸和精确映射不变，旧媒体记录重放及旧 probe 契约不变。
- **Dependencies:** `None`；直接复用现有媒体校验与帧提取能力。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 2.2、5、9、10 节；② `src/video_ai/media/video.py`；③ `src/video_ai/media/frames.py`；④ `src/video_ai/media/composition_video.py`；⑤ `src/video_ai/runtime/production_scene_clips.py`；⑥ `src/video_ai/runtime/production_scene_upscale.py`；⑦ `src/video_ai/runtime/production_scene_composition.py`；⑧ `tests/unit/test_composition_video.py`。
- **First action:** 梳理原始输出到最终编码的实际色彩转换点，完成独立 sidecar 的输入输出和 unknown 处理设计，不修改旧 probe 返回结构。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；本次未运行色彩链样例或修改媒体处理。
- **Preparation evidence:** 2026-10-23 在 VCO-01 完成记录之后，按 Order 2 选中本任务；直接依赖为 None。已完成并关联 `docs/task-designs/VCO-02-design.md`，冻结旁路接口/schema、真实转换点、显式 SDR 分析空间、unknown/失败规则及测试验收；随后写入并关联 `docs/task-handoffs/VCO-02-handoff.md`，执行 `NOT_STARTED -> READY`。准备仅为详细设计与交接，未新增 colorimetry 源码、未运行转换样例或开始实现。

### VCO-03

- **Goal:** 对接缝、片内漂移、长链累计、主体和动作异常生成可复算的只读报告，并区分合理变化与不可比内容。
- **Scope:** 新增 `src/video_ai/media/continuity_analysis.py`；消费 VCO-02 的颜色解释与分析空间，对父子片及场景长链分析接缝基线、亮度/色度/饱和度和剪切趋势、可匹配区域累计变化、光流/主体位置/镜头轨迹和动作重置。配对色差仅用于可对齐的同一内容；用多题材标注样本校准阈值和告警，样本数量、指标与阈值在专项设计中确定，不捏造全局阈值。本任务不写生产准入、不自动校色。
- **Acceptance:** ① 合成亮度/色度接缝、主体局部变化、片内渐进偏色、三段累计漂移及突发动作重置能形成对应定位证据，不只依赖全图 MAE 或直方图。② 日落、阴影、运镜、新背景和遮挡保留变化依据；无可靠匹配区域或对齐不可信时返回 not_comparable/unverified，不必然判错。③ 报告包含输入/参考 SHA、算法版本、比较帧编号、时间戳、证据帧、可比性与置信度，冻结输入可复算。④ 标注样本、校准依据及误报/漏报检查可追踪；自动报告不宣称动态观看通过。
- **Dependencies:** `VCO-02` 的色彩 sidecar、统一分析空间和 unknown 规则。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 6、10 节；② 本板 VCO-02 实际交付的设计与色彩诊断产物；③ `src/video_ai/media/frames.py`；④ `src/video_ai/media/video.py`；⑤ `src/video_ai/runtime/scene_clip_observations.py`；⑥ `docs/task-designs/JIM-08-continuity-diagnosis.md`。
- **First action:** 根据 VCO-02 的实际诊断接口，完成分析器输入输出、可比性状态、证据帧和标注校准方案的详细设计。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；尚无本任务算法、校准阈值或验证结果。

### VCO-04

- **Goal:** 将机器连续性报告接入现有观察与恢复流程，保证未观察、失败或不可比的结果不会自动升级为通过。
- **Scope:** 新增 `src/video_ai/runtime/scene_continuity_records.py`，持久化输入 SHA、算法版本、对比帧和报告；接入 production_scene_clips 现有观察链及修订/恢复。保持“视觉输入身份 → 技术与色彩报告 → 机器诊断 → 完整动态观察 → 超分合成及最终观看 → 显式发布”的顺序。诊断算法变化仅重算报告及准入，不重新生成原片；提示/模型变化和校色变化分别作用于相应依赖。
- **Acceptance:** ① failed、unverified、不可比、报告缺失/漂移及缺少有效 human_video/具备实际完整播放能力的 agent_video 观察，均不能被写成视频 passed。② 报告绑定准确媒体/参考/算法身份，可中断恢复、重算并保留失败证据；静帧或自动分数不能代替完整动态观察。③ 仅改诊断算法不会重新 POST 模型请求或重出原片；未知任务结果沿原 request/prompt_id/HTTP 记录恢复，不补单。④ 旧冻结 run 仍按原契约恢复，新记录的缺项或 SHA 漂移在推进/发布前拒绝，相关修订与恢复用例有实际结果。
- **Dependencies:** `VCO-03` 的分析接口、报告字段、可比性状态和算法身份。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 3、6、9、10 节；② 本板 VCO-03 实际交付的设计与分析报告；③ `src/video_ai/runtime/production_scene_clips.py`；④ `src/video_ai/runtime/scene_clip_observations.py`；⑤ `src/video_ai/runtime/production_scene_pipeline.py`；⑥ `src/video_ai/runtime/scene_revision_records.py`；⑦ `tests/integration/test_scene_pipeline_recovery.py`；⑧ `tests/integration/test_scene_revision_flow.py`。
- **First action:** 对照 VCO-03 的实际报告契约和现有观察状态流，完成准入、记录身份及算法变更恢复的详细设计。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；尚未改变原观察、恢复或发布门槛。

### VCO-05

- **Goal:** 以隔离真实试验证明或否定当前资源下 20 秒整段候选的可用性，并明确跨题材验证范围。
- **Scope:** 按既有 B 阶段先完成通用 runner/helper 设计与软件检查，再在已授权条件下执行一次隔离请求。首例只读使用原 run `20261021-014723-4ebdc1fecab2` 的 scene3 已准入图，不将该题材写入通用实现；保持 Wan2.2 双专家、768×432、16fps、40 步、CFG3.5、Euler/simple、15 步切换及案例原首片 seed，321 请求帧精确保留 [0,320)。冻结 case/graph/模型/输入/提示，记录 GPU、内存、期限、HTTP 和输出。初例通过后，跨题材样片按另行明确的实际授权覆盖不同主体/材质及另一种镜头运动；不自动下载后端或追加 GPU 任务。不修改原生产预算、不写回原 run。
- **Acceptance:** ① 软件验证覆盖 321/320/[0,320)、身份漂移拒绝、重复执行不二次 POST、失败不降规格、原 run 不改写。② 真实执行前核验资源、模型与输入及服务拥有权，仅管理自有服务；一次 POST，结果不明只查询原任务，OOM/超时/非法输出/明显外观失败保留现场并停止。③ 原始输出、原始帧、精确映射、SHA、审阅副本、日志、耗时和资源证据齐全；20 秒技术结果、采样外观和完整视频观看结论分开。④ 仅技术、完整动态观察和资源记录同时通过才形成 VCO-07 准入证据；无观看能力或缺有效观察时保留 unverified。⑤ 跨题材能力只按实际已验证范围表述；未授权或未完成的跨题材部分明确保留待办，不能把单例外推。本任务不以整段样片取消原独立续接验收。
- **Dependencies:** `VCO-01` 的已冻结、已审查视觉提示契约及纯视觉渲染。诊断可按既有 B 阶段独立记录，本任务不以 VCO-02/03 的实现作为首例执行的必要输入。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 8、10、11 节；② `docs/task-designs/JIM-08-color-repair-design.md` 全文，重点 B、颜色与动态验收；③ 本板 VCO-01 实际交付的契约及验证证据；④ `docs/task-designs/JIM-08-verification.md`；⑤ `docs/task-handoffs/JIM-08-handoff.md`；⑥ `src/video_ai/runtime/production_visual_templates.py`；⑦ `src/video_ai/runtime/scene_clip_records.py`；⑧ `scripts/bootstrap.ps1`。实际案例媒体路径从原准入记录读取后再冻结，不在本板猜测。
- **First action:** 只读定位既有 B 阶段指定案例的准入记录，完成隔离 runner、单次提交恢复、321/320 帧预算和观看证据的实施设计。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；RTX 5090 D v2 24GB 的 321 帧能力尚未证明，本板未提交真实推理或追加样片。若实际失败，只有完整交付已限定试验的失败证据且无未完成范围时，才可据实判定该验证任务完成；失败不是生产准入。

### VCO-06

- **Goal:** 对主体和运动完整、仅存在轻微可定位色偏的视频提供默认关闭、可回退的独立修复候选。
- **Scope:** 新增 `src/video_ai/media/color_repair.py` 和 `src/video_ai/runtime/scene_color_repair_records.py`；基于可匹配稳定区域估计有幅度上限的曝光/白平衡/色度变换，时间平滑避免频闪，保存原片、候选片、参考 SHA、算法版本、参数及前后报告。接入候选的原生校验、观察、修订及恢复。修复幅度与适用门槛须由已校准样本及专项设计确定，不执行全图强制直方图匹配、逐帧独立重调或背景冻结。
- **Acceptance:** ① 默认不修，已稳定原片和不可比内容不自动处理，重大颜色/结构/动作异常不以校色冒充解决。② 轻度色温/曝光偏移候选有改善证据，未新增频闪或材质失真，并重新通过原生帧/PTS、色彩诊断和实际完整视频观察。③ 原片及其接受记录不被覆盖，失败可回退并保留证据。④ 若以修复片继续生成，必须新建显式修订与父子血缘，不悄悄替换已接受父片；参数/算法变化仅使候选及其依赖失效。⑤ 默认关闭、不可比拒修、参考漂移、候选恢复和血缘失效均有验证结果。
- **Dependencies:** `VCO-03` 的可比区域、漂移诊断与校准依据；`VCO-04` 的报告准入、观察与恢复身份。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 7、9、10 节；② 本板 VCO-03 和 VCO-04 的实际设计及交付记录；③ `src/video_ai/planning/scene_revision.py`；④ `src/video_ai/runtime/scene_revision_records.py`；⑤ `src/video_ai/runtime/production_scene_revision.py`；⑥ `src/video_ai/runtime/production_scene_clips.py`；⑦ `src/video_ai/runtime/production_scene_upscale.py`；⑧ `src/video_ai/runtime/production_scene_composition.py`。
- **First action:** 根据已交付诊断与准入契约，完成修复适用条件、幅度限制、候选身份、前后复检和血缘修订的详细设计。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；未启用校色、生成修复片或改写已接受媒体。

### VCO-07

- **Goal:** 将已通过真实验证的整段生成能力，以显式新模式接入完整生产链，并保持旧分段模式可精确恢复。
- **Scope:** 在 VCO-05 的实际通过范围内接入 `scene_rendering.mode=whole_scene_v1`，缺省 `segmented_v1`；沿既有 C 阶段派生独立版本化执行预算与渲染身份，贯通配置、输入、planning、graph、源片、裁剪/映射、观察、超分、合成、revision/recovery 与交付。不得只解除 96 帧 guard；不重新定义语义 scene-plan 或无故重新出图，不把短/中整段能力宣传为任意长镜头能力。
- **Acceptance:** ① 有 VCO-05 对应资源、原始输出、完整动态观看通过及适用范围证据；失败或缺项时不启用新生产模式。② 新预算在所有消费者一致，完整覆盖原时间轴，16fps、原始保留映射、PCM 样本和字幕不截短、不补帧冒充。③ 旧配置/冻结 run 保持原 options、graph、96 帧预算和恢复；未知 mode/预算或身份漂移拒绝。④ 模式变化仅使相关视频及下游失效，可核验继承原文、语义计划、已接受图和 PCM/字幕；不继承旧视频观看结论。⑤ 定向/恢复/全库检查及实际生产样片、超分合成、最终完整观看和显式发布有各自证据；同 run 重放不重复提交或发布。⑥ 原独立多片续接验收仍未因整段通过而自动完成。
- **Dependencies:** `VCO-05` 的真实技术、资源和完整动态观看通过证据；`VCO-04` 的诊断准入、身份与恢复契约。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 8、9、10 节；② `docs/task-designs/JIM-08-color-repair-design.md` 全文，重点 C；③ `docs/task-designs/JIM-08-whole-scene-proposal.md` 的长场景范围修正及全消费者预算设计（历史 137/221 帧预览不是当前 20 秒验收）；④ 本板 VCO-05 和 VCO-04 的实际设计与证据；⑤ `src/video_ai/planning/production_visual_plan.py`；⑥ `src/video_ai/planning/scene_clip_continuation.py`；⑦ `src/video_ai/runtime/scene_clip_records.py`；⑧ `src/video_ai/runtime/production_scene_clips.py`；⑨ `src/video_ai/runtime/production_scene_upscale.py`；⑩ `src/video_ai/runtime/production_scene_composition.py`；⑪ `src/video_ai/runtime/production_inputs.py`；⑫ `src/video_ai/planning/scene_revision.py`。
- **First action:** 核验 VCO-05 实际通过范围，再完成整段执行预算、消费者清单及旧模式兼容的实施设计；通过证据不足时先报告该缺口，不修改 guard。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；本板未证明 whole_scene_v1 可生产启用。

### VCO-08

- **Goal:** 为确需跨窗口保持一镜到底的长镜头验证真实时序上下文后端，并仅在通过后接入版本化生产策略。
- **Scope:** 外部前提是已有新的正式时序条件协议和独立真实试验依据，随后完成 `temporal_extension_v1` 的后端契约、历史/新增帧分账、重叠只输出一次、镜头状态延续、资源预算、显式时基适配与恢复设计。经隔离真实多窗口验证后才接入生产；24/30fps 后端不得偷偷替换正式 16fps 或损失完整时长。不将旧单尾帧/9 帧/VACE/SVI/F1 失败方案改名，不默认下载模型或追加推理，不把语义切镜当作一镜到底。
- **Acceptance:** ① 正式实现依据与实际 graph 可证明后端接收时序上下文，审计参考图不能冒充模型条件；模型/协议/输入/工作流身份完整。② 历史与新增帧分别计数、重叠只输出一次，时基适配后完整时长与映射准确，不靠冻结、循环、插帧或变速补齐。③ 真实多窗口长链分别验证主体、色彩、构图、镜头轨迹和动作阶段，保留自动报告与完整动态观察，不以首帧接近或整段单例代替。④ 窗口失败保留既有媒体与任务身份，未知结果不重复 POST，输入/协议漂移拒绝恢复；模式变化正确失效相关视频及下游。⑤ 实验与生产准入分别记录，未通过不启用，软件测试或新协议名称本身不构成视觉通过。
- **Dependencies:** `VCO-01` 的纯视觉提示及来源绑定契约；`VCO-04` 的连续性报告、完整观察和恢复准入。另需新的正式时序协议及独立真实试验作为外部前提，建板时尚无可准入后端。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 2.3、8、9、10 节；② `docs/task-designs/JIM-08-whole-scene-proposal.md` 的长场景适用范围修正；③ `docs/task-designs/JIM-08-continuity-diagnosis.md`；④ `docs/task-designs/JIM-08-continuity-repair-proposal.md`；⑤ `docs/task-designs/JIM-08-industry-continuity-research.md`；⑥ 本板 VCO-01 和 VCO-04 的实际设计与交付证据；⑦ `src/video_ai/planning/scene_clip_continuation.py`；⑧ `src/video_ai/runtime/scene_clip_records.py`。新增后端的正式资料、协议与实际试验证据在确立后补充，不预造引用。
- **First action:** 核对是否已有区别于历史失败方案的正式时序协议与真实试验依据，并据此明确专项设计输入；缺少时记录缺口，不启动下载或推理。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；没有本板认可的原生跨窗后端通过证据，不预先声明阻塞已解除或能力已实现。

## Risks

- **真实效果与证据：** 软件回归、SHA 相同、技术视频有效、静帧采样或自动分数均不能替代完整动态观察。不可比、failed、unverified 和缺少有效观察不得标为 passed。
- **资源与成本：** 321 原生帧尚未证明可在 RTX 5090 D v2 24GB 上成功；OOM/超时不自动降规格、换模型或反复提交。跨题材与新后端真实任务须有对应授权，未知提交只能恢复查询。
- **归因与校准：** 首例同时改变提示与生成长度，不能据改善归因单一变量；色彩元数据不完整、压缩和像素不匹配均可能误导判断。阈值、样本量与修复上限必须后续用实际标注依据确定。
- **旧输入和工作区：** 旧冻结 run 的 graph、请求和恢复须保持原契约；不得 reset/revert、批量暂存或覆盖未知改动。提示、诊断算法和校色参数三类变化需分别定义失效范围。
- **任务范围：** 整段模式只覆盖已经验证的资源与时长，不能取消 JIM-08 原多片续接要求。VCO-08 的新协议与实测前提尚未满足，不承诺任意长度都稳定；语义切镜是独立选项，未在本板自动采用。
- **后继准备：** 有序选择后继不等于前提已满足；尤其 VCO-05 失败时不得据“试验已结束”自动准备 VCO-07。未具备实施设计、直接输入或真实通过证据时，应保留当前已完成事实和后继原状态。
