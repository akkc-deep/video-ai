# VCO-03 AI实验校准交付

> **当前AI路线已完成：** 无需填表或重复下载。六项证据已集中交付，新几何通道90项完整结果、3个新来源一次检查、50项测试通过。相机新检查3项跳变全检出且12项正常无误报；动作仍有重播弃权，未启用生产。见 [最终交付](VCO-03-AI-final-results.md)。以下为历史记录。

> **最新v3接点实验：** 已完成校准侧接点聚合与工作像素噪声处理，26项测试通过；新独立检查未执行。见 [v3结果](VCO-03-AI-events-v3-results.md)。无需人工填表；本页旧结果保留。

> **最新AI补充校准 v2：** 13项新增结果完整测量，六项阈值均有数值；新单源检查中动作漏检1项、相机误报7项，如实保留。无需人工填表。见 [本轮结果](VCO-03-AI-followup-results.md)。原版结果以下保留。

用户已明确选择“ai校准的就可以，我不想填表格”。当前交付走AI实验路线，**不需要填写人工表格**；原双人正式benchmark另行保留，不阻塞这条已授权路线。

本轮24来源、240个控制位置均有结果：230个完成全原生帧测量，10个触及固定metadata资源上限并记弃权。完成54,730组比较、27,710个含固定参考的实验帧请求；失败case没有用部分帧替代完整结果。分组12校准/12检查保持原计划，先拟合并封存六项结果，再做一次检查。

| 检测项 | 实验阈值 | 检查平衡错误率 | 检查覆盖率 | 检查端到端召回 |
|---|---:|---:|---:|---:|
| 接缝色彩 | 4.8581 | 0.090909 | 0.592 | 0.69231 |
| 局部色偏 | 8.4125 | 0.1746 | 0.80233 | 1 |
| 渐变色漂 | 8.4126 | 0.30242 | 0.8046 | 0.75 |
| 累计色漂 | 无值 | 无值 | 0 | 0 |
| 动作/运动突变 | 无值 | 无值 | 0 | 0 |
| 相机跳变 | 8.9736 | 0.4375 | 0.33158 | 0.28571 |

累计色漂和动作突变缺少有效正常类样本，阈值保持null。相机跳变检查端到端召回约28.6%，当前偏弱。4个数值阈值不表示4项已经达到通用生产标准；这些是AI弱标签实验，独立准确率尚未证明。

原2,460条AI建议保持类别和理由，另480条新增源标签保持unverified，共2,940条；没有将qzw的整体正常转录当独立真值，没有编造真人、观看时间或裁定。新增4源使用独立AI annotation，原ROI/表格/视频不改。保留所有早期失败、旧快照和代码审查记录。

输出仅为experimental-profile，production_eligible=false；普通profile校验已实际拒绝其结构，没有启用生产告警或启动VCO-04。原正式benchmark未完成是独立记录，不再作为要求用户填表的理由。

- [完整结果](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025/README.md)
- [HTML报告](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025/index.html)
- [实验profile](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025/experimental-profile.json)
- [一次检查评估与失败明细](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025/evaluation.json)
- [最终核验](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025/delivery-final-check.json)

后续AI工作重点是补充两个缺类项目的可信正常样本与提高相机测量覆盖；须建立新实验版本，不能反复使用本次检查侧调阈值后仍称独立检查。无需用户补填表格。
