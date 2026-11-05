# VCO-08 Native16 Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 真实验证768×432、16fps、四窗320帧资格样片。

**Architecture:** 从已接受native15案例的冻结源派生独立案例，新增纯协议模块与固定shape子类，保持官方采样路径。资源/一次采样/未知不重跑门禁沿用；新视频单独观看。

**Tech Stack:** Windows PowerShell bootstrap、stdlib Python3.12、既有嵌入式3.13/Torch2.13+cu130、原LongCat代码与模型/隔离依赖。

**Spec:** `docs/task-designs/VCO-08-native16-qualification-design.md`

## Global Constraints

- 用户已选“按建议直接推进，无需逐步确认”；本阶段直接执行。
- 不写.git、不新下载/文本编码/模型副本、不改旧案例；新目录`D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification`。
- CPU测试与GPU串行，监测现有回归session33919至退出，不修改其src/tests/scripts。
- 无执行时间/人工占用上限；原实际余量门槛不变；每窗最多一次，unknown不重采样。
- 固定93+80+80+67、320帧/16fps/20秒，13历史只输出一次，末窗裁尾13，不改官方数学。

## Review Focus

- 末窗13历史与13裁尾不能混淆；320输出映射每帧唯一。
- 实际模型条件须为父窗13帧，不能只改审计元数据。
- 480p/15fps旧资源或媒体证据不能满足新准入。
- 缺失文本缓存必须拒绝，不触发重编码。
- 旧intent/failed/unknown不能获得新采样机会；成功latent才可decode-only。

## Progress / Rulings

- 用户已明确连续推进；文档记录实施选择，不再加入设计批准等待。
- 既有dirty workspace授权与.git只读约束优先于skill默认worktree/commit流程；本计划仅文件变更、证据落盘，不创建worktree或commit。
- 当前native15整链已接受；native16所有真实技术/视觉结论初始unverified。

### Task 1: 新身份与纯协议

**Files:** 新目录`prepare_native16.py`、`native16_contract.py`、`native16_contract_probe.py`；复制27源所需小文件及原case/text binding/reference。

**Interfaces:** `window_mapping(stage)`返回raw93/context/append/chain/tail精确范围；`condition_shape(resolution, scale_factor_spatial)`返回(432,768)，仅允许432p-native16及可整除尺寸的正整数scale。

- [x] 写probe，缺模块运行RED；断言stage1..4分别[0,93)、[13,93)、[13,93)、[13,80)，累计320，非法stage/标识/scale拒绝。
- [x] 实现纯模块；原25源逐项SHA核对后复制，新case保存原文本来源；用原SHA证明文本/首图不变、权重复制/下载/编码0。
- [x] 运行probe GREEN，保存身份与命令结果。RED日志3ec7070、GREEN/准备34a4dce；新case SHA44bdb18c5eba8084a936b198d458d5b33f83bcd26f5fb11e010c4823fd5d0139。

### Task 2: 固定shape pipeline与执行源适配

**Files:** `native16_pipeline.py`、`native16_pipeline_probe.py`、新副本worker/media/resource/state/supervisor/freeze/admission/assemble。

**Interfaces:** `Native16Pipeline`只覆写官方`get_condition_shape`；worker/probe均使用该类。worker的prompt_context改为只读缓存；mapping统一消费Task1函数。media时钟固定16；新资源门禁核对实际VAE[1,16,4,54,96]、输出[93,432,768,3]、KV4076863488字节及部署clock16。

- [x] 原类对新分辨率入口RED；实现子类后官方i2v/vc入口形状路径GREEN，不进入采样。日志ff43f0b→6df5726。
- [x] 新目录替换硬编码480/832/60/104、stage上限、15fps及末窗mapping；不改官方working源或数值适配。9项修改及SHA保存在source-adaptation.json。
- [x] probe覆盖缺缓存/资源shape或clock漂移拒绝、最终mapping；真实tiny raw/viewing时钟与PTS通过。worker a9ccff9 RED→59882b5 GREEN，admission 9fe053f RED→a1f83f8 GREEN；media cd9b070通过。27源freeze与worker --check日志f042034退出0，software SHAe21f5a7ed34736e85acff28af8785a05a8b4a5837fd90dc69bcba898f65d96d8。真实多窗组装仍留Task3，不把fixture当资格视频。
- [x] 一次fresh-context只读审查新目录增量。native16_qualification_review无Critical/Important/Minor；9修改SHA及11官方源一致，review.json保留。Ruling：review在最终freeze前完成，review后未修改27项执行源；freeze/worker检查确认相同内容。

### Task 3: 资源准入与四窗实际运行

**Files:** 新目录资源/布局/准入收据、window001..004、chain004。

- [x] 当前CPU回归在会话中断后已退出：native33919不可用，41072/28172实际均不存在，日志无终态，不冒充4375项通过。原751通过及timeout修复5项保持；未知余项留软件收尾。Ruling：实际无CPU进程后推进已授权GPU资格，避免为缺失结果从头重启研究。启动时原余量守卫仍执行。
- [x] 运行五阶段真实新shape探针，无scheduler/视频，session59052退出0、211.4秒，结果full-dit-resource-probe-d9165fba1ae8445f861090cf92d1a1a0.json；最低commit5,278,523,392/物理18,981,482,496/磁盘53,038,338,048字节。layout日志278084d、final-admission b2f07be均退出0，27/11源及case/cache/资源/布局一致。
- [x] 仅清理已退出资源探针自有96个KV scratch叶文件共4,076,863,488字节；48元数据和逐文件SHA/清理收据保留，实际窗口文件0修改。日志090a1db，清理后磁盘57,114,968,064字节。
- [ ] stage1一次，核验技术+实际静态；无明显失败签发下窗screening，再按相同规则顺序stage2/3/4。失败停止，不重采样。

