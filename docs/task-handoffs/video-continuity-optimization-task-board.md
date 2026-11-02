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
- **Evidence:** 实现阶段按既有设计先做必要的 RED/GREEN，再运行对应定向与必要集成检查，保存命令、退出码和输入身份；测试与 GPU 推理串行。**2026-10-24 用户更新：全库回归统一放到最后一个任务 VCO-08/项目最终收尾执行，不再逐任务执行。** 未完成的全库保留为未完成，不能登记通过。
- **Current closeout boundary:** 2026-10-26按用户已选择的“AI校准、不填表格”及连续完成授权统一VCO-03任务验收：主任务消费软件分析器、可追溯AI实验与一次检查，原24源双人正式Benchmark及六类生产ready要求保留为未验收限制，不再作为本AI任务路线的阻塞条件。状态按下方最新记录更新；历史BLOCKED快照不代表当前状态。用户随后明确要求“完成任务VCO-04”，本任务按已关联设计进入实施及定向验证；不自动执行真实推理、发布或后续任务。全库仍仅在VCO-08/项目最终收尾执行。
- **2026-10-30 closeout correction:** 用户指出任务状态不对并要求完成下一任务准备；按VCO-06主设计显式修订的结项口径，软件/研究交付和真实输入拒修结论记为COMPLETED，自然资格/真实改善与生产校色继续未验收。随后按Order7完成VCO-07设计与next-task交接并准备为READY；准备不启动实现、真实请求或发布，历史BLOCKED快照不覆盖当前表格状态。
- **Conditional work:** `VCO-05` 的隔离试验须有明确执行授权；单次失败应完整交付失败证据并停止，不能自动追加试验。`VCO-07` 另须实际通过证据；`VCO-08` 另须新的真实时序协议及独立验证。缺少这些前提不能自动启用模式或准备后继，也不在建板时预先记成 BLOCKED。

## Tasks

| Order | Task ID | Title | Status | Dependencies | Design document | Handoff |
|---:|---|---|---|---|---|---|
| 1 | VCO-01 | P0-A：版本化片段视觉提示契约落地 | COMPLETED | None | docs/task-designs/VCO-01-design.md | None |
| 2 | VCO-02 | P0-B：原生色彩元数据与编码链诊断 | COMPLETED | None | docs/task-designs/VCO-02-design.md | docs/task-handoffs/VCO-02-handoff.md |
| 3 | VCO-03 | P1-A：色彩与动作连续性分析器 | COMPLETED | VCO-02 | docs/task-designs/VCO-03-design.md | docs/task-handoffs/VCO-03-handoff.md |
| 4 | VCO-04 | P1-B：诊断接入观察门槛与版本化恢复 | COMPLETED | VCO-03 | docs/task-designs/VCO-04-design.md | docs/task-handoffs/VCO-04-handoff.md |
| 5 | VCO-05 | P1-C：单次 20 秒隔离生成与跨题材验证 | COMPLETED | VCO-01 | docs/task-designs/VCO-05-design.md | docs/task-handoffs/VCO-05-handoff.md |
| 6 | VCO-06 | P2-A：轻度非破坏性校色与修订血缘 | COMPLETED | VCO-03, VCO-04 | docs/task-designs/VCO-06-design.md | docs/task-handoffs/VCO-06-handoff.md |
| 7 | VCO-07 | P2-B：经实测准入的版本化整段生产模式 | COMPLETED | VCO-04, VCO-05 | docs/task-designs/VCO-07-design.md | docs/task-handoffs/VCO-07-handoff.md |
| 8 | VCO-08 | P3：原生跨窗口续写后端验证与接入 | IN_PROGRESS | VCO-01, VCO-04 | docs/task-designs/VCO-08-design.md | docs/task-handoffs/VCO-08-handoff.md |

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

- **Completion evidence:** 2026-10-24 `IN_PROGRESS -> COMPLETED`。独立色彩 sidecar、完整逐帧声明、PNG CRC/profile、显式 SDR raw RGB、输入/工具/证据 SHA 冻结、映射与链路 recorded/unknown 已落地；四项验收与实际控制样例对应关系见 `docs/task-designs/VCO-02-verification.md`。独立审查问题已修复，定向检查 166+2 项均退出 0；收尾复核 375/375 源码/测试/脚本身份无变化，git diff --check 通过。用户已明确将全库后移至最后一个任务，当前全库已停止：首轮 412 项、第二轮 700 项部分通过均不算全库通过。源生产接口及原 JIM-08 记录保持原值，改动留在工作区。按用户本轮仅收尾当前任务的指示，不准备或启动 VCO-03；其状态和引用保持原值。
- **Start evidence:** 2026-10-23 用户明确要求“完成任务 VCO-02”，完整读取本任务设计与入口交接后执行 `READY -> IN_PROGRESS`；保留交接路径。实施和验证账本为 `docs/task-designs/VCO-02-plan.md`。
- **Goal:** 能将颜色差异定位到模型原始输出、解码、裁片、超分或最终编码的具体阶段。
- **Scope:** 新增 `src/video_ai/media/colorimetry.py`，为 generated.mp4、原生尾帧 PNG、source.mp4、超分帧和最终成片提供独立色彩诊断 sidecar。记录 ffprobe 色彩字段、pix_fmt、编码器及实际解码/转换规则，明确统一分析空间；审查 video、frames、composition_video 的转换路径。初期保持 `validate_video_probe()` 严格返回字段契约，不以改标签冒充颜色转换，不盲目强制 Rec.709。
- **Acceptance:** ① 各阶段诊断能追溯媒体身份与处理步骤，包含 color_space/color_primaries/color_transfer/color_range，缺失或冲突明确保留 unknown 与风险。② 比较使用实际解码帧及明确分析空间，区分压缩差异与颜色解释差异；源解释不明时不强猜矩阵或范围。③ Rec.709、不同色彩标记、full/limited、未标记和解码/编码往返样例均有可复核诊断结果。④ 处理前后原生 16fps、PTS、帧数、尺寸和精确映射不变，旧媒体记录重放及旧 probe 契约不变。
- **Dependencies:** `None`；直接复用现有媒体校验与帧提取能力。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 2.2、5、9、10 节；② `src/video_ai/media/video.py`；③ `src/video_ai/media/frames.py`；④ `src/video_ai/media/composition_video.py`；⑤ `src/video_ai/runtime/production_scene_clips.py`；⑥ `src/video_ai/runtime/production_scene_upscale.py`；⑦ `src/video_ai/runtime/production_scene_composition.py`；⑧ `tests/unit/test_composition_video.py`。
- **First action:** 梳理原始输出到最终编码的实际色彩转换点，完成独立 sidecar 的输入输出和 unknown 处理设计，不修改旧 probe 返回结构。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；本次未运行色彩链样例或修改媒体处理。
- **Preparation evidence:** 2026-10-23 在 VCO-01 完成记录之后，按 Order 2 选中本任务；直接依赖为 None。已完成并关联 `docs/task-designs/VCO-02-design.md`，冻结旁路接口/schema、真实转换点、显式 SDR 分析空间、unknown/失败规则及测试验收；随后写入并关联 `docs/task-handoffs/VCO-02-handoff.md`，执行 `NOT_STARTED -> READY`。准备仅为详细设计与交接，未新增 colorimetry 源码、未运行转换样例或开始实现。

### VCO-03

- **2026-10-26 当前完成记录：** `IN_PROGRESS -> COMPLETED`，按用户已选择的AI路线和最新Acceptance五项验收完成。软件分析器、原24源240项AI实验、六项集中结果及后续90项字面片段重播补充均已交付；校准/封存/一次检查、真实弃权、弱标签来源、独立审阅处置与producer闭包有现有证据。最新重播补充记录62项测试通过、90原始receipt及6252显示ROI帧摘要核验，当前仅复核191项既有文件引用的bytes/SHA相符，未重跑测试/检测。集中入口 [六项结果](VCO-03-AI-final-results.md) 与 [重播补充](VCO-03-temporal-replay-results.md)。原正式双人Benchmark未验收、实验profile不具生产资格作为限制保留；不再显示为本任务阻塞。本次只校正VCO-03状态，VCO-04按用户上一轮“仅设计”范围保留NOT_STARTED，不创建后继交接或启动实现。

- **2026-10-26 AI路线收尾登记：** 在上项阻塞解除已落板后，依据用户此前明确的“继续处理吧”“你一直把这个任务做完，中间不要停了”授权，执行 `READY -> IN_PROGRESS`，仅核对已交付AI结果并登记完成，不重新开展素材采集、实验或模型推理。保留 `docs/task-handoffs/VCO-03-handoff.md` 为历史入口；状态以本表最新记录为准。

- **2026-10-26 当前契约与阻塞解除：** 用户已明确“ai校准的就可以，我不想填表格”，并反复授权继续直至完成。按 `docs/task-designs/VCO-03-design.md` 最新Acceptance，将已完成的AI路线作为主任务验收口径；保留原正式人审协议未验收、实验profile不可用于生产的限制。读取本任务历史pause handoff并核对AI路线契约/交付证据后，执行 `BLOCKED -> READY`。这是当前状态口径校正，不补造真人标签、六类ready profile或历史验证结果，也不重新运行检查。

- **AI route final delivery (2026-10-26, explicit continuous-completion request):** 用户选择的无需人工表格AI实验路线已完成；原色彩四项封存结果保留，另15源90项亮度几何控制全部完整测量，12校准/3新检查，先封存后一次18项检查。相机TP3/FP0/TN12/FN0；动作位置代理TP2，时间重播仍弃权，不宣称自然动作已通过。50项测试及最终闭包核验通过。最终入口 `docs/task-handoffs/VCO-03-AI-final-results.md`；没有修改本表正式人审状态、启用生产或启动VCO-04。

- **AI experiment delivered (2026-10-25, current user-selected route):** 用户明确“ai校准的就可以，我不想填表格”。独立AI路线24源/240结果已完成：230完整测量、10资源弃权，4阈值/2缺正常类null，先封存后一次检查。相机端到端召回28.6%如实保留。当前AI交付不再要求人工表；原正式benchmark BLOCKED独立留档，不阻塞AI路线，未冒充完成真人验收/启用生产或VCO-04。专项设计 `docs/task-designs/VCO-03-AI-experiment.md`，交付 `docs/task-handoffs/VCO-03-AI-calibration-results.md`。

- **Latest input audit (2026-10-25):** 24候选/2,868原生帧和20源正式regions/truth复核通过，原200控制配方与兼容源绑定一致；新增40项recipe/native映射计划未构造。24源来源许可完整归并，已验证原血缘无已知跨split冲突，独立性/分组仍未冻结；保留正式标签缺口与AI来源。当前集中说明 `docs/task-handoffs/VCO-03-calibration-input-status.md`。16项软件身份保持，未拟合/评估留出，BLOCKED与VCO-04 NOT_STARTED保持。

- **Latest motion evidence (2026-10-25):** 用户要求继续处理。affine测量与clip anchor重置分离，108项定向检查通过（首次合跑超预算保留，随后五文件硬限时分批复核）；原样边界分数75.998/77.799降至1.161/1.749。独立AI背景支持使新增区域在实际第60帧取得camera_jump峰值5852.966，原背景该帧仍失败。原视频/200控制/正式ROI保持，新增6次诊断累计22次、独特case仍13。四新增候选技术准备已就绪但未正式准入；双人表已接收并保留AI来源，正式标签/血缘分组/校准尚未齐。完整证据见交付文末与 `D:/VideoSi/projects/video-ai/continuity-benchmark/motion-registration-fix-20261025/delivery-final-check.json`。BLOCKED与VCO-04 NOT_STARTED不变。

- **Corrected material accepted:** 用户对people_03两项修订视频回复“没问题”，已绑定具体播放/控制身份，位置问题本轮关闭；22项弱可见性反馈保留。单用户描述性反馈已汇总，未自动赋予normal/anomaly或伪造第二人/观看时间。B独立审阅入口和证据见交付文末；200个已构造控制、0正式双人标签/0校准/0profile及BLOCKED保持。

- **people_03 correction (latest):** 用户接受v5选区，手/钢笔分开建正式区域；190旧控制复用、10个people_03控制重建，逻辑总数仍200。只两项操作RGB有变化：遮挡hand、局部色偏pen；两项100帧作用范围核对，其他8类800帧与旧版RGB相同，新30帧独立重算通过。4,876行ROI、双人空表各2,940行。新目标选择尚须校准入口支持精确重放（默认会选所有subject），此兼容问题与原来源/时基/血缘/双人标签缺口均未解除。新两项集中入口和证明见交付文末。源码16/16未变，无校准或VCO-04。

