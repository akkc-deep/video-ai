# VCO-03：色彩与动作连续性分析器

> **2026-10-26 当前任务完成口径修订：** 用户已明确“ai校准的就可以，我不想填表格”，之后持续授权完成AI路线，并在交付后要求设计VCO-04。本任务按“软件分析器＋可追溯AI实验校准及一次检查”验收；下方Acceptance的当前AI路线条款是主任务完成门槛。原24源/双人独立观看/六项ready profile协议保留为正式Benchmark规则，尚未验收，不再阻塞用户已选择的AI任务路线。软件schema、防泄漏、真实来源、报告/阈值身份和生产profile准入规则不放宽；任务完成不赋予实验profile生产资格。

## Goal

消费 VCO-02 已冻结的颜色解释、真实 `srgb_rgb24_v1` 分析帧和原生帧映射，对接缝、片内变化及三段以上长链生成可复算的区域级色彩/运动证据。把“检测到了变化”“变化是否可比”“是否超出校准样本范围”分开记录，供 VCO-04 后续接入观察与恢复。

任务身份、范围、顺序和状态以 `docs/task-handoffs/video-continuity-optimization-task-board.md` 的 VCO-03 为准。直接依赖仅 VCO-02；其实现及 166+2 项定向检查已完成，全库按用户指示留到项目最后。2026-10-24 用户要求设计下一任务，并明确选择：① 本任务设计样本采集和标注流程；② NumPy + OpenCV CPU 方案。本次仅设计，不安装依赖、采集媒体、标注、运行校准、改源码或登记算法通过。

## Scope

包含：只读批量读取 VCO-02 证据；有明确区域身份的配准与稀疏光流；区域亮度、Lab 色差、色度、采样剪切率；接缝基线、固定参考与累计趋势；主体位置、背景相机轨迹和动作突变候选；独立 audit 报告；样本目录、标注模板、控制变体、阈值拟合和留出评估。

不包含：生产观察/发布准入、运行恢复索引（VCO-04）、自动校色（VCO-06）、修改源视频/metadata/帧率、重新生成模型视频、GPU/光流模型/自动主体检测、网络素材抓取或模型下载。ROI 由明确输入声明，光流支持的是图像运动证据，不声称理解“重新起飞”等动作语义。静帧和数值不能替代完整播放。

**2026-10-24 素材准备授权更新：** 软件交付后，用户先要求协助准备材料，随后明确选择“你来寻找吧”。这一新指令允许为本任务查找并下载有明确使用许可的公开视频，保存来源、许可、下载和身份依据；覆盖上文对本次素材搜集的原限制。不授权模型推理、自动发布、伪造观看/标注、改写源片色彩声明或降低 24-source/双人观看/真实校准验收。候选清单和已下载文件必须与已准入的真实校准素材分开计数。

### 方案选择

| 方案 | 取舍与决定 |
|---|---|
| NumPy + OpenCV CPU | 用户已选择；采用稀疏 Lucas–Kanade 光流、特征点和确定性稳健仿射拟合，支持平移/旋转/适度缩放。新增可选依赖，仅诊断命令导入。 |
| 标准库 + FFmpeg 自制块匹配 | 保留为讨论过的替代方案；依赖少，但复杂运镜/形变支持更保守，本轮不采用。 |

## Approach

### 1. 依赖和执行边界

在 `pyproject.toml` 增加可选 extra `continuity = ["numpy==2.2.6", "opencv-python-headless==4.12.0.88"]`；基础 `dependencies=[]` 不变。正常生产命令、旧导入和恢复不要求安装该 extra；首次调用分析函数缺依赖时报明确 RuntimeError，不隐式安装。禁止同时安装有 GUI 的 opencv-python 与 headless 包。

设计阶段已只读核对 PyPI：Python 3.12/Windows x64 可用的两个 wheel 分别为 12,614,190 和 38,923,559 字节；后者要求 Python>=3.9 时 `numpy>=2,<2.3`，与上述版本相容。SHA256：NumPy `c1f9540be57940698ed329904db803cf7a402f3fc200bfe599334c9bd84a40b2`；OpenCV `86b413bdd6c6bf497832e346cd5371995de148e579b9774f8eba686dee3f5528`。核对日志 `D:/VideoSi/cache/video-ai/logs/vco03-design-wheels-979198c29802410eb501a109c4af314a.log`，未下载 wheel 或安装。

只用 ndarray/Mat CPU 接口，不使用 UMat、CUDA、DNN、视频解码或图形界面。分析调用以模块内锁保护 OpenCV 线程设置，保存 `getNumThreads()`，设置为 1，并在 finally 恢复；不修改全局 RNG、NumPy seterr 或父进程环境。仿射拟合使用确定性 IRLS，不调用随机 RANSAC。记录 Python/NumPy/OpenCV 版本、OpenCV build information、算法源码和已安装包 RECORD 中非 pyc 文件的 SHA；每个唯一文件在一次调用中冻结一次、结束复核一次，禁止每帧重复哈希工具/源视频。

所有写入在调用者 `create_run(RuntimePaths.from_config(config))` 新建的 audit run 的 `logs/continuity/`，使用非 production RunLogger。源生产 run、VCO-02 audit、输入目录、原标注均只读，不实例化其 RunLogger、不创建其锁、不恢复其记录。路径沿用既有本地 D:/VideoSi、非 alias/UNC/symlink/junction、常规文件规则；目录、重复目标和已有产物拒绝覆盖。

### 2. VCO-02 只读证据接口

现有 `_load_sidecar()` 依赖源 audit logger；不能把源 RunLogger 交给下一分析 run，也不能直接相信一份 JSON。VCO-03 在 `media/colorimetry.py` 增加以下公开接口，复用提取出的内部只读校验核心：

```python
load_color_analysis_set(record_paths, *, config, timeout=300) -> ColorAnalysisReader
```

输入为非空、无重复的显式分析帧 JSON 绝对路径列表；不扫描目录。返回只读上下文管理器 ColorAnalysisReader：`schema_version=1`、`algorithm=colorimetry_evidence_v1`；`frames` 保留请求顺序，每行精确 `{record_identity, record, sidecar_identity}`；`sidecars` 按规范 sidecar 路径索引原 sidecar、同资产只保留一份；`identities` 为按规范绝对路径排序且去重的完整 FileIdentity 列表；`read_rgb(record_path)` 按需返回 ready 帧实际 bytes，否则 null。frames 中不累计 full-resolution bytes。退出 with（含异常）复核冻结身份，不写文件。

校验要求：

- 原 sidecar 精确结构、algorithm、input_sha256、原 probe、来源 PNG chunk、processing、risks、颜色解释均重新导出核验；保留 VCO-02 全部原规则，不放宽旧字段。
- 分析记录精确原有 13 字段：schema_version、algorithm、source、sidecar、frame_index、pts、time_base、mapping、status、analysis_space、pixels、command、risks；source/sidecar 身份、asset_id 路径、非 bool frame_index、范围、mapping、原生 pts/time_base 均与 sidecar 一致。路径必须为该 sidecar 同目录下 `analysis/frame_<index:06d>.json/.rgb`。
- ready 必须为已支持且 resolved 的 `srgb_rgb24_v1`；pixels 长度恰为 width*height*3，SHA/stat 匹配；CommandResult 成功、cwd 是原 audit、输入源和完整单帧 zscale args 与 `_analysis_filter` 规则一致，原 stdout 的 bytes/SHA 与 `.rgb` 相等。未经命令实际转换的 RGB 不得进入分析。
- unverified 不得携带 pixels/共同空间，保留原因；缺 zscale 的命令证据仍只作为未验证原因，不提升状态。
- 每个 sidecar 仅校验一次，共享源/工具/证据在此读取窗口内去重校验。结束重新验证全部实际读过的 FileIdentity；源/工具或证据同 size/mtime 字节漂移仍抛 OSError。此缓存仅存在于调用栈，不能跨运行复用。
- 只读上下文只实现规范路径、freeze、verify 和 config；不创建 RunLogger，不执行命令，不写任何文件。VCO-02 四个既有公开接口和 v1 输出保持不变。

