# LVA-02 校验复用与恢复结果

LVA-02 实现、离线基准及范围内恢复验证已交付，任务记为完成。**候选未默认启用**：它减少逻辑校验，但本次真实生产夹具墙钟变慢；按设计“候选无收益时保留 strict”处理，不认领生产加速。范围外旧测试失败保留在下文，没有宣称全库通过。

结构化结果：[LVA-02-results.json](LVA-02-results.json)。原始报告 `E:/VideoAI/scratch/benchmarks/LVA-02-validation-results.json`；只读补齐既有帧/PTS证据及目录放大样本的报告 `E:/VideoAI/scratch/benchmarks/LVA-02-validation-enriched.json`。全部操作位于新建 `E:/VideoAI/scratch/benchmarks/LVA-02-*` 或测试隔离目录，无 GPU、付费调用、原生产恢复或旧run修改。

## 实现与采用结论

`scene_validation_pass.py` 提供有界、线程内、fresh read-pass作用域。只在现存lease覆盖相同Artifact时捕获完整ByteGuard；命中仍验证可变依赖并重放外层capture。退出清空引用，checkpoint/窗口/线程/绑定变化失效。外层capture溢出不可修复；仅无外层的本地捕获超限可退出后strict重试。revision/temporal/来源视图、弱保护及畸形输入保持strict。

clip/media/composition的窄guard接线已实现，`candidate_scene_validation()` 仅供离线实验显式启用；**生产默认guard仍strict，不创建新的native read-pass**。不提供用户配置开关，不改持久化schema或旧任务身份。模型/tool、ownership、父片、HTTP、响应落盘及晋升边界均保留。`_technical` 的既有 `inspection_reuse()` 原样保留。

| 候选 | 实际结论 |
| --- | --- |
| 同guard Artifact memo | 强保护放大样本受益；默认夹具总体回退strict，不推广 |
| 同pass目录集合复用 | 放大样本4次扫描→2次（首查及退出）；默认夹具总体未获益，不推广 |
| clip/media同步guard | 各自fresh退出，strict marker跨窗口传播；生产默认strict |
| composition前后捕获 | 实验接线保留，默认strict；不认领未单独测量的合成收益 |
| 模型stamp/global/HTTP/晋升 | 无删除，次数不减；stamp是metadata，不是模型全文哈希 |
| inspect/trim/末帧 | 历史优化，不重做、不认领新收益；恢复完整验真 |

## 默认生产夹具四次对照

FFmpeg/FFprobe为真实工具；Comfy为内存transport，禁止网络和GPU。生产帧规划只允许fast 768×432或quality 1280×720，因此采用真实768×432、16fps及原预算，不为设计中的128×72修改生产约束。每侧4次、顺序交替、进程热；OS磁盘缓存及并行测试负载未控制。墙钟仅使用轻量计数器，完整profiler另采样，不能混合比较。

| 模式 | strict均值秒 | 候选均值秒 | strict Artifact工作 | 候选严格工作/证明命中 |
| --- | ---: | ---: | ---: | ---: |
| 正常生成 | 18.908746 | 20.756011 | 12,876 | 8,982 / 3,894 |
| 已完成恢复 | 3.767128 | 3.763768 | 891 | 891 / 0 |

正常逻辑严格工作减少30.24%，墙钟增加9.77%；恢复约0.09%的差别不解释为收益。profiler单独诊断：实际SHA均6,704次、71,891,585字节，媒体进程均79、probe38、完整验证解码64；恢复实际SHA均1,771次、59,468,319字节，媒体进程均34、probe17、完整验证解码28。模型/tool stamp正常952次、恢复28次；66次正常guard边界未删除。实际SHA/解码没有减少，不能将逻辑入口下降称为I/O节省。

四份诊断的全调用聚合均完整、观测错误0。两份normal原始事件明细分别超过上限35,982/32,088项，`complete=false`；两份recovery明细完整。这不影响已保留的聚合数字，但不能称normal逐事件追踪完整，也不为补明细重跑生成。

