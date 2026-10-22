# Jimeng Scenes Project Task Board

## Project

- **Project ID:** `jimeng-scenes`，任务前缀 `JIM`。
- **Goal:** 将现有自动制作改为完整文案归纳关键画面、调用用户配置的即梦官方模型、邮件选图，再生成保持一致性的动态视频和完整旁白字幕成片。
- **Scope:** 实施 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md`。包含模型与参数配置、段落画面规划、共享视觉设定、基准图与参考图、QQ 邮件选图、Wan 末帧续接、一致性验收、局部返工和安全恢复。复用现有配音、Wan、超分及合成能力；排除网页选图、自动收信、即梦视频接口、自动创建云资源和题材专用补丁。
- **Completion condition:** 总体方案 Acceptance 五项均有实际证据；用户选定的基准与后续参考关系可追踪，至少三个同主体画面及一个含两个续接片段的长画面完成实际观察；QQ 邮箱真实收信，完整旁白和字幕保留；不一致或未观察的版本不能正式交付；替身端到端、故障恢复和相关历史回归分别记录通过结果。替身测试不能替代真实画面验收。
- **Overall design:** `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md`，已由用户确认。
- **Authorization evidence:** 建板时用户明确要求“可以，按这个方案拆分任务吧”，当时仅授权拆分和记录。2026-10-18 用户后续明确要求“JIM-01 完成这个任务”，授权该项本地实现与验证；本轮没有真实收费出图、图片上传或邮件发送。
- **Board boundary:** 本板只管理此次改造。`D:/VideoSi/docs/task-handoffs/video-ai-task-board.md` 与 `D:/VideoSi/docs/task-handoffs/make-video-task-board.md` 保持其原有历史记录，不在本板重编号或重开旧任务。

## Workflow

- **Execution:** 按下列 Order 提供默认实施顺序，执行安排由用户决定。创建任务板不启动首项，不派发实现，也不自动切换其他任务状态。
- **Next-task selection:** 当前任务完成后，选择 Order 更大且未完成的最小 Order 任务；直接依赖描述输入来源，不替代预定义顺序。
- **Successor preparation:** 记录当前任务的完成证据后，完成并关联所选后继的具体设计，才创建其 next-task 交接并准备为 READY。后继设计存在缺口时保留前任务完成状态，不生成部分交接。
- **Allowed transitions:** `NOT_STARTED -> READY`、`READY -> IN_PROGRESS`、`IN_PROGRESS -> PAUSED`、`PAUSED -> IN_PROGRESS`、`READY -> BLOCKED`、`IN_PROGRESS -> BLOCKED`、`BLOCKED -> READY`、`IN_PROGRESS -> COMPLETED`。
- **Initialization:** `JIM-01` 为 `READY`，其他均为 `NOT_STARTED`，Handoff 均为 `None`。`READY` 表示首个可推进任务，不表示已经开发或测试通过。
- **Design documents:** 建板时各任务详细设计均未创建；当前确切引用以表格 Design document 为准，共同总体方案列在 Project 和各任务 Sources 中。创建任务设计后必须回填相应单元格，不能把总体方案冒充已经完成的各项实施契约。
- **Evidence:** 每项功能同时承担其本阶段的单次提交、错误处理、身份校验和恢复测试；不能等到最后一个恢复任务才补防重复收费或防重复发送措施。未运行的测试仅可列为计划，不能记为通过。

## Tasks

| Order | Task ID | Title | Status | Dependencies | Design document | Handoff |
|---:|---|---|---|---|---|---|
| 1 | JIM-01 | 可配置即梦官方模型接入与候选图持久化 | COMPLETED | None | D:/code/py/video-ai/docs/task-designs/JIM-01-design.md | None |
| 2 | JIM-02 | 段落关键画面、共享视觉设定与时间预算 | COMPLETED | JIM-01 | D:/code/py/video-ai/docs/task-designs/JIM-02-design.md | D:/code/py/video-ai/docs/task-handoffs/JIM-02-handoff.md |
| 3 | JIM-03 | 候选图邮件、基准选图与等待续作 | COMPLETED | JIM-01, JIM-02 | D:/code/py/video-ai/docs/task-designs/JIM-03-design.md | D:/code/py/video-ai/docs/task-handoffs/JIM-03-handoff.md |
| 4 | JIM-04 | 参考图存储与关联画面一致性生成 | COMPLETED | JIM-01, JIM-02, JIM-03 | D:/code/py/video-ai/docs/task-designs/JIM-04-design.md | D:/code/py/video-ai/docs/task-handoffs/JIM-04-handoff.md |
| 5 | JIM-05 | Wan 连续片段、末帧续接与动态观察 | COMPLETED | JIM-02, JIM-04 | D:/code/py/video-ai/docs/task-designs/JIM-05-design.md | D:/code/py/video-ai/docs/task-handoffs/JIM-05-handoff.md |
| 6 | JIM-06 | 新时间轴合成与成片一致性交付验收 | COMPLETED | JIM-03, JIM-05 | D:/code/py/video-ai/docs/task-designs/JIM-06-design.md | D:/code/py/video-ai/docs/task-handoffs/JIM-06-handoff.md |
| 7 | JIM-07 | 跨阶段恢复、修订运行与局部返工 | COMPLETED | JIM-04, JIM-05, JIM-06 | D:/code/py/video-ai/docs/task-designs/JIM-07-design.md | D:/code/py/video-ai/docs/task-handoffs/JIM-07-handoff.md |
| 8 | JIM-08 | 全链路回归、真实样片验收与使用说明 | IN_PROGRESS | JIM-07 | D:/code/py/video-ai/docs/task-designs/JIM-08-design.md | D:/code/py/video-ai/docs/task-handoffs/JIM-08-handoff.md |

## Task Details

### JIM-01

- **Goal:** 给定画面提示词和用户所选模型，即可通过火山引擎官方接口生成并保存可追踪的候选图片。
- **Scope:** 新增外部 HTTPS 与官方签名/异步任务适配；配置 `image_generation.req_key`、模型参数、凭证环境变量名和候选数；新增 `--image-model` 覆盖；新策略识别、配置冻结、版本化图片记录及不依赖 SDXL 的必要预检。保存任务 ID、脱敏请求和响应、原始图片及 SHA256。候选生成可先由测试入口驱动，不要求本任务完成段落规划或邮件流程。
- **Acceptance:** ① 配置或 CLI 可换文生图模型，不把某版参数套到全部模型；恢复时使用冻结模型，擅自修改模型明确拒绝。② 官方业务错误、空 data、排队/生成/完成/过期状态和多图结果有独立验证。③ HTTP 替身证明提交成功后中断能查原任务；提交结果不明不会自动重复付费提交；下载失败只恢复下载。④ 原图持久保存，尺寸按模型配置核验；凭证与签名 URL 不泄露到普通日志。⑤ 旧配置默认行为不变；新策略缺少 SDXL 文件不被误拒绝。自动验证不要求真实账号。
- **Dependencies:** `None`；直接复用现有项目源码与既有配音、视频工具约束。
- **Sources:** ① `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点“即梦官方接口与模型配置”“版本、预检和恢复”；② `D:/code/py/video-ai/src/video_ai/config.py`；③ `D:/code/py/video-ai/src/video_ai/cli.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_inputs.py`；⑤ `D:/code/py/video-ai/src/video_ai/runtime/production_visual_records.py`；⑥ `D:/code/py/video-ai/src/video_ai/adapters/common.py`；⑦ 总体方案末尾的官方接口资料。
- **First action:** 对照当前配置、冻结输入和本机 HTTP 客户端，编写本任务详细设计，确定外部 HTTPS 边界、官方请求协议、模型配置和单次提交记录契约，再回填 Design document。
- **State evidence:** 2026-10-18 用户明确要求“JIM-01 完成这个任务”，由 `READY -> IN_PROGRESS`；完成配置/CLI 覆盖、官方签名异步适配、schema=2 冻结/候选记录、原图/SHA256/尺寸核验、下载收据与保守恢复后，由 `IN_PROGRESS -> COMPLETED`。五项验收逐项证据见 `D:/code/py/video-ai/docs/task-designs/JIM-01-verification.md`；新增专项 **79 passed in 8.59s**，历史配置/制作 CLI 专项 **74 passed in 145.58s**，最终全套 `& $VideoAiPython -B -m pytest -q --tb=short` 为 **2628 passed in 3758.32s**，退出码 0，完整输出 `D:/VideoSi/cache/video-ai/logs/jim-01-full-verified.txt`。独立审查的两项 Important 均已用失败测试复现、修复并复核关闭。使用 HTTP 替身及真实媒体解码，没有真实收费生成/上传/邮件；新策略候选由 Python API 驱动，段落/邮件/视频协调器留在后续任务。

### JIM-02

- **Start evidence:** 2026-10-18 用户明确要求“JIM-02 完成这个任务”；完整读取所引用设计与交接，记录 `READY -> IN_PROGRESS`。实施计划为 `D:/code/py/video-ai/docs/task-designs/JIM-02-plan.md`。