资源上限固定：单 raw RGB<=32MiB；单 JSON<=16MiB；一次普通分析最多4096个 frame/ref、65536 comparisons，超限在分配前 ValueError(resource_limit)，不得静默裁短。特征缓存采用 LRU，总数组 nbytes<=128MiB；同时最多保留左右两帧 raw（<=64MiB），故分析器自有图像数组/bytes预算<=192MiB，不把此值误称含 Python/OpenCV 运行库的进程 RSS 上限。固定参考也占缓存、可被逐出，后续按原冻结 SHA 重读 `.rgb`，不重复哈希其源视频/工具；每次重读的 raw 自身仍校验 SHA。metadata 另限64MiB，sidecar intern 避免每帧深拷贝全 probe。超长场景需调用者显式分批、保留固定参考并声明每批覆盖；不把批次当完整场景累计报告。校准逐 source/case 调用同一有界核心，不把24个 source的全尺寸像素同时加载。

### 3. 分析接口与输入

新增 `media/continuity_analysis.py`：

```python
validate_continuity_manifest(manifest) -> dict
measure_continuity(plan, frame_provider, *, deadline=None) -> dict
analyze_continuity(manifest, *, config, paths, logger, timeout=300) -> tuple[dict, list]
```

第一项纯结构校验并返回深拷贝；第二项只测量、不写文件/执行命令，经下述 provider 按需获取已验证帧；第三项冻结输入、构造普通 plan/provider、测量、应用可选 profile、最后复核身份并 exclusive 保存。algorithm 固定 `continuity_cv_v1`。measure 的直接返回值是未持久化的计算结果，不是已审计生产报告；只有外层身份校验完成才可写 report。每个读/算阶段检查共享总期限；无无限重试、隐式重新解码或推理。

所有新 JSON schema_version=1；对象拒绝未知字段，数字拒绝 bool/NaN/Inf；ID 为唯一 ASCII `[a-z][a-z0-9_]*`。FileIdentity 使用现有精确 path/bytes/mtime_ns/sha256/verified_at；摘要使用既有 canonical_digest/hash_file。集合字段保持明确输入顺序，哈希去除 verified_at 等观测时间，但保留真实内容/路径/算法/参数身份。

Manifest 精确字段：

| 字段 | 契约 |
|---|---|
| schema_version / algorithm | 1 / continuity_cv_v1 |
| scope / scene_id | clip 或 scene；非空场景 ID |
| domain | `{genre, source_kind}`；genre为第7节六类枚举的英文ID或unspecified，source_kind=captured/generated/animation/unspecified，均由输入声明、不按像素猜测 |
| timeline | `{fps_num, fps_den}`，正整数；有全局映射时须与该映射的实际时间证据相符。正式生产的16/1规则仍由原运行契约/VCO-04保持，本离线分析不从素材名猜生产策略、不更改源时间基 |
| clips | 有序 `{clip_id, frames}`；frames 为 `{frame_id, record:FileIdentity}` 列表 |
| references | `{frame_id, record:FileIdentity}` 列表；固定比较参考，不自动赋予生产已接受资格 |
| regions | 下述区域标注 JSON 的 FileIdentity |
| comparisons | `{comparison_id, kind, left, right, region_ids}` 列表，left/right 为 frame_id |
| context | 下述合理变化声明 JSON 的 FileIdentity 或 null |
| profile | 已冻结的校准 profile FileIdentity 或 null；不接受内存阈值或命令行阈值覆盖 |

frame_id 全局唯一；重复物理帧只能在显式 same_frame 比较两端复用其唯一 ID，不能伪造两个时间点。clips.frames 必须属于对应已证明 clip，按实际帧序排列，不重排、补帧、复制或采样后假称完整。原 source pts/time_base 保留；全局时间由已证明 output_frame_index 与 timeline 导出，两者分别存储。无证明的时间/对应关系不补猜。

comparisons.kind 的四种语义：

- `same_frame`：原 clip_id/generated_frame_index 相同，或同 source SHA/asset_frame_index，有 VCO-02 映射证据；只有同时满足第4节空间恒等证明时才可直接比较无纹理色块，否则仍需配准。
- `adjacent`：同 clip 两个相邻的实际帧，原 PTS 严格递增、无跳号；缺帧只报告缺口，不插值出补帧。
- `parent_join`：左 clip 最后保留帧→右 clip 首个实际保留帧，clip 顺序相邻且已证明 output_frame_index 相差 1；不能拿子输入 PNG 或被丢弃的头帧冒充子首保留帧。
- `reference`：固定 reference→当前帧，来源与区域声明明确；不同 clip 的 generated_frame_index 相同不构成同一内容证明。

区域标注 JSON 精确 `{schema_version, author, reviewed_at, regions}`，每个 region 精确 `{region_id, role, identity_note, anchors}`；role 为 subject/background；anchors 为 `{frame:FileIdentity, rect:[x0,y0,x1,y1]}`。rect 为像素边缘归一化坐标，0<=x0<x1<=1、0<=y0<y1<=1；每个涉及 clip 至少有一个输入锚点，frame 必须属于输入。identity_note 是作者对跨 clip 同一区域身份的声明，不是自动主体识别结果。不同身份或没有声明的区域不得硬配。未来帧真值框不作为分析输入。

合理变化文件精确 `{schema_version, author, reviewed_at, events}`；event 精确 `{event_id, kind, frame_ids, region_ids, detector_ids, description, references}`，kind 为 lighting/camera/occlusion/content_change/appearance_change。三个ID列表非空，必须引用当前输入的帧/区域/六类detector，不允许通配符。references 为明确 FileIdentity 列表且非空。声明绑定实际原文/已审查视觉契约/人工说明，保留作者与出处；校验身份不等于验证叙事真实性。仅当比较涉及 frame_ids、region_id 命中且 detector_id 命中时，该 detector 降为 not_comparable/declared_change；不解析自由文本决定屏蔽范围，不改写几何测量。lighting 仅可声明四类颜色detector，camera 仅可声明 camera_jump；其他kind也须逐项列出，不能用一句“有运镜”屏蔽整个报告。

### 4. 区域配准、光流和可比性

固定参数全部进入 `parameters_sha256`，不得按题材或素材名分支：

| 项目 | continuity_cv_v1 固定值 |
|---|---|
| 工作缩略图 | 两端宽高比须完全一致，否则aspect_change/not_comparable；公共长边=min(256,两端原长边)，公共尺寸按该比例四舍五入，至少32×32，否则unverified；INTER_AREA，不上采样 |
| 光流灰度 | 非线性 R'G'B' 的 .2126/.7152/.0722 加权量化至 uint8；与下述线性亮度指标分开 |
| 特征 | goodFeaturesToTrack：maxCorners=256，qualityLevel=.01，minDistance=4，blockSize=7，Harris=false，按 y/x 稳定排序 |
| 稀疏光流 | calcOpticalFlowPyrLK：winSize=(21,21)，maxLevel=3，criteria=(COUNT|EPS,30,.01)，flags=0，minEigThreshold=1e-4；正反各一次 |
| 对应筛选 | 双向误差<=1 工作像素；9×9 去均值归一化 patch NCC>=.85；零方差 patch 不参与光流 |
| 支持量 | 每区域>=12 有效点，覆盖 4×4 ROI 网格的至少4格，配准有效重叠面积>=35% |
| 背景相机拟合 | 仅声明 background 的点；完整2×3仿射、np.linalg.lstsq，5轮 Huber IRLS、delta=1.5工作像素；最终残差<=2像素；设计矩阵条件数<=1e6，行列式在[.5,2] |

