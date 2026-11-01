# VCO-06：自然视频输入与校色资格修订设计

> **实施进度（2026-10-28）：** 正式研究导入、独立context/epoch、全帧分片报告、探索性自然指标基线及生产freeze/load拒绝已实现并用真实纸质素材跑通。49帧及参考图50条记录ready，48 adjacent+49 reference共97组全部可比，49帧新基线各1024个有效配对；88项定向检查通过。具体包、真实命令和限制见[正式研究输入交付](../task-handoffs/VCO-06-research-input-delivery.md)。下文“拟实现/当前尚不存在”保留设计时语境：导入/报告/基线接口现已存在；独立自然资格profile、合格拟合/候选和真实播放Precheck仍未建立，VCO-06仍BLOCKED。研究根配置使用独立 `research/options.json`，普通ProjectConfig不开放研究生产开关。

日期：2026-10-28。主契约：[VCO-06-design.md](VCO-06-design.md)。用户已明确回复“我我同意你修改方案”，承接此前“继续完成，直到可以使用”的目标。本文件记录已批准的修订路线和工程决定，不预记实现、校准或视觉验收通过。

## Goal

让有真实生成证据的原生视频能够合法进入独立研究诊断，并区分可校正的整体色偏与生成模型造成的纹理、形状和局部明暗差异。满足资格的内容才能产生默认关闭、可回退的单参数校色候选，最终由真实完整播放验收。

“可以使用”分为研究输入可读取、可提出修复候选、候选实际观察通过三个结果。导入成功、分数变化、noop 或保留原片不能代替 VCO-06 的真实校色改善验收。

## Scope

包含：真实 Wan 素材的显式研究导入；完整来源与全帧诊断；大报告分片及有界读取；自然视频重建差异的独立资格研究；新的版本化指标/profile；后续研究候选、观察和恢复接入。

本次修改授权允许为这条新研究路线新增或修改必要产品接口、编写新研究协议和重新评估适用性。以下边界继续有效：

- 原 `research_candidate_v1`、旧 r2 profile、旧阈值和失败结果保持原版本语义。新指标不传给旧消费者，不通过刷新旧 SHA 伪装兼容。
- 新研究路线也保持 `production_eligible=false`、`production_ready=false`；生产父片、超分、合成、修订和发布继续拒绝研究素材与候选。
- 继续使用已证明 sRGB 的 RGB8、完整原生16fps、逐帧PTS、一一映射和无音轨贡献媒体。原始音频、字幕和旧 run 独立保留。
- 不引入局部重染、多轴合成、自动轮换算子选最优、时间变化参数、直方图匹配、背景冻结、插帧、截短或变速。每次从原片拟合一个恒定参数，operation 由实际作者明确选择。
- 完整动态观察仍需要真实播放。静帧、CPU分数和模板不能提供播放结论；不要求用户填写新的双人校准表。
- 不安装新依赖、不发布、不写 `.git`；全库回归仍在 VCO-08。沿用现有 NumPy/OpenCV/FFmpeg 环境。

## Approach

### 1. 已有证据和方案取舍

[实际资格结果](../task-handoffs/VCO-06-input-qualification-results.md)已经证明以下事实：

| 已有输入 | 已完成 | 未满足 |
|---|---|---|
| 旧三个已接受首段 | 真实生产来源、原生媒体和历史接受证据 | 原选图缺少当前支持的 sRGB 声明；旧冻结上下文缺诊断策略 |
| 新织物段，49帧 | 原图与全部视频帧色彩解释、像素、16fps时序 | 49个已保存reference测量中37个不可比；完整报告因16MiB输出限制未提交 |
| 新纸质段，49帧 | 同样的技术检查；首帧ordinary报告闭包 | 当前已声明ROI的首帧必要残差条件失败；其余帧尚未证明自然配对 |

织物、纸质段首帧运行时同规则1024点的原始 p99 分别为20、9；r2合格方向最多改变约3码值，残差下界为17、6。这个结论只针对已测配对，不能推广为所有ROI或所有未来素材都不可能合格。它也不能单独证明局部差异全是无害的VAE噪声。

