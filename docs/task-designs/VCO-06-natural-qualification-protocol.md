# VCO-06 独立自然校色资格协议

日期：2026-10-28。承接 [已批准的自然输入修订设计](VCO-06-natural-input-design.md) 第4–7节；执行账本为 [qualification continuation plan](../superpowers/plans/2026-10-28-vco06-qualification-continuation.md)。

## 当前状态

本文件固定研究定义、阶段和拒绝条件。**完整研究输入尚未冻结，没有 thresholds.SEALED.json、独立 holdout evaluation 或自然资格 profile。** 当前新增的 audit 命令只复核现有开发材料、实际重放像素特征并计算诊断统计，不执行 freeze/measure/seal/evaluate/finalize，也不生成候选。

复用输入：`D:/VideoSi/projects/video-ai/vco06-usable-input/20261028-141129-0710d61477d0/delivery.json`，纸质素材49帧及原选图。该视频已用于开发、失败分析和用户查看，只能记入已见开发材料；不是新的盲测样本，不是已确认自然偏色正例。用户“没有看到有明显问题，我分辨不出来”保留原文，不能转换成完整观看、normal、anomaly、已知轴或改善标签。

## 1. 研究问题和不变条件

研究9×9 linearRGB邻域中位数能否区分真实整体色偏、正常重建差异及必须拒修的局部/结构/时间变化。旧原图残差预算不改；新指标是否适用由新的独立资格实验决定。

- 全部原生16fps帧、准确PTS和映射、明确sRGB处理链，无音轨贡献媒体。
- unchanged ordinary 配准/ROI传播；包括首帧，每帧完整可比，至少81个去重有效配对，不删不利帧/区域。
- 整片单一恒定参数，从原片开始，已知族/轴由实际作者选择。现阶段无资格时不估计自然修复参数或编码候选。
- 方向只可能是旧r2已合格的 exposure负、wb_r负、wb_g正/负；实际幅度不超过相应旧封存上限。旧r2及其失败不重写。
- 整帧无新增裁切、参数时间变化=0；后续编码解码相对意图RGB最大2码值不改。
- 无新依赖、无生产资格、无发布、无全库回归、无 .git 写入。

## 2. 数据、分组与标签

正式 inputs 必须包含 development 和新的 holdout：各至少12个完整自然视频、各至少4个 scene_group，组在split之间不重叠。同原图、同素材家族或同场景不同seed归同组，不能把帧、裁片或人工污染当独立视频/组。

每个希望取得资格的方向，在每个split都须至少4个真实自然案例，跨4个组。12个视频的最低规模不保证四个方向都取得覆盖；不足的方向保持unqualified，不能为补分母拆分同源片。qualified_domains仅为两split实际共同覆盖的域。

旧24来源、旧holdout、织物/纸质开发段和本轮已经查看/测量的材料列入 `development_seen` 排除表，不能转成新盲测。现有纸质段可以用于工程重放与后续开发负例分析，但不得冒充新独立来源或自然正例。

自然标签至少包括：媒体/参考身份、真实来源和组依据、完整播放范围、作者/时区时间、实际观察文字、是否合理变光、结构/运动是否完整、是否为中性/明确轻微色偏/不安全/不可比、已知operation/方向依据及无法确认项。使用独立研究来源schema，不伪造生产schema2观察。无实际播放能力的AI可提供技术统计，视觉标签为unverified；不要求用户重新填双人校准表或识别其无法分辨的细微色偏。

自然改善正例还需完整真实原片/候选播放，确认改善且无材质、运动、镜头、频闪或时序退化。当前的源视频查看反馈不能提前提供这一结论。缺观察不进入已通过正例数，也不从登记分母删除。

## 3. 测量定义

对每帧i、每角色r、每个固定有效点p：

1. 参考和当前图分别取完整9×9邻域，均位于实际图像与预声明ROI交集内；不足项在拟合前按固定规则排除并计数。
2. sRGB按标准分段函数转linearRGB，再逐通道取中位数。informative代码值范围[2,253]；不得用未来候选挑点。
3. 保存 `q=log2(median_linear_reference/median_linear_current)`。每角色/帧确定性最多1024项；估计时全序列最多16384 informative项，所有帧参与评分。
4. 曝光d=[1,1,1]；指定白平衡通道1、其余−0.5。`s=dot(q,d)/dot(d,d)`。
5. `b[i,r]=median_p(s)`；`o[i,r]=p90_p(norm(q-s*d))`，norm为三通道L2，p90使用NumPy线性分位数规则。

帧和角色等权，不按每行采样点数量加权：

```text
B = mean_(i,r)(abs(b[i,r]))
improvement = B_before - B_after
frame_regression = max_(i,r)(abs(b_after)-abs(b_before))
off_axis = max_(i,r)(o_before,o_after)
temporal_increase = max_(i>0,r)(
    abs(b_after[i,r]-b_after[i-1,r])
    - abs(b_before[i,r]-b_before[i-1,r]))
```

单帧temporal_increase=0。负的regression/increase保留，不截为0。前后frame、role、点数量与坐标必须逐项相同；角色消失、错序、删点或不完整支持拒绝比较。单位为linearRGB比值的log2。原始RGB p99/max和原因继续保留，不能仅展示平滑后的统计。

当前代码 `media/natural_repair_statistics.py` 只实现上述b/o和固定支持前后比较，不拟合a、不选择轴、不创建阈值或资格。审计对exposure/wb_r/wb_g三种投影分别记诊断，其中wb_g的同一统计覆盖两个可能符号；这不是逐轴试修或选择最佳算子。

