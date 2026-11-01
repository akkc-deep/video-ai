# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `docs/task-handoffs/video-continuity-optimization-task-board.md`
- **Completed task:** `VCO-03`，当前状态 `COMPLETED`，按用户已接受的AI实验路线验收。
- **Next task:** `VCO-04`，Order 4，是已完成VCO-03之后预定义顺序中最小的未完成任务。
- **Design document:** `docs/task-designs/VCO-04-design.md`，已完成并关联任务板，已作一次独立可实施性检查，问题已补齐。
- **Expected next status:** `READY`。先写本交接，再关联任务板Handoff，最后执行 `NOT_STARTED -> READY`；不代表实现已经开始。

## Next Task

**VCO-04：P1-B，诊断接入观察门槛与版本化恢复。**

目标是把VCO-03的真实连续性证据接入片段观察、后代生成及媒体/发布检查，使诊断缺失、漂移、失败或当前回应未完成时不能沿用旧推进资格。

实施范围按已完成设计：仅为显式启用的新scene run增加`scene_continuity.policy=advisory_v1`、独立诊断epoch/assessment/review记录、原始来源闭包核验、本地analysis/reassess操作及现有生产入口守卫。旧run沿原冻结options、graph、请求、完整视频观察和媒体恢复契约运行。

可观察验收：

1. 策略精确冻结，缺省旧run的请求/记录保持兼容，不能通过当前config或目录存在而自动启用。
2. 诊断绑定准确保留帧/完整父片前缀、原生时间与映射、起点ROI/context、算法/包身份和独立audit来源；完整闭包缺项/漂移拒绝，机器弃权保持原值。
3. 机器结果、完整动态观察、当前推进资格分别记账；实际`human_video`或具备真实完整播放能力的`agent_video`及当前全部风险回应共同成立才允许ready。三段及以上须有同作者全prefix播放证据。
4. 诊断重评和恢复不会重新POST模型或生成原片；保留原视频、超分、成片、PCM/字幕及历史观察。已确认缺陷不能靠换epoch或同源继承消失。
5. 已生成后代/已有complete或composition/delivery的快捷路径与底层直接调用也校验当前资格；原技术历史读取不能被当前重评等待误判为非法。
6. 设计指定两组定向测试及故障恢复/零外部作用检查实际通过，结果写入实施验证文档。全库仍留在VCO-08，不预造播放能力、准确率或生产profile通过。

本交接仅准备下一任务，不授权本轮执行实现、真实GPU/付费推理、模型服务、发布或重复素材校准。

## Dependencies

### VCO-03：分析接口与ordinary报告

- **Artifact:** `src/video_ai/media/continuity_analysis.py`、`src/video_ai/media/_continuity_schema.py`、`src/video_ai/media/_continuity_audit.py`；接口与精确格式见 `docs/task-designs/VCO-03-design.md` 第3、6、8节及当前Acceptance，验证记录见 `docs/task-designs/VCO-03-verification.md`。
- **Decision:** 复用`analyze_continuity(manifest, *, config, paths, logger, timeout=300)`，只接受已验证的ordinary输入，写新的非production audit；raw结果不具生产passed资格。VCO-04新增只读报告验证器，不另造检测算法。
- **Rationale:** 已有分析器提供六类分数、可比性、原生/全局时间和完整来源证据；runtime负责接入及恢复，不应重做算法或伪造分数。
- **Constraint:** sRGB输入准入、起点anchor/未来truth隔离、4096帧/65536比较、16MiB单JSON/64MiB元数据及原始身份规则保持。无profile/弱匹配/unknown颜色保持unverified或不可比；不更改源片、PTS、16fps生产映射或普通profile验证条件。
- **Usage:** 在独立attempt调用分析器，将其准确报告、原媒体/映射/分析帧及依赖闭包绑定到当前assessment；经新的readonly verifier核验后才交给动态观察回应。
- **Readiness evidence:** 软件接口与相关定向验证已交付，任务板VCO-03最新完成记录按AI路线验收。原软件和AI成果可复用；VCO-04的runtime模块及新增报告validator尚未实现，必须在本任务按设计新增，不能误认已有这些接口。

### VCO-03：AI实验结果与适用限制