这些是版本化的数值稳定/匹配支持条件，不是视频质量阈值。校准必须统计由它们造成的弃权率；调整任一值创建新算法/参数身份并重新校准，不能手改数值复用旧 profile。

每个 pair-region 精确产出 `comparability = comparable | not_comparable | unverified`、reasons、支持点数/网格覆盖/双向误差/NCC/有效面积、仿射和置信度。置信度定义为匹配支持度而非“正确概率”：各项归一到[0,1]后取最小值，项为有效点比例、覆盖格数/16、有效重叠率、max(0,1-p90双向误差)、(中位NCC+1)/2；分母0则该项0。保存分项及 `confidence_kind=match_support`。只有同 source SHA/asset_frame_index，或原成功处理规则能证明仅时间裁剪/整幅等比例缩放、无空间裁切/旋转/未知模型几何时，same_frame 可使用恒等归一化坐标：confidence=1、basis=same_source_mapping、confidence_components=null；一般“同一生成帧”仅证明内容来源，未知空间处理仍需配准。未取得对应时 confidence=0、分项=null，仍不证明标签/摄制意图正确。

缺 ready RGB、unknown/conflicting/unsupported、缺映射或时间、区域身份不明：unverified。图像中的遮挡/内容替换导致相同局部对应无效、几何条件不满足：not_comparable。合理变化声明只作用于明确列出的detector，不伪造几何失败。空 ROI、非法坐标/引用则 ValueError。配对色差仅取已通过检查的同一区域对应 patch，不跨主体、字幕覆盖区、新背景或遮挡凑数。自然 pan/zoom 有可靠配准时继续局部测量；不可靠时弃权，不产生必然异常。

每个subject也用同样点数、残差、条件数和det范围执行独立5轮IRLS仿射；无法拟合时不传播框。背景相机拟合汇总声明background的有效点，另须覆盖整幅4×4网格至少4格。拟合以归一化坐标求解，Huber/残差阈值换算到右图工作像素。仿射存为归一化左→右坐标的2×3矩阵；相机平移是图像中心(.5,.5)经变换后的位移，旋转由线性部分的极分解R=U·Vt得到atan2(R10,R00)，尺度为sqrt(det(A))、记录log尺度；拒绝反射/退化。主体框把原框四角经subject仿射后取轴对齐包围盒，不裁切逻辑框，中心为包围盒中心；显示图可裁边，但edge_margin必须用未裁逻辑框。主体相对速度=(subject中心位移-该点的背景预测位移)/实际dt；无背景则该项null，不假设相机静止。跟踪丢失记录tracking_lost，不自动认定出框/变形。

颜色采样固定为：每个有效跟踪点取工作坐标9×9整数偏移，以该点实际左/右光流对应的中心分别加同一偏移；两端patch必须完整在同一区域/有效画面内，否则丢弃该点。工作像素中心按 `(x+.5)*原宽/工作宽-.5`（y同理）映射到原RGB，最近邻取样、tie取较小索引，不对颜色做光流灰度归一化或双线性插值。对同一 `(左原像素,右原像素)` 去重，每对只计权一次；统计这些像素对的Lab差，不统计patch均值的差。same_frame恒等坐标则在ROI内按工作网格逐点同规则取样。至少81个唯一像素对，否则unverified。patch中心、流向量和接受掩码作为pair证据，不把未来真值框喂给配准。

### 5. 测量与候选定位

所有颜色测量使用原始 sRGB 分析值，光流的亮度归一化不能回写颜色。先执行 IEC 61966-2-1 逆传递，u<=.04045 时 u/12.92，否则 ((u+.055)/1.055)^2.4；线性 Y=.2126R+.7152G+.0722B。XYZ矩阵行分别为(.4124564,.3575761,.1804375)、(.2126729,.7151522,.0721750)、(.0193339,.1191920,.9503041)，白点(.95047,1,1.08883)，Lab 使用 delta=6/29 的标准分段；本版配对色差为 ΔE76 的欧氏距离，明确不是 ΔE2000。色度 C*=sqrt(a²+b²)；亮度比使用 log2((Yright+1/65535)/(Yleft+1/65535))。统计采用有限值、排序中位数及线性分位数 q*(n-1)。

每个有效区域记录：ΔL*/Δa*/Δb*、ΔE76 中位/p90、线性 Y 和 log 比、C*变化、采样 R/G/B==0 或255的比例。剪切率是工作采样点的码值比例，不等于传感器剪切或全分辨率统计。

六个校准检测器及固定 score：

| detector_id | score 和定位 |
|---|---|
| seam_color | parent_join 的区域中位 ΔE76 减去父尾/子头各0.5秒内可比相邻对基线的较大中位数，结果下限0；每侧至少3个有效相邻对，否则 unverified |
| local_color | 每个可比区域对的 p90 ΔE76；按 region 单独报告，不能仅依赖全图均值 |
| color_drift | 相对固定 reference 的 p90 ΔE76，输出完整时间序列以及亮度/色度/剪切分项 |
| cumulative_color | 同一固定参考的 ΔLab 三分量各作 Theil–Sen 斜率，斜率向量范数×有效时间跨度；至少3个有序 clip、每 clip 至少3个有效参考比较，附末端相对参考偏差，不相加 ΔE 冒充累计量 |
| motion_reset | 主体相对背景速度向量的突变范数，除以前0.5秒速度差的 MAD+1e-6；至少3个有效历史速度；单位/时间以实际 dt 和归一化画面尺寸表示 |
| camera_jump | 平移速度突变的归一化范数、旋转速度突变绝对值、log尺度速度突变绝对值分别除以前0.5秒对应差值 MAD+1e-6，取三者最大值；不足3个历史样本则 unverified |

主体中心/框、距画面边缘的最小有符号归一化边距、光流向量、相机轨迹、速度方向变化全部保存为证据；motion_reset 输出名称为“动作/运动突变候选”，不作语义动作已重启的结论。不同 source fps 保留原 PTS/Fraction 时间差，不变速到16fps。生产全局输出时间仍按已证明16fps映射另存。

MAD统一用于标量序列：median(abs(s-median(s)))；motion_reset的历史s为相邻相对速度向量之差的范数，camera_jump的三个历史s分别为相邻相机平移速度差范数、旋转速度差绝对值、log尺度速度差绝对值，不把向量MAD留给实现者选择。轨迹timestamp为 `{pts,time_base}` 的显示时间；frame_results保留原生时间及全局时间字段，实验时间来源由provenance明确区分。

命中合理变化声明时，保留原分项测量，对相关检测器给 not_comparable/declared_change；遮挡/视角变化不能借全图直方图转成异常。没有 profile、profile 不适用或对应指标不可用时只给测量和 unverified，不填任何默认颜色/运动阈值。

### 6. 报告与证据 schema

`logs/continuity/report.json` 精确字段：

`schema_version, algorithm, parameters, parameters_sha256, input_sha256, inputs, dependencies, scope, scene_id, domain, coverage, frame_results, comparisons, trajectories, detectors, profile, risks, created_at`。

