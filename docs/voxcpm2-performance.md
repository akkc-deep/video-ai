# TTS-VOX-09 性能评估

任务定义见[接入设计 §8–9](voxcpm2-integration-design.md)，实验契约见[09 设计](task-designs/TTS-VOX-09-design.md)，执行步骤见[计划](superpowers/plans/2026-11-28-voxcpm2-performance.md)。

## 结果与决定

**TTS-VOX-09 性能评估已完成（2026-11-28），保留当前官方生产实现。** 参考特征缓存的热生成收益仅 **2.31%**，未达 10% 门槛；六对原始 PCM16 与去上下文后的正文 PCM16 全部一致。没有新主观试听结论，不启用候选，不改批准音色、生产默认或历史任务。

真实结果：[TTS-VOX-09-result.json](research/TTS-VOX-09-result.json)。原始结果和 WAV 位于 `E:/VideoAI/scratch/benchmarks/TTS-VOX-09/20261128-222209-485528/`。进程正常退出，13 次生成（1 冷 + 12 热）、0 失败、0 重试；设备 RTX 5090 D v2，PyTorch 2.9.1+cu128，CPU threads=8。

| 热对照指标（每方案 6 次） | 官方基线 | 参考特征缓存 |
|---|---:|---:|
| 合计生成秒数 | 54.520 | 53.260 |
| 逐段写盘/变速/去上下文流水线秒数 | 54.839 | 53.576 |
| 合计原始音频秒数（含上下文） | 42.880 | 42.880 |
| 合计交付正文秒数 | 32.316 | 32.316 |
| 原始口径 RTF | 1.271 | 1.242 |
| 正文口径 RTF（仍计合成引导语的计算成本） | 1.687 | 1.648 |
| PyTorch 峰值 allocated GiB | 5.845 | 5.623 |
| PyTorch allocator reserved GiB | 6.355 | 6.355 |

两轮生成耗时分别减少 **3.22% / 1.37%**，整轮总计节省 1.260 秒；计入一次缓存构建 0.042 秒后候选生成合计 53.302 秒。逐段流水线改善 2.30%，不含最终 `assemble_narration` 的静音/RMS 合并；整个实验入口耗时 177.905 秒则包含导入、模型加载、冷样本、全部对照、写盘、逐段处理与最终两份试听合并，不含解释器退出。导入 31.896 秒，模型加载 10.571 秒，首次冷生成 25.580 秒，均单独记录。

reserved 是交替对照中共享 CUDA allocator 的保留量，不能据此声称独立加载时的显存节省。上述 allocated 峰值是本进程的实验读数，没有加入生产 GPU 监控。

两份正文试听样本均为 792,843 采样点 / **16.518 秒**，含 17,251 个补足停顿采样点，采用相同全篇增益 0.4860100952。不存在音高处理或背景音。原始和正文 RTF 均未达 0.3 目标，短片段结果不可外推长文。未把“PCM 一致”写成新的发音、自然度或长时稳定试听通过。

## 对照方法

基线为锁定的官方 VoxCPM2 顶层 `generate`，BF16 LM、FP32 AudioVAE、`optimize=false`，模型在本阶段常驻且串行生成。候选直接调用同版本公开的 `build_prompt_cache` / `generate_with_prompt_cache`，将相同参考的右 padding 克隆特征与左 padding 续读特征各构建一次，避免每段重复编码。

缓存只属于该模型实例，身份包括参考 WAV SHA256、参考文本、reference-prompt 模式、模型 revision 和源码 revision；不滚动合并生成音频，也不跨模型或音色复用。没有变更模型、安装依赖或生产实现。

固定配方为 `provided-reference-narration-v1`：seed=42、cfg=2、steps=20，固定参考音频与转写，0.95 倍语速、500ms 段间静音补足、-23dBFS 全篇 RMS。原文使用已批准旅行者2号完整旁白的开头、中间、结尾三个实际片段。统一加入可丢弃上下文“下面继续讲述。”，在 atempo 后按生产声学静音边界剔除，再测量正文时长；试听文件不含引导语，无 ASR、字幕或强制对齐。

