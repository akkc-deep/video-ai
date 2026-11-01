# VCO-06 离线修复参数校准

## Goal

用户2026-10-27选择“先补离线AI校色校准，再做VCO-06”。复用既有24来源，测定已知配对像素条件下的保守修复数值范围；不把VCO-03检测阈值当作修复幅度。本阶段交付实验校准及之后的VCO-06实施设计，不实施生产校色或启动新生成。

## Scope

只读 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025/experiment-inputs.FROZEN.json` 中24个source，沿用12 calibration/12 holdout及scene_group；六题材各4源不换组。原生帧记录全部检查，不补帧/裁短时间。处理已有ready的srgb_rgb24_v1 RGB及其原生PTS/时间基，未知/漂移输入拒绝。独立证据根 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027`；原样本、标签、既有控制、封存阈值及生产run均不写回。

这是AI指导、可复现数值控制实验。原图为构造真值，不制造真人/新VLM标注，不声称独立盲评或实际视频观看。本实验仅校准**已证实对应、已知算子族与白平衡轴**下的修复算子；算子族/轴同样是条件信息，不宣称验证了自动选模。它不证明现实场景的像素配准、语义身份或合理光照判别。实际修复必须另外满足VCO-03可比性及VCO-04观察/风险回应。profile永久production_eligible=false。

## Approach

### 取样、身份与拆分

逐source使用VCO-02已保存RGB记录及其sidecar解析宽高、明确sRGB、原生PTS。校验记录/sidecar/pixels/source/regions/truth的bytes/SHA/mtime及完整序列；保存所有输入身份，前后复核。RGB处理最多驻留一张原生图；每帧在主体/背景各以确定性均匀格点至多1024像素采样，只用truth中visibility=visible的当帧ROI，partial/occluded不直接配对，已有mask须验证并应用。无可用ROI/少于81有效配对样本时弃权，保留来源和原因。baseline eligibility在任何控制拟合前固定：每帧至少81对采样，且全序列至少81对RGB三通道都在[2,253]的拟合样本；控制阶段失去支持不能把该来源移出分母。采样用于算子校准，不冒充全分辨率成片验证；不改变或省略原生时间戳。

控制真值与拟合输入分离：算子只接收参考/候选RGB对和明确上下文，不接收注入参数；注入recipe仅由评分器计算可复核结果。此处对应坐标来自可控构造，标注为oracle correspondence，不能证明未来实际配准有效。

### 算子与扫描

在明确sRGB下先解码linear RGB。v1限制为两种互斥算子：①每通道正对角增益，稳健估计各通道log2(reference/current)中位数，向预先声明的曝光方向[1,1,1]或三个白平衡轴投影成单一幅度；白平衡轴归一化零均值，max绝对分量=1。不得合成未测的多轴或曝光+白平衡组合。②以linear Rec.709亮度为轴的单一色度缩放，最小二乘估计标量，保持亮度，不做任意色相旋转/全3×3混色。条件不足或模型残差过大时拒绝，不用另一模型掩盖重大差异。每算子全片拟合至多确定性均匀抽取16384对，评分逐帧覆盖全部取样点，避免跨片浮点数组堆积。

预先声明扫描幅度 `[1/64,1/32,1/16,1/8,1/4,1/2,1]` log2单位，均为**工程搜索网格，不是已证明安全的数值**。曝光两符号；白平衡方向为RGB三个轴减去自身通道均值、两符号；色度两符号。每源共70个非零静态控制，另identity及三个门槛负例（explicit allowed lighting、not comparable、confirmed motion defect），共74项。白平衡方向归一化使max绝对分量等于幅度。不能根据结果改网格或更换来源。

每控制对全序列估计**一组恒定参数**，应用全片不逐帧独立重调；这是v1的时间平滑策略（参数时间变化严格为0），不会引入参数跳动。时间变化漂移/独立逐帧白平衡、任意色相、局部区域选择性改色不在本次可启用范围；在后续设计中明确拒绝而非伪造对应上限。原图的正常运动/光照随时间变化保留，不冻结背景。

运算冻结：sRGB标准分段解码/编码（0.04045、12.92、0.0031308、2.4）；linear增益为 `x * 2**(a*d)`，曝光d=[1,1,1]，白平衡d为上述归一化轴；色度为 `Y + 2**a*(x-Y)`，Y=x·[0.2126,0.7152,0.0722]，Y广播三通道。每次注入和修复均在linear域变换、clip[0,1]后编码，最后np.rint到uint8；不能量化前提前裁成sRGB整数。增益只对reference/current均位于[2,253]的三通道有效对取log2，避免零值；色度分母≤1e-12时弃权。注入a与理想修复a为相反数；结果同时记录injection_level与estimated_correction_amplitude，profile注明符号关系，不能混用。未知上下文、明确合理光照、不可比或动作缺陷先拒修；恒等字节输入返回noop。

### 冻结验收规则与上限拟合