- inputs 精确 `{manifest, files}`，manifest 为规范化输入深拷贝，files 为实际读过的完整 FileIdentity（含标注/context/profile/原 VCO-02 闭包）；dependencies 精确 `{python, numpy, opencv, build_information, package_files, fingerprint}`，前3项版本字符串，build_information 是落盘文本 FileIdentity，package_files 为已安装依赖与算法源码身份列表。
- input_sha256 绑定 inputs 的稳定身份、算法、参数、依赖 fingerprint 与 profile 内容 SHA，不含时间戳。相同冻结输入的数值与 canonical metric digest 可复算；输出路径/创建时间不要求字节相同。
- coverage 精确 `{requested_frames, ready_frames, requested_pairs, comparable_pairs, not_comparable_pairs, unverified_pairs}`，只表示测量覆盖率，无质量 passed。
- frame_results 每行精确 `{frame_id, record, source, source_frame_index, pts, time_base, output_frame_index, timeline_seconds, status, risks}`；时间字段不得混写来源与成片时间。
- comparisons 每行精确 `{comparison_id, kind, left, right, regions}`；region 结果精确 `{region_id, comparability, reasons, geometry, confidence, confidence_kind, confidence_components, metrics, evidence}`。geometry 精确 `{basis, working_size, candidate_points, valid_points, occupied_cells, overlap_fraction, fb_error_p90, ncc_median, affine, vectors, sampled_pairs}`；working_size为[width,height]，vectors行精确 `{left, right, residual, fb_error, ncc}`（坐标/位移归一化，误差工作像素，未知background时residual=null），sampled_pairs为去重后的左右原像素整数坐标对。confidence_components为null或精确 `{tracked_fraction, grid_fraction, overlap_fraction, fb_support, ncc_support}`。metrics 精确 `{delta_lab_median, delta_e_median, delta_e_p90, left_luma_median, right_luma_median, luma_log_ratio, left_chroma_median, right_chroma_median, chroma_delta, left_clipped_fractions, right_clipped_fractions, sampled_clipped_delta}`；delta_lab_median为3向量，其余普通指标为有限数或null；三个clipped对象均为null或精确 `{r_low,r_high,g_low,g_high,b_low,b_high}`，delta为右减左。evidence 为关联帧记录和下述诊断 PNG 的 FileIdentity。
- trajectories 每行精确 `{region_id, samples}`；sample 精确 `{frame_id, timestamp, center, box, image_plane_velocity, camera_compensated_velocity, flow_direction, direction_delta, camera_translation, camera_rotation, camera_log_scale, edge_margin, status, confidence}`，缺可靠依据的项 null。方向为atan2(vy,vx)，零速度null；方向差wrap至[-pi,pi]。
- detectors 每行精确 `{detector_id, region_id, frame_ids, score, threshold, status, reasons, confidence, evidence}`，status 为 candidate/no_candidate/not_comparable/unverified；threshold 来自 profile 对应行或 null。no_candidate 不是视频通过，confidence 沿用测量支持度。
- risks 行精确 `{code, detail, frame_ids}`；包含 unknown_color、unverified_mapping、identity_unverified、insufficient_texture、occlusion、registration_failed、missing_history、missing_reference、missing_profile、profile_mismatch、out_of_calibration_scope。
- profile为null或精确 `{identity, applicability, status, enabled_detectors, domain_match, reasons}`；identity为profile的FileIdentity，status沿用其ready/partial/unverified，domain_match为bool。parameters严格等于以下固定v1字典（分数在Python中求double后序列化），不接受输入增删/覆盖；任何数值/约定变更需要新身份及重新校准：

```python
{
 'geometry': {
  'coordinates': 'normalized_affine_nn_patch_v1', 'thumbnail_long_edge': 256,
  'minimum_image_size': [32,32],
  'features': {'maxCorners':256,'qualityLevel':.01,'minDistance':4,'blockSize':7,'useHarrisDetector':False},
  'flow': {'winSize':[21,21],'maxLevel':3,'criteria':[3,30,.01],'flags':0,'minEigThreshold':1e-4},
  'matching': {'max_fb_error':1.,'patch_size':9,'min_ncc':.85,'min_points':12,
   'grid_size':[4,4],'min_grid_cells':4,'min_overlap':.35,'min_sample_pairs':81},
  'affine': {'model':'full_affine_irls','iterations':5,'huber_delta':1.5,
   'max_residual':2.,'max_condition':1e6,'det_range':[.5,2.]}
 },
 'color': {'input_space':'srgb_rgb24_v1','flow_luma':[.2126,.7152,.0722],
  'srgb_cutoff':.04045,'srgb_divisor':12.92,'srgb_offset':.055,'srgb_scale':1.055,'srgb_gamma':2.4,
  'xyz':[[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]],
  'white':[.95047,1.,1.08883],'lab_delta':6/29,'luma_epsilon':1/65535,'delta_e':'CIE76'},
 'windows': {'baseline_seconds':.5,'minimum_pairs':3,'minimum_reference_pairs_per_clip':3,
  'minimum_cumulative_clips':3,'quantile':.9,'motion_epsilon':1e-6},
 'resources': {'max_raw_bytes':33554432,'max_feature_cache_bytes':134217728,
  'max_image_bytes':201326592,'max_json_bytes':16777216,'max_metadata_bytes':67108864,
  'max_frames':4096,'max_comparisons':65536}
}
```

证据 PNG 写在 `logs/continuity/evidence/<comparison_index:06d>_<side>_<region_index:04d>.png`；标准库编码已验证分析 RGB 的缩略图、sRGB chunk；pair JSON为 `logs/continuity/pairs/<comparison_index:06d>.json`，精确 `{schema_version, algorithm, input_sha256, comparison}`，comparison完全等于report中对应行，含原record身份、坐标和向量；无 raw 时只保留原未验证记录，不造图。数值结果另写 `metrics.json`，精确 `{schema_version, algorithm, input_sha256, frame_results, comparisons, trajectories, detectors}`，profile/评估只绑定该文件的 canonical 内容摘要。所有写入 exclusive，漂移/失败不写 report.json，现场诊断证据可保留，下次显式新建 audit。

### 7. 样本采集、标注及防泄漏协议

用户选择在本任务设计流程，**不表示已经有这些样本或已播放/标注**。以下是本设计确定的首批规模和操作协议，不是已有实测数量或通用准确性保证。

首批24个独立 source scene，6个分层各4个：人物与衣饰、动物与毛羽、交通/工业物体、自然户外、室内与材质、动画/图形。分类只用于评估分层，算法不得按 genre 分支。每个 scene 选一个连续≥4秒区间，保留原 fps/PTS/分辨率；可接受任意可靠原生时基，不强改16fps。需要有可标注主体、背景和可观察图像运动。素材必须是操作者明确提供或有明确使用依据的本地文件；不自动扫描“最新”、联网采集、付费请求或生成模型视频。

每个 source scene 有唯一 scene_group，按明确列表每层2个校准、2个留出，共12/12。相同原片、相邻/重叠区间、同图的衍生片、同生成血缘属于同一 scene_group，禁止跨 split。split 清单先冻结再拟合；不根据结果换样本或移动 split。未满足数量/题材/标签/颜色解释时可开发软件和测试 fixture，但不能把真实校准部分记为完成。

