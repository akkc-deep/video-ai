# VCO-06 输入资格继续执行结果

2026-10-28T03:58:47.482845+08:00。**status=blocked，尚未达到 ready_for_propose。**

本次按“继续完成，直到可以使用”继续检查了已有织物段，并新增真实生成了中性纸质场景。新片段：[generated-native16.mp4](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-034811-31098b7f1402/generated-native16.mp4)；原选图：[selected-reference-srgb.png](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-034811-31098b7f1402/evidence/selected-reference-srgb.png)。这是技术素材，不是已经准入的校色输入。

两段均完整49帧、768×432、原生16fps，独立原选图在实际生成前已完成有源ICC依据的真实转换，实际模型输入字节相同；全部49帧VCO-02均ready、有效像素、明确sRGB、无音轨。新请求ID：`dde7b6f2-8c82-4b25-bc2e-9ea84cf75645`；本次只新增一次真实Wan请求，无未知请求重发。新自有服务已关闭。3,011个历史原件和436个既有软件/约定文件的bytes/SHA256/mtime_ns未变，旧原件文件集合相同；第一次素材包的原索引文件逐字节核对未变。

## 素材资格结果

| 项目 | 织物段 | 新中性纸质段 |
|---|---:|---:|
| 原选图/49帧色彩及像素 | 通过 | 通过 |
| 原图→原片自然配对 | 已产生49个reference测量，12 comparable、37 not_comparable；完整metrics/report输出超16MiB，保留失败现场，不能称完整报告闭包通过 | 先做首帧必要条件审计，ordinary报告闭包已核验；不是全49帧配对报告 |
| 首帧运行时同规则均匀取样 | 1024对 | 1024对 |
| 首帧原始p99 / max误差 | 20 / 38 | 9 / 24 |
| 所有封存合格方向最多可改动的单通道码值 | 3 | 3 |
| 修正后p99 / max的保守下界 | 17 / 35 | 6 / 21 |
| 原契约要求 | p99≤2、max≤4 | p99≤2、max≤4 |
| 当前已声明配对证据的准入判断 | 拒绝 | 拒绝 |

下界从正式r2 profile的最大合格幅度0.036521558455209775，按sRGB传递函数和原量化规则，对所有256种8-bit输入码值的正负增益端点求出最大变化，再用三角不等式计算。没有拟合算子、轮换轴挑最优、生成修复片或修改阈值。它只证明当前已声明ROI和所测首帧的必要条件不成立；不宣称已证明任何其他ROI或所有未来生成素材均不可能合格。

第二段首帧报告仅有1个比较，coverage中的ready_frames=2，指该报告实际测量参考图和首帧；其余48帧的VCO-02像素ready记录完整存在，不代表已经完成它们的自然配对。没有将首帧检查冒充全片准入，也没有裁短旧片或修改大小/帧数来绕过资源拒绝。

## 仍未完成

1. 当前两组声明配对不在封存修复域，不能靠补来源记录获得合格的自然改善证据。
2. 独立真实Wan素材仍缺正式生产来源导入契约；没有手写假schema2 Wan clip/ready receipt、旧冻结options或接受记录。
3. 当前epoch/assessment、完整合格pair manifest、真实完整播放观察及Precheck未建立；operation保持null。

原要求明确“不得重校准、扩大合格方向或改检测/修复阈值”，并要求“不改产品源码、校准冻结software或封存profile”。本次保持这些约束。继续需要在更换真实样本与另行设计正式导入/自然素材准入之间明确路线；当前证据不允许宣布完成。纯技术可解码不等于可校色，早先material_only索引不代表实际匹配已合格。

证据入口：[delivery.json](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-034811-31098b7f1402/delivery.json)、[qualification.json](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-034811-31098b7f1402/qualification.json)、[entry-residual-bound.json](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-034811-31098b7f1402/evidence/entry-residual-bound.json)、[上一段拒绝证据](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-033711-72d66bdba9df/evidence/rejection-analysis.json)。未改任务板状态，未调用propose/发布/全库回归或重校准。


交付目录：`D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-034811-31098b7f1402`。
