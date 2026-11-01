# VCO-06 真实校色素材准备要求

> **最新可消费交付：** [正式研究输入交付](../task-handoffs/VCO-06-research-input-delivery.md)提供已被新入口实际验证的49帧纸质研究素材、全部97组比较及逐帧自然指标基线。它满足新研究输入读取阶段；旧v1候选请求及新自然校色propose仍不具资格。后文“新路线尚未实现”保留方案修订时快照，以该最新交付的实际实现范围为准；不得把研究输入就绪改写成校色候选就绪。

日期：2026-10-28。用途：交给另一个任务准备 VCO-06 可实际消费的素材和证据。本文件是配套输入要求，不替换 [VCO-06 实施契约](VCO-06-design.md)，不新增任务板编号，也不解除当前 BLOCKED 状态。

> **后续授权与适用范围：** 本文件下文是原 `research_candidate_v1` 的输入合同。用户在两次真实素材资格检查后明确回复“我我同意你修改方案”，新的研究导入、报告保存及自然适用性研究按 [修订设计](VCO-06-natural-input-design.md) 执行。原文“不得重校准/改阈值”“不改产品源码”继续保护旧v1/r2，但不再禁止另建必要研究接口、新协议与独立profile；不得修改旧profile、给旧失败改判或把新指标送入旧接口。新路线的准入状态和完整播放要求见修订设计。该授权不代表现有素材ready_for_propose，新路线也尚未实现或封存资格。

## Goal

交付 **1 组真实生成的原生视频、生成它时实际使用的原选图，以及完整来源、色彩、诊断和播放预检证据**，使 VCO-06 可以开始真实校色候选验证。

素材应当主体和动作完整，仅有轻微、可定位、适合一个恒定参数修正的曝光或单轴白平衡偏差。准备成功不等于校色成功；真正的改善和候选全片观看由 VCO-06 后续验收。

给执行任务的简短指令：

> 先在现有真实 run 中寻找符合本文件的完整原选图/原片组合，优先无父片的首段。先检查参考图色彩声明和真实来源，再投入全帧诊断。交付能通过现有接口校验的输入包；找不到就交付明确的缺项和证据，不合成偏色、不伪造记录、不改旧 run 来凑通过。需要新生成时先完成生成前检查，并按该任务已有的真实推理授权执行。

## Scope

包含素材选择、原选图色彩解释、原生视频/来源核验、当前诊断上下文与 assessment、独立修复配对 manifest、实际完整原片播放预检、可追溯交付索引和原件保护。

本任务的交付终点是“可以请求生成研究候选”。不要求准备任务生成修复后的 master/playback、填写候选 Review、启用生产校色、发布视频或完成 VCO-06。不得重校准、扩大合格方向或改检测/修复阈值。

本文件只编写要求，不执行素材准备或推理。后续执行任务是否获准新增 GPU/模型请求，以它实际获得的授权为准；已有明确授权不重复请求。仅有本文件不代表追加真实生成已获授权。

## Approach

### 1. 先读这些现有材料

1. [VCO-06 设计](VCO-06-design.md)，特别是第 4–7 节及 Acceptance。
2. [真实输入审计](../task-handoffs/VCO-06-real-input-audit.md)：了解现有白鹭和另外两个首段为什么未能准入。
3. [VCO-06 阻塞交接](../task-handoffs/VCO-06-handoff.md) 和 [操作说明](VCO-06-operations.md)。
4. [VCO-04 操作说明](VCO-04-operations.md)：新 run 的策略冻结、当前 epoch、assessment 和实际播放回应。
5. [封存校准结果](../task-handoffs/VCO-06-calibration-results.md)：只读使用现有 r2 profile，不重新拟合。

权威接口在以下源码；测试 helper 只能帮助理解结构，不能复制其中 fixture_only 的作者、观看文字、ROI 或结论：