外部输入 `catalog.json` 精确 `{schema_version, corpus_id, corpus_kind, sources, split, created_at}`，corpus_kind 为 real_benchmark 或 fixture_only；sources 每行精确 `{source_id, genre, source_kind, scene_group, media, frame_records, interval, rights_note, regions, truth, context}`。genre枚举ID固定为 people/animals/transport/outdoor/indoor/animation（对应上述六类），source_kind=captured/generated/animation；media、regions、truth、context 为 FileIdentity（context 可 null）；frame_records 为有序 VCO-02 分析帧记录身份列表；interval 精确 `{start_pts, end_pts, time_base}`，半开区间，必须完整覆盖选段；split 精确 `{calibration_groups, holdout_groups}`。source SHA/原 run 关联和 scene_group 冲突拒绝，依赖人工声明的“独立拍摄”在限制中保留。

truth JSON 精确 `{schema_version, author, reviewed_at, samples}`；sample精确 `{frame, regions}`，frame为原VCO-02记录FileIdentity，regions行精确 `{region_id, box, visibility, mask}`；box使用同样归一化坐标，visibility=visible/partial/occluded，mask为原尺寸单通道8bit PNG的FileIdentity或null（null表示box矩形mask）。标注覆盖每个原帧；人工先核对插值辅助结果，再逐帧确认，不能把未确认插值当真值。未来box/mask仅传给控制构造器和评估器，普通分析manifest/FrameProvider不含它们。control可用真值mask施加局部改色/遮挡，但测量器只能收到变换后的RGB、每clip起点锚点以及由整幅几何变换推导的padding有效区，不能收到未来subject位置/visibility或mask。初始anchor文件与truth分别冻结，接触边界须有测试验证。

采集步骤固定：人工指定候选路径和使用说明→只读核对媒体身份/来源/时间与 VCO-02 ready 覆盖→准备小批次明确帧索引的 VCO-02 独立 audit（不修改原片）→填目录与初始 ROI→冻结目录/split→生成未填写标签模板→两人独立完整播放并标注→分歧由第三人裁定形成新标签文件→冻结标签→校准一次→仅一次留出评估。数据准备不在 pytest 中执行，不开长期后台；每批实际准备命令单独给出预算与日志，失败保留已有记录，不自动扩大采集或推理。

每个 source 派生10个已记录控制 case，共240 case：

| case | 构造和真值 |
|---|---|
| unchanged | 原区间，人工标注已有自然变化；不能自动视为无异常 |
| allowed_lighting | 线性 RGB 曝光因子1→1.2缓变，带对应 lighting 声明，颜色不判必然异常 |
| allowed_camera | 整幅连续平移0→宽度5%、缩放1→1.05，带 camera 声明及有效区域掩码 |
| occlusion | 在区间中间25%时长覆盖主体框50%面积，已声明遮挡，预期弃权而非必然异常 |
| seam_color | 中点后线性 R 乘1.2、B乘.9并clip[0,1]，无合理变化声明，形成接缝正例 |
| local_color | 同一时段只对 subject ROI 作上项变化，其他区域不变，用于局部正例 |
| gradual_drift | 全区间线性 R 因子1→1.2、B因子1→.9，形成渐变正例 |
| cumulative_drift | 区间分成三段，R因子1/1.1/1.2、B因子1/.95/.9；均与原始固定参考比较 |
| motion_reset | 显示序列前半原样，后半从选段起点重播同长度，显式标为控制重置；不得称源视频自身 PTS/动作已改变 |
| camera_jump | 中点后整幅平移宽度8%，不提供合理 camera 声明，形成相机轨迹跳变正例 |

控制操作在已验证 RGB 内存副本/独立实验文件上执行，原 VCO-02 文件和时间不变；保存精确 recipe、掩码、父帧 SHA、控制显示序号/时间和源帧 PTS 两套映射。重复/重排只存在显式 benchmark control，不能作为生产 manifest 的 adjacent 记录；measure_continuity 的内部控制数据通道必须由校准器创建且附 control provenance。没有插帧/变速/校色生产输出。上述变换幅度是受控实验条件，不是检测阈值或真实模型异常程度。

案例必须两位标注者独立看完整区间和变体，不能只按 recipe 自动认定真值；低纹理、动作重播不产生实际变化或遮挡过大时可标 unverified，并保留原因、配对范围和原素材。不可用样本不得凑数；补充数据必须新建 corpus 版本、保留旧评估，不能反复看留出集调阈值。

`labels.json` 精确 `{schema_version, corpus_sha256, annotators, adjudicator, entries, reviewed_at}`；annotators 为两个不同非空作者 ID，adjudicator 为不同 ID；每个 entry 精确 `{case_id, region_id, frame_interval, detector_id, labels, final_label, rationale, evidence, adjudication}`。labels 为两个 `{author, label, viewed_interval, viewed_at}`，各作者须与annotators一一对应；label/final_label 为 anomaly/normal/not_comparable/unverified；所有frame_interval/viewed_interval均为半开显示帧索引[start,end)，非bool整数且在[0,N]内，viewed_interval须覆盖完整[0,N)。adjudication为null或精确 `{author, adjudicated_at, reason, evidence}`；两人标签不同必须有与root adjudicator一致的独立裁定记录及FileIdentity证据，不能只写一句rationale代替。其余evidence为播放记录/注释文件 FileIdentity 列表且非空，所有时间为带时区ISO。不得伪造人的播放或签名；缺人工输入保持模板/unverified，不登记真实校准通过。ROI 真值轨迹仅用于评估，分析器只收到每 clip 初始锚点，不能把未来真值框泄漏给跟踪。

#### 7.1 内部控制通道和两套时间

普通分析不接收可自称已验证的内存RGB或控制manifest。`analyze_continuity` 只接受第3节普通manifest和 `ColorAnalysisReader`。校准器另有唯一控制构造入口：

```python
build_control_case(source, variant, *, reader, truth) -> (ControlCase, FrameProvider)
```

这是内部实验接口，不作为生产CLI的输入格式。先由reader核验全部原帧，再构造变体；没有来自reader的冻结来源就拒绝。低层 `measure_continuity` 接受规范化 ResolvedPlan 和 FrameProvider，既可用于普通只读来源，也可用于这个已留证控制通道；直接调用的计算结果不能被当成report/profile验收。

ResolvedPlan 精确 `{schema_version, algorithm, purpose, domain, frames, clips, references, regions, comparisons, context, provenance}`；purpose=ordinary/benchmark_control；clips/references/comparisons语义与普通manifest相同但引用内部frame_id；regions是已解析的role/起点anchor，context是已解析的定域events。frames行精确 `{frame_id, source_record, source_clip_id, source_frame_index, source_pts, source_time_base, display_pts, display_time_base, output_frame_index}`。普通purpose的display取已证明全局时间（没有全局映射时同clip使用源时间），不能从列表位置猜；控制purpose遵循下面display_map，明确标为实验时间。provenance精确 `{kind, input_sha256, source_files, control_case}`，kind=verified_source/benchmark_control；control_case为null或控制JSON的FileIdentity，truth不展开给测量器。

FrameProvider只实现 `get(frame_id)` 和 `release(frame_id)`；get返回精确 `{width, height, rgb24, valid_mask}`，rgb24是经过身份验证/已记录控制构造的RGB bytes，valid_mask为null（全有效）或同尺寸bool数组，仅表达整幅warp引入的padding。接口不提供未来box/mask/visibility。普通provider从reader读，控制provider从已验证父帧按recipe惰性生成并受同一192MiB图像预算约束；测量核心不打开provenance文件，人工真值只由构造器/评估器读取。

