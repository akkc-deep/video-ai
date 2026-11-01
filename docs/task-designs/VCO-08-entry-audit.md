# VCO-08 入口核查与后端候选

日期：2026-11-01。用户请求：完成任务 VCO-08。

本次完成了任务板 First action 的只读入口核查及三项官方候选资料检查。**VCO-08 未完成，尚无实施就绪设计或可准入后端。** 本文是核查结果，不是生产接入设计或试验执行授权。

## 当前契约与实现

- 任务板：`docs/task-handoffs/video-continuity-optimization-task-board.md`，VCO-08 当前为 NOT_STARTED，Design document/Handoff 均为 None。缺少外部前提时记录缺口，不启动下载或推理。
- VCO-07 的已登记完成结果仅证明 `whole_scene_v1` 的有限整段生产能力；不构成真实跨窗口续写通过。
- `src/video_ai/planning/scene_execution.py` 的 MODES 只有 `segmented_v1`、`whole_scene_v1`；`src/video_ai/runtime/scene_clip_records.py:255` 的 graph_for 仍传递 start_image。检索 src/tests/config/workflows/scripts 未找到 temporal_extension_v1 实现。
- 历史依据：`JIM-08-continuity-diagnosis.md`、`JIM-08-continuity-repair-proposal.md`、`JIM-08-industry-continuity-research.md` 及任务板记录。既有末帧/9帧、VACE、SVI、F1、SkyReels 试验没有可直接继承的跨窗生产通过结果；不得换名重跑后宣称已验证。

## 本次官方候选核查

以下均为公开文档/源码依据，没有执行上游程序，也不是本机视频效果验证。

| 候选 | 已核实机制/入口 | 未解决的准入问题 | 当前判断 |
|---|---|---|---|
| LongLive 2.0 | inference.py 有 i2v、ImagePromptDataset、VAE 编码 initial_latent 并传入 pipeline 的实际入口；5B 分支保存为 24fps | 默认 inference.yaml 未配置 I2V；没有核实适用 I2V checkpoint 的不可变身份、逐文件清单及本机资源；不能从存在 I2V 入口推出通用公布权重已经适用 | 保留候选，不准入 |
| MemFlow | 官方描述按当前提示检索历史帧，更新有限容量记忆库 | 官方 README Requirements 明确为 80GB GPU、Linux；本机适配与实际条件/权重未验证 | 不作为本机首选 |
| LongCat-Video 基础模型 | 官方有原生 video-continuation 与多段长视频入口；实际 generate_vc 使用编码历史 latent/clean KV 条件；输出裁除历史前缀 | 官方 BF16 整模型入 GPU 路径超出本机容量；示例依赖 NCCL，Windows 运行未核实；基础链 15fps、refinement 可为30fps，不能直接替代16fps；没有独立本机多窗试验 | 可作为新的协议研究候选，不准入 |

LongCat 来自本次新读取的官方实现，不是旧 VACE/SVI/F1 方案改名。README 宣称的分钟级稳定性仍属作者陈述，不登记为本项目效果通过。Avatar/Avatar-1.5 的音频驱动用途及 INT8 支持不自动适用于基础 LongCat-Video。

## LongCat 的可复核细节

对应本次保存的上游源码行号：

