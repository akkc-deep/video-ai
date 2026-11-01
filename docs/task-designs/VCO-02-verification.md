# VCO-02 验证记录

本记录对应 `docs/task-designs/VCO-02-design.md` 和既定任务板 VCO-02。所有样例为本地 CPU 合成媒体；没有模型请求、GPU 推理、服务启动、校色或视频质量通过结论。原生产媒体接口和参数未修改。

## 实际交付

- `src/video_ai/media/colorimetry.py`：纯解析、PNG chunk/CRC、严格 entry、源/证据/工具 SHA 冻结、独立 sidecar、显式 zscale raw RGB、逐帧记录和有序 chain。
- `tests/unit/test_colorimetry.py`：32 项，覆盖缺失/冲突/unsupported、完整帧声明、旧 probe 精确返回值、结构拒绝、同 stat 漂移、超时和尾帧无证明的时间。
- `tests/integration/test_colorimetry_flow.py`：23 项，覆盖真实范围/transfer/矩阵、PNG profile、五阶段、编码往返、源 run 不变、错误与伪造 sidecar。
- 原 `validate_video_probe`、inspect_video identity 外层、media-ready、options/graph、默认编码链及 JIM-08 记录保持原契约。

## 命令与状态

所有 Python 均先 dot-source `scripts/bootstrap.ps1` 并调用 `Initialize-VideoAiEnvironment`；使用 `D:/VideoSi/envs/video-ai/Scripts/python.exe -B`、独立 cache_dir 和 basetemp，完整命令与退出码在下列日志中。

| 检查 | 结果 | 完整日志 |
|---|---|---|
| 定向：新模块、新集成与旧 video/composition_video/frames | 166 passed，147.76 秒，退出 0 | `D:/VideoSi/cache/video-ai/logs/vco02-targeted-b1b7ef183922454f9676a76680a6db1d.log` |
| 新增彩色色块独立矩阵公式 tv/pc | 2 passed，4.47 秒，退出 0 | `D:/VideoSi/cache/video-ai/logs/vco02-color-patches-3e38d1b1d0cb4fdc9d945dff7d3404ba.log` |
| 首次裸全库 `python -B -m pytest -v` | 未完成：进程已退出，日志停在 412 passed，无最终结果；不能算通过 | `D:/VideoSi/cache/video-ai/logs/vco02-full-bd57b1bc6cbb4071872d209679c0d7a5.log` |
| 第二次裸全库 | 按用户要求停止，已记录 700 passed、0 failed、0 error；全库未完成，不算通过 | `D:/VideoSi/cache/video-ai/logs/vco02-full-retry-190ae0b2b74a41d68a3eed92fa60f023.log` |
| 收尾源码/测试/脚本身份 | 375/375 与启动快照一致，无新增或变化；退出 0 | `D:/VideoSi/cache/video-ai/logs/vco02-closeout-d51fe33e30e64759a94b7d716b341685.log` |

**2026-10-24 收尾结论：** 用户明确要求“最后一个任务再做全库回归，这个任务完成的话收尾吧”。已停止本轮验证 helper 与两级 Python 进程，持久化状态为 `deferred_by_user`（`D:/VideoSi/cache/video-ai/logs/vco02-full-retry-6c75e743-status.json`）；没有遗留本轮回归进程。全库统一后移至 VCO-08/项目最终收尾，不把部分通过当成全库通过。本任务以实现、独立审查、166+2 项定向检查退出 0、真实五阶段证据和源码身份复核完成验收。下一任务本轮不启动、不扩展设计。

2026-10-23 18:21 的恢复记录保留：原全库 worker 已不在，日志没有结束状态；原因未确定。随后启动的第二轮在用户调整验证安排后停止。收尾身份记录为 `D:/VideoSi/cache/video-ai/logs/vco02-closeout-identity-20261023.json`，记录 375 文件无变化及第二轮停止前的 700 项结果。

全库样例索引为 `D:/VideoSi/cache/video-ai/logs/vco02-evidence-bd57b1bc6cbb4071872d209679c0d7a5.jsonl`：逐测试记录确切 source_run/audit_run，每个 audit 还有 `logs/colorimetry/fixture-context.json`。原始 stdout/stderr、CommandResult、版本输出和完整 SHA 均保存在对应 audit 中，不依赖目录“最新”推断。