候选常规生产扫描计数不作为精确对比：原计数器未涵盖strict直接glob，而候选_scan涵盖该形式。该Minor限制明确保留；目录收益只使用新增同规则放大样本，原始数字不覆盖、不粉饰。

## 放大样本与内容证据

32个已有强lease Artifact，同一回调重复4次：严格128→32、证明命中96；原四样本平均约0.08734→0.05595秒。无window两侧均128次strict，约0.13235/0.13132秒，不解释微小噪声。另以空JSON目录重复4查的四次样本验证strict扫描4、候选2（含退出），弱保护仍4。**不跨独立socket guard共享memo**，不把该人为放大倍数用于生产。

每个normal/recovery样本记录原prompt ID、POST/GET/ensure、source/generated SHA及完整frame mapping。全部侧的source SHA一致；恢复的全部scene-clips文件集合和SHA保持，新增POST=0。实际完整逐帧PTS从本次既有video探测JSON提取，帧数与探测结论一致、每相邻PTS严格1/16秒；未重新decode。独立脚本结果提供每帧PTS、time_base、宽高和确切证据路径。

原benchmark未直接spy producer次数，JSON明确 `direct_producer_invocations=null`；正常成功producer数量由不可变media-ready receipt按operation分别记录，恢复无新增staging/receipt/输出。不能把receipt推导计数称为直接方法调用计数。新计数器已为未来复测加入producer spy，不为填这项字段重跑生成。

## 验证与已知缺陷

- 新helper/guard、clip记录、两类事务、真实socket发送、native lease及ByteGuard：214通过（7.79s）。
- 既有媒体性能：22通过、1项按设计排除（4.95s）。
- 新真实FFmpeg generated receipt中断、恢复及同大小mtime回滚篡改、两项超分prefix恢复：最终5通过（721.74s）。前一轮3通过（166.75s）仅为历史记录，不重复累计。
- 原恢复集最终：64通过、6失败、6排除（1649.92s）。合成原命令/产物晋升及缺失索引恢复测试通过；五个旧legacy Comfy测试仍在freeze之前被模型隔离路径拒绝，一个完整交付测试遇到既有reclaim清理问题。首次工具路径失败已修复；不继续扩展到legacy模型/交付锁实现，也不为收尾重跑完整媒体集。
- 补充连续性/本地输出恢复：50通过、3项旧路径夹具失败（2.16s），详见JSON known_failures。

已知排除/失败没有通过修改生产策略绕开：`test_owned_service_cache_identity_rejects_pid_reuse` 缺process_identity；六个 `test_public_preparation_refusal_is_blocked_without_identity_or_writes` 在未修改的verification.py:284先抛异常；三个continuity测试fixture落在E:/VideoAI之外，被未修改的 `_scene_continuity_io.local` 拒绝。没有宣称全库无失败。

最终原恢复集另外六项失败的定位：`test_production_comfy_recovery.py` 的lost/missing/multiple、local_history_key、changed_original_http共五项，其 `production_visual_helpers.configure_comfy` 覆盖隔离model路径为真实生产model路径，`freeze_inputs` 在进入本项前拒绝；`test_authentic_candidate_explicit_review_delivery_and_twice_readonly_prefix` 在故意篡改来源后触发旧 `SceneOutputLock._reclaim_guard` 清理拒绝，残留.reclaim使后续交付报 `output reclaim already guarded`。对应生产模块均未修改，默认guard已保持strict；不把这些结果写成恢复成功。

独立代码审查未确认剩余安全缺陷；Important报告证据缺口已补实际PTS和有来源限定的receipt统计，不能测得的直接producer计数如实为空。额外RED→GREEN修复了hit文件异常后memo未失效、原inventory拒绝信息和deadline异常类型。

## 限制

没有新GPU、1080P质量或整片吞吐结论。LVA-01已接受媒体与生产暂停状态不变；不改采样、服务调度、即梦、底层verification/protected-inputs或用户原有冷准入文件。候选默认启用被实测否决，后续任务必须保留这一决策。
