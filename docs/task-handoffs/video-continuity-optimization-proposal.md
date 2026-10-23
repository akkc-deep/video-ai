# video-ai：视频连续性与色彩稳定性通用优化方案

> **性质**：技术方案、后续任务拆分依据。**不是已执行的实施计划**。  
> **日期**：2026-10-23  
> **基线仓库**：`akkc-deep/video-ai`，`main`，提交 `e8c05efe59c8fc7b1b201d7418a5cbea8de80fb4`  
> **拟存放位置**：`docs/task-designs/video-continuity-optimization-proposal.md`  
> **状态**：待入库、待评审、待拆分任务；没有改动生产代码、历史运行或任务板。

## 1. 问题与目标

当一个20秒或更长的连续镜头被分割成几个短视频时，现有方案用父片最后保留帧作为子片的起始图。首帧可能接近，但后续画面出现偏色、曝光变化、主体材质或动作变化；多次续写还会累积偏移。

区分三种异常：①父子接缝立即跳变；②子片开始正确但内部持续漂移；③多段续写累积偏离最初的主体/环境基准。还须排除颜色差异来自 MP4 解码、裁片、超分、色彩元数据或最终编码，而不是生成模型。

目标是建设**模型无关的连续性诊断与质量控制层**，配合模型特定的生成策略，减少没有剧情依据的色彩、动作与镜头变化。应允许日落、阴影、灯光切换和真实运镜导致的正常变化，不能把所有画面冻结成同一颜色。

## 2. 仓库现状与已有证据

### 2.1 正式生产链不是单纯 Wan2.1

`config/production.example.json` 和 `src/video_ai/runtime/production_visual_templates.py` 显示：正式生产是 Wan2.2 I2V 14B 高/低噪声双专家工作流，使用 Wan2.1 VAE，原生16fps，常用768×432；之后使用 RealESRGAN 逐帧超分至1080p。Wan2.1 VACE 14B、SVI、SkyReels-V3、FramePack-F1 等是单独试验，不等于已切换正式生产后端。

### 2.2 已证实的问题

- `src/video_ai/planning/scene_clip_continuation.py` 中，同一场景的片段复用 `motion_prompt`，并附加 `VISUAL_BIBLE_JSON` 正向提示。续段可能重复解释整个场景动作，且把追溯用 JSON 与模型视觉指令混杂。
- `src/video_ai/runtime/scene_clip_records.py` 的 `graph_for()` 真实 ComfyUI 条件主要只有 `start_image`、文本、长宽、帧数、fps、seed；`comparison_images` 只是记录，**不能据此说已作为模型参考图输入**。
- `src/video_ai/runtime/production_scene_clips.py` 可靠地从原始 `generated.mp4` 提取真正保留的最后一帧；此前父末PNG与子起始PNG的 SHA 相同，排除了拿错图，却没有解决生成时的漂移。
- `src/video_ai/media/video.py` 现有校验涵盖解码帧数、时间戳、尺寸等，缺少独立、完整的 `color_space / color_primaries / color_transfer / color_range` 诊断证据。
- `src/video_ai/runtime/scene_clip_observations.py` 已有 `color_clothing`、`time_lighting`、`motion_process`、`parent_join` 等观察字段，缺少可复现的自动连续性分析；人工/具备实际播放能力的观察门槛不能被自动分数代替。

### 2.3 不重复已失败试验

`docs/task-designs/JIM-08-continuity-diagnosis.md`、`JIM-08-continuity-repair-proposal.md` 记录了 9 帧历史条件、latent 锁定、VACE、SVI 和 F1 试验未能证实达到所需的动态/色彩一致性。因此不得将“固定seed、多帧条件、切FP16、改CFG、启用VACE、全局去红/去蓝”单独宣传为可靠修复。

`docs/task-designs/JIM-08-color-repair-design.md` 已经提出**版本化片段视觉提示 → 隔离单次20秒验证 → 验证后才集成生产模式**。本文件扩展它的通用检测、可选修复和长期架构；避免发明第二套互相冲突的提示契约。`JIM-08-whole-scene-proposal.md` 已指出整段生成不适用于任意长度，不可拿短镜头通过替代连续多窗续写验收。

## 3. 总体架构

```text
完整原文 / 已接受图片 / 视觉设定 / 音频时间轴
  ↓
片段级视觉提示契约：外观、材质、环境、动作、运镜、合理变化
  ↓
生成策略（只有经过真实验证的模式才能生产启用）
  ├─ segmented_v1：旧单尾帧I2V，严格兼容
  ├─ whole_scene_v1：经资源与画质验证后的一次整段生成
  └─ temporal_extension_v1：未来原生视频续写后端（待验证）
  ↓
原始生成视频 + 精确帧映射 + SHA / 视频色彩元数据
  ↓
Continuity Analysis：接缝、片内、长链、颜色、主体、动作、编码
  ├─ 可接受 → 进入原有实际视频观察
  ├─ 不确定 → 标记并请求真实动态观察
  ├─ 轻微偏色 → 可选独立校色候选 → 再检测与观察
  └─ 结构/动作或重大颜色异常 → 保留失败、停止或显式重生成修订
  ↓
已验收视频 → 逐帧超分 → 合成PCM/字幕 → 最终完整观看 → 发布
```