- **User review feedback round:** 用户表示其余项目没有问题；保留people_03两项位置修订、22项弱可见性观察。单用户描述性反馈已汇总，未自动分配normal/anomaly、未补造观看范围/时间或第二审阅者。people_03新手部/钢笔区域100帧草稿待确认，旧控制/正式truth未替换；详见交付文末最新记录。当前200构造/0正式双人标签/0校准，BLOCKED不变。

- **Confirmed ROI / actual controls (latest):** 用户明确确认20段最新版逐帧ROI，已冻结20源/2,388帧正式regions/truth；既有控制通道实际构造200/240变体、23,880显示帧，逐帧PTS/播放帧数全部核对，600帧独立RGB重构通过。当前ROI确认20、控制200、真人控制审阅/校准/profile均0；仍缺1户外/3动画，血缘与12/12未冻结，青蛙毫秒时基33/34步长与当前校准器恒定步长限制不兼容，未改源时间/绕过检查。新双人待审入口和证据见 `docs/task-handoffs/VCO-03-remaining-delivery.md` 文末。软件16/16身份未变，未重跑pytest，BLOCKED/VCO-04 NOT_STARTED保持。

- **User content feedback:** 用户表示当前视频都没有问题，已按此前要求的20段拟用ready视频登记内容接受意见，未补签逐帧ROI/血缘/完整播放记录或控制标签。具体记录与下一步框审阅入口见 `docs/task-handoffs/VCO-03-remaining-delivery.md` 末尾更新；状态及原计数不变。

- **Manual-download follow-up (previous snapshot):** 2026-10-24 手动下载续办：21/21 请求文件完整解码；18 个新来源颜色 resolved，已完成 2,172 个连续原生 ready 帧。复用旧三段 312 帧后，共 21 段 / 2,484 个完整 ready 原生帧。31 个待确认项目来源共 3,593 帧播放/逐帧材料、7,186 行未签署 ROI；240 个原有 case 位置保留，实际 ROI 确认/控制/真人审阅/评估均为 0。 拟用 24 个位置已有 20 个颜色/原生帧就绪：people 4、animals 4、transport 4、outdoor 3、indoor 4、animation 1；另有一段人物备用。至少还缺 outdoor 1、animation 3，内容/独立血缘未确认还可能增加替换需求。Spring 和狗缺必要颜色声明，黄花现有解释不受支持；不得补猜 Rec.709。 2,484个选中RGB与只读退出闭包、新包离线材料、旧包2,769文件及16/16软件身份均复核通过。详见 `docs/task-handoffs/VCO-03-remaining-delivery.md`；新入口是原S下remaining-work/manual-intake-20261024/review-package/index.html，进度已写回remaining-progress.json。原BLOCKED状态/Design/Handoff保持，无VCO-04启动或软件重测。

- **Remaining-checklist execution (previous snapshot):** 2026-10-24 用户明确要求执行清单、复用已有成果、先推进自动工作再集中交付真人材料。本轮复核原三文件，完成 20 个 ISO 原媒体地址的下载/有界续传尝试，并尝试 11 个 Wikimedia 版本、3 个 NPS 来源与 2 个 Shotstack CC0 文件；新增 8 个完整下载，总计 11 个版本/10 个待确认项目来源。两版 BBB 同源；3 个 MP4 包复制封装副本不增加来源数，原 PTS/time_base、名义 fps、颜色及包 SHA 相同，容器平均速率差异留证。Caminandes [240,336) 、青蛙 [240,360) 及人物片 [120,216) 共 312 个原生 ready 帧完整通过只读 reader；另七源仍颜色 unknown/unsupported/conflicting。已准备 10 源 1,105 帧的完整播放与 2,210 行未签署 ROI 草稿、血缘/未冻结 split 草稿、240 个待构造位置及双人空标签表；实际 ROI 确认、控制构造、真人审阅、真实评估均为 0。最终数据复核退出 0：523 份 ready 记录/522 个不同原生源帧，含拒绝候选和旧单帧重复证据；16/16 冻结实现文件与三份旧媒体未变。交付记录 `docs/task-handoffs/VCO-03-remaining-delivery.md`；逐源持续进度在原候选目录 `remaining-progress.json`，审阅入口为其 `remaining-work/review-package/index.html`。24 源门槛仍缺 21 个颜色 ready 候选区间，素材/颜色与真人依赖分别记录；不将“已有审阅包”登记为全部准备完成。VCO-03 仍 BLOCKED，无状态转换，既有 Design/Handoff 引用不变，未重新实现/测试软件或推进 VCO-04。
- **Remaining-work delegation:** 2026-10-24 用户要求输出剩余工作清单以交由另一个任务执行；已整理 `docs/task-handoffs/VCO-03-remaining-checklist.md`，按既有设计列出补下载、颜色/连续区间、血缘/分组、ROI/真值、240 控制审阅包、真实双人观看/裁定和校准/一次留出评估的输入及完成标准。清单不代表执行结果；VCO-03 状态仍为 BLOCKED，Handoff 和 Design document 引用不变，不准备 VCO-04。
- **Public sourcing evidence:** 2026-10-24 用户明确选择“你来寻找吧”，授权代寻有明确许可的公开素材，设计中已记录这一窄范围更新。已整理 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/public-source-candidates.json` 及 CSV：六题材各 4 个、共 24 个候选，含 20 个逐页标注 CC0 的 ISO Republic 视频和 4 个独立动画项目的许可依据，split 仍未冻结、独立血缘仍待核验。已从公开镜像下载 Big Buck Bunny、Elephants Dream teaser、Caminandes 三个 MP4，保存 ZIP/媒体 SHA 与下载凭据；原文件未改写。流元数据初查前两者缺必要颜色声明；Caminandes 已经 VCO-02 完整声明核验、显式转换第 300 帧为 6220800 字节 srgb_rgb24_v1，并通过只读 batch 复核，原 PTS=300000、time_base=1/24000。该单帧不代表完整 4 秒素材：完整 ROI/真值素材 0、控制 case 0、真人观看 0、真实校准 0。ISO 主站本地下载超时，公开 Blender 镜像可达；后续从本清单继续下载/核验或寻找可达且同样有明确许可的替代素材，无需要求用户手写 catalog。状态仍 BLOCKED，详情见候选目录的 sourcing-status.json 和现有验证/交接。
- **Preparation follow-up:** 用户随后询问“你可以帮我做吗”。已核对现有采集/双人观看协议，并创建 `D:/VideoSi/projects/video-ai/continuity-benchmark/preparation-a94b200fad4842de9847302838bcab81`：24 个素材待选位置、六题材各 4 个且拟定每类 2/2 split、240 条待构造/待审阅记录的 JSON/CSV 和准备状态。计数、唯一性、分层与空审阅者检查通过，日志 `D:/VideoSi/cache/video-ai/logs/vco03-preparation-kit-a94b200fad4842de9847302838bcab81.log`。这些是 draft，不是校准 catalog/人工 labels；实际素材 0、已构造 case 0、人工审阅 0、真实校准 0。素材来源选择已询问，尚未获得目录或公开视频采集选择；未下载、扫描素材或修改代码，BLOCKED 状态及验收不变。
- **Software evidence:** 2026-10-24 只读批量 reader、固定 NumPy/OpenCV CPU 区域配准和六类原始 score、独立报告/证据、控制变体与校准/一次留出工具、四个离线命令已实现。独立审查的重要问题经失败回归和修复处理；最后设计指定五文件 101 passed、252.66 秒、退出 0，16/16 源码/测试/脚本/pyproject 大小/mtime/SHA 与启动快照一致，git diff --check 通过。完整命令、日志与限制见 `docs/task-designs/VCO-03-verification.md`；20-case fixture_only 校准保持 unverified，不是实际人工校准。
- **Blocker evidence:** 2026-10-24 先写入 `docs/task-handoffs/VCO-03-handoff.md` 的 pause 阻塞交接，再执行 `IN_PROGRESS -> BLOCKED`。设计 Acceptance 第 4 项所需 24 个真实独立 source、240 控制 case 的实际双人完整观看/裁定标签及六类 ready real_benchmark profile 尚未提供或取得；已询问明确 catalog/labels 路径，当前未获材料。解除须有可访问且符合既定协议的真实目录、标签和对应证据及身份校验结果；不伪造观看者/标签，不按 fixture 登记完成，不准备 VCO-04。仅 `.git` 只读下保留本地工作区改动，全库仍留至 VCO-08。
- **Start evidence:** 2026-10-24 用户明确要求“VCO-03 完成任务”；完整读取本任务设计与入口交接后执行 `READY -> IN_PROGRESS`，保留原交接路径。实施账本为 `docs/task-designs/VCO-03-plan.md`。仅执行设计指定定向检查，全库留到 VCO-08；真实素材和双人观看标注尚待明确提供，不以 fixture 代替。
- **Goal:** 对接缝、片内漂移、长链累计、主体和动作异常生成可复算的只读报告，并区分合理变化与不可比内容。
- **Scope:** 新增 `src/video_ai/media/continuity_analysis.py`；消费 VCO-02 的颜色解释与分析空间，对父子片及场景长链分析接缝基线、亮度/色度/饱和度和剪切趋势、可匹配区域累计变化、光流/主体位置/镜头轨迹和动作重置。配对色差仅用于可对齐的同一内容；用多题材标注样本校准阈值和告警，样本数量、指标与阈值在专项设计中确定，不捏造全局阈值。本任务不写生产准入、不自动校色。
- **Acceptance:** ① 合成亮度/色度接缝、主体局部变化、片内渐进偏色、三段累计漂移及突发动作重置能形成对应定位证据，不只依赖全图 MAE 或直方图。② 日落、阴影、运镜、新背景和遮挡保留变化依据；无可靠匹配区域或对齐不可信时返回 not_comparable/unverified，不必然判错。③ 报告包含输入/参考 SHA、算法版本、比较帧编号、时间戳、证据帧、可比性与置信度，冻结输入可复算。④ 标注样本、校准依据及误报/漏报检查可追踪；自动报告不宣称动态观看通过。
- **Dependencies:** `VCO-02` 的色彩 sidecar、统一分析空间和 unknown 规则。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 6、10 节；② 本板 VCO-02 实际交付的设计与色彩诊断产物；③ `src/video_ai/media/frames.py`；④ `src/video_ai/media/video.py`；⑤ `src/video_ai/runtime/scene_clip_observations.py`；⑥ `docs/task-designs/JIM-08-continuity-diagnosis.md`。
- **First action:** 收到明确实施启动指令并读取完成设计与入口交接后，先在 `tests/unit/test_colorimetry.py` 为只读批量 reader 写失败测试，验证不创建源 RunLogger/文件/锁、严格证据复核及唯一源/工具的有界校验，再实现 `load_color_analysis_set`。按设计仅做定向检查，全库留到最终任务。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；尚无本任务算法、校准阈值或验证结果。
- **Preparation evidence:** 2026-10-24 在 VCO-02 已完成后，按用户“设计下一个任务吧”选中 Order 3；用户明确选择本任务设计样本采集/标注流程及 NumPy + OpenCV CPU 方案。已完成并先回填 `docs/task-designs/VCO-03-design.md`，冻结只读批量接口、六类检测器、精确输入输出、资源限制、24-source/240-case协议、防泄漏/一次留出评估、定向检查及验收；一次独立可实施性审查提出的七项问题均已细化。随后写入并关联 `docs/task-handoffs/VCO-03-handoff.md`，核对直接依赖 VCO-02 设计/源码/验证及真实样例入口后执行 `NOT_STARTED -> READY`。本次仅文档设计和交接，未安装依赖、实现、采集/标注、运行 pytest/校准或启动服务；没有算法或真实校准通过记录，全库仍留到最后任务。


- **2026-10-25 继续准备证据：** 原生不等间隔PTS、显式局部目标重放及profile源事实核对已修复；最终106项定向检查退出0。20源/2,388原帧及people03十变体1,000帧RGB复算通过，39,207个封存文件身份未变。5个软件文件因修复更新，旧16项快照保留。仍缺1户外/3动画、独立来源/12+12分组及真实双人逐项标签，未拟合或运行留出；状态仍BLOCKED。集中材料 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/index.html`，证据 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/continuation-verification.json`。


- **2026-10-25 两表接收与AI后续审核：** akkc/qzw各2460行已封存核对，结构错误0；940项相同、1520项不同，双方观看时间均空，来源含AI建议/整体转录，不伪造成真人独立标签。用户已明确后续视频交AI审核。新增4文件均完整解码、颜色resolved，480原生帧/全部播放PTS及960条未确认选区草稿已核验；24位置均有原生帧草案，但正式ROI仍20源、控制200/240，独立血缘/split/真实校准仍未齐，状态保持BLOCKED。入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review.html`，证据 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review-verification.json`。


- **2026-10-25 原始诊断样例：** 仅原计划校准侧两个来源，复用13个控制，1,560显示帧/3,107完整比较/11,704条分数记录；未拟合、未看留出、未用AI代填表计算阈值。背景空间支持不足原因已由保存向量复核；原始分数与弃权一并展示，16项软件身份未变。HTML/MD/CSV/SVG入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/index.html`；浏览器交互自动验证受环境限制未完成，数据与链接已验。此为未校准诊断，不登记VCO-03正式完成或准备VCO-04。

