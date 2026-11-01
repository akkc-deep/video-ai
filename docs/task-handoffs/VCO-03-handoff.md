# Pause Handoff

> **当前主任务：COMPLETED。** 2026-10-26已按用户接受的AI实验路线统一验收口径并同步任务板；无需人工补表。字面重播补充90项控制、12校准源＋3新检查源，检查TP9/FP0/TN6、周期弃权3，62项测试通过。见 [补充交付](VCO-03-temporal-replay-results.md)。本文件保留原pause和正式真人Benchmark未验收事实作为历史，不再表示当前VCO-03任务受阻。

> **后继正式交接：** [VCO-04交接文件](VCO-04-handoff.md)已整理完成，包含可复用输入、限制、设计和具体实施第一步；VCO-04为READY，尚未开始实现。本文件下方Pause是历史快照。

## Handoff Type

pause

## Task Link

- **Task board:** `docs/task-handoffs/video-continuity-optimization-task-board.md`
- **Task ID:** `VCO-03`
- **Transition:** `IN_PROGRESS -> BLOCKED`（历史pause；当前主任务已按AI路线完成，见任务板2026-10-26完成记录）

## Current State

**当前（2026-10-26状态统一）：VCO-03已COMPLETED。** 用户选择“ai校准的就可以，我不想填表格”后，AI实验及持续完成/重播补充均已交付。原先保留BLOCKED是将已不适用的主任务人审门槛继续当作当前阻塞；现已在主设计Acceptance及任务板统一修正。原正式双人Benchmark仍未验收，实验profile仍不可用于生产，未伪造相应通过。本次未开始VCO-04实现。以下“最新/BLOCKED/下一步”描述均为各日期的历史快照。

**最新（2026-10-25）：正式ROI仍20源，已构造控制200/240；新增4候选已完成颜色/原生帧及AI草稿准备，尚未正式准入。已接收akkc/qzw两表并保留AI来源与缺失观看字段，未冻结正式标签。青蛙时基和局部目标重放兼容问题已修复；本轮再修复anchor重置进入运动速度，定向108项通过，并保存独立AI背景支持复测。正式血缘/分组、ROI/标签及校准依赖仍未齐，VCO-03保持BLOCKED。优先读文末“运动边界修复与背景支持复测”，勿按旧快照重复下载或索要旧表。**

**2026-10-24 手动下载续办后的最新状态：** 2026-10-24 手动下载续办：21/21 请求文件完整解码；18 个新来源颜色 resolved，已完成 2,172 个连续原生 ready 帧。复用旧三段 312 帧后，共 21 段 / 2,484 个完整 ready 原生帧。31 个待确认项目来源共 3,593 帧播放/逐帧材料、7,186 行未签署 ROI；240 个原有 case 位置保留，实际 ROI 确认/控制/真人审阅/评估均为 0。 拟用 24 个位置已有 20 个颜色/原生帧就绪：people 4、animals 4、transport 4、outdoor 3、indoor 4、animation 1；另有一段人物备用。至少还缺 outdoor 1、animation 3，内容/独立血缘未确认还可能增加替换需求。Spring 和狗缺必要颜色声明，黄花现有解释不受支持；不得补猜 Rec.709。 新集中审阅入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-package/index.html`，逐源进度 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/followup-progress.json`，验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/followup-verification.json`，命令/退出码 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/commands-index.json`。 旧封存十源包保留；下文较早阶段记录为历史。BLOCKED和后继任务状态不变。

软件实现和本轮定向验证已交付：只读 VCO-02 reader、区域色彩/稀疏光流/六类原始分数、独立报告、十类控制变体、校准组拟合与一次留出评估工具、四个离线命令。最终五文件 101 项通过，退出 0；16 个源码/测试/脚本/pyproject 身份复核无变化。

任务整体仍为部分完成。真实 24 个独立 source、240 控制 case 的双人完整观看标注、分歧裁定及六类 ready 的 real_benchmark profile 尚无输入或结果。已询问明确 catalog/labels 路径，当前未获材料；fixture_only 测试没有替代这些验收。全库按用户要求留到 VCO-08；未推进 VCO-04，未执行模型推理或生产准入。

用户随后要求协助，已准备数据登记草稿目录 `D:/VideoSi/projects/video-ai/continuity-benchmark/preparation-a94b200fad4842de9847302838bcab81`。其中 source-intake.draft.json 有 24 个待选位置，review-queue.draft.json/.csv 有 240 条待构造/待审阅记录，preparation-status.json 明确记实际素材/构造/人工审阅/真实校准均为 0；不得当成真实 catalog/labels。待用户选择明确本地目录或有明确许可的公开视频来源后继续准备。