- **Goal:** 完整文案可以归纳为少量有上下文的关键画面，画面数与句子数脱钩，同时保留完整旁白及时间覆盖。
- **Scope:** 区分 narration unit、scene、clip；画面规划器读取完整原文、段落和既有配音时间轴；生成 `production/visual-bible.json`、主体/场景组、图片及动作描述、基准画面依赖图、画面到多旁白单元的关联和动态片段预算。每段目标画面数默认 3，可对短段减少；单请求时长默认上限 6 秒。不在本任务实现视频生成或以规划结果宣称画面一致性已通过。
- **Acceptance:** ① 至少一个画面覆盖两句旁白，不能由句号数量机械决定出图数量。② 原文、配音与字幕文本完整保留；画面覆盖从 0 到 total_frames，无重叠、无空洞，包括停顿与首尾。③ 相同主体共享稳定标识、外观来源和基准关系，原文事实与创作选择分别记录；剧情换景/换装有依据。④ 参考依赖图可拓扑排序，非法循环/来源范围/缺项拒绝。⑤ 长画面拆 clip 不额外增加 scene 图片；新规则不放宽历史槽位校验。
- **Dependencies:** `JIM-01` 的新策略、冻结配置和版本化记录边界。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点“内容与时间轴”“一致性设定与参考图”；② `D:/code/py/video-ai/src/video_ai/planning/production_units.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_storyboard.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_visual_storyboard.py`；⑤ `D:/code/py/video-ai/src/video_ai/planning/production_timing.py`；⑥ `D:/code/py/video-ai/src/video_ai/runtime/production_timeline.py`；⑦ `D:/code/py/video-ai/src/video_ai/planning/production_visual_plan.py`。
- **First action:** 按已完成的 JIM-02 设计，在 `tests/unit/test_production_scenes.py` 建立同段两句共用 scene 的固定提案和真实 ProductionTimeline，断言完整原文、PCM bindings 与总帧覆盖；先观察接口缺失失败，再实现独立 `planning/production_scenes.py`。
- **State evidence:** 用户明确开始后完成独立 scene 规划、共享视觉设定/固定基准图、完整 PCM/frame 绑定、Wan clip 预算、配置及持锁规划事务恢复，由 `IN_PROGRESS -> COMPLETED`。五项验收和独立审查证据见 `D:/code/py/video-ai/docs/task-designs/JIM-02-verification.md`。修复后专项与相关历史/Ollama **267 passed in 31.29s**；最终全套 `& $VideoAiPython -B -m pytest -q --tb=short` 为 **2757 passed in 3790.62s (1:03:10)**，退出码 0，输出 `D:/VideoSi/cache/video-ai/logs/jim-02-full-verified.txt`。独立审查两项 Important（首次外观/场景引用未来事实、上下文隐式截断）均由 4 个失败测试复现后修复，Minor=0。没有真实收费生成、上传或邮件；默认本机模型启动/硬件容量未实际联调。旧交接路径保留为开始上下文，新策略全流程入口继续保护。

### JIM-03

- **Start evidence:** 2026-10-18 用户明确要求“完成JIM-03”；全文读取设计与交接，记录 `READY -> IN_PROGRESS`；实施计划 `D:/code/py/video-ai/docs/task-designs/JIM-03-plan.md`。

- **Goal:** 基准画面候选能发到用户 QQ 邮箱，用户通过编号作出可验证选择，程序保存进度并安全等待/续作。
- **Scope:** SMTP SSL、邮件正文与编号、基准/候选/原文对照、整组对照图、实际附件及编码后拆包；稳定 Message-ID、发送意图和回执；基准与普通批次的选择文件、SHA256 接受记录、整组一致性观察绑定；`--image-selection` 入口；`awaiting_image_selection` 和 `email_delivery_unknown` 结果及锁/服务释放。发件和收件均为 `318575094@qq.com`。不自动收信或部署选图网页。
- **Acceptance:** ① 本地 SMTP 替身收到实际图片、可复制编号、原文和一致性要求；15 MiB 默认上限按完整 MIME 字节计，拆包不丢候选。② 普通续作不重复发送已接受邮件；发送结果不明不会自动重发；修复邮件配置不重新出图。③ 当前批次每画面恰好一张且身份正确才能接受；重复、缺项、跨 run 和变化图片拒绝；部分选择仅作草稿。④ 单纯选编号不自动伪造整组一致性通过；未完全选图并确认整组前无新 Wan 提交。⑤ 等待返回后锁和本次自有服务释放，续作保留候选及已选基准。本任务用测试驱动模拟后续批次，不依赖尚未实现的参考图生成。
- **Dependencies:** `JIM-01` 的候选图片/模型记录；`JIM-02` 的场景、批次与基准依赖信息。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点“候选图、邮件和等待状态”“用户选图与续作”；② `D:/code/py/video-ai/src/video_ai/cli.py`；③ `D:/code/py/video-ai/src/video_ai/production.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_state.py`；⑤ `D:/code/py/video-ai/src/video_ai/runtime/production_visual_review.py`；⑥ `D:/code/py/video-ai/src/video_ai/media/images.py`。
- **First action:** 按已完成的 JIM-03 设计，在 `tests/unit/test_selection_email.py` 建两 scene、同名局部 candidate ID、真实 PNG、完整原文和基准用途的 fixture，断言实际 MIME 的编号/附件/编码后限额；先观察接口缺失失败，再实现纯邮件构建。
- **State evidence:** JIM-02 先记录 COMPLETED 后，完成、全文自审并关联 `D:/code/py/video-ai/docs/task-designs/JIM-03-design.md`；设计明确 SMTP/MIME、批次/基准身份、选择/观察精确结构、独立 schema=2 结果、CLI 准备运行分派及恢复/测试。随后写入并关联 `D:/code/py/video-ai/docs/task-handoffs/JIM-03-handoff.md`，由 `NOT_STARTED -> READY`。本次仅后继准备，JIM-03 实现未启动，新测试尚未创建/运行；收发地址已确认，SMTP 授权码/真实投递仍未验证。

- **Completion evidence:** 2026-10-18 完成 SMTP SSL/MIME 编码后拆包、真实原图/预览/对照图、发送意图/回执与显式重发、持锁批次/基准选择、原始提交副本、整组实际观察准入及 prepared-run CLI schema=2，记录 `IN_PROGRESS -> COMPLETED`。验收与独立审查证据见 `D:/code/py/video-ai/docs/task-designs/JIM-03-verification.md`。新专项最终审查前 **129 passed in 155.93s**；CLI 两项 Important 先 RED 后修复，另测锁释放 OSError；相关历史 **114 passed in 225.54s**。144 个模块全量初次 **2886 passed、2 failed、1 error**（1228.41 秒），三个旧测试串行复查 **3 passed in 10.12s**，代码未改，完整覆盖 **2889 个唯一用例均有通过证据**。原并行失败与复查成功均保留，汇总 `D:/VideoSi/cache/video-ai/logs/jim-03-verified-coverage.json`。本地 SMTP/HTTP 替身及真实 ffmpeg，无真实 QQ 邮件、收费生成、上传或 Wan；真实收件与视觉一致性留到后续验收，候选/选图接口可供 JIM-04 消费。

### JIM-04

- **Start evidence:** 2026-10-19 用户明确要求“JIM-04完成这个任务”；全文读取设计及交接，记录 `READY -> IN_PROGRESS`；实施与验证记录 `D:/code/py/video-ai/docs/task-designs/JIM-04-plan.md`。

- **Goal:** 选定的基准图实际参与关联画面的生成，重复主体和场景有固定视觉参考，而非独立文生图后再碰运气筛选。
- **Scope:** 新增 `src/video_ai/adapters/reference_storage.py`，使用配置的现有 TOS 私有桶保存选图并签发 HTTPS GET URL；核对模型参考图能力、数量和尺寸；同模型引用或用户明确配置 `reference_generation.req_key`；按依赖批次生成候选并复用 JIM-03 邮件/选择流程；请求绑定共享设定和固定基准。未知/不支持参考的模型不能自动换模或退回纯文字生成。
- **Acceptance:** ① 替身请求中确有已接受基准的参考输入，且每个输入对应主体/背景用途清楚，同主体跨画面直接引用同一固定基准。② 基准未选、能力不明、配置缺失、参考数量超限或 URL 有效期不足均在关联画面付费提交前停止。③ 本地 SHA256、TOS 对象来源和依赖关系可核验，预签名 URL 不泄露；不创建桶或修改桶权限。④ 未提交请求可刷新 URL，已受理任务只能查询原任务；恢复不重新出图。⑤ 后续候选能按批发邮件，全部选图和整组一致性确认通过后产出精确的 Wan 输入清单。实际服务是否能取图留到 JIM-08 真实验收。
- **Dependencies:** `JIM-01` 的官方图片任务适配；`JIM-02` 的视觉设定/参考依赖图；`JIM-03` 的已接受基准及分批邮件/选择接口。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点“一致性设定与参考图”；② `D:/code/py/video-ai/src/video_ai/runtime/production_visuals.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_visual_records.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_inputs.py`；⑤ 总体方案末尾的即梦参考输入与 TOS 官方资料；⑥ 已完成 JIM-01 至 JIM-03 时登记的直接输入契约与验证证据。
- **First action:** 按 JIM-04 完成设计，在 `tests/unit/test_reference_storage.py` 建固定 UTC/AK/SK 与 GET TTL=3600 的独立 TOS4 签名向量；bootstrap 后先观察缺适配器失败，再实现纯签名和受控 HEAD/GET/PUT。
- **State evidence:** 初始化为 `NOT_STARTED`；模型选择、TOS 桶与权限待本地配置，没有真实上传或取图验证。

- **Preparation evidence:** JIM-03 先记录 COMPLETED 后按 Order=4 选择本项，完成并全文自审/关联 `D:/code/py/video-ai/docs/task-designs/JIM-04-design.md`；配置补齐但不修改既有冻结/基准、TOS4 协议、模型能力档案、实际 reference 输入/来源与 Wan 首图准入均有具体契约。交接 `D:/code/py/video-ai/docs/task-handoffs/JIM-04-handoff.md` 写入并关联后记录 `NOT_STARTED -> READY`。本次只准备实施入口，没有启动 JIM-04 实现或运行其新测试。