## 4. 控制证据与自然证据分账

控制在预登记原片的字节独立副本上构造，包括 identity、单轴恒定偏移、已知逆变换、错误方向/过量修改、混合轴、时间变化、局部改色、裁切及纹理/结构变化。所有实际recipe的operation、方向、幅度、作用范围、时间函数、量化规则和完整来源须在正式测量前随protocol冻结，不能事后挑控制参数得到分离。

当前尚无完整来源清单及正式控制recipe清单；因此这里只固定必须覆盖的种类，不声称控制已构造/测量或正式protocol已封存。不得从本轮纸质数据的统计量倒推出让它通过的recipe或阈值。

人工注入及已知逆变换只证明数值/拒绝行为，不计为自然正例、自然改善或真实视频观察。单元测试中的数值三元组、人工邻域和fixture同样不计入研究样本数。

## 5. 阶段、输入身份和封存

1. **研究定义/采集计划**：固定公式、完整目标清单、来源/家族/组、split、已有暴露排除表、拟研究方向、控制recipe、采集请求预算、实际观察协议、软件/依赖身份。
2. **完整输入冻结**：取得真实来源后生成不可变 `protocol.FROZEN.json`、`inputs.FROZEN.json`、software库存和真实标签索引。检查split/组不重叠、方向覆盖和观测来源。未来文件SHA或视频不能用占位值假装已冻结。若先采集新材料，采集计划在生成前冻结；输入清单在资格测量前冻结。未知模型结果只恢复原prompt，不补单。
3. **development测量**：仅消费development；所有完整帧、失败、资源拒绝、弃权和未知标签保留。已见材料的探索性结果单独标识，不包装为预注册新实验。
4. **threshold seal**：按下一节中点规则得到值或明确unqualified，并封存阈值/完整development结果；不读取holdout测量来调参。
5. **一次holdout**：只在seal身份已冻结后执行一次完整检查；拒绝旧曝光样本、跨组、缺项、漂移或改seal。失败不删除、不重试调参。同请求恢复只能复用同身份已完成结果。
6. **finalize/profile**：完整检查阶段顺序、input/producer/software/结果闭包、来源分母和实际观察；至少一个方向通过才可由正式生成器产生合格新profile。缺数据/标签/分离时无资格，不写手工profile开启消费者。

此处列出的是后续完整研究的产物合同，**当前CLI仅有 audit**，没有把未实现的阶段命令写成已存在功能。

## 6. 阈值与取得资格

五个字段在未满足证据前全部为null：

- noop_bias_ceiling
- minimum_bias_improvement
- maximum_frame_bias_regression
- maximum_off_axis_residual
- maximum_temporal_bias_increase

取值规则沿用批准设计：中性例最大初始bias与自然正例最小初始bias的中点为noop边界；中性例可能最大改善与自然正例最小改善的中点为最低改善；其余三项取全部正例相应最大值与预登记对应有害控制最小值的中点。必须存在严格间隔；重叠、缺例、语义未知或方向覆盖不足即unqualified。

非零候选必须严格改善且满足最低改善，逐帧退化、正交轴和时间增加分别不超上限，并通过硬保护；noop要求max(abs(b_before))≤noop边界。holdout要求中性例全部noop，不安全/合理变光/不可比例全部拒修，对应方向全部有效自然正例技术与实际观察通过。缺观察、失败、资源拒绝或弃权不得从分母中移除。

新profile字段/固定algorithm/purpose及旧r2引用闭包按主修订设计执行。旧r2只提供额外方向/幅度硬上限，不提供新自然阈值。没有合格方向是合法研究结果，但不能据此生成自然修复候选或完成VCO-06。

## 7. 当前可执行的复核

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-natural-qualification-audit'
Invoke-VideoAiNative $VideoAiPython @('-B',
 'scripts/experiments/vco06_natural_qualification.py','audit',
 '--delivery','D:/VideoSi/projects/video-ai/vco06-usable-input/20261028-141129-0710d61477d0/delivery.json',
 '--output',$NewUniqueAuditPath)
exit $VideoAiExitCode
```

输出必须位于独立 `D:/VideoSi/projects/video-ai/vco06-natural-qualification/` 下新路径，拒绝覆盖或写回输入。命令通过正式研究context重核源事务/像素/全帧报告，再从原图/完整帧和已冻结普通配对坐标重放特征，按原producer序列化逐字节核对旧baseline；修改baseline再刷新交付SHA也不能成为合法重放。

预期结果为 `awaiting_qualification`、退出3，包含全部49帧诊断、空qualified_directions、null阈值和缺项，不产生修复媒体。拒绝/漂移/损坏退出2，中断130。重放失败要保留原原因，不刷新旧SHA或覆盖旧baseline“修复”记录。

## 8. 当前真正缺少的输入

已交付包只提供1个已见开发来源；0个经过有效实际观察确认的自然偏色正例，0个新holdout案例，已知operation/轴Precheck缺失。

因此现有包足够执行来源、完整配对、原像素重放和上述诊断开发；不足以进行正式阈值校准/封存、独立holdout、真实候选或改善验收。下一阶段需要完整独立数据/recipe/实际观察来源，不能把“复用输入包”解释为复制同一素材充足样本数，也不能要求用户勉强确认其看不出的偏色。