**后续来源选择已收到：** 用户明确说“你来寻找吧”，由我代寻公开许可素材。现有候选与实际下载状态在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/sourcing-status.json`；24 个候选按六题材各 4 个列于同目录 public-source-candidates.json/.csv。已下载 3 个动画源及保留身份，其中 Caminandes 的一帧通过 VCO-02 实际转换和只读复核；另两源流声明缺项，不补猜。24 源完整 4 秒/ROI/真值、240 控制 case 和真人观看仍未完成，不能解除总体阻塞。

## Changed Files

- `pyproject.toml`：增加固定版本 continuity 可选依赖，基础 dependencies 保持空。
- `src/video_ai/media/colorimetry.py`：复用只读校验核心，增加按需批量证据读取和退出复核，保留旧接口与 v1 输出。
- `src/video_ai/media/continuity_analysis.py`：精确 manifest、普通映射/时间/锚点验证、测量与审计报告、profile 证据消费。
- `src/video_ai/media/_continuity_schema.py`：固定 v1 参数和结构校验。
- `src/video_ai/media/_continuity_geometry.py`：确定性配准、实际浮点中心采样、颜色公式、LRU 和预算。
- `src/video_ai/media/_continuity_scores.py`：六类 score、基线/历史/累计及定域声明。
- `src/video_ai/media/_continuity_audit.py`：输入/依赖身份、exclusive 文件及 PNG 证据。
- `src/video_ai/media/_continuity_controls.py`：十类实验构造、原生/显示时间、真值掩码构造隔离和峰值预算。
- `src/video_ai/media/continuity_calibration.py`：目录/标注骨架、血缘分组、拟合、留出、比例/Wilson 指标及 profile 复核。
- `scripts/continuity_audit.py`：validate-catalog、annotation-template、calibrate、analyze 四命令。
- `tests/continuity_helpers.py`、`tests/unit/test_continuity_analysis.py`、`tests/unit/test_continuity_calibration.py`、`tests/integration/test_continuity_analysis_flow.py`、`tests/unit/test_colorimetry.py`：确定性小 fixture、拒绝/公式/几何/校准/真实 CPU 链路检查。
- `docs/task-designs/VCO-03-plan.md`、`docs/task-designs/VCO-03-verification.md`、本任务板和本交接：实施、证据、真实输入缺口与状态。

## Verification

最终命令（bootstrap 的独立命令 ID 为 8dbed14b3f6c4c00a03a67c3b554f404）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco03-release-targeted'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest','-v',
 'tests/unit/test_continuity_analysis.py','tests/unit/test_continuity_calibration.py',
 'tests/integration/test_continuity_analysis_flow.py','tests/unit/test_colorimetry.py',
 'tests/integration/test_colorimetry_flow.py',
 '-o',"cache_dir=D:/VideoSi/cache/video-ai/temp/vco03-cache-$VideoAiCommandId",
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco03-release-$VideoAiCommandId")
exit $VideoAiExitCode
```

结果：101 passed，252.66 秒，退出 0。日志 `D:/VideoSi/cache/video-ai/logs/vco03-release-targeted-8dbed14b3f6c4c00a03a67c3b554f404.log`。16/16 身份复核通过，快照 `D:/VideoSi/cache/video-ai/temp/vco03-release-source-identities.json`；git diff --check 通过。独立审查和全部 RED/GREEN/修复记录见 `docs/task-designs/VCO-03-verification.md`。

真实校准未执行；20-case 软件集成只产 fixture_only/unverified。裸全库未运行。

准备草稿独立校验：24 个 source slot、240 个唯一 case slot，六题材各 4 个、拟定校准/留出各 2 个；审阅者和实际媒体路径均为空。日志 `D:/VideoSi/cache/video-ai/logs/vco03-preparation-kit-a94b200fad4842de9847302838bcab81.log`。本次仅生成数据草稿和登记记录，没有修改代码或重跑 pytest。

## Remaining Work

历史下载协助入口（21文件现已全部完成验收）：已准备 `D:/VideoSi/projects/video-ai/continuity-benchmark/manual-downloads-20261024/download-links.html`（主清单 21、备用 7、优先五项约 30MB），同目录有 CSV/JSON 来源许可记录及预期文件名。现已完成21文件登记/解码/颜色检查；video.mp4来源对应由用户确认。当前以最新交付和manual-intake进度为准，保留旧下载失败凭据。

