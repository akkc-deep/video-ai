# VCO-02：原生色彩元数据与编码链诊断

## Goal

为模型原始输出、原生尾帧、裁片、超分帧和最终成片生成独立、可复算的色彩证据，支持逐阶段检查颜色解释与编码差异。信息不足时明确保留 unknown，不能把元数据一致、像素接近或一次解码成功解释为视频质量通过。

任务身份与范围以 `docs/task-handoffs/video-continuity-optimization-task-board.md` 的 VCO-02 为准，直接任务依赖为 None。实现、实测结果和限制分别记录于 `VCO-02-plan.md` 与 `VCO-02-verification.md`；以下为实施契约，不以设计文字替代实测证据。

## Scope

新增标准库和现有 FFmpeg/ffprobe 实现的旁路诊断接口，保存五类媒体的 sidecar、原始 probe/逐帧字段、处理命令证据与显式分析空间的实际解码帧。诊断由调用者显式调用，写入独立 audit run；不修改源 run、原片、生产编码参数、默认 pipeline、配置/options、旧媒体记录 schema 或观察/发布门槛。

不包含连续性算法、告警阈值、自动归因或打分、校色、HDR 色调映射、通用 ICC 变换、GPU/模型请求、模型下载和真实视频观看验收。不同原始像素内容的颜色差异不在本任务直接归因为模型漂移。

## Approach

### 已核对的实际链路

| 阶段 | 当前实现与证据入口 | 必须记录的事实 |
|---|---|---|
| generated | `runtime/production_scene_clips.py::_technical`；`clip.json`、generated media-ready receipt | 模型输出到 generated.mp4 为身份复制；编码器优先保留 probe 原始声明，缺少实际编码命令时不猜测模型编码细节 |
| native_tail | `media/frames.py::extract_native_frame`；`last-frame.json` 与命令记录 | 从 generated 的 `retained_source_end-1` 提取，`select=eq(n\,index),format=rgb24`；颜色转换依赖 FFmpeg 隐式解释，不因 PNG 为 RGB 就推断 sRGB |
| retained | `media/video.py::trim_scene_video`；source media-ready receipt、mapping.json | 精确 `[start_frame,end_frame)`；`trim=...,setpts=N/(16*TB)`，libx264/CRF18/yuv420p；未显式设置色彩参数 |
| upscaled | `media/scene_upscale.py`、`media/frames.py`、`runtime/_scene_upscale_records.py`；extraction/frame receipts | source 经 `format=rgb24` 提帧，RealESRGAN 输出 RGB24 PNG；模型/graph 身份来自既有记录，PNG 未标记的传递函数继续为 unknown |
| composition | `runtime/_scene_composition_commands.py::encode_args`；原 encode/probe receipts | 实际生产路径为逐帧 PNG + 字幕 + narration，libx264/CRF18/yuv420p、AAC；无显式色彩参数。另记录 `media/composition_video.py` 的通用路径具有 base 编码和 burn/mux 两次编码，不能与正式生产路径混淆 |

`composition_video.raw_rgb/blend_frame`、`frames.encode_video_frames` 和 `scene_upscale._decode` 的 RGB/YUV 路径也纳入转换清单。缺原始成功命令或缺精确转换参数时，记录 `implicit_ffmpeg_conversion` 或 `missing_processing_evidence`，不能用源码中的默认值冒充该媒体实际执行的命令。

### 接口与调用方式

新增 `src/video_ai/media/colorimetry.py`，公开以下接口，返回普通独立 dict，不修改入参：

```python
parse_color_probe(probe, frame_data, *, png_metadata=None) -> dict
inspect_color_asset(entry, *, config, paths, logger, timeout=300) -> tuple[dict, list]
decode_analysis_frame(sidecar, *, frame_index, config, paths, logger,
                      timeout=300) -> tuple[dict, list]
inspect_color_chain(entries, *, config, paths, logger, timeout=1200) -> tuple[dict, list]
```

`logger` 必须属于调用者用 `create_run(RuntimePaths.from_config(config))` 创建的新 audit run；不得传入源生产 run 的 logger。所有写入仅在该 audit run 的 `logs/colorimetry/` 及命令日志中，所有 subprocess 的 cwd 也在 audit run。读取的源媒体/来源证据是显式提供的常规文件，禁止 symlink、路径别名和目录冒充文件；沿用现有路径拼写/根校验。读取原 run 不会创建它的锁、日志或新媒体。