2026-11-03更新：上项原Q按失败停止，独立修复C现已四窗各一次完成且全数技术/实际静态通过；第三4161.422秒、第四4157.734秒。C四窗真实320帧/16fps/20秒已组装并逐保留区核验（chain integrity0f6708185220c1c9e77344dba098aac2376a9573b486563800a1ab226b070274）。新完整human_video问题已发出，动态接受仍未取得；该unchecked原项保留Q失败血缘，不将原Q写成成功。

当前stage1已于10:52:53+08启动一次，worker8684/supervisor3144/owner PowerShell3192，外层tool session54147，bootstrap日志af791da7f0b649eb903d3ef0e6630322。外层使用Start-Process -WindowStyle Hidden并持久化launch-intent/owner时间/日志；冻结的数值/监督执行源未改。只监测此进程，不以工具会话丢失代替worker已退出判断。首次0/50已进入真实采样，未预记视频通过。

Q实际于14/50以commit_reserve失败退出，无latent/媒体，failure-observation.json保留，27冻结源不改，不能重启Q。Ruling：依据用户已明确“按建议直接推进，无需逐步确认”及持续完成授权，对已具体修复并验证的资源故障建立独立技术续验C；这不是复用/清除原Q intent或无修复换seed重抽。保留原Q失败与新C血缘，明确累计已有1个失败native16采样；C仍各窗最多一次、同规格/同提示/同seed/同模型、不降低实际余量门槛。错误代价是新增这一技术资格案例的计算，故不能将此裁决泛化为无限随机重试。

C=Q/allocator-async-candidate-v1，case66ab2b4eaf48fc1adde81e8319c0384a33c93b7022baf5fd438bf832317077d0、software637d88ff64441e241d922585a4ca16cd279b7c0fe70575dea328083ed1302e93。原官方/数值适配23源保持；只4源改异步allocator选择/绑定及停止原资源快照。合成FFN输出逐字节一致，完整五阶段资源预检3407退出0，211.2秒；峰值reserved8,187,281,408字节（Q13,281,263,616），最低commit6,267,060,224/物理13,692,510,208字节。独立review唯一Important为layout提前导入Torch；实际RED3989d682→预置两个allocator环境变量后GREEN1d103b20，源码冻结未改。final-admission375c86c8退出0；probe scratch精确释放4,076,863,488字节，元数据/收据保留。proposal.json/candidate.patch为完整可复核结果。

11:45:42+08仅启动一次C首窗，worker20888/owner PowerShell7252，tool session2444，bootstrap日志397ff5ba403f481dbeec87e0c05a15fd；C/live-run.json为当前入口。后续只读原进程，不重启；成功后核验/实际静态，按已授权四窗继续，完整新视频动态接受另记。

C首窗12:56:45退出0，4263.735秒，93帧/16fps/768×432/raw逐像素一致；result849ff142563d9882c323f77aceae4277ee6c92672303a97419c925d7b172f3c3。实际完整性128170f7和静态cf586942退出0；screening2d1cfdf2bdb556b7c909988e5ef012e88ef48efc7c0233ea2ab528666ddb7236。实际接触图的曝光/构图风险留最终动态，不伪造新观看。12:58:02仅启动stage2一次，worker29840/supervisor28792/owner30652/tool69039；日志d7cbdfd13c034c9b83248d89ef4b6e31。当前只监测第二窗，stage3/4尚未开始。
- [ ] 组装320帧，核验实际SHA/13历史/48层真实KV/输出PTS与映射；提交完整20秒视频并等待新的完整动态反馈。
- [ ] 按事实更新实录/板、生产适用范围和后续接口设计；不把资格样片当VCO-08全部完成。

## Verification commands

2026-11-03续验：C第二窗已完整性/实际静态通过（详见research-results与live-run）。第三窗原worker3752于11:40:49+08退出0，4161.422秒；全部artifact和实际48层KV4,076,863,488字节完整SHA通过（26ece37d78544e2abba0913d7249d007），result b763f56a29e7832d88b3ae48f2d4184c2ef41ed8301161305fab7ccd78534463。实际静态已查看并记录后段明显变暗和腿/翼出框风险，screening69f063dd652bab4b4bf1234ec1f1ff1095401b143830842ff52d7fd3c3d6ec8a；动态unverified。11:42:25+08仅启动C第四窗一次（worker14808/supervisor9000/owner8536），不重采样前三窗。等待第四窗退出后verify/static与完整320帧组装/新动态接受。

每条Python经项目bootstrap；CPU合同probe：`Invoke-VideoAiNative $VideoAiPython @('-B','<new-root>/native16_contract_probe.py')`。pipeline/数值脚本使用既有嵌入式Python。真实命令按顺序为`full_dit_resource_probe.py`、`freeze_software.py`、`checkpoint_layout_probe.py`、`final_admission_check.py`、`supervise_window.py --stage N`及`assemble_chain.py --windows 4`。每项必须退出0并核对实际收据；研究完整动态接受另记。