- **Completion evidence:** 2026-10-19 完成固定已选原图的 TOS 内容寻址发布、独立 TOS4 向量、受控参考 URL 实际提交、严格能力及配置冻结/补充、共享设定/多用途来源、单次提交恢复、原任务查询与邮件复用、完整观察后的精确 Wan 首图清单，记录 `IN_PROGRESS -> COMPLETED`。验收 `D:/code/py/video-ai/docs/task-designs/JIM-04-verification.md`；最终新专项 **118 passed in 360.71s**、设计列出的历史回归 **186 passed in 200.44s**、串行全套 **3012 passed in 3840.59s (1:04:00)**，全部退出码 0，日志 `D:/VideoSi/cache/video-ai/logs/jim-04-{targeted,historical,full}-final.txt`。独立审查复现并修复备用配置凭证落盘、能力验证/复制不同读、同字节多基准对象冲突、实际发送时 TTL 与身份、提交证据摘要绑定问题，另修复真实 JPEG 格式映射；审查及 scoped re-review 无剩余 Critical/Important。20 个实现/测试/示例/说明文件的 SHA256 在验证后完全匹配，`D:/VideoSi/cache/video-ai/logs/jim-04-verified-files.json`。本地真实 PNG/JPEG/ffmpeg 与 HTTP/SMTP/socket 替身；没有真实云上传、收费生成、QQ 收信、Wan 或视觉质量验收，真实服务留 JIM-08。后继依次消费完整图片准入接口，不复用旧纯文字模拟作为参考证据。

### JIM-05

- **Start evidence:** 2026-10-19 用户明确要求“完成任务JIM-05”；完整读取设计和交接，记录 `READY -> IN_PROGRESS`。实施计划 `docs/task-designs/JIM-05-plan.md`；初始 PATH 未发现 Git，后通过 `C:/Program Files/Git/cmd/git.exe` 只读检查；.git 只读，在提供的 checkout 保留实现与验证证据。

- **Goal:** 用户选中的图片进入 Wan；同一长画面的动态片段沿实际保留末帧续接，并在漂移或未观察时阻止继续传播。
- **Scope:** 修改 `src/video_ai/planning/production_visual_plan.py`、`src/video_ai/runtime/production_visuals.py` 与 `src/video_ai/media/frames.py`；首片读取选图副本，续片使用父片实际保留末帧；保存父片/输入图/帧索引身份、衔接帧丢弃和逐帧映射；实现父片动态过程观察与 `awaiting_continuity_review`，明确连续续接和有意切镜两种边界。复用 Wan 模型与工作流，不改成即梦视频。
- **Acceptance:** ① 首片输入与用户选择精确关联，未经完整图片准入不请求 Wan。② 续片输入来自父片最后一个实际保留原生帧，不能取裁掉的补帧；父片未观察或不一致时不提交其续片。③ 续片申请衔接余量并丢首帧，最终映射按原文时间轴准确覆盖，不循环、冻结或截短旁白补时。④ 视频提示词保留固定主体/环境；过程观察不能仅用首尾截图或相似度代替。⑤ 中断恢复使用原 Comfy 提交，父片身份改变拒绝复用续片；独立场景等待和失败状态不混淆。
- **Dependencies:** `JIM-02` 的 scene/clip 时间预算；`JIM-04` 的完整已接受图片清单、基准及共享视觉设定。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点“动态视频的延续与验收”；② `D:/code/py/video-ai/src/video_ai/planning/production_visual_plan.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_visuals.py`；④ `D:/code/py/video-ai/src/video_ai/media/frames.py`；⑤ `D:/code/py/video-ai/workflows/wan22_i2v_14b_api.mapping.json`；⑥ `D:/code/py/video-ai/src/video_ai/runtime/_source_clip_review.py`；⑦ `D:/code/py/video-ai/src/video_ai/planning/final_review.py`。
- **First action:** 按已完成 JIM-05 设计，在 `tests/unit/test_scene_clip_continuation.py` 建立 `test_200_frame_retained_native_mapping`，由既有 plan_scene_clips 生成 200 帧预算，断言保留/生成 `[93,92,15]`/`[93,93,17]`、末保留索引 `[92,92,15]`、head/tail null 和全局恰好一次覆盖；bootstrap 后先运行观察缺新接口 RED，再实现纯规则，不修改 JIM-02 预算。
- **State evidence:** 初始化为 `NOT_STARTED`；尚无动态生成或续接观察结果。

- **Preparation evidence:** 2026-10-19 JIM-04 先记录 COMPLETED 后按 Order=5 选择本项，观察到 NOT_STARTED/Design=None；完成并全文审阅 `D:/code/py/video-ai/docs/task-designs/JIM-05-design.md` 后仅回填 Design document，再写入并关联 `D:/code/py/video-ai/docs/task-handoffs/JIM-05-handoff.md`，最后记录 `NOT_STARTED -> READY`。设计明确 prepared-run API、独立 schema=2 原生帧/样本映射、父末保留帧、每片实际过程观察、独立 scene 推进及 Comfy 单次提交/原 ID 恢复；JIM-02/JIM-04 直接输入无已知未解决冲突。本次只准备后继，JIM-05 实现、新测试和真实动态观看均未启动。

- **Completion evidence:** 2026-10-19 完成独立 schema=2 prepared-run Wan 源片、固定共享提示词、父末保留原生帧字节续接、区间裁片/完整样本和帧映射、每片过程观察准入、独立 scene 推进及原 Comfy UUID/graph 恢复，记录 `IN_PROGRESS -> COMPLETED`。五项验收见 `D:/code/py/video-ai/docs/task-designs/JIM-05-verification.md`；独立审查和修复见 `JIM-05-review.md`。原导入版本专项 **269 passed in 3343.84s**；最终字节历史回归 **212 passed in 838.51s**；全新进程全套 **3206 passed in 7302.90s (2:01:42)**，均退出 0。全套包含最后补充的未知 run、失败观察原文中断及临时裁片恢复；**21 个文件 SHA256 全部匹配**。日志 `D:/VideoSi/cache/video-ai/logs/jim-05-full-final.txt`，哈希核对 `jim-05-verified-files-check.json`。本地替身及真实媒体验证，没有真实 Wan、云请求或邮件；真实视觉效果留待后续验收。旧 shot/schema=1 契约保留，超分/合成/交付和全流程协调未在本项实现。

### JIM-06

- **Start evidence:** 2026-10-19 用户明确要求“完成JIM-06”；全文读取已关联设计与入口交接，记录 `READY -> IN_PROGRESS`。实施计划 `D:/code/py/video-ai/docs/task-designs/JIM-06-plan.md`；保留当前 checkout 前序成果及只读 Git 元数据。按既有详细契约实施独立 schema=2，不执行真实模型/云服务或伪造实际观看结论。

- **Goal:** 新画面/片段时间轴能复用超分与合成输出完整候选片，只有整片一致性实际验收后才正式交付。
- **Scope:** 将 scene/clip 映射接入超分、完整 PCM/字幕合成、完成前缀与交付消费者；新策略识别原文完整性、整组图片观察、动态观察及最终连续视频观察；候选输出与正式交付分离。保留现有输出规格和历史策略契约，不把编码技术检查当作画面一致性通过。
- **Acceptance:** ① 多句共用画面和跨片续接均保持完整配音、字幕及总帧数；首尾和停顿覆盖不丢失。② 最终观察绑定确切候选、选图、基准及动态片段身份；未核实或不一致不产生正式交付收据。③ 有效实际验收后才复制确切已验收版本，重新编码或文件变化使观察失效。④ 历史运行仍按原审核/交付逻辑恢复，未被新策略替换。⑤ 候选片可以保留供检查，不伪报已正式交付。
- **Dependencies:** `JIM-03` 的选择/一致性观察记录；`JIM-05` 的源片、连续链、动态观察及精确帧映射。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点最终验收和版本兼容要求；② `D:/code/py/video-ai/src/video_ai/runtime/production_upscale.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_composition.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_delivery.py`；⑤ `D:/code/py/video-ai/src/video_ai/runtime/production_completed.py`；⑥ `D:/code/py/video-ai/src/video_ai/media/production_composition.py`；⑦ `D:/code/py/video-ai/src/video_ai/planning/final_review.py`。
- **First action:** 按已完成 JIM-06 设计，在 `tests/unit/test_scene_media.py` 建 `test_200_retained_frames_upscale_once_without_second_head_drop`，由既有 200 帧预算及 JIM-05 mapping 调用新纯计划，断言仅 200 个贡献、93/92/15、generated 第三片 1..15、child retained=0 映到 generated=1 和 global=0..199；bootstrap 后先观察缺接口 RED，再实现独立 scene 超分计划，不修改上游预算。
- **State evidence:** 初始化为 `NOT_STARTED`；尚无新策略候选片、整片观察或交付证据。

- **Preparation evidence:** 2026-10-19 JIM-05 先以新鲜全套 3206 passed、退出 0 及 21 个 SHA256 匹配记录 COMPLETED 后，按 Order=6 选择本项，观察到 NOT_STARTED/Design=None。完成并全文审阅 `D:/code/py/video-ai/docs/task-designs/JIM-06-design.md`，先仅回填 Design document，再写入并关联 `D:/code/py/video-ai/docs/task-handoffs/JIM-06-handoff.md`，最后记录 `NOT_STARTED -> READY`。设计确定独立 schema=2 单帧超分/原任务恢复、200 帧一一贡献、完整 PCM/SRT/ASS、技术候选与实际最终观察、收据最后的不覆盖交付、只读完成前缀和具体 RED/回归命令；JIM-03/JIM-05 直接输入无已知未解决冲突。本次仅后继准备，JIM-06 实现、新测试和真实影片观看未启动。

- **Completion evidence:** 2026-10-20 完成独立 schema=2 原生保留帧逐帧 RealESRGAN 超分、完整原文 PCM/SRT/ASS/font 候选合成、确切候选的最终连续影片观察准入、不覆盖且收据最后的 file-ID+SHA 交付、阶段内原任务/媒体恢复及只读完成前缀，记录 `IN_PROGRESS -> COMPLETED`。五项验收见 `D:/code/py/video-ai/docs/task-designs/JIM-06-verification.md`。初次专项 **189 passed、1 failed**（测试局部 10 秒预算提前耗尽），仅修正测试为生产冻结预算后，受影响 authentic 用例 **1 passed in 269.18s**；原失败证据保留。最终历史 **456 passed in 3866.66s**，fresh 全套 **3396 passed in 15981.10s (4:26:21)**，均退出 0，全套覆盖全部 190 个新用例。脚本和协调者独立重算均为 **342/342 文件 SHA256 匹配**；全库日志 `D:/VideoSi/cache/video-ai/logs/jim-06-full-final.txt`，独立核对 `jim-06-root-final-identity-check.json`。独立复审无剩余 Critical/Important，13 个生产文件在最终测试预算修正前后不变。真实 200 帧链 93/92/15、完整非零 PCM/字幕/媒体、完整交付恢复与两次只读重放均通过；使用本地替身和真实媒体工具，没有真实模型推理、云操作、邮件或实际观看质量声明。用户最终澄清“视频的长度帧不限制，帧率也不变”，保留原生 16 fps 与完整时长；没有截为 30 帧或改变帧率。全流程协调/修订留 JIM-07，真实服务和观看验收留 JIM-08。