parse_color_probe 返回精确 `{video, png_metadata, interpretation, risks}`，字段结构见下文。三个运行接口返回 `(record, evidence_paths)`，record 分别为已落盘 sidecar、分析帧记录或 chain，evidence_paths 为本次输出/原始命令证据的 Path 列表。decode_analysis_frame 从该 logger 下既定 asset_id 路径读回并核验 sidecar 与入参相等；不能接受只有内存声明、未落盘的 sidecar。源文件不得位于 audit run 内，避免把写入源 run 的 logger 当成新 audit logger。

单资产诊断可独立调用；完整链调用使用五个 stage 的有序 entries，超分阶段每个 PNG 对应一个 entry，以稳定 asset_id 区分。调用者从现有已核验 clip、last-frame、mapping、extraction、frame、composition 记录取得路径和映射；不通过目录扫描猜测“最新”媒体。缺阶段时 chain 仍可生成诊断，但 coverage 为 partial，列出缺失 stage，不能声称链路完整。

### 输入及持久化 schema_version=1

所有新结构精确检查字段；未知字段、bool 代替版本/索引、重复 ID、重复本地帧映射、非法路径和引用环均 ValueError。SHA 使用现有 canonical_digest/hash_file；不引入第二套摘要规则。

`entry` 精确字段：

| 字段 | 契约 |
|---|---|
| asset_id | 唯一 ASCII `[A-Za-z0-9_-]+`，只作 audit 标识，不参与原生产身份 |
| stage | generated / native_tail / retained / upscaled / composition |
| path | 实际存在的绝对 MP4 或 PNG 文件路径；序列不以通配符作为源 |
| mapping | `{rows, evidence}`；evidence 为原始 mapping/last-frame/frame-map 记录的 FileIdentity 列表，可空；rows 为下述映射行列表 |
| processing | `{operation, upstream_ids, command_records}`；operation 为非空描述字符串，upstream_ids 为实际直接来源 asset_id，command_records 为已有成功媒体命令/receipt 文件的 FileIdentity 列表，可空 |

映射行精确字段为 `asset_frame_index, clip_id, generated_frame_index, retained_frame_index, output_frame_index, pts, time_base`。asset_frame_index 是本资产零基解码序号；clip_id 可为 null，其余三种索引允许 null 表示没有对应证明，否则必须非负整数；pts 为实际整数 ticks 或 null，time_base 为正有理数字符串或 null，两者同时存在/缺席。保留源视频原始 PTS；不能将 retained 的零起点 PTS 写成 generated 原始 PTS。PNG 的原生时间来自所引用视频映射；ffprobe 对单 PNG 推断的 25fps 不是生产时基。无证据映射标记 `unverified_mapping`，不据此构造可比帧。

诊断先冻结源媒体、mapping/processing 证据和工具 FileIdentity（path/bytes/mtime_ns/sha256），每条命令后及最终写入前重新验证；同 size/mtime 字节漂移也必须拒绝。upstream_ids 只表达调用者提供的关系；只有原记录明确绑定了输入/输出 SHA 和帧映射时才将关联标为 recorded，否则为 unknown。部分链的外部来源允许通过缺失 ID 记为 unknown；完整覆盖链不允许悬空来源。关系不是推断因果的许可。

每个 sidecar 精确顶层字段：

`schema_version, algorithm, asset_id, stage, source, input_sha256, mapping, processing, probe, interpretation, analysis_space, commands, tools, risks, created_at`。