最新逐源材料/失败和下一动作见manual-intake/followup-progress.json与最新交付。拟用 24 个位置已有 20 个颜色/原生帧就绪：people 4、animals 4、transport 4、outdoor 3、indoor 4、animation 1；另有一段人物备用。至少还缺 outdoor 1、animation 3，内容/独立血缘未确认还可能增加替换需求。Spring 和狗缺必要颜色声明，黄花现有解释不受支持；不得补猜 Rec.709。 已完成全部当前颜色可用区间和现有源ROI草稿，第一项真人操作是完整播放并逐帧确认内容/血缘/ROI；真实truth后才构造对应控制，变体就绪后再双人观看。

按已完成设计的既定协议提供并验证真实 24-source 六题材目录、12/12 scene 分组和 240 控制 case；两人实际完整观看、逐项标注与第三人分歧裁定；冻结目录/标签后运行实际校准和一次留出评估，检查六类主 detector 的 ready profile 及覆盖率/误报/漏报。未满足时如实保留未完成，不按 variant 自动签出标签，不复用留出集调参。

2026-10-24 用户要求将剩余工作输出为清单，交由另一个任务执行。详细执行顺序、输入路径、逐项完成标准和可复制接手指令见 `docs/task-handoffs/VCO-03-remaining-checklist.md`。这是本任务的补充执行清单，不是 VCO-04 交接或状态转换。实际人工依赖不阻止先完成可独立执行的下载、颜色/区间核验和审阅材料准备。

## Resume Task

恢复 `VCO-03 — P1-A：色彩与动作连续性分析器`，目标仍是形成可复算的只读连续性报告并完成设计规定的真实校准验收。

## Start Here

最新入口：先读 `docs/task-handoffs/VCO-03-remaining-delivery.md`，再打开新集中审阅入口。新集中审阅入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-package/index.html`，逐源进度 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/followup-progress.json`，验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/followup-verification.json`，命令/退出码 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/commands-index.json`。 复用旧三段与新18段，不重做软件。辅助脚本为D:/VideoSi/cache/video-ai/temp/vco03_check_manual_downloads.py、vco03_prepare_manual_intervals.py、vco03_manual_roi_drafts.py、vco03_assemble_manual_review.py、vco03_verify_manual_followup.py，均通过bootstrap；旧sync脚本有旧计数，不用于本版本。

1. `docs/task-designs/VCO-03-design.md` 全文。
2. `docs/task-handoffs/video-continuity-optimization-task-board.md` 的 VCO-03 行和详情。
3. `docs/task-designs/VCO-03-verification.md` 与 `docs/task-designs/VCO-03-plan.md`。
4. 实际提供的 catalog.json、labels.json 及明确引用的源文件；然后阅读 `continuity_calibration.py` 和离线脚本。

5. 当前公开素材候选目录的 public-source-candidates.json、download-inspection.json、caminandes-one-frame-preparation.json、sourcing-status.json，以及原准备目录中更新后的 source-intake.draft.json。

6. `docs/task-handoffs/VCO-03-remaining-checklist.md`：逐项执行并记录证据；已交付软件不从头重做。

第一行动：取得操作者明确提供的真实 catalog.json / labels.json 绝对路径，按协议核对素材使用依据、独立 scene 分组、完整 VCO-02 ready 证据及真实双人观看/裁定记录。记录可复核的阻塞解除证据后，单独执行 BLOCKED -> READY，再按明确启动要求执行 READY -> IN_PROGRESS；不重新开始已通过的软件实施。

用户现已委托代寻素材，所以上述“取得操作者提供文件”的首步更新为：从已记录的公开许可候选清单继续完成可达文件下载、源身份/颜色/独立血缘及连续 4 秒区间核验；如原站不可达，寻找同样具有明确许可的替代来源。由工具生成 catalog/审阅材料，不要求用户手写 JSON。仍需实际观看者完成两人独立记录及必要裁定；仅在全部解除条件成立后再转 READY。

## Blocker

本节记录原正式人审协议的历史缺口。用户后选AI路线已按最新主设计完成，不再以本节要求阻塞主任务；原协议本身仍未验收，不能把任务COMPLETED解释为真人Benchmark或生产profile已通过。