- `src/video_ai/media/colorimetry.py`
- `src/video_ai/media/continuity_analysis.py`、`continuity_report.py`
- `src/video_ai/runtime/scene_clip_observations.py`
- `src/video_ai/runtime/scene_continuity_records.py`
- `src/video_ai/runtime/scene_color_repair_records.py`
- `src/video_ai/runtime/_scene_color_repair_validation.py`

### 2. 选择路线与执行顺序

| 顺序 | 做什么 | 通过后再做什么 | 不满足时 |
|---|---|---|---|
| 1 | 找真实、受现有生产记录支持的 run/clip 和实际原选图 | 读 PNG 声明、核验原选图身份 | 记录来源缺项；不把零散 MP4 包装成 clip |
| 2 | 用现有 VCO-02 实际检查原选图 | 检查完整原片的原生时间和颜色 | unknown/conflicting/unsupported 即停止该组后续准备 |
| 3 | 核验原片技术来源和实际完整播放 | 建立当前诊断和独立配对输入 | 结构、动作、频闪或合理光照变化不适用时换组 |
| 4 | 准备当前 assessment、真实 Precheck 和完整 pair manifest | 校验输入闭包、生成交付索引 | 明确未确认项；不写 ready_for_propose |
| 5 | 核对原件未变并交付 | 由 VCO-06 复核并显式恢复任务 | 准备任务不自行改 VCO-06 状态 |

优先复用已符合条件的真实素材。若现有素材均不合格，只能返回缺项，或在另有真实生成授权时建立新的、从创建前就具备完整色彩及诊断记录的 run。不能通过向旧冻结 options 补字段修复其来源。

### 3. 原选图的硬性要求

必须是目标 clip 的真实生成 request 中绑定的 `selected_image`，即模型生成这段视频之前实际使用的那张图。交付其原始路径、原字节 SHA256 和字节数，以及 request/选图记录对它的引用。

不能替换为视频首帧、从视频截取的“干净帧”、修复后的图、相似图片、另一张更漂亮的参考图或未来帧。

**当前代码支持的 PNG 分支很具体，不能只写“有 ICC 就行”：**

| 项目 | 目前可消费的要求 |
|---|---|
| 格式 | 真正的 PNG，实际 probe 为 `rgb24`，8-bit 三通道 RGB |
| sRGB | 文件有有效的 PNG `sRGB` chunk，`srgb_intent` 为 0–3 |
| gAMA | 可缺省；若存在，值必须为 45455，不能与 sRGB 冲突 |
| cHRM | 可缺省；若存在，必须为 `[31270,32900,64000,33000,30000,60000,15000,6000]` |
| iCCP/ICC | 当前 PNG 消费分支不支持，`icc_sha256` 必须为 null；仅带 ICC 而没有 sRGB chunk 不合格 |
| 解码 | 现有 `inspect_color_asset` 得到 `interpretation.status=resolved`；`decode_analysis_frame` 得到 `status=ready` 且 `pixels` 非 null |
| 身份 | 分析记录中的原图 bytes/SHA256 与 request.selected_image 完全相同 |

alpha、灰度、调色板、16-bit、HDR、未知传递函数或色彩声明冲突的图片，不应作为这一版的可用参考。文件扩展名和看起来颜色正常都不能证明 sRGB。

如果原文件名是 `.original`、内部确实是合格 PNG，可以另存**字节完全相同**的 `.png` 文件供工具识别；记录两者身份并证明 bytes/SHA256 相同。改名不会补足缺失的色彩声明。

**已有视频所绑定的原图不可事后重编码、加 sRGB 标签、去 ICC、调色或转换后再替换。** 这些操作改变原字节，不能满足旧 request 的选图身份。

如果另一个任务获准从头生成新视频，可以在生成前完成有依据的真实色彩转换或制作：已知源色彩解释 → 实际转换 → 产出本身具有正确声明的 RGB PNG → 保存输入/输出身份、工具和转换记录 → 冻结并实际将此 PNG 用作生成选图。不能给未知像素直接贴 sRGB 标签。最终交付参考必须是新视频真正使用的那份 PNG；这条路线不能补救旧视频的绑定。

