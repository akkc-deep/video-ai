1、生成视频的过程中不要过度校验
2、用户已确认 provided-reference-narration-v1 为后续所有视频的固定旁白音色。默认配方为运行根 shared/config/tts/default-narration.json，仓库冻结副本为 config/approved-narration.json；除非用户明确要求，不得重新设计、随机选择或替换音色。
3、后续新视频保持 reference-prompt 参考续读、seed=42、cfg=2、steps=20、0.95 倍语速、500ms 段间静音补足和 -23dBFS 全篇 RMS 目标；不升降调、不加背景音、不逐段切换情绪或声线。统一使用“下面继续讲述。”作为可丢弃的合成上下文，按变速后音频的长静音边界移除引导语及段首残留，再只对实际交付的原文正文测量时间轴；禁止把引导语写入旁白或字幕，禁止用含残留的整段强制对齐结果决定裁剪位置。
4、TTS-VOX-07 已完成正式 make-video 配方接线，运行根 shared/config/production.json 已显式启用该旁白。新任务冻结配方和参考资产并使用 VoxCPM2；禁止静默退回旧 GPT-SoVITS 音色。已有任务继续使用其冻结快照，不原地覆盖历史旁白。TTS-VOX-10 已完成安装迁移、显式默认切换和备份回退，使用说明见 docs/voxcpm2-installation.md；完整视觉视频验证仍属 TTS-VOX-08。
5、用户已确认“后面的视频都按这一版来”，指 output/旅行者2号/完整重配音-20261128/旅行者2号-完整重配音.mp4（12分02.75秒，137段全部重新生成）。持久批准样本为 shared/assets/voices/provided-reference-narration-v1/approved-production-20261128.wav；批准记录为 shared/config/tts/approved-full-narration-20261128.json。此版本取代旧850ms默认；旧任务仍按自己的冻结配方处理。