采用的路线是**显式研究来源导入 + 独立自然资格研究 + 新策略接入**。继续随机生成不能解决缺少导入接口的问题；把17或6直接改成新阈值则没有独立验证依据。两段现有视频仅作为已查看的开发/失败材料，不作为新盲测，也不因本次改方案自动转为通过。

本轮首个可执行阶段是现有材料上的CPU资格基线和来源验证。新增模型请求另按冻结的采集清单执行，沿用已获得的真实推理授权；没有必要重复请求同一项授权。未知请求只恢复原ID，不能补单。

### 2. 正式研究导入，保持真实来源类型

新增策略 `research_material_import_v1`，仅接受本项目实际保留的直接Wan事务证据，不开放任意MP4的自声明导入。首版只接受无父片、完整原输出；有父链、外来剪辑或缺来源材料返回 `unsupported_source`。

权威证明必须包括：原冻结options/配置、原manifest、固定Wan workflow/mapping及模型stamp、唯一实际 `/prompt` 请求与受理、保存的成功history、原输出、实际LoadImage输入、生成前真正选用的图片及其色彩转换记录。逐项验证client/prompt/graph/output节点/文件前缀、原输入路径和字节身份；`generated=true`、文件存在或作者声称生成过均不构成证明。

导入Request使用schema1精确字段：

```text
schema_version,material_id,policy,source_index,config,requested_at,reason
```

`material_id`为规范UUID；`policy`固定 `research_material_import_v1`；`source_index/config`为真实Artifact；时间带时区且不在未来。Artifact沿用 `{path,bytes,sha256}`，VCO-02继续使用自己的五字段FileIdentity。

执行顺序：完整只读预检 → 创建唯一新研究run并持RunLock → 保存原Request/intent → 独占复制原图/原片/证据 → 完整技术校验 → 写import commit → 在首次freeze前把commit身份绑定到研究配置 → 冻结options → 建立研究epoch。中断输出保留；同UUID恢复只校验或补完原事务，不能创建第二次生成请求、覆盖旧文件或迁移旧run。

新增根配置 `scene_research_material`，精确为 `{schema_version:1,policy:"research_material_import_v1",commit:Artifact}`；只供显式研究入口消费，必须与新的 `scene_continuity=advisory_v1` 同时冻结。普通 `make-video` 在任何服务/模型动作前拒绝这种配置。旧配置缺少该字段时行为不变。

研究run的记录在 `research/material/`，import commit精确为：

```text
schema_version,kind,run_id,material_id,request,origin,selected_image,
source,frame_map,last_frame,color_analysis,closure,created_at
```

`kind=research_wan_material_v1`；`origin`引用原事务证据索引，复制项同时保存原身份和副本身份，bytes/SHA必须相同；`closure`按绝对路径排序去重。`frame_map`精确记录全部原输出 `generated_frame_index` 与研究 `material_frame_index`、PTS/time_base；没有生产 `output_frame_index`、旁白预算或生产ready身份。不得为它填写假schema2 Wan clip/request/接受记录。最后一帧由原输出准确提取，并绑定实际命令与索引。

导入返回精确 `{schema_version,material_id,run_dir,status,commit,error}`；成功为 `research_input_ready`/0，等待为 `awaiting_evidence`/3，拒绝2，开始后的I/O失败1，中断130。`status`操作只读取证。导入成功仅允许研究诊断；不会赋予修复资格或生产资格。

新增独立研究context provider，真实提供来源、原选图、完整帧映射、当前epoch/assessment及历史观察。使用 `research/continuity/`，不冒充原生产VCO-04当前assessment。原生产context和导入的研究context由明确的冻结策略区分，禁止monkeypatch、测试helper或运行时伪造生产plan/timeline。

### 3. 大报告保存和资源合同

