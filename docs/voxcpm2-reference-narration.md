# 按用户视频参考生成自然科普旁白

**用户已确认此版，要求后续所有视频使用同一声音。** 参考音频、已确认样本和完整配方已保存到稳定共享目录；[固定旁白规范与入口状态](approved-narration.md)。原试听来源继续保留。确认音色不等于正式 make-video 接线已完成。

用户提供 `C:/Users/qzw19/Downloads/test.mp4` 进行分析，并在分析后要求“继续吧”。本轮使用该素材中已分离的人声作为固定参考，生成全新的星空科普文案，不再依赖随机设计音色或强制提高基频。来源与身份不作额外推断。

## 参考与处理

采用先前分析中 300–330 秒的本地 UVR5 HP5 人声估计，再取开头 14 秒，统一为 48kHz 单声道 PCM16。参考文本由已有本地 Paraformer 转写，未逐字人工核对，分离残留也可能存在；因此不能声称参考是绝对纯净或转写完全准确。

两段新正文复用同一份 reference_wav_path、prompt_wav_path 和参考文本，固定 seed=42 / cfg=2 / steps=20。正文无哄睡指令前缀，按自然科普讲述组织句子，不升降调、不加背景音或频率效果。

与此前把整段拉至 0.6–0.75 倍的方向不同，本轮保留自然发音节奏，只统一 `atempo=0.95`、段间静音补足 850ms、全篇恒定增益 RMS 目标 -23dBFS。它们是试听制作设置，不是保证助眠的参数。每段起止位置按处理后的实际 PCM 累计，不伪造句级时间。

## 本次产物

试听：`E:/VideoAI/scratch/benchmarks/TTS-VOX-06-reference-narration/20261127-230050-146057/R-reference-narration/narration.wav`。

[实际参数、时长与参考来源](research/TTS-VOX-06-reference-narration-result.json)；[可复现配方](../config/voxcpm2-reference-narration.json)。14 秒参考文本和文件保存在原准备目录，源视频未修改。一个模型阶段实际生成两段新正文，进程退出 0，使用现有 WAV/采样点合并检查，没有追加完整视频、长时压力或生成音频 ASR 检查。

资产 `provided-reference-narration-v1` 现为用户已确认的后续默认声音；原始候选 preset 保留为历史试听记录，当前权威配方为运行根 `shared/config/tts/default-narration.json`。07 接入必须同时实现参考续读、冻结源摘要和这些实际处理参数，不能仅采用旧的 reference-only 服务契约。