### JIM-07

- **Start evidence:** 用户要求“完成任务JIM-07”，审阅执行流程后明确“那就按原计划执行吧”；已完整读取关联设计及交接，记录 `READY -> IN_PROGRESS`。实施计划 `D:/code/py/video-ai/docs/task-designs/JIM-07-plan.md`，本会话原生执行；进度与裁决见 `D:/code/py/video-ai/docs/task-designs/JIM-07-progress.md`。保留提供的 checkout 及只读 Git 元数据，先运行指定依赖失效测试 RED；尚无完成验收结论。

- **Completion evidence:** 2026-10-20 完成新策略公共协调、只消费/显式发布、新冻结修订、内容/准入双图、来源只读及可核验局部继承，记录 `IN_PROGRESS -> COMPLETED`。五项结果级验收见 `D:/code/py/video-ai/docs/task-designs/JIM-07-verification.md`。最终裸全库 **3552 passed in 19130.96s (5:18:50)，退出0**，逐例核对新增六模块 **156/156**、指定历史九模块 **195/195** 均通过、无重复；脚本及root独立重算 **364/364** 文件身份匹配，`git diff --check`退出0。最终日志 `D:/VideoSi/cache/video-ai/logs/jim-07-final-v3-all-pytest.txt`，覆盖与独立身份结果为同目录 `jim-07-final-v3-all-pytest-coverage.json`、`jim-07-final-v3-root-identity-check.json`。完整公共流程实际只新增2个Wan片段/8个超分帧、继承10帧、18帧接受，原运行字节/mtime不变；历史200帧主链93/92/15、两次只读完成重放、损坏证明阻断、原任务与修订逐边界恢复均通过。一次独立审查3项Important经RED/GREEN修复；全库发现的旧CLI未冻结锁回归及不合法identity-copy测试夹具也已修复/校正，所有失败与中止日志如实保留。保留原生16 fps和完整时长/文本/PCM/字幕，不设总帧上限；使用替身和真实媒体工具，没有真实模型、云、SMTP或实际观看通过声明，真实联调仍留JIM-08。未创建Git分支、提交或推送；后继准备在本次完成记录之后进行。

- **Goal:** 多轮选图、连续视频观察和显式返工能从确切进度恢复，只重做受到变更影响的依赖，且保留历史证据。
- **Scope:** 全流程协调、等待结果/CLI 续作、跨阶段中断点、修订运行、依赖失效和无关前缀复用；覆盖重选基准、重做画面、父片漂移、模型变更及邮件发送不明。继承各阶段已经实现的单次提交规则，不重新设计接口或延后其安全恢复要求。
- **Acceptance:** ① 在出图、TOS、邮件、选择接受、Wan、超分、合成及交付边界注入中断，续作消费原 ID/接受记录，不能重复收费或发送邮件。② 重选基准/重做父片建立新修订，受影响的图片、视频、超分、观察与候选失效，无关且身份核实的输入可复用。③ 原运行和旧接受记录不被覆盖；模型变更不能原地改已冻结 run。④ 已完成前缀重放不启动新推理或重新编码；未知提交保留诊断并等待核对。⑤ `awaiting_image_selection`、`awaiting_image_model_configuration`、`email_delivery_unknown` 和 `awaiting_continuity_review` 的恢复方式清楚且互不混淆。
- **Dependencies:** `JIM-04` 的图片依赖与选择闭环；`JIM-05` 的片段父子链及观察；`JIM-06` 的最终候选、交付和证据消费者。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点返工、版本和恢复约束；② `D:/code/py/video-ai/src/video_ai/production.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_state.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_inputs.py`；⑤ `D:/code/py/video-ai/src/video_ai/runtime/production_completed.py`；⑥ `D:/code/py/video-ai/tests/integration/test_make_video_recovery_contract.py`；⑦ JIM-04 至 JIM-06 完成后登记的依赖契约及恢复证据。
- **First action:** 按已完成的 JIM-07 设计，在 `tests/unit/test_scene_revision.py` 创建 `test_reselected_baseline_invalidates_reference_descendants_but_preserves_unrelated_scene`：S1→S2→S3 参考链与独立 S4，重选 S1 原候选，断言候选可复用、choice/参考后继及对应媒体失效，全组重新观察但 S4 内容可复用；bootstrap、Python -B 先观察缺新纯接口 RED，再实现 `planning/scene_revision.py`。
- **State evidence:** 初始化为 `NOT_STARTED`；尚无跨阶段故障注入或修订复用验证。

- **Preparation evidence:** 2026-10-20 JIM-06 先以最终全库 3396 passed、退出 0 及 342 项身份匹配记录 COMPLETED 后，按 Order=7 选择本项，观察到 NOT_STARTED/Design=None。完成并全文自审 `D:/code/py/video-ai/docs/task-designs/JIM-07-design.md` 后先回填 Design document；设计明确阶段结果兼容、消费与显式发布、跨阶段原任务恢复、内容/准入双图、来源只读与新修订冻结、继承视图/RevisionGuard、Windows 安全路径、逐边界故障注入及具体 RED/回归命令。再写入、全文核对并关联 `D:/code/py/video-ai/docs/task-handoffs/JIM-07-handoff.md`，33 个引用路径均存在，直接依赖无未解决冲突，最后记录 `NOT_STARTED -> READY`。本次仅后继准备；JIM-07 实现及新测试尚未启动，无新增外部模型/云/邮件操作。

### JIM-08

- **2026-10-22 latest bounded controls finished:** F1 caption对照`52bd2e82-76d2-4c94-85b9-fce91d78b7e4`第二窗73帧/30fps仍明显右移、右侧余量减小，failed_persistent_subject_tracking，stopgate后退出0、无第三窗。与原F1链相比有减轻但不合格。两链完整独立审计均通过3011/378/25资产/源/依赖/原始RGB/PTS/latent/RNG保护；最终对照确认两窗实际噪声逐值相同、文本确实变化、视觉逐值相同，17个研究helper语法通过。无新生产修改/裸全库/human接受，不再扫提示/seed/CFG；原版FramePack仅只读机制核查，未下载/推理。尚无通用颜色+构图修复，IN_PROGRESS。下方“第二窗继续/任务启动”为历史时点。

- **2026-10-22 latest F1 stop:** 原生任务`fb146581-7496-4f24-9984-c61075633c3d`在第二窗gate停止、退出0；73帧/真正30fps，主体右移、头喙出框，failed_subject_framing，无第三窗。短时氛围较接近不足以通过颜色。下方“任务启动”已是历史。补独立技术审计后，唯一新caption对照优先跟拍/图像平面约束，原模型/seed/视觉条件保持，仅重编码文本，先两窗失败即停。无human/生产接受，IN_PROGRESS。

- **2026-10-22 current F1 isolated feasibility:** 三个SVI首窗对照（暖光词、原FP16 DiT、原BF16文本路径）全部failed_color_lighting_fidelity，完整审计均确认3011/378/资源身份保持，停止后继。按自行修复/通用方案授权转查不同长期参照机制，限独立研究，不替换正式16fps/463帧。F1实际25资产42,866,789,142字节完整校验已完成；官方源pin/独立依赖、真实小CPU类/UniPC、全模型1274 meta键、分片mmap加载与native参数/前向逐值同的RED→GREEN检查通过。输入编码结束、VAE往返DeltaE76均值0.734，实际完整图内部筛查通过，仅允许实验。唯一原生链任务启动于`jim-08-framepack-f1-validation-20261022/trial-001/`，日志`jim-08-framepack-native-chain-`；最多9窗325帧/真正30fps、逐窗agent_image门槛、全累积latent原生解码，无额外生成窗混合。VAE内置tile合并明确保留，不冒称底层无加权。尚无F1视频/颜色/动态接受或生产集成；IN_PROGRESS。

- **2026-10-22 current original-text control:** 原FP16 DiT首窗15分11秒技术完成仍金橙高光/深暗背景，failed_color_lighting_fidelity，未续窗；完整final-audit核对3011/378及旧新资源SHA不变。剩余原FP8文本路径核验：同token正向relative L2约9.7%，不据此定根因；复用本地原BF16 UMT5无新下载，ConditioningLoader实际逐值相等、prompt/token绑定，graph仅文本路径变更，其余同原FP16 DiT对照。唯一原任务`6ed066d9-2f04-4a75-9ebd-504a83e306d4`采样中，证据`jim-08-svi-all16-validation-20261022/`及日志`jim-08-svi-original-bf16-text-first-window-0ae48e9e00f841d0901342a2c869ef63.log`。此阶段最多一个首窗，尚无质量/动态结论，未生产集成，IN_PROGRESS。

- **2026-10-22 current FP16 sampling:** 真正原FP16高/低Wan2.2 I2V两文件共57,155,829,584字节下载及完整SHA已通过，隔离目录保留。高/低各1095 F16张量、400 LoRA目标形状检查通过；新runner仅由case添加模型目录，graph归一除两个UNET名字外与原首窗完全相同。唯一原任务`d9283b1d-504d-41ad-b635-03e7ccb13de9`采样中，日志`jim-08-svi-original-fp16-first-window-9fc9efa014eb47b2bb78c94dcc382974.log`；原prompt/seed/anchor/LoRA/FP8文本/50步保留，没有叠加提示词修改，无新颜色/动态结论。仅一个首窗，未切生产/改变正式时基，IN_PROGRESS。