现有 `continuity_cv_v1` 的几何阈值、源码和旧报告不变。新增研究报告schema2：

- 根报告保存input/engine/参数摘要、全部帧身份、完整比较顺序、各分片Artifact、覆盖统计与风险；比较和几何点只保存一次。
- 每个comparison使用独立分片，保留所有真实vectors、sampled_pairs、comparability、reasons和证据。大分片按确定性连续序号继续拆分；不删除点、帧或失败比较。
- 根索引核对全部 `F−1` adjacent 和 `F` reference（含第0帧），检测缺项、重复、分叉、错序和producer借用。缺一个分片就不能形成已提交报告。
- 数据使用固定UTF-8紧凑JSON；保留原始数值，不取整坐标或降低精度。legacy消费者继续拒绝schema2；不能只改schema数字后交给旧加载器。

新研究读取器的工程上限明确为：每JSON≤16MiB；一个活跃读取窗口metadata≤64MiB；一次研究操作去重后的累计JSON读取量≤256MiB；原生帧≤4096；比较≤65536；本地操作仍≤300秒。RGB工作预算128MiB、单帧≤32MiB和16GiB输出预检上限保持。256MiB是新研究路线的有界累计I/O上限，不是旧64MiB合同已验证可扩大的结论，也不是同时驻留量。

读取器按窗口释放对象，身份索引缓存去重但不缓存跨调用“已验证”状态；提交前按流重新核对全部文件。超限或超时保留 `resource_limit/timeout` 和失败现场，不改帧数、ROI、分辨率或参数自动重试。

### 4. 新的测量假设，先研究再准入

现有原图→生成帧的RGB p99/max同时包含重建、材质、配准和色彩差异，不能直接当作纯整体色偏。新策略独立命名 `natural_constant_color_repair_v1`；旧策略的原图残差 p99≤2/max≤4 不再被当作新策略已经校准的自然门槛。**编码回读相对意图RGB的最大2码值预算仍保留**，因为它比较的是同一变换的预期输出与编码输出。

首个研究假设固定如下，不在两个现有失败结果上反复选择滤镜：

1. 注册和ROI传播只消费未改变阈值的ordinary几何结果。所有F帧均可比，每帧至少81个有效配对支持；首帧不跳过，不能在拟合后删掉不利帧/区域。
2. 对运行时既定配对坐标，取原始RGB的9×9邻域。邻域必须完整位于图像和预先声明的有效区域内；边缘不完整项在拟合前按固定规则排除并记录数目。中心坐标、region_id和role在before/after固定复用。
3. RGB按标准sRGB函数转linearRGB后，对每个邻域逐通道取中位数。每角色/帧仍确定性均匀保留最多1024项，完整帧参与评分，全序列最多16384个informative项参与估计。所有通道中位码值须在[2,253]；支持不足即弃权。
4. 继续使用明确operation对应的方向向量：曝光 `[1,1,1]`，指定白平衡通道1、另两通道−0.5；同一median log2投影只求一个全片a。不得自动换轴、裁幅或叠加修复。
5. 新指标保存逐帧、逐角色的投影色偏、正交轴残差、时间差分和修正前后变化；原始RGB p99/max仍完整保存为诊断，不能隐藏纹理变化。整帧变换、全幅无新增裁切及参数时间变化=0继续是硬门槛。

新自然准入阈值字段精确为 `noop_bias_ceiling,minimum_bias_improvement,maximum_frame_bias_regression,maximum_off_axis_residual,maximum_temporal_bias_increase`。本轮数值均为**未确定**；不得填成20、9、17、6或其他为了当前样本通过的值。无已验证值时新策略返回 `awaiting_qualification/3`，不能拟合或编码候选。

