# 男声自然度与稳定性试听修订

用户反馈上一版“声音不够稳，不够自然”。已把上一版的持久偏好标记为 `needs_revision` 并保存原始反馈，不把旧样本当成已验收。

后续用户要求语速更慢、多段声音一致；最新[慢速固定音色多段试听](voxcpm2-consistent-voice.md)沿用 B 的参考，统一参考续读及 0.8 倍语速。A/B 不是已验收的最终配置。

本轮只进行小规模真实试听实验，没有修改生产代码、分段/字幕契约或默认后端，也没有重复长文、ASR、音高分类或全套测试。一次加载现有 VoxCPM2 GPU 模型，生成 A、新参考和 B 三条音频。模型源码版本与冻结版本一致，输出只进行必要数组及单次 WAV 格式/采样点检查，进程正常退出。

## 样本

目录：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06-natural-voice/20261127-013858-190683`。

- **A：精简指令、整段连读。** `A-simple-continuous.wav` 使用上一版参考音色，仅保留“平静自然的男声旁白”短指令；同一段原文一次生成，取消逐句重启与人为插入间隔。
- **B：平实男声、参考续读。** `B-natural-continuation.wav` 使用新设计的平实成年男声参考，按官方 reference_wav_path + prompt_wav_path + prompt_text 模式连贯生成，同样原文、无情绪前缀。prompt_text 使用新参考的预期生成原文，尚未经独立转写或人工逐字确认。
- `reference-v2.wav` 是 B 的新音色参考，不作为完整旁白样本。候选资产保存在 `shared/assets/voices/male-natural-documentary-v2-20261127-013858-190683/voice.json`。

两版均使用原 seed=42 / cfg=2，试听时将 diffusion steps 从 10 改为 20；没有强制拉慢语速、压低音高、逐段动态压缩或后期变声。A/B 为供用户选择的听感候选，不是单变量归因实验。不能从生成成功推断任何一版更稳定或更自然。

整段生成只标记整段时长，没有按字数伪造句级时间。B 尚未接入生产服务；当前生产服务的参考克隆不包含此参考续读模式。候选尚未替换持久偏好，须先根据用户试听决定下一步；不能仅选择新 profile 就声称复现了 B 的续读条件。

[真实生成记录](research/TTS-VOX-06-natural-voice-result.json)。复现（专用 VoxCPM2 环境）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'natural-male-audition'
$env:PYTHONPATH = "$PWD\src"
$env:PYTHONUTF8 = '1'
& "$VideoAiRuntimeRoot/shared/envs/voxcpm2/Scripts/python.exe" -B -u scripts/experiments/voxcpm2_natural_voice.py
```
