# VCO-03 AI接点事件实验 v3

本轮完成了校准侧的接点事件改进及核验，无需人工填表。复用原12个校准来源、120项控制与3项已测背景试验，未重跑原生像素测量；未使用原12检查源或Scott检查结果拟合。

| 检测项 | 新实验阈值 | 有效normal/anomaly | 原始接点覆盖率 | 校准TP/FP/TN/FN | 异常弃权 |
|---|---:|---:|---:|---:|---:|
| 动作突变 | 无值 | 0/0 | 0.0% | 0/0/0/0 | 5 |
| 相机跳变 | 10.948 | 18/3 | 21.6% | 3/0/18/0 | 8 |

这些是校准侧观察，不是新的独立准确率。新增真实检查素材没有满足准入条件，所以本轮没有新检查指标；没有复用Scott来制造“提升”结果。完整混淆矩阵、95% Wilson区间和题材分层见封存JSON。

## 为什么改

校准侧动作正例的关键接点没有有效测量，旧case p90来自非接点帧；因此整段高分无法证明检测到了事件。相机正常序列的极小波动又可能被近零MAD放大。新实验只看已声明parent_join，使用原生dt及工作像素残差，预先固定1工作像素噪声下限，并保留至少3个连续有效历史速度的要求。

缺失支持、声明变化、历史断档或部分接点缺失均保留不可比/弃权。新脚本不读取variant、recipe强度、truth或未来ROI；适用范围仅片段接点，不覆盖任意片内突变。生产核心、原颜色四项与前两轮输入/阈值/结果未修改。

## 证据与剩余问题

已验证6824个冻结证据文件；逐接点派生结果复算一致。26项测试通过，含接点缺失、原生不等dt、微小噪声和篡改producer/来源/digest/闭包的拒绝。代码审查发现的两项重要问题已在拟合前修正；最初冻结副本保留为pre-fit rejected，没有从中拟合阈值。

三个背景probe现绑定原producer的实测扩展区域计划、原脚本、AI区域草稿及717个比较分块，并核验闭包完成、source membership和request/control/dependency摘要。它们共享people02来源，不能按三个独立source计数。

接点没有可比较像素时，当前方法仍无法可靠判断动作；不能把丢跟踪当正常或异常。应继续补能在接点保留主体与背景支持的校准素材，并在另一个新来源上独立检查。相机固定噪声尺度对不同拍摄/帧率的适用性尚待验证，不能启用生产。

## 新素材筛选结果

复用了本地下载：NPS、Spring和BBB缺必要颜色声明，Shotstack orientation存在颜色冲突；旋转版与原版同血缘。已保存Shotstack仓库目录查询；ISO视频页和许可页两次有界请求均超时。没有猜颜色标签、重新要求用户下载，或将程序生成测试当真实视频验证。

## 文件

- [校准profile](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/experimental-calibration-profile-v3.json) · [封存阈值/原始接点解释](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/thresholds-v3.SEALED.json)
- [逐项分数](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/event-case-scores-v3.csv) · [接点覆盖与弃权](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/join-coverage-v3.csv)
- [实际冻结输入](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/inputs-v3r1.FROZEN.json) · [拟合前被拒冻结副本](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/inputs-v3.FROZEN.json)
- [来源筛选记录](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/bounded-source-search.json) · [代码审查及测试](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/code-review-v3.json) · [最终核验](D:/VideoSi/projects/video-ai/continuity-benchmark/AI-event-calibration-v3-20261026/delivery-final-check-v3.json)

所有输出production_eligible=false；普通profile校验实际拒绝该结构。未启动VCO-04。当前无需你填表。
