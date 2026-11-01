# VCO-03 AI补充校准 v2 交付

本轮已完成，仍按用户选择的AI路线推进，**无需填写人工表格**。新增2项校准原样对照和11项新素材检查全部完整测量，0资源弃权；六项均有实验阈值。

新检查只有一个未进入原24源的Scott视频，不能据此声称通用准确率。原版24源/240项及检查侧保持封存。

| 检测项 | 实验阈值 | 新检查TP/FP/TN/FN | 覆盖率 | 端到端召回 |
|---|---:|---:|---:|---:|
| 接缝色彩 | 4.85805 | 2/0/14/3 | 100% | 40.0% |
| 局部色偏 | 8.41253 | 4/6/6/3 | 100% | 57.1% |
| 渐变色漂 | 8.41262 | 4/6/6/3 | 100% | 57.1% |
| 累计色漂 | 4.58277 | 1/0/2/1 | 100% | 50.0% |
| 动作突变 | 7.94478 | 0/0/9/1 | 100% | 0.0% |
| 相机跳变 | 38.34794 | 1/7/2/0 | 100% | 100.0% |

动作突变漏检唯一异常；相机跳变检出了异常，但9个正常判断中误报7个。局部色偏和渐变色漂也有误报，不能启用生产。累计/动作有效normal仅2/1条，仍需更多来源验证；阈值没有根据本次检查回调。

本轮只在独立v2副本修正角色与三段适用域，不能将分母修正称作算法提升。相机用整段有效分数max替代p90，仅改变实验聚合；原p90保留。生产16个软件文件身份未变，没有重复运行原108项软件测试。

已核验2,579组完整比较、155个比较分块摘要、336个中性原样RGB帧；原producer receipt、完整源闭包和先封存后检查顺序通过。7项轻量编排guard通过，独立AI代码审查无未解决Critical/Important。AI仅审过全帧顺序图和变体关键帧，不冒充真人动态完整观看。

新增case重算范围为13项，背景probe复核范围为3项。若未来异常发生在source receipt写出前，未认证case会拒绝恢复；本轮13项全部正常闭包。完整限制见下方补充记录。

- [完整报告](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-calibration-followup-20261025/README.md) · [HTML](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-calibration-followup-20261025/index.html)
- [实验profile](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-calibration-followup-20261025/experimental-profile-v2.json) · [逐项评估](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-calibration-followup-20261025/evaluation-v2.json)
- [最终核验](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-calibration-followup-20261025/delivery-final-check-v2.json) · [AI代码审查](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-calibration-followup-20261025/code-review-v2.json)
- [运行限制与证据范围](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-calibration-followup-20261025/operations-notes-v2.md) · [命令/退出码](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-calibration-followup-20261025/commands-v2.json)

输出production_eligible=false，普通profile校验实际拒绝；没有启动VCO-04。原正式benchmark状态单独保留，不要求用户为本AI路线补表。下一轮开发应优先在新校准材料中研究动作短事件聚合与相机误报，再使用另一个未调参来源检查；不能重用本次检查作为独立提升证明。
