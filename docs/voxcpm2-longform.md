# VoxCPM2 音色及长文案（TTS-VOX-06）

已实现固定音色的无损长文分段、串行 TTS、静音补足、全篇恒定增益及实际采样点映射。[任务设计](task-designs/TTS-VOX-06-design.md)；[实测归档](research/TTS-VOX-06-result.json)。生产编排、恢复和现有时间轴接线仍由 07 完成；当前默认后端不变。

**2026-11-27 音色纠正：** 用户要求纪录片助眠男声，前版音色未获接受。已独立设计新的温润中低男声，生成 35.074 秒短样本，并保存显式音色偏好；[试听路径与新音色用法](voxcpm2-sleep-voice.md)。下方 218 秒样本仅保留为历史技术验证，不代表当前男声偏好已验收。

## 调用

```python
from video_ai.adapters.common import HttpClient
from video_ai.adapters.longform import LongFormSynthesizer
from video_ai.planning.speech import freeze_voice, plan_speech

# config 必须显式冻结为 voxcpm2；emotion_plan 来自 05。
# logger 与服务生命周期由当前阶段持有；不接管外来服务。
voice = freeze_voice(config, base_style=emotion_plan['base_style'])
plan = plan_speech(emotion_plan, voice)
synth = LongFormSynthesizer(
    HttpClient(config.services['tts'], config.timeouts['tts_request'], logger),
    voice,
    request_scope=revision_attempt_identity,
)
result = synth.synthesize(plan, revision_dir/'audio'/'longform')
```

输出目录必须尚不存在，避免覆盖已有修订。`FrozenVoice` 冻结模型版本、参考音频摘要、voice_id、基础风格和推理参数；每个语音单元只改变受限情绪、强度和语气。参考音频沿用配置已验证的身份，服务启动时一次检查和复制，不逐段计算摘要。一个串行客户端保留阶段内的 health/voices 检查结果；未知提交继续使用 04 的原任务查询语义，不另加业务重试。

输出包含 `speech-plan.json`、`requests/speech_0001.json`、`segments/speech_0001.wav`、`narration.wav` 和 `tts-result.json`。逐段生成失败或不合法 PCM 不发布合并旁白和成功回执，已生成片段保留供诊断；本接口尚不承担 07 的生产断点恢复。

## 分段和对齐

原文与合成文本均来自源切片，保留 Python Unicode 半开范围、CRLF、空白、数字、英文和 emoji。情绪原文覆盖先检查一次；生成前只核对计划与冻结身份、语音顺序和不可漏读的 skip 规则。

按句末、段落和有效情绪变化分段，合并同风格短语。长句软目标 180 字，硬上限 250 字；优先标点/空白，无边界时按软目标硬切。为保留可观测的句级时间，完整短句允许低于 80 字，不跨句合并。常见英文称谓、词内点号、后接小写词的 U.S./e.g. 不提升为句末；这是阶段 06 的启发式，不修改历史分段器。

同一句内，情绪切点若会产生少于 8 个可发声字符的小片段，合并并使用该范围按可发声字符计数的主要情绪，平票选先出现的风格；原始情绪来源 ID 全部保留。该规则修复了真实样本“看啊，”被孤立生成的问题，不保证模型不再出现坏样本。纯空白/标点不请求 TTS；普通空白附着相邻单元，超长空白作为 skip 保留原文覆盖。

`tts-result.json` 为每个单元保存原文范围、实际 `start_sample/end_sample`、PCM 采样数、边缘静音、补静音和 `pause_end_sample`，以及服务 request_id。采样率固定 48,000，秒数为采样位置除以 48,000。标记 `alignment=independent-tts-units`：时间来自各自独立生成的音频，不按字数推算；超长句内部短语也只是实际独立 TTS 边界，没有伪造词级时间。skip 不产生虚构时间。07 再将该映射适配原有字幕和镜头时间轴，不能直接冒充旧 timeline schema。

## 停顿和后处理