- **2026-10-26 AI时间片段重播补充已交付：** 复用12校准来源＋3个此前未测来源，90项控制全部执行；冻结后新检查TP9/FP0/TN6/FN0、周期负例弃权3，标签内覆盖率83.3%。校准72总项中48有标签、24未确认标签排除；重复变体不作为独立来源。62项定向测试及90原始receipt/6252显示ROI帧摘要核验通过，一次独立审阅问题已附加验证/明确报告解决，未重测调参。详见 [补充结果](VCO-03-temporal-replay-results.md)。本轮授权AI实验完成，正式双人Benchmark状态不变，VCO-04未启动。

### VCO-04

- **Completion evidence（2026-10-27）：** `IN_PROGRESS -> COMPLETED`。已实现可选advisory_v1策略冻结、ordinary报告完整来源核验、不可变诊断epoch/源码依赖归档、本地分析/重评/风险回应、全前缀资格及生成/超分/合成/发布守卫。机器unverified不升级passed；同源已确认缺陷跨代次保留；诊断恢复不重POST模型或改原片。411项不同定向用例逐项通过（最终核心74、真实CPU链路8、旧兼容329，其中旧发布25项首次失败已修复并全部重跑）；407/407源码身份一致，git diff --check退出0。完整逐项验收/原始日志与限制见 `docs/task-designs/VCO-04-verification.md`，操作说明见 `docs/task-designs/VCO-04-operations.md`，独立审查及处置见 `docs/task-designs/VCO-04-review.md`。真实播放声明仍仅为明确软件fixture，未宣称六类生产profile/正式Benchmark/实际视频质量通过；未启动模型服务、真实GPU/付费试验、生产发布或后续任务。全库仍留在VCO-08；.git只读，改动留在当前工作区。

- **Start evidence（2026-10-26）：** 用户明确要求“完成任务VCO-04”；完整读取已关联设计和入口交接后执行 `READY -> IN_PROGRESS`。按现有设计实施与定向验证，不运行全库、真实推理或发布；保留历史成果及交接路径。

- **Preparation evidence（2026-10-26）：** VCO-03按用户接受的AI路线已登记COMPLETED后，用户继续询问交接文件；按Order 4选中本任务，完整复核已关联 `docs/task-designs/VCO-04-design.md` 及直接依赖的软件/ordinary报告与AI证据限制。设计已完成并经一次独立可实施性检查，尚无实现或测试通过声明。先写 `docs/task-handoffs/VCO-04-handoff.md`，再关联Handoff，最后执行 `NOT_STARTED -> READY`。已明确首个缺失/旧epoch诊断不得准入的RED用例。此状态只表示设计和交接就绪，不启动实现、模型服务、GPU/付费试验或发布；旧VCO-03 pause文件仅为历史入口。

- **Goal:** 将机器连续性报告接入现有观察与恢复流程，保证未观察、失败或不可比的结果不会自动升级为通过。
- **Scope:** 新增 `src/video_ai/runtime/scene_continuity_records.py`，持久化输入 SHA、算法版本、对比帧和报告；接入 production_scene_clips 现有观察链及修订/恢复。保持“视觉输入身份 → 技术与色彩报告 → 机器诊断 → 完整动态观察 → 超分合成及最终观看 → 显式发布”的顺序。诊断算法变化仅重算报告及准入，不重新生成原片；提示/模型变化和校色变化分别作用于相应依赖。
- **Acceptance:** ① failed、unverified、不可比、报告缺失/漂移及缺少有效 human_video/具备实际完整播放能力的 agent_video 观察，均不能被写成视频 passed。② 报告绑定准确媒体/参考/算法身份，可中断恢复、重算并保留失败证据；静帧或自动分数不能代替完整动态观察。③ 仅改诊断算法不会重新 POST 模型请求或重出原片；未知任务结果沿原 request/prompt_id/HTTP 记录恢复，不补单。④ 旧冻结 run 仍按原契约恢复，新记录的缺项或 SHA 漂移在推进/发布前拒绝，相关修订与恢复用例有实际结果。
- **Dependencies:** `VCO-03` 的分析接口、报告字段、可比性状态和算法身份。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 3、6、9、10 节；② 本板 VCO-03 实际交付的设计与分析报告；③ `src/video_ai/runtime/production_scene_clips.py`；④ `src/video_ai/runtime/scene_clip_observations.py`；⑤ `src/video_ai/runtime/production_scene_pipeline.py`；⑥ `src/video_ai/runtime/scene_revision_records.py`；⑦ `tests/integration/test_scene_pipeline_recovery.py`；⑧ `tests/integration/test_scene_revision_flow.py`。
- **First action:** 对照 VCO-03 的实际报告契约和现有观察状态流，完成准入、记录身份及算法变更恢复的详细设计。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；尚未改变原观察、恢复或发布门槛。

### VCO-05

- **Completion evidence（2026-10-27）：** `IN_PROGRESS -> COMPLETED`，完成本轮已授权首例验证范围。软件122项、聚焦旧兼容3项、播放修复34项均有既有退出0记录；完整旧生成文件扩展运行中断未登记通过，全库仍留VCO-08。唯一真实请求 `c76c898d-303f-460e-912e-e54e384efbda` 3798.752秒成功，321帧原片/321原生解码PNG/320帧20秒映射及无损RGB证据、1874有效资源采样和原run不变均齐全。新版兼容片交付后，用户“没问题，继续吧”，按前序全片四项验收上下文记录human_video接受；不伪造独立播放事件或观看时间。最新 `user-observation.json`、`final-assessment.json`、`completion-check.json` 绑定新版SHA `ae175cc0e6819039a524f23c7642e0a667ada071ea61486adbf717155eb71ca6` 及原片血缘，媒体/报告身份复核、git diff --check均退出0。交付 `docs/task-handoffs/VCO-05-results.md`、验证 `docs/task-designs/VCO-05-verification.md`；pause handoff保留为历史入口。仅该硬件/模型/768×432/16fps/20秒鸟类跟拍案例通过，跨题材/另一运镜/更长/多窗尚未验证且未授权追加；未启用whole_scene_v1、未发布、未改原JIM-08续接验收。

- **Resume evidence（2026-10-27）：** 依据用户“没问题，继续吧”恢复当前VCO-05收尾，`READY -> IN_PROGRESS`。剩余范围为核对并登记已接受首例的验收、更新交付和任务板；按本板、完整设计、历史pause handoff、results/verification及实际user-observation/final-assessment顺序读取。首个动作是复核已绑定新版SHA的用户接受与技术/资源闭包，不重新推理或运行旧intent。

- **Resolution evidence（2026-10-27）：** 新版320帧/20秒兼容片交付后，用户回复“没问题，继续吧”。结合前序针对完整20秒及主体颜色/光照/构图/动作的验收询问，记录为该确切样片的human_video肯定反馈，原文保留、不补造独立播放器事件或观看时间。已复核新版SHA `ae175cc0e6819039a524f23c7642e0a667ada071ea61486adbf717155eb71ca6`及原片/无损/映射血缘，写入 `D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/user-observation.json`、`final-assessment.json`；旧技术结果保持历史unverified原值。完整读取关联设计与pause handoff后执行 `BLOCKED -> READY`，保留handoff为历史入口。仅解除当前首例观察缺口，不自动追加跨题材、启用生产或开始后继实现。

- **Playback repair evidence（2026-10-27）：** 用户报告旧无损审阅片“视频损坏无法打开”；旧片SHA和完整解码仍正常，RGB High 4:4:4 Predictive存在普通播放器兼容性问题。已追加 `D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/review-playback.mp4`（High/yuv420p、faststart、320帧/20秒、2863820字节，SHA `ae175cc0e6819039a524f23c7642e0a667ada071ea61486adbf717155eb71ca6`），明确为CRF16有损播放副本，原片/无损RGB证据及原case不覆盖。34项回归退出0，无新模型推理；完整动态观察仍unverified、BLOCKED保持。后续用户反馈绑定新版SHA和playback-review.json原片血缘，既有handoff已同步；不能把文件修复或后台COM探测当作动态观看通过。

- **Latest evidence（2026-10-27）：** 软件与唯一真实首例技术已交付；因没有有效完整动态播放反馈，先写 `docs/task-handoffs/VCO-05-handoff.md` 后执行 `IN_PROGRESS -> BLOCKED`，未登记COMPLETED。122项软件/CPU媒体验证及3项聚焦旧兼容退出0；旧生成文件扩展检查中断未算通过，全库仍留VCO-08。原任务 `c76c898d-303f-460e-912e-e54e384efbda` 仅一次POST、3798.752秒、history success；321帧原片/321原生解码PNG及320帧/20秒无损RGB审阅片、精确PTS/[0,320)与全部RGB核对通过。1874/1874资源采样有效，峰值总GPU21657MiB、系统内存33298898944字节，内存余量小。3011原run文件及1107依赖结束后不变，自有服务停止且锁释放。集中交付 `docs/task-handoffs/VCO-05-results.md`、逐项验证 `docs/task-designs/VCO-05-verification.md`。采样未见明显重大变色/突变，但full_video_observation=unverified、production_eligible=false。解除条件为用户对确切SHA审阅片完整播放20秒并确认颜色/光照/构图/动作，或提供实际全播放能力agent_video结论；不能从静帧、自动分数或沉默推断。跨题材未授权不追加，后继状态不变。

- **Start evidence（2026-10-27）：** 依据上述明确完成请求，完整读取关联设计后执行 `READY -> IN_PROGRESS`。新增隔离工具与RED/GREEN检查；尚未POST真实首例。保留原有未提交改动、原run及后续任务状态。

- **Preparation evidence（2026-10-27）：** 用户要求“完成任务VOC-05”，按本板唯一对应任务VCO-05处理。完整读取B阶段、VCO-01实际契约及原run准入后，完成并关联 `docs/task-designs/VCO-05-design.md`，`NOT_STARTED -> READY`；实施计划 `docs/task-designs/VCO-05-plan.md`。独立可实施性审查已完成，补充逐帧色度/明暗截断/采样图要求。当前授权包含本任务规定首例，不自动追加跨题材GPU任务。

- **Goal:** 以隔离真实试验证明或否定当前资源下 20 秒整段候选的可用性，并明确跨题材验证范围。
- **Scope:** 按既有 B 阶段先完成通用 runner/helper 设计与软件检查，再在已授权条件下执行一次隔离请求。首例只读使用原 run `20261021-014723-4ebdc1fecab2` 的 scene3 已准入图，不将该题材写入通用实现；保持 Wan2.2 双专家、768×432、16fps、40 步、CFG3.5、Euler/simple、15 步切换及案例原首片 seed，321 请求帧精确保留 [0,320)。冻结 case/graph/模型/输入/提示，记录 GPU、内存、期限、HTTP 和输出。初例通过后，跨题材样片按另行明确的实际授权覆盖不同主体/材质及另一种镜头运动；不自动下载后端或追加 GPU 任务。不修改原生产预算、不写回原 run。
- **Acceptance:** ① 软件验证覆盖 321/320/[0,320)、身份漂移拒绝、重复执行不二次 POST、失败不降规格、原 run 不改写。② 真实执行前核验资源、模型与输入及服务拥有权，仅管理自有服务；一次 POST，结果不明只查询原任务，OOM/超时/非法输出/明显外观失败保留现场并停止。③ 原始输出、原始帧、精确映射、SHA、审阅副本、日志、耗时和资源证据齐全；20 秒技术结果、采样外观和完整视频观看结论分开。④ 仅技术、完整动态观察和资源记录同时通过才形成 VCO-07 准入证据；无观看能力或缺有效观察时保留 unverified。⑤ 跨题材能力只按实际已验证范围表述；未授权或未完成的跨题材部分明确保留待办，不能把单例外推。本任务不以整段样片取消原独立续接验收。
- **Dependencies:** `VCO-01` 的已冻结、已审查视觉提示契约及纯视觉渲染。诊断可按既有 B 阶段独立记录，本任务不以 VCO-02/03 的实现作为首例执行的必要输入。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 8、10、11 节；② `docs/task-designs/JIM-08-color-repair-design.md` 全文，重点 B、颜色与动态验收；③ 本板 VCO-01 实际交付的契约及验证证据；④ `docs/task-designs/JIM-08-verification.md`；⑤ `docs/task-handoffs/JIM-08-handoff.md`；⑥ `src/video_ai/runtime/production_visual_templates.py`；⑦ `src/video_ai/runtime/scene_clip_records.py`；⑧ `scripts/bootstrap.ps1`。实际案例媒体路径从原准入记录读取后再冻结，不在本板猜测。
- **First action:** 只读定位既有 B 阶段指定案例的准入记录，完成隔离 runner、单次提交恢复、321/320 帧预算和观看证据的实施设计。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；RTX 5090 D v2 24GB 的 321 帧能力尚未证明，本板未提交真实推理或追加样片。若实际失败，只有完整交付已限定试验的失败证据且无未完成范围时，才可据实判定该验证任务完成；失败不是生产准入。

