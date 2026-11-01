# VCO-06：轻度非破坏性校色与修订血缘

> **2026-10-30 当前结项口径修订：** 用户指出“任务状态不对，同时完成下一个任务的准备”。本次将任务结项与校色能力准入分别记录：VCO-06按已实现的软件、规定检查、实际输入审计及保守拒修结果结项；自然资格、真实候选及改善仍未验收，`production_eligible=false`、`ready_for_propose=false`保持。下文Acceptance第3、5项据此修订，不把零合格正例写成改善通过。任务板是当前状态的唯一依据；下方BLOCKED说明均为修订前快照。当前结项证据见[状态纠正](../task-handoffs/VCO-06-status-correction.md)。本轮不重做采集、观看、软件实现或模型请求。修订前主设计、任务板和同任务pause交接的原字节见 `D:/VideoSi/projects/video-ai/vco06-natural-qualification/status-adjustments/20261030-015108-25ce410f2be24b8f928ae8bd5427d1a5/entry-manifest.json`。

> **2026-10-30 软件续作收尾：** 自然研究阶段工具、新profile闭包loader及独立自然候选/观察/恢复消费者现已实现；194项最终定向和规定六文件178项兼容均通过，实际16段保留／拒修及6838原件保全完成。见[本轮软件交付](../task-handoffs/VCO-06-natural-software-results.md)和[补齐合同](VCO-06-natural-software-design.md)。这更新的是实现进度；真实已知轴正例仍为0，未产生合格自然profile、真实候选或改善通过，VCO-06继续BLOCKED。下方旧v1、旧r2及早期“尚未实现”原文保留历史语境，不刷新旧SHA或改变原失败。

> **最新实施证据：** 新研究路线的来源导入、全49帧分片诊断和探索性基线已实际交付，入口为[正式研究输入交付](../task-handoffs/VCO-06-research-input-delivery.md)。下方修订入口中的“新路线未实现”是前一轮方案修订时的快照。当前为 `research_input_ready`，仍 `ready_for_propose=false`；新自然资格profile和实际播放Precheck未完成，不改本文件旧v1门槛或VCO-06 BLOCKED状态。

> **2026-10-28 修订入口：** 用户已明确同意修改方案。当前新增路线以 [自然视频输入与校色资格修订设计](VCO-06-natural-input-design.md) 为准，实施顺序为CPU基线/协议、正式研究导入与分片报告、独立自然资格研究、新策略候选及实际观察。下文保留的是已实现 `research_candidate_v1` 的契约；其r2方向、幅度和原p99/max门槛继续按旧版本执行，不套用新研究指标。新路线另建policy/profile/账本；允许新增必要研究接口及重新评估自然适用性，旧profile和失败证据保持原字节。方案批准没有使现有两段素材通过，VCO-06仍为BLOCKED。新路线未实现/未校准，不能据此调用新策略或登记候选改善。原文修订前字节已归档，见 `D:/VideoSi/projects/video-ai/vco06-plan-revisions/20261028-102315-be4e162f9dd1/baseline.json`。

## Goal

对主体和运动完整、仅存在轻微可定位色偏的原生视频，提供默认关闭、可回退的独立校色候选。原片、原模型请求及其接受/拒绝记录保持独立；数值改善、技术媒体检查、完整动态观察与生产可用性分别记账。

任务身份以 `docs/task-handoffs/video-continuity-optimization-task-board.md` 的VCO-06为准。v1设计时用户选择“先补离线AI校色校准，再做VCO-06”，并明确回复“同意，按这条路线走”；后续软件交付及两次真实素材生成见任务板和实际资格结果。2026-10-28用户进一步同意修改方案，授权本文件顶部的新研究路线；方案批准与实际实现/资格/观看验收分别记账。

## Scope

包含受限恒定曝光/单轴白平衡算子、显式研究候选入口、VCO-03稳定匹配证据消费、VCO-04当前epoch/风险绑定、不可变候选与修订记录、原生媒体/色彩复检、实际完整观察及恢复。仅处理已证实sRGB的8-bit RGB、原生16fps恒帧率无音轨源贡献片；音频/字幕保持既有独立链路。旧run不补默认配置或改options。

v1只提供 `research_candidate_v1`，不赋予实验profile普通生产资格。全序列只拟合一个参数；不做色度修复、多轴合成、任意色相、局部重染、时间变化参数、自动算子选择、直方图匹配、插帧/截短/变速、背景冻结、重新推理或自动采纳。自然匹配和光照语义未被本次数值控制实验验证，必须继续显示这一限制。

修订接入在本版本的确切行为：候选修改形成独立修订血缘；普通生产revision及续片入口明确拒绝把研究候选当作已接受原片。当前profile永久 `production_eligible=false`，因此没有可合法开启的生产采纳分支。不制造schema2 Wan生成记录来包装校色媒体；未来允许修复片作为生产父片，需要另外冻结生产资格和媒体导入契约，本版本的拒绝规则不靠配置开关解除。