首次生成独立记为 cold，不计入热对照。三段正文执行两轮 AB / BA，合计六对、十二次热生成，避免单一先后顺序。模型不重载，不自动重试。每次记录生成耗时、写盘/变速/去引导语的流水线耗时、真实原始及正文采样点、RTF、PyTorch 进程峰值显存。RTF 用总生成秒数除以总实际音频秒数，原始音频包含合成上下文的口径与交付正文口径分列；缓存构建成本另列。

启用的客观门槛是热生成时间至少降低 10%、两轮均为正收益、所有配对原始 PCM16 和去引导语后正文 PCM16 均一致。客观门槛也不能代替主观对照试听；脚本始终只评估，不自动更改生产配置。

## 复现

在仓库根执行，使用已安装的专用环境与本地冻结模型：

```powershell
$env:VIDEO_AI_RUNTIME_ROOT = 'E:\VideoAI'
$env:PYTHONIOENCODING = 'utf-8'
& E:/VideoAI/shared/envs/voxcpm2/Scripts/python.exe scripts/experiments/voxcpm2_performance.py
```

每次写入新的 `scratch/benchmarks/TTS-VOX-09/<时间戳>/`，其中 `frozen-recipe.json`、`frozen-deployment.json`、`reference.wav` 是本次输入。`*-raw-internal.wav` 和 `*-with-context.wav` 仅为带上下文的内部诊断；试听使用 `baseline-listening.wav` 与 `prompt-cache-listening.wav`，各自的 `*-assembly.json` 保存实际正文段级采样点及全篇增益。脚本无句级时间戳，不提供完整视觉视频验收。

## 其他加速路径与边界

Nano-vLLM 与批处理没有在当前冻结环境中安装或实测；其 Windows / Blackwell、参考续读和输出等价仍需单独验证。torch.compile / CUDA Graph 没有在本次启用，需另行验证编译工具链与动态自回归图兼容。不能把未评估写成“不兼容”或“实测失败”，也不为追求速度降低 steps、更换音色或回退 GPT-SoVITS。

当前语音单元本身很短，本实验不能声称 5/10/30 分钟性能、30 分钟音色稳定性、发音或睡眠效果通过。02 的历史累计 RTF 0.762 / 0.756 / 0.750 来自旧实验配方，仅作历史记录，不作为本次 20 steps 批准配方的长时对照。完整视觉视频验证属 08，安装迁移属 10。

## 验证

汇总测试先得到六个预期失败（尚无 summarize），实现后六项通过，覆盖按时长加权的 RTF、冷样本排除、缓存构建成本、缺项/重复/错配、PCM 差异与某一轮倒退。相关回归命令：

```powershell
$voxTestBase = 'E:\VideoAI\scratch\TTS-VOX-09-tests-' + [guid]::NewGuid().ToString('N')
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -m pytest tests/unit/test_voxcpm_performance.py tests/unit/test_narration.py tests/unit/test_narration_guard_default.py tests/unit/test_approved_voice_production.py tests/unit/test_voxcpm_service.py -q -p no:cacheprovider --basetemp $voxTestBase
```

结果为 **63 passed / 3 skipped**；跳过项为本机无符号链接权限。首次使用系统默认临时目录时，已有服务测试将 `E:/VideoAI` 固定为受控根，而夹具位于 C 盘，导致预期端口检查前被路径边界拒绝；改用运行根内全新的测试临时目录后通过，没有修改该测试或放宽生产路径边界。没有执行全仓测试，也不声称全仓回归通过。

独立只读审查未发现重要实现或计量缺陷；关于逐段流水线不含最终合并、reserved 不是独立内存收益的两项口径说明已纳入本文。最终以完整 `evaluated` 报告核对六对齐全、客观门槛未通过、默认未启用，不额外重跑推理或 ASR。