- **2026-10-22 precision control preparation:** 暖光描述单因素首窗`18fc7f99-f083-42e5-a4d6-c3c28ffe3c0e`10分40秒完成，仍金橙增强/背景变暗，failed_color_lighting_fidelity，停止续窗；新final-audit核对原3011/生产378/资源不变。原生SVI作者有50步颜色风格变化和FP8提醒，下一项只检验同Wan2.2 I2V DiT来源精度，主设计7.5已冻结真实FP16高低共57,155,829,584字节/不可变revision/SHA、60GB及15分钟传输上限。独立下载`jim-08-svi-fp16-validation-20261022/`执行中，完整校验及header/400层兼容通过才最多一个首窗；不叠加提示词修改，不变时基/生产，不宣称已修复。IN_PROGRESS。

- **2026-10-22 current user rejection:** 用户明确“这次画面颜色偏红，完全不对了”，否决SVI三窗审阅候选（SHA `3d74ccf06801c1fcc524027230f012139542669dc9ca55ce259db5b3c73f3472`）。human颜色rejected、production false；接缝/动作没有用户结论，不编造。下方等待播放/内部static pass均为历史。继续按颜色失真逐层诊断：先原图/原PNG/容器，再单因素验证提示中重复暖色描述；FP8仍是未排除限制，不做减红调色、未切生产。证据`jim-08-svi-color-rejection-20261022/`及verification新首节。保持IN_PROGRESS。

- **Current review candidate / waiting actual playback:** SVI第三原任务`0eab4ee4-a14a-4d4f-a09e-7ce8c34ee66c`成功，3窗81+76+76=233帧/16fps/14.5625秒，2处接缝5.0625/9.8125秒。主体材料色相对旧VACE改善，但冷色翼面/背景水面变暗/天空颜色保留lighting watch，motion与human接受全部待核实；未宣称修好。原样副本`reviews/JIM-08-SVI-Pro-color-continuity-review.mp4` SHA `3d74ccf06801c1fcc524027230f012139542669dc9ca55ce259db5b3c73f3472`已提供用户，已询问完整播放判断。23:58 SVI final-audit退出0：3011原运行大小/SHA/mtime、378生产基准和原/派生资源身份不变，3个intent与2个原latent继承边界吻合、sample全部有限、8 helper编译、自有服务已结束。没有生产源码/workflow改动或新裸全库，通用与更长链仍未验收，IN_PROGRESS。

- **SVI last bounded window executing:** 第二窗完成，裁5保留76，与首窗157帧/9.8125秒、接缝5.0625秒raw RGB/PTS核对；主体材料色未见强失真，内部static_screen_pass，但背景/水面变暗作为lighting watch保留，motion/human仍未确认。第三窗已按预算启动，仅继承第二窗原latent SHA `151cb7bbdd0e173538364f0a06abaf2ad4b091a7c61845231f953760e96125d5`，不同冻结seed，未改profile/调色。case/window-003与日志已保存，暂无末窗质量结论，IN_PROGRESS。

- **SVI current second window:** 首窗`af25fcb4-38d8-4fa8-a22f-fc2eec70e7b3`完成，81帧/5.0625秒，raw/latent/graph/PTS核对通过，采样及末帧未见强材料异色，内部static_screen_pass、motion unverified，无human接受。第二窗`62c551a1-e5e8-4093-880d-e6898631c6e7`执行中，确切继承首窗原sample latent SHA `b46eff3938abbf1e1a9356fc63b1ac085493b8aafc59c6e0eed01c3d037fbf5f`及同一anchor，独立冻结seed，不重编码RGB；第三窗未提交。不能由首窗改善推断跨窗已修好，IN_PROGRESS。

- **Current isolated SVI first window:** `af25fcb4-38d8-4fa8-a22f-fc2eec70e7b3`已受理执行，证据`jim-08-svi-pro-validation-20261021/window-001`，暂无完成/外观结论。固定KJ条件类和native WAN21.extra_conds四组CPU数值/latent缓存往返通过，SVI图3检查RED→GREEN。原BF16 LoRA裸键名匹配0层，仅加命名空间前缀后高低各400层匹配、800tensor逐值不变，派生文件独立；原始/派生/现有FP8基底和anchor SHA全绑定。首窗81帧/832×480/16fps/50Euler步，高21低29、CFG4/shift5；最多3窗且逐窗外观失败即停，不新增生产接受，IN_PROGRESS。

- **Current SVI feasibility after distortion diagnosis:** Rescale原任务`16f57007-760e-4144-b75f-f5bdd6cdc703`221.73秒技术完成，但原始PNG仍有颜色/材质/光照失真，known DeltaE76均值3.06→3.52，appearance failed、motion unverified；没有扫描倍率。该阶段final-audit退出0，3011原运行/378生产及VACE/VAE身份保持。用户继续排查/自行修复授权下转查SVI Pro误差回收：已核对官方源码/固定KJ条件类、16fps原生示例，双来源相同清单的2个Pro LoRA共2,453,857,104字节已下载到独立目录并完整SHA通过，未安装包/替换基础权重/改正式run。主设计7.3限定先CPU检查latent/padding、最多3窗/两边界、失败即停；当前无SVI GPU提交，现有Wan2.2 FP8量化限制明确保留。详见verification当前首节；IN_PROGRESS。

- **Current user correction / color distortion:** 用户要求按颜色失真继续排查并允许外部资料，已扩展为色相/色度/饱和度、曝光/对比度/截断与细节退化，不只测蓝通道。已保存VACE#44完整评论及社区refine源码：外部报告与本机现象接近，但正确mask/无损PNG仍有退化，混白去饱和历史不是已验证根治。标准CIELAB诊断4检查和原生RescaleCFG单因素图2检查通过；真实VAE/旧DiT边界测量执行中，后续先CPU验证flow rescale和被动审计hook，再一个固定输入GPU对照。记录`jim-08-color-distortion-20261021/`与verification新首节。没有新模型下载/生产改动，IN_PROGRESS保持。

- **Latest blue-cast outcome:** 两个新增原任务均完成：原BF16文本路径`1f88f71e-8bdf-4d5c-ba07-17ab691b79fd`218.43秒有部分颜色改善仍失败；仅20→50步`04eca9eb-3938-44d7-af86-b01f0b755da0`539.30秒仍明显蓝/青，两者appearance failed、motion unverified。真实53帧/41新增及134帧16fps审阅RGB/PTS均核对；没有新的human接受。原生CreateVideo/保存实现的色条/三原图/历史末帧5例未复现强蓝偏，B-R全图均值差最大0.154/255，不冒称所有局部误差皆已排除。当前缩小到生成阶段的局部外观/光照漂移，未锁定单一bug、未修好；不继续步数/seed盲调，不叠加题材调色。记录和审阅原件在`jim-08-color-trace-20261021/`及verification新首节，正式run/workflow保持；下方“执行中”均为历史时点。IN_PROGRESS保持。

- **22:21 integrity receipt:** `jim-08-color-trace-20261021/final-audit.json`完整审计退出0，原3011大小/SHA/mtime、378生产基准及模型/VAE完整SHA保持，两个任务case/helper/graph/history/client/输出身份吻合，自有服务已结束；15个helper编译通过，无新裸全库或human接受。未修改正式生产配置，不宣称通用视频生成已完成。

- **Latest user steering / blue-cast tracing:** 用户“先检查为什么偏蓝，你自己找方案修复吧 做好记录”，继续已有模型内证据调查，暂缓未选FramePack/时基方案。`jim-08-color-trace-20261021/conditions-002/report.json` 记录真实VAE数值对照，参考/历史/未知区/mask经native extra_conds与官方条件构造最大差0（不是完整官方推理独立等价证明）。文本对照发现官方中文逗号预处理差异，强制相同token后FP8/FP16与原BF16编码cosine正0.998466、反0.997547，未发现非有限值；差异本身不证明根因。原BF16条件实际续片对照仅替换文本路径，原生ConditioningLoader数值预检和2项图检查通过；唯一任务`1f88f71e-8bdf-4d5c-ba07-17ab691b79fd`已受理，尚无完成/质量结果。详见verification新首节；不修改正式run/生产workflow，IN_PROGRESS保持。

- **Latest repair outcome / next design choice:** 本轮原精度/较长历史/无旧父片的VACE初始生成各一个任务技术完成，仍无完整外观通过。初始生成`c394a442-207c-401b-bf1d-3064f74747bc`220.90秒、53帧/3.3125秒，采样白羽蓝偏减轻但背景/湖面曝光漂移，appearance failed、motion unverified；没有新续片或human_video接受。21:42最终审计`jim-08-color-diagnosis-20261021/final-audit.json`退出0，原3011项/378生产基准、原模型/VAE、三个case/helper与intent一致，保留一次审计检查器str/Path错误及修正；没有生产改动/新裸全库。主设计第8节已准备下一选择：FramePack F1统一首片/历史链，源片按原生30fps、真实PTS映射最终16fps，有限9窗、先完整权重/资源准入、下载上限60GB。这会改“源片原生16fps”契约，待用户明确选择；尚未下载/安装/运行F1，不继续堆VACE参数，不把部分颜色改善宣称修复完成。任务保持IN_PROGRESS。

- **History result / backend diagnosis:** 25帧历史对照`53dc5d76-08b6-4f25-9cb9-c3a3e3458725`已成功，300.64秒，69帧取41新增、16fps/134帧RGB与PTS核验；采样接缝更近、蓝偏减轻但后段仍偏蓝/变形，未通过，motion仍unverified。已停止旧Wan2.2→VACE2.1组合的时序参数试验，继续核对混合后端假设：用同一现有VACE原FP16、原图生成独立首片（无历史H0/N53/G53），不拼旧父片/继承接受。初始图2项RED→GREEN、H0原生CPU/reference/trim通过；`initial-trial-001`执行中，尚无完成/画质结论。主设计已明确通用方案须冻结首片/续写后端身份与兼容性证据，不因图片/帧率相同就默认兼容，IN_PROGRESS保持。

