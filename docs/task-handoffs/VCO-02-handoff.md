# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `docs/task-handoffs/video-continuity-optimization-task-board.md`
- **Completed task:** `VCO-01`
- **Next task:** `VCO-02`，按既定 Order 2 选择。
- **Design document:** `docs/task-designs/VCO-02-design.md`
- **Expected next status:** `READY`；本交接写入并关联后执行 `NOT_STARTED -> READY`。READY 不表示实现已经启动。

## Next Task

**VCO-02 — P0-B：原生色彩元数据与编码链诊断。**

目标是将颜色差异的检查定位到模型原始输出、解码、裁片、超分和最终编码的具体资产与处理步骤。按已完成设计新增 `src/video_ai/media/colorimetry.py`：独立 sidecar、原始 probe/逐帧颜色字段、命令与媒体 SHA、精确帧映射，以及已知 SDR 输入的 `srgb_rgb24_v1` 实际解码帧。由显式调用写入新 audit run，原 run 只读；不修改默认生产链、旧 probe 返回字段、帧预算或媒体标签。

验收须具有五阶段可定位证据，缺失/冲突保留 unknown/unverified；通过 Rec.709、不同标记、full/limited、未标记及解码/编码往返控制样例；前后 16fps、全部 PTS、帧数、尺寸和精确映射不变；旧媒体重放与严格 probe 契约保持兼容。执行设计内定向与裸全库检查并保存命令、输入/工具 SHA 和退出码。上述是本任务待实施验收要求，尚无本任务实现或样例通过结果。

## Dependencies

None

## Start Here

按以下顺序阅读：

1. `docs/task-designs/VCO-02-design.md` 全文：接口、输入/sidecar/分析帧 schema、unknown 规则、独立 audit 写入与失败边界。
2. `docs/task-handoffs/video-continuity-optimization-proposal.md` 第 2.2、5、9、10 节。
3. `src/video_ai/media/video.py`、`src/video_ai/media/frames.py`、`src/video_ai/media/composition_video.py`。
4. `src/video_ai/runtime/production_scene_clips.py`、`src/video_ai/runtime/production_scene_upscale.py`、`src/video_ai/runtime/production_scene_composition.py`。
5. `src/video_ai/media/scene_upscale.py`、`src/video_ai/runtime/_scene_upscale_records.py`、`src/video_ai/runtime/_scene_composition_commands.py`；实际最终编码由 encode_args 实现，不是通用 composition_video 的两次编码路径。
6. `tests/unit/test_video.py`、`tests/unit/test_frames.py`、`tests/unit/test_composition_video.py`。

**Implementation first action:** 在明确启动 VCO-02 并按任务板记录 `READY -> IN_PROGRESS` 后，先新增 `tests/unit/test_colorimetry.py`，依据设计固定 parse_color_probe 的精确结构，写入缺颜色字段、stream/frame 冲突及旧 validate_video_probe 返回字段不变的用例，使用设计中的 bootstrap/独立缓存运行取得 RED，再实现纯解析接口。后续创建 `tests/integration/test_colorimetry_flow.py`，避免与单元测试重名。不要先修改旧 probe 返回值或默认编码参数。

## Risks

- 旧 MP4/PNG 可能没有充分色彩声明，unknown/unverified 是必须保留的诊断结果；不得因 RGB24、尺寸或文件扩展名就默认 sRGB/Rec.709。
- 当前只读工具能力检查显示 FFmpeg 提供 zscale/colorspace 及显式输入颜色参数；这不是转换样例通过证据。工具版本/SHA、命令和 raw RGB 需在实施时实际验证。
- 标记一致不能证明真实颜色正确；压缩、抽样、字幕、尺寸变化和模型超分可能改变像素。本任务不做自动连续性阈值、校色或视频质量通过判定。
- 所有产物写新 audit run；源媒体、mapping、日志和冻结 run 均只读。不得启动 GPU、付费请求或模型下载。当前 .git 只读，保留工作区改动，不执行提交或 worktree 元数据写入。