- **Reason:** 设计 Acceptance 第 4 项所需的真实样本和人工观看标注尚未提供，无法运行真实校准并取得六类主 detector 的 ready profile；软件 fixture 不构成该证据。
- **Resolution condition:** 提供可访问且按既定协议完整的真实 catalog / labels 与对应素材、ROI/真值、观看和裁定证据，明确实际文件身份并通过所需输入校验。是否达到六类 ready 由后续真实评估决定，不能预先宣布。

## Risks

- 一个审查 Minor 延后：两个不同持久化记录虽可另行证明同源同帧时，无纹理比较可能保守弃权；不据此伪造 comparable。
- 标注骨架不会填写人的观看、签名或真值；必须由操作者完成实际记录。
- 字节/依赖/参数或算法变化使旧 profile 不适用，需按契约重新校准。
- `.git` 只读，未创建 worktree 或提交；保留工作区原 VCO-02 改动。自动分数/静帧不代表完整动态观看或生产通过。


用户内容反馈更新：用户表示“我认为里面的视频都没有问题”。按上一轮明确要求的20段拟用ready视频范围，已登记内容接受意见；原话、范围解释、片段身份在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/user-content-feedback.json`。没有据此补签完整播放区间、逐帧ROI、独立血缘或双人控制标签。下一步集中核对入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/roi-review.html`（20段、2,388帧/4,776行框草稿）。原封存审阅包不变，ROI确认/控制/评估计数仍为0，VCO-03保持BLOCKED。


ROI修订：用户指出熔岩灯iso_indoor_02的n=368蓝色背景框包含液滴，已在独立版本 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/roi-revisions/iso_indoor_02-background-v2` 修订背景框并检查全部120帧。主体框、原生RGB/PTS、旧封存包保持原样；仍未签署ROI。后续使用 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/roi-revisions/latest-revisions.json` 中的覆盖路径，不用旧背景框生成正式truth。更新待审入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/roi-review-v2.html`。


ROI修订：路口iso_transport_02的n=125主体框偏到相邻车辆，现已为全部120帧修订黄色车主体粗框；背景/原生证据不变，仍待逐帧确认。新版本 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/roi-revisions/iso_transport_02-subject-v2` 已并入latest-revisions.json，保留此前熔岩灯修订。待审入口更新为 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/roi-review-v3.html`。


2026-10-24 用户最新版ROI确认后的更新：用户表示“全部看完了 现在没问题了”，已按此前明确的20段最新版逐帧材料登记接受，实际作者标识conversation_user，reviewed_at使用该确认接收时间并在凭据解释；不虚构姓名、第二审阅者或控制观看。对应2,388帧/4,776行ROI已生成独立精确schema的regions/truth，使用两项最新修订覆盖路径。

已通过既有build_control_case/ControlProvider和真实VCO-02 reader构造这20源的200个控制（总240位置仍缺40），共23,880个实验显示帧，保留原生/实验两套时间、recipe、原帧身份、每帧控制RGB摘要、原尺寸padding mask及完整播放/逐帧材料。全部播放N与每帧PTS逐一核对；另对每case首/中/末帧实际重构RGB及padding，共600帧，核对PNG与原生控制缩图。未使用普通manifest冒充重播；原片/原分析记录不改。

新双人待审入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/review-package/index.html`；独立A/B空表、裁定表、240位置与200真实播放路径在该目录。两份表各2,880行，其中2,400行为已构造待观看、480行未构造不得填。尚无任何真人控制标签；variant名称不签出anomaly/normal。

