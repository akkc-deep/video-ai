# 慢速、多段一致的男声旁白

**后续方向修正：** 用户反馈下述升调/减低频样本听着闹心、不够助眠，并明确选择低刺激、平稳柔和的纯男声，不加嗡鸣。已先查催眠声音及助眠音频研究，再重新设计轻声参考；[最新资料与纯男声样本](voxcpm2-low-stimulation-research.md)。下述链仅保留为历史试听，不是当前认可的最终配置。

**最新微调：** 用户进一步反馈“声音还是有点重，并且语速略快了点”。已复用原来三段真实 TTS 原始音频，将总语速从 0.8 降至 **0.75**（比上版再慢 6.25%），low shelf 改为 180Hz / **-4dB**，并用 Rubber Band **+0.75 半音、保留共振峰**轻提音高。全部段落使用相同处理，没有重新设计或生成声音。新样本：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06-consistent-voice/20261127-024911-055764/narration.wav`；[真实参数与时长](research/TTS-VOX-06-lighter-slower-result.json)。音色与语速微调仍待试听，前版语速的接受记录已根据新反馈撤回。

变速、轻提音高后，已按每段输出的实际采样点重新生成段级时间和合并旁白，没有沿用旧时间位置。最新持久偏好包含完整 `postprocess_filters`，该链从原始 TTS 段开始，已经包含 `atempo=0.75`，07 不得重复变速。语音参考、自然朗读表演和跨段一致性方向继续保留。

用户在试听后明确提出：“语速快了，多段之间的声音需要保持一致”。本轮沿用上一轮 B 的 `male-natural-documentary-v2`，不重新设计声音；用三段不同正文作连续试听。

**最新试听反馈：声音有点太低沉，其他没问题。** 因此保留 0.8 倍语速、男声参考、自然度和三段朗读，直接复用同一成品，只统一削弱 180Hz 附近低频厚重感 2.5dB，没有重新生成、升降调或改节奏。新样本：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06-tone-adjust/20261127-020030-943873/narration.wav`，仍为 48.922 秒；前后 PCM 采样数完全相同，段级时间继续有效。[音色微调记录](research/TTS-VOX-06-tone-adjust-result.json)。

用户已接受的语速、自然度和跨段一致性已写入最新持久偏好的 `accepted_dimensions`；只有减低沉的微调还待试听。`shared/config/tts/male-sleep-documentary.json` 当前指向 v2 的参考续读配方，并包含 `tone_filter=bass=g=-2.5:f=180:t=q:w=0.707`；07 必须保留相同全篇后处理，不能只照旧参考克隆接口重建。

## 固定方式

每段使用同一份 reference.wav、同一份参考原文，并同时传入 reference_wav_path、prompt_wav_path 和 prompt_text。每段固定 seed=42 / cfg=2 / steps=20，不按段更换情绪指令，不以刚生成的上一段不断替换参考。种子只是固定输入之一，不能单独代表主观音色一致性验收。

每段合成后统一使用 FFmpeg `atempo=0.8`，播放语速降低 20%，保留音高；不是将采样率改低。合并时共用一个全篇增益，不逐段另调音色或强压缩；段间静音只补足到 650ms，保留尾音。

按**变速后的实际采样点**累计每段 start_sample/end_sample 和补静音。该试听仅有真实段级边界，没有字级/句级强制对齐，也不按字数推算句级时间。07 接线时必须在变速后再完成下游对齐，不能套用变速前时间。

## 产物与使用边界

实验使用 `scripts/experiments/voxcpm2_consistent_voice.py`，保存 raw 原始段、segments 变速段、narration.wav 连续样本、tts-result.json 实际段级时间及 candidate-preset.json。

本次目录：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06-consistent-voice/20261127-014528-028691`，试听 `narration.wav`。三段不同正文均已实际生成，进程退出码 0；[实际时长、冻结参数和采样点记录](research/TTS-VOX-06-consistent-voice-result.json)。未自动判定听感通过。

新候选配方明确 `conditioning_mode=reference-prompt`、`speech_rate=0.8`、固定参考及禁止逐段更换指令；持久用户偏好记录所需语速、一致性规则和候选路径，仍保持 `needs_revision`，没有冒充用户已验收。旧的仅参考克隆服务尚不能自动重现该续读+变速配方，07 必须显式实现这些条件。

没有重新设计音色、生成完整长文或视频，也没有重复 ASR/全量回归检查。每次只作必要输出合法性和真实采样点处理；主观音色一致性与自然度仍由试听判断。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'consistent-slow-male'
$env:PYTHONPATH = "$PWD\src"
$env:PYTHONUTF8 = '1'
& "$VideoAiRuntimeRoot/shared/envs/voxcpm2/Scripts/python.exe" -B -u scripts/experiments/voxcpm2_consistent_voice.py --speed 0.8
# 只调速度时可复用本次原始段，不重复 GPU 生成：
& "$VideoAiRuntimeRoot/shared/envs/voxcpm2/Scripts/python.exe" -B -u scripts/experiments/voxcpm2_consistent_voice.py --speed 0.75 --reuse-from '<本次实验目录>'
```
