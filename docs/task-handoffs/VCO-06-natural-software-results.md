# VCO-06 自然研究软件交付

2026-10-30收尾（本轮自10-29续作）。软件流程已补齐，194项最终定向检查及规定六文件178项兼容检查均通过，实际16段保留／拒修及原件身份复核完成。**真实自然资格及校色改善仍未通过，VCO-06保持BLOCKED。**

## 已实现

- 新 `vco06_natural_study.py` 支持check-inputs/freeze/measure/seal/evaluate/finalize/status：完整真实来源、原作者观察、预登记group/split、holdout盲态和跨study占用、不可变事务、失败分母、严格中点、一次holdout及闭包profile loader。
- 新 `natural_color_repair.py` 支持assess/propose/review/status：当前研究上下文和安全Precheck、新旧两个合格profile、明确已知轴、原r2方向/幅度上限、单参数全片修复、完整native16主候选/观看副本、实际RGB回读≤2及无新增裁切、固定支持指标和前后普通报告。
- 新loader从原RGB重新构造普通geometry/轨迹/detector，再重放数值与控制；不靠刷新JSON/SHA宣布通过，不执行归档代码。
- status只读；原始Request/观察字节保留；部分现场不自动重渲染；最多3个同源attempt；历史非颜色失败、failed观察和所有实际风险回应均保持绑定。稳定原片可noop，未知资格/已知缺陷保留或拒修。
- 历史采集/pilot、旧audit/估计器及旧r2模块/文件保持字节；新consumer另建版本化入口。无普通生产资格、采纳或发布。

操作合同及完整字段见 [操作说明](../task-designs/VCO-06-natural-software-operations.md)，设计与取舍见 [补齐设计](../task-designs/VCO-06-natural-software-design.md)，实施账本见 [计划Ledger](../superpowers/plans/2026-10-29-vco06-natural-software.md)。

## 当前最终软件检查

16个明确指定的定向测试文件，**194 passed，597.45秒，exit0，无skip**：

`D:/VideoSi/cache/video-ai/logs/vco06-natural-closeout-targeted-c232204151954eba8e2836274fa1912c.log`

覆盖新engine/study/profile/candidate/实际CPU媒体、观察/恢复，以及既有自然特征/统计、旧r2闭包、正式研究来源/分片报告和生产拒绝。CPU素材确为16fps、完整逐帧probe/decode；源/资格/作者测试provider显式隔离，构造观察不算真人或自然改善。

一次独立只读审查发现8项Important、0项Critical，已在同一修补轮闭合并经RED/GREEN回归验证；见 [审查及处置](../task-designs/VCO-06-natural-software-review.md)。额外回归保证改变JSON键顺序不能重复回应同一risk、遗漏另一非颜色风险；合法负的修复退化上限不会使未改变的稳定原片错误拒绝，非零修复仍使用原封存负值。

更早169/189/192项及63/21项专项存在重叠，保留日志作过程证据，不与194项相加。完整全库依原约定留VCO-08，本轮没有运行裸pytest。

精确六文件兼容检查，**178 passed，5690.52秒，exit0，无skip**：

`D:/VideoSi/cache/video-ai/logs/vco06-natural-six-compat-b662f8816515421d9367c2975ea2f3d0.log`

文件为 `test_scene_clip_records.py`、`test_scene_clip_observations.py`、`test_scene_revision.py`、`test_scene_revision_flow.py`、`test_scene_pipeline_recovery.py`、`test_scene_continuity_recovery.py`，按计划串行执行。该178项与194项文件范围互不重叠；没有启动全库或新增模型推理。

## 实际16段材料

首轮实际软件复核：

`D:/VideoSi/projects/video-ai/vco06-natural-qualification/software-audits/20261029-existing16-c6f36d83165a49c28e21046277f499f0/delivery.json`

SHA256 `7c9a7be5ae7b9c4af7e8705bdf57350107c5c0279971192866ba749226a560df`。16段各49帧，技术来源/原生时序/全部像素重新核验；4段按明确非颜色失败拒修，12段保留未知校色适用性；原件6824个文件bytes/SHA/mtime完全不变，零拟合、零候选编码、零新增模型请求。

`awaiting_observation`在这里表示颜色目标/已知轴或原记录语义尚不满足校色资格，**不表示用户没有看完视频，也不要求重新观看16段**。原作者“只是看到了变化”的光照澄清、47/48个真实回调及完整played范围保留在前次接收记录；原文件不改成新的正例。

最终修补后，用原下载与全部已登记观察身份重跑16段assess，结果仍为4段拒修、12段保留未知适用性；16×49原生帧全部重新验证，0个已确认已知轴正例、0次拟合/候选编码/新模型请求。新的独立交付：

`D:/VideoSi/projects/video-ai/vco06-natural-qualification/software-audits/20261029-existing16-7c3b470462224447a52a0aca62f69d44/delivery.json`

SHA256 `8b90348efb6029be13402dac165b5c81937fe0f28caf87b11da8926f4f309721`。**6838个原文件bytes/SHA/mtime不变**；较首轮多14个登记原文副本，原件范围扩充并未覆盖旧审计。日志 `vco06-natural-final-actual16-001e1ea8691a45a8be82cb80349e5644.log`，exit0；每个原文件、归档观察、case处置、软件库存及实际producer均有绑定。

这16个研究import当前没有自己的普通assessment/pair manifest；本轮没有编造ROI、未来SHA或正式资格Request，也没有让已见development改名进入新holdout。

## 收尾复核

同一新根的 `closeout.json`，SHA256 `66d44584be30782257322de423d75fdd5153b503d2574f37be4266578bba1ca9`，绑定本轮最终194/178日志、实际16段交付、6838原件及原pilot前54项历史基线、10个产品/CLI和10个测试/辅助文件身份。产品SHA与最终194测试中的独立software.FROZEN库存逐项一致，源/测试mtime早于该次测试启动；两个新CLI的实际help导入检查通过。日志 `vco06-natural-final-closeout-87ae899ffa2e42e3b2fe7a5c5c58443d.log`，exit0。

旧交接、任务板和主设计改写前原字节保存在新根 `entry-document-archives/`；当前只更新同任务证据，Design/Handoff引用及状态不迁移。`git --no-optional-locks diff --check`退出0，只有既有LF/CRLF提示，未转换文件；无Git写入、提交、发布或后继准备。本轮测试与实际审计均已结束，无遗留本轮后台任务。

## 真实验收状态

当前仍为0个经确认的已知轴轻微自然偏色正例，没有合格自然profile、真实修复候选或完整原片/候选改善通过。观察已完成、代码补齐、控制/CPU夹具通过和保留原片都不能替代这一结果。原24次采集及4次pilot均已停止，不自动追加生成或新的观看任务，不准备VCO-07。

正式资格需要真实适用来源和规定的独立分组/标签覆盖，再由实现好的阶段工具生成阈值/一次holdout/实际观察闭包。任何未知、失败、区间不分离或超预算均保留并返回unqualified/refused；最大规模成功未被宣称。