## Approach

### 1. 已有事实、方案和边界

直接消费VCO-03 `continuity_cv_v1` 普通报告/几何坐标及VCO-04 epoch、Binding、concerns和实际观察协议；不把AI检测阈值换算成修复上限。现有 `scene_revision.py` schema2只支持reconfigure/reselect_images/regenerate_images/regenerate_clips，`scene_clip_records.py`则严格证明Wan generated→retained source映射。修改这些记录的媒体路径会破坏请求证据，因此使用独立候选账本。

已选路线是既有24来源上的离线控制→校准封存→原holdout一次检查→根据合格方向提供研究候选。直接用检测阈值当幅度没有依据；直接替换source或给实验profile生产资格会改变已接受血缘，均不采用。NumPy/OpenCV CPU沿用现有continuity extra，不增加安装、网络、GPU或模型依赖。

以下是基于证据的工程决定：保留单参数恒定变换；已稳定或不能证明匹配/意图的内容弃权；只生成可供观看的研究候选；未验证的生产导入明确拒绝。完整动态观察可以由具备实际播放能力的agent提供，不要求新的人工校准表。

### 2. 校准证据及可执行域

协议 `docs/task-designs/VCO-06-calibration-design.md`；正式证据根 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2`。原根 `AI-repair-calibration-20261027` 保留首源身份格式适配失败，不作为有效校准。r2保持原24-source、六题材、12/12拆分，原生帧不裁短，70非零控制+identity+3门槛控制/源。先封存再检查，不能从holdout扩域。

精确可用方向以r2 `experimental-repair-profile.json` 的 `qualified_directions` 与 `calibrated_bounds` 联合判定。未列入qualified的方向，无论是否有校准上限均不可生成候选；空列表表示所有非零请求都弃权。实现必须读取并验证完整封存闭包，不手抄文档表格作默认参数。每条界限的 `max_injection_level` 只描述构造污染控制，实际参数上限使用 `correction_amplitude_ceiling`，符号使用 `correction_direction`，不得混用二者。

一次检查实际仅4/10方向合格：exposure修复负向a∈[−0.01918276884903868,0)、wb_r负向a∈[−0.018851552816108768,0)、wb_g正向a∈(0,0.036521558455209775]、wb_g负向a∈[−0.03628187114179243,0)。这是实测网格控制及其最大估计幅度的工程包络，不是连续自然视频域的准确率保证；其他曝光/白平衡方向及全部chroma拒绝。a=0统一noop。完整逐方向表与失败/弃权见 `docs/task-handoffs/VCO-06-calibration-results.md` 及根目录closeout-verification.json。

profile必须准确具有 `purpose=offline_AI_repair_calibration`、`algorithm=AI_conditional_constant_color_repair_v1`、`production_eligible=false`、`evidence_only=true`；核验inputs独立身份、原index equality、protocol、software identities、source pack/results独立身份、sealed calibration结果及evaluation引用。研究入口只接受上述完整profile；VCO-03普通生产profile校验器继续拒绝它。代码/依赖漂移时历史结果可只读取证，不能新拟合或渲染候选。

运行时上下文不得宣称自然匹配是oracle。本次校准是“已知配对且已知算子族/轴”下的数值条件证明；实际VCO-03匹配仅是研究候选的工程前提。profile与候选记录始终保存两者差别，完整观看不会把研究profile改成production_eligible。

### 3. 无默认启用的显式接口

不新增普通make-video配置。新增本地 `scripts/scene_color_repair.py`，所有写入持有原run的RunLock，只提供：

```text
propose --run-dir ABS --request ABS
review  --run-dir ABS --review ABS
status  --run-dir ABS [--candidate-id UUID]
```

propose只做本地检查/候选编码，review只消费作者证据，status只读取核验；三者都不推进生产或发布。不接收URL/glob/latest/内存profile/新config/强制覆盖/忽略风险。返回精确 `{schema_version,run_id,candidate_id,status,intent,terminal,review_template,error}`，Artifact或null；error为null或 `{kind,message,evidence_paths}`。schema_version=1，status为abstained/noop/awaiting_review/reviewed/blocked/failed/interrupted，退出码为0/0/3/0/2/1/130。reviewed仅表示候选观察记录完成，production_ready始终false。

公共接口：

```python
# media/color_repair.py；不导入实验脚本，不读生产目录、不调用进程
estimate_constant_repair(reference, current, *, operation, context, profile) -> dict
apply_constant_repair(rgb, *, operation, amplitude) -> uint8_array
score_repair_pairs(reference, current, repaired) -> dict
# runtime/scene_color_repair_records.py；只读
validate_repair_request(value, expected) -> dict
load_repair_profile(path, *, reader) -> dict
load_scene_color_repair_progress(frozen, *, candidate_id=None) -> dict
require_production_repair_origin(value) -> None  # 本版本对研究候选必定ProductionRefused
# runtime/production_scene_color_repair.py；持锁本地事务
propose_scene_color_repair(frozen, units, timeline, request_path, *, paths, logger, lock=None, timeout=300) -> SceneColorRepairResult
consume_scene_color_repair_review(frozen, review_path, *, paths, logger, lock=None) -> SceneColorRepairResult
```

### 4. 严格结构与身份

所有新JSON schema_version=1、精确字段，拒绝unknown键、bool冒充整数、非有限数、未来/无时区时间及非规范UUID。Artifact为 `{path,bytes,sha256}`，文件原始字节SHA；五字段FileIdentity沿用VCO-02定义，不直接与四字段实验身份作全字典比较。规范绝对本地路径按既有规则拒绝alias/UNC、软硬链接、junction和越界。新记录根为 `production/scene-color-repair/`，只读外来证据必须在D:/VideoSi，安装代码/依赖使用原capture规则。

Request精确：`{schema_version,run_id,candidate_id,policy,clip_id,source_clip,assessment,profile,manifest,operation,context,revision_of,requested_at,reason}`。

- policy固定research_candidate_v1。source_clip为原clip.json Artifact；assessment为该clip当前VCO-04 assessment Artifact。普通原片可以未接受，但技术链必须完整；缺陷只能是作者已明确的轻微颜色问题，不能靠原accepted忽略后来的风险。
- profile、manifest为Artifact；manifest是下面规定的独立修复配对manifest，不等于assessment.manifest。propose在intent之后、拟合之前用它运行一次普通VCO-03独立audit，保存并完整验证pair_report；不把传入手写报告当测量。不得从实验oracle坐标直接映射到真实视频。
- operation为exposure/wb_r/wb_g/wb_b之一，作者显式选择已知族/轴，不循环试多个模型挑最优。context精确 `{comparable,intentional_lighting_change,confirmed_motion_defect,subject_structure_intact,operator_basis,review}`；前四为bool，前三必须true/false/false且第四true；operator_basis非空文字，review为下文Precheck Artifact。未知或矛盾先拒绝。
- revision_of为null或同run同clip已有候选terminal Artifact；若该候选中断且无terminal，可引用其intent Artifact。两种类型按固定文件路径及精确schema辨别，不能引用任意JSON，形成无环链；每次仍从原raw估计/渲染，不对上次候选累积修复。不同clip/原片/重复UUID改变request拒绝。

Precheck精确 `{schema_version,run_id,clip_id,assessment,source_clip,video_observation,reviewer,reviewed_at,color_issue,operation,operator_basis,subject_structure_intact,motion_intact,intentional_lighting_change,responses}`。video_observation是实际完整原片schema2观察Artifact；可含color/time_lighting失败，但subject_identity/appearance_structure/motion_process/end_frame_stability/parent_join等非颜色检查必须passed。color_issue为非空轻微颜色说明；operation/basis与Request一致；结构/运动true，intentional_lighting_change=false。responses按VCO-04 concerns精确覆盖，只允许颜色detector的confirmed_issue；其余必须由有效实际完整播放明确not_observed或原冻结context解释。任何结构/动作确认缺陷、unknown、未回应、显式合理光照声明与本上下文冲突都拒绝，不能为修复清除原阻断。

Precheck只授权研究候选，不改变原VCO-04 review/receipt。原片观测failed永久保留；不能写一份新的原片passed覆盖它。作者/时间/范围/父片完整性按原观察协议复核，文字声明不能替代真实播放。

目录与精确结构：

| 文件 | 字段 |
|---|---|
| `candidates/<id>/request.json` | 原Request字节，不重序列化替代 |
| `candidates/<id>/intent.json` | schema_version,run_id,candidate_id,request,binding,engine,created_at |
| `candidates/<id>/fit.json` | schema_version,candidate_id,status,operation,amplitude,correction_bound,fit_pairs,frame_support,before,after,reasons |
| `candidates/<id>/media.json` | schema_version,candidate_id,source,candidate,frames,width,height,fps,time_base,pts,frame_map,encoding,last_frame,evidence |
| `candidates/<id>/terminal.json` | schema_version,run_id,candidate_id,intent,status,fit,media,pair_report,before_report,after_report,closure,failure,finished_at |
| `candidates/<id>/review-template.json` | 下文Review模板，作者/时间空、verdict=unverified，不可接受 |
| `reviews/<sha256>.json` | Review原始字节，所有有效作者提交留存 |
| `candidates/<id>/review-receipt.json` | schema_version,run_id,candidate_id,terminal,review,state,created_at |

Binding精确 `{source_clip,source,mapping,last_frame,selected_image,parent_chain,epoch,assessment,manifest,precheck,profile,profile_closure,revision_of}`。parent_chain按同scene祖先顺序列出原clip/mapping/last_frame/观察Artifact；profile_closure是排序去重Artifact列表；其他均Artifact，revision_of可null。Engine精确 `{algorithm,implementation,dependency_fingerprint,encoding}`，algorithm固定 `constant_color_repair_v1`，implementation按实际源码排序归档，依赖沿用VCO-03完整RECORD/build库存定义；encoding为下述精确recipe摘要。

parent_chain每项精确 `{clip_id,clip,mapping,last_frame,video_observation}`；只要求历史技术/观察真实，不继承原ready。Engine归档复用VCO-04的engine/manifest.json结构（engine_digest、versions、build_information、files），新增当前三个repair产品模块和CLI的原始/归档源码身份；总512MiB、1MiB流式复制预算，归档不执行。dependency_fingerprint=canonical_digest({continuity_engine:已核验VCO-04 Engine,repair_implementation:上述排序Artifact列表,python_numpy_opencv:原capture完整库存摘要})，不接收作者手写fingerprint。

fit.status仅estimated/noop/abstained，amplitude为有限数或弃权null；correction_bound为精确sealed方向行（noop可null），fit_pairs为非bool非负整数，frame_support按F帧精确列 `{source_frame_index,pairs,informative_pairs}`。before/after均为F项 `{source_frame_index,mae,p99_error,max_error,new_clip}`；弃权前未有评分时允许两者均[]，否则不得部分覆盖。reasons为字符串列表，弃权必须非空。纯estimate_constant_repair返回精确 `{status,operation,amplitude,correction_bound,fit_pairs,reasons}`，runtime补齐fit.json帧评分字段。

media.source/candidate/last_frame均Artifact，frames/width/height为正整数，fps固定`16/1`，time_base为实际candidate正理性时间基，pts为F个原始int。frame_map为独立JSON Artifact，其精确结构 `{schema_version,candidate_id,source,candidate,frames}`，frames为F项 `{candidate_frame,source_frame,generated_frame,output_frame,source_pts,source_time_base,candidate_pts,candidate_time_base,rgb_sha256}`。四个frame索引严格从原mapping推导，rgb_sha256指该帧量化后的意图RGB；source_pts/time_base取原native贡献帧，candidate坐标取真实probe。encoding精确 `{algorithm,parameters,command_receipts}`，algorithm=fixed_srgb_yuv444_crf0_v1、parameters为本节冻结recipe对象、command_receipts为原始CommandResult及源/目标字节绑定receipt Artifact数组；media.evidence为probe/完整decode/观看副本/PNG/色彩sidecar等所有产物Artifact数组。awaiting_review前核验帧表与全部输出，不允许把暂存媒体路径当正式Artifact。

terminal.status仅abstained/noop/awaiting_review/failed/interrupted；fit/media/report可null，但awaiting_review必须全部非null。closure为已读输入/输出Artifact排序列表，failure为null或上述error；interrupted也不伪造已核验闭包。不能由terminal字段自行宣布完成观察。pair_report为本intent自有独立audit的普通报告Artifact，只用于下述显式配对拟合，不取代原assessment及风险。

### 5. 匹配、拟合和拒修

独立修复manifest精确沿用ordinary VCO-03 schema1：scope=clip、scene_id等于目标scene、domain.source_kind=generated、genre等于当前assessment、timeline=16/1、profile=null，clips恰好一项为目标clip全部F个原片保留帧，按原mapping输出顺序且无遗漏。references恰好一个frame_id=repair_clean_reference，为原request.selected_image的独立VCO-02分析记录（原选图SHA必须相同、证明sRGB、不是当前视频首帧的别名）；该原图已是模型生成前的参考，Precheck须明确它的颜色/照明是目标意图，不能拿未来候选或其他片段作真值。首个原生视频帧同样与这张独立原图配对，不跳过。

comparisons按原生帧序列严格包含：全部F−1项adjacent（ID为repair_adj_000001起，left为上一帧、right为本帧），再全部F项reference（ID为repair_ref_000000起，left固定repair_clean_reference、right为本帧）。region_ids为作者声明的稳定subject/background区域ID排序列表，所有comparison集合完全相同；regions对参考与目标首帧都有明确anchor，后续由现有普通跟踪传播，不提供未来truth。context必须与冻结原文合理变化声明一致。总source/regions/context/frames/选图及映射闭包在intent绑定并复核。

propose只在空的独立audit run调用analyze_continuity，完整validate_continuity_report并核对本intent的Engine/manifest/producer，pair_report的input_sha256须等于此manifest。**只消费repair_ref_*的geometry.sampled_pairs，left为干净参考RGB、right为当前原片RGB**；adjacent和parent_join从不进入拟合。pair_report中所有F个reference必须确实存在、区域comparability=comparable，每帧至少81个去重配对点；采样只用有效区域，丢失/遮挡或跟踪无支持不冒充visible。原生每帧都有支持才可拟合；缺失/低纹理、人工改坐标、错误PTS或超资源限制均弃权。几何阈值沿用continuity_cv_v1 PARAMETERS，不因色偏失败而调低，不自动只挑成功帧。此研究配对报告不走VCO-04当前assessment注册，所以不与其scene首保留帧参考规则冲突。

每角色每帧确定性均匀保留至多1024对，合并去重；全序列均匀抽至多16384个informative对估计，RGB三个通道ref/current均在[2,253]，少于81弃权。所有取样点逐帧评分，不能在拟合后丢掉不利帧。恒等原始RGB noop；全部匹配样本max通道误差≤2时也noop，防止对已稳定片人为改色；这个2码值是工程不操作门槛，不称作人眼阈值。

运算与校准一致：标准sRGB分段解码→linearRGB；d为曝光[1,1,1]或白平衡指定通道1、另两通道−0.5。median(log2(ref/current))向d投影得单一a。修复为linearRGB×2**(a*d)，clip[0,1]后sRGB编码、np.rint到uint8。禁止截断a“硬夹进”可用域、超限换模型或多次叠加。a=0时noop；其他a必须方向合格且abs(a)≤该方向sealed correction_amplitude_ceiling。校准注入幅度不是a。

每帧匹配点修复后p99最大通道误差≤2，任意通道max≤4，新裁切不高于未修原片（参考interior[3,252]定义同校准）；全序列after_mae必须严格小于before_mae，否则弃权。每帧after_mae不得大于before_mae。逐帧保存原指标、改后指标、支持及时间差分。残差不满足也不另尝试算子。上述仅为匹配区域工程门槛，不宣称全幅语义正确。

修复只用恒定全片参数，不随运动调整；参数时间变化=0。对整帧流式应用同一受限变换，输出每帧还检查任何原值[3,252]通道未新增0/255；匹配区域外出现新裁切就拒绝整候选，保留失败输出。原始高光边界不反推“可接受的新裁切”。检查全幅RGB差异及同坐标前后变化，保存新增饱和/裁切计数；不使用平均分掩盖单帧失败。

### 6. 原生候选和编码证据

只读原clip retained source，验证宽高、native16fps、完整F帧、原PTS与time_base及mapping；生成一张对应一张，不包含模型额外conditioning帧，不调整原scene预算。RGB经VCO-02明确处理链，未知颜色或无法证明sRGB拒绝。候选不冒充Wan generated输出。

主候选master.mp4使用VCO-02现已支持的明确sRGB编码YUV444：rawvideo rgb24、WxH、framerate16输入，固定滤镜 `zscale=matrixin=gbr:transferin=iec61966-2-1:primariesin=bt709:rangein=full:matrix=bt709:transfer=iec61966-2-1:primaries=bt709:range=full:dither=none,format=yuv444p`，`-c:v libx264 -crf 0 -preset medium -pix_fmt yuv444p -an -color_primaries bt709 -color_trc iec61966-2-1 -colorspace bt709 -color_range pc -bsf:v h264_metadata=colour_primaries=1:transfer_characteristics=13:matrix_coefficients=1:video_full_range_flag=1`。YUV码值编码无损，RGB→YUV整数转换有量化，不能称RGB逐字节无损。VCO-02标准回读每帧必须与意图RGB最大通道误差≤2；最终解码候选仍以原配对坐标重新评分，p99≤2/max≤4、逐帧不退化/全片严格改善、全幅无新增裁切均保持原门槛，不因编码放宽。任一失败保存编码现场并failed，不另换编码器重试。

每条命令、stdout/stderr、二进制、处理recipe及意图RGB逐帧SHA保存；实际输出time_base可重标度，但PTS必须逐帧满足 `candidate_pts*candidate_time_base == i/16`，一一映射、长度F/16，禁止只比平均fps。2026-10-27真实四帧64×36工具探针已证明此recipe可保存全部帧/流BT.709、sRGB、pc声明，time_base=1/16384、PTS0/1024/2048/3072，RGB往返最大1码值；日志 `D:/VideoSi/cache/video-ai/logs/vco06-yuv444-feasibility-24d4d3c556a44e3fa4e2ec2c7b477488.log`。该小探针不替代未来全片逐帧检查。

另生成实际观看副本playback.mp4：从master解码，固定 `zscale=matrixin=bt709:transferin=iec61966-2-1:primariesin=bt709:rangein=full:matrix=bt709:transfer=bt709:primaries=bt709:range=limited:dither=none,format=yuv420p`，`-c:v libx264 -profile:v high -crf 16 -preset medium -pix_fmt yuv420p -an -colorspace bt709 -color_trc bt709 -color_primaries bt709 -color_range tv`。不把有损副本的字节当主候选。原生帧数、顺序、时长、PTS映射与主候选一致，重新probe/完整decode；用户VCO-05的RGB High444兼容失败作为这里选标准观看副本的依据。观看记录同时绑定两个Artifact及其处理链，不把未播放的主候选虚构成实际播放。

主候选、观看副本、尾帧PNG保存在候选目录，VCO-02色彩sidecar/analysis frames及各次普通VCO-03 report在各自独立audit run（分析源永远位于该次audit之外）。before_report准确引用原assessment.report，作为原scene/prefix风险上下文；after_report另复制原assessment.manifest的scope/ROI/context/reference/comparison集合、只把目标clip全F帧替换为candidate已验证VCO-02记录。生成新的regions文件：目标clip的anchor.frame换为相应candidate记录身份，rect/region_id/role不变；其他anchor/前缀不变，context中的frame_id保持原映射。在新独立audit测量并验证，不能注册为原VCO-04新的current assessment或发放生产ready。源候选一一映射由本intent/media.json验证，不伪造generated源。拟合用的pair_report是第三条明确独立的干净参考路径；最终解码后的配对评分固定复用pair_report坐标，不重新挑容易匹配的点。机器unverified仍为unverified；after报告无法完整保存/闭包验证则failed。

300秒本地操作检查期限，单次I/O后检查，不声称精确抢占OS I/O；原分析器上限继续有效，修复像素工作预算128MiB、单帧RGB≤32MiB；逐帧流式编码/验证、不驻留全分辨率全片。JSON≤16MiB、同次metadata≤64MiB、native帧≤4096。输出磁盘预算预检为 `3*F*width*height*3 + 512MiB`，超过16GiB则resource_limit，不自动缩尺寸/抽帧；这是工程拒绝上限，非成功保证。所有子进程使用既有run_logged/env/timeout和退出核验。

### 7. 完整动态观察与修订

Review精确 `{schema_version,run_id,candidate_id,terminal,source,candidate,playback,parent_chain,before_report,after_report,review_method,reviewer,viewed_at,playback_ranges,start_observation,process_observation,end_observation,quality_observation,checks,responses,verdict,issues}`。review_method仅human_video/agent_video；四段文字非空；同作者实际完整观看原片、候选观看副本和必要的同scene完整祖先前缀，playback_ranges按绑定顺序列出 `{media,start_frame,end_frame}` 并精确覆盖，不能用静帧或数值替代。

checks精确 `{subject_identity,appearance_structure,color_improvement,material_preservation,motion_process,camera_path,parent_join,no_new_flicker,native_timing}`，每值passed/failed/unverified。responses对before和after全部concern以 `{assessment,concern_id,disposition,reason,references}` 精确覆盖；报告作用域以Artifact区分，不合并同名风险。颜色改善必须有before/after差异说明，原confirmed color issue只能说候选中resolved_in_candidate，原始阻断不删除；after任何确认缺陷、不可确认项均不可passed。其他disposition沿用VCO-04完整播放回应限制。issues为 `{check,media,frames,description}`；verdict按全部checks/responses确定，存在failed必须failed，存在unverified则unverified，其余全passed才passed。作者时间不早于媒体/报告完成且不晚于当前。

responses.disposition仅 `not_observed_in_full_playback / explained_change / confirmed_issue / unverified / resolved_in_candidate`。最后一项仅可用于before_report中已确认的颜色concern，须color_improvement=passed且references含对应after_report/fit，不能回应动作/结构或after风险；其余沿用VCO-04规则。confirmed_issue强制failed、unverified强制unverified，不只从checks计算终态。playback_ranges必须精确为parent_chain各source（由祖先clip Artifact解析）按顺序、当前source、当前playback三个部分，分别覆盖每个媒体自身的完整[0,该媒体帧数)范围；Review.candidate绑定master用于技术身份，实际观看媒体绑定playback，不假称播放master。

passed仅产生 `research_candidate_reviewed` receipt，failed为 `rejected`；unverified只保存raw允许补齐，不写唯一终态receipt。已有failed或后来有效failed原始提交永久阻断该候选；新passed不可覆盖。status返回精确 `{schema_version,run_id,candidates,production_ready}`，production_ready=false；每项 `{candidate_id,intent,terminal,review,state,reasons,revision_of}`，state为awaiting_precheck/abstained/noop/awaiting_review/research_candidate_reviewed/rejected/failed/interrupted/stale。

候选修订必须新UUID+revision_of；算法/参数/profile/原媒体/epoch/ROI/context改变使旧候选stale，只使候选及其观察/报告依赖失效，不删除原视频、模型请求、超分、合成、PCM、字幕或原接受记录。旧候选保留可只读取证；新候选回到原raw重新拟合。原VCO-04 epoch改变即使视频相同也须新的绑定/当前回应，不能复制旧ready。

所有生产父片/超分/合成/发布和生产revision导入只接受原有媒体来源协议；增加显式 `require_production_repair_origin` 拒绝研究candidate路径/record/receipt以及以原source字段偷换候选。既有source SHA、lastframe、request/graph与media-ready闭包本来也必须逐字节核验；新增测试覆盖底层API，不能只在CLI拦截。普通revision schema2拒绝新增kind=adopt_color_repair及candidate字段，不引入假装可用的生产schema3。若有人显式要求以修复片续写，返回blocked及研究profile身份原因，原parent及后代均不变、零POST。

### 8. 事务与恢复

复用原RunLock，全部持久化以exclusive临时文件+fsync+rename，相同原始字节幂等。写入顺序request→intent→fit→media/审计产物→terminal→review raw→receipt；每步前后校验owner和已捕获输入字节。分叉、漂移、同UUID异request、多个成功输出或缺证据均拒绝；不以文件存在当作ready。

已完成terminal只核验，不重估计/编码。仅缺terminal但已齐全且匹配intent的fit/media/报告可核验后补terminal；中断的部分编码/诊断输出保留，返回interrupted，下一次同request不得自动重跑；需显式新UUID并revision_of引用旧intent（无terminal时允许intent Artifact作为revision_of，字段类型由schema验证其路径/内容），仍只从raw开始。最多3个同raw/operation/profile候选attempt，第四个在编码前拒绝；算法/profile改变计为新实验族，但不能让生产启用。

status和历史读取零写入、零新诊断/帧提取/编码，可保留原只读技术核验。真正writer前再核验当前epoch、全部闭包和真实播放提交；不能跨调用缓存ready。

## Files

- 新增 `src/video_ai/media/color_repair.py`：纯受限算子、估计/评分；显式单线程数值上下文，finally恢复设置。
- 新增 `src/video_ai/runtime/scene_color_repair_records.py`：严格schema、profile闭包、Binding/修订链、只读状态、生产来源拒绝。
- 新增 `src/video_ai/runtime/production_scene_color_repair.py`：显式本地事务、流式编码/原生验证、独立审计与review，不含模型客户端。
- 新增 `scripts/scene_color_repair.py`：三个本地操作，沿用bootstrap/frozen inputs，互斥参数/退出码。
- 修改 `src/video_ai/runtime/scene_revision_records.py`、`_scene_revision_origin_clips.py`、`scene_clip_records.py`、`scene_media_records.py`：原来源协议验证处明确研究候选不可生产导入，旧格式不变；不增加生成或历史跳过开关。
- 只读复用 `media/colorimetry.py`、`continuity_report.py`、`continuity_analysis.py` 和VCO-04记录/事务接口，不修改校准冻结software清单中的文件；产品新代码另建Engine身份。这样不会因实现时改写校准所依赖的源码而让正式profile失效。未来需要升级这些依赖时须新协议重新校准，不能更新旧SHA继续使用。
- 新增 `tests/unit/test_color_repair.py`、`tests/unit/test_scene_color_repair_records.py`、`tests/integration/test_scene_color_repair_flow.py`、`tests/integration/test_scene_color_repair_recovery.py`；新增 `tests/scene_color_repair_helpers.py` 明确fixture_only。
- 实施时新增 `docs/task-designs/VCO-06-verification.md`，逐条记录真实结果/命令/限制。校准脚本及其冻结证据不随产品代码重构改写。

## Tests

实施先写相应RED再GREEN。当前只有离线校准23项实际通过；以下产品测试尚未实现或执行，不预记passed。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-core'
& $VideoAiPython -B -m pytest tests/unit/test_color_repair.py tests/unit/test_scene_color_repair_records.py tests/integration/test_scene_color_repair_flow.py tests/integration/test_scene_color_repair_recovery.py -q --basetemp "D:/VideoSi/cache/video-ai/temp/vco06-core-$VideoAiCommandId" -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

预计退出0、无缺依赖skip；集成按文件串行也可，完整汇总。兼容命令同样bootstrap，以vco06-compat初始化，精确运行 `tests/unit/test_scene_clip_records.py tests/unit/test_scene_clip_observations.py tests/unit/test_scene_revision.py tests/integration/test_scene_revision_flow.py tests/integration/test_scene_pipeline_recovery.py tests/integration/test_scene_continuity_recovery.py`，同一pytest参数及独立basetemp，预期全通过。全库回归按用户要求留VCO-08。

必测场景：

1. 数值转移/量化与冻结实现逐字节一致，单参数全片恒定；已知非裁切曝光/各轴真值重建；真实裁切、稀疏大损伤、无改善、任一帧退化拒绝；稳定原样noop。
2. 只允许qualified方向，符号/实际参数幅度严格对应；null/unqualified即使数值改善也弃权；不硬夹参数/换模型，色度和混合轴拒绝。旧实验profile不能进入普通生产profile验证。
3. 全帧可比/81pairs、已知轴/明确无合理光照、作者实际完整预检；unknown/partial/缺帧/假oracle/重大结构动作/合理变化/同size与mtime漂移拒绝。
4. 使用CPU FFmpeg64×36、16fps、两段各2帧（VCO-04实际报告预算内），实际VCO-02→原assessment→独立干净选图pair_report→受限候选→全帧有界RGB回读与重新评分→标准观看副本→after报告闭包。构造原assessment有adjacent/parent_join与独立配对参考不同，证明只选pair_report.reference、首帧不缺支持，坏/外来producer报告不接受。合成播放记录标fixture，不声称真人或agent实际观看。
5. 主候选/观看副本F帧、原生时间理性映射、全幅无新增裁切、末帧/源图/媒体身份精确；ffmpeg失败、未知颜色、超资源/超时不覆盖raw，不能返回awaiting_review。
6. 原始source/generated/request/graph/accepted/rejected/子片/PCM/字幕/旧超分与成片字节不变；无请求普通run不建候选目录、不改变旧options/恢复。
7. review缺实际完整范围/身份、静帧AI、漏风险/假改善/未确认/新增频闪、failed后passed、换epoch拷贝receipt均不reviewed；完整fixture仅证明软件状态规则。
8. 每个事务边界KeyboardInterrupt，完整输出不重算、部分保留、新UUID追溯、3次上限、错锁/漂移/分叉拒绝；status目录清单与文件字节前后相同。
9. 从底层revision/parent/超分/合成/发布入口把candidate当source，明确拒绝且所有HTTP/model/service/SMTP调用计数为0；旧合法原片继承与发布测试保持原行为。

## Acceptance

1. 默认关闭、请求显式、条件不足/noop/不合格方向准确记录；输入和原父子血缘不改，生产研究候选导入必拒绝。
2. 有资格方向的控制及真实CPU小样本完成原生/色彩/前后报告/恢复验证，单参数、无新增裁切和逐帧误差预算有实际证据。纯fixture不作为自然视频视觉改善证明。
3. 交付实际输入的适用性结论，区分观看完成、适用资格、候选技术检查与真实改善。现有16段已完成观看，最终审计4段拒修、12段资格未知、0个已确认已知轴正例；记录这一负结果及原件保护可完成本任务的软件/研究交付。真正的轻度偏色改善、材质/运动/频闪、原生时序和完整前后动态观察仍须实际视频证据，当前均不登记通过；真实资格不足时保持拒修，不启用生产。
4. 原片与观察失败保留，可选择继续使用原已接受版本；候选修订及所有依赖仅局部失效，研究候选不能用于生产父片；所有恢复/漂移/零POST/旧兼容定向用例有日志。
5. 实施验证逐条对应交付证据，并永久保留本次AI/oracle、旧holdout非新盲测及production_eligible=false限制。按本轮用户状态纠正与后继准备要求，软件实现、定向/兼容检查及真实输入审计已交付后，可登记VCO-06 COMPLETED；该状态仅证明任务交付完成，不代表自然资格、真实修复改善或生产校色准入通过。历史失败、未确认标签和未验收限制不得改写；VCO-07只消费自己的直接依赖VCO-04/05，不以VCO-06结项启用校色。

## Risks

- oracle控制仅证明数值算子，不证明自然配准、语义与自动选模。v1提供研究候选、保守弃权及实际观察，不将它包装成通用可靠修复。
- 色度没有连续可用校准上限；实际检查不合格的方向全部禁用，不用更宽容指标重试holdout。
- 普通VCO-03每帧配对报告体积很大，预算不足时完整拒绝；不以抽帧偷换完整支持。实际自然素材缺完整对应时可能没有候选，须如实记录。
- 工具探针发现FFV1/NUT与libx264rgb的普通声明不足以直接复用现有VCO-02 supported分支，故采用已实测的显式sRGB/BT.709 YUV444 recipe；整数RGB转换及观看副本有损必须明示，最终解码仍用原误差门槛。不能把工具探针当全片验收，也不能绕过VCO-02普通输入验证。
- `.git`只读且有多轮未提交成果，所有改动留原工作区；不reset/revert、批量暂存、提交/推送或清理其他任务文件。
- 实施可行性检查：fresh-context builder提出唯一重要问题——修复配对manifest/report与原VCO-04固定参考的关系。第4–6节已明确独立选图参考、本intent自有普通pair_report、只消费reference配对、首帧完整覆盖；原scene风险另用before/after报告，未改变VCO-04契约。容器recipe另外做了实际工具探针。没有遗留需用户选择的产品问题；实际输入和播放结果仍须在实施时据实建立，不预造成功。