- algorithm 固定 `colorimetry_v1`；source 是完整 FileIdentity；input_sha256 为冻结 entry、源/证据 SHA、工具 SHA 与算法版本的 canonical digest。
- probe 为 `{raw_probe, raw_frames, png_metadata, video}`：前两项为原始 JSON 日志 FileIdentity。png_metadata 对 MP4 为 null，对 PNG 为精确 `{srgb_intent, gamma, chromaticities, icc_sha256}`，分别为 sRGB chunk 的整数 intent、gAMA 原始整数、cHRM 八个原始整数的数组和 iCCP chunk SHA，缺席均为 null；重复或矛盾颜色 chunk 记录冲突，坏 CRC 为非法媒体。video 精确字段为 codec_name、pix_fmt、width、height、encoder、color_space/color_primaries/color_transfer/color_range、time_base、r_frame_rate、avg_frame_rate、frames。encoder 为 `{stream,format}`，同时保留 stream 与 format tags 的原始声明，无声明为 unknown；实际编码命令另见 processing，不把 Lavf/Lavc 标签当成完整编码配方。frames 来自完整解码帧记录并与 count_frames 交叉验证；PNG 的帧数为 1，三个时基/fps 字段为 null，不使用解复用器伪造时间。
- video 的四个 color 字段为 `{raw, value}`，raw 缺席时 null，value 缺失/unspecified/N/A 时为字符串 unknown；未知但非空的声明原值保留，不能归一成 bt709。逐帧字段与 stream 字段不同、或帧间不同，保留具体帧编号与原值。
- interpretation 精确字段 `{status, values, evidence, conflicts}`。status 为 resolved / unknown / conflicting / unsupported；values 为四项规范化颜色字段，evidence 为声明来源描述列表，conflicts 为 `{frame_index, field, stream_value, frame_value}` 列表。resolved 仅表示声明可解释且一致，不证明声明符合真实摄制意图。帧缺标记本身不覆盖有效 stream 标记，但明确冲突不能忽略。
- processing 的输出增加 `{status, rules}` 两项：status 为 recorded / unknown；rules 为每条原命令的 args、filter、encoder、pix_fmt、explicit_color_options 和 conversion_status。只从真实、成功且输入/输出身份匹配的命令证据提取；缺 promotion 证明、旧日志缺项或隐式转换记录风险，不假装完成精确颜色解释。
- analysis_space 为 `srgb_rgb24_v1` 或 null；只有以下规则全部成立时有值。commands 为本次实际 probe/version 命令的完整 CommandResult，tools 精确为 `{ffmpeg,ffprobe}`，每项为 `{identity,version_command,version_output}`，identity/version_output 为 FileIdentity，version_command 为 CommandResult。risks 行精确为 `{code,detail,frame_index}`，前两项非空字符串，frame_index 为非负整数或 null；无质量 passed 字段。稳定 code 包括 missing_color_metadata、conflicting_color_metadata、unsupported_color_interpretation、missing_processing_evidence、implicit_ffmpeg_conversion、unverified_mapping、missing_stage、missing_zscale。

sidecar 写入 `logs/colorimetry/<asset_id>/sidecar.json`，exclusive 创建；相同路径已存在拒绝覆盖，重跑使用新 audit run。链输出 `logs/colorimetry/chain.json`，精确字段为 `schema_version, algorithm, assets, edges, coverage, missing_stages, risks, created_at`；assets 是有序 `{asset_id, sidecar, analysis_frames}`，后两项分别是 sidecar FileIdentity 和分析帧记录的 FileIdentity 列表；edges 为 `{from_asset_id,to_asset_id,status}`，status 为 recorded / unknown。输入 entries 按依赖拓扑顺序、直接来源先于目标，输出保留该顺序；不自动按目录名排序。coverage 为 complete / partial，仅表示诊断阶段覆盖率。

### 元数据读取及 unknown 规则

以 `run_logged` 执行实际配置的 ffprobe，保存完整原始 stdout/stderr 和版本：先 `-v error -count_frames -show_streams -show_format -of json`，再 `-v error -select_streams v:0 -show_frames -of json`。选取唯一视频流，最终 MP4 可带音频，不能复用旧“恰好一个无音频 H.264 流”限制来拒绝最终成片。保留逐帧 PTS 与颜色声明，不仅采头帧。PNG 额外以标准库读取并检查相关 chunk CRC，iCCP 只记录原始 chunk SHA，不执行不受控 profile 解压或转换。

四项解释不齐时 unknown；stream/frame 不一致时 conflicting；BT.2020/PQ/HLG、非支持矩阵、10/12bit、ICC-only 或其他未实现组合为 unsupported。所有情况都照常保留可读的 metadata sidecar，analysis_space=null，风险带缺失/冲突的字段和帧号。工具失败、非法媒体、超时、证据或源字节漂移则抛出异常，不写成功 sidecar；命令失败现场保留。未知颜色不是技术视频失败，也不改变原生产状态。

