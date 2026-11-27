# 已确认的后续视频旁白

用户确认：“用这个音色吧，后面所有视频都按照这个声音生成”。选中的是上一轮 35.156 秒参考版，不是此前随机设计、气声哄睡或升调版本。

- 固定 voice_id：`provided-reference-narration-v1`。
- 正式保存的资产：运行根 `shared/assets/voices/provided-reference-narration-v1/voice.json`，同目录 `reference.wav` 与 `approved-sample.wav`。
- 唯一默认配方：运行根 `shared/config/tts/default-narration.json`。旧候选偏好文件 `shared/config/tts/male-sleep-documentary.json` 已同步为该已确认配方。
- [仓库冻结副本](../config/approved-narration.json)；[确认与冻结证据](research/TTS-VOX-06-voice-approval.json)。

参考文件已从临时试听路径复制到共享资产区，参考音频内容与已确认配方的 SHA256 一致。此后不能因 scratch 清理、重新试音色或更改全局提示而悄悄换掉声音。

## 冻结的生成方式

同一参考音频同时用于 reference_wav_path 和 prompt_wav_path，固定参考文本。每段固定 seed=42、cfg=2、steps=20，正文不加逐段情绪指令或哄睡前缀。统一 `atempo=0.95` 一次，段间按已有静音补足至 850ms，全篇恒定增益 RMS 目标 -23dBFS。无升降调、无背景音。时间轴在处理后按实际 PCM 累计。

`recipe_sha256` 标识以上声学输入和模型/源码版本；参数、参考或处理方式有变化都应形成明确的新配方，而不是继续冒称同一已确认版本。固定种子不是跨设备/版本逐字节一致性的承诺。

## 入口状态

**本次完成了用户音色确认、稳定资产保存和默认规范冻结；正式 make-video 自动入口尚未完成接线。** 当前该入口仍使用旧 TTS，并明确拒绝 voxcpm2；现有 Vox 服务也只有 reference-only 生成路径，不能单靠选择新 voice.json 复现已确认的参考续读试听。

TTS-VOX-07 必须接入这份配方：冻结模型/参考/参考文本/参数、支持 reference-prompt 模式、拥有服务生命周期、处理语音单元与实际时间轴、保留缓存恢复语义，并保证新任务不再隐式使用旧音色。AGENTS.md 已记录这一强制规则，禁止将只保存配置说成自动入口已生效。

已有任务保持原冻结后端和音频。若需要给历史视频换旁白，应新建修订并重建受影响时间轴和下游产物。