### VCO-06

- **2026-10-30 当前完成记录：** `IN_PROGRESS -> COMPLETED`。按用户本轮状态纠正及后继准备要求和主设计修订Acceptance，VCO-06的软件/研究交付结项；软件实现、194项最终定向、178项规定兼容及实际16段审计/6838原件保护证据齐全。本轮重新核验20个源码/测试文件和三份已有日志/实际delivery的bytes/SHA相符，未重跑测试。真实已知轴正例仍0，无合格自然profile、真实候选或改善验收通过，production_eligible=false/ready_for_propose=false不变；这些事实作为能力限制保留，不再作为本交付任务的BLOCKED状态。详见 `docs/task-handoffs/VCO-06-status-correction.md` 及其resolution-evidence.json；旧closeout和旧pause的BLOCKED原值留档，不改签。原Design/Handoff引用保留，之后按Order7准备VCO-07，不启动其实现。

- **2026-10-30 结项复核启动：** 在上述 `BLOCKED -> READY` 已登记后，依据本轮明确状态纠正与后继准备请求执行 `READY -> IN_PROGRESS`；范围仅为核对已有交付和按修订Acceptance登记结项，不重新实现、采集、观看或执行模型请求。输入顺序为本板、主设计全文、原pause交接、自然软件交付及其delivery/closeout；原入口交接保留为历史上下文。

- **2026-10-30 状态纠正／结项口径修订：** 用户指出“任务状态不对，同时完成下一个任务的准备”。完整复读关联主设计和同任务pause交接后，将主设计Acceptance第3、5项显式改为已实现软件、规定检查及真实输入审计/保守拒修结果的任务结项；自然资格、真实候选及改善仍未验收，不授予生产资格。此为结项范围的显式修订，不是宣称旧自然素材阻塞已经技术解决。依据本轮用户纠正要求和既有194/178检查、实际16段/6838原件保全证据，登记 `BLOCKED -> READY`，保留原Design/Handoff引用。原任务板/主设计/pause交接已按原字节归档，见 `D:/VideoSi/projects/video-ai/vco06-natural-qualification/status-adjustments/20261030-015108-25ce410f2be24b8f928ae8bd5427d1a5/entry-manifest.json`。下方全部BLOCKED说明为历史快照。

- **Natural software closeout（2026-10-30）：** 按用户“你继续完成”补齐独立自然研究全阶段、严格闭包profile loader、自然候选/观察/恢复与只读status。一次独立审查8项Important及相关完整性边界均以RED/GREEN闭合；最终194项定向597.45s、规定六文件178项兼容5690.52s均exit0，无skip。实际16段完整登记观察重核为4段拒修/12段保留未知适用性，6838原件及原pilot前54项bytes/SHA/mtime不变；10个产品/CLI SHA匹配最终测试独立库存，10个测试/辅助文件未漂移、2个CLI help通过。交付 `docs/task-handoffs/VCO-06-natural-software-results.md`，新根 `software-audits/20261029-existing16-7c3b470462224447a52a0aca62f69d44/closeout.json`。软件缺口已补，真实已知轴正例仍0，无合格自然profile/真实候选/改善通过；当前BLOCKED、Design/Handoff及其他任务状态引用保持，无新模型/GPU请求、额外采集/观看任务、生产发布或后继准备。原交接/任务板/主设计改写前已归档；所有本轮测试和审计结束。

- **Pilot actual viewing（2026-10-29）：** 用户看完新4段，已接收4份真实导出，原schema和事务/媒体/参考/集合/时间校验全部通过，原标签保留unverified。p01报告与参考完全不一致且target/structure/motion=false，p02报告左侧掉落异常疑点，p03/p04报告没有问题；0个已确认已知轴色偏正例，未校准/生成profile或候选。实际接收日志exit0，原4文件bytes/SHA/mtime不变；证据 `docs/task-handoffs/VCO-06-pilot-results.md` 首节及 `pilot-audits/20261029-observed-e4f0aec9aa474349afa442783cd4bdbf/pilot-observation-result.json`。按方案停止本次4请求pilot，不扩批，不要求重做16段已完成观看。BLOCKED及全部Design/Handoff/其他任务引用保持，不把观看完成当改善验收。

- **Four-request pilot（2026-10-29）：** 用户要求继续新小批路线，先冻结独立4次预算，再完成4/4真实原片、4/4正式技术导入和196原生帧/PTS/sRGB核验，实际POST4次，无补单；54项旧原件bytes/SHA/mtime不变，服务/锁关闭。冻结前98项定向检查退出0。新片固定相机/物体，只作development_seen重建稳定性探索，不冒充独立盲测组；实际人类观看/自然标签/已知轴尚未确认，无自然profile或候选。结果 `docs/task-handoffs/VCO-06-pilot-results.md`，入口新根 `pilots/20261029-stationary4-c2a7e6583ce44798be1753c5c6607d19/observe-pilot-04-c459d8cff3cb.html`。原12段观看不重做；本轮4次预算已用完，不自动扩批。BLOCKED及Design/Handoff/其他任务引用不变，仅更新本任务证据与同址交接。

- **Actual observation intake（2026-10-29）：** 用户已完成当前12段development观看；找到13份实际原始导出，10份v1未确认记录（9段，含一次重复提交）经原schema及真实来源校验入库，3份草稿原样保留。12段实际浏览器缓存具有完整原生ended/played时间范围，47/48个实际回调不补写；另存用户全体观看报告。用户澄清10段“希望变光=是”只是观察到变化，解释视图单独修正意图，原JSON不动。1份中性报告经澄清一致，唯一mild草稿仍无已知修正轴且只有1组，9段标签保留unverified，形变/增物/动作中变色记录永久保留；0个合格已知轴正例，不足各方向跨4组覆盖，五阈值仍null、qualified_directions=[]，无profile或候选。结果 `docs/task-handoffs/VCO-06-observation-intake-results.md`，21项原件bytes/SHA/mtime不变。只更新本任务证据和同址交接，BLOCKED/Design/Handoff及其他任务不变；不再以未观看为阻塞，不自动超出固定24次采集预算补单。

- **Qualification continuation（2026-10-28）：** 按用户“读取交付记录、复用现有输入包，继续资格校准、真实候选和改善验收”执行。已复用纸质研究run并从真实原图/全49帧及固定配对坐标重放9×9特征，原baseline紧凑字节完全匹配；新增规范b/o、等权统计、固定支持比较和独立只读资格审计，132项当前定向检查退出0。最终审计awaiting_qualification/退出3，qualified_directions=[]、五阈值null；1个已见开发来源不足独立资格实验，0个已确认自然正例/0个新holdout，真实已知轴Precheck亦缺，未拟合/渲染候选或登记改善。结果 `docs/task-handoffs/VCO-06-qualification-continuation-results.md`、协议 `docs/task-designs/VCO-06-natural-qualification-protocol.md`；交接已更新。原输入/报告/交付568文件集合、bytes/SHA/mtime及最终451个Python文件身份均不变，旧r2 profile不变。只补本任务当前证据，BLOCKED及Design/Handoff/其他任务/后继保持，不产生新的状态迁移；无新模型/GPU请求、实际发布、Git写入或全库回归。

- **Research input delivery（2026-10-28）：** 按用户“我要一个可以用于任务的”“继续当前任务”实现并实测正式研究导入、独立context/epoch、全帧分片报告与探索性自然基线。入口 `docs/task-handoffs/VCO-06-research-input-delivery.md`；新run `20261028-145342-f5100beeb167` 为 `research_input_ready`，49视频帧+1参考ready，48 adjacent+49 reference共97/97 comparable，49帧基线各1024有效配对，88项定向检查退出0。旧v1/r2及旧失败保留；独立资格profile和实际完整播放Precheck仍缺，`ready_for_propose=false`。方案从文档推进到实际可读取的研究输入，不登记候选改善或VCO-06完成；本行仍BLOCKED，Design/Handoff及后继状态不变。

- **Latest design revision（2026-10-28）：** 用户明确回复“我我同意你修改方案”，批准正式研究素材导入与自然校色资格的新路线。主Design document仍为 `docs/task-designs/VCO-06-design.md`，其顶部已关联 `docs/task-designs/VCO-06-natural-input-design.md`；原v1/r2合同、profile与失败证据保留。最新实际输入资格见 `docs/task-handoffs/VCO-06-input-qualification-results.md`：两份新真实49帧素材技术/色彩通过，但当前已声明首帧配对不满足旧自然残差门槛；织物完整报告还受输出资源限制，独立素材缺正式研究导入与完整播放预检。新路线依次实施CPU基线/冻结研究协议、研究导入/分片报告、独立自然资格研究及新策略候选。新准入阈值尚未测得，方案批准不构成解除阻塞：本行保持BLOCKED，不登记COMPLETED，不准备VCO-07，全库仍留VCO-08。修订前四份文档原字节和源码/profile基线在 `D:/VideoSi/projects/video-ai/vco06-plan-revisions/20261028-102315-be4e162f9dd1/baseline.json`。

- **Current blocker evidence（2026-10-28）：** 完整复读本任务设计后，先写 `docs/task-handoffs/VCO-06-handoff.md` 的pause交接，再执行 `IN_PROGRESS -> BLOCKED`；未登记COMPLETED。显式默认关闭研究候选、恒定校色、前后报告、原生媒体、不可变观察/修订/恢复及生产来源拒绝已实现；186个不同专项用例与178个兼容用例分别有通过证据，合计364，完整命令与已修正测试失败保留在 `docs/task-designs/VCO-06-verification.md`。最终当前源码159单元、4真实CPU/历史流程及精确六文件178兼容检查均退出0，兼容耗时5755.44秒；扩展事务结果早于最后归档路径预检两行修复，未冒充一次全量合跑。收尾433/433 Python源码/测试/脚本身份与最终快照一致；原run3011/3011文件集合、bytes/SHA/mtime_ns不变，无新增或缺失；git diff --check退出0。用户授权自行选样后，选择原run白鹭首段并审计另外两段已接受首片，但三份原选图均不能证明sRGB，真实VCO-02参考门槛为unknown/unverified/pixels=null；旧run也无当前冻结epoch/assessment和实际校色Precheck。真实候选改善及完整动态观看仍未验收，不满足设计Acceptance3、5。真实输入审计 `docs/task-handoffs/VCO-06-real-input-audit.md`；解除条件为取得并核验适用自然原片、具有有效sRGB解释的独立原选图和当前诊断/真实完整播放预检，之后再恢复候选与实际观看验收。原入口已按字节归档，路径/SHA见交接。production_eligible=false；无新模型/GPU请求、实际发布或后继准备，全库仍留VCO-08，其他任务状态与引用保持原值。

- **Start evidence（2026-10-27）：** 用户明确要求“完成任务VCO06”。完整读取已关联设计与入口交接后执行 `READY -> IN_PROGRESS`，保留原交接路径。实施账本为 `docs/task-designs/VCO-06-plan.md`；沿用已封存r2校准与研究候选范围，不重新拟合、不启动模型推理。完成须同时满足软件及实际完整动态观察验收，不能用fixture代替。