### 4. 视频与来源记录的硬性要求

| 项目 | 要求 |
|---|---|
| 真实来源 | 现有生产协议能验证的真实原片；有实际 run/clip、模型 request、graph、generated、retained source、mapping、尾帧和原选图绑定 |
| 贡献媒体 | 使用原 clip 的 retained source，不拿有损审阅副本、超分片或合成成片替代 |
| 帧率 | 原生恒定 16/1，不能由 24/25/30fps 转换得到 |
| 时间 | 完整 F 帧，逐帧 PTS 与实际 time_base 对应 `i/16`，帧数、顺序和映射全部核对 |
| 内容 | 完整原贡献片，不剪掉坏帧、不截短、不插帧、不变速、不循环、不冻结背景 |
| 轨道 | 目标 source 只有视频轨道，没有音轨或辅助轨道；原工程音频/字幕单独保存 |
| 色彩 | 所有帧实际可解释为 sRGB；现有 repair 校验器必须接受，不能只看容器标签 |
| 分析 | 原片全部 retained 帧的 VCO-02 record 均 ready、有有效像素和真实映射；不能抽帧 |
| 原件 | 原片、请求、graph、mapping、尾帧和原有接受/拒绝观察保留原字节 |

现有可消费的视频编码分支为 8-bit YUV、BT.709 matrix/primaries，传递函数和范围须明确并受现有 VCO-02 支持；修复入口额外要求能证明 sRGB。仅有 BT.709 transfer 的普通观看片，不能因 VCO-02 能解码就宣称满足 repair 的 sRGB 门槛。以实际分析记录和 repair 输入校验结果为准。

任意外来 MP4、手机录像、独立试验产物即使颜色和帧率正确，也不自动具有当前接口所需的生产 clip 来源。不得为它手写假 Wan request/clip/ready receipt。若只能找到这类素材，交付为 material_only，明确需要另外的正式导入契约，不能宣称解除本任务阻塞。

没有要求一定用白鹭、20 秒或某一种题材。优先选择已有完整来源、无父片的首段，以减少祖先播放与来源依赖。新生成的长度应在生成前确定；不得事后裁短以通过检查。

### 5. 内容适用性与可操作方向

合适的内容：主体身份、结构和动作完整；图与视频有持续可匹配的稳定区域；曝光/白平衡偏差轻微，且大致恒定；原选图的颜色和照明明确是期望目标。

不适合的内容：主体变形、动作过程缺失或倒退、明显换装/材质变化、局部重染、频闪、随时间变化的色偏、混合多轴色偏、过曝/压黑造成信息损失、原文要求的日落/变光、镜头运动或遮挡使稳定区域失去配对支持。校色不得被用来解决这些缺陷。

当前封存结果只允许下面四个修复方向。这里的正负号是**施加的修复参数 a**，不是污染注入参数；文字描述只是选样参考，最终以 profile 和实际拟合为准。

| operation | 合格修复方向 | 选样时的直观参考 |
|---|---|---|
| exposure | a < 0 | 原片相对原图轻微偏亮，需整体降低曝光 |
| wb_r | a < 0 | 原片相对原图轻微偏红，需减弱红轴 |
| wb_g | a > 0 | 原片相对原图绿轴偏弱，需增强绿轴 |
| wb_g | a < 0 | 原片相对原图轻微偏绿，需减弱绿轴 |

实际幅度上限只读正式 r2 profile 的 `correction_amplitude_ceiling` 和 `qualified_directions`，不要手抄此表作为默认参数。wb_b、其他曝光/白平衡方向以及全部 chroma 不合格。作者明确选一个已知族/轴并说明依据，不能循环试几个算子挑最优，也不能为选样人工制造色偏。

原片已经稳定时，后续正常结果可能是 noop；无法匹配、幅度越界或方向不合格时应弃权。**noop、合成污染修复及分数下降均不能代替 VCO-06 所需的真实自然偏色改善证据。**

### 6. 当前 VCO-04 上下文与原片播放预检