验证：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/control-delivery-verification.json`，逐源verification/与sealed-case-identities/保存闭包。原两版封存审阅包合计8785文件与16/16冻结软件身份未变；未重跑pytest。审阅编码试运行曾因-r与passthrough冲突、concat微秒逐段取整漂移而拒绝，已保留失败audit；使用累计边界微秒差和原生tick末帧duration，严格复核所有PTS后才登记构造成功。校验脚本曾误比较FileIdentity的verified_at观测时间，改为既有稳定身份比较；大小/mtime/SHA仍严格核对。

总体仍BLOCKED：至少还缺1户外/3动画可用来源，独立血缘与12/12 split尚未确认/冻结；两位真人需独立完整观看原区间及真实变体并逐region/detector填标签，分歧由第三位真人裁定。另外已实际发现青蛙原片的1/1000时基有33/34步长，当前校准入口仅接收恒定步长；此兼容问题单列，不能靠改原PTS或跳过检查解决。本轮没有拟合/留出/真实profile，也不启动VCO-04。


控制审阅本轮反馈更新：用户表示“其他的没问题了”。已保留people_03的手部遮挡/钢笔色偏两项位置问题，以及20项allowed_lighting和熔岩灯两项drift的“不明显”观察；其余项目登记为未提出额外构造问题，不按variant或“没问题”自动写出normal/anomaly。汇总原话和范围解释：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/review-feedback/round-001-summary.json`。people_03两种操作的新选区已做100帧草稿，当前待用户确认：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/correction-drafts/people_03-targets-v3/index.html`；旧控制和正式truth尚未替换，须确认新区域后再重建受影响的控制。没有第二位审阅者、完整case/region/detector标签或裁定记录；当前仍不校准，BLOCKED不变。


people_03选区修订：用户指出第85帧粉色钢笔选区不准。原生放大图确认旧轮廓碰到拇指且关键帧插值未跟上写字运动；已在100帧新草稿中使用原生轮廓和逐帧笔环位置对齐，保持绿色手部框不变。第85帧拇指/纸面取样点未选中、笔杆/笔尖内部点选中；整体仍待真人确认，未重建控制或替换正式truth。最新待审页：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/correction-drafts/people_03-targets-v5/index.html`；本次反馈和检查在confirmed-roi-controls-001/review-feedback/people03-target-n85-001.json。v4失败的严格像素检查及原audit保留，没有将失败草稿提升为真值。


2026-10-25 people_03修订更新：用户回复“这次可以了”，已将最新版v5选区接受意见与版本身份独立登记（接受范围按对话解释，不补造额外原片观看、case标签或第二人）。正式手部/钢笔/背景三类区域与100帧真值已分别保存；钢笔使用已接受的原尺寸mask。

新版本 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002` 复用190个旧控制，重建people_03的10个；其中两项按用户明确目标分别选择hand遮挡、pen局部色偏。仍使用既有verified reader、build_control_case和ControlProvider，在像素生成前显式记录recipe.local_region_ids选择；未改生产源码/算法幅度。全部100帧检查色偏在钢笔mask之外像素不变、遮挡严格符合手框上半部规则；其余8类800帧原生控制RGB与旧版逐一完全相同。10类又独立重算30帧RGB/PNG/padding，播放帧数与所有原生实验PTS通过。

请从 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/people03-corrected.html` 直接查看修订的两项；完整200控制新入口是 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/index.html`。其他来源和旧版均保留，不重计成210个case。手/笔独立region后，正式ROI为4,876行，双人空表各2,940行（2,460行已构造待审，480行未构造）。没有将“其他没问题”写成normal/anomaly，实际双人标签与校准均0。

新校准兼容限制必须保留：当前校准循环默认选择所有subject区域，还不会重放这两项用户指定的目标子集。对应选择、输入和构造器适配器已存 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/calibration-target-replay-requirements.json`，正式校准前须支持并验证精确重放，不能用默认的双subject构造替代本次已审阅的两项。此前青蛙33/34毫秒步长、4个来源缺口、血缘/split、独立双人标签与裁定依赖仍在，任务保持BLOCKED，无留出或VCO-04启动。数据辅助脚本改变不影响16/16冻结实现身份，未重跑pytest。

