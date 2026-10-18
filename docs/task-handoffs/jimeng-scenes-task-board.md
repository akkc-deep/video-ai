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
| 3 | JIM-03 | 候选图邮件、基准选图与等待续作 | READY | JIM-01, JIM-02 | D:/code/py/video-ai/docs/task-designs/JIM-03-design.md | D:/code/py/video-ai/docs/task-handoffs/JIM-03-handoff.md |
| 4 | JIM-04 | 参考图存储与关联画面一致性生成 | NOT_STARTED | JIM-01, JIM-02, JIM-03 | None | None |
| 5 | JIM-05 | Wan 连续片段、末帧续接与动态观察 | NOT_STARTED | JIM-02, JIM-04 | None | None |
| 6 | JIM-06 | 新时间轴合成与成片一致性交付验收 | NOT_STARTED | JIM-03, JIM-05 | None | None |
| 7 | JIM-07 | 跨阶段恢复、修订运行与局部返工 | NOT_STARTED | JIM-04, JIM-05, JIM-06 | None | None |
| 8 | JIM-08 | 全链路回归、真实样片验收与使用说明 | NOT_STARTED | JIM-07 | None | None |

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

- **Goal:** 基准画面候选能发到用户 QQ 邮箱，用户通过编号作出可验证选择，程序保存进度并安全等待/续作。
- **Scope:** SMTP SSL、邮件正文与编号、基准/候选/原文对照、整组对照图、实际附件及编码后拆包；稳定 Message-ID、发送意图和回执；基准与普通批次的选择文件、SHA256 接受记录、整组一致性观察绑定；`--image-selection` 入口；`awaiting_image_selection` 和 `email_delivery_unknown` 结果及锁/服务释放。发件和收件均为 `318575094@qq.com`。不自动收信或部署选图网页。
- **Acceptance:** ① 本地 SMTP 替身收到实际图片、可复制编号、原文和一致性要求；15 MiB 默认上限按完整 MIME 字节计，拆包不丢候选。② 普通续作不重复发送已接受邮件；发送结果不明不会自动重发；修复邮件配置不重新出图。③ 当前批次每画面恰好一张且身份正确才能接受；重复、缺项、跨 run 和变化图片拒绝；部分选择仅作草稿。④ 单纯选编号不自动伪造整组一致性通过；未完全选图并确认整组前无新 Wan 提交。⑤ 等待返回后锁和本次自有服务释放，续作保留候选及已选基准。本任务用测试驱动模拟后续批次，不依赖尚未实现的参考图生成。
- **Dependencies:** `JIM-01` 的候选图片/模型记录；`JIM-02` 的场景、批次与基准依赖信息。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点“候选图、邮件和等待状态”“用户选图与续作”；② `D:/code/py/video-ai/src/video_ai/cli.py`；③ `D:/code/py/video-ai/src/video_ai/production.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_state.py`；⑤ `D:/code/py/video-ai/src/video_ai/runtime/production_visual_review.py`；⑥ `D:/code/py/video-ai/src/video_ai/media/images.py`。
- **First action:** 按已完成的 JIM-03 设计，在 `tests/unit/test_selection_email.py` 建两 scene、同名局部 candidate ID、真实 PNG、完整原文和基准用途的 fixture，断言实际 MIME 的编号/附件/编码后限额；先观察接口缺失失败，再实现纯邮件构建。
- **State evidence:** JIM-02 先记录 COMPLETED 后，完成、全文自审并关联 `D:/code/py/video-ai/docs/task-designs/JIM-03-design.md`；设计明确 SMTP/MIME、批次/基准身份、选择/观察精确结构、独立 schema=2 结果、CLI 准备运行分派及恢复/测试。随后写入并关联 `D:/code/py/video-ai/docs/task-handoffs/JIM-03-handoff.md`，由 `NOT_STARTED -> READY`。本次仅后继准备，JIM-03 实现未启动，新测试尚未创建/运行；收发地址已确认，SMTP 授权码/真实投递仍未验证。