统计定义在本设计固定：对每帧i、每角色r的每个有效邻域p，令 `q=log2(median_linear_reference/median_linear_current)`、`s=dot(q,d)/dot(d,d)`；`b[i,r]=median_p(s)`，`o[i,r]=p90_p(norm(q-s*d))`。所有帧/角色等权，before/after使用相同项和坐标。`B=mean_(i,r)(abs(b[i,r]))`；`improvement=B_before-B_after`；`frame_regression=max_(i,r)(abs(b_after)-abs(b_before))`；`off_axis=max_(i,r)(o_before,o_after)`；`temporal_increase=max_(i>0,r)(abs(b_after[i,r]-b_after[i-1,r])-abs(b_before[i,r]-b_before[i-1,r]))`。不把负的regression/increase截成正数；只有全片一帧时temporal_increase记0。上述色偏单位为linearRGB比值的log2，空间维度上的norm为三通道L2。

noop要求 `max(abs(b_before))≤noop_bias_ceiling`；非零候选要求improvement严格为正且达到minimum_bias_improvement，其余三个最大统计量分别不超过对应上限，另通过既有硬保护。noop的幅度返回0；无法证明目标或支持不足仍弃权，不以noop掩盖unknown。阈值以校准范围中点规则产生而非预设常数，缺值时保持拒绝，因此“数值尚未测得”不要求实现者自行猜默认值。

初版新自然策略只能使用旧r2已合格的四个方向，并以相应 `correction_amplitude_ceiling` 作额外硬上限。重新研究适用性不自动扩大修复幅度或方向；若以后需要扩域，必须另建数值校准与profile版本。

### 5. 独立资格研究和profile封存

当前两段、旧24来源及已经查看过的holdout只能进入开发或历史分析，不得命名为新盲测。新的研究protocol、完整来源清单、scene_group、operation/方向、控制recipe、软件/依赖、指标、拆分与选择规则须在测量前冻结。

本修订选择以下研究最低覆盖作为工程决定：development与新holdout各12个完整视频、各至少4个scene_group，两split的group不重叠；同原图、同素材家族或同场景的不同seed归入同group。每个拟取得资格的方向在每个split至少有4个真实自然案例且跨4个group；未达到覆盖的方向不取得资格。题材资格仅声明两split实际共同覆盖的域，不外推到全部六题材。

研究分开保存两类证据：

- **已知真值控制**：在既有原片的字节独立副本上施加预登记恒定算子，验证数值估计、量化、noop、越界、混合轴、时间变化、局部改色和裁切拒绝；人工构造的污染不能计为自然偏色改善。
- **真实自然案例**：独立生成前参考与全部原生视频帧的真实匹配、明确目标颜色/合理光照意图、实际完整播放观察。没有可实际播放能力的AI只提供技术测量，视觉标签保持unverified。未知标签不进入“正例已通过”分母。

development阶段对每个阈值保存正例可接受范围与负例拒绝范围。noop边界取全部中性例的最大初始bias与自然正例的最小初始bias之间的中点；最低改善取中性例可能出现的最大改善与自然正例最小改善之间的中点；帧退化、正交轴、时间变化的上限分别取全部正例对应最大值与预登记有害控制对应最小值之间的中点。有害控制分别为错方向/过量修改、混合轴/局部改色、时间变化；这些是离线已知标签控制，不是合法runtime请求或自然改善。只有范围有严格间隔时才产生阈值；重叠、缺例、语义未知或方向覆盖不足则该方向 `unqualified`。研究protocol在开始前连同样本、控制参数和上述定义冻结，不能在这里预造实测值。

先封存阈值，再对新holdout检查一次。取得资格要求：预登记中性例全部noop；不安全/合理变光/不可比例全部拒修；对应方向的全部有效自然正例满足逐帧保护和实际观察改善。任何缺观察、失败、资源拒绝或弃权都据实保留，不能从目录或分母中删除。没有方向通过也是有效研究结论，但不能生成自然修复候选或完成VCO-06。

新 `natural-repair-profile.json` 的schema1精确字段：

```text
schema_version,algorithm,purpose,production_eligible,evidence_only,
protocol,inputs,software,conditional_profile,thresholds,evaluation,
qualified_domains,qualified_directions,limitations,created_at
```