- **Artifact:** `docs/task-handoffs/VCO-03-AI-final-results.md`、`docs/task-handoffs/VCO-03-temporal-replay-results.md`；原六项研究profile为 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/experimental-profile.json`；重播证据根为 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026`，其 `delivery-final-check.json`、`readonly-final-verification.json`、`evaluation.json`、`final-review.md` 是对应交付/核验入口。
- **Decision:** 用户已接受AI校准并不要求人填表，VCO-03主任务为COMPLETED。原双人正式Benchmark未验收、实验profile不具生产资格作为限制保留；它们不再使主任务显示BLOCKED。
- **Rationale:** 当前交付完成了预定实验、一次检查、真实覆盖/弃权及可追溯审阅；完成研究交付与宣称六项生产阈值可靠是不同事实。
- **Constraint:** 四项色彩和两项几何采用不同分析域/算法，重播补充识别字面录制片段重播；不能合并分母、把变体当独立来源、将编码Y阈值套入ordinary sRGB分数或改字段伪装real_benchmark。原始实验/标签/阈值/检查不覆盖、不重测调参。
- **Usage:** 作为能力说明、适用范围和限制引用；当前生产clip诊断可用`profile=null`的ordinary报告，不能把固定控制case的实验分数直接挂到别的媒体上。
- **Readiness evidence:** 原几何15源/90项控制与一次18项新检查已交付；后续重播补充12校准源＋3此前未测来源、90项结果，记录62项定向测试通过、90原始receipt及6252个显示ROI帧摘要核验。其新检查TP9/FP0/TN6/FN0、周期负例弃权3，覆盖15/18；只支持所述研究范围。以上为已有验证结果，本次交接未重跑测试/实验。

上述直接输入没有未解决的使用冲突：VCO-04采用ordinary证据接入和实际动态观察，研究profile仅作说明。原真人Benchmark缺口不是本任务软件实施的先决条件，也不允许因此放宽当前生产观察门槛。

## Start Here

按以下顺序读取：

1. `docs/task-designs/VCO-04-design.md`全文：以其精确schema、代次链、历史技术读取/当前资格拆分、风险回应和验收为实施契约，不再重新设计接口。
2. `docs/task-handoffs/video-continuity-optimization-task-board.md`的VCO-04行/详情及VCO-03当前完成记录；状态以任务板为准。
3. `docs/task-designs/VCO-03-design.md`当前Acceptance及普通分析/报告格式，随后阅读上面两份结果文档的适用限制。
4. `src/video_ai/runtime/scene_clip_observations.py`、`scene_clip_records.py`、`production_scene_clips.py`：原schema2观察、父片准入和不可变complete。
5. `src/video_ai/runtime/production_scene_pipeline.py`、`scene_media_records.py`、`scene_completed.py`、`production_scene_delivery.py`：已有完成前缀、guard及发布入口。
6. `src/video_ai/runtime/scene_revision_records.py`、`_scene_revision_origins.py`、`_scene_revision_readers.py`与 `tests/integration/test_scene_pipeline_recovery.py`、`test_scene_revision_flow.py`：历史继承和未知请求恢复。

**实施第一步：** 在用户明确启动VCO-04并按任务板执行`READY -> IN_PROGRESS`后，新增 `tests/unit/test_scene_continuity_records.py` 的首个RED用例：显式启用策略的新run即使已有合法schema2视频accepted观察，当前assessment缺失或属于旧epoch时，`require_scene_continuity_acceptance()`仍拒绝推进，且模型提交计数为0。复用现有prepared-pipeline fixture，先观察这一行为测试失败，再实现相应策略/epoch/只读资格校验；随后按设计完成剩余接口和定向检查。不要先运行真实pipeline或补采素材。

实施文件路径及完整测试命令已在设计Files/Tests中给出；所有Python经 `scripts/bootstrap.ps1`、`Initialize-VideoAiEnvironment`、`Invoke-VideoAiNative`，运行产物和缓存位于D:/VideoSi。实施时创建 `docs/task-designs/VCO-04-verification.md`记录真实结果；当前没有VCO-04软件测试通过记录。

## Risks

- 当前未证明本环境具备完整动态播放能力；没有真实能力时，保留等待状态，不把静帧AI或数值冒充agent_video。
- 旧accepted父片已有后代、immutable complete及已完成媒体前缀与新诊断overlay必须分离；只在CLI或publish检查会留下绕过路径。
- 未确认Review只存raw、后续可补齐，终态才写唯一receipt；确认缺陷跨epoch/同源继承仍生效。不能因新代次丢掉更晚失败证据。
- 算法/包升级后的历史证据需按设计读取绑定归档，不能执行归档代码，也不能用旧安装身份发放当前ready。
- 显式输入缺分析帧/起点ROI/context时等待，不猜主体/色彩、不截短前缀，不重新要求VCO-03双人校准表。
- `.git`只读且工作区有多轮未提交成果；不reset/revert、批量暂存或清理旧任务文件。本交接不新增后端/模型或任何真实推理授权。