### JIM-04

- **Goal:** 选定的基准图实际参与关联画面的生成，重复主体和场景有固定视觉参考，而非独立文生图后再碰运气筛选。
- **Scope:** 新增 `src/video_ai/adapters/reference_storage.py`，使用配置的现有 TOS 私有桶保存选图并签发 HTTPS GET URL；核对模型参考图能力、数量和尺寸；同模型引用或用户明确配置 `reference_generation.req_key`；按依赖批次生成候选并复用 JIM-03 邮件/选择流程；请求绑定共享设定和固定基准。未知/不支持参考的模型不能自动换模或退回纯文字生成。
- **Acceptance:** ① 替身请求中确有已接受基准的参考输入，且每个输入对应主体/背景用途清楚，同主体跨画面直接引用同一固定基准。② 基准未选、能力不明、配置缺失、参考数量超限或 URL 有效期不足均在关联画面付费提交前停止。③ 本地 SHA256、TOS 对象来源和依赖关系可核验，预签名 URL 不泄露；不创建桶或修改桶权限。④ 未提交请求可刷新 URL，已受理任务只能查询原任务；恢复不重新出图。⑤ 后续候选能按批发邮件，全部选图和整组一致性确认通过后产出精确的 Wan 输入清单。实际服务是否能取图留到 JIM-08 真实验收。
- **Dependencies:** `JIM-01` 的官方图片任务适配；`JIM-02` 的视觉设定/参考依赖图；`JIM-03` 的已接受基准及分批邮件/选择接口。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点“一致性设定与参考图”；② `D:/code/py/video-ai/src/video_ai/runtime/production_visuals.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_visual_records.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_inputs.py`；⑤ 总体方案末尾的即梦参考输入与 TOS 官方资料；⑥ 已完成 JIM-01 至 JIM-03 时登记的直接输入契约与验证证据。
- **First action:** 从基准选择记录到模型实际 `image_urls` 的路径定义存储、预签名和请求身份契约，并设计过期 URL、缺参考能力时零生成提交的用例。
- **State evidence:** 初始化为 `NOT_STARTED`；模型选择、TOS 桶与权限待本地配置，没有真实上传或取图验证。

### JIM-05

- **Goal:** 用户选中的图片进入 Wan；同一长画面的动态片段沿实际保留末帧续接，并在漂移或未观察时阻止继续传播。
- **Scope:** 修改 `src/video_ai/planning/production_visual_plan.py`、`src/video_ai/runtime/production_visuals.py` 与 `src/video_ai/media/frames.py`；首片读取选图副本，续片使用父片实际保留末帧；保存父片/输入图/帧索引身份、衔接帧丢弃和逐帧映射；实现父片动态过程观察与 `awaiting_continuity_review`，明确连续续接和有意切镜两种边界。复用 Wan 模型与工作流，不改成即梦视频。
- **Acceptance:** ① 首片输入与用户选择精确关联，未经完整图片准入不请求 Wan。② 续片输入来自父片最后一个实际保留原生帧，不能取裁掉的补帧；父片未观察或不一致时不提交其续片。③ 续片申请衔接余量并丢首帧，最终映射按原文时间轴准确覆盖，不循环、冻结或截短旁白补时。④ 视频提示词保留固定主体/环境；过程观察不能仅用首尾截图或相似度代替。⑤ 中断恢复使用原 Comfy 提交，父片身份改变拒绝复用续片；独立场景等待和失败状态不混淆。
- **Dependencies:** `JIM-02` 的 scene/clip 时间预算；`JIM-04` 的完整已接受图片清单、基准及共享视觉设定。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点“动态视频的延续与验收”；② `D:/code/py/video-ai/src/video_ai/planning/production_visual_plan.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_visuals.py`；④ `D:/code/py/video-ai/src/video_ai/media/frames.py`；⑤ `D:/code/py/video-ai/workflows/wan22_i2v_14b_api.mapping.json`；⑥ `D:/code/py/video-ai/src/video_ai/runtime/_source_clip_review.py`；⑦ `D:/code/py/video-ai/src/video_ai/planning/final_review.py`。
- **First action:** 为一个跨两段的连续画面确定父片末帧选择、续片首帧丢弃和总帧预算的数值契约，先建立可观察的帧映射验收例。
- **State evidence:** 初始化为 `NOT_STARTED`；尚无动态生成或续接观察结果。

