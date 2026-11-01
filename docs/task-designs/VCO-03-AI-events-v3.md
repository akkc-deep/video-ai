# VCO-03 AI接点事件实验 v3

用户要求继续自动推进，沿用AI校准、无需人工表格。原V1与v2输入/标签/阈值/检查结果均封存，不使用Scott或原12检查源开发、调参、重拟合。本轮不启动VCO-04或生产profile。

校准侧已证实：有效motion正例的接点没有原始分数，case p90来源于非事件帧；camera正常片段可因接近零的历史MAD而出现数百分。诊断文件为运行目录的calibration-only-root-cause.json。不能用整段max替换p90解决缺失接点，也不能把跟踪失败当异常。

实现选择：新增独立实验脚本，不改生产16文件。与“继续调原max阈值”和“立即替换生产核心”相比，此方案保留原结果，可单独核验接点覆盖与物理噪声尺度。该选择由执行者在既有自主授权内作出。

输入为原已验证points、control及源宽高。事件仅来自control.comparisons中的parent_join，不读取variant、recipe变换强度、truth、未来ROI或标注。适用域仅已声明接点，不声称能覆盖任意片内突变。按label.frame_interval过滤接点；声明变化保持not_comparable。

使用原生时间差，以短边比例不变且长边最大256的既有工作网格度量。subject使用原camera_compensated_velocity；background使用原camera_translation/rotation/log_scale，按中心/四角五探针重建位移场。时间窗口为既有0.5秒，需至少3个连续有效历史速度；缺失/非递增时间/不支持配准都会重置历史，不跨缺口拼接。当前位移减历史速度中位数×当前dt，得到工作像素事件残差；以max(1工作像素,历史位移残差MAD)归一。1px是预先固定的工程噪声下限，不依据检查集搜索；保留其未认证统计模型限制。

case聚合只取相关接点最大值；所有相关接点必须有效，否则score=null、state=unverified，保留逐接点原因及部分分数。角色不适用/无接点为not_comparable。所有frame-level原分数和前两版阈值保持不变。旧动作正例可能全部失去有效分数，阈值允许null，不能为了六项数值齐全引用非事件帧。

测试覆盖：平滑相机平移/旋转/缩放，极小噪声，单接点跳变，主体匀速与突变，不等dt，历史缺口，声明变化，部分接点缺失，角色/无接点，标签区间、非有限值及乱序/重复帧拒绝。测试先RED后GREEN，所有运行经bootstrap，输出在D:/VideoSi；不运行全库或模型/GPU。

校准重用原12源及v2三项背景probe，检查嵌套identity、原producer/source closure；仅动作与相机重算实验事件分数。原标签独立复制，不根据新分数改标签。沿用既有_fit_threshold且仅有有效normal/anomaly时允许拟合；先保存输入/脚本/参数身份，再拟合一次封存。

继续筛选未用于前两版的真实许可素材；已知NPS缺颜色、Spring/BBB未知、Shotstack orientation冲突不得猜标签准入，旋转版本不能当独立来源。若无新合格原生源，完成校准侧实验、测试、失败和候选证据交付，将新独立检查明确保留未执行，不重新使用Scott或以程序生成fixture冒充真实检查。

最终交付包括版本化参数、接点覆盖/弃权、阈值（可null）、校准混淆矩阵、逐接点解释及未执行的新检查记录。production_eligible=false且普通profile校验拒绝。数值改善仅称校准侧观察。