- **Preparation audit（2026-10-27）：** VCO-05先登记COMPLETED后按Order6选中本任务，观察NOT_STARTED、Design document=None、Handoff=None。只读核对VCO-03实际AI实验profile（production_eligible=false，含检测阈值，无校色专用幅度/适用profile）及VCO-04观察/恢复接口；不能把色偏检测分数当曝光/白平衡/色度修复上限。核对见 `docs/task-handoffs/VCO-06-input-audit.md`。用户已回复“同意，按这条路线走”，授权先补离线AI修复校准，再据真实结果完成本任务详细设计与后继准备；执行协议与账本为 `docs/task-designs/VCO-06-calibration-design.md`、`docs/task-designs/VCO-06-calibration-plan.md`。准备阶段保持原状态和引用，不创建部分next-task交接，不启动生产校色或新推理。VCO-05完成不回退。

- **Goal:** 对主体和运动完整、仅存在轻微可定位色偏的视频提供默认关闭、可回退的独立修复候选。
- **Scope:** 新增 `src/video_ai/media/color_repair.py` 和 `src/video_ai/runtime/scene_color_repair_records.py`；基于可匹配稳定区域估计有幅度上限的曝光/白平衡/色度变换，时间平滑避免频闪，保存原片、候选片、参考 SHA、算法版本、参数及前后报告。接入候选的原生校验、观察、修订及恢复。修复幅度与适用门槛须由已校准样本及专项设计确定，不执行全图强制直方图匹配、逐帧独立重调或背景冻结。
- **Acceptance（2026-10-30结项口径）：** ① 默认不修，已稳定原片和不可比内容不自动处理，重大颜色/结构/动作异常不以校色冒充解决。② 软件/研究交付须有定向/兼容结果与实际素材审计；资格不足时保留未知或拒修，真实轻度偏色改善、无新增频闪/材质失真和完整前后动态观察独立保持未验收，不能由结项状态冒充通过。③ 原片及其接受记录不被覆盖，失败可回退并保留证据。④ 当前研究候选不可生产采纳；未来以修复片继续生成须另行通过生产资格并建立显式修订与父子血缘。⑤ 默认关闭、不可比拒修、参考漂移、候选恢复和血缘失效均有验证结果；依主设计修订Acceptance第3、5项登记本轮软件/研究任务完成。
- **Dependencies:** `VCO-03` 的可比区域、漂移诊断与校准依据；`VCO-04` 的报告准入、观察与恢复身份。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 7、9、10 节；② 本板 VCO-03 和 VCO-04 的实际设计及交付记录；③ `src/video_ai/planning/scene_revision.py`；④ `src/video_ai/runtime/scene_revision_records.py`；⑤ `src/video_ai/runtime/production_scene_revision.py`；⑥ `src/video_ai/runtime/production_scene_clips.py`；⑦ `src/video_ai/runtime/production_scene_upscale.py`；⑧ `src/video_ai/runtime/production_scene_composition.py`。
- **First action（已结项）：** 读取 `docs/task-handoffs/VCO-06-status-correction.md` 和最新主设计口径；软件/研究交付已完成，16段观看不重做。未验收的自然资格/改善和生产禁用限制继续保留，不自动恢复采集或将历史pause当作当前任务状态；下一步按Order7准备VCO-07。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；未启用校色、生成修复片或改写已接受媒体。
- **Preparation evidence:** 2026-10-27用户批准“先补离线AI校色校准，再做VCO-06”路线后，完成r2的24源/2868原生帧/1776控制、先封存后原12源一次检查，4/10方向条件合格，production_eligible=false。23项定向测试通过、24/24来源闭包复核、阶段顺序与fit/evaluate复算一致，失败/82项弃权和首轮格式适配失败现场全部保留，结果为 `docs/task-handoffs/VCO-06-calibration-results.md`。据实完成并关联详细设计，fresh-context builder唯一重要配对路径问题已明确；另有真实工具探针验证候选编码/颜色声明/16fps时间映射。先回填设计、写入并关联 `docs/task-handoffs/VCO-06-handoff.md`，再将本任务 `NOT_STARTED -> READY`。当前仅后继准备完成，未开始生产产品实现、未生成真实修复候选或登记实际观看通过；完整动态验收仍按设计保留。VCO-05保持COMPLETED，全库仍留VCO-08。

### VCO-07

- **2026-11-01 06:14 完成（IN_PROGRESS -> COMPLETED）：** 已按当前主设计及用户移除重复检验的覆盖要求完成软件、三源独立生成与实际观看准入、463帧1080p超分、完整28.9375秒/16fps/原PCM字幕合成、真实最终观看、独立显式发布及同run零新增重放。最终两次用户原话“视频配音都没有问题”“继续吧 没问题”与补问范围原件保留；正式接受05:44:08、发布回执06:04:05、最终闭环06:14:12。closeout session23458退出0，phase final-film-closeout-phase-aaf18f158320412da5246c30e90908e5/result.json证实complete=true、源POST3/超分POST463、收尾及重放新增模型POST0/邮件尝试0、交付字节/mtime/文件身份不变。正式文件D:/VideoSi/output/video-ai/20261029-202326-3adf41844095.mp4/.srt/.delivery.json，视频SHA8de8460233e5735d1cd8c7fa1fe4709447ec3f9f0d6f07adc299452ec59ce832；实际连续超分2.756秒/帧，约80.57倍提速。完整验收汇总docs/task-designs/VCO-07-completion-report.md。当前任务无剩余项；本轮按用户“当前任务完成”限定结项，VCO-08保留NOT_STARTED及原外部前提，不预造后继设计或通过证据。以下IN_PROGRESS等均为历史。

- **2026-11-01 05:10 成片已就绪：** 修复后463/463帧04:43:56完成，最近20帧均值约2.76秒/旧222.071秒，约80倍；正常session40798于04:55:10返回awaiting_final_review/exit3。phase214d/result.json记录463超分POST、本次334、源POST3、forbidden=[]、published=false。完整28.9375秒1080p候选candidate.mp4，SHA8de8460233e5735d1cd8c7fa1fe4709447ec3f9f0d6f07adc299452ec59ce832，技术检查均passed。保持IN_PROGRESS：需要该候选新的完整最终视频/旁白/字幕反馈、独立publish及零新增重放；旧源反馈不能代替。VCO-08仍不开始。

- **2026-11-01 03:47 去除重复检验后续跑：** 用户明确“把这些检验都去掉，没有用”，覆盖whole媒体逐写/发送全量proof/父目录/inventory/工具及逐帧object_info要求。旧生产在129完整帧、无待处理intent时停止；原源片3POST/已看反馈保留。移除回归128项通过10.23秒，一次审查无发现；恢复时发现已退出Windows进程对象被误当活锁，GetProcessTimes退出FILETIME修复经真实RED及42项GREEN1.51秒、同一审查追加无发现。首次恢复phaseab4340仅preflight拒绝/0新POST；修正后已且仅已启动新session40798、日志748f9c79754349e0aed2db8cd5d61ae2、phase214d9d35e305419d8398ef4b05b9a0d5、354软件库存。当前保持IN_PROGRESS，实测新吞吐/463帧/合成/新最终观看/显式发布/零新增重放仍待。下列旧20441/冻结要求为历史，VCO-08不启动。

- **2026-11-01 01:52 生产持续：** 同一session20441/43872（launcher24204）及owned Comfy38648实际均活跃，100/463完成帧、intent101/超分POST101，原源POST准确3；最后frame.json01:49:59.707。350b918/ef96ff01/phase2140941b保持同次生产，不停止/重启或修改运行中实现，不重做source/analysis/epoch/源观看。保持IN_PROGRESS，余下全帧/合成/新完整成片视频音频字幕反馈/独立发布/零新增重放待，VCO-08不启动。

- **2026-10-31 22:47 生产持续：** 同一session20441/worker43872（launcher24204）和owned Comfy38648实际仍活跃；已完成50/463帧，intent51，最后frame.json22:45:20.967。350 b918/ef96ff01/phase2140941b不变，连续帧约222秒，用户已获知整批粗估约28小时。未停止/重启/修改生产软件，也未重做源片/分析/epoch/源观看。保持IN_PROGRESS，继续监测现有调用；全463帧、合成、新最终完整观看/音频字幕、独立发布和零新增重放仍待，VCO-08不启动。

- **2026-10-31 19:45 真实首帧通过：** 同一session20441/43872、350 b918/ef96ff01/phase2140941b继续运行。owned Comfy38648健康后首个RealESRGAN1.30秒，intent19:42:33/accepted19:43:12/submission19:44:05及frame.json19:44:30保存；输出原writer验证1080p/2392431bytes。当前1/463完成帧/1submission/1intent，243保留文件，后续帧继续。HTTP修复已越过实际失败点，不再重做或重启；任务仍IN_PROGRESS，完整463帧/合成/新最终观看/显式发布/零新增重放仍待真实证据，VCO-08不启动。

- **2026-10-31 18:52 当前推进：** 保持IN_PROGRESS。前次27558退出2是实际HTTP首帧预算超时，非GPU/用户阻塞，0intent/超分POST/完成帧；新HTTP修复保留原180帧协议及300服务准备，每实际socket写完整guard，pure read/wait仅deadline/cancel，fresh whole服务先准备，默认/segmented/原intent不改。98相关+23原源事务通过，独立review无Critical/Important/Minor且另16项通过；真实HTTP模型fb004710为167.566秒/35source/1夹具POST/0生产网络，非真实交付。fbc71681冻结350软件b918c65e，225保留文件/219图/首帧request/Engine05a相符，原345仅2改5新增。新resume-reviewed-http-media.py已按持续授权调用一次session20441/logef96ff01、phase2140941b；现在只监测此调用，不改冻结代码、不重问源观看。最终463帧/合成/新观看/独立发布/重放仍待，VCO-08不启动。

- **2026-10-31 17:36 继续执行：** 依据当前“已关闭”和原持续完成授权，`READY -> IN_PROGRESS`，继续同一run超分/合成至最终真实验收。消费已读历史handoff、主设计、345软件dc2e5bae、225保留状态036c和新GPU解除983eb9d5；首动仅执行resume-media-after-awesun-agent.py一次，普通make_video完整准入，保留正式219提取与首帧request，不重生成源片/分析/epoch/源观看。publish=False，无自动重试。最终观看/发布/重放仍待真实结果。

- **2026-10-31 17:36 阻塞解除：** 用户回复“已关闭”，Chrome40572已退出GPU。首次快速57b09d16仅发现已授权向日葵的新代理19220；其准确路径D:/Program Files/Oray/AweSun/agent/AweSun.exe与原flutter程序均签名Valid、同一证书E17E09B3，属同一已授权应用。Ruling：沿用原“剩余未关闭的不用关”对向日葵的授权，只添加本run这个实际核验的准确代理路径，不修改全局策略/未知身份规则，不关闭应用。803801b2准备退出0，真实原策略+6准确路径预检983eb9d5 verified/external_pids=[]/free22470MiB，0POST；原225文件和343软件逐项仍符，追加两个准确操作脚本冻结345软件dc2e5bae。已完整读取主设计/历史pause，登记`BLOCKED -> READY`；剩余463帧/合成/新最终观看/独立发布及重放不变，原handoff保留历史入口。

- **2026-10-31 16:29 当前阻塞：** `IN_PROGRESS -> BLOCKED`，已先刷新同一路径pause handoff并保留旧原字节。session9118/d9a66ce6于16:24:18真实退出1：原219PNG已由writer严格验证/提升，extraction-ready/extraction及首帧request/graph/input_copy已保存；当前225文件/0intent/0超分POST/0完成帧。失败为GpuBusyError，唯一external PID40572=chrome.exe/C+G，完整路径系统拒读，原5项桌面授权保持；没有关闭任何应用或放宽未知身份。7982a11d快速实测仍仅40572阻塞。新343软件9b14d5ab及225文件audit036c016b准备5957df62退出0，恢复入口resume-media-after-gpu-busy.py先快速GPU预检，再普通生产，不重提取219图。异步请求用户让Chrome退出GPU已发出；真实原策略实测external_gpu_task=false后按BLOCKED->READY->IN_PROGRESS恢复，持续授权仍有效，无需另问普通继续授权。最终463帧/合成/新观看/发布/重放均待，VCO-08不启动。

- **2026-10-31 15:34 实际恢复：** 保持IN_PROGRESS；三源真实观看/作者回应已正式ready，不重问。原219PNG批次修复69项及覆盖修复201项通过；新发送Artifact去重154项通过，一次独立审查无发现。实际covered profile87974退出0；v2预算模型c57c57f7通过179.212/180秒、0真实网络，不等同GPU验收。准确341文件库存9d3edbec冻结4e4ff128退出0，原220文件/Engine05a保持；按持续授权启动一次resume-native-batch-media.py，session9118/logd9a66ce6，phase437a0f02。等待此调用，禁止重启/修改冻结实现；实际463帧/合成/最终新观看/独立发布及零新增重放仍待。详见operations顶部，VCO-08不启动。