## 工具与数值解释

本次配置工具均为 FFmpeg/ffprobe `9.0.2-essentials_build-www.gyan.dev`。

| 工具 | 路径 | 字节数 | SHA256 |
|---|---|---:|---|
| ffmpeg | `D:/VideoSi/tools/ffmpeg/bin/ffmpeg.exe` | 105423872 | `3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec` |
| ffprobe | `D:/VideoSi/tools/ffmpeg/bin/ffprobe.exe` | 105221120 | `f0d36ecbbdd3bcfac3efa078c96c7271c2e68b3810595552ac3b7f17e9a65c52` |

第一项完整范围控制的 sidecar 为 `D:/VideoSi/projects/video-ai/runs/20261023-120801-56c82087e624/logs/colorimetry/sample/sidecar.json`；源 MP4 SHA 为 `ce7e72f54c33c074e92525590b77d28a269aed889d97d3673ee29f50bb7c4e3d`，1780 字节。sidecar 内的 FileIdentity 同时保留 mtime_ns 和 verified_at。

统一空间为 BT.709/sRGB primaries、identity RGB matrix、IEC 61966-2-1 transfer、full range、RGB24。对于 BT.709 标记，本版明确采用 zscale 的显示端 BT.1886 理想 EOTF（2.4），再转 sRGB；不是摄像机逆 OETF。独立测试据标准公式构造 full/limited 灰块和含色度的 RGB 色块，在无损 CPU fixture 内检验每通道最多 2 个码值的量化差；此容差不是视频质量阈值。zimg `gamma.cpp` 的显示端/scene-referred 分支用于解释工具行为，调研副本为 `D:/VideoSi/cache/video-ai/temp/vco02-zimg-gamma.cpp`；生产模块不访问网络。

当前工具上，仅在输出端给通用颜色选项会遗漏 primaries/transfer。初始真实 fixture 因此正确得到 unknown；修正夹具为明确输入标记和 x264 VUI 后再验证，生产参数未变。full range 的 H.264 解码 pix_fmt 可为 yuvj420p；保留原值，不伪写为 yuv420p。

## 实际生产转换清单

| 路径/阶段 | 审查所得实际转换 | 诊断处理 |
|---|---|---|
| `runtime/production_scene_clips.py::_technical` generated | 模型输出身份复制；原成功媒体证据由 receipt 保存 | 保留原声明；无模型真实编码命令不猜编码配方 |
| `media/frames.py::extract_native_frame` | 原 generated 的精确零基 index，select 后 format=rgb24 PNG | 原命令未显式约束颜色转换；PNG 无 profile 保留 unknown |
| `media/video.py::trim_scene_video` | 精确 `[start,end)`，setpts=N/(16*TB)，libx264 CRF18/yuv420p | 不改原片和 PTS；分别保留 generated/source 的时间，不混写 |
| `media/frames.py::extract_video_frames`、`media/scene_upscale.py::_decode` | retained 经 RGB24 解码和逐帧 PNG | 无标记的 PNG 不推断 sRGB；既有模型身份仅来自原记录 |
| `media/frames.py::encode_video_frames` | PNG 序列→libx264/yuv420p；默认颜色解释未显式冻结 | 有真实命令才记录规则，标记隐式转换 |
| `media/composition_video.py::raw_rgb/blend_frame` | raw RGB；gbrp 上按有理权重 blend，再打包 RGB24 | 不用 RGB 数值差异自动归因为模型漂移 |
| `media/composition_video.py::encode_composition` | 通用合成中的 encode_base 和 burn_mux 两次编码 | 与正式场景成片路径分别记录 |
| `runtime/_scene_composition_commands.py::encode_args` | 正式场景 PNG + subtitles + narration，一次 libx264 CRF18/yuv420p、AAC | 不与通用两次编码路径混淆；带 AAC 可诊断 |

## 控制样例与逐项验收