ControlCase JSON 写 `logs/continuity/calibration/controls/<case_id>.json`，精确 `{schema_version, case_id, source_id, scene_group, split, variant, base_input_sha256, recipe, display_map, clips, references, comparisons, anchors, context, padding_masks, truth, created_at}`。truth只为FileIdentity；padding_masks为按display顺序的单通道PNG FileIdentity或null列表，供复算构造结果，不作为ROI真值输入。上述所有身份与recipe参与case_sha256；构造的每个frame都有可复算父record和原source PTS，不修改原media或原记录。

recipe精确 `{variant, linear_r_factors, linear_g_factors, linear_b_factors, translation_x, scale, occlusion_fraction, occlusion_interval, local_region_ids}`。前5个数值序列长度均为N，无操作用1/1/1/0/1；translation_x是画面宽度比例；其余项分别为[0,1]标量、半开display索引区间或null、subject区域ID列表。颜色先转线性、乘因子clip[0,1]后转sRGB取最近整数（.5取偶数）；光流仍测量该最终RGB。局部变换采用truth的mask（无mask用box）；遮挡在subject真值box上半部填RGB(128,128,128)，occlusion_fraction=.5，不把这个构造mask传给跟踪。整幅camera变换绕中心按scale后平移、INTER_LINEAR、边外填0，并用相同插值及仿射变换float32全1图，仅结果精确为1的位置属于padding有效区；padding及混合边缘像素不参与配准或颜色统计。

display_map每行精确 `{frame_id, source_frame_id, display_index, display_pts, display_time_base, transform_index}`。N为选段原帧数，不新增/插值视频帧；display_pts取原顺序PTS减首PTS，time_base保持原值。除motion_reset，source_frame_id按原顺序；motion_reset令h=floor(N/2)，前h帧原序，后N-h帧映射源索引0..N-h-1。transform_index=display_index；源PTS从对应reader记录取得，不改写为display值。原型生成器必须把控制的重复/重排放在benchmark_control中，普通manifest的顺序/邻接校验不得放宽。

所有变体除cumulative_drift都在h处分成两个实验clip，便于正常/异常join可对照；cumulative按floor(N/3)、floor(2N/3)分三clip。每段内部生成所有adjacent、段间生成parent_join；固定reference为未变换的原source首帧，每段与其生成reference比较。其frame_id与控制显示ID分开，same source的两种实验身份只在控制通道允许。anchors只包含每个实验clip第一显示帧所对应的人工起点框（按控制几何变换更新），不能传入该clip后续真值。local_color可在每个已建立对应的区域逐对测量，不依赖全图或未来mask。

recipe数值按表构造：曝光为t=i/(N-1)的线性变化；中点跳变从h开始；occlusion区间为[floor(3N/8),ceil(5N/8))；cumulative因子按三段固定。allowed_lighting的三个通道同乘1+.2t；allowed_camera的translation_x=.05t、scale=1+.05t；camera_jump的translation_x从0跳到.08。其余R/B因子与表相同、G=1；局部/遮挡区域由local_region_ids逐项指定。

构造阶段的校准context只把已知lighting/camera/occlusion声明映射到明确display帧、region_ids和detector_ids；不得读取最终anomaly/normal标签来决定屏蔽。模板生成器可填构造意图，但所有人工labels保持unverified，不能按variant名称自动签出真值。paired frame/clip计划和控制文件在拟合前冻结，校准/留出使用完全相同构造器。

### 8. 校准与独立评估接口

新增 `media/continuity_calibration.py`：

```python
build_annotation_template(catalog) -> dict
validate_calibration_catalog(catalog, labels=None) -> dict
calibrate_continuity(catalog, labels, *, config, paths, logger, timeout=600) -> tuple[dict, list]
```

纯校验不启动 subprocess；校准只在显式调用执行，使用上面同一测量核心和控制 recipe。每 case-region-detector 汇总为有效 score 的 p90（seam仅一个join时直接取该score，多个join也取p90），保留帧级结果，不能把同 source 的大量帧当独立样本。只在 calibration_groups 上枚举相邻有限 score 中点及两端 nextafter 边界，使用 score>threshold 判候选；最小化 balanced error=(FPR+FNR)/2，平局选较高阈值。没有适用正/负样本、所有 score 不可分或标签不足时 threshold=null，不制造常数。

阈值冻结后对 holdout_groups 仅评估一次。每 detector 报 TP/FP/TN/FN、条件 FPR/FNR/precision/recall、有效覆盖率、弃权数、按六题材和 source scene 分层结果、比例的95% Wilson区间；分母0输出 null。异常上的弃权同时计入端到端漏检，不能只报“可比子集”掩盖弃权。六类主 detector 均需实际评估记录；最低可用性为校准和留出 balanced error 都严格小于常量预测的 .5，且每个 split 的正、负类各覆盖至少6个独立 source scene、六题材均有有效样本。否则该 detector disabled，保留失效原因与实测结果；不据此宣称生产准确率达标。

Profile 精确顶层：`schema_version, algorithm, parameters_sha256, dependency_fingerprint, corpus, labels, split_sha256, thresholds, purpose, status, applicability, detectors, calibration_metrics, holdout_metrics, limitations, created_at`。corpus/labels/thresholds均为FileIdentity；split_sha256仅绑定明确分组列表及source身份。purpose 为 real_benchmark 或 fixture_only；status 为 ready/partial/unverified。detectors 行精确 `{detector_id, threshold, enabled, calibration_groups, holdout_groups, reason}`；metrics 行精确 `{detector_id, overall, strata}`，overall/strata 的每组精确 `{group, tp, fp, tn, fn, abstained_positive, abstained_negative, not_comparable, unverified, fpr, fnr, precision, recall, end_to_end_recall, coverage, wilson}`；wilson 精确 `{fpr, fnr, precision, recall, coverage}`，每项为两元素区间或 null。

applicability精确 `{genres, source_kinds, source_fps, analysis_space, comparison_kinds}`；genres/source_kinds分别取校准和留出均有有效已标注样本的枚举交集，source_fps为两组均观测到的最简 `{num,den}` 列表，不填连续区间假称覆盖未见时基；analysis_space固定srgb_rgb24_v1；comparison_kinds为两组实际有效比较类型的交集。普通manifest必须声明domain，不能从人/动物像素或文件名猜；unspecified或未覆盖字段输出out_of_calibration_scope，仍保留原始测量，不应用阈值。控制变体继承原素材source_kind且另存控制provenance，不把captured基准冒充已经验证generated域。真实素材可来自既有本地生成输出，但本任务不为补题材自动推理。

主分析仅接受 algorithm/parameters/dependencies 完全相符且 purpose=real_benchmark 的 profile；partial 只启用其中满足条件的 detector，其余 unverified；没有覆盖的题材/输入域声明 out_of_calibration_scope，不能自动扩大适用范围。fixture_only 只验证软件，不可用于普通分析报告的告警。profile 存 `logs/continuity/calibration/profile.json`，完整目录/标注身份、recipe 和逐 case 指标另存同目录，exclusive 创建。数据不足时报告 unverified/partial，不把“跑完代码”当任务真实校准完成；VCO-03 全部完成需要六类主 detector 的 ready profile 与留出记录，否则如实交付部分和缺口。

