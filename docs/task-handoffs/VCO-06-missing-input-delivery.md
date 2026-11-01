# VCO-06 缺失输入补齐：新素材采集与观察入口

> **2026-10-29实际观察更新：** 新采集24/24及正式研究导入均已完成；用户完成当前12段development观看，13份实际导出已归档，其中10份正式未确认记录（9段）入库，3草稿保留。12段原生完整时间范围和用户全体观看报告已有记录；光照选择误解已由用户澄清并另存补充证据。0个已确认合格的已知轴自然偏色正例，不能进入阈值seal或候选。当前入口为 [实际观察接收结果](VCO-06-observation-intake-results.md)；下文的采集进行中、尚无观看等为原阶段历史。

2026-10-28。用户要求“你先把缺少的东西补上”，本轮由执行者准备新来源、冻结采集清单并实际运行本地 Wan，不要求用户另找数据。**本文件当前是采集进行中的记录；未取得实际结果的数量不记为完成，VCO-06仍BLOCKED。**

## 新的唯一入口

- 采集根：`D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261028-acquire-62d31ee3276941ecb65e35e23e4db250/`。
- 请求前冻结：该目录 `collection.FROZEN.json`，35818 bytes，SHA256 `55d624f985b95dedae2aefdb99e2712d8a26edf20afb67335f43994f577e7d74`；独立身份入口 `collection-receipt.json`。
- 实施及测试账本：[补齐输入计划](../superpowers/plans/2026-10-28-vco06-missing-input-acquisition.md)。

## 采集的定义和限制

已制作8张新的768×432参考图，图像制作时直接定义sRGB码值，PNG本身具有sRGB声明；不对未知来源照片事后贴标签。渲染器原始字节归档在新采集根，制作记录和实际模型输入逐项绑定。

场景组为陶瓷、几何块、折纸、木材、织物、石材、金属和石膏静物，每个原参考图预登记3个不同seed；组1–4固定为development、组5–8固定为holdout，共24项请求上限、每split12项和4组。相同参考图的不同seed始终属于同一组，不能算成3个独立场景组。组依据是新创建的不同材质/几何场景；所有图共用渲染工具及部分制作风格，统计独立性和适用域仍须在正式资格研究中审查，不能外推为自然摄影或六题材覆盖。

选择这个受限研究域的原因：本轮公共素材下载失败；普通Windows照片/壁纸检查未发现可消费的色彩声明；已用触摸键盘素材及其相关变体不能充当新盲测。这里交付的是**新的渲染静物参考及其真实、未经人工偏色的Wan输出**。参考图的程序制作不提供自然色偏标签，模型是否产生可修偏差仍由实际视频及完整观察确定，不能按构造直接计为正例。

每项请求固定49帧、原生16fps、768×432、无父片、完整输出；不截短、不换seed、不按结果补单。原始输出、HTTP POST受理、完整history、实际LoadImage输入、冻结options、graph及模型stamp保留。任何未知或执行失败停止采集批次，下一次只恢复原请求，不发替代POST。

`collection.FROZEN.json`冻结的是**采集计划**，不是尚未存在的完整 `inputs.FROZEN.json` 或正式资格 `protocol.FROZEN.json`。没有为未来输出填假SHA，也没有在seal前测量/查看holdout自然指标。

## 当前执行结果

8张参考图、24项请求清单及控制配方已冻结。第一项 `g01_ceramic_spheres_s01` 已提交并被真实Wan受理，prompt为 `bc520083-385e-4f17-bcd3-ad38b7ed7d58`；原run为 `D:/VideoSi/projects/video-ai/runs/20261028-213842-64956ee2381d`。实际采集命令运行中，日志：`D:/VideoSi/cache/video-ai/logs/vco06-acquire-preregistered-24-bf326f52ebfe4a518113736ed068f18e.log`。

此处不预记24段完成、正式研究导入或任何自然标签；完成数量和正式交付将在命令结束后追加。

## 已准备的观察入口

新增 `scripts/experiments/vco06_observe.html` 和 `vco06_acquire.py portal/observe`。实际视频完成后可导出开发集的本地原图/完整原片对照页；浏览器逐帧展示记录必须覆盖0–48，隐藏页面、跳转、倍速、暂停/缓冲或漏帧使完整记录无效。标签默认unverified，颜色目标、结构、动作、变光、已知修正轴和实际观察由真实播放者明确记录。

原始JSON由观察者显式保存，可从明确指定的Downloads等本地路径导入；验证、哈希和归档使用同一份原字节，媒体身份和播放时间必须与实际输出一致。所有失败/未知原文保留，不把浏览器遥测当作视觉语义真值，不自动生成已通过Precheck或改善结论。当前入口只开放development；holdout等待独立封存后的流程，不能提前在同一校准入口浏览。

当前工具无实际完整视频观看能力；浏览器测试仅证明事件/数据规则，**尚无新增实际观看者报告或有效自然正例**。

## 控制配方与软件证据

冻结配方包含identity、单轴±0.01/±0.02的linearRGB变换及已知逆变换、错方向、3倍过修、混合轴、固定区域局部改色、完整49帧时间正弦变化、裁切和16像素结构位移。量化规则和作用范围保存在采集计划，尚未构造/测量控制；控制不进入真实自然案例计数。

新记录、采集/恢复、观察校验及旧来源/CLI定向组：最终61 passed，27.10秒，exit0、无skip。日志 `vco06-acquisition-review-fixed-green-c3a39ab0c31448c18813ad45373c5422.log`。独立审查指出的来源路径、恢复、事务身份、配置搬迁、播放中断、归档竞争、下载路径及holdout暴露问题均在实际freeze前RED/GREEN修复；详细历史及更早失败见实施账本。

新事务校验器还对旧纸质素材真实POST/history/原输出做过只读验证，exit0，日志 `vco06-acquisition-original-transaction-check-73e8dbaeedc94110a749da486f5e3241.log`。旧输入568项bytes/SHA/mtime ticks及旧451项Python字节核对未变，结果保存为新根 `preservation-before.json`。首次PowerShell源码清单核对误包成嵌套数组，假差异报告保存在 `preservation-before-checker-error.json`；修正展开后对原基线复核通过，未更新基线。

未安装依赖、未运行全库回归、未改变旧r2、原输入包或生产来源协议，未发布或写Git。新采集完成也只补技术素材；正式输入冻结、实际自然标签、development校准/seal/一次holdout、合格profile及候选改善仍须分别满足原设计。