交付目标 run 自己的冻结配置、当前完整 epoch/commit、目标 clip 的唯一 current assessment、其完整 manifest/report/producer/Engine 引用。

新 run 必须在创建前显式配置：

```json
"scene_continuity": {"schema_version": 1, "policy": "advisory_v1"}
```

仅修改当前全局配置不影响旧冻结 run。原 run `20261021-014723-4ebdc1fecab2` 保持只读，不能补写 options/policy 或把新诊断伪装成它原本已有的冻结记录。

原 assessment 按 VCO-04 的真实完整 same-scene prefix 规则建立。它的参考规则与下节独立校色配对不同，不能用校色配对报告替代 assessment。没有生产资格的检测 profile 可以保留机器 unverified；不得人为改成 machine passed。

必须有实际完整播放作者的原片 schema2 observation，再据此生成 `Precheck`。不要求新的人工校准表。可由 human_video，或确有完整播放能力的 agent_video 提供；逐帧图片检查、静帧 AI、自动分数和填模板均不算完整播放。

Precheck 精确字段沿用现有契约，不增加自定义字段：

```text
schema_version,run_id,clip_id,assessment,source_clip,video_observation,
reviewer,reviewed_at,color_issue,operation,operator_basis,
subject_structure_intact,motion_intact,intentional_lighting_change,responses
```

具体要求：

- `subject_structure_intact=true`、`motion_intact=true`、`intentional_lighting_change=false`，必须与实际观察、冻结原文/context 一致。
- `color_issue` 写明实际看到了什么轻微偏差、在哪些稳定材质/区域可见；不能只写“用于测试”。
- `operator_basis` 说明为何属于选定 operation，以及为什么独立原选图的颜色/照明是目标；与后续 request 完全一致。
- 原 observation 的身份、范围、原生时序、观看方式、作者和时间都有效。色彩检查可以 failed；非颜色检查须按协议 passed/合法不适用，不能隐藏 unknown 或 confirmed issue。
- `responses` 精确覆盖 current assessment 的每个 concern；只有颜色 concern 可以 confirmed_issue，其余须有实际完整播放否定或冻结原文的有效合理变化解释。未知风险不能写成通过。
- 保留所有历史失败。任何已确认的非颜色结构/动作缺陷都不能通过新 precheck、新 epoch 或继承新 run 清除。
- `reviewed_at` 带真实时区，不早于所引用的 assessment、实际播放记录及相关历史观察，不填未来时间。
- 若选择有父片的续段，提交完整同 scene 祖先链；祖先须有同一作者真实完整、passed 的播放证据。建议直接选无父片的首段降低准备成本。

无法获得实际完整播放时可交付技术素材和未确认说明，但不能生成已通过的 Precheck，也不能标记 ready_for_propose。

### 7. 独立原选图配对与全帧覆盖

必须准备两套用途不同的普通诊断输入：

1. 当前 VCO-04 assessment 的原片/前缀风险上下文。
2. 校色用独立原选图 → 原片每一帧的 pair manifest。

pair manifest 采用 existing ordinary schema1，精确遵循 VCO-06 第 5 节：

- `scope=clip`，scene/genre 与 current assessment 相同，`source_kind=generated`，timeline=16/1，`profile=null`。
- `clips` 恰好一个目标 clip，frames 与 assessment 中目标 clip 的全部 F 帧记录逐项相同。
- `references` 恰好一个，frame_id 固定为 `repair_clean_reference`；指向独立原选图的 VCO-02 analysis record。
- 所有 F−1 个 adjacent 排在前面，ID 为 `repair_adj_000001` 起；随后全部 F 个 reference，ID 为 `repair_ref_000000` 起，含视频第 0 帧。
- 每项 reference 的 left 均为独立原选图，right 为相应原生视频帧。adjacent/parent_join 不参与校色拟合。
- ROI 有真实作者、时间和稳定 region_id/role；每个区域同时有原选图和视频首保留帧的真实 anchor。只声明起点区域，由既有跟踪传播；不写未来 truth 坐标。
- comparisons 的 region_ids 为同一排序列表；不能每帧挑不同的“容易成功”区域。