### JIM-06

- **Goal:** 新画面/片段时间轴能复用超分与合成输出完整候选片，只有整片一致性实际验收后才正式交付。
- **Scope:** 将 scene/clip 映射接入超分、完整 PCM/字幕合成、完成前缀与交付消费者；新策略识别原文完整性、整组图片观察、动态观察及最终连续视频观察；候选输出与正式交付分离。保留现有输出规格和历史策略契约，不把编码技术检查当作画面一致性通过。
- **Acceptance:** ① 多句共用画面和跨片续接均保持完整配音、字幕及总帧数；首尾和停顿覆盖不丢失。② 最终观察绑定确切候选、选图、基准及动态片段身份；未核实或不一致不产生正式交付收据。③ 有效实际验收后才复制确切已验收版本，重新编码或文件变化使观察失效。④ 历史运行仍按原审核/交付逻辑恢复，未被新策略替换。⑤ 候选片可以保留供检查，不伪报已正式交付。
- **Dependencies:** `JIM-03` 的选择/一致性观察记录；`JIM-05` 的源片、连续链、动态观察及精确帧映射。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点最终验收和版本兼容要求；② `D:/code/py/video-ai/src/video_ai/runtime/production_upscale.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_composition.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_delivery.py`；⑤ `D:/code/py/video-ai/src/video_ai/runtime/production_completed.py`；⑥ `D:/code/py/video-ai/src/video_ai/media/production_composition.py`；⑦ `D:/code/py/video-ai/src/video_ai/planning/final_review.py`。
- **First action:** 对照当前超分/合成消费者，定义 scene/clip 到最终帧贡献的接入方式及新策略正式交付所需的完整观察绑定。
- **State evidence:** 初始化为 `NOT_STARTED`；尚无新策略候选片、整片观察或交付证据。

### JIM-07

- **Goal:** 多轮选图、连续视频观察和显式返工能从确切进度恢复，只重做受到变更影响的依赖，且保留历史证据。
- **Scope:** 全流程协调、等待结果/CLI 续作、跨阶段中断点、修订运行、依赖失效和无关前缀复用；覆盖重选基准、重做画面、父片漂移、模型变更及邮件发送不明。继承各阶段已经实现的单次提交规则，不重新设计接口或延后其安全恢复要求。
- **Acceptance:** ① 在出图、TOS、邮件、选择接受、Wan、超分、合成及交付边界注入中断，续作消费原 ID/接受记录，不能重复收费或发送邮件。② 重选基准/重做父片建立新修订，受影响的图片、视频、超分、观察与候选失效，无关且身份核实的输入可复用。③ 原运行和旧接受记录不被覆盖；模型变更不能原地改已冻结 run。④ 已完成前缀重放不启动新推理或重新编码；未知提交保留诊断并等待核对。⑤ `awaiting_image_selection`、`awaiting_image_model_configuration`、`email_delivery_unknown` 和 `awaiting_continuity_review` 的恢复方式清楚且互不混淆。
- **Dependencies:** `JIM-04` 的图片依赖与选择闭环；`JIM-05` 的片段父子链及观察；`JIM-06` 的最终候选、交付和证据消费者。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 全文，重点返工、版本和恢复约束；② `D:/code/py/video-ai/src/video_ai/production.py`；③ `D:/code/py/video-ai/src/video_ai/runtime/production_state.py`；④ `D:/code/py/video-ai/src/video_ai/runtime/production_inputs.py`；⑤ `D:/code/py/video-ai/src/video_ai/runtime/production_completed.py`；⑥ `D:/code/py/video-ai/tests/integration/test_make_video_recovery_contract.py`；⑦ JIM-04 至 JIM-06 完成后登记的依赖契约及恢复证据。
- **First action:** 列出已实现各阶段的持久化提交边界，绘制变更到失效产物的依赖表，明确修订运行的只读继承与重新接受规则。
- **State evidence:** 初始化为 `NOT_STARTED`；尚无跨阶段故障注入或修订复用验证。

