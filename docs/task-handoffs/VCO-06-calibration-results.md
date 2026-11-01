# VCO-06 离线AI修复校准结果

2026-10-27按用户“同意，按这条路线走”完成既有材料上的条件数值校准及一次检查。**仅4/10个算子方向在封存域内通过；production_eligible=false。** 不表示自然视频已修好、实际播放通过或VCO-06已经实施完成。

## 协议与覆盖

- 协议/计划：`docs/task-designs/VCO-06-calibration-design.md`、`VCO-06-calibration-plan.md`。
- 有效根：`D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2`；原24来源12 calibration/12 holdout、六题材和scene_group不改，全部2868原生帧记录覆盖，共1776控制，24/24来源完成末尾输入闭包核验。source计算累计343.439秒，不含准备/封存/收尾。
- baseline eligible为calibration 11/12、holdout12/12，均覆盖六题材。`iso_animation_tools`有完整120帧/每帧1024取样点，但三通道均在[2,253]的informative pairs=0，全部74项弃权，没有按控制结果事后剔除。
- 总计1625个measured、69个显式context_rejected、82个abstained；1093项满足相应控制要求。82弃权包含上述74项和eligible来源`iso_indoor_02`在强控制下8次informative支持不足；后者仍在对应档位分母中，不能用失去支持扩大上限。
- identity在23个eligible源均noop；合理光照、不可比、确认动作缺陷三个逻辑门槛各23/24次确实拒修，另1次未执行。它们测试显式上下文守卫，不是语义AI检测准确率。

每源完整取样点数、原生PTS/时间基、ROI来源/限制、控制recipe、拟合值、逐帧RGB/Lab/裁切/时间误差保存在source-packs/source-results；不生成新的模型视频，也没有改写原素材、旧标签或既有生产run。

## 封存与一次检查

下表方向为**修复参数a的方向**；注入方向相反。前缀上限L是控制注入强度，A是校准中最大实际估计修复幅度，二者均为log2单位，不能混用。holdout要求全部预先eligible源、封存档位内全部控制同时满足误差/裁切、修复方向及abs(a)≤A；没有据检查结果调整任何上限。

| 算子 | 修复方向 | 注入前缀L | 修复幅度A | 检查通过/域内控制数 | 资格 |
|---|---:|---:|---:|---:|---|
| exposure | + | 0.25 | 0.250628489331295 | 57/60 | 不合格 |
| exposure | − | 0.015625 | 0.01918276884903868 | 12/12 | 条件合格 |
| wb_r | + | 0.0625 | 0.06549871699634681 | 34/36 | 不合格 |
| wb_r | − | 0.015625 | 0.018851552816108768 | 12/12 | 条件合格 |
| wb_g | + | 0.03125 | 0.036521558455209775 | 24/24 | 条件合格 |
| wb_g | − | 0.03125 | 0.03628187114179243 | 24/24 | 条件合格 |
| wb_b | + | 0.03125 | 0.0341663968267182 | 22/24 | 不合格 |
| wb_b | − | 0.03125 | 0.03404457636254319 | 22/24 | 不合格 |
| chroma | + | null | null | 未取得校准域 | 不合格 |
| chroma | − | null | null | 未取得校准域 | 不合格 |

曝光正向失败包括`iso_people_03`在L=.25估计a=.2513222339486388超sealed A；`iso_animation_stars`在L=.0625/.125最大误差5/9，尽管p99为0/.77仍被最大4码值规则拒绝。红轴正向在transport04估计幅度越界且p99=3，并在stars出现稀疏5码值误差。蓝轴两方向各有commons_144217105及transport03估计幅度越界；即使重建误差小也未扩大域。色度在校准集最小档即未全通过，没有继续声称更大档位偶然通过可用。

这些是**已知同像素对应、已知算子族与轴、全片恒定偏移**的构造实验。工程误差预算为每帧p99≤2、任何取样通道max≤4、无增加新裁切；不是人眼阈值、自然光照意图或通用修复安全上限。网格之间的连续参数域没有独立自然样本覆盖，不能以4/10当作40%视频修复成功率。

## 不可变产物

以下文件均相对有效根，SHA为文件原始字节：

