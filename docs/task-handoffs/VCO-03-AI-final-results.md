# VCO-03 AI路线最终交付

> **后续补充（2026-10-26）：** 已完成独立的字面时间片段重播通道，3个此前未测来源的一次检查TP9/FP0/TN6、周期弃权3，覆盖率83.3%。见 [重播补充交付](VCO-03-temporal-replay-results.md)。下文原六项封存结果保持原口径，不能用补充通道替换旧动作分数或推断一般动作语义已解决。

用户选择的AI实验路线已完成，无需填写表格、重复下载或逐轮确认。保留原色彩四项结果，新增动作/相机几何实验已完成12源校准及3个新来源的一次检查；固定90项控制均有结果，其中90项完整测量、0项运行失败。

| 项目 | 实验阈值 | 检查来源数 | 检查覆盖率 | 检查端到端召回 |
|---|---:|---:|---:|---:|
| 接缝色彩 | 4.8581 | 12 | 59.2% | 69.2% |
| 局部色偏 | 8.4125 | 12 | 80.2% | 100.0% |
| 渐变色漂 | 8.4126 | 12 | 80.5% | 75.0% |
| 累计色漂 | 4.5828 | 1 | 100.0% | 50.0% |
| 动作/位置突变 | 11.273 | 3 | 57.1% | 40.0% |
| 相机跳变 | 13.5 | 3 | 100.0% | 100.0% |

四项色彩来自原封存的sRGB实验：前三项为原12检查来源，累计色漂为Scott单源补充检查。两项几何来自此次3个NPS新来源的原生亮度平面；六行不能合并为一个统一准确率或同一套生产阈值。

## 这次真正补齐的工作

几何通道15个来源的完整原生帧包、90项六变体控制、180条冻结AI判断、72项校准控制、18项新检查均已闭环。阈值先封存，之后才运行NPS bison/wolves/railway检测；没有根据新检查回调阈值，没有重跑原12源/Scott检查。核验10,368个控制帧请求、10,278个相邻/接点比较，1,728个原样亮度帧摘要一致。

相机新检查TP/FP/TN/FN=3/0/12/0，异常弃权0；在这3个场景中检出了全部注入相机跳变，正常项没有误报。不能外推为任意视频的100%准确率。

动作/位置项TP/FP/TN/FN=2/0/6/0，异常弃权3。可测正例主要来自合成主体ROI位置跳变；时间重播仍缺有效支持，不能声称自然动作重播已解决。分变体、题材、覆盖、弃权和95% Wilson区间均保存在评估JSON中。

## 为什么没有再要求下载/填表

复用了已有公开许可NPS原文件。它们的颜色声明仍不完整，因此只提取原生编码Y平面做几何分析，未猜色彩标签、未进入色彩四项准入。AI审过全部原生帧顺序图和各变体四关键帧，作者来源明确，不冒充真人动态完整观看。

为了跨接点匹配，新增隔离SIFT对应和工作像素事件评分；至少12内点、4分布网格、patch匹配及重叠门槛保留。校准时发现归一化float32多边形求交会把近乎重合区域误算为零，已在实验模块改用float64裁剪，真实矩阵回归RED→GREEN。没有降低匹配门槛，生产16文件和前三轮核心产物保持原字节。

## 如何使用本次结果

这是完成的AI实验交付，production_eligible=false，普通profile校验实际拒绝。可用于离线诊断和后续研发，不能作为生产自动放行、自然动作语义保证或正式双人benchmark验收。没有启动VCO-04，也没有要求你做额外人工操作。

- [六项实验profile](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/experimental-profile.json) · [新几何一次检查](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/stable-overlap/geometry-evaluation.json)
- [新几何封存阈值](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/stable-overlap/thresholds.SEALED.json) · [冻结输入](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/stable-overlap/experiment-inputs.FROZEN.json)
- [逐项分数CSV](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/geometry-case-scores.csv) · [来源及许可](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/source-attributions.json)
- [AI标签和理由](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/stable-overlap/AI-labels-before-fit.FROZEN.json) · [90项审阅材料索引](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/control-review-index.json)
- [最终核验](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/delivery-final-check.json) · [代码审查和测试](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/code-review-and-tests.json) · [命令日志](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-continuity-final-20261026/commands-index.json)