### 统一分析空间与实际转换

第一版只支持声明完整且无冲突的 8bit SDR：YUV 的 matrix/primaries 为 bt709、transfer 为 bt709 或 iec61966-2-1、range 为 tv/pc；RGB PNG 必须有有效 sRGB chunk，且无冲突的 gAMA/cHRM/iCCP 声明。RGB24 的整数范围可按 PNG 规范认定 full，但没有 profile 时不能推断传递函数或色度坐标。仅 gAMA 或文件扩展名不能证明 sRGB。

输出 `srgb_rgb24_v1` 定义为 BT.709/sRGB primaries、sRGB IEC 61966-2-1 非线性传递、identity RGB matrix、full range、8bit RGB24。调用 `decode_analysis_frame` 时先重验 sidecar/source/tools 身份，frame_index 必须是本媒体实际解码范围内非 bool 整数。按零基解码顺序 select 精确一帧，不以 seek 秒数近似。

YUV 使用实际 CPU zscale 转换，输入 matrix/transfer/primaries/range 从已验证声明经固定 allowlist 映射，输出显式 gbr / iec61966-2-1 / bt709 / full，dither=none，再 `format=gbrp,format=rgb24` 打包。BT709 的 tv/pc 分别映射 limited/full；禁止用 `setparams` 或 `-color_*` 标签代替转换。sRGB PNG 也用显式输入/输出参数，不借助默认矩阵。完整 args、filter 和工具版本写入证据；固定单线程、输出 `-frames:v 1 -fps_mode passthrough -pix_fmt rgb24 -f rawvideo`，保存实际 raw RGB，检查恰好 width*height*3 字节。

返回分析帧记录精确字段：`schema_version, algorithm, source, sidecar, frame_index, pts, time_base, mapping, status, analysis_space, pixels, command, risks`。status 为 ready / unverified；pixels 为 raw RGB FileIdentity 或 null，sidecar 为原 sidecar FileIdentity。unknown/conflicting/unsupported 输入返回 unverified、pixels=null，不悄悄运行默认解码后冠以共同空间。frames 保存在 audit 的独立子目录，不取代尾帧、模型输入或超分帧。

分析帧 algorithm 固定 `colorimetry_v1`，mapping 为该索引对应行或 null，pts/time_base 保存实际资产解码时间，PNG 则为已证明的来源时间或 null。命令缺席时 command=null。raw 文件为 `logs/colorimetry/<asset_id>/analysis/frame_<index:06d>.rgb`，记录为同 stem 的 `.json`，index 为零基；每次 exclusive 创建，重复分析同帧拒绝覆盖。unverified 情况也写对应记录，便于链明确列出未生成 pixels 的原因。decode 的 CommandResult 留在分析帧记录中，不回写已冻结 sidecar。

链诊断对每个视频的全部已提供 mapping 行、以及所有 PNG 生成分析帧；没有 mapping 时仍保存 metadata，但不伪造比较对应关系。配对比较只能使用双方 ready 且 mapping 证明对应同一原始内容的帧。该接口交给后续 VCO-03，不在本任务制定连续性阈值。颜色解释改变和压缩重编码的差异通过下述独立控制样例分别留证，不以两张图不同就自动判定原因。

机器缺 zscale 时保存 capability 失败与 unverified，不降级为隐式 RGB 解码。本次只读 capability 检查已确认当前 FFmpeg 同时提供 zscale/colorspace，以及显式输入矩阵/传递/原色/范围选项；这不表示转换样例已测试通过。

### 兼容与失败边界

`validate_video_probe()` 返回字段仍精确为 width/height/codec/pixel_format/fps/frames/duration；inspect_video 的 identity 外层也不增加色彩字段。所有旧 probe、media-ready、frame/clip/upscale/composition 及 options/graph 保持原值。新诊断不成为生产接受前提，算法变化不重新生成模型视频。

单命令最多 300 秒，单资产 timeout 是总期限；chain timeout 是跨资产共享总期限，所有命令使用剩余预算。无网络客户端、服务启动、GPU 采样或 POST。文件/工具漂移 OSError，结构/源格式不合法 ValueError，命令失败 RuntimeError，超时保留原 timeout 异常与日志。chain 任一资产执行失败时不写 complete chain；已完成 sidecar 和失败证据保留，下一次显式调用选择新 audit run。