校准的辅助JSON也冻结结构：`catalog-snapshot.json`精确 `{schema_version, catalog_identity, catalog}`；`labels-snapshot.json`精确 `{schema_version, labels_identity, labels}`；`case-results.json`精确 `{schema_version, algorithm, corpus_sha256, labels_sha256, cases}`，cases行精确 `{case_id, source_id, scene_group, split, control, metrics, metric_digest, labels, detector_results}`，control为上述ControlCase的FileIdentity，metrics为该case的metrics.json身份，labels为实际使用的标签entry列表，detector_results复用report.detectors精确结构。这里保存封存阈值下的原始实验预测，不根据最终profile的enabled状态回写预测或混淆矩阵，以免评估循环。`evaluation.json`精确 `{schema_version, algorithm, profile_sha256, case_results, calibration_metrics, holdout_metrics, domain_coverage, limitations}`；case_results为上述文件身份，domain_coverage复用applicability，其余复用profile对应结构。高层校验器可读取整份标签来检查结构/来源，但拟合函数只能收到calibration组的case score/标签，不能获得holdout行；生成holdout控制输入不等于允许用其调阈值。候选阈值先写入exclusive的`thresholds.json`，精确 `{schema_version, algorithm, calibration_groups, thresholds}`，thresholds行精确 `{detector_id, threshold, reason}`；最终profile以thresholds身份绑定这一步。封存后才计算holdout score、评估一次并输出最终profile，测试须断言拟合器从未收到holdout行。

### 9. 操作入口、性能与失败规则

新增离线 `scripts/continuity_audit.py`，只提供 `validate-catalog`、`annotation-template`、`calibrate`、`analyze` 四子命令；所有输入用显式 `--config/--manifest/--catalog/--labels` 绝对路径，不接收通配符/URL/“最新run”。输出新 audit 路径和状态 JSON；返回码0表示命令成功保存诊断，2表示结构/路径/依赖/漂移拒绝，3表示数据不足或不适用，124表示超时。candidate 不等于程序失败或生产拒绝。主生产 CLI/options/graph 均不扩展。

一次分析只读一次唯一输入闭包，结束做一次 SHA 复核；每 clip 工作缓存保留特征/小尺寸 RGB，避免反复读整段；纯数学结果不依赖命令启动数。单命令预算300秒、校准总预算600秒，命令/数据准备显式独立运行，超时保留 TimeoutError/原证据，不自动后台重启。单位测试不执行24-source采集或真实校准，不跑旧200帧生产 pipeline 来验证一个局部指标。

结构/引用环/重复 ID/非法标注 ValueError；字节或工具/包漂移 OSError；可选依赖缺失或 OpenCV 执行失败 RuntimeError；不可靠匹配是正常 not_comparable/unverified，不抛为技术视频失败。任何异常均不得修改源媒体或生产状态，未完成的 report/profile 不登记成功。

## Files

| 文件 | 责任 |
|---|---|
| `pyproject.toml` | 仅增加 continuity 可选 extra |
| `src/video_ai/media/colorimetry.py` | 提取可复用只读校验核心，增加批量证据读取；既有四接口/输出不变 |
| `src/video_ai/media/continuity_analysis.py` | 输入校验、光流/区域/色彩/轨迹、score、只读 audit 报告 |
| `src/video_ai/media/continuity_calibration.py` | 目录/标注模板、控制配方、source分组、拟合与一次留出评估 |
| `scripts/continuity_audit.py` | 四个显式离线子命令，不接生产准入 |
| `tests/continuity_helpers.py` | 小尺寸确定性纹理/运动/颜色 fixture；明确 fixture_only |
| `tests/unit/test_continuity_analysis.py` | 配准/色彩/时序/拒绝与精确 schema |
| `tests/unit/test_continuity_calibration.py` | 防泄漏、未标注拒绝、拟合/平局/禁用/评估与弃权分母 |
| `tests/integration/test_continuity_analysis_flow.py` | 真实 CPU FFmpeg→VCO-02→只读批量读取→独立报告及原件不变 |
| `tests/unit/test_colorimetry.py` | 增补只读 loader、缓存边界、伪造/同stat漂移回归 |
| `docs/task-designs/VCO-03-verification.md` | 实施时记录真实命令/源码身份、样本/标签来源、校准结果和限制；本次不创建通过记录 |

真实 catalog、labels、profile 和证据在 D:/VideoSi 的显式输入/audit 目录，不将私人/大体积媒体提交仓库。VCO-04 的 `runtime/scene_continuity_records.py` 和生产观察/恢复实现不在本任务修改。

## Tests

本轮仅设计；实施时先写 RED：伪造 raw/profile/映射不能形成 comparable，未安装 extra 明确拒绝；再实现只读批量入口和核心测量。每个测试文件 basename 唯一。依赖安装是实施步骤，本轮未执行；用既有 bootstrap 将包缓存/环境限定在 D:/VideoSi：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco03-dependencies'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pip','install','-e','.[dev,continuity]')
exit $VideoAiExitCode
```

定向 RED/GREEN/最终检查均在仓库根执行，使用各次独立缓存；最终范围固定如下，不启动全库：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco03-targeted'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest','-v',
 'tests/unit/test_continuity_analysis.py','tests/unit/test_continuity_calibration.py',
 'tests/integration/test_continuity_analysis_flow.py','tests/unit/test_colorimetry.py',
 'tests/integration/test_colorimetry_flow.py',
 '-o',"cache_dir=D:/VideoSi/cache/video-ai/temp/vco03-cache-$VideoAiCommandId",
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco03-targeted-$VideoAiCommandId")
exit $VideoAiExitCode
```

预计退出0；不得以缺依赖 skip 代替通过。验收覆盖：

1. 批量 reader 无 RunLogger/文件/锁创建、同资产只导出一次、唯一源/工具哈希数量不随帧数线性增长；修改原 PNG profile/sidecar/命令/pixels，同 stat 字节漂移均拒绝；旧 VCO-02 schema/结果精确不变。
2. 独立解析公式的 sRGB黑/白/灰、D65 Lab、ΔE76对称/零点；不能用被测函数生成 expected。纹理区域局部色变在全图均值相近时仍有区域证据。
3. 已知平移/旋转/缩放的纹理场景：光流/主体/相机分别定位；不同内容/遮挡/无纹理/出框丢失正确弃权，不能输出伪造色差或动作失败。
4. seam基线、渐进亮度/色度、三段累计、突发动作/相机重置均定位到正确 frame/region；允许的日落、阴影、zoom保留声明与来源；缺声明不凭全图差异断言原因。
5. 原生PTS与全局16fps坐标分开；对子片丢弃头帧、重复时点、缺帧、same_frame映射伪造、跨不同clip同索引、无参考等分别拒绝或unverified。
6. 校准按scene分组，不按帧泄漏；同媒体/衍生跨split拒绝；空标签/未实际播放/单人代双人/分歧未裁定不能形成ready；fixture_only不能用于普通报告。对字面已知score表验证候选中点、严格大于、平局取高阈值、分母0/null、Wilson边界、异常弃权计漏检。
7. 整套最小集成仅小尺寸64×36、每clip最多8帧、三段总24帧；一个真实 MP4 带完整显式SDR标签和至少一个 sRGB PNG。逐文件检查源run/audit bytes/mtime/SHA，报告写新run；不给新模型/服务/网络/GPU任何调用入口。
8. 构造失效profile、包/算法SHA漂移、共享预算耗尽、路径别名、重复输出和OpenCV失败，检查无成功报告；检查线程设置和父进程环境在成功/异常后均恢复。
9. 同一输入按不同cache预算/LRU逐出顺序测量得到相同metric_digest；大尺寸/JSON/帧数/比较数超预算须在分配前拒绝；禁止loader返回全片full-resolution bytes。控制通道重播只改变display_map，不改变原source PTS；普通manifest伪装benchmark_control拒绝。未来truth路径在measure阶段设置为不可读仍可完成计算，控制构造/评估读truth各有明确访问记录。
10. 构造多个ROI与不同detector的同帧context，只屏蔽显式指定项；验证报告分项/流向量/pair文件无遗漏，跨分辨率归一化坐标/最近邻patch去重/未裁subject框/极分解角度有字面expected；manifest缺domain或profile无该genre/source_kind/fps/比较类型时不应用阈值。

