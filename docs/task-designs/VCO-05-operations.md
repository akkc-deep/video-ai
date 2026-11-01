# VCO-05 隔离工具操作

工具入口：`scripts/experiments/vco05_whole_scene.py`。这不是生产make-video入口，不改变96帧保护或正式scene预算。

本次唯一实际执行根：`D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321`。更早first-trial目录是POST=0的发送前冻结快照，已有superseded.json说明，不作为第二次推理。

## 查看

先在仓库根执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco05-status'
& $VideoAiPython -B scripts/experiments/vco05_whole_scene.py status --root D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321
```

status只读，依次显示result/submission-result/intent/prepared中当前可用记录。原任务ID另见acceptance.json；进度见service.stderr，原始HTTP在http/，资源快照在resources/。不要用第二个root重交同一实验。

## 冻结与执行

prepare消费原run的真实图片准入、完整语义计划和VCO-01文本审查契约；生成新的独立目录。scene_id与契约是参数，不在通用代码编码题材。prepare只读源run，不请求模型。

execute核对所有冻结身份，取得本case锁和共享GPU锁，然后启动自有独立服务、核对监听PID及内置节点。模型搜索路径必须与冻结权重一致，extra_model_paths/同名影子文件拒绝；外部custom node hook关闭。共享GPU锁存在或端口被占用时不接管。

本次execute的执行授权只覆盖原定首例；重新准备目录不是重新推理的授权。持久化intent以后任何重进都不得再POST。结果不明时只查询原任务；进程崩溃留下的锁不自动夺取。不要删除intent/锁来获取新的发送机会。已知失败保留结果并停止。

## 媒体证据

日常观看使用 `review-playback.mp4`：H.264 High、8-bit yuv420p、faststart、320帧/20秒。`review.mp4` 是High 4:4:4 Predictive/gbrp无损RGB审计片，部分系统播放器不支持，不再作为默认观看链接。兼容版是独立CRF16压缩副本，playback-review.json记录其SHA和原始/无损证据血缘；原件不覆盖。

成功原片必须是精确321帧/16fps，全部实际PTS=i/16、固定尺寸及单个无声H.264流。审计提取全部321张原生PNG，映射只保留[0,320)，无损RGB审阅片恰320帧/20秒，并逐帧framemd5核对像素。

`audit --root <same-root>`仅消费原submission-result中的唯一映射输出，不重新生成模型视频。已完成审计重进会复核原片、审阅片、映射及每张原生PNG身份；媒体处理未完整完成时保留失败现场，不覆盖已有证据。

播放兼容修复后，audit会为已有无损审计额外创建兼容副本，或验证已存在副本的身份。它不需要也不会启动ComfyUI。旧case的执行代码SHA保留原值；新的后处理代码身份另记在playback-review.json，不用execute入口重新运行旧推理。

采样图samples.png包含源帧320作为丢弃尾帧诊断，审阅片最后一帧是源帧319。RGB统计为未配对码值分布，不能替代色彩解释或实际播放。没有实际完整动态观察时full_video_observation始终unverified；technical passed不构成生产准入。跨题材、更长时长、多窗续写及生产集成分别需要相应后续证据。
