# VCO-07 验收汇总

当前状态：**COMPLETED（2026-11-01 06:14+08）**。实际源片、463帧超分、完整成片、真实用户最终反馈、正式final_review_ready、独立发布和零新增重放全部成立；任务板已按IN_PROGRESS -> COMPLETED登记。closeout session23458正常退出0。

## 已取得的实际结果

| 项目 | 结果与证据 |
|---|---|
| 目标运行 | `D:/VideoSi/projects/video-ai/runs/20261029-202326-3adf41844095`，保留原修订、图像、PCM与字幕 |
| 三段源片 | 219/110/134保留帧，总463帧，16fps；各自真实完整观看与当前连续性准入已接受，原源模型POST总计3 |
| 超分 | 463/463帧、1920×1080，04:43:56完成；全部463原intent/submission，保留旧129帧并新增334帧 |
| 实际吞吐 | 最近20帧平均2.75616843秒；旧均值222.071419秒，约80.57倍；此为连续帧吞吐，不含一次性恢复启动 |
| 成片 | `production/scene-composition/candidate.mp4`，28.9375秒/463帧，37404418字节，SHA256 `8de8460233e5735d1cd8c7fa1fe4709447ec3f9f0d6f07adc299452ec59ce832` |
| 技术结果 | `candidate-commit.json`的原文覆盖、原PCM样本、帧映射、字幕、最终媒体检查均passed；完整原PCM保留，并按原帧时间轴保留尾部静音填充 |
| 最终用户反馈 | 原话“视频配音都没有问题”；对完整播放、全部旁白、字幕文字和同步的补充确认回复“继续吧 没问题”。依该上下文登记正常；仅有整片级反馈，不添加逐秒或逐场景细节 |
| 观看时间记账 | 2026-11-01T05:27:47.881391+08:00为最终确认记录时刻，不声称存在用户给出的精确早先播放时间 |
| 正式发布 | 交付回执delivered_at为2026-11-01T06:04:05.512082+08:00，movie/subtitle/receipt均实际写入，publish返回delivered |
| 同run重放 | 再次普通make_video返回delivered；无新增模型提交或邮件尝试，交付原件、回执、目录字节、mtime和文件身份保持不变 |

源片按各自原图比较；第三段的原图为飞行姿态，第一段水中站立图不作为第三段动作姿态约束。源观看与最终成片观看分别保存。

## 软件与用户覆盖的检查边界

版本化whole预算、旧分支兼容、原intent恢复及实际输出验证沿用已记录的定向与集成证据，详见VCO-07-verification.md、operations及各范围审查报告；不重复运行既有通过批次，不把软件夹具当实际观看。

用户明确“把这些检验都去掉，没有用”后，whole媒体移除每次写入/发送的全量依赖、inventory、父目录及工具审计，以及逐帧object_info。原RunLock、请求身份、不可变落盘、原任务恢复、实际PNG验证、最终人工接受和独立发布继续使用。移除范围先8失败2通过，相关最终128项10.23秒通过；退出进程保留句柄导致活锁误判的实际RED后，相关42项1.51秒通过。同一范围独立审查无遗留Critical/Important/Minor。全库仍按用户要求留在项目最终收尾，不计本任务已运行。

## 实际证据位置

- 生产、合成结果：`D:/VideoSi/projects/video-ai/vco07-diagnostics/without-media-rechecks-phase-214d9d35e305419d8398ef4b05b9a0d5/result.json`。
- 实际吞吐：同phase的`completed-throughput.json`。
- 原话与确认来源：`D:/VideoSi/projects/video-ai/vco07-diagnostics/confirmed-final-observation-c9cd532c8be54ce898b288d2db568cbc/feedback.json`。
- 本候选作者观察文件：同目录`observation.json`；05:44:14正式消费返回final_review_ready，接受回执为目标run的`production/scene-composition/final-observation-accepted.json`。
- 当前收尾调用：session23458，日志`vco07-final-accept-publish-replay-0f464bb57d4a4c52bc46316523453a21.log`；phase `final-film-closeout-phase-aaf18f158320412da5246c30e90908e5`，按实际观察消费、显式publish、普通同run重放顺序执行。
- 最终闭环：上述phase的`result.json`，06:14:12.990913记录complete=true、new_model_posts=0、new_mail_attempts=0、两项replay保持证明true；原源POST3、超分POST463。

## 正式产物

- [成片](D:/VideoSi/output/video-ai/20261029-202326-3adf41844095.mp4)：37404418字节，SHA256 `8de8460233e5735d1cd8c7fa1fe4709447ec3f9f0d6f07adc299452ec59ce832`。
- [字幕](D:/VideoSi/output/video-ai/20261029-202326-3adf41844095.srt)：343字节，SHA256 `8bccc3e8c62996eed6877f14d086761831df83d1e4233cd42b494c4956344322`。
- [交付回执](D:/VideoSi/output/video-ai/20261029-202326-3adf41844095.delivery.json)：1450字节，SHA256 `3d49e91625c43f72ed1af534d9020529e5857ce133475dd09b0a468d19ffeedb`。

06:14:28已重新读取正式三文件并核对SHA；与闭环证明一致，run/GPU锁均已释放。VCO-07无剩余验收项。本轮用户限定完成当前任务；VCO-08的新正式时序协议和独立真实试验前提仍未成立，保持原状态，不以本任务结项替代其设计或资格。
