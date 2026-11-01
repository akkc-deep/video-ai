# VCO-06 自然校色软件闭环补齐

2026-10-29。用户明确要求继续完成自然校色软件流程，停止追加试采。承接主设计及natural-input修订设计，不改变真实改善验收、不将16段未知/无偏色/非颜色缺陷改为正例。本文只补齐已批准路线的工程合同；执行方法为当前会话直接实施和一次最终独立审查。

## Goal

实现可执行的输入检查/冻结、development测量、严格间隔中点封存、一次holdout、profile生成/验证，以及独立自然候选的propose/review/status。现有真实材料能够实际返回原片保留/拒修/等待资格；有完整合格证据时正路径可执行。软件测试中的构造数据只验证软件，不算真实自然改善。

## Scope

只新增版本化模块与CLI。旧natural_color_repair.py、natural_repair_statistics.py、research_material_baseline.py、全部原采集/pilot冻结软件、旧r2与旧CLI保持字节，不刷新其SHA。新实现使用同一natural_constant_color_repair_v1公式、9×9特征和旧r2额外幅度上限；不扩大方向、不改普通几何、媒体、生产拒绝规则。新CLI `vco06_natural_study.py`，旧audit入口继续保留。

无模型/GPU请求、依赖安装、发布、Git写入或新的观看任务；全库仍留VCO-08。所有原件与旧观察保留。

## Approach

### 接口与输入

Study request精确字段：schema_version,study_id,config,conditional_profile,seen,cases,requested_at,reason。study_id规范UUID，config/conditional_profile/seen为Artifact。case精确为case_id,scene_group,group_basis,domain,split,material,manifest,observations；material为真实research/material/commit.json Artifact，manifest为原生全帧独立参考配对manifest，observations为原作者提交Artifact数组。split为development/holdout；同参考或同视频不能跨group/split，同family的group_basis需要在输入准备时如实声明，代码不能独立证明语义独立性。seen记录已暴露的视频/参考SHA，holdout不允许借用；holdout观察在seal前只核对字节身份，不解码标签、像素或自然指标。

正式freeze要求每split≥12且≥4组、完整真实来源和非占位文件、已记录观察身份；实际语义/方向覆盖在development和sealed holdout各自阶段检查。readiness/assess允许不足24的真实开发输入，返回不足及保留原片，不伪造正式freeze。引用source commit必须与当前真实研究context一致；所有帧和原选图来自正式context，配对manifest不得删帧或借坐标。

seen精确为schema_version,video_sha256,reference_sha256；列表去重排序。source family/group为输入作者有依据的登记，不根据阈值结果重分组。实际16段仅开发/历史检查，不能进入新holdout。

### 事务与阶段

新study根位于自然研究根/studies/<study_id>，独占写入锁覆盖每次阶段动作，不能接管未知锁。protocol.FROZEN.json、inputs.FROZEN.json、software.FROZEN.json及freeze-receipt先于任何测量。写入为exclusive临时文件、fsync、无覆盖rename；已完成的同输入阶段只核验，部分计算保留并明确拒绝自动重算。每case操作≤300秒、单JSON≤16MiB、窗口≤64MiB、去重JSON总量≤256MiB，阶段索引只保存Artifact，各case独立有界执行。

measure只处理development，按每case生成自己的普通几何分片报告、全帧9×9原始特征、预登记控制和固定支持前后指标。未知/失败保留为结果，不删分母。seal重新从已绑定development结果计算五个严格间隔中点，不接受手写阈值。evaluate必须引用独立seal身份，只执行一次holdout；若无任何合格development方向，记录skipped_no_qualified_direction并不打开holdout自然数据。finalize在完整阶段闭包核验后才产生既定schema的natural-repair-profile.json；无合格方向输出unqualified并无profile。

固定控制：identity、各可用轴±0.01/±0.02、对应量化逆变换、同符号错误方向、-3a过修、exposure+0.02/wb_r+0.02混轴、wb_r时间正弦0.02、固定中心矩形局部wb_r+0.02、exposure+2裁切、中心矩形右移16像素。它们是独立副本上的离线数值证据，不能计作自然正例。可用于当前数据的软件拒绝检查，不要求构造样本变成视觉通过。

**实现澄清：** 资格计算需要自然正例的前后改善量。只有已冻结研究中的、作者明确轴/方向且语义安全的development案例可做校准专用dry transform：在内存/独立控制证据中按原r2上限估计一个参数、实际RGB8量化后重新测量，不编码runtime候选、不发ready。此离线计算是阈值研究，不能作为自然改善观察。runtime仍必须先有合格闭包profile才拟合/编码；旧等待分支原字节不变。

估计仍为≤16384全序列确定性informative项的逐通道median(log2 ratio)向指定d投影，不自动选轴、不夹幅；每帧≥81支持。b/o、等权B、最大退化/正交残差/时间增加完全复用已固定定义；前后坐标、角色、点数必须一致。中性noop使用max(abs(b_before))；缺例、缺4组、区间不严格分离、任何实际拒绝/未知均不制造合格方向。