真实样本校准是独立的显式实施验收，不藏进 pytest。验证文档必须分别报告软件检查与真实24-source/240-case标注/评估；未采集或未标注就如实未完成。**用户已规定裸全库回归仅在项目最后一个任务统一执行，本任务不执行，不自动恢复 VCO-02 已停止的全库 worker。**

## Acceptance

### 当前AI路线验收（2026-10-26，取代原人审协议作为主任务完成门槛）

1. 已交付只读分析器、六类分数、控制构造/拟合/评估入口，兼容及定向检查结果可追溯；未知颜色、弱匹配、未校准和不可比保持真实，不自动声明视觉passed。
2. 用户选择的AI输入、弱标签、来源、分组、代码与参数先冻结，校准后封存阈值，再对预定检查来源执行一次评估；全部预定位置有完整结果或明确失败/弃权，允许null及原因，不要求人为凑齐六项ready。
3. 四项既有sRGB色彩结果与两项编码Y几何结果集中交付，逐项保留来源、分析域、实际分母、混淆矩阵、覆盖及限制，不合并为统一准确率或统一生产阈值。详见 [AI持续完成契约](VCO-03-AI-completion.md) 和 [六项交付](../task-handoffs/VCO-03-AI-final-results.md)。
4. 动作时间片段重播补充有真实录制序列控制、冻结后3个此前未测来源的一次检查、90项完整结果和原始producer证据；62项定向检查及6252个显示ROI帧摘要核验已交付，相关变体不冒充独立来源，弃权和未确认标签明确区分。详见 [重播补充交付](../task-handoffs/VCO-03-temporal-replay-results.md)。
5. 独立审阅及重要问题处置、完整输入/producer/阈值闭包与历史产物保留有证据；AI作者不冒充真人，实验profile保持production_eligible=false、普通profile校验拒绝，未擅自启动生成/发布或后续任务。

以上五项结果均已在所链接交付及其核验文件留证。主任务可登记COMPLETED；原正式Benchmark未验收和生产能力限制作为明确限制保留，不再使该任务显示BLOCKED。全库仍按原约定留在VCO-08，本次状态核对不重跑实验或测试。

### 原正式Benchmark验收（历史协议，未宣称通过）

1. VCO-02 的真实分析空间和闭包身份被只读复核；未知颜色/映射、弱匹配、合理变化均有明确可比性与原因，源片、原始 PTS、生产接口不变。
2. 合成接缝、局部色偏、渐变、三段累计和运动重置能输出区域/帧级证据；相机运动与主体相对运动分开，无可靠支持时弃权，不能只看全图 MAE/直方图。
3. 报告完整绑定输入/依赖/参数/profile SHA、比较帧、两种时间坐标、支持度及证据图；冻结输入可复算。无质量 passed、无自动校色/重生成或生产准入。
4. 24个真实独立 source 的六题材目录、12/12分组、240控制case、完整双人观看标注与分歧裁定、六个主 detector 的实际校准与一次留出评估齐全；无可用性证据则仅部分完成，不把 fixture 或历史白鹭单例当真实跨题材通过。
5. 本任务定向命令退出0，原件不变/失败路径有实际证据。全库执行留到最后一个任务，不以未跑全库阻止本任务按上述范围验收。

## Risks

### 2026-10-25 原生时间与已确认局部目标兼容修订

本修订用于继续用户已授权的剩余清单，不改变变换幅度、检测算法、24源/双人标注门槛。source 可额外包含 `control_targets`，其键只能是 occlusion / local_color，值精确为 `{region_ids, authorization}`：非空、无重复的 subject ID 列表及真实说明的 FileIdentity。不提供时沿用全部 subject；提供时须在生成任何控制像素前核验授权身份和区域，构造、校准、profile 复核共同重放同一选择。选择随 catalog 参与 corpus SHA，修改选择必须重新绑定标签；不得读取最终标签决定目标。occlusion context 只声明所选区域，并引用授权。原有精确 source 字段仍必需，其他未知字段继续拒绝。

校准连续区间允许严格递增但不等间隔的原生 PTS。所列原帧必须与已验证 sidecar 的连续索引/PTS/time_base 一致；半开结束边界必须等于下一原帧 PTS，若到达文件末尾，则使用最后一帧明确的正 duration / pkt_duration（同时存在时必须一致）。缺末尾时长不得猜测或外推。控制 display_map 和 source PTS 均不改写。profile 的 source_fps 对不等间隔源保存实际相邻 PTS 间隔倒数的最简分数集合，校准、封存证据复核和普通分析使用同一约定；这是观测到的时间步长覆盖范围，不宣称恒定帧率或插帧支持。

这些代码修复改变源码依赖身份，旧软件身份快照保留为历史；已有原片、RGB、已确认审阅视频不覆盖。重建结果须逐帧验证与已审材料的 RGB 相同，之后才能复用该材料开展正式标注。仍不自动启动真实拟合或留出评估。

- 真实素材和人工标签尚未采集；本次设计冻结了获取/标注协议，未声称已有24 source或任何校准结果。实现可以从只读加载器与小fixture开始，真实校准完成依赖人工按协议供给和观看材料。
- ROI身份由明确人工声明，光流不是语义主体识别；大形变、低纹理、遮挡和跨大视角可能大量弃权。必须报告覆盖率与弃权漏检，不能为了数字好看降低匹配支持门槛。
- 240 case 源自24 source，独立单位仍只有24；控制变体和小留出集不能证明任意模型、题材或镜头均可靠。profile范围明确为该基准，并保存分层误报/漏报与区间。
- OpenCV/NumPy与CPU构建差异会改变边界数值；版本、包文件、build information和参数参与身份，变更重新校准。实际安装/CPU smoke test尚待实施，当前只核对了wheel元数据。
- 历史MP4/PNG可能unknown；不强制贴标签或绕过VCO-02生成测量值。依赖数据不适用时保持unverified，不通过额外推理补齐。
- 不存在需要下一实施者自行决定的接口、算法路线、样本协议、拟合/评估规则或测试范围；实际阈值与准确率是实施实验的输出，不能在设计阶段编造。

独立可实施性审查已完成一次：提出控制通道、context定域、输出schema、像素/几何定义、真值隔离、内存上界和profile适用域七项问题；上述细化逐项解决，没有新增用户意图问题。版本固定、保守配准门槛、24-source规模及12/12分组是本设计的工程选择；它们不等于既有实测结果或通用质量保证。


### 2026-10-25 clip起点anchor与运动证据分离修正

每clip起点anchor用于该帧ROI身份、颜色采样及随后clip的跟踪坐标。其中心相对前段传播框的修订量不是图像运动。配准成功的当前帧对，运动位移一律取左框中心经该对subject仿射后的位移，并减去同点背景相机预测；实际dt、窗口和MAD公式保持。报告box/center继续表示声明/传播的跟踪框，因此在显式重置时不能再由相邻sample.center差反推测得速度，须查对应pair的affine。配准失败不由anchor补造速度，无背景时相对速度仍null。此修复恢复第4节的像素对应约定；matching参数、schema及ALGORITHM不变，源码依赖指纹变化使旧profile失配，正式校准仍须重做。