工程重建要求预先固定为：每个已测帧的p99(max通道RGB误差)≤2个8-bit码值、**任一采样点任一通道误差≤4码值**，候选新增裁切率不高于未修控制（容差0）；新增裁切定义为参考通道码值位于[3,252]而结果变为0或255，参考自身的边界/量化邻域不算新损伤。即使稀疏重大损伤不足1%，也会被4码值最大误差拒绝。残差超上述预算的估计不构成可用候选。identity必须noop，三个显式负例必须拒修。2/4码值是本实验的量化误差预算，不是来自真人的通用可感知阈值。记录MAE、p99、最大误差、ΔE76诊断、裁切和时间误差差分；不以平均改善遮蔽坏帧。

按operation与注入正/负方向分别选择从最小网格开始**连续通过前缀**的最大幅度，并显式映射为相反方向的修复参数域；中途失败后更大的偶然通过不能扩大上限。每档必须所有预先baseline-eligible的calibration来源均通过，且至少6个来源/scene_group、覆盖全部六题材；不能只挑6个成功来源。控制时失去支持算该档失败，不动态移除来源。覆盖不足时对应上限null并写原因。只使用calibration结果。白平衡各轴分别保留，禁止合成未经验证的多轴组合；曝光和白平衡联合作用也不自动通过。非可比/输入无效/资源弃权必须单独计数，不当作通过或阴性。

先写 `thresholds.SEALED.json` 并封存身份，之后才处理原holdout来源。一次检查应用封存规则，报告逐源/题材覆盖率、上限内通过/失败/弃权；不回调网格、误差预算、参数或阈值。每方向检查要求所有预先eligible的holdout来源在上限内全部通过，且至少6源/组与全部六题材；覆盖不足记insufficient而非通过，任一失败则qualification=false。保留拟合上限和失败数据，不将失败后禁用算子宣传为重新通过。没有合格上限时仍交付null结果，不凑出成功。

### 资源与产物

每source计算预算265秒，入口身份守卫及末尾核验计入检查；单次文件I/O完成后再检查期限，不声称操作系统调度或I/O可被精确抢占。像素工作预算128MiB：分配前按3倍原生RGB、全部采样/坐标包及16MiB拟合工作区做保守预检，单帧RGB不超过32MiB；mask先验证PNG尺寸/SHA再解码。该预算是像素分配约束，不是Python/NumPy进程总RSS保证。最多处理原24个source，不额外抓取、生成或扩增来源。每source取样包/结果及其独立身份不可变保存；顶层输入也有独立身份，复制sources必须等于原index，检查阶段另绑定seal中的inputs。闭包失败硬阻断封存/资格，不能保留通过rows绕过或从分母移除。软件变动拒绝恢复，失败现场保留。安装依赖/源材料只读。

产物包括protocol.FROZEN.json、inputs.FROZEN.json、source-packs、逐控制recipe/结果、calibration/holdout结果、thresholds.SEALED.json、一次evaluation.json、experimental-repair-profile.json、来源/限制、输入身份前后核验和命令日志。显式purpose=offline_AI_repair_calibration，production_eligible=false；不得由普通VCO-03生产profile入口接受。

参数域另外记录已通过calibration控制的最大绝对**估计修复幅度**，检查时既要求方向与注入相反（零值noop允许），又要求估计值在该封存幅度内。它与注入网格上限是两个字段；即使重建误差小，检查估计越界也不能算域内通过，不据检查结果扩域。

## Files

- 新增 `scripts/experiments/vco06_repair_calibration.py`：算子/门槛、取样、控制、拟合、封存与一次检查入口，不改生产模块。
- 新增 `tests/unit/test_vco06_repair_calibration.py`：真实数值控制、残差/裁切、连续上限、拆分与封存守卫。
- 新增本协议、`VCO-06-calibration-plan.md`、最终校准交付；真实结果之后才完成 `VCO-06-design.md` 并按交接技能回填任务板。

## Tests

所有Python先 `. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment 'vco06-<stage>'`。`& $VideoAiPython -B -m pytest tests/unit/test_vco06_repair_calibration.py -q --basetemp "D:/VideoSi/cache/video-ai/temp/vco06-$VideoAiCommandId" -o cache_dir=D:/VideoSi/cache/video-ai/pytest`；期望全部通过、退出0。先RED缺接口/错误分支，再实现GREEN。

用已知非裁切RGB真值测试增益和色度重建；原样noop、合法光照/不可比/动作缺陷拒修；clipped重大颜色不能被低平均残差接受；连续前缀不会跳过失败；holdout不能参与拟合/未封存拒评；输入漂移拒绝、失败不覆写原样本。真实运行保留全部命令/退出码，不把fixture测试或算子重建结果当作自然视频已经改善。

## Acceptance

24源按原split各有取样/结果或明确弃权；calibration先于seal，holdout在seal之后只检查一次。上限是测量输出或null，不预造数值。输入不变、无模型请求、无生产开启。数值结果与oracle对应/AI来源限制随profile保留；据结果完成可实施VCO-06设计，不能将本阶段当作VCO-06全部功能已经完成。

## Risks

当前语料及分组在先前实验中已被AI看过，holdout不是新盲测，重复变体不是独立来源。配对真值来自构造，不能外推现实匹配和剧情判别；ROI可能混有背景，元数据/作者语义限制保留。原样本非正式16fps，native时间全部保持，只校准颜色算子；真正16fps候选/观察/修订血缘仍属后续实现验收。恒定参数仅覆盖静态偏移，渐变/混合/局部/色相变化不自动修。