独立 PNG 还需 source-bound mapping 证明，不能只写空 mapping。参考坐标表达“独立静态选图在声明参考时刻的位置”，不冒充模型生成帧：

```json
{
  "asset_frame_index": 0,
  "clip_id": "repair_reference_image",
  "generated_frame_index": null,
  "retained_frame_index": null,
  "output_frame_index": null,
  "pts": 0,
  "time_base": "1/16"
}
```

配套证明文件形状为 `{source: 原图真实FileIdentity, rows: [该行]}`，其内容与 VCO-02 entry.mapping 一致，并以真实文件身份列入 mapping.evidence。当前 API 将这种独立选图 entry 放在 `stage=native_tail`；这里仅是已有技术入口，文字说明和 null 索引必须保留“独立静态参考”的真实含义。代码范例在 `tests/scene_color_repair_helpers.py`，不得复制其 fixture 结论。

建议准备任务对 pair manifest 运行一次真实 ordinary 预审计，及早发现自然素材没有完整匹配支持的问题。若执行，必须完整验证报告闭包，记录所有 F 个 repair_ref_* 的 comparability 和去重配对点；后续拟合要求每帧 comparable 且至少 81 对，估计还有 informative 点要求。任何一帧失败都不能抽掉该帧或放宽几何阈值。

预审计报告只用作素材资格证据。正式 propose 仍须产生绑定自己 intent/producer 的 pair report，不能拿准备任务的报告冒充正式输出。没有预审计时明确登记“自然配对尚未测量”，不得宣称参考匹配已通过或保证候选可生成。

### 8. 资源、路径与数据保护

- 所有媒体和外来证据使用 `D:/VideoSi` 内明确绝对本地路径；不能使用 URL、latest、glob、符号/硬链接、junction 或其他路径别名。
- 原选图/原片等分析输入须位于本次独立 audit run 之外，诊断产物放到新的独立 audit run。
- 单 JSON ≤16MiB、同次解析 metadata ≤64MiB、原生帧数 ≤4096；普通分析器还限制 comparisons 数量。不能通过漏帧压缩证据。
- 单帧 RGB ≤32MiB、修复工作预算128MiB；原图可能大于视频，必须把原图解码内存纳入预检。
- 修复输出预检为 `3*F*width*height*3 + 512MiB`，须 ≤16GiB；这只是上限，不保证实际操作成功。
- 沿用300秒本地操作检查期限和原分析器限制，超限如实返回 resource_limit/timeout，不改大小、帧数或参数重试。
- 原始媒体、选图、请求、graph、mapping、原有接受/拒绝记录及历史生产文件不覆盖。诊断可在具备冻结策略的工作 run 按既有 RunLock/不可变事务追加，但须单列新增记录，不能伪称整个目录零变化。
- 旧受保护 run 要有前后文件清单、bytes/SHA256/mtime_ns 核对；如完全只读，应连文件集合也一致。新工作 run 则核对其既有原件未改，并清楚列出合法新增的诊断产物。
- 不改产品源码、校准冻结 software 或封存 profile；不安装新依赖、不运行全库回归、不发布、不改 .git。

## Files

准备任务建立一个新的、唯一的交付目录，例如：

```text
D:/VideoSi/projects/video-ai/vco06-input-preparation/<delivery-id>/
  README.md                    # 实际选样、已完成/未完成、交接入口
  delivery.json                # 可定位的权威文件索引
  protected-before.json        # 受保护原件的准备前身份
  protected-after.json         # 准备后身份与允许新增项
  qualification.json           # 各项实际检查结论及证据引用
  evidence/                    # 独立静态参考 mapping、ROI/context/manifest 等准备材料
  logs/                        # 命令、退出码、stdout/stderr、工具身份
  tools/                       # 如写了临时审计脚本，保存脚本原字节
```

