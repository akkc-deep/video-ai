# VCO-06 后继准备输入核对

日期：2026-10-27。本文件是输入核对历史，**不是实施设计或next-task交接**。初次核对时Design document/Handoff均None、状态NOT_STARTED；随后用户批准路线并完成下述校准，已完成/关联 `docs/task-designs/VCO-06-design.md` 和 `docs/task-handoffs/VCO-06-handoff.md`，任务板准备为READY，产品实现未开始。

## 选择依据

VCO-05完成登记之后，按任务板预定义Order选择更大且未完成的最小Order，得到Order6的VCO-06。观察状态NOT_STARTED；没有跳过它自动选择VCO-07，也没有开始VCO-06实现、校色或GPU任务。

## 已确认输入

- 任务板：`docs/task-handoffs/video-continuity-optimization-task-board.md` 的VCO-06目标、范围、验收与Sources。要求“修复幅度与适用门槛须由已校准样本及专项设计确定”，默认关闭、不可比/重大结构动作异常拒修，原片与接受记录保留。
- 总体方案：`docs/task-handoffs/video-continuity-optimization-proposal.md` 第7节同样要求先有匹配稳定区域、受限且时间平滑的修复依据，不允许全幅强制匹配或逐帧独立重调。
- VCO-03交付：`docs/task-handoffs/VCO-03-AI-final-results.md`；实际profile为 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/experimental-profile.json`。完整顶层字段只包含实验身份、检测器、几何输入/评估和限制等；production_eligible=false，无repair/exposure/white_balance/gain/smoothing/cap字段。
- 上述色彩阈值衡量检测分数，不能换算为可允许的曝光EV、RGB/白平衡增益、色度变换或每帧时间平滑上限。AI实验可为离线研发提供数据，不能据其直接签发普通生产修复profile。
- VCO-04：`docs/task-designs/VCO-04-operations.md`、`VCO-04-verification.md`，已提供媒体/算法/报告身份、epoch、观察与显式风险回应、局部重算和恢复守卫；没有制定安全校色幅度。
- 当前修订规划 `src/video_ai/planning/scene_revision.py` 支持reconfigure/reselect_images/regenerate_images/regenerate_clips，没有已冻结的校色候选采纳kind。后续详细设计需明确新增候选与修订接口，不能悄悄替换已接受父片。

只读核对日志：`D:/VideoSi/cache/video-ai/logs/vco06-dependency-audit-a3815dcd689f4a86bd9659fd4cc6c4c1.log`。

## 首个材料缺口

已交付的直接依赖未提供校色专用适用门槛和幅度上限的校准证据。现在直接给出EV、白平衡增益、色度或平滑常数，会把设计者猜测伪装成实测范围；无法满足任务板要求的实施设计准备条件。

推荐延续已有AI偏好，在VCO-06内先以既有素材/控制做离线修复专用校准，再依冻结结果确定修复上限与适用域；无需新增模型推理或人工填表。这是新增校准工作的范围安排，不把现有检测阈值改名为修复上限。替代路线是由用户明确暂缓校色，调整顺序到VCO-07整段模式设计；不得自动跳序或启用模式。

用户随后明确回复“同意，按这条路线走”，已授权先完成离线AI修复校准，再据结果完成VCO-06详细设计与后继准备。协议及计划分别为 `docs/task-designs/VCO-06-calibration-design.md`、`docs/task-designs/VCO-06-calibration-plan.md`。不再等待该选择，不新增人工填表或模型生成。

2026-10-27正式冻结前22项测试通过；首次根 `AI-repair-calibration-20261027` 的首源因五/四字段身份适配缺陷被末尾核验拒绝。独立复核494个身份的path/bytes/SHA/mtime全部未变。保留原失败现场，补RED→GREEN及真实漂移拒绝回归，23项通过后在 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2` 重新冻结，原网格/门槛/拆分不变。完整命令与判定随计划账本保留。待真实结果形成后才决定实施域，不把准备校准记成VCO-06生产功能完成。

最终r2的24来源/2868帧/1776控制闭包全部通过，12源calibration→seal→12源holdout→evaluation时序核验正确；仅4/10方向条件合格，82项弃权保留。最终结果/身份/命令见 `docs/task-handoffs/VCO-06-calibration-results.md`。详细设计使用独立干净选图配对，默认关闭、研究候选独立及显式修订、生产导入拒绝；不能将本实验当自然视频修复或实际完整观看通过。后继准备已解决最初幅度依据缺口，原历史缺口不再代表仍在等待用户选择。