- `longcat_continuation.py:43` 设置 num_cond_frames=13；95–106 将真实 video 和条件帧数送入 generate_vc，开启 use_kv_cache。
- `longcat_pipeline.py:269` 取历史尾帧，经 VAE 编码并填充条件 latent；1022–1026 缓存 clean 条件并分离新增 latent，1081–1082 合回条件用于解码。
- `longcat_continuation.py:114` 以原视频加 output[num_cond_frames:] 组装；`longcat_long.py:128` 每段只追加去前缀后的帧。93总帧/13历史帧的示例每个续窗追加80帧；这只是源码预算，不是实际输出结果。
- `longcat_continuation.py:56` 初始化 NCCL；65–81 加载 BF16 编码器、VAE、DiT 并 pipe.to(local_rank)。offload_kv_cache 仅表示 KV 卸载，不能证明 DiT 权重已卸载。
- 官方基础模型为13.6B。仅按 BF16 两字节估算约27.2GB（25.33GiB），已超过 GPU 的24455MiB；尚未包含其他模块、激活和缓存。这是容量下界估算，不是实测峰值或完整下载预算。
- `longcat_continuation.py:89` 用15fps目标及 round(current_fps/target_fps)整数stride处理输入。直接把16fps旧片送入该示例，stride会为1，再保存为15fps，无法保持原时长；不能照搬。
- 官方 demo 还串行执行基础、distill、refinement 多种调用，不可整份直接执行作为一次有上限试验。若采用，须单独冻结一个调用路径。

## 证据与本次检查

官方资料由 GitHub 连接器 github_fetch 读取，七份正文保存在：

`D:/VideoSi/projects/video-ai/vco08-preflight/20261101-1238/`

入口 `sources.json` 记录原 URL，`source-hashes.json` 记录本地保存字节的大小和 SHA256。来源为 NVlabs/LongLive 的 LongLive2.0/configs/inference.yaml、inference.py，KlingAIResearch/MemFlow/README.md，以及 meituan-longcat/LongCat-Video 的 README.md、run_demo_video_continuation.py、run_demo_long_video.py、longcat_video/pipeline_longcat_video.py。URL 使用 main；尚未冻结上游 commit，快照 SHA 只绑定已保存的文本。

- `nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader`：RTX 5090 D v2，24455MiB，总查询时占用1896MiB。未加载模型或停止任何应用。
- Get-CimInstance Win32_OperatingSystem 查询被拒绝访问，没有取得当前系统内存结果；32GB 是历史文档配置，未标为本轮实测。
- 七份上游正文已写入并以 Get-FileHash 保存 SHA256。没有执行这些 Python 快照。
- 一次猜测的 LongLive pipeline 文件地址未取得正文，不作为证据；两项猜测的历史验证文档文件名和 models/huggingface 目录不存在，不据此断言相应试验/模型不存在。
- 本轮没有修改产品代码、配置、测试或既有 run；没有模型/权重下载、依赖安装、GPU 推理、付费请求或发布。文档核查未运行 pytest，全库回归仍未完成。

## 尚缺的实施输入

1. 选定的新后端及适用权重、代码、依赖的不可变身份和资源清单；已有权重不得假定可互换。
2. 本机运行方法：若选 LongCat，先解决 DiT 容量、分阶段加载/卸载与原生 Windows/NCCL 路径，不能以 KV 卸载冒充整模型可运行；未准入不下载模型或试跑 OOM。
3. 独立试验的原生时基、历史/新增帧预算、输入内容、单次调用上限、资源预算和失败停止规则；真实完整动态观察须另有证据，不能复用 VCO-07 观看。
4. 新后端多窗试验的实际媒体、自动报告、主体/色彩/构图/运镜/动作观察结果。未通过前不启用 temporal_extension_v1。
5. 后续接入的精确16fps时间轴适配、重叠只输出一次、完整PCM/字幕、失效/恢复/未知不重复提交，以及最终全库回归。

## 建议的下一步与范围选择

建议把 LongCat-Video 保留为新的协议研究路线，LongLive 为备选；当前不能承诺任一候选在本机可运行或视觉通过。若继续该路线，应先完成资源/平台可行性和独立试验设计，再就冻结后的具体下载、隔离依赖与单次多窗试验处理执行范围。保留当前24GB/Windows和正式16fps约束；任何更换环境或放宽验收都须明示。

任务板目前把新的协议和独立实测列为外部前提，并明确“不默认下载模型或追加推理”。需要先确定是否把上述新后端研究试验纳入本任务；在此前提未确定、实施设计未完成时，不将本次入口核查标成 VCO-08 完成，也不填写一个表面就绪的 Design document。
