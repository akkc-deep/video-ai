# VCO-06 自然研究软件操作

本入口只做离线研究，始终不授予生产资格。真实资格与改善验收另记；当前16段仍无已确认的已知轴正例，不需要重新观看，也不追加生成。现有材料处置结果见 `docs/task-handoffs/VCO-06-natural-software-results.md`。

## 环境和入口

所有命令在仓库根执行。每次Python调用先执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-natural-operation'
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/experiments/vco06_natural_study.py','status','--root',$StudyRoot)
exit $VideoAiExitCode
```

`$StudyRoot`必须是实际 `D:/VideoSi/projects/video-ai/vco06-natural-qualification/studies/<规范UUID>`。例中的变量均指真实文件，不是可以填写未来SHA的占位输入。

研究命令为 `scripts/experiments/vco06_natural_study.py` 的 `check-inputs / freeze / measure / seal / evaluate / finalize / status`。候选命令为 `scripts/natural_color_repair.py` 的 `assess / propose / review / status`。历史 `vco06_natural_qualification.py audit` 和旧 `scene_color_repair.py` 保持原版本。

## 研究输入与阶段

研究Request精确字段为 `schema_version,study_id,config,conditional_profile,seen,cases,requested_at,reason`。Artifact精确使用实际 `{path,bytes,sha256}`。config为实际配置，conditional_profile为原r2的 `experimental-repair-profile.json`，还会验证其完整闭包。seen为 `schema_version,video_sha256,reference_sha256`，两个数组须去重排序，包含已见开发材料和已暴露历史holdout。

每case字段为 `case_id,scene_group,group_basis,domain,split,material,manifest,observations`。material引用真正研究commit；manifest包含原选图及全部原生帧、原ROI和完整普通比较；observations引用原作者提交。family/split须与原生成登记一致，domain与manifest.genre一致；不能把同图不同seed拆成独立组，不能用人工控制补自然正例。

`check-inputs --request ABS`只读检查，允许报告不足24段的准备度。正式 `freeze --request ABS [--root ABS]`要求development/holdout分别至少12段、4组且来源完整；冻结protocol、输入、软件、原r2闭包及receipt。新holdout在此登记跨study占用，换UUID不能复用试过的盲测来源/参考。未知/不足不生成假资格。

`measure --root ABS`只处理development；每case先写intent，独立普通报告、固定9×9特征及实际RGB8控制分别保存。合法轻微偏色正例才允许按旧r2上限做校准dry transform和独立qualification preview；它们不进入runtime候选账本。所有失败和未知都留在登记分母。

`seal --root ABS`重放development结果，并按严格区间中点计算五阈值或unqualified。`evaluate --root ABS`只能引用已独立封存的seal，一次处理holdout；所有development方向均未分离时记录 `skipped_no_qualified_direction`，不打开holdout自然标签/像素。已完成同身份结果只核验，部分case拒绝自动重测；现场和锁归属不明时不得删除或接管。

`finalize --root ABS [--observations ABS]`核验完整闭包。观察索引精确为 `schema_version,evaluation,cases`，evaluation引用本研究一次evaluation，cases引用实际完整观看原片/qualification playback的观察。观察schema及逐项检查见下节，与预览媒体/报告/完整范围绑定。阈值技术通过不能替代该观察。

至少一个方向和共同domain同时有技术及真实观察证据才写 `natural-repair-profile.json`。其loader再次核验原源、标签、原r2、冻结软件、实际像素/控制、严格中点和一次holdout；不执行归档代码。qualified_domains使用每个合格方向共同覆盖域的交集，避免隐含扩大方向/domain组合。

finalize是不可变结论；缺失/失败时写unqualified，不用修改原观察或封存阈值来重试。可先用status查看阶段；需要真实观察的研究应在观察齐备后finalize。当前材料不满足研究正例前提，没有提交新观察任务。

## 候选与观察

`assess --run-dir ABS [--observations ABS ...] [--natural-profile ABS]`只读返回当前实际原片处置，不拟合、不编码。未知轴/未解决观察保持 `awaiting_observation`；这里表示校色适用性尚未确认，不否认原作者已完整观看。明确结构/动作失败为 `abstained`；明确无需修正可保留原片，均不算校色改善。

`propose --request ABS`的Request精确字段为：

```text
schema_version,run_id,candidate_id,policy,material,epoch,assessment,
pair_manifest,conditional_profile,natural_profile,precheck,
operation,operator_basis,revision_of,requested_at,reason
```

policy固定 `research_candidate_natural_v1`。来源必须为真实无父链研究导入，epoch/assessment为当前值，pair_manifest须与当前研究assessment及原选图/全帧绑定。natural_profile为已通过独立闭包验证的新profile，缺失时不估计。operation只由作者明确选择exposure/wb_r/wb_g，不能遍历挑优、换轴或夹幅。

Precheck精确字段：

```text
schema_version,source_kind,run_id,material,epoch,assessment,source,
pair_manifest,observations,review_method,reviewer,viewed_at,
playback_ranges,color_issue,operation,correction_direction,operator_basis,
target_reference_confirmed,subject_structure_intact,motion_intact,
intentional_lighting_change,responses
```

source_kind固定 `research_wan_material_v1`；完整原片实际播放、目标/结构/动作true、预期变光false，已知轴/方向与原作者观察一致。原已登记观察及普通风险全部回应；历史非颜色失败和未解决项不能由新颜色通过清除。

每次从原片估计一个全片参数。实际master用固定sRGB/YUV444 CRF0，另生成BT.709/YUV420标准观看副本；完整probe/decode验证native16/F帧/PTS/尾帧、意图RGB回读≤2码值、全幅无新增裁切和固定支持自然指标，再保存独立before/after普通报告。RGB→YUV有整数转换，不能称RGB逐字节无损。generic composition只记录研究clip ID和原生本地PTS，不伪造生产generated/retained/output索引。

事务位于原研究run的 `research/natural-color-repair/<candidate_id>/`，独立UUID登记防止改请求复用；最多3次同源attempt，包括等待、失败、中断。新修订必须引用实际terminal或尚无terminal的intent；所有现场保留，同UUID不重新渲染。status只读核验。

`review --run-dir ABS --candidate-id UUID --observation ABS`只消费真实观察；格式：

```text
schema_version,kind,candidate_id,source,candidate,playback,
before_report,after_report,review_method,reviewer,viewed_at,
playback_ranges,start_observation,process_observation,end_observation,
quality_observation,checks,responses,issues,verdict
```

kind固定 `natural_repair_visual_review_v1`。实际播放范围精确覆盖原片和playback各自完整 `[0,F)`、fps `16/1`；candidate绑定master用于技术身份，不冒称播放了master。checks完整包括主体、结构、颜色改善、材质、动作、镜头、无新频闪和原生时序；风险按实际before/after报告逐项回应。四段原文、作者和时区时间必须真实。

全部passed才 `research_candidate_reviewed`，failed永久保留，unverified只保存原字节而无通过receipt。该状态仍不授予生产资格，不采纳、不发布、不启动后续生成。真实观看不能用测试fixture或静帧代替。

## 限制

每项源/控制操作最长300秒；native帧≤4096、RGB单帧≤32MiB、像素工作预算128MiB；单JSON≤16MiB、特征窗口≤64MiB、累计元数据≤256MiB。超预算完整拒绝，不能缩帧、换尺寸、删失败或更新旧SHA。profile完整重放可能耗时较长；软件验证不宣称最大规模已成功，也不把控制或构造的CPU素材计为自然正例。
