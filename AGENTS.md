1、生成视频的过程中不要过度校验
2、用户已确认 provided-reference-narration-v1 为后续所有视频的固定旁白音色。默认配方为运行根 shared/config/tts/default-narration.json，仓库冻结副本为 config/approved-narration.json；除非用户明确要求，不得重新设计、随机选择或替换音色。
3、保持已确认的 reference-prompt 参考续读、seed=42、cfg=2、steps=20、0.95 倍语速、850ms 段间停顿补足和 -23dBFS 全篇 RMS 目标；不升降调、不加背景音、不逐段切换情绪或声线。变速后按实际采样点生成时间轴。
4、当前正式 make-video 入口尚未接入该 VoxCPM2 配方。后续视频任务须先完成 TTS-VOX-07 接线或明确消费同一冻结配方，禁止静默退回旧 GPT-SoVITS 音色；不得把“已保存默认配方”说成“正式入口已自动生效”。已有任务继续使用其冻结快照，不原地覆盖历史旁白。