`<delivery-id>` 使用新建的唯一标识，不覆盖旧交付。这里是建议的收集目录，不是新生产 run 或新 runtime schema；真实媒体和权威记录可以保留在原路径，由索引引用，不能随意搬文件破坏绝对路径绑定。

`delivery.json` 至少说明下列字段，所有文件引用用真实 `{path,bytes,sha256}`，实际 VCO-02 接口仍使用自己的五字段 FileIdentity，不混用两种结构：

| 字段 | 内容 |
|---|---|
| schema_version | 交付索引版本1，仅用于本准备包 |
| prepared_at / prepared_by | 真实带时区时间、实际执行者 |
| status | `material_only`、`ready_for_propose` 或 `blocked` |
| run_dir / clip_id | 真实可加载的目标 run 和准确 clip ID；缺失时不能 ready |
| source_records | selected_image、request、graph、clip、mapping、source、generated、last_frame 的权威引用 |
| reference_analysis | 原选图 sidecar、analysis record、mapping proof，以及存在时的字节相同 PNG 副本 |
| source_analysis | 全部原生分析记录/sidecar 的完整索引，不只列采样帧 |
| current_diagnostics | frozen policy、当前 epoch/commit、assessment、manifest、report 及完整闭包入口 |
| playback_precheck | 实际原片 observation、Precheck，及必要祖先的观察；未获得时为 null |
| repair_inputs | pair manifest、regions/context、指定 operation/basis、正式 r2 profile 引用；若已准备 request 也列其引用 |
| qualification | qualification.json 的引用，标明自然配对是已测量还是未测量 |
| preservation | 准备前后原件身份核对报告 |
| blockers | 每个缺项、确切原因和可定位证据；没有则空列表 |

不填写空作者、占位 SHA、虚构路径、未来时间或预先写 passed。机器可读索引不代表 runtime 已接受；真正 schema 与闭包仍由现有校验器判断。

README 必须让接手者直接找到：应使用哪个 run/clip、原选图在哪、原片在哪、实际缺陷是什么、选哪个 operation/为什么、谁完整播放过、当前 assessment/Precheck/pair manifest 在哪、哪些仍未验证，以及下一条实际可执行命令。

正式 profile 的权威根：

```text
D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2/
  experimental-repair-profile.json
```

只引用并验证其完整封存闭包；不复制一个精简 profile 冒充正式文件。

## Tests

这是素材资格核验，不重跑已经交付的364项软件用例，也不运行全库。保存实际执行命令、退出码、工具/输入身份及完整结果；下面命令中的变量由执行者填为本次真实绝对路径，不能原样交付占位值。

所有 Python 先 bootstrap，通过已有环境运行；检查串行执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-input-preparation'

# 查看目标 run 的当前诊断；只读，不会自动补 epoch/assessment。
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/scene_continuity_audit.py',
 'status','--run-dir',$ActualRunDirectory)

# 仅在具备冻结策略、真实完整 manifest 及合法分析请求时建立 assessment。
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/scene_continuity_audit.py',
 'analyze','--run-dir',$ActualRunDirectory,'--request',$ActualAnalysisRequest)

# 可选的独立配对预审计；不能代替正式 propose 的自有报告。
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/continuity_audit.py',
 'analyze','--config',$ActualConfigPath,'--manifest',$ActualPairManifest)