句间默认 220ms，段间默认 450ms，边界情绪建议分别限制在 150–300ms 和 350–650ms；末尾不补停顿。以两侧实际语音内容之间的原文边界判断停顿，段首换行不会错误增加下一句停顿。已有静音按连续绝对振幅不超过 32/32768 的边缘采样计算，只补 `max(0, 目标 - 上段尾静音 - 下段头静音)`。

逐单元一次读取 PCM，检查 48kHz/单声道/PCM16、完整采样和非近乎静音，不裁剪头尾。最多 3ms 淡入淡出仅发生在已有静音内。先流式合并临时 WAV，再应用一次全篇恒定增益：默认目标 RMS -20dBFS，峰值上限 .95，不逐段压缩、不降噪。这是 RMS 归一化，不是 LUFS 算法；受峰值上限约束时不保证精确达到目标 RMS。恒定增益不改变采样数。结果准备完成后才原子发布，不重复解码做确认。

## 实测和边界

2026-11-26，使用 05 已有四情绪混排计划，加 02 冻结长稿前 1,029 字的显式 narrative 范围，共 1,153 字。没有重复 Ollama 或 ASR 验证。

- 初次目录：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06/20261126-190654-077405`。42 个单元完成生成，但三字“看啊，”的 PCM 峰值仅 14、长 38.24 秒，合并明确失败，没有发布旁白；本次拥有服务退出 0。
- 修复目录：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06/20261126-191337-699731`。新计划 41 个单元，最大 59 字。按源范围与冻结请求参数完全匹配复用 40 个已完成任务，仅生成 1 个合并单元；HTTP 原始日志确认只有一次 `/tts/generate` POST。实验修复工具不等于 07 生产恢复接线。
- 最终 `audio/narration.wav`：48kHz、单声道、PCM16，10,473,141 个采样点，**218.1904375 秒**。单元本体 9,937,920 个采样点，补静音 535,221 个；原文映射和采样数累计通过。
- 使用相同参考摘要、模型版本、seed=42/cfg=2/steps=10；全片增益 0.9551105755，不剪尾音。本次拥有服务退出 0。
- 按最终 41 个任务保存的 `generation_time_ms` 求和，真实模型生成耗时 174.595 秒，单元音频 207.04 秒，模型 RTF **0.843**，没有达到 0.3 目标。修复流程的墙钟 10.656 秒包含缓存查询和下载，不能作为重新生成整篇的性能结果。
- 新增测试 **48 passed**；最终相关回归 **337 passed / 3 skipped，7.75 秒**，日志 `E:/VideoAI/scratch/logs/vox06-final.txt`。三个跳过项为 Windows 符号链接权限。一次独立审查发现的 7 项 P2 均有复现测试并已修复；真实坏样本引出的极短分段问题也经 RED→GREEN 修复。

没有新增主观试听、30 分钟音色稳定、真实 10–30 分钟新链路或完整视频结论。02 的质量和性能限制继续保留。坏样本仍会明确失败，生产重试/恢复由 07 完成；不将客观格式和对齐验证冒充音质验收。

## 复现

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vox06-tests'
$env:PYTHONPATH = "$PWD\src;$PWD\tests;$PWD\tests\unit"
& $VideoAiPython -B -m pytest tests/unit/test_speech_plan.py tests/unit/test_narration.py tests/unit/test_longform_tts.py tests/unit/test_emotion_director.py tests/unit/test_tts_backends.py tests/unit/test_tts.py tests/unit/test_voxcpm_service.py tests/unit/test_segments.py tests/unit/test_timeline.py tests/unit/test_production_timeline.py tests/unit/test_audio.py tests/unit/test_composition_audio.py tests/unit/test_config.py tests/unit/test_manifest.py -q -o cache_dir=E:/VideoAI/scratch/tests/vox06-cache

# 需要重新验收时运行，创建独立 scratch 目录；每个单元真实生成一次。
& $VideoAiPython -B -u scripts/experiments/voxcpm2_longform_smoke.py
# 仅修复某次实验分段：严格相同源文/音色，查询并复用完全相同的已完成请求。
& $VideoAiPython -B -u scripts/experiments/voxcpm2_longform_smoke.py --repair-output '<原实验目录>'
```