**原则**：先修正生成输入，后定位异常；自动诊断与自动修复分离；绝不覆盖原片。所有行为应基于已冻结输入及独立的可恢复/审计证据。模型条件协议因后端而异，不能给不支持多帧/参考图的 Wan 图随意加参数。

## 4. 方向 A：版本化视觉提示契约（P0）

**直接复用** `JIM-08-color-repair-design.md` 阶段 A 的字段、SHA、来源绑定、人工文本审查及修订失效设计。

- 将 `source_facts`、审计 JSON、原文定位和其他 scene 动作留在证据层，不塞进 positive prompt。
- clip 级单独表达 `motion`、`camera`、`lighting`、经来源证明的 `changes`；首片从选定原图当前姿态开始，续片从父片当时实际状态延续，不能重新讲述起飞、加速等完整过程。
- 仅使用本 scene 的稳定外观/场景关系和经核验视觉风格，允许原文明确要求的自然光照和材质变化。
- 真实模型参考图片必须经过实际 workflow 节点的支持及实验核验；审计用 comparison_images 与模型条件分开表示。

**建议文件**：
- 修改 `src/video_ai/planning/scene_clip_continuation.py`、`src/video_ai/runtime/scene_clip_records.py`。
- 按既有设计新增 `src/video_ai/planning/scene_video_prompts.py`、`src/video_ai/runtime/scene_video_prompt_records.py`。
- 关联 `src/video_ai/config.py`、`src/video_ai/runtime/production_inputs.py`、`src/video_ai/planning/scene_revision.py` 与恢复层。

**验收**：新模式只提交场景和片段相关提示；旧配置、旧冻结 run 的 options、graph、请求和恢复原样。提示契约变化只使相关视频及后代失效，不重复生成可以继承的已接受图、原文、PCM和字幕。软件测试通过不代表视频颜色通过。

## 5. 方向 B：原生色彩空间及编码链诊断（P0）

为 `generated.mp4`、原生尾帧PNG、裁片 `source.mp4`、超分帧、最终成片保存颜色诊断侧车（sidecar），主要记录 ffprobe 的 color_space、color_primaries、color_transfer、color_range、pix_fmt、编码器及解码/转换规则。

- 使用实际解码帧和明确记录的统一分析空间比较，不把 RGB 的数值差异与 JPEG/H.264 压缩损失直接当成模型漂移。
- 当元数据缺失或不一致时报告 `unknown` 和风险，不强猜 Rec.709；仅更改 metadata 标签不是正确的色彩转换。
- SDR/Rec.709 目标的编码/矩阵、范围应在确认源解释后规范，处理前后逐帧验证时间戳、尺寸和帧数。
- 初期不改变旧 `validate_video_probe()` 的严格返回字段契约，以独立旁路诊断避免破坏旧媒体记录重放。

**建议新增** `src/video_ai/media/colorimetry.py`；审查 `src/video_ai/media/video.py`、`frames.py`、`composition_video.py` 及相应单测。

**验收**：可查明差异发生于模型原始输出或某一编码/解码步骤；不同色彩标记、未标记 full/limited range 及往返转换样例通过；原生16fps、PTS、精确帧映射不变。

## 6. 方向 C：通用连续性诊断（P1）

对父/子视频及同一场景的所有片段生成**只读诊断报告**。检测输出不等于批准。

1. **接缝**：比较父片末尾正常帧间变化与父末帧→子片首个实际保留帧；MAE 只是诊断，不单独判通过。
2. **片内颜色漂移**：记录分段/逐帧亮度、色度、饱和度、高光/暗部剪切，分析由暖变冷、变暗、偏红等趋势。
3. **长链累计**：针对可匹配的同一主体/环境区域，与已接受原始参考及之前稳定片段对比，避免逐段复用已偏移颜色。
4. **动作与构图**：光流、主体位置/跟踪、镜头轨迹、边界出框、突发动作重置等，分别记录外观与动态异常。
5. **合理内容变化**：日落、进入阴影、变焦、出现新背景、遮挡或像素区域不匹配时输出 `not_comparable` / `unverified`，不使用全图直方图硬判。

计算可用 Lab/ΔE2000、稳定区域的亮度/色度、光流等，但**只有可对齐的同一内容才可进行配对颜色比较**。检测阈值、修复幅度与告警规则应由多题材标注样本校准，不能随便发明全局阈值。