- **Current production evidence（2026-10-31）：** 三源219/110/134帧的真实完整观看、当前05a报告和作者风险回应均已正式准入；review-phase3d0d63a2/result.json确认all_source_gates_ready=true、原源POST3/新源POST0。旧媒体20544在0超分intent/HTTP时身份核验后停止-1，仅保留1379-byte inputs.json。live-proof修复323项及预算/事务36项通过，独立core/integration审查APPROVE，真实ready完整proof4.360/4.375秒、原180秒帧期限不变。321软件df51清单及持锁恢复audit26b0通过；原RunLock自动归档29100死锁。当前唯一恢复native77536/worker14976/日志98e29cfa，阶段media-resume-phase-d0dde8ef7c5a4e56a358b8c5ad0988e5；只监测原调用，不重复源生成/分析/观看或启动。463帧超分、合成、新的最终音频字幕完整观看、独立发布及零新增重放尚待真实结果，保持IN_PROGRESS，不提前准备VCO-08。

- **2026-10-31 current continuation:** 保持IN_PROGRESS，三段源片全部技术完成且用户实际完整观看已确认；第三段原文“刚完整看完，飞行及外观正常”已绑定其飞行原图。旧a5第一段已写报告通过历史Engine只读4111项闭包验证。提升证明修复及独立审查资源问题经RED后六文件87 passed/62.33秒，准确日志02f5f389d4344b1f8a25154f5d70f175。新293文件软件35184bae898b4f54ad239583a87de54d已冻结，现按持续完成授权串行新epoch/当前诊断/风险回应与准入，不重生成原三源片、不要求重复观看。超分、合成、最终完整观看、显式发布/重放仍待实际结果，不能COMPLETED或准备VCO-08。

- **265 software actual advance started（2026-10-30，本次）：** 前置软件/源文件/保留状态/实时GPU准入复核通过，已启动原普通入口消费dfc0ad370eaf49f993519d95bc4bfb3b新audit；日志a635bd00df8e43b6bc398c83c120cede，start8c2b595e32324c5e9257ff96213e4d15，native74696/worker23164。当前IN_PROGRESS并监测这一调用，不并发第二入口或修改265库存源码，不将启动当作模型/观看/交付通过。

- **Network guard context corrected（2026-10-30，本次持续执行）：** 0278bfcb0f7747e8ae41bbedfc64ce32 CPU回归证实发送线程丢失调用方已认证ContextVars；保留原全部send/字节/inventory守卫，仅以copy_context运行network worker。新上下文回归与原有限HTTP传输共10项GREEN（4ef97b9007844a019ee30b6fb508ec76）。为避免已知冷重准入阻塞，agent在0模型intent/HTTP/GPU租约时中止02de6cd/97fb CPU调用，native35487退出1无产品result；b851dfd6/7e6e7f6f审计确认源3011/保留1005/262软件未变，原RunLock按死PID7840证据归档锁。64778835b2954fffbf60f846b543886f新准备退出0，265库存554913ebee1443ca89971125e0930653、新audit dfc0ad370eaf49f993519d95bc4bfb3b、当前epoch/实时GPU准入均核验。继续在持续完成授权下用新audit调用原post-directory operator，模型POST仍0，不重建修订或索取重复继续确认。

- **Pre-model health fix / continuous execution（2026-10-30，本次）：** 在用户持续完成授权下，目录后调用484f4df6973b41f2bc985db3fe15aab0/start d9e926abc8404652a1888c8480fbf4dd处于CPU准入时，新增回归2387fa/da608aec证明快速健康响应会被完整准入日志耗尽2秒预算。agent在0模型intent/HTTP/GPU租约时中止该调用（native28132退出1，无产品result），原RunLock按已退出PID29268证据归档旧锁；8f8970cc0006481ebb11793e399f3aa6审计确认原3011源文件/保留1005状态及259软件均未变。仅将健康证据写入改为真实持锁检查，原模型字节/inventory准入及所有网络/模型时限保留；完整健康/服务23项GREEN（f6f3da9edb69478fa67f8374bebdb520）。4e945f54d52f46f29af098dce395114e恢复准备退出0，新262库存17fde906ecf84fcfa716b3d5deb4dd6e/new audit1bba71bff899498d82490a0c35422022就绪，0POST/实时GPU准入通过。当前仍IN_PROGRESS，继续消费新audit调用原post-directory operator，不重新询问已授权继续动作，不准备VCO-08。

- **Directory recovery resumed（2026-10-30，本次）：** 观察READY后按用户“继完成当前任务，直到完成”登记`READY -> IN_PROGRESS`。以准确f55864933bae4558abdbee5ced7f1332审计及实际用户原文调用已准备的advance-production-after-directory.py；保留原epoch/输入/graph/request，实时重核软件/状态/源文件/GPU准入后普通推进，publish=False，仍不登记模型/观看/交付通过。

- **Continuous completion authorization（2026-10-30，本次）：** 用户明确回复“继完成当前任务，直到完成”，解除目录修复后的继续执行授权阻塞，登记`BLOCKED -> READY`。消费现有259库存/f558恢复audit、9项GREEN及真实CLI解析0的已准备状态，不重跑既有软件检查/创建修订。该授权支持持续处理本地启动前软件/目录问题并推进同一VCO-07；未知原模型结果按原intent恢复、每准确clip一次首次POST、实际完整观看及独立显式发布门槛继续按设计执行。旧交接保留为历史入口，不再对已授权的例行继续动作反复询问。

- **Latest service failure / prepared recovery（2026-10-30 20:18+08）：** 本轮用户“已关闭，剩余未关闭的不用关，现在继续吧”授权的702d6b普通推进已退出1，result35608f06c4ff4c429904810a32ec67ae为ServiceStartError/service exited before health:2；已越过桌面准入，自有Comfy CLI因run/comfy/user不存在退出，0模型intent/POST/技术输出，原3011文件未变，worker33404/session80152结束，run/GPU锁释放。目录准备已在持锁资源/服务启动前修复，新增2项RED准确复现；完整服务9项GREEN（53df470401a6468fa056a3bf7172f77c）及实际冻结命令追加--help解析退出0。10c19b1dd8154c62946bd98c1dcc1cd3准备审计退出0，case下新259库存453818f3a24c474ea1e8e25ee9ff70ac、新audit f55864933bae4558abdbee5ced7f1332均就绪；新advance-production-after-directory.py未执行。已先备份并刷新同路径handoff，再登记`IN_PROGRESS -> BLOCKED`，等待服务失败后的新一次明确继续授权；旧桌面阻塞已解决，5项准确路径授权保留，不再要求关闭应用。软件既有证据不重跑，真实观看/交付未验收，VCO-08仍NOT_STARTED；以下运行中/旧阻塞均为历史记录。

- **Post-GPU advance started（2026-10-30，本次）：** 新advance-production-after-gpu.py已且仅已启动一次，前置软件/原source/保留状态/实时桌面准入复核通过。日志`vco07-production-post-gpu-authorized-702d6b02528041f3b149166b2a8cd787.log`，case下start `production-start-post-gpu-35608f06c4ff4c429904810a32ec67ae.json`，publish=False/automatic_retry=False，当前IN_PROGRESS等待此调用结果，不能重复调用或预记真实通过。

- **GPU recovery restart（2026-10-30，本次）：** 观察READY后，按实际用户“已关闭，剩余未关闭的不用关，现在继续吧”登记`READY -> IN_PROGRESS`。从已审计当前epoch/输入/graph/request零POST部分状态执行advance-production-after-gpu.py一次，参数为6a232ef82e684d62a3a2a1ddb2c46ba4恢复audit及上述实际授权；5项准确桌面路径仅本run调用生效，普通产品准入全部保留，publish=False/无自动重试。等待此新调用实际结果，当前不登记模型/观看/交付通过。

- **GPU blocker resolution（2026-10-30，本次）：** 用户明确回复“已关闭，剩余未关闭的不用关，现在继续吧”，授权保留当前桌面应用并继续同一run。只读核验准确5路径（原4项加WPS桌面子进程），采用仅本run调用有效的desktop_approval_scope，纯C/未知身份/其他run仍拒绝；23项桌面/资源定向检查退出0，GPU真实预检无未允许external_pids。7f9f1fd1eb1f4567b26b5177e4047fb7恢复审计退出0，报告`revision-audit-gpu-recovery-6a232ef82e684d62a3a2a1ddb2c46ba4.json`，确认原3011文件、保留1005状态、原epoch完整当前、256软件库存及zero_model_posts=true。记录`BLOCKED -> READY`；旧交接作为本次入口历史保留，不重跑已有core/兼容/whole、不重建修订、不关闭应用、不准备VCO-08。

- **Latest stop / new blocker（2026-10-30 18:38+08）：** 用户“同意，继续执行”已解除旧授权阻塞并实际执行一次130ced3e53a9461c9f13f07e5bf876d1；本次退出1，case下`production-result-post-epoch-c2276ff54bb44d198e74293fa6244598.json`为source_clips/GpuBusyError。初始epoch已提交、第一scene input/graph/request已保存；GPU准入拒绝8个未在已批准桌面名单内的C+G进程。0模型intent/POST/技术clip/output、scene2/3 pending，原3011文件结束后字节不变，worker39764已退出/run锁释放，无自动重试/关闭应用/策略修改。先备份旧交接并刷新同路径pause handoff后执行`IN_PROGRESS -> BLOCKED`，Design/Handoff不变。解除条件为用户决定并实际解除这8项准入阻塞及明确允许失败后同一目标继续，再按已提交epoch和5份scene-clips记录核验当前现场；旧inputs-only audit/operator不可直接复用或清理绕过。停止状态1005文件库存为case下`production-stop-gpu-aa0ceaba777f4893bf680bf044d3c432.json`。既有软件通过证据不重跑，真实观看/交付未验收，VCO-08保持NOT_STARTED；下方“当前运行/旧授权阻塞”为历史记录。

- **Authorized advance started（2026-10-30，本次）：** 用户“同意，继续执行”已作为新operator实际授权原文。准确b02ddab7d18142f085b867b4623e1c10恢复audit、253库存/零POST部分状态及source基线的前置核验通过；advance-production-after-epoch.py仅启动一次，日志130ced3e53a9461c9f13f07e5bf876d1，case下start为production-start-post-epoch-c2276ff54bb44d198e74293fa6244598.json。当前IN_PROGRESS并等待该调用结果；publish=False，无自动重试，不重建目标或重复软件检查，不预记真实验收。

- **Restart evidence（2026-10-30，本次续接）：** 以上“同意，继续执行”为明确恢复请求；观察READY后登记 `READY -> IN_PROGRESS`。从已修复、已审计的零POST部分状态执行advance-production-after-epoch.py，参数为准确新恢复audit及实际授权原文；不重建修订、不重跑已有软件检查、不执行旧advance或归档代码，VCO-08不变。

- **Resolution evidence（2026-10-30，本次续接）：** 用户明确回复“同意，继续执行”，解除失败后等待新授权的阻塞。完整读取关联主设计及当前pause handoff后，核验新恢复audit b02ddab7d18142f085b867b4623e1c10仍指向准确目标20261029-202326-3adf41844095、253库存SHA仍为fb5a5b6a5d719e9652866e53f913134095414ef1a7345498d1e503a2f7154314，目标scene-clips仍仅有inputs.json且无活动Python。登记 `BLOCKED -> READY`，保留handoff为历史入口；本次授权为同一目标的一次普通推进，每scene一次首次请求，publish=False，原失败/未知/OOM停止及禁止自动重试限制保持。

- **Current blocker / handoff（2026-10-30，本轮）：** 唯一真实advance在CPU预检超时退出1，0真实POST、原3011文件字节未变；已按“失败/未知/OOM停止，无自动重试”停止。初始epoch Reader时点已最小修复，16项CPU单元检查退出0；新253库存及零POST部分状态恢复audit（b02ddab7d18142f085b867b4623e1c10）已退出0，下一次operator已准备但未执行。当前等待失败后的明确继续执行授权。已先备份旧入口交接并刷新同路径pause handoff，再登记 `IN_PROGRESS -> BLOCKED`；Design/Handoff引用保留。解除条件为用户明确允许同一目标继续首次真实生成并核验新库存/audit；无回复不当授权。取得后按 `BLOCKED -> READY -> IN_PROGRESS` 继续，不能重跑既有软件检查、重新创建修订或准备VCO-08。