验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/correction-delivery-verification.json`；日志/退出码见同级commands-index.json。最新进度已写回S/remaining-progress.json。


2026-10-25 修订材料接受：用户对刚交付的people_03手部遮挡/钢笔局部色偏两项新版回复“没问题”。已按实际控制文件及播放文件身份登记为作用位置/画面可接受，关闭本轮位置问题；原话在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-feedback/people03-corrected-material-acceptance.json`。此前22项弱可见性反馈与已解释的people_01现象继续保留。该意见没有扩写为case/region/detector的normal/anomaly标签，也未补造观看范围/时间、第二位真人或裁定。下一位真人独立审阅入口为 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/reviewer-b.html`，B表仍为空。本轮画面与位置反馈已汇总；正式标签、其余素材/血缘/split、时间兼容及目标选择重放仍未齐，VCO-03保持BLOCKED，无校准。


### 2026-10-25 继续任务：校准兼容修复与集中材料

用户要求“继续任务啊”。本轮复用已确认素材/ROI/200个控制，修复青蛙33/34ms原生PTS被等间隔门槛误拒、已接受的挡手/钢笔变色不能由正式校准重放的问题。catalog source可选control_targets绑定真实授权及subject ID并参与corpus SHA；profile复核也直接核对原区域身份和原生时序，拒绝修改后重新计算身份的控制时间/角色。参数、变换幅度、原媒体与已审材料保持原样。

最终五文件检查106 passed，退出0，日志 `D:/VideoSi/cache/video-ai/logs/vco03-compatibility-final-targeted-458c8400d9774061a402c853099cf89c.log`；初始5项RED及profile篡改链RED均有记录，修复后GREEN。实际20源/2,388帧原生区间核验通过；people03全部10变体/1,000帧正式构造器RGB及padding与既有材料一致。封存审阅材料/控制共39,207个唯一文件身份未变；历史16软件身份中5个按本修复改变，其余11个保持一致，新快照在本轮目录，旧快照保留。独立审查的一项Important已按RED/GREEN修复；一项Minor保留：普通profile适用域保守检查整片时步，区间外时步可能导致弃权。未运行全库、真实拟合或留出。

新增候选下载3项中途/握手超时、1项403，均留有限尝试证据；未把partial计为下载。仍缺1户外/3动画。集中入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/index.html`；补缺下载入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/manual-downloads-20261025-remaining/download-links.html`；兼容20源清单 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/final-code-verification/prepared-sources.compatible.partial.json`；验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/continuation-verification.json`；命令/退出码 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/commands-index.json`。已审位置意见不需重复确认；正式A/B逐case-region-detector独立标签仍为0，独立血缘及12/12分组未冻结，真实profile为0。VCO-03仍BLOCKED，VCO-04不启动。


2026-10-25 新下载及真人称呼更新：新增4候选实际下载到旧manual-downloads-20261024目录，本轮已完整解码/颜色resolved 3项（白桦、星空、光斑），3D工具仍为xltd临时文件。白桦和光斑各120个原生帧已就绪，共240帧；星空为稀疏暗背景，自动区间提议未通过普通非黑/纹理启发式，已保留整片联系表，尚未确认区间/稳定区域，未伪造ROI或构造控制。新增ROI确认/控制/真实标签仍为0。

用户明确“我和另一位真人判断一致”，随后提供“我叫akkc，另一个人叫qzw”；已保存真实声明与称呼，历史conversation_user对应akkc，未据此补猜逐项类别或观看时间。两份现有200控制的命名表各2460行，仅预填author；来源核对表另存一份。全部当前填写入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/review-akkc-qzw-20261025/index.html`，说明列明只填label/viewed_start/viewed_end/viewed_at/rationale，evidence_path可由导入程序绑定本表，原ROI和旧空白模板不用重填。新增材料进度 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/latest-progress.json`。未改生产源码/测试，未重跑已通过的106项；未执行真实校准或后继任务。


### 2026-10-25 已交两表与后续AI审核

用户先后报告akkc/qzw已填完，并明确“后面的视频我也都让ai审核”。已保留两份提交副本并核对2460行/200控制：结构错误均0，标签相同940、不同1520，双方viewed_at各缺2460。akkc原证据标为AI代填建议，qzw为整体未发现异常反馈转录，故不把表格差异自动记作已验证真人分歧，也不伪造观看时间、裁定或正式标签。接收/差异证据 `D:\VideoSi\projects\video-ai\continuity-benchmark\public-sourcing-725743bd99ca43f79aa47a85010ce0e7\remaining-work\manual-intake-20261024\replacement-manual-intake-20261025\received-reviews-7db6c87e6fe5\submission-verification.json`。

新增4文件全部完整解码且颜色resolved，各120原生帧共480帧，经原VCO-02 reader与_source_timing复核，完整播放N及每帧PTS全核对；新增960条AI选区草稿保持author=null/confirmed=false。AI检查首尾联系表及概览；星空/光斑未建立可靠同体/背景身份，工具黑背景缺纹理，不能据技术就绪保证正式校准适用性。24位置均有原生帧草案，但正式ROI仍20源、控制仍200/240，来源独立血缘/split仍未冻结。AI入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review.html`；验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review-verification.json`。16项软件身份未变，未重跑既有106项测试；未拟合、未跑留出、未启动VCO-04，任务仍BLOCKED。


### 2026-10-25 原始诊断样例交付

用户同意继续完成带分数、定位和不可比原因的诊断报告。本轮只使用原计划校准侧people_02的10种已有控制，另补people_01的原样/运动重播/相机跳变3种，未改样本归组、未读取留出侧结果、未读取判断表参与计算。现有build_control_case/ColorAnalysisReader/measure_continuity实际计算13个控制、1,560显示帧（各另含1固定参考）、3,107完整比较，输出11,704条分数记录。每次命令<=300秒，校准/阈值拟合入口已在数据脚本中禁止。