## Files

### 实施中确认的解释与证据细节

- `srgb_rgb24_v1` 对 BT.709 使用 zscale 的显示端 BT.1886 理想显示 EOTF（指数 2.4），随后转换为 sRGB；不声称重建摄像机的 scene-referred 逆 OETF。实测独立公式使用此明确约定。sRGB transfer 保持 IEC 61966-2-1 解释，全部转换参数仍显式写入命令。
- 对已核验原记录的规范化 mapping 导出，可提供精确 `{source, rows}` JSON 作为 mapping.evidence：source 为该资产 FileIdentity，rows 必须与 entry 完全一致，source 的 path/bytes/SHA 必须匹配。导出是调用者已核验映射的显式记录，诊断不从目录或像素猜测对应关系，也不创建/修改源 run 的导出。视频 rows 的 PTS/time_base 必须与本资产完整逐帧 probe 一致；PNG 仅使用已记录来源时间。任意无绑定 JSON 不构成证明。
- 直接识别的历史映射包括 clip 的 `frame_mapping_sha256` 与原 mapping.json，以及 last-frame 的 image/generated/原视频逐帧时间和 clip mapping 联合证明。缺少完整绑定则保留 unverified_mapping，不用单个 last-frame 字段推算保留索引或时间。
- processing 只从带原 source、target/output 和成功 CommandResult 的直接命令记录提取规则；核验输入/输出字节身份并冻结原 stdout/stderr。生产 media-ready 的 staging→target promotion、超分模型 graph 和其他复合证据未提供完整适配证明时保留 unknown；不能把源码默认参数或成功-looking 标签当成真实命令。
- chain edge 仅在双方映射已绑定、目标坐标由来源覆盖、且原成功命令绑定双方源 SHA 时为 recorded，否则为 unknown。coverage 仍仅为五阶段覆盖率。

- 新增 `src/video_ai/media/colorimetry.py`：纯解析、schema、PNG 标签读取、只读 probe、显式分析帧解码及独立链 sidecar。
- 新增 `tests/unit/test_colorimetry.py`：精确结构、unknown/conflict、颜色参数映射、输入不可变、失败/漂移和旧 probe 字段。
- 新增 `tests/integration/test_colorimetry_flow.py`：真实 CPU FFmpeg 控制样例和五阶段只读诊断，basename 与单元文件不同。
- 更新本设计并新增 `docs/task-designs/VCO-02-verification.md`：记录转换清单、实际命令/工具版本、样例身份、数值结果与限制；完成后更新既定任务板。

前述 video/frames/composition/runtime 文件是审查及回归输入，本方案不要求修改其生产实现。无需新增 NumPy/OpenCV、模型或配置字段。

## Tests

**验证安排更新（2026-10-24，用户明确指示）：** 用户要求“最后一个任务再做全库回归，这个任务完成的话收尾吧”。本任务以定向单元/集成、必要旧媒体兼容回归及审查证据收尾；裸全库统一后移至本项目最后一个任务 VCO-08 的最终收尾阶段，不再作为 VCO-02 本轮完成的前置条件。中断或主动停止的全库记录不算通过。此指示覆盖本设计先前要求本任务立即执行全库的安排。

RED 先运行新增精确 schema/unknown/旧 probe 契约用例，确认因缺接口或目标行为失败，再实现；不能以工具不存在或 import basename 冲突代替行为 RED。以下命令都从仓库根运行，先 bootstrap，每一阶段使用独立名称和运行缓存：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco02-targeted'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest','-v','tests/unit/test_colorimetry.py','tests/integration/test_colorimetry_flow.py','tests/unit/test_video.py','tests/unit/test_composition_video.py','tests/unit/test_frames.py','-o',"cache_dir=D:/VideoSi/cache/video-ai/temp/vco02-cache-$VideoAiCommandId",'--basetemp',"D:/VideoSi/cache/video-ai/temp/vco02-targeted-$VideoAiCommandId")
exit $VideoAiExitCode
```

以下裸全库命令保留为项目最后一个任务统一执行的参考，本轮 VCO-02 不再执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco-project-final-full'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest','-v','-o',"cache_dir=D:/VideoSi/cache/video-ai/temp/vco-final-cache-$VideoAiCommandId",'--basetemp',"D:/VideoSi/cache/video-ai/temp/vco-final-full-$VideoAiCommandId")
exit $VideoAiExitCode
```