| 产物 | bytes | SHA256 |
|---|---:|---|
| protocol.FROZEN.json | 1391 | 65cea982c8a1afa7d41f59e404aa0f546bc3707436343409af6020cf2d00c22d |
| inputs.FROZEN.json | 1238507 | c42cd465d5a83c696aeee32db678a5da3892b5bf7c1eced8d94eb4ac3d5497b7 |
| thresholds.SEALED.json | 12299 | fa7bfac9f892f4836cf60ea8b67745a02a3d3790b58577ba0a06404889b6fe8e |
| evaluation.json | 53135 | f954a24e81c87a8d2294c1878a1fc6639f597ca38027c49165fae0241b4169aa |
| experimental-repair-profile.json | 59376 | d0423aa2012f80fe590798242014a46c1af210fbfcfb3a7163f776bbf46b158f |

`closeout-verification.json`记录24源、2868帧、1776项、逐方向资格/失败、身份及累计时间。收尾实际重新检查phase guard、两split全来源闭包、source/result独立身份、evaluation/profile/inputs/seal引用，并复算fit_bounds/evaluate与保存值逐字段一致。只是复核保存测量，不重新读取holdout拟合或改变阈值。

## 软件验证及失败现场

校准器 `scripts/experiments/vco06_repair_calibration.py`，定向测试 `tests/unit/test_vco06_repair_calibration.py`。首轮RED、阶段GREEN及fresh-context审查见计划账本；正式冻结前22 passed，实际输入暴露五字段reader身份与四字段实验身份全字典比较问题。首源74项后闭包拒绝，原失败根完整保留，未封存/未访问holdout。

诊断证明494个文件的path/bytes/SHA/mtime均未变。新增reader身份适配回归RED（1 failed/22 passed）→GREEN（23 passed），同时检查真实字节漂移仍拒绝。未改变算子、网格、评分/支持门槛、拆分；用r2新根重新冻结，原失败根不覆盖。

所有命令先bootstrap并Initialize-VideoAiEnvironment，Python3.12、NumPy2.2.6、OpenCV4.12；以下日志均在 `D:/VideoSi/cache/video-ai/logs/`，各阶段退出0，明确RED除外：

- 正式前测试/prepare：`vco06-freeze-a18f1d81cece4cc0bb85efaa443fd522.log`，22 passed。
- 首次失败测量：`vco06-calibration-run-7501bd5b0f64469783b2972f877ceae1.log`，exit2，原现场保留。
- 身份RED：`vco06-reader-identity-red-776029fe79c545b9872c94e7bc5c19ce.log`，exit1。
- 身份GREEN/r2 prepare/12源测量：`vco06-reader-identity-green-0ef6ca01e8ca44fe851503930ed052c1.log`，23 passed，12源completed。
- 原现场身份复核：`vco06-identity-audit-0d4276acb64a450481c84a474c2707e5.log`，494 unchanged/0 changed。
- 封存：`vco06-seal-fc695b9f6e1942afb8476fd014dde7e5.log`。
- 12 holdout源一次测量/finalize：`vco06-holdout-run-870d2c8c34174a58852b08e086adddc3.log`。
- 最终闭包与复算：`vco06-closeout-verification-12f1af07532b4eb5b1f7c12ffb198469.log`。
- 报表数据核对：`vco06-report-data-0717ac13ba6c4c22940c5af363748d00.log`。
- 阶段顺序核验：`vco06-phase-order-verification-be186bddd99443de85ecf5e8cfb40135.log`，12 calibration全部早于seal、12 holdout全部晚于seal且早于evaluation；保存phase-order-verification.json。
- 最终定向检查：`vco06-final-check-680a607c9d2f4772a1f5c9e231c1afc8.log`，23 passed/exit0，software/顶层证据不变、board/design/handoff一致；git diff --check退出0，仅既有换行提示。

精确CLI为 `prepare --root ROOT`；`measure --root ROOT --source-id ID` 按原index中calibration来源逐个串行；`seal --root ROOT`；按原index中holdout来源逐个串行measure；最后 `finalize --root ROOT`。失败/弃权不覆盖、不选择性重新测量。全库按用户要求仍留VCO-08。

## 给VCO-06的输入

本实验提供条件数值包络与不可用方向；不提供现实自然配准校准、自动光照意图判别或普通生产修复profile。后继设计为 `docs/task-designs/VCO-06-design.md`，默认关闭、研究候选独立保存、不合格方向拒绝、实际完整播放仍是独立验收。此文件不是next-task handoff，不自行改变任务状态。

原24源及AI split曾用于前期实验，不是新盲测，也不保证scene_group统计独立。原生素材不是16fps，本次没有改帧率；未来16fps实际候选必须另做技术/观察验收。没有新下载、模型POST、GPU推理、生产启用或发布；VCO-05保持COMPLETED。
