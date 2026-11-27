# 清亮自然男声，避免刻意哄睡腔

用户拒绝上一轮两份音色，认为仍太低沉，要求声音轻快一些，并指出刻意哄睡听感生硬。按此前慢语速要求，将“轻快”先落实为音色更清亮轻盈、自然聊天感，不自动加快速度。

## 调整依据与范围

上一轮 A/B 参考进行了一次有声帧音高诊断：保留 pYIN voiced 且 probability≥0.5 的帧，参考中位数约为 A 138Hz、B 109Hz。此数值只用于发现候选仍偏向低音区，不是医学标准、性别判定、睡眠效果判定或感知音色好坏的充分条件；气声和低置信度会限制估计可靠性。没有进行 ASR 或扫描所有历史音频。

本轮不再让声音设计围绕“轻声、柔软、睡前陪伴”等词，改用官方支持的自然语言音色描述，尝试清亮的青年男性/轻盈男高音声线，以及自然聊天式青年男声。两份新参考均真实生成，并对直接输出数组做同样的简要音高诊断，避免只换标签却完全不了解音区。

正文改成海边的普通风景叙述，没有闭眼、呼吸、放松等引导口吻。取消原来的高频搁架衰减，保留天然清晰度；不升降调、不加频率效果、不加背景声音。保留 0.75 倍慢语速、1.2 秒段间补足停顿、全篇恒定增益目标 -25dBFS、固定参考续读与正文 seed=42 / cfg=2 / steps=20。

两版在同一组文案和后处理条件下试听，标签是设计方向，不自动证明清亮、自然或更好。由于 TTS 更换参考，实际语调和段长仍可能变化，不能声称只更换了波形音色而绝对保留所有表演。

[可复现配方](../config/voxcpm2-bright-casual-audition.json)。使用专用 VoxCPM2 解释器执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'bright-casual-voice'
$env:PYTHONPATH = "$PWD\src"
$env:PYTHONUTF8 = '1'
& "$VideoAiRuntimeRoot/shared/envs/voxcpm2/Scripts/python.exe" -B -u scripts/experiments/voxcpm2_voice_audition.py --recipe config/voxcpm2-bright-casual-audition.json
```

新音色暂不提升为已接受音色。当前要求和候选路径记录在持久偏好；07 仍须在用户选定后冻结实际参考与相应处理条件。

## 本次选择与样本

初始两份新参考仍偏低，未继续将它们作为“清亮版”交给用户。随后仅做一轮三份较短参考的筛选，最高一份估计中位数约 149Hz。最初 150Hz 只是粗略试听启发式，不能把相差约 1Hz 当成质量或医学结论；因此复用该批中音区最高的一份 E-clear-tenor，而非为追逐任意阈值继续生成。参考设计 cfg=3.0 / seed=811，正文仍为 cfg=2 / steps=20 / seed=42。数据不是最终音色听感的替代。

该参考合成的自然聊天语气原本较快，相同 0.75 后处理不能保证与此前声音相同的实际语速。最终直接复用两段原始生成，统一 `atempo=0.6`，不用 EQ、升降调或底音，按处理后实际采样点重建段级时间；不重复 GPU 合成。

试听：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06-bright-natural/20261127-223108-308118/natural-slow-final/narration.wav`。[候选来源、诊断限制及最终参数](research/TTS-VOX-06-bright-natural-result.json)。只有这一份进入最终试听列表，仍待用户判断声音是否合适。150Hz 不是后续生产的声音准入条件。