固定 `algorithm=natural_constant_color_repair_v1`、`purpose=offline_natural_repair_qualification`、`production_eligible=false`、`evidence_only=true`；`conditional_profile`引用原r2 Artifact及完整闭包。其余证据字段为不可变Artifact或精确排序数组；新profile加载器校验冻结inputs/seal/evaluation的独立身份和完整来源，不接受手写结论或精简profile。新profile不替换旧文件，也不能传入旧v1加载器。

### 6. 候选、观察和结果状态

新入口采用显式policy `research_candidate_natural_v1`，另建 `research/natural-color-repair/` 账本。Request精确字段：

```text
schema_version,run_id,candidate_id,policy,material,epoch,assessment,
pair_manifest,conditional_profile,natural_profile,precheck,
operation,operator_basis,revision_of,requested_at,reason
```

原生产片如需进入新路线，也先经真实生产context验证，再提供明确的只读研究视图；不得直接信任路径或绕过历史确认风险。新导入素材由正式研究context提供绑定，不伪称有原生产assessment。

Precheck沿用“实际完整播放、明确颜色目标/已知轴、主体/动作完整、无合理变光、回应全部风险”的语义。研究观察使用独立schema和 `source_kind=research_wan_material_v1`，不填假的 `production_strategy=paragraph_jimeng_v1` 来源。所有失败原文和更晚的有效非颜色缺陷永久保留。候选实际播放仍绑定标准观看副本，完整覆盖原片/候选及存在时的真实祖先。

候选编码、意图RGB与解码逐帧一一映射、标准观看副本、无新增裁切、不可变事务、新UUID修订和同族最多3次attempt继续沿用原设计。源图→视频自然指标采用新profile；candidate解码→意图RGB的编码保护不改。unsupported/profile未资格/匹配不足返回明确等待或弃权，不能仅因成功写文件返回awaiting_review。

| 状态 | 代表什么 | 不代表什么 |
|---|---|---|
| material_only | 只有技术素材和原证据 | 正式来源已准入 |
| research_input_ready | 导入、颜色、完整时序和来源闭包成立，可运行研究诊断 | 已发现可修色偏、已通过观看 |
| awaiting_qualification / awaiting_observation | 缺新的自然资格或真实播放证据 | 自动通过或模型失败 |
| ready_for_propose | 新策略、current研究epoch/assessment、完整配对与真实Precheck有效 | 修复一定能成功 |
| noop / abstained | 原样保留或拒修的真实结果 | 校色改善验收完成 |
| awaiting_review | 独立候选已完成全部技术/保护检查 | 实际完整观看通过 |
| research_candidate_reviewed | 有完整且有效的研究观察 | 生产可用或已发布 |

原片实际可接受且不需修正时，可以明确保留原片，不强行制造色偏来完成任务；“原片可接受”也不计为VCO-06校色改善证据。

### 7. 当前实施顺序和启动条件

1. **CPU基线与研究协议**：保全两段失败样本，落地研究输入来源验证器、明确新指标的统计定义/控制目录和可重放基线。先记录新逻辑是否会错误地放过已知结构/局部变化；不先写profile数值。
2. **研究导入与分片报告**：接口和负例测试齐备后，以两个现有真实事务验证来源、恢复、全帧和报告闭包。预期结果可为研究输入就绪但修复资格仍等待。
3. **新资格研究**：冻结采集清单/请求预算后补齐独立数据、实际观察和控制；按development→seal→一次holdout顺序执行。新增生成请求沿用已有授权；缺来源/色彩声明时先拒绝该输入，不为它伪造记录或反复推理。
4. **新策略接入与真实候选**：只有新profile存在合格方向且完整观察前提成立后接入propose；完成新的真实原片/候选完整动态验收后，才讨论VCO-06完成。

当前第二阶段依赖第一阶段的固定协议和接口schema，第三阶段的数据/标签尚不齐备，第四阶段未获实测准入。它们是明确的执行门槛，不是已经完成的事实。原任务板继续BLOCKED；方案批准本身不构成输入阻塞解除，不自动准备VCO-07。