为保留16MiB单文件上限，原始比较逐pair分块落盘，未删比较/降采样/修改参数。3,107块身份复核、39块指标摘要独立重算通过；16个软件文件身份保持。原样人物02背景仅覆盖全图3格，119时间比较均无相机支持；人物01原样40/119时间比较具备相机支持，保留其它弃权，不把无分数当正常。六类分数已有可核对的对照，但无异常阈值、无准确率/真人验收通过。

HTML含并排原样/变体、区域与比较类型选择、同来源同项目一致纵轴、曲线点/峰值显示时间定位及算法轨迹框；Markdown、CSV、SVG可独立查看。浏览器两次无头交互检查受本机图形/权限及超时限制未完成，未宣称通过；JS语法和本地资源另验。入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/index.html`；摘要 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/README.md`；证据 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/evidence-verification.json`；来源和命令 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/diagnostic-provenance.json`、`D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/commands-and-browser-status.json`。本轮为数据/报告，未改生产源码或重跑已有106项定向测试，未拟合、未跑留出、未启动VCO-04。VCO-03正式验收仍未完成，状态保持BLOCKED。


### 2026-10-25 背景覆盖改进试验

用户询问下一步后，继续对已定位的背景支持不足做独立AI输入试验：保留people_02原主体/背景，增补右侧沙发候选，仅提供clip起点/参考锚点；原样、重播、跳变各120帧重算。360控制RGB与旧材料一致，717比较中原两个区域1,434项色彩测量/可比性完全相同，16项软件身份未改。新支持数量和运动/相机分数见 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/README.md`，验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/experiment-verification.json`。

v1数据脚本因共享region_ids列表的重复追加触发资源保护，失败状态保留；v2按比较独立复制列表并验证无重复后成功，未放宽资源或算法阈值。新增框仍为AI候选，不替代正式ROI/真值，不改变原200控制或13个独特诊断case计数（共16次输入版本测量），不拟合/读留出/读标签。入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/index.html`；正式VCO-03仍未完成。


### 2026-10-25 运动边界修复与背景支持复测（最新）

用户要求“继续处理吧”。`continuity_analysis.py` 当前帧对速度改由已通过匹配的左→右仿射作用于左框中心计算，clip起点anchor仍用于选区及后续跟踪，避免anchor重置进入运动速度。两项真实纹理回归先RED（静止误测0.64、平移误测-0.1102），修复后26项分析器单元检查GREEN。独立AI代码审查无Critical/Important问题，未冒充真人视频审阅。

同一people02校准侧、相同右侧AI背景输入复测：原样第60/61帧75.9977/77.7987降至1.1613/1.7490；重播48.6539/50.8001，实际图像变化仍保留。代码前后717比较/三区域2,151项匹配与颜色结果完全相同。原窗口背景跳变时仅10个点通过筛选、原右沙发仅2个，不降低12点门槛。

独立AI背景输入试验改用宽窗户与顶部植物/遮篷；从clip起点传播并使用相同匹配器，两区域跳变对最终13向量覆盖全图4格，C中119/119时间比较可估计相机。新增两个背景区域第60帧camera_jump均5852.9661，峰值第60帧；原样同帧3.5604。原背景本身该帧仍跟踪失败、分数为空，不能写成原区域已恢复。新区域是基于静态概览及有限支持探查调整的AI草稿，并非正式ROI或独立验证集；顶部植物独立运动及跨片背景身份仍待正式核验。原两区域1,434项颜色测量/可比性保持一致。

五个指定测试文件合计108 passed。首次合跑325.54秒超出300秒单命令预算，记录保留且不登记预算合规；随后按文件分成五次270秒硬超时的检查，各批结果/实际时长见commands-and-checks.json。未执行全库；未改匹配参数/阈值、源片、原200控制、正式ROI或判断表。16项软件身份中仅分析器和本单元测试改变，旧快照/旧依赖指纹保留；新测量在独立audit，旧profile不得复用。本轮新增6次测量，原始诊断累计22次、独特case仍13。

入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/motion-registration-fix-20261025/index.html`；说明 `.../README.md`；数值 `.../before-after.csv`；完整测量证据 `.../experiment-verification.json`；命令 `.../commands-and-checks.json`；新软件身份 `.../software-identities.json`；最终交付核查 `.../delivery-final-check.json`。这些省略号均指前述同一目录。

