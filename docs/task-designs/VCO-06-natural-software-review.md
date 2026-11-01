# VCO-06 自然研究软件独立审查

2026-10-29。一次独立只读审查，agent `natural_software_final_review`；未运行测试、Python、媒体命令、网络或修改文件。审查范围为本轮新增engine/study/profile/candidate/CLI及定向测试，依据natural-software设计、natural-input设计和资格协议。历史冻结文件保持原字节。此记录不是自然资格或视觉改善结论。

## 发现与修补范围

审查共8项Important、0项Critical：

1. `failed=True`可绕过source/像素重放，却携带可被归约为正例的字段。改为互斥的精确success/failure schema；canonical失败只有unverified/failed投影，无preview；真实失败保留在分母，未知holdout标签/状态明确拒绝。
2. 原普通report校验器验证结构和闭包，未重算geometry；刷新shard/特征SHA可选择有利支持点。新只读helper以原RGB重跑既有 `_resolve_manifest/_ReaderProvider/measure_continuity`，逐项比较sampled_pairs、可比性、完整比较、轨迹、detector、帧及coverage；旧模块不改、不执行归档代码。
3. 被评分master帧未与master inspection直接绑定，playback可只列部分帧。改为精确库存一致、逐帧实际source/index/PTS与完整数量/顺序验证，master和playback分别完整读取。
4. media为空时terminal可自称技术/观察通过。改为精确持久状态和时序/必需Artifact约束；noop也重放真实稳定指标，reviewed仅由有效观察receipt推导。
5. 新修订可跳过一个失败sibling；只检查checks会漏掉非颜色confirmed_issue。改为全同源attempt检查，并同时消费checks、issues和risk disposition。
6. failed receipt可指向另一份passed观察而留下未核对的旧raw。共享loader同时校验SHA目录、原外部Artifact、保留原字节、receipt schema/时间及实际verdict；status和血缘共用。
7. study/assess可遗漏已登记的晚到结构/运动失败。改为完整已登记观察身份核对；holdout在seal前只比较opaque身份，seal后才解码观察语义；现有原作者内容不重写。
8. 每variant重新开始300秒，超时后仍启动后续控制。统一case/render/replay deadline，超时停止；多case的总时长不伪装成单case，独立元数据anchor在batch之后复核。

补充完整性回归：相同risk对象仅改变JSON键顺序，也不能冒充两条回应、遗漏另一风险。它属于第7项的精确回应覆盖，不扩大任务功能。

## 验证

具体RED/GREEN命令及日志位于实施计划Ledger。首轮11项单位回归失败；media漏帧/错序及几何重放缺失有RED；原master swap夹具复用了相同分析记录，被既有重复路径规则拒绝，因此改为另一份真实VCO-02分析记录后重新观察RED。没有把原本已通过的错误夹具当作修复证据。

随后63项unit及21项stage/真实CPU媒体/事务专项分别通过。最终完整定向回归、规定六文件兼容和实际16段保留复核以交付结果中的最终日志为准；不累加重叠测试，不把中断或fixture观察计为真实改善。按执行技能约定一次修补轮以回归验证闭合，不追加独立复审。

最终结果（2026-10-30）：194项定向597.45s、规定六文件178项兼容5690.52s均exit0，无skip；16段实际处置及6838原件、原pilot前54项基线复核exit0。额外success schema、单case与多case预算边界、重复风险回应、稳定noop负上限均有RED/GREEN，非零修复上限保持封存值。产品SHA与194测试中的独立库存一致；最终逐项日志见软件交付及计划Ledger。本次未留下未修Important或deferred minor；真实自然资格/改善仍未验收。

## 未作出的判断

Reviewer未独立核验6824文件保全审计、测试结果、实际视觉质量或source family语义独立性。真实自然数据尚不满足资格；当前无实际自然profile或改善通过。最大资源规模成功未被宣称；超预算须完整拒绝。生产边界沿用既有研究来源拒绝，软件测试和真实自然验收分别记账。