- **Color diagnosis / current probe:** 原生FP16对照`553b2477-c49e-42a2-97b7-d3373523a1bc`已技术成功，221秒，运行日志确认为FP16、无FP8；静态仍有蓝/青色羽毛和形态变化，appearance failed、motion unverified。因此VAE往返或FP8转换都不能充分解释现有问题。继续检查仅0.5秒历史的限制：25帧/1.5秒原生时间跨度已逐像素核对，新增41帧保持、G69纳入全部上下文，原FP16与其余采样/提示不改。历史图3项RED→GREEN、H5/H9/H25原生CPU路由/trim与实际25帧检查通过。唯一历史原任务`53dc5d76-08b6-4f25-9cb9-c3a3e3458725`执行中，尚无质量结论；新case/证据在`jim-08-color-diagnosis-20261021/`。不为题材做调色、不改正式run，IN_PROGRESS保持。

- **Color repair continuation / current execution:** 用户明确“那你继续修复吧，颜色也不对”，继续修复而不把颜色反馈扩写为动作接受。已在关联设计补第7节：原生VAE无扩散往返检查先排查颜色路径，再仅改变FP8→原始FP16加载作一次对照。五组色条/原图/历史往返退出0，实际采样未复现明显蓝偏，全图通道均值变化最大约0.506/255；首次探针未展平5维decode输出失败及修正均保留。精度图三项先RED后GREEN，真实graph仅一个weight_dtype字段变化；默认加载必须运行时确认FP16。独立原精度试验已启动，目录`D:/VideoSi/cache/video-ai/logs/jim-08-color-diagnosis-20261021/precision-trial-001/`，尚无完成/质量结论。不调色掩盖、不下载其他模型、不改正式run，状态IN_PROGRESS。

- **Generic-reference result / current state:** 20:09唯一VACE参考+历史对照技术成功，原任务`6f395e46-c206-4730-9a79-024640a17ce6`，217.84秒；53实际生成帧中取41新增，16fps/134帧/8.375秒无混合审阅副本像素/PTS精确核验。实际静态筛查仍有明显蓝/青色羽色和头颈/翼部外观变化，appearance failed、motion unverified、无human_video接受；按范围停止，没有追加请求或推广生产。最终临时检查4 tests OK、两尺寸/预算原生CPU检查通过，均非生产pytest或通用画质证明。20:11审计`D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/final-audit.json`核对原3011文件/378生产基准不变、完整原权重SHA匹配、采样/提示未改和唯一intent。通用目标已补入本项设计Goal/Scope/Approach/Acceptance；题材/镜头/长链必须分别验证，禁止白鹭专用分支，不能以单视频修补宣称完成。状态保持IN_PROGRESS，下面“采样中”是历史记录。

- **Generic-solution authorization / current execution:** 用户明确“把这些调整一下在方案中试试，还有切记你要做通用的视频生成方案，而不是针对某一个视频完成工作”。本项设计已增补通用参考/历史/镜头/模型能力分派及跨题材/多窗口验收边界，白鹭只作失败回归案例；本轮复用已有VACE，授权新增独立原图参考的一个受控对照，不再等待此步骤同意。临时验证器由外部case manifest提供所有内容、源文件、尺寸和时长；三项图连接检查先3fail后3pass，两尺寸/预算CPU原生条件/trim检查通过（首次float32逐值比较过严失败保留，改1e-7算术容差后通过，不放宽源PNG字节身份）。GPU原任务`6f395e46-c206-4730-9a79-024640a17ce6`已受理并采样，证据目录`D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/`；尚无画质/动态/其他题材通过。生产源码/workflow和原run未改；FramePack/其他模型与无限重试未授权。以下“下一试验待选择”是历史快照，任务保持IN_PROGRESS。

- **Next-probe preparation:** 本轮只读审计`jim-08-resume-readonly-audit-cefff00c56f747e4a22314ea395647f5.json`退出0，原run3011项大小/SHA/mtime、378项生产基准、SkyReels审阅副本匹配，仍6技术clip/3首片接受。下一次FramePack F1探针问题、固定输入/配置、最多9窗约10.8333秒、无混合接缝及停止条件记录于`docs/task-designs/JIM-08-industry-continuity-research.md`恢复审查节，待用户选择新增试验；研究原生30fps不替代正式16fps验收。HF元数据三仓库均超时，确切权重清单/下载量及本机内存峰值尚未核实。没有新模型下载、安装、推理或pytest，不宣称连续性修复。

- **Resume / current state:** 2026-10-21用户明确“按 JIM-08 交接继续。”；全文读取关联设计与同任务pause交接，保留原交接路径，记录`PAUSED -> IN_PROGRESS`。恢复范围为长场景连续性与外观方案、后续真实动态/成片验收及使用说明；不扩大模型试验授权。来源顺序为任务板本项、JIM-08-design.md与原交接、verification最新记录、continuity-diagnosis与industry-continuity-research、skyreels-v3-validation及其final-audit/visual-screening。第一动作是只读核对SkyReels首窗失败、原run连续性状态及方案限制，再整理具体下一方案与验证条件；不运行helper、不重复已有intent、不普通CLI推进失败链。原6/7技术生成、3/7动态接受及全部拒绝记录保留，未完成超分合成/最终观察/发布/完成重放。以下PAUSED是历史快照。

- **Pause / current state:** 2026-10-21用户明确“现在还剩什么工作，交接给下一个任务吧”。完整重读关联设计、保留旧交接原字节快照后，先刷新[同任务暂停交接](JIM-08-handoff.md)，再记录`IN_PROGRESS -> PAUSED`。原连续性问题未解决，不能COMPLETED或创建JIM-09；下一会话继续JIM-08。现有配置/选图/QQ收信与三个首片接受保留，原run6/7技术生成、3/7接受；原三个续片、VACE及SkyReels首窗均未通过一致性准入，后者只有agent_image外观失败、动作未验证，未跑第二窗。剩余为具体下一方案选择及连续性修复、三scene/多片完整动态验收、超分/完整旁白字幕合成、最终观看试听、显式发布及重复续作核验。全部自有推理/下载已结束，本次只做交接、不启动新试验。恢复第一动作只读核对交接、verification、诊断/调研与SkyReels final-audit/visual-screening，再整理可审阅下一方案；不自动推进失败链/重交intent或换模型。下方IN_PROGRESS及等待描述均为历史执行快照，以本条和表格PAUSED为准。

- **Current validation:** 用户授权的[SkyReels-V3隔离验证](../task-designs/JIM-08-skyreels-v3-validation.md)已完成第一窗：官方BF16、8步、632.52秒，132新增帧/24fps=5.5秒，本机可运行。实际采样发现后续暖金光照减弱、背景转灰绿及羽毛阴影变冷，agent_image外观筛查失败，按约定停止第二窗；未声称完整动态播放或human_video通过。审阅副本`D:/VideoSi/projects/video-ai/reviews/JIM-08-skyreels-v3-first-window.mp4`共8.541667秒，3.041667秒起新增，SHA及逐帧/PTS通过；显式历史时基适配不改变原16fps验收。18:41最终审计10模型完整SHA、17固定代码身份、原run3011字节/mtime及378生产基准身份均一致，推理正常退出；加载适配与失败前置探针保留。无第二窗intent、参数重试或其他模型调用，无生产迁移/新全库；JIM-08继续IN_PROGRESS，原连续性问题未解决。详见verification当前段及`jim-08-skyreels-v3-validation-20261021/final-audit.json`。

- **Latest research:** 2026-10-21 用户授权调研长场景业界方案，已完成[连续生成方案调研](../task-designs/JIM-08-industry-continuity-research.md)，核对官方实现与部署条件。先评估SkyReels-V3专用视频续写的资源/时基准入，FramePack作为从选图重做分钟长镜头的备选，LongLive/MemFlow作长期记忆架构参考。V3原生24fps、FramePack30fps与当前16fps契约不同，24GB/32GB峰值未实测；Seedance2.5云端extend已核验，但旧片帧率/像素低于其输入门槛。无新增模型下载、安装或生成，生产代码与原验收未改，没有新动态通过；原失败和短场景方案边界保留，状态IN_PROGRESS。完整资料快照与待选择的小样停止条件见报告及verification当前段。

- **Current diagnosis:** 用户明确三个续片都不连续，要求深度分析后解决，已停止最后片/合成/发布。原三个首片接受仍保留，三个续片均未准入。接缝采样/原样连续副本/原run3011文件不变及native9帧APNG条件探针已完成；A/B同模型隔离诊断均完成但未证明连续；C1暴露高低阶段噪声污染，已原生CPU复现；同假设C2已完成并消除历史噪声，但新增接缝仍未改善，不推广生产；用户现已同意JIM-08-continuity-repair-proposal.md的VACE14B单段试验；已交叉核对固定版本/34,675,323,640字节/SHA，14:07完整下载/SHA通过、14:08原生CPU探针通过；14:12唯一scene3 GPU试验技术完成，53生成/41新增帧及134帧完整副本核实。用户明确“画面确实变了，有问题”，VACE一致性失败，不推广或增加试验。已只读准备JIM-08-whole-scene-proposal.md及3份原Wan2.2整段graph预览，用户追问长场景后已将整段方案限定为短场景候选，补入跨窗口状态保持的必要条件；原多片续接验收不变、尚未批准新生成路径；未生成新视频，原3011文件及378基准身份不变，非生产验收。根因证据、受限推断、原始失败及修复边界见`JIM-08-continuity-diagnosis.md`和verification最新段；技术SHA正确不能保证动态连续。状态IN_PROGRESS。下方等待用户接受续片是被本次拒绝取代的历史状态。