### Profile与自然候选

补充裁定：资格协议要求实际原片/改善预览完整观看，故已获作者明确轴和安全语义的冻结案例在dry transform之后可另存CPU编码的qualification preview，仍不进入runtime候选账本。实际预览编码/回读和固定支持数值一并复核；独立原作者观察索引可在一次holdout计算之后交给finalize，绑定evaluation身份及每段原片/标准预览/报告。缺观察或失败即unqualified，不允许更改已封存阈值或重新测量。测试中的预览/观察fixture不计真实自然资格。

profile精确沿用主设计字段及purpose；闭包包含原r2及其原封存库存、study freeze/软件/所有development结果/seal/evaluation、实际来源和观察。加载器只读核验阶段路径/时间/身份、重新归约阈值与方向，当前软件漂移拒绝新拟合；不执行归档代码。手写精简profile、篡改seal、只改计数/方向或丢弃失败记录均拒绝。

新入口 `natural_color_repair.py propose/review/status/assess`；Request沿用主设计的material/epoch/assessment/pair_manifest/两个profile/Precheck/operation/basis/revision_of字段。仅正式研究source、当前epoch/ordinary assessment、原图与完整帧、明确安全Precheck和有效profile可进入拟合。assess可不带profile，明确返回原片保留/拒修/等待，不把unknown称noop。历史明确结构/动作失败永久阻断；所有原观察需有回应，不能用新的颜色通过覆盖。

独立 `research/natural-color-repair/` 事务保存原Request、intent、fit、master、标准观看副本、原生映射、全幅无新增裁切、实际编码解码≤2码值及解码后的固定配对新指标、before/after普通报告、完整review原文与receipt。保持一个全片参数、原生16fps/F帧、末帧、新UUID与同族3次上限；partial输出不自动重渲染，status只读。VCO-02的通用变换媒体分析使用composition阶段元数据，明确标为research candidate，不制造Wan/production retained映射。

Review绑定真实source/master/playback/报告，完整观看、结构/材质/动作/镜头/频闪/时序和颜色改善均明确passed才research_candidate_reviewed。failed永久保留，unknown只留原文；不授予production_ready/eligible。当前16段没有此正例，必须返回真实保留/拒绝/等待。

## Files

- media/natural_repair_engine.py：纯已知轴参数与数值判定；保留旧等待函数。
- runtime/natural_study_records.py、natural_study_measure.py、natural_study.py：严格输入/事务/控制测量及阶段机。
- runtime/natural_repair_profile.py：闭包profile只读验证。
- runtime/natural_candidate_records.py、natural_candidate_media.py、production_natural_repair.py：独立候选绑定/原生媒体/事务、恢复和观察。
- scripts/experiments/vco06_natural_study.py、scripts/natural_color_repair.py：显式本地CLI。
- 对应unit及真实CPU integration测试、实际16段结果和完整交付文档。

## Tests

每项RED→GREEN，串行，通过bootstrap/Invoke-VideoAiNative。新数值/阶段/loader/候选测试先定向，再相关既有研究/生产拒绝与规定六文件兼容检查；全库不运行。fixture只作软件证明，至少一次真实CPU编码/完整回读/拒绝/恢复链路。

预期：未知/非颜色问题保留原片且零编码/请求；合法软件fixture正路径可经历freeze→measure→seal→evaluate→profile→propose→review，任何漂移/失序/缺帧/错媒体/错方向/预算/中断/伪造profile/未来时间/跨组/holdout泄露均拒绝。实际16段运行只生成可复核的拒修/保留报告，不生成真实自然profile或候选。

## Acceptance

- [x] 所有阶段、自然profile loader和候选/观察/恢复/只读status有真实可调用实现，非仅等待stub。
- [x] 无profile/已知失败/不适用真实样本准确保留/拒修；零新增模型请求，未知不升级。
- [x] 通过针对性软件正负路径和真实CPU媒体/恢复测试；旧兼容及原件身份有证据。
- [x] 软件交付与真实自然资格/改善验收分开；后者缺失时VCO-06仍未完成，不准备后继。

2026-10-30收尾证据：[软件交付](../task-handoffs/VCO-06-natural-software-results.md)。最终194项定向、178项规定兼容均exit0；实际16段保留／拒修，6838原件及原pilot前54项基线保持bytes/SHA/mtime。以上只完成本补齐设计的软件验收，不代替主任务的真实自然改善Acceptance。

## Risks

真实素材仍不足以封存合格自然profile；软件可实现但不能制造实证。离线dry transform是必要的资格测量，不是实际改善验收。group_basis与视觉标签依赖实际作者/预登记依据，无法仅靠文件名证明独立性；加载器拒绝已知交叉与漂移，不宣称自动理解全部语义。旧输入/软件已冻结，任何需要改动既有文件的实现必须改用新模块/版本，不能刷新旧SHA。