**建议新增**：`src/video_ai/media/continuity_analysis.py`（算法）、`src/video_ai/runtime/scene_continuity_records.py`（输入SHA、算法版本、对比帧编号、报告与恢复）。接入 `production_scene_clips.py` 现有观察链，保留人工/动态 agent 审查。

**验收**：合成接缝跳变、片内渐变、多段累积漂移被发现；自然光照/运镜/遮挡不被当成必然错误；报告含可比性、置信度、时间戳、原始 SHA 和证据帧；结果可复算，不自动宣称动态通过。

## 7. 方向 D：轻度、可选、非破坏性校色（P2）

**默认关闭**。仅当主体/运动完整、仅出现轻微可定位偏色时，依据可匹配的稳定区域估计受限曝光/白平衡/色度变换；在时间轴上平滑参数防止闪烁，并明确修正强度上限。不得强制全幅直方图匹配、每帧独立重调或冻结背景。

生成独立修复候选，保存原片、修复片、参考身份SHA、算法版本、校色参数、前后报告。修复后重做原生帧/PTS、颜色和实际完整视频观察。若后续续写要以修复片作参考，必须新建明确修订及父子血缘，不能悄悄替换旧已接受片段。

**建议新增**：`src/video_ai/media/color_repair.py`、`src/video_ai/runtime/scene_color_repair_records.py`，关联修订、源片、超分、合成及恢复机制。

**验收**：轻度色偏改善且无新的频闪/材质失真；不可比内容不自动修；已接受原片不被改写，修复失败可回退原始证据。

## 8. 方向 E：长镜头生成策略（独立验证后集成）

不能简单解除现有 `plan_scene_clips()` 的时间切片预算和 `scene_clip_continuation.py` 中 `generated_frames <= 96` 的 guard。这些与请求帧数、裁剪、映射、超分、合成、失效和恢复存在跨模块依赖。

| 候选模式 | 适用场景 | 前提与约束 |
|---|---|---|
| `segmented_v1` | 现有兼容模式 | 保留末帧I2V和旧96帧预算，不宣称稳定续写 |
| `whole_scene_v1` | 可用模型一次生成稳定短/中镜头 | 完整动态观察、显存与时间预算实际通过后才能生产集成 |
| `temporal_extension_v1` | 真正需要跨窗口一镜到底 | 后端原生支持时序上下文，需独立视频效果验证，不能把历史失败方案改名 |
| 语义切镜（独立选项） | 剧情允许合理镜头切换 | 不冒充用户要求的一镜到底；镜头间外观也须一致 |

按既有 `JIM-08-color-repair-design.md` 阶段 B：隔离请求 **321 原生生成帧**，精确保留 `[0,320)`，获得20秒/16fps 样片，记录完整模型/graph/input、GPU与内存、推理日志、样片SHA、实际完整播放结果。该预算**尚未证明 RTX5090D V2 24GB 环境能正常生成**。失败就保留证据，不偷偷降低分辨率、改帧率、截短、插帧、变速或反复提交。

长镜头跨窗口模式需要：后端真实时序条件协议、历史帧和新增帧分别计数、历史只输出一次、精确镜头时基、外观和镜头状态的可验证延续。既有 VACE、9帧历史和 SVI/F1 失败结论不可自动判成功。不同后端24/30fps与正式16fps不同，必须显式时基适配且保留完整时长。

**潜在修改**：`src/video_ai/planning/production_visual_plan.py`、`scene_clip_continuation.py`、`runtime/scene_clip_records.py`、`production_scene_clips.py`、`production_scene_upscale.py`、`production_scene_composition.py`、配置、workflow、revision、recovery以及相关测试。新模式应以版本化预算、独立身份与失效图接入；旧 run 严格继续原 graph。

## 9. 统一质量门槛与版本化恢复

建议依序验证：视觉输入身份 → 技术视频有效与原生颜色元数据报告 → 机器连续性诊断 → 实际完整视频观察 → 超分合成与最终完整审查 → 显式发布。

- 技术通过、算法诊断通过、静帧采样通过均不能自动升级为视频外观通过。
- `failed`、`unverified`、无可比区域、缺少有效观察结果都不能记为 `passed`。
- 改提示或生成后端：受影响片段及其后代视频、观察、超分/合成/交付失效；可合法继承原文、PCM、视觉设定与已接受图片。
- 仅改诊断算法：原始模型视频不重复生成，但报告及其准入需重算。
- 改校色处理：只影响修复候选及其依赖；原视频保持不变。
- 不明模型任务结果：沿已有 request/prompt_id/HTTP 记录恢复，不重复 POST，不无授权发起GPU/付费试验。
- 保存 SHA、算法/模型/工作流版本、时间、原始媒体/新媒体与观察身份；避免破坏旧冻结 run。
- 既有工作区曾有大量未提交变更，后续实施不得 reset/revert、批量暂存或覆盖未知改动。