- **Current continuation gate:** 第二轮真实续片三个均完成，12:07:16原CLI退出3 awaiting_continuity_review/error=null；6/7技术完成、3/7真实动态观察已接受，最后scene1 clip3尚未生成。独立审计确认每个续片start.png与父片末保留原生PNG大小/SHA一致，丢首帧且保持16fps；新三段模板仍未观察。证据`jim-08-real-wan-second-clips-b1776b2b1b674560a8045e443c552d76`及-gate-audit.json。等待用户完整播放三组父片/续片确认衔接后继续，不把已确认首片外推到续片，状态IN_PROGRESS。以下3/7首片完成为历史状态。

- **Latest dynamic review:** 用户明确“三段都看完，正常”，三段首片human_video观察已于11:51–11:52由原CLI分别消费、observation-accepted.json落盘，三个首片均接受。实际退出2 blocked/error=null只是后续片pending，消费入口未提交续片。已普通同run继续第二轮续片，原父末保留帧续接；尚未接受未来片段或成片，状态IN_PROGRESS。用户原话0025fed5及三份CLI证据见verification最新段，以下0动态接受为历史状态。

- **Current real phase:** 同run真实Wan三个首片已完成，各93帧/5.8125秒，11:15:25原CLI退出3 awaiting_continuity_review/error=null；当前计划7片中3片完成/0动态观察接受，4续片待父片观看。日志及静态字节审计`jim-08-real-wan-prepared-directories-44f65e85735445dea080d2b12af2865a`，三段完整source.mp4和精确观察模板均已准备。此前启动失败仅因本run comfy/user目录不存在，补受控运行目录后恢复，无生产/测试或冻结配置变更；原失败保留。用户已确认静态风格及QQ收信，图片整组准入通过。现有工具无完整视频观看，等待用户真实连续播放回复，不以静帧冒充观察；尚无成片/发布，状态IN_PROGRESS。以下等待图片/收信/首片是历史状态。

- **Latest selection:** 用户明确场景2、3均选第2张，10:41:41原CLI已将两个确切选择及SHA保存进第二批accepted.json，原提交副本摘要核验一致。实际退出3 awaiting_image_selection/error=null、all_images_accepted=false，未写complete-acceptance；仅整组主体/风格观察及实际QQ收信仍待确认，无Wan。证据`jim-08-real-accept-scene2-2-scene3-2-aadf31d6ab174bbc8d92cf49e5f83388`及verification最新段；状态IN_PROGRESS。以下“两个选择待答”为历史描述。

- **Current execution:** 当前版本裸全库**3651 passed in20068.38s（5:34:28），pytest退出0**，09:55:56结束，前缀`jim-08-grounding-full-regression-a1596fa456d04178b7cbbed7197dd9cc`。378项前后与独立重算全部匹配、3651唯一节点零非通过，独立审计`jim-08-root-final-full-audit-3605d610b6474dfb8cbfb8cbab6c9730-audit.json`。运行目录PowerShell验证外壳的OrderedDictionary分组误报导致外壳退出1，原失败保留、独立复核后只修外壳统计，未改生产/测试或假记退出码。参考恢复47项通过、复审无剩余具体问题。第二批4张实际TOS参考图已完成、QQ SMTP250接受；该基准对象匿名正常TLS GET实际403。当前awaiting_image_selection，两个选择/整组观察/实际收信仍待真实回答，无Wan/成片/发布，任务保持IN_PROGRESS。用户每30分钟仅进度的活跃执行汇报已持续完成；无外部定时任务。

- **Latest progress:** 用户选左图，原CLI03:18:55返回 `image_batch_accepted`；03:19普通续作被冻结800字节参考prompt限制拦下，尚无TOS/关联图/Wan。只读修复设计核查中，保留原配置、基准与所有事实。前次裸全库368pass/3fail后中断保留，三项均为HTTP fixture误用json.loads读取带尾注prompt；仅fixture改raw_decode，RED后3pass。03:22:06启动新裸全库，前缀 `jim-08-grounding-full-regression-59e3d586f7964bb092797401ec59178d`，未有最终结果。用户要求后续每30分钟仅报进度，不贴日志；任务仍IN_PROGRESS。

- **Current gate:** 新scene-local wire真实run `20261021-014723-4ebdc1fecab2` 首次规划通过，实际28.9375秒/3个同主体scene/7个计划片段；即梦4.0已实际生成两张2560×1440基准图，QQ SMTP250接受，CLI退出3 `awaiting_image_selection`。已展示contact_sheet并询问用户选左/右及真实收信附件事实，均待答；TOS参考/Wan/全片仍未执行。当前裸全库3630项已于01:50:35 +08串行启动，375项前置身份快照，日志前缀 `jim-08-grounding-full-regression-25bcafeba7a14b6eacef7ed1014deb8f`，运行中而非通过。状态保持IN_PROGRESS。

- **Upgrade progress:** 用户明确“不用严格是30秒，实际多长就是多长”，以完整配音/实际时间轴为准。14B自有服务pull退出0、所有blob SHA核对一致并已停；模型精确冻结已实现。前三个14B实测均退出2并保留，未发生云/TOS/SMTP。按实际缺陷先RED后增加编号约束、反馈及可逆scene-local环境wire，修复审查发现的历史候选容量阻断恢复；当前九模块230 passed in57.35s，日志 `jim-08-environment-final-targeted-3ee5bc7736714da3bc2f7de8bffefb3c.log`。新独立公共CLI `20261021-014723-4ebdc1fecab2` 正在运行，日志前缀 `jim-08-real-14b-environment-54251c42e0fa477397605a52dcf45bda`；裸全库待串行执行，不声明官方出图/邮件/影片通过。详情见verification当前续作节。

- **Upgrade resume:** 消费同任务交接并保留历史路径，依据用户“同意，升级吧”及原“完成JIM-08”继续执行，记录 `READY -> IN_PROGRESS`。剩余为显式本地模型升级及精确旧恢复、当前回归和原全链路真实验收。首个动作是在自有空闲loopback端口下载已批准14B，同时在现有模块先RED后实现模型绑定；来源为本项已更新设计、verification、执行计划及原始run证据。不得更换已确认4.0或把安装成功当作规划/观看通过。

- **Model-upgrade resolution:** 2026-10-21用户明确“同意，升级吧”，授权之前已具体提出的Qwen3 14B约9.3GB下载、本地scene planner显式选择与旧8B精确恢复、独立实测。完整读取本项设计及同任务pause交接，模型方案缺项解除，记录 `BLOCKED -> READY`。即梦图片仍4.0；时长目标仍30秒，没有把模型升级同意解释为接受33秒成片。授权不证明14B效果、云权限、实际邮件或影片通过。

- **Latest blocker evidence:** 最新thinking独立run `20261020-233458-996ce31b92b0` 仍在第二个完成提案漏speech_0002/重复speech_0003，被完整性校验拒绝，退出2；实际539帧/33.6875秒。原文案/前置固定设定文案、普通/思考模式均未得到可接受规划；没有云图像、TOS、SMTP、视频或发布。当前八模块213 passed in34.80s，退出0；新裸全库未执行。用户已确认即梦4.0及提供本地凭证/桶，不能重问。已取14B公开元数据（约9.3GB），未下载，向用户询问是否升级本地分镜或保留8B诊断，以及30秒容差，均尚无答复。先保存旧交接快照并刷新同任务pause交接，再记录 `IN_PROGRESS -> BLOCKED`；解除条件为用户明确下一步本地分镜方案，允许对应修复/配置实测。具体证据和拟议范围见verification最新进展；下方IN_PROGRESS为历史快照，未满足COMPLETED。

- **Latest execution evidence:** v2 run `20261020-225656-80131ea756f2` 和修复后独立run `20261020-230858-4b618d9ad6f0` 均在第二次已完成规划提案中因未来来源被拒绝，退出2；后者500帧/31.25秒，不是精确30秒。原请求/响应和配音保留，没有云图像、TOS、SMTP或影片接受。已修复场景引用transport与纠错诊断，保留完整原文/容量guard/一次纠正/历史精确恢复；合法fixture真实RED后最后八模块204项通过。当前源码/测试已变，前置全库不再覆盖，新的裸全库待执行。新独立试跑已启动（日志前缀 `jim-08-real-start-source-repair-4153c1def6bf468fa06047fd7d824e97`）；具体日志与边界见 `docs/task-designs/JIM-08-verification.md` 最新进展。状态保持IN_PROGRESS，下方“尚在执行、未改源码”均为历史快照。

- **Real execution evidence:** 2026-10-20 首轮真实本地run `20261020-225154-10d18e7c8a70` 已完成13单元GPT-SoVITS配音（21.9秒PCM、时间轴495帧/30.9375秒），22:53:39退出2、scene_plan blocked：无损prompt/schema加完整输出保守预算42,322字节上界>32,768，在规划请求前拒绝。未到即梦/TOS/SMTP。按用户文案委托保留原运行，另以三个连贯画面描述的`jimeng-acceptance-v2.txt`新建本地run `20261020-225656-80131ea756f2`，日志前缀 `D:/VideoSi/cache/video-ai/logs/jim-08-real-start-v2-c06984923cba4a20b704029bf5e399b9`；尚在执行，状态保持IN_PROGRESS。未修改生产源码/测试、冻结原文或容量guard，未重发未知任务，未声明真实收信/视觉/正式交付通过。

- **Resume evidence:** 消费同一入口交接并保留历史路径；用户原“完成JIM-08”、后续30秒文案委托及本轮“同意，那就用4.0吧”构成继续实施上下文。配置缺项解除后记录 `READY -> IN_PROGRESS`。剩余范围为真实CLI配音/规划/官方候选及参考读取、QQ收信、用户选择和完整动态/最终观察、发布和完成重放；来源依次为本项设计、verification、正式任务配置/原文、已绑定官方原字节及本地凭证文件。第一实施动作为同进程临时加载已提供凭证，执行现有make-video公共CLI，到首个等待点测量真实时间轴并核对三画面/两片连续链；不伪造观察、不变速或截断旁白，不自动新增返工尝试。

