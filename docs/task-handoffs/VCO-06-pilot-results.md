# VCO-06 四次静态展示试采结果

2026-10-29。用户要求继续新小批试采路线后，已完成方案、独立4次预算冻结、软件实现和实际本地Wan生成。**4/4段真实原片、4/4正式研究技术导入完成，共196个原生视频帧逐帧验证；实际POST恰好4次，无补单。随后已接收用户新4段观看报告及4份实际导出；未取得已确认的自然偏色正例，本轮按预定条件停止试采，VCO-06未完成。**

## 实际观看接收（2026-10-29）

用户报告“我看完了”；已找到 `docs/task-handoffs/p0*.json` 四份实际原文件，通过pilot原schema及真实生成事务/媒体/参考/集合/时间绑定校验入库，4/4返回unverified。原分类、作者、文字、47个实际回调与实际约3.06秒计时全部保留，没有补造49帧或将没有问题改记为正式中性标签。

| case | 用户原话 | 本轮处理 |
|---|---|---|
| p01_woven_display | 视频完全跟参考图不一致 | 原target/structure/motion均false，不能作为仅颜色缺陷的校色源 |
| p02_stone_display | 最左侧的掉下去图有点奇怪 | 固定物体意图下存在未解决的非颜色动作疑点；保留原勾选与文字，不自动判安全 |
| p03_wood_display | 没有问题 | 保留原片与未确认分类，没有报告待修色偏 |
| p04_tile_display | 没有问题 | 保留原片与未确认分类，没有报告待修色偏 |

本轮0个已确认已知轴偏色正例；未校准阈值、未生成自然profile或候选。试采按原方案停止，不自动追加请求，也不要求重看已完成的16段。这个结果不证明所有未来自然素材都不可修，只说明本批没有足够的实际偏色/已知轴证据支持资格或改善验收。

实际接收根：`D:/VideoSi/projects/video-ai/vco06-natural-qualification/pilot-audits/20261029-observed-e4f0aec9aa474349afa442783cd4bdbf/`；`pilot-observation-result.json`10920 bytes/SHA `fd42aa812602dd4eb5bb9aaf039d90da014a36ca278f4e2e5cf507eb18bd50f6`。其中保留原始导出副本、实际intake收据和独立用户观看补充；4个用户原文件bytes/SHA/mtime不变。日志 `D:/VideoSi/cache/video-ai/logs/vco06-pilot-actual-observation-intake-78b5eaad93f44426b5b35dcadc541022.log`，exit0。接收未修改产品源码或测试、未发新模型请求；旧delivery.json与下面的“尚未完成”是原交付时快照，当前以本节为准。

## 使用入口

- [本轮4段原图/原片观察页](D:/VideoSi/projects/video-ai/vco06-natural-qualification/pilots/20261029-stationary4-c2a7e6583ce44798be1753c5c6607d19/observe-pilot-04-c459d8cff3cb.html)
- [交付索引](D:/VideoSi/projects/video-ai/vco06-natural-qualification/pilots/20261029-stationary4-c2a7e6583ce44798be1753c5c6607d19/delivery.json)
- [本地说明](D:/VideoSi/projects/video-ai/vco06-natural-qualification/pilots/20261029-stationary4-c2a7e6583ce44798be1753c5c6607d19/README.md)
- 方案：[小批试采设计](../task-designs/VCO-06-pilot-design.md)；实施与验证账本：[pilot plan](../superpowers/plans/2026-10-29-vco06-pilot.md)。

本轮根为 `D:/VideoSi/projects/video-ai/vco06-natural-qualification/pilots/20261029-stationary4-c2a7e6583ce44798be1753c5c6607d19/`。

这4段为本轮新生成的纹理展示，预期固定相机、物体静止、照明稳定。无预期物体动作，不将“画面不动”冒充复杂动作测试；实际出现形变、多物体或时间变色仍须照实记录。它们全是development_seen，共用制作工具及布局，不作为4个独立盲测资格组，不提前查看旧holdout。

观察页光照问题已改为“生成目标是否要求灯光或曝光随时间变化”，明确区分原目标与实际观察到的意外变化。此前12段和13份用户原记录保持原字节，不要求重做旧观看。原交付时新4段观察未知，后续实际接收结果见上节，不将技术数据自动补成视觉结论。

## 实际请求与技术结果

| case | 新参考布局 | 原prompt ID | 结果 |
|---|---|---|---|
| p01_woven_display | 织纹展示 | d324a55c-c2cb-4e8c-a3d4-9bb64d66c5fa | generated / research_input_ready |
| p02_stone_display | 石面展示 | a20bbe1e-4290-44fc-8a2e-0f36ea2e3252 | generated / research_input_ready |
| p03_wood_display | 木纹展示 | 049a0530-c260-4072-827b-879e88d3524b | generated / research_input_ready |
| p04_tile_display | 瓷砖展示 | 2a89cfc9-3f3d-440d-b961-a1cf5a29fe14 | generated / research_input_ready |