- **Latest actual failure and CPU fix（2026-10-30，本轮）：** 唯一真实advance 41cd4eed35de4a9b913201b8805d4ebb已退出1，source_clips阶段TimeoutError continuity deadline expired；真实POST=0、无模型输出/epoch intent，结果确认原3011文件字节不变。已按失败停止，无第二次真实推进。根因是初始epoch的300秒Reader提前在whole准入_context之前启动；最小修复改为预检成功后创建，保持epoch/分析各自共享300及原模型intent7200不变。RED正确复现，修复后scene_continuity_records全文件16passed退出0。旧whole六例/core347/13兼容304/服务7原证据保留，不重跑。新253软件库存和失败软件250文件原字节归档已准备，当前仅运行零POST部分状态的只读恢复audit；准确路径见operations/verification。尚无真实GPU/观看/交付通过，不登记完成，不准备VCO-08。

- **Actual advance in progress（2026-10-30，本轮）：** 全部规定软件门槛通过后，另存250文件库存`implementation-post-compat-8e401a809bba46e582f0fa58ff80d51c.json`；当前真实修订审计846475d0615647a9a2d05f7faed01b4e退出0，报告`revision-audit-444e07a3e29b4cf4bcc0e8387282c218.json`确认原3011文件基线。随后已且仅已对`20261029-202326-3adf41844095`启动一次普通advance，publish=False，日志`vco07-production-advance-once-41cd4eed35de4a9b913201b8805d4ebb.log`，case下start为`production-start-3dfeb346131c4511be41818dc182d6c9.json`。当前原进程仍运行，最后检查真实POST为0，未取得推理/观看/发布结果。下一动作是等待/核验这一次调用的结果及现有intent，不得重复启动advance；具体库存与case绝对路径见operations。VCO-07仍IN_PROGRESS，VCO-08保持不变。

- **Current software verification（2026-10-30，本轮续接）：** 规定软件门槛已通过，任务仍为IN_PROGRESS。原whole交付期望修正后的贯通、common延后预算、首请求拒绝停止后续scene三项均在9f4d3729be9e41c088027eeb5f00dca7日志中PASSED；最后lost-response测试修正全局计数误判后，定向4ea944c44493454196d7e31dc5edaff3日志1 passed、721.28秒、退出0，验证每clip仅一次、原请求保持及缺预算不写不提交。与原268a6487批前两项构成六例逐项通过证据；core347/13兼容304/服务7原结果保留。本轮产品源码未改，真实修订不重建；下一步刷新库存/审计并普通advance一次。没有真实观看或发布通过，不登记COMPLETED，不变更VCO-08。

- **Resume evidence（2026-10-30）：** 用户明确要求“读取 docs/task-handoffs/VCO-07-handoff.md，继续 VCO-07，从交接记录的失败点接着处理，不要从头重做”。完整读取主设计及历史pause交接后登记 `PAUSED -> IN_PROGRESS`，保留交接路径。剩余范围仍为whole失败及未执行恢复验证、刷新软件库存/审计现有准确修订、单次真实advance及独立观看/超分合成/发布重放验收；按任务板、主设计、交接/verification、plan/operations、失败日志/接口的顺序读取。首个动作是核定缺最终观察时delivery的blocked契约；不重跑347 core/13兼容304项、不重建修订、不启动全库或VCO-08。

- **Pause / conversation handoff（2026-10-30）：** 用户澄清“不是给08，是要让下一个对话干活，你现在干太久了”，要求当前对话停止并由下个对话继续同一VCO-07。已先更新 `docs/task-handoffs/VCO-07-handoff.md` 为pause交接，再登记 `IN_PROGRESS -> PAUSED`。规定core最终347、13兼容逐文件304、服务7项均退出0；最新whole批2 passed/1 failed、退出1，在缺最终观察时produce_scene_delivery返回blocked而新测试期待awaiting_final_review，后3个recovery未执行。未完成真实GPU/观看/交付，不登记完成，不修改主设计验收或VCO-08的范围、状态、Design/Handoff。当前无存活Python测试；原入口交接/任务板/设计已备份，准确日志、现有真实修订、过期软件库存及下一步均见pause交接，不重新准备修订或重跑已通过兼容。

- **Implementation progress（2026-10-30）：** 显式whole/segmented预算、准入冻结闭包、schema2提示/schema3渲染身份、全媒体消费者和修订恢复已接入。核心及扩展12文件424项、运行时审查修复78项、common失效修订1项、Windows大文件晋升22项均退出0；五个规定兼容单元文件通过。服务器重启打断的集成/实际修订不计通过，现按原请求与规定序列恢复。独立审查及逐项日志见 `docs/task-designs/VCO-07-verification.md`，当前操作边界见 `docs/task-designs/VCO-07-operations.md`。真实源片、当前诊断与完整观看、超分合成、最终观看、显式发布和重放尚未齐备，保持IN_PROGRESS，不准备VCO-08。

- **Start evidence（2026-10-30）：** 用户明确要求“完成VCO-07”；完整读取已关联设计与next-task交接后登记 `READY -> IN_PROGRESS`。实施计划为 `docs/task-designs/VCO-07-plan.md`；先执行预算RED/GREEN，再贯通冻结/全消费者/修订恢复，按设计区分软件与真实生产验收，全库仍留VCO-08。

- **Preparation evidence（2026-10-30）：** VCO-06按本轮修订口径先登记COMPLETED，再按Order7选中本任务，观察原状态NOT_STARTED、Design/Handoff均None。已完成并先关联 `docs/task-designs/VCO-07-design.md`；一次独立只读builder check返回“nothing important left”，记录 `docs/task-designs/VCO-07-preparation-review.md`。直接输入VCO-04观察/恢复与VCO-05首例实际接受不冲突；2211项输入身份（含321原生PNG、1874资源JSON）已核验，准备前490项源码/测试/脚本库存保存在 `D:/VideoSi/projects/video-ai/vco07-preparation/20261030-015108/input-check.json`。设计冻结显式mode、独立execution预算、schema2 whole提示/无环绑定、schema3渲染身份、全消费者/源目标revision/恢复及精确测试/验收；只有实测768×432/16fps和320保留帧/321请求帧有限工程包络，不外推跨题材/更长/多窗。随后写入并关联 `docs/task-handoffs/VCO-07-handoff.md`，最后执行 `NOT_STARTED -> READY`。仅准备完成，无新产品代码、测试执行、模型/GPU请求、超分合成或发布；不把READY记成已开始实施，不改变VCO-08。