- **Resolution evidence:** 用户明确“同意，那就用4.0吧”，在此前授权助手准备30秒文案的上下文中确认白鹭方案及4.0模型。凭证三项和桶已提供；已按现有解析器建立正式任务配置/原文及真实官方材料绑定的参考能力档案。本机Python/OpenSSL成功获取官方完整HTML原字节，SHA=`c683c91f401d3e2a78d2fe0a0fbd623ac81b33cb910f33c63162c4145b9d1011`；档案明确只准入本次2560×1440原图、15,000,000字节及保守800 UTF-8字节提示词，不将本地下限/字节上限冒称服务精确限制。配置解析退出0，doctor真实本地预检退出0；日志 `D:/VideoSi/cache/video-ai/logs/jim-08-real-config-prepare-024fd93e79b34ddfa273636ec473f350.log`、`jim-08-real-preflight-317416029d7e47029faadb4b49a69f15.log`。完整读取关联设计与同任务pause交接，原输入缺失条件已解除，记录 `BLOCKED -> READY`。远端权限、真实收信及观看仍待本项实施，不混作解除配置缺项之前的已通过事实。

- **Sample preparation evidence:** 2026-10-20 22:46 +08:00 用户明确授权助手准备文案并指定视频30秒；已准备独立 `.proposed.txt` 三段白鹭文案和 `.proposed.json` 4.0模型完整配置建议，保留原实际声音、媒体、权重及工作流，合入已提供桶设置。本地配置各解析器、原配置/voice/media保留核对退出0，日志 `D:/VideoSi/cache/video-ai/logs/jim-08-30second-proposal-d2ae8faca69a4f939fa139a67acafeb6.log`。建议待用户确认，能力档案尚未核验；没有配音或真实调用，不宣称实际30秒。该目标只作用于本次样片，不设全局帧数上限；状态保持BLOCKED。

- **Partial input evidence:** 2026-10-20 22:41 +08:00 用户表示SMTP授权码已保存；原本地凭证文件JSON合法，AK/SK及SMTP三字段非空，独立检查进程可临时加载同名环境变量。脱敏报告 `D:/VideoSi/cache/video-ai/logs/jim-08-smtp-credential-check-fa69f351a461431580edd4b7138023a6.json`；未输出值、未远端鉴权或发信。凭证及桶本地输入已提供，仍待最终模型确认、文案、核验参考能力和完整运行配置；状态保持BLOCKED。此前缺SMTP描述均为历史检查。

- **Partial input evidence:** 2026-10-20 22:19 +08:00 用户确认已创建桶`testvitest`、华北2（北京）；创建 `D:/VideoSi/projects/video-ai/config/jimeng-reference-settings.json`，region=`cn-beijing`、endpoint=`https://tos-cn-beijing.volces.com`，只引用AK/SK环境变量名。现有参考配置解析器/根字段检查退出0，日志 `D:/VideoSi/cache/video-ai/logs/jim-08-tos-settings-check-fcebc4a3dfa64f36ac48414f2d0ec8c6.log`；无云请求，权限及参考读取仍未核实。桶设置已提供，SMTP授权码、文案、最终模型确认/核验能力和完整配置尚未齐备，状态保持BLOCKED。

- **Partial input evidence:** 2026-10-20 21:55 +08:00 用户提供 `D:/VideoSi/projects/video-ai/config/jimeng.credentials.local.json`；JSON合法，AK/SK两字段非空，一次独立检查进程可临时加载同名环境变量。未输出或记录秘密值，未测试远端鉴权；现有程序不会自动读取该JSON，实际CLI须同进程加载。脱敏报告 `D:/VideoSi/cache/video-ai/logs/jim-08-credential-file-check-b1ca7bb370df43719e304182a9db26d6.json`。SMTP、已有TOS设置、能力档案、运行配置和文案缺项尚未解除，状态保持BLOCKED；此前凭证缺失描述保留为历史检查，不代表AK/SK仍未提供。

- **Start evidence:** 2026-10-20 用户明确要求“完成JIM-08”；完整读取本项已关联设计、入口交接及任务定义，记录 `READY -> IN_PROGRESS`。按设计先建立 `docs/task-designs/JIM-08-verification.md` 五项证据矩阵；保留当前 checkout、前序修改和只读 Git 元数据。任务配置及原文尚不存在，默认凭证变量仅检查存在性，未读取或输出秘密值；真实请求等待实际输入，不以示例模型、替身观察或自编文案替代。

- **Blocked evidence:** 2026-10-20 本地文档/合法示例更新完成，最终九模块 **264 passed in 5.13s，退出0**；示例加载、相对链接/锚点和11个CLI选项核对退出0；**363项源码/测试/workflow** 与JIM-07最终全库基线SHA及清单相同。最初81 passed/75个临时目录权限错误、改独立basetemp后156通过及检查器一次错误假设均保留日志，未修改生产逻辑或测试。本轮完整媒体/裸全库只引用相同生产字节的前置基线，不登记为本轮重跑。真实任务配置 `D:/VideoSi/projects/video-ai/config/jimeng-acceptance.json`、原文 `D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance.txt` 不存在，三个默认凭证变量未设置，未提供实际模型/参考能力及已有桶设置，真实请求无法开始。已先写入同任务pause交接 `D:/code/py/video-ai/docs/task-handoffs/JIM-08-handoff.md`，再记录 `IN_PROGRESS -> BLOCKED`；原入口快照保留在D盘日志。完整证据 `D:/code/py/video-ai/docs/task-designs/JIM-08-verification.md`。用户提供确切配置/文案路径并在执行环境设置所声明变量，按设计核验后才能BLOCKED→READY；没有真实云、邮件、观看或发布通过声明，未满足COMPLETED。

- **Goal:** 用实际账号、邮件和连续样片确认新流程可用、画面一致性满足要求，并交付可照做的配置和使用说明。
- **Scope:** 执行替身端到端、全链路故障用例及相关旧回归；配置用户模型/参考模型、AK/SK、QQ SMTP 授权码与已有 TOS 桶；使用符合总体方案验收范围的短文案完成真实生成、邮件接收、人工选图、动态观察、整片验收和同 run 重复续作；更新 `README.md`、`config/README.md` 与示例配置。默认测试不执行真实云调用或真实发信。
- **Acceptance:** ① 各阶段定向和相关历史回归结果落盘，失败已修复，没有把未运行项登记为通过。② 用户配置的模型在实际请求中可核对，官方生成和 TOS 参考读取均有真实结果。③ 用户 QQ 邮箱收到包含基准及候选的邮件，实际选择与收到的图片一致。④ 同一主体至少三个画面、一个至少两段的连续长画面完成实际观察，未发现未解决的一致性问题；完整旁白/字幕与正式输出核对。⑤ 重复续作没有新增出图、Wan 提交、编码或重复邮件；使用说明包含等待、选图、授权码配置、模型切换和返工方式。总体方案 Acceptance 五项逐项有可定位证据。
- **Dependencies:** `JIM-07` 完成的可恢复全链路及其所消费的各阶段产物。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 的 Tests、Acceptance、Risks；② 本任务板各任务实际登记的完成和验证证据；③ `D:/code/py/video-ai/scripts/bootstrap.ps1`；④ `D:/code/py/video-ai/README.md`；⑤ `D:/code/py/video-ai/config/README.md`；⑥ `D:/code/py/video-ai/config/production.example.json`。
- **First action:** 按总体方案五项 Acceptance 制作验收检查表，将替身证据、真实服务证据及实际观看结论分开，并核实真实运行配置已齐备。
- **State evidence:** 初始化为 `NOT_STARTED`；收发地址已确认，官方及 SMTP 凭证、TOS 配置与最终测试文案尚未提供；没有真实生成、收信或一致性验收结果。

- **Preparation evidence:** 2026-10-20 JIM-07先以最终裸全库3552 passed、退出0，新增156/指定历史195全部覆盖及364项身份一致记录COMPLETED；按预定义Order=8选择本项，观察NOT_STARTED。随后完成、全文自审并先关联 `D:/code/py/video-ai/docs/task-designs/JIM-08-design.md`，明确真实配置接收/停止规则、现有CLI逐门槛执行、五项验收矩阵及具体测试命令。再按模板创建、全文自审并关联 `D:/code/py/video-ai/docs/task-handoffs/JIM-08-handoff.md`，19个既有来源引用均存在，直接依赖约束无冲突，最后记录 `NOT_STARTED -> READY`。本次仅设计及交接准备，尚未开始JIM-08实施；真实模型、凭证、桶和文案由其配置阶段接收，不将其尚未提供误记为已验证。

## Risks

- **一致性结果：** 参考图、固定视觉设定及尾帧续接不能保证模型每次成功。必须按整组图片、动态过程和最终连续影片分别观察；技术测试、固定种子与相似度分数均不能代替结论。
- **模型选择与能力：** 用户自行设置模型；仅支持纯文生图的模型可用于基准，关联画面需配置支持参考图的模型。未知能力不能靠名称猜测，也不能自动换模型。
- **真实服务配置：** 官方模型权限、AK/SK、QQ SMTP 授权码、已有 TOS 桶和 URL 可读取性未验证；可先用替身完成代码任务，真实验收仍必须具备相应输入。只有在具体执行时缺少必要输入，才按状态机记录实际阻塞。
- **等待与成本：** 分批基准选图、整组确认、连续视频观察和显式返工会增加等待及实际调用费用；首版不无限重试或自动重新付费提交。
- **旧路径兼容：** 当前生产链的槽位、SDXL、Comfy 请求身份及完成前缀校验关联较多；必须按新策略版本分派，不放宽旧契约来迁就新记录。
- **设计细化：** 当前是基于已确认总体方案的任务拆分，各任务尚无详细实施契约。设计时若发现需要改变已确认行为，应明确记录并向用户核实，不能以任务细化为由扩大范围。
- **范围和证据：** 本轮只更新总体设计状态并创建任务板，不登记任何实现完成、测试通过、真实邮件或图像结果；不创建普通后继交接，也不启动首个任务。