下一步仍以正式准入、独立血缘/12+12分组、可追溯标签和真实校准依赖为准；本轮只证实该校准侧样例的代码修复和测量支持，不宣称整体准确率通过。用户当前无需重复下载、观看或填表。VCO-03保持BLOCKED，VCO-04保持NOT_STARTED。


### 2026-10-25 校准输入依赖审计与40个待构造计划（最新）

用户要求继续任务。本轮只读复用24候选/2,868原生帧，四批各6源经既有ColorAnalysisReader、_source_timing和原始血缘提取核验，最长36.52秒，退出0；20源正式regions/truth通过schema及全帧覆盖检查，4源保持unsigned AI草稿。来源/作者/许可均已补入新24源CSV，包括原空表漏填的Caminandes/青蛙。已选24源未发现已验证媒体原始血缘跨源/跨split冲突，未据此宣称独立性已证实；原12+12位置分配与每题材2+2保持，未冻结。

全部200已有控制recipe及display_map长度与兼容20源输入一致。新副本显式复用兼容清单中的people03 control_targets（hand遮挡、pen改色）；原jobs仍指向无此字段的旧source.json，故新的重放绑定直接指向本批sources-20，避免再走默认全主体。旧源、控制和视频不覆盖。

新增4源的40个待构造计划已绑定实际120原生帧身份、官方_recipe、显示/原生双时间和clip边界；未调用构造器/测量器、未生成RGB或新ControlCase，实际控制仍200。20源部分catalog经过纯结构校验，但缺24源/独立血缘/冻结/正式标签，不能直接运行真实校准。软件16项身份保持，沿用108项定向通过记录，未重复pytest。

统一当前说明 `docs/task-handoffs/VCO-03-calibration-input-status.md`；入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/index.html`；全部证据、40计划、200重放绑定和来源CSV均在同目录，最终核验delivery-final-check.json。三类真实缺口集中为新增区域/真值、独立血缘与分组、正式审阅记录；保留AI来源，不伪造标签/时间/独立性，不要求重复下载或重填整套旧表。无拟合/留出/VCO-04，VCO-03状态保持BLOCKED。


### 2026-10-25 用户选择AI实验校准并完成（当前交付路线）

用户明确“ai校准的就可以，我不想填表格”，授权独立AI实验路线；设计 `docs/task-designs/VCO-03-AI-experiment.md`。已冻结24来源/12+12分组及2,940条AI弱标签，原表、真人ROI和正式benchmark协议分别保留；AI-only annotation没有冒充真人。当前不需要用户填写表格，旧人工依赖不阻塞本AI路线。

240控制位置均有结果：230完整测量、10固定metadata资源弃权；54,730完整比较、27,710含参考实验帧请求。120校准case结果齐备后只拟合一次，封存阈值身份后才算120检查case。4项有实验阈值：seam4.85805、local8.41253、drift8.41262、camera8.97361；累计/动作缺有效正常类，保持null。相机检查端到端召回28.6%，不隐去弱项。标签940 normal/133 anomaly/120 not_comparable/1747 unverified，新增4源480项全部unverified；不按recipe补造正负，不使用qzw整体normal转录作独立标签。

临时数据脚本初期一次reader超时和JSON格式膨胀拒绝均保留；紧凑分块不放宽16MiB/64MiB资源门槛。两帧缓存32次原生像素/掩码一致性通过；按码值LUT加速构造与原provider的5源/6变体/120帧原生像素/掩码逐字节相同，已有20源的后续快路径逐帧对照原控制RGB摘要。生产算法16项身份保持，不重跑已有108项软件检查。

独立AI代码审查提出“失败producer不能借新receipt获认证”和“检查侧须绑定封存阈值身份”两项Important；4项预期RED→5项GREEN（含有效receipt正例），原source失败产物隔离，合法续算保持原producer/输入摘要/依赖/闭包绑定。10资源失败仅从其原已闭合失败receipt派生空分数与弃权，不补造完整比较。

统一交付 `docs/task-handoffs/VCO-03-AI-calibration-results.md`；报告/实验profile/评估/CSV/冻结输入/最终核验均在 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025`。experimental-profile始终production_eligible=false，普通profile校验实际拒绝，没有启动VCO-04。原正式benchmark状态单独保留；本AI实验路线已完成，后续不再索要人工表。