主要拟实现接口如下，均为新增接口，当前尚不存在：

```python
# runtime/research_material_records.py
verify_wan_material(index_path, *, config, timeout=300) -> dict
load_research_material_context(frozen, *, reader) -> dict
# runtime/production_research_material.py
import_research_material(request_path, *, paths, logger=None, timeout=300) -> dict
# media/research_pair_report.py
analyze_research_pairs(manifest, *, config, paths, logger, timeout=300) -> tuple
validate_research_pair_report(path, *, manifest, config, timeout=300) -> dict
# media/natural_color_repair.py
natural_patch_features(reference, current, coordinates, regions) -> dict
estimate_natural_repair(features, *, operation, context, conditional_profile, natural_profile) -> dict
# runtime/natural_repair_profile.py
load_natural_repair_profile(path, *, reader) -> dict
```

## Files

本轮仅修改文档和留存原字节归档。以下产品/测试文件是后续实现的明确目标，尚未创建或通过测试：

| 路径 | 职责 |
|---|---|
| `scripts/scene_research_material.py` | 显式import/status/observe；来源与观察事务，不调用模型 |
| `src/video_ai/runtime/research_material_records.py` | Request/commit/来源证据验证、只读研究context、生产拒绝 |
| `src/video_ai/runtime/production_research_material.py` | 持锁、独占复制、freeze前commit绑定、恢复 |
| `src/video_ai/media/research_pair_report.py` | schema2分片索引、完整覆盖和流式闭包验证 |
| `src/video_ai/media/natural_color_repair.py` | 固定邻域稳健统计、单参数估计、新指标、资格缺失时拒绝 |
| `scripts/experiments/vco06_natural_qualification.py` | freeze/measure/seal/evaluate/finalize阶段守卫，不执行归档代码 |
| `src/video_ai/runtime/natural_repair_profile.py` | 新profile完整证据闭包、域/方向/阈值资格 |
| `scripts/natural_color_repair.py`、`src/video_ai/runtime/production_natural_repair.py` | 新policy候选/观察/status，独立账本 |
| `src/video_ai/config.py`、`runtime/production_inputs.py` | 仅新研究配置解析、freeze前绑定；缺字段旧行为不变 |
| `runtime/production_scene_pipeline.py`、`runtime/scene_media_records.py`、`runtime/scene_revision_records.py` | 写入/服务启动前显式拒绝研究来源生产使用 |
| `tests/unit/test_research_material_records.py`、`test_research_pair_report.py`、`test_natural_color_repair.py`、`test_natural_repair_profile.py` | 身份、资源、数值和profile拒绝回归 |
| `tests/integration/test_research_material_flow.py`、`test_natural_repair_flow.py` | 真实CPU媒体、恢复、独立观察与新旧入口隔离 |

原r2冻结software清单中的 `media/colorimetry.py`、`_continuity_controls.py`、`_continuity_schema.py`、`_continuity_geometry.py`、`runtime/manifest.py`、`runtime/paths.py`、`adapters/common.py`、`experiments/whole_scene_case.py`、校准脚本和依赖保持原字节。需要改动其中任一文件时，先登记版本迁移并重新建立新研究依赖，不能修改旧software身份清单维持“通过”。

## Tests

本轮为方案修订，未执行新软件测试，以下都是实施时的命令与预期，不是实测通过记录。每个实现先RED后GREEN，依赖项先完成再运行其后继；检查串行，无安装或全库回归。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-natural-import'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_research_material_records.py',
 'tests/unit/test_research_pair_report.py',
 'tests/integration/test_research_material_flow.py','-q',
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco06-natural-import-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
$importExit = $VideoAiExitCode