## 10. 测试与验收矩阵

| 类别 | 必须覆盖的场景 | 通过依据 |
|---|---|---|
| 色彩链 | Rec.709及不同色彩元数据、full/limited与未标记数据、解码/编码往返 | 归因清楚，unknown保留，时基帧数一致 |
| 接缝 | 只变亮度、只变色度、主体局部变化 | 定位准确，不只靠全幅MAE |
| 片内与长链 | 几秒渐进偏色、三段逐次偏移 | 检测漂移来源和累积趋势 |
| 合理变化 | 日落、进入阴影、运镜转向树林、遮挡 | 不能一律自动判错 |
| 动作 | 突然重启、速度变化、主体出框、运镜跳变 | 不允许仅靠调色“修好” |
| 修复 | 轻度色温/曝光变化、已稳定原片、不可比背景 | 改善且不新增频闪，原片不变 |
| 恢复 | 旧冻结run、SHA漂移、未知提交、诊断算法变更 | 旧输入/graph不变、不会重复提交或发布 |
| 成片 | 16fps/帧映射、完整PCM/字幕、1080p成片 | 时长、帧数、音频样本与内容准确 |
| 真实跨题材 | 不同人物/动物/材质/环境和相机运动 | 实际完整播放、拒绝与通过均有证据 |

软件回归成功只能证明实现符合代码契约，不能证明模型视觉结果已经达到要求。整段20秒单案例通过也不能外推任意时长或任意题材。阈值和基准样本数量在后续专项任务中确定，不在方案里捏造数字。

## 11. 后续任务拆分建议（暂不创建任务编号）

| 顺序 | 独立交付 | 前置依赖 | 独立验证重点 |
|---|---|---|---|
| P0-A | JIM-08现有视觉提示契约落地 | `JIM-08-color-repair-design.md` | 提示纯视觉、逐clip变化依据、旧graph兼容与修订失效 |
| P0-B | 原生颜色元数据/编码链诊断 | 现有媒体校验 | 定位发生阶段，不修改旧结构/16fps |
| P1-A | 色彩/动作连续性分析器 | P0-B | 接缝、片内、长链、合理变化、不可比状态 |
| P1-B | 诊断报告接入观察/恢复门槛 | P1-A | 不自动假通过、不重复提交、失败保留 |
| P1-C | 单次20秒隔离真实生成及多题材验证 | P0-A | 模型资源、实际完整播放、技术/视觉分别验收 |
| P2-A | 轻度非破坏性校色与修订 | P1-A、P1-B | 不闪烁、不覆盖、不篡改父子血缘 |
| P2-B | 版本化整段生产模式 | P1-C真实通过 | 预算在所有消费者一致，旧模式零漂移回归 |
| P3 | 原生跨窗续写后端 | 有新的正式时序协议及真实试验后 | 动作/色彩/构图、时基、恢复、多窗口长链 |

每项后续具体任务应进一步冻结：输入输出接口、schema、准确源码路径、逐条可测验收标准、失败用例、RED/GREEN测试、恢复与真实GPU/动态观察关卡、可回滚策略。拆分前本文件只是技术范围和依赖地图，不替换用户现有 JIM-08 任务板状态。

## 12. 未决设计问题

1. 连续性诊断是否需 OpenCV/NumPy/光流模型，或可首先由现有FFmpeg/Python实现；以依赖规模与准确性取舍。
2. 稳定主体/背景区域的可比性、可解释光照变化、阈值及多题材样本如何标注与冻结。
3. 哪些中间步骤采用无损RGB，哪些采用H.264/yuv420p，以及 Rec.709/色域转换的准确策略。
4. 修复候选是否可以用于下代视频的模型输入；默认禁止，除非显式新修订与再次观察。
5. 整段候选未通过时是否测试新后端；必须另有模型依据、真实预算与授权，不进行无限随机试验。

## 13. 关联材料

- `docs/task-designs/JIM-08-color-repair-design.md`
- `docs/task-designs/JIM-08-continuity-diagnosis.md`
- `docs/task-designs/JIM-08-continuity-repair-proposal.md`
- `docs/task-designs/JIM-08-whole-scene-proposal.md`
- `docs/task-designs/JIM-08-industry-continuity-research.md`
- `docs/task-designs/JIM-08-verification.md`
- `docs/task-handoffs/JIM-08-handoff.md`
- 主要源码：`scene_clip_continuation.py`、`scene_clip_records.py`、`production_scene_clips.py`、`media/video.py`、`media/frames.py`、`media/composition_video.py`

**说明**：本文件根据GitHub仓库的只读源码和文档审查编制，并非对本机GPU/原视频或测试进行本次重新验证。文中“建议新增”的文件、模块与模式均未声称已经存在。