本任务定向命令预期退出 0；全库结果由项目最后一个任务另行登记。`tests/unit/test_frames.py` 已确认存在。测试均为本地合成媒体和 CPU 命令；不调用生成模型。

必须覆盖：

1. 纯解析缺失/unknown/不支持/stream-frame 冲突、PNG 无 profile/sRGB/ICC-only/CRC 错误；精确 schema、完整逐帧记录、bool/重复 mapping/引用环拒绝；无入参修改。
2. 真实 16fps、16 帧的小尺寸确定性色块：正确标记 BT709 limited 与 full，输出实际分析帧；以标准公式构造对应 YUV 码值并校验显式范围解码，RGB 每通道容差仅为该无损合成 fixture 的 2 个整数码值，不作为视频质量阈值。BT709 与 sRGB transfer 样例保留不同的实际转换参数和输出证据。
3. 同一像素负载、不同矩阵标记，以及完全未标记样例：保留声明差异/unsupported 或 unknown；未标记不生成 ready 分析帧。错误标记不能靠改标签“修复”，同 metadata 不等于真实颜色正确。
4. 同一已知输入分别做无损控制、libx264/yuv420p CRF18 往返：保存前后 SHA、raw 像素和逐帧差异数值，分开记录范围解释变化与压缩损失；不要求有损编码逐字节相等，不制定泛化通过阈值。
5. 五阶段链：generated、精确裁片、原生尾帧、合成超分测试 PNG、带音频最终 MP4；fixture 超分明确标记为测试缩放，不冒充 RealESRGAN 效果。映射覆盖每一帧，原始索引/保留索引/输出索引与 PTS 可追溯；缺阶段产生 partial，缺命令/PNG profile 产生对应风险。
6. 诊断前后逐文件比较源 run 的 bytes/mtime_ns/SHA；原视频的帧数、尺寸、全部 PTS、原生 16fps 和既有 mapping 不变。最终 MP4 带 AAC 也能独立诊断；旧 validate_video_probe 的返回字段和值精确相等。
7. 同 stat 源/证据/工具字节漂移、probe/解码失败、超时、错误输出字节数、重复目标路径、非本地路径和错误 logger run 均拒绝成功登记；没有媒体重写、服务启动、网络请求或 GPU 动作。

## Acceptance

- 任务板四项验收逐条映射到以上测试和带 SHA 的日志/sidecar；五阶段和真实解码证据可定位到准确资产、转换步骤及帧编号。
- 只有已支持且声明一致的输入产生 srgb_rgb24_v1 实际 raw RGB；缺失、冲突及 unsupported 情况保留原始字段、unknown/unverified 和风险，不能推断矩阵/范围。
- 控制样例覆盖 Rec.709、不同标记、full/limited、未标记及解码/编码往返，能区分实验控制变量；不自动推断真实视频差异的原因。
- 源 run 和旧媒体/请求契约不变，原生 16fps、PTS、帧数、尺寸和精确映射的回归实际通过；本任务定向回归退出 0，全库按用户最新指示后移至最后一个任务统一执行。软件证据不替代完整动态观看，不新增视频质量通过结论。

## Risks

真实历史 MP4/PNG 可能缺标记，首版会产生较多 unverified；保留未知是验收行为，不能为了提高覆盖率默认套 Rec.709/sRGB。标签本身也可能不准确，resolved 仅说明元数据解释一致。

libx264 有损压缩、色度抽样和 FFmpeg 版本都会影响像素；工具 SHA、版本、完整命令与 raw 解码输出均须冻结。不同内容、字幕覆盖、尺寸变化和模型超分不能直接逐像素归因；配准、连续性阈值和观看结论留给后续任务。

逐帧 probe/分析可能较慢；本任务以一次顺序 probe、按映射显式解码与独立 audit run 控制重复工作，不缓存跨调用的源文件身份。当前 .git 只读，实施应保留用户工作区，不执行提交、worktree 元数据写入或 reset。没有阻止本设计实现的未决需求；不支持的颜色解释按上述规则明确输出 unverified。