1. **媒体与处理步骤可追溯。** sidecar 精确 schema，四颜色项分别保留 raw/value，完整逐帧 probe、stream/format encoder 标签、处理命令与输入/工具 SHA。五阶段样例的链为 `D:/VideoSi/projects/video-ai/runs/20261023-120821-7dd0ad541ddc/logs/colorimetry/chain.json`，分析记录数为 16/1/14/1/16。generated→tail、generated→retained、upscaled→composition 有绑定证据；测试缩放 tail→upscaled 缺原输入/输出绑定 receipt，准确为 unknown。coverage=complete 仅指阶段齐全。
2. **比较使用实际共同空间。** 已知输入输出实际 `.rgb`，检查 width*height*3 字节，sidecar/分析记录独立落盘；缺失、冲突、unsupported、缺 zscale 为 unverified/pixels=null，不隐式解码替代。未标记 PNG、ICC-only、重复颜色 chunk 和坏 CRC 均覆盖。源 PNG chunk 会在 decode 时重新读取，伪造持久化 sRGB 声明也拒绝。
3. **控制变量可复核。** 相同解码 YUV 负载分别标 bt709、bt470bg、未标记，状态分别 resolved/unsupported/unknown。范围与 transfer 使用实际不同转换参数；原始 payload 不同的输入不自动归因。无损 x264 和 CRF18 都从同一已知 PNG 输入转换并编码，逐帧 SHA、raw RGB、MAE/max_abs 保存于 roundtrip-control.json；无损只表示 YUV 编码无损，RGB↔YUV420 与色度抽样仍损失信息，不要求 RGB 逐字节相等。
4. **源 run 与旧契约保持兼容。** 集成测试诊断前后逐文件核对 bytes/mtime_ns/SHA，检查原生 16fps、16 帧、32×32、全部 PTS 为 0..15360 步长 1024，裁片保留 14 帧、原始索引和保留索引区分。五阶段最终视频从测试放大 PNG 实际编码，包含 AAC；此为测试缩放与静帧编码夹具，不冒充 RealESRGAN 或动态连续性验收。旧严格 probe 的精确字段和值有纯解析和真实媒体回归。

本次全库中的往返数值报告为 `D:/VideoSi/projects/video-ai/runs/20261023-120913-2e22923cfa60/logs/colorimetry/roundtrip-control.json`。原始 PNG SHA 为 `d193e7a7edda1625c3556e17ff1a7a14f4bf8bb8c982a5e18302e4fe4f842a81`。两种编码各保留全部 16 帧的差异值；第 0 帧结果如下，仅是该输入的实验记录。

| 分支 | RGB MAE（相对原 PNG） | 最大绝对差 | 第 0 帧 RGB SHA256 |
|---|---:|---:|---|
| x264 CRF0，无损 YUV 编码控制 | 0.6100260416666666 | 11 | `d8f650ef56cdad5bdfd8a7fde1011071c3f365dd6033fda3c171700fe4608b17` |
| x264 CRF18 | 1.1901041666666667 | 13 | `a15e653bdbcea479d229325dd371bfbbe30a22bd9ebb34ecf92bad92171ad608` |

两者都经历相同 RGB/YUV420 转换，CRF0 的 RGB 差异仍包含量化/色度抽样及重建；范围/矩阵解释由独立控制样例隔离验证，不将这里的总差异全部归于压缩或模型。

## 失败与审查

拒绝非法字段、bool 索引/版本、重复 ID/本地索引、引用环、非拓扑输入、完整链悬空来源、非本地/别名/目录源、源 run logger、同路径重写；partial 链允许外部未知来源并明确缺失 stage。源、证据或工具同 size/mtime 字节变化仍报 OSError；失败/超时/错误 raw 字节数不写成功记录，现场命令日志保留。chain 共享总预算，单命令上限 300 秒。

独立审查提出的六项 Important 问题均已针对性修复：帧级声明覆盖、原生尾帧来源时间、持久化 sidecar 与源 PNG 重导、处理输入 SHA、recorded edge 正分支、五阶段成片真实来源。PNG unsupported 格式分类也已修复。RED/GREEN 日志和过程中的 fixture 修正详见 `VCO-02-plan.md`，没有未解决审查项。

仅支持已明确声明的 8bit SDR。HDR/10bit/ICC 变换、真实摄制意图、自动连续性判断、配准/阈值/校色、GPU/真实视频观看均不在本任务交付结论中。无法从完整原始命令和 promotion/model 证据证明的历史处理仍为 unknown；不会为了提高覆盖率推断成功。