Initialize-VideoAiEnvironment 'vco06-natural-metrics'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_natural_color_repair.py',
 'tests/unit/test_natural_repair_profile.py',
 'tests/integration/test_natural_repair_flow.py','-q',
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco06-natural-metrics-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
$metricsExit = $VideoAiExitCode
```

预期均退出0，无依赖skip。必须覆盖：

1. 真实原prompt/graph/input/output成功导入；手写最简request、缺HTTP、双POST、错client/graph/seed/输入SHA、未知结果、漂移、外来MP4、alias均拒绝，且零新模型请求。
2. 原图缺真实色彩声明拒绝；有依据的生成前ICC转换可准入；事后替换已有绑定原图拒绝。复制身份保留原出处，不把新路径包装成旧请求路径。
3. 完整49帧/PTS、无音轨、尾帧、分片根索引和全部失败比较闭包；删一个分片/一帧、重复、错序或超资源拒绝，零抽帧。新schema不能被旧reader接受。
4. 新配置只对新研究run生效；普通production底层入口在任何服务/模型/发布动作前拒绝，旧合法run不新增研究目录。
5. 邻域、边缘排除、有效支持、采样、sRGB转换及单参数全片一致；无profile/空资格/null阈值拒绝；原r2幅度和方向上限继续生效，不选择性删帧、换轴或裁幅。
6. 已知纹理重建噪声与整体偏差分别记账；局部重染、形变、合理变光、混合轴、时间变化、无改善和新增裁切不得凭平滑指标通过；原始RGB误差诊断保留。
7. freeze前禁止measure，seal前禁止holdout；同group跨split、已看样本标盲测、缺播放标签、失败后删例、修改seal或旧profile拒绝。新结论可为全部不合格。
8. 旧v1仍执行旧p99/max门槛；新分支不得绕过编码回读≤2、全幅无新增裁切、历史非颜色缺陷和实际完整观察。中断、重复UUID、失败后passed、旧epoch借用收据拒绝。

兼容性在对应接口完成后精确复跑原设计列出的六个生产/恢复测试文件，并保存各自退出码；不把文档检查或旧364项历史结果记为本轮软件验证。

## Acceptance

- [ ] 研究导入具有真实完整来源、颜色、原生时间、全帧与尾帧证据，旧媒体和观察不改；独立素材能够合法读取而不伪造生产来源。
- [ ] 两份当前开发素材的新测量/分片结果可重放；旧失败和未完成报告仍保留原状态。
- [ ] 新协议在数据测量前冻结，阈值由development得出并先seal后独立holdout；没有资格时诚实等待/弃权，旧r2不变。
- [ ] 新策略使用独立policy/profile/ledger；旧v1继续按旧契约拒绝不满足条件的材料，生产入口继续拒绝研究来源。
- [ ] 只有真实来源、完整匹配、有效新profile、当前研究诊断和实际Precheck同时成立时才标记ready_for_propose。
- [ ] 至少一组真实自然候选经全片技术保护、逐帧新指标和真实完整原片/候选观看确认改善；只保留原片、noop、控制样本或分数下降不能替代。
- [ ] 有对应定向软件/兼容性验证与原件保存证据。以上完成前不登记VCO-06 COMPLETED，不准备VCO-07。

## Risks

- 新9×9稳健统计只是待检验的研究假设，可能损失真实局部色偏或错误容忍材质变化；没有独立资格和实际观察时不能启用。
- 来源验证解决合法消费，不解决素材本身适用性；报告分片解决保存，不解决织物段的37个不可比测量。
- 新协议的冻结产物、数据清单、自然标签和实测阈值尚未生成；逐指标统计定义已在本设计固定。**研究阶段可开始，候选启用仍受这些产物约束**。
- 新盲测/scene_group覆盖不一定能收集齐；达到边界后如实报告不足，不把旧holdout改名、不制造污染充当自然正例。
- 当前工具无实际完整视频播放能力；真实视觉证据仍须由实际完整播放者提供。用户批准改方案不等于已观看或接受任何一段视频。
- 本设计不保证新profile一定产生合格方向，也不提供普通生产校色资格；不得把“直到可用”解释成必须制造成功结果。