每段768×432、49帧、16fps、完整3.0625秒，完整原始输出复制后SHA与模型输出一致。正式验证保留实际LoadImage输入、生成前参考/创作定义、固定workflow及参数、原options/manifest、唯一POST受理/history/output和模型stamp。参考图从创建时定义sRGB，不对未知照片补标签。

后续实际执行完整ffprobe/PTS核验、全部49帧sRGB解码、源证据闭包验证和正式research import。独立 `technical-native49/` 保存全部196帧的RGB均值、参考差与相邻帧差；**这些是未配准的原始RGB开发诊断，不是ordinary几何匹配、9×9资格指标、修正轴选择、阈值或视觉质量结论**。未生成校色候选、资格profile或生产采纳。

## 软件与原件验证

新pilot使用独立schema与加载器，旧24段加载器拒绝它。固定4个case、一个seed/参考、development-only，任何未知case/改prompt/改seed/改预算拒绝；完整原请求只恢复原ID。共享独占锁覆盖跨case/跨pilot整个模型生命周期，已有外部Comfy端口不接管。归档实际代码/可执行文件/Comfy入口/workflow解释器身份，每次调用重核；portal用内容寻址快照保留先前空/部分结果。

冻结前最终6文件 **98 passed，35.18s，exit0**，其中41项新pilot用例、57项相关原用例；日志 `D:/VideoSi/cache/video-ai/logs/vco06-pilot-final-preflight-e376c56de27b402b90b1199a7eda74de.log`。全部RED、审查发现及修复日志在实施账本。之后只对未冻结HTML作光照说明文字调整，JavaScript/schema未变；未把软件测试当作实际视频观察。没有在GPU推理期间跑测试。

54项原件（旧24段视频、8张参考、13份用户原导出、4份冻结采集软件、collection/页面及原r2 profile）bytes、SHA、mtime全部不变。结果位于 `D:/VideoSi/projects/video-ai/vco06-natural-qualification/pilot-audits/20261029-c2a7e6583ce44798be1753c5c6607d19/preservation-final.json`；同根保留更新前默认交接和任务板原字节。

实际采集服务已关闭，8188不再监听，pilot采集锁已释放。本轮没有新依赖、Git写入、发布或后继任务准备；4次新预算已用完，不自动扩批。主任务保持BLOCKED，Design/Handoff引用不变。

## 实际命令与身份

所有Python均先bootstrap、Initialize-VideoAiEnvironment，再Invoke-VideoAiNative，串行执行。实际日志根 `D:/VideoSi/cache/video-ai/logs/`：

- Freeze：`vco06-pilot-freeze-four-2e9d035f0ff74e468c9a88c4b6209a91.log`，exit0。
- Acquire all4：`vco06-pilot-acquire-four-493edbaa57e04d8289c166e3605cb971.log`，exit0。
- Prepare/import all4：`vco06-pilot-prepare-four-f01fdfcd9e8f4c2b8c273fb837e11750.log`，exit0。
- 全196帧原始RGB开发诊断：`vco06-pilot-native49-diagnostics-230b2a7d181c42c9b77bd6a886e562f3.log`，exit0。
- 原件保全：`vco06-pilot-final-preservation-1f2cab461c08440f9c2cdf5e2c539244.log`，exit0。
- 实际交付：`vco06-pilot-delivery-1e4758d42b7349e29613d034db8e89b3.log`，exit0。

`pilot.FROZEN.json`：12374 bytes，SHA `436605905d6177a6bec828cab028197a60387c3a81c21d2e504718245b4578d5`。

`delivery.json`：10433 bytes，SHA `f6da661c8707fbeba8efbf345fdf6979edc36ca2b42d981fc965ae9af2262e6e`。

观察页：24944 bytes，SHA `c459d8cff3cb3f12000f63cae335fdccd5b3943af889a24166faea0477aa6c21`。

接收新pilot实际导出使用 `scripts/experiments/vco06_pilot.py observe --root <本轮根> --observation <实际JSON绝对路径>`，具体bootstrap命令在本轮README。旧24段observe入口不能冒充接收新schema；原始草稿、未确认、真实缺陷和缺帧不得自动升级。

## 尚未完成

新4段实际完整观看、结构/颜色/已知轴判断未提供，不能声称试采已证明可校色。若仍是形变、局部/时间变色或没有偏色正例，本轮按真实结果停止；若存在适用来源，再以其真实标签和新明确预算设计完整资格输入。每split最低12段/4组、各方向跨4组正例、development→seal→一次新holdout及真实候选改善要求保持原值。完整资格阶段工具和自然候选消费者仍待实现；旧audit与本轮RGB诊断都不能替代它们。