```

每条命令后立即记录 `$VideoAiExitCode`，不要用最后一条命令的退出码覆盖前面的失败。VCO-04 analyze 合法返回 awaiting_review/3；普通 profile=null 分析返回 unverified/3 是诚实的机器状态，不能改记为 machine passed。status 的0/3分别表示ready/等待，2表示拒绝或损坏；没有生产ready不等于色彩输入已经失败，须看确切原因。

参考图和全部原片帧必须实际调用 `inspect_color_asset` / `decode_analysis_frame`，再用 `load_color_analysis_set` 复核像素、来源与映射；现有命令没有一条“给图片加标签就完成准备”的捷径。准备任务可以用一次性脚本串接这些既有 API，但脚本、参数和日志必须随交付保存，不能导入测试 helper 产生真实记录。

应记录的可观察结果：

1. 原选图 `resolved`、分析 `ready`、pixels非null、真实SHA与selected_image相同；没有 unverified_mapping。
2. 视频所有 F 帧记录 ready，source/PTS/16fps/mapping精确，轨道符合要求。
3. 目标 run 能由 `load_frozen_inputs` 加载，生产原片来源可由既有 scene_context/collect_progress 核验；不能只有文件存在。
4. current assessment 唯一且绑定当前完整 epoch/目标原片；实际 observation 和 Precheck 通过现有字段/身份/时间/风险校验。
5. pair manifest 通过 ordinary schema 和 repair 的 `validate_pair_manifest` 校验；来源、完整帧序列、参考身份和资源预检有效。实际匹配支持是否已测量单独记录。
6. 原件准备前后核对通过。若有不一致，交付 blocked 并保留证据，不更新基线来掩盖。

若填写 `repair-request.json`，按 VCO-06 Request 精确 schema 使用新的规范 UUID、真实 current assessment/profile/manifest/Precheck，并通过现有 `validate_repair_request` 及当前绑定/历史风险核验；准备任务不调用 propose。接手的 VCO-06 任务在复核后才运行：

```powershell
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/scene_color_repair.py',
 'propose','--run-dir',$ActualRunDirectory,'--request',$ActualRepairRequest)
```

该命令属于后续候选生成，不是本准备任务的通过检查。成功可生成候选也仅为 awaiting_review/3；noop/abstained/0 不表示自然改善通过，failed/1、blocked/2、interrupted/130保留原始原因。

## Acceptance

准备任务完成并标记 `ready_for_propose` 的条件是：

- [ ] 一组真实、当前接口能核验完整生产来源的原片/原选图，不能只交两份松散媒体。
- [ ] 原选图本身符合当前 PNG sRGB 分支，实际 gate 为 resolved/ready，身份与 request 的实际选图一致。
- [ ] 完整原生16fps、逐帧PTS、映射、全帧色彩分析、轨道和资源预检通过。
- [ ] 有当前冻结策略/epoch/唯一 assessment、完整报告闭包及所有历史风险证据。
- [ ] 有真实完整播放原片的观察和合法 Precheck；确认仅轻微颜色问题，无已确认非颜色缺陷；operation及目标颜色意图明确。
- [ ] 独立 pair manifest/ROI/原图 mapping 完整有效，首帧不遗漏；自然配对支持的已测/未测状态没有混淆。
- [ ] 原件未改，合法新增诊断产物单列；索引全部路径、bytes/SHA和作者/时间真实可复核。
- [ ] README 写明下一步和未验证内容；交付不声称候选已经改善或完整观看通过。

只能交图片/视频，或缺来源、色彩解释、实际预检、当前诊断时，状态应为 `material_only` 或 `blocked`，列明缺项。准备任务结束不自动把 VCO-06 改为 COMPLETED，也不自动准备 VCO-07。VCO-06 接手者复核解除条件后，才按任务板状态机记录 BLOCKED→READY→IN_PROGRESS。

## Risks

- 元数据完整只能证明可解释性，不能证明图片正确或视频质量。真实改善仍须 VCO-06 候选与实际完整播放确认。
- 现有三份已验收首段的原选图缺 sRGB 声明；原20秒样片“正常”的接受也不是新校色候选的验收，不能直接复用为本任务已通过。
- 即使输入合格，真实自然配对可能不足、参数方向/幅度可能不合格，最终仍可合法弃权。不能以“必须交成功”为由制造污染或调阈值。
- 没有实际完整播放能力时，原片观察和 Precheck 是尚未解决的依赖，不能由静帧/软件分数代填。
- 若需要新视频，真实生成的执行授权、时长、资源、服务所有权及单次请求恢复要求须在执行任务中据实确定；本文件不预造这些决定或结果。
- profile 仍为 AI/oracle 条件校准、旧 holdout 非新盲测，`production_eligible=false`。准备完成不改变生产资格。
