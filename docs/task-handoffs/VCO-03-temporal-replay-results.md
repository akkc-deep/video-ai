# VCO-03 时间片段重播补充工作交付

2026-10-26。本轮授权的 AI 补充实验已完成，你无需再下载、填表或确认。新增真实录制片段重播测量，保留已有六项成果；没有启用生产或 VCO-04。

新通道直接比较接点后约0.4秒内容与先前显示序列，避开旧跨接点刚性匹配对大姿态变化的限制。测量接收固定起点选区、像素、有效mask和原生时间，不读取配方、源帧映射或真值。静止、低信息和周期歧义保留弃权。

12个已有校准来源＋3个此前未测来源，各六控制，共90项全部完成。控制包含原样、实际动作片段重播、仅回放侧JPEG重压、仅回放侧编码亮度变化、连续渐变亮度、已建立循环；没有使用位置剪贴正例。

| 范围 | 总项 | 有标签项 | TP/FP/TN/FN | 有标签弃权 | 有标签覆盖率 |
|---|---:|---:|---|---:|---:|
| 校准 |72|48|12/0/20/0|16|32/48＝66.7%|
| 新来源一次检查 |18|18|9/0/6/0|3|15/18＝83.3%|

阈值0.7365891044951167先封存，随后才检查狗饮水、Shotstack海浪和Spring人物近景。每个来源的三种重播均检出；六项原样/渐变光照无误报，三项已建立循环因周期歧义弃权。Spring原森林选段经逐帧检查缺少可辨角色，测分前改选同片连续人物近景，所有原始选择和依据保留。

校准另有24项因动作/身份可见性不充分而标为unverified并排除，其中18项仍有测量值。总测量覆盖率50/72＝69.4%，不能与有标签覆盖率混同；既有评估字段`unverified=16`指有标签测量弃权。12个校准正例变体只来自4个原始来源。

9个新正例变体只来自3个原始来源：狗为实拍动物，海浪为场景非刚性运动，Spring为动画。评估JSON中的行级Wilson区间仅是相关变体的名义摘要；源级3/3成功的描述性95% Wilson区间为43.9%–100%，不能据此声称六题材普适准确率。该通道识别字面录制片段重播，不认证人物身份，也不覆盖新生成动作的所有语义重置。审核明确来自AI静帧序列，未冒充真人动态观看。

62项定向测试通过，90份原始结果/receipt、6252个显示ROI帧摘要、原生时间、冻结标签/阈值、嵌套工具和构建身份核验通过。一次独立审阅提出的证据绑定、分母、相关区间三项Important已通过附加只读验证及报告修正解决。Spring额外remux日志仅记录当前身份，不补造历史摘要。冻结检测程序和新检查结果未改动、未重测。

原生产16文件、历史16核心产物与上一轮最终5核心产物保持原字节。全库回归仍按项目约定留在VCO-08。本轮是完成的AI研究交付；普通生产profile校验实际拒绝该格式，原正式双人Benchmark状态不变。

- [完整交付说明](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026/README.md)
- [逐项分数CSV](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026/case-scores.csv) · [评估JSON](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026/evaluation.json)
- [最终只读核验](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026/readonly-final-verification.json) · [审阅及处理记录](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026/final-review.md)
- [冻结输入](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026/inputs.FROZEN.json) · [封存阈值](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026/thresholds.SEALED.json) · [素材许可和署名](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-temporal-replay-20261026/source-rights.md)
- [此前六项成果](VCO-03-AI-final-results.md) · [本轮计划与执行记录](../task-designs/VCO-03-temporal-replay-plan.md)
