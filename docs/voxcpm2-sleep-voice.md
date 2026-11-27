# 纪录片助眠男声

2026-11-27 用户纠正音色要求：“声音不对，我需要的是纪录片的旁白，用来助眠，需要男声”。上一版 06 克隆了旧的 `online-reference.wav`，通用叙事指令没有确保男声或助眠听感，不能把其技术验证当成用户接受音色。

本次已按**成年男声、温润中低音、舒缓平稳、轻声自然、情绪克制**生成独立新音色和短样本。当前状态是 **generated_pending_listening**，由用户试听判断男声听感及助眠适用性，没有自动标记音质通过。

**后续用户反馈：声音不够稳、不够自然。** 该版持久偏好现为 `needs_revision`，不是已验收音色。已提供[精简指令与参考续读的两版新试听](voxcpm2-natural-voice.md)，未自动提升新候选为生产默认。

## 试听与资产

- 新旁白：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06-male-sleep/20261127-011350-715610/audio/narration.wav`，**35.074 秒**，5 个独立单元，48kHz/mono/PCM16，1,683,568 个采样点。
- 独立音色资产：`E:/VideoAI/shared/assets/voices/male-sleep-documentary-v1-20261127-011350-715610/voice.json`，同目录 `reference.wav` 为 16.64 秒声音设计结果。
- 持久偏好：`E:/VideoAI/shared/config/tts/male-sleep-documentary.json`，保存可重定位的运行根相对资产路径、参考摘要、基础风格、gentle / 0.15 / 舒缓和 seed=42。
- [生成配方](../config/voxcpm2-sleep-voice.json)；[实测记录](research/TTS-VOX-06-male-sleep-result.json)。

参考音色通过 VoxCPM2 声音设计生成，不传入旧 reference_wav_path 或其他人的声音；之后实际用新参考通过现有服务和 06 长文模块合成短旁白。新 voice_id 为 `male-sleep-documentary-v1`，新参考摘要为 `65573cdeb3b1c7da1e40eb33913dc6452537e96d3061d7d9ba094d4553268daf`。服务启动一次核对和复制新参考，客户端绑定相同 voice_id 和摘要，不能复用旧音色缓存。

使用已有 cfg=2 / steps=10 / seed=42，关闭降噪和内部坏样本重试。新样本采用 gentle / 0.15 / 舒缓，固定基础风格，不将 awe/excited 等大幅起伏作为该助眠样本的情绪。没有重复完整长文、ASR 或视频验证；本次拥有的服务退出码 0。

## 显式使用

`freeze_voice` 和 `VoxServiceProcess` 现在都支持 `voice_profile`；相对路径相对于 runtime_root，绝对路径必须位于运行根。资产内 reference_audio 仅允许资产目录内的相对路径，启动时摘要不符即拒绝。未传新参数的历史调用仍保持原绑定。

```python
from video_ai.config import read_json
from video_ai.planning.speech import freeze_voice
from video_ai.voxcpm.process import VoxServiceProcess

# config 已显式选择 voxcpm2；生产编排接线仍由 07 完成。
preference = read_json(config.runtime_root/'shared/config/tts/male-sleep-documentary.json')
voice = freeze_voice(config, voice_profile=preference['voice_profile'])
controller = VoxServiceProcess(
    config.runtime_root, revision_state_dir,
    voice_profile=preference['voice_profile'],
)
# 05 规划必须使用 voice.base_style，助眠默认 gentle/.15/舒缓来自 preference。
# 06 使用 LongFormSynthesizer(http, voice, request_scope=...).synthesize(...)
```

07 接入时须消费这份用户偏好，不能继续悄悄选择旧 `existing-reference`；阶段内服务和 FrozenVoice 必须选择同一资产。没有覆盖旧 GPT voice.json、历史参考或旧旁白，模型默认后端仍未切换。

## 复现与验证

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'male-sleep-voice'
$env:PYTHONPATH = "$PWD\src;$PWD\tests"
$env:PYTHONUTF8 = '1'
& $VideoAiPython -B -u scripts/experiments/voxcpm2_sleep_voice.py
```

每次创建新音色资产和新样本，服务成功停止后才发布偏好；失败保留先前偏好并记录原因。声音设计前核对一次源码提交，不重复模型权重散列。当前实际生成所用提交与冻结提交一致。

新增 18 项测试；相关回归 **271 passed / 3 skipped，6.79 秒**，日志 `E:/VideoAI/scratch/logs/vox06-male-final.txt`。独立审查发现的相对路径、异常退出时偏好发布顺序、声音设计源码 provenance 共 3 项 P2 均经 RED→GREEN 修复。三个跳过项为 Windows 符号链接权限。男声、音色偏好和助眠效果仍等待真实试听，不以这些测试代替。