### JIM-08

- **Goal:** 用实际账号、邮件和连续样片确认新流程可用、画面一致性满足要求，并交付可照做的配置和使用说明。
- **Scope:** 执行替身端到端、全链路故障用例及相关旧回归；配置用户模型/参考模型、AK/SK、QQ SMTP 授权码与已有 TOS 桶；使用符合总体方案验收范围的短文案完成真实生成、邮件接收、人工选图、动态观察、整片验收和同 run 重复续作；更新 `README.md`、`config/README.md` 与示例配置。默认测试不执行真实云调用或真实发信。
- **Acceptance:** ① 各阶段定向和相关历史回归结果落盘，失败已修复，没有把未运行项登记为通过。② 用户配置的模型在实际请求中可核对，官方生成和 TOS 参考读取均有真实结果。③ 用户 QQ 邮箱收到包含基准及候选的邮件，实际选择与收到的图片一致。④ 同一主体至少三个画面、一个至少两段的连续长画面完成实际观察，未发现未解决的一致性问题；完整旁白/字幕与正式输出核对。⑤ 重复续作没有新增出图、Wan 提交、编码或重复邮件；使用说明包含等待、选图、授权码配置、模型切换和返工方式。总体方案 Acceptance 五项逐项有可定位证据。
- **Dependencies:** `JIM-07` 完成的可恢复全链路及其所消费的各阶段产物。
- **Sources:** ① 总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 的 Tests、Acceptance、Risks；② 本任务板各任务实际登记的完成和验证证据；③ `D:/code/py/video-ai/scripts/bootstrap.ps1`；④ `D:/code/py/video-ai/README.md`；⑤ `D:/code/py/video-ai/config/README.md`；⑥ `D:/code/py/video-ai/config/production.example.json`。
- **First action:** 按总体方案五项 Acceptance 制作验收检查表，将替身证据、真实服务证据及实际观看结论分开，并核实真实运行配置已齐备。
- **State evidence:** 初始化为 `NOT_STARTED`；收发地址已确认，官方及 SMTP 凭证、TOS 配置与最终测试文案尚未提供；没有真实生成、收信或一致性验收结果。

## Risks

- **一致性结果：** 参考图、固定视觉设定及尾帧续接不能保证模型每次成功。必须按整组图片、动态过程和最终连续影片分别观察；技术测试、固定种子与相似度分数均不能代替结论。
- **模型选择与能力：** 用户自行设置模型；仅支持纯文生图的模型可用于基准，关联画面需配置支持参考图的模型。未知能力不能靠名称猜测，也不能自动换模型。
- **真实服务配置：** 官方模型权限、AK/SK、QQ SMTP 授权码、已有 TOS 桶和 URL 可读取性未验证；可先用替身完成代码任务，真实验收仍必须具备相应输入。只有在具体执行时缺少必要输入，才按状态机记录实际阻塞。
- **等待与成本：** 分批基准选图、整组确认、连续视频观察和显式返工会增加等待及实际调用费用；首版不无限重试或自动重新付费提交。
- **旧路径兼容：** 当前生产链的槽位、SDXL、Comfy 请求身份及完成前缀校验关联较多；必须按新策略版本分派，不放宽旧契约来迁就新记录。
- **设计细化：** 当前是基于已确认总体方案的任务拆分，各任务尚无详细实施契约。设计时若发现需要改变已确认行为，应明确记录并向用户核实，不能以任务细化为由扩大范围。
- **范围和证据：** 本轮只更新总体设计状态并创建任务板，不登记任何实现完成、测试通过、真实邮件或图像结果；不创建普通后继交接，也不启动首个任务。