- **Goal:** 将已通过真实验证的整段生成能力，以显式新模式接入完整生产链，并保持旧分段模式可精确恢复。
- **Scope:** 在 VCO-05 的实际通过范围内接入 `scene_rendering.mode=whole_scene_v1`，缺省 `segmented_v1`；沿既有 C 阶段派生独立版本化执行预算与渲染身份，贯通配置、输入、planning、graph、源片、裁剪/映射、观察、超分、合成、revision/recovery 与交付。不得只解除 96 帧 guard；不重新定义语义 scene-plan 或无故重新出图，不把短/中整段能力宣传为任意长镜头能力。
- **Acceptance:** ① 有 VCO-05 对应资源、原始输出、完整动态观看通过及适用范围证据；失败或缺项时不启用新生产模式。② 新预算在所有消费者一致，完整覆盖原时间轴，16fps、原始保留映射、PCM 样本和字幕不截短、不补帧冒充。③ 旧配置/冻结 run 保持原 options、graph、96 帧预算和恢复；未知 mode/预算或身份漂移拒绝。④ 模式变化仅使相关视频及下游失效，可核验继承原文、语义计划、已接受图和 PCM/字幕；不继承旧视频观看结论。⑤ 定向/恢复检查及实际生产样片、超分合成、最终完整观看和显式发布有各自证据；全库按用户既有要求留VCO-08/项目收尾，不预记通过；同 run 重放不重复提交或发布。⑥ 原独立多片续接验收仍未因整段通过而自动完成。
- **Dependencies:** `VCO-05` 的真实技术、资源和完整动态观看通过证据；`VCO-04` 的诊断准入、身份与恢复契约。
- **Sources:** ① `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 8、9、10 节；② `docs/task-designs/JIM-08-color-repair-design.md` 全文，重点 C；③ `docs/task-designs/JIM-08-whole-scene-proposal.md` 的长场景范围修正及全消费者预算设计（历史 137/221 帧预览不是当前 20 秒验收）；④ 本板 VCO-05 和 VCO-04 的实际设计与证据；⑤ `src/video_ai/planning/production_visual_plan.py`；⑥ `src/video_ai/planning/scene_clip_continuation.py`；⑦ `src/video_ai/runtime/scene_clip_records.py`；⑧ `src/video_ai/runtime/production_scene_clips.py`；⑨ `src/video_ai/runtime/production_scene_upscale.py`；⑩ `src/video_ai/runtime/production_scene_composition.py`；⑪ `src/video_ai/runtime/production_inputs.py`；⑫ `src/video_ai/planning/scene_revision.py`。
- **First action:** 完整读取已关联VCO-07设计与next-task交接；明确开始请求后登记READY -> IN_PROGRESS，再新增 `tests/unit/test_scene_execution.py` 的320/321、三scene463帧及超上限拒绝RED用例，按设计bootstrap命令验证后实现纯预算模块；不重复设计，不只删除96guard，不启动真实模型。
- **State evidence:** 2026-10-23 初始化为 `NOT_STARTED`；本板未证明 whole_scene_v1 可生产启用。

### VCO-08

- **2026-11-02 10:05 当前进展：** 保持IN_PROGRESS。独立案例003三窗均已真实技术完成，每窗仅一次采样；第三窗session29654/worker40556退出0、4632.156秒，result SHA cc06527eed75c86c555519874231e950354628625fe2c00eb024b3950c2bf2e3。三窗artifact、父链及两续窗各48层/4,907,335,680字节KV完整SHA核验通过；只追加新增区组成253帧/15fps/16.8667秒链，raw逐像素一致。原模型/文本复用，0新增下载/编码。首窗完整观看已接受；新的整链播放问题已发出，曝光变化、主体偏左/部分翼尖出画等静态风险保留，完整动态仍unverified，正式16fps未启用。GPU退出后单点真实复现原timeout测试失败（95.31秒），证实被用户要求的production无时限覆盖；只修测试故障注入，不改生产规则，5项定向复验session98891运行中。4375精确余项尚待，不重跑751已报告通过前缀。详见研究实录最新段落及VCO-08-native16-interface-audit.md；旧handoff中BLOCKED为历史。

- **第二窗已开始、回归精确排程（2026-11-02 07:22+08）：** 为让已授权两窗继续，先通过两次完全一致的5127节点收集和520源未变验证，保存全库已报告前缀751PASS/1FAIL及4375个精确余项，结束自有pytest40232（script_exit15为调度中断，不是全库通过）。`M/regression-resume-manifest.json`绑定顺序/源/日志，后续只复现timeout失败节点并续跑余项，避免重复通过前缀。CPU退出、主机余量核对后，stage2唯一采样session66767/worker28276启动，13历史+80新增/50步/15fps，无时间/占用配额；原首窗及用户完整观看接受保持。任务仍IN_PROGRESS，准确当前状态见研究实录顶部和M/live-run.json。

- **首窗完整观看接受：** 用户明确回复“完整观看后可接受，继续后续两窗”。已将反馈保存到M/trial-001/window-001/dynamic-review.json，绑定父result及观看副本SHA，保留已披露曝光变化；screening SHA7ba082ff…，allow_next_window=true。仅该首窗接受，全链及正式16fps尚未验收；不重复询问同一接受/两窗继续授权。全库session5241仍在运行，按CPU/GPU串行约束，退出后监督stage2一次。

- **第三案例首窗完成及当前验证（2026-11-02 02:24+08）：** session75394/worker30428退出0，50/50、4428.968秒，latent/93帧/原生15fps/6.2秒已提交，无损副本逐像素一致，result SHA091d3423…。静态原始帧显示后段明显变亮；已保存绑定父result的static-observation并提供完整视频请求动态反馈，暂未签发screening/启动第二窗，不预记视觉通过。GPU已退出后启动固定当前源码的项目收尾全库`./scripts/test_windows.ps1 -q`，session5241、日志test-9a1489230dd64f3a97032566b0a5d460，仍在运行，未预记通过。任务IN_PROGRESS；正式16fps/多窗/动态及最终全库结果仍待完成。新目录live-run.json和研究实录顶部为当前入口，旧交接仅为上次失败历史。

- **第三案例实际开始（2026-11-02 01:07+08）：** 独立目录`20261102-0102-progress-io`部署已验证读锁小修复，24其余源不变，case003 SHA c8164ea1…/软件71bd3242…。真实读锁3项及资源守卫检查通过；五阶段资源235.197秒/退出0，最低commit6,591,651,840/物理15,364,513,792字节，三组件layout、最终25/11源身份及独立只读review均通过。首窗唯一采样session75394/worker30428已开始，无时间/占用配额；模型/文本复用，0下载/编码/权重复制。原两失败案/冻结源/intent保持，当前IN_PROGRESS，不预记视频/正式16fps或全库通过。准确日志和活动入口见research-results顶部及新目录live-run.json。

- **读锁修复新案例开始：** 同一“继续完成当前任务”作为明确继续执行指令，观察READY后登记READY -> IN_PROGRESS。按N/progress-io-candidate-v1已验证候选准备新案例及新资源/软件身份，再监督首窗一次；不重新下载/编码，不覆盖原N或R冻结源/intent，不重启已退出session86714。

- **读锁修复新案例授权：** 针对已交付并通过真实Win32读锁RED/GREEN的修复候选和“另建案例继续”问题，用户明确回复“继续完成当前任务”。完整复读本任务设计及当前阻塞交接后，以该答复解除新案例执行阻塞，登记BLOCKED -> READY；保留两次失败案和同路径交接作为历史。允许应用候选、另建独立身份，复用模型/文本并按原题材/seed/规格继续三窗；研究与正式生产仍无执行时间上限，新试验无人工分配上限，空闲余量守卫保持。授权不等于资源/视频/正式16fps验收通过。

- **新案例技术阻塞（2026-11-02 00:05+08）：** session86714/worker24508在16/50步后因可选progress.json的WinError5读锁替换冲突退出1，elapsed1421.782秒、stop_reason=null，不是OOM/时间/资源停止；无成功latent/媒体。25冻结源未变，原N及历史R案/intent全部保留，不重采样。候选`N/progress-io-candidate-v1/`仅让Windows共享冲突延后可选快照发布，stdout和全部资源检查不变；真实Win32读锁RED→GREEN，3.12/worker3.13各3项通过，无CUDA/模型调用。已先归档旧交接并更新同路径pause阻塞交接，再登记IN_PROGRESS -> BLOCKED；用户未要求暂停，VCO-08未完成。已提交具体新案例继续问题，待明确允许后BLOCKED -> READY -> IN_PROGRESS；无需重问时间/占用上限解除。新资源/视频/正式16fps/全库不预记通过。准确身份、日志、候选SHA及恢复入口见最新handoff和research-results顶部。

- **新复验实际运行（2026-11-01 23:42+08）：** 独立新目录`D:/VideoSi/projects/video-ai/vco08-preflight/20261101-2314-allocator-unlimited`五阶段资源预检233.452秒退出0（c45a733527024074a389b2cbe22fbd3f），人工8GiB池/20GiB峰值配额均移除，保留原空闲余量；VAE空闲缓存释放的真实encode/decode逐位等价验证通过。25源freeze `2a444e36…`、三组件layout及最终身份检查通过，新case `a6580131…`；模型/文本复用，0下载/重编码。新首窗已且仅已启动一次，session86714/worker24508，intent `77aee0ae…`，正在50步采样，无时间上限，勿重启。原失败案全部保留；本状态仍IN_PROGRESS，不预记视频/多窗/正式16fps/全库通过。日志和完整身份见research-results顶部。

- **新案例开始证据：** 同一“是的，移除内存占用上限”作为继续执行依据，登记READY -> IN_PROGRESS；保留当前交接为原失败/恢复历史。先在独立研究目录部署已审查候选，移除8GiB池与人工峰值占用上限，完成实际pipeline驻留预检和新freeze/layout，再监督新案例首窗一次。原case/window-start及intent不删除、不覆盖，不重新下载/编码，不重跑已完成软件批次。

- **阻塞解除证据：** 用户对另建案例、取消人工分配池并先资源复验再继续三窗的明确询问回复“是的，移除内存占用上限”。该指令明确授权新技术复验，保留原失败案，复用已下载权重/文本，题材/seed/规格不改。完整读取本任务设计/阻塞交接后登记BLOCKED -> READY；该授权不等于GPU资源或视频通过。

- **技术阻塞与软件收尾（2026-11-01 22:30+08）：** 已完整复读关联设计、确认源IN_PROGRESS，先归档旧交接原字节并写入新的pause阻塞交接，再登记 `IN_PROGRESS -> BLOCKED`，同路径Handoff保留。时间解除已经覆盖研究和正式production/scene/pipeline，相关定向与兼容通过：legacy476、最终whole230、精确integration7、最终原四研究文件19+其中两个guard共同覆盖原21；逐批证据见两份time-limits文档及research-results。没有虚构去重总数；原275并非完整通过，延期33个精确ID留VCO-08最后全库。唯一实际首窗已0/50因8GiB人工池OOM，无成功latent/视频；不能在原case重采样。25冻结运行源、原案/日志/缓存均保留。allocator-candidate-v2仅语法及CPU准入通过，尚未应用/执行GPU；新的技术复验范围待明确。解除条件是用户明确授权独立新技术复验及其原案失败血缘（如取消人工8GiB池但保留原运行余量、复用模型/文本与同规格三窗），不把授权当实际资源或视频通过。当前无活动测试/模型，正式16fps/视觉/最终全库仍未完成。

- **最新实际失败（2026-11-01 21:35+08）：** session86229监督真实首窗一次，0/50步DiT FFN处触发冻结8GiB PyTorch分配池OOM，GPU当时仍15.70GiB空闲。worker28200及supervisor均退出1；无成功latent/视频，无stage2/3，不自动重试；case/window-start和intent留存，软件1342e93c...及case5db7a7a4...已进入运行身份，禁止再做准备期覆盖。此前随机latent五阶段成功不等于真实pipeline通过。正在完成生产/旧pipeline取消时间上限的剩余定向回归；真实多窗、正式16fps资格和项目最终全库仍未完成，保持IN_PROGRESS，不记VCO-08完成。详见研究实录顶部。

- **无时限资源成功：** 原FFN五阶段完整247.783秒退出0，结果full-dit-resource-probe-1acf48d3d9254b099a95a516b994f683；最低commit12,392,964,096、物理16,430,608,384字节，保持原资源门槛。最终25文件freeze软件SHA1342e93c...、三组件layout及25源/11官方源/case/cache准入复核通过；新case5db7a7a4...，文本仍53c254...、0重编码。独立只读审查无重要问题。真实采样尚未开始；正在实施正式生产取消执行时限，先软件定向再串行真实首窗，不把资源通过记为视频或VCO-08完成。

- **用户解除时间上限：** 用户明确研究及“正式生产视频的时候也不要设置预算”。按该最新指令取消探针/每窗/案例及正式生产执行时间上限，原资源/一次采样/unknown不重试保持。研究None clock与资源门禁/恢复fixture通过，归档原case/文本绑定，case仅两个时间字段改null，新SHA5db7a7a4...，原文本缓存未变且0重编码。原FFN五阶段session86537运行中，生产时间策略另行实现与定向测试；本任务仍IN_PROGRESS，不因取消时限而视为资源/视频/生产通过。

- **原FFN恢复实测（2026-11-01）：** 完整探针session53408退出1，结果full-dit-resource-probe-723406d612844f1c8ead7fd4c8d54680：三DiT前向和VAE编码已完成，93帧解码/finite/postprocess已计算，但末次Guard246.402秒超过240秒；无资源准入、无真实intent。最低commit12,626,620,416、物理18,070,351,872字节，内存本次满足。首窗/续窗80.786/94.858秒，50步投影超过3600秒。待确认仅时间修订：准备360秒、每窗7200秒、案例21600秒，原FFN/规格/步数/seed/资源阈值不变，具体R/time-budget-proposal.json及研究实录；尚未改case/cache/software。保留IN_PROGRESS，未把研究或任务记为完成。

- **恢复定向证据（2026-11-01 19:36+08）：** 已应用交接中三行研究窗口初始化及两个旧媒体守卫fake更新，产品SHA8158c248...与隔离候选一致。交接指定四文件及两个媒体测试ID实际21 passed / 495.97s / exit0，日志test-69601399cb1142218249ad1076e87b3d。尚未运行新的五阶段资源检查或真实视频；原FFN资源检查为下一步，最终全库/生产16fps与整体验收仍未完成。

- **Resume evidence（2026-11-01）：** 用户明确要求读取VCO-08交接并恢复继续尚未完成的VCO-08，已完整读取关联研究设计及pause handoff，登记 `PAUSED -> IN_PROGRESS`，保留交接为历史入口。按交接顺序消费本板、研究设计、handoff/research-results、active-regression及候选/RED日志；首步核实产品SHA仍为8b28f283...，应用三行GeometryDecoder初始化与两个媒体守卫fake更新，运行指定实际定向复验。随后按最新主机状态以原FFN验证完整五阶段资源，再处理freeze/layout/一次真实采样门槛；不重下模型、不重跑T5、不重启已停止全库基线，不改变正式16fps及原五项验收。

- **Pause / conversation handoff（2026-11-01 19:17+08）：** 用户明确要求“把任务暂停，我要交接给下一个会话”。完整读取关联研究设计后，先写`docs/task-handoffs/VCO-08-handoff.md`，再登记 `IN_PROGRESS -> PAUSED` 并链接交接。原全库session89796的自有Python PID7624已按请求停止，launcher21160亦已退出；session返回1、bootstrap日志exit/script_exit=-1，部分输出5FAIL/8ERROR、无最终pytest总结，不能记全库通过。候选修复尚未应用，无实际视频采样。下一会话从该交接的三行初始化/两个fake修复及实际定向复验继续，不再等待旧session、不重下模型或重跑T5；正式16fps生产接入及整体验收仍未完成。

- **Current research result（2026-11-01，暂停现场）：** 已关联`docs/task-designs/VCO-08-design.md`，只覆盖用户同意的LongCat前置研究。固定代码6b3f4b8、权重03b55529的23/23文件共77,577,230,776字节已下载校验；真实T5缓存、只读映射、单块48次重放及BF16磁盘KV探针通过。完整预训练模型前向曾因Windows commit最低4,234,903,552字节（约3.94GiB）低于4GiB阈值而停止，缺口约57.3MiB；最近主机快照余量回升，仍须完整五阶段模型重新取证，不能把单块通过或空闲主机快照代证完整模型。无case/window-start、视频intent/采样或新观看，资源准入门禁实测拒绝；当前源码尚待资源通过后新freeze/layout。详见`docs/task-designs/VCO-08-research-results.md`及最新pause handoff；研究目录`preparation-stop.json`为历史资源现场，`active-regression.json`已登记用户暂停。已中止全库日志test-6cbc7cce122d44e49274cd71238e166e保留；研究窗口初始化及旧媒体门禁夹具的隔离候选已验证，实际源码/测试尚未应用。恢复后先定向修复复验，再按最新主机状态以原FFN复验资源；未取得新准入不启动视频。

- **Start evidence（2026-11-01）：** 以上明确继续请求同时作为READY -> IN_PROGRESS启动依据；无入口handoff。先核实基础LongCat的Windows/单卡分阶段加载路径、固定代码/权重清单和原生研究时基；研究允许独立可丢弃探针，不改写旧生产run、不声称已通过生产验收。

- **Research authorization（2026-11-01）：** 用户对“将LongCat-Video隔离可行性前置研究纳入VCO-08”明确回复“同意，继续吧”。本次是当前任务的独立准备，按NOT_STARTED -> READY登记；允许推进所选LongCat研究路线的本机资源、平台、时基及隔离探针准备，不重复请求同一研究范围。生产准入和本任务五项原Acceptance保持，不能把允许研究当成真实多窗通过。Design/Handoff暂仍None，按已核实事实完善研究设计。

- **Entry audit（2026-11-01）：** 用户要求“完成任务VCO-08”。已完成只读入口及新候选核查，结果见 `docs/task-designs/VCO-08-entry-audit.md`；七份官方源码/文档文本与SHA清单保存于 `D:/VideoSi/projects/video-ai/vco08-preflight/20261101-1238/`。现有生产只支持segmented/whole；LongLive的适用I2V权重及本机资源尚未核实，MemFlow官方要求80GB/Linux，新候选LongCat有真实历史latent/KV续写入口，但官方BF16整模型路径超出本机24455MiB、依赖NCCL且原生示例15/30fps，尚无本机多窗通过证据。外部准入前提仍缺；本次未启动下载/安装/推理或生产实现，状态维持NOT_STARTED，Design/Handoff均None。需先确定新后端研究试验是否纳入执行范围，再完成具体可行性/试验设计；未运行pytest或全库，不记本任务完成。

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
