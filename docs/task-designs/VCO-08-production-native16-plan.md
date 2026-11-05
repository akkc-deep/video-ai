# VCO-08 Production Native16 Implementation Plan

**Final status（2026-11-04）：Tasks 1..7 complete。** 主五项Acceptance见[最终验收证据](VCO-08-production-verification.md)。当前源码五阶段真实资源/正常exporter已通过，生产准入SHA1e56f31d5bb2c885342d250daaf9209bc38ff21383c9f3226cfbb30eac5c8d47；逐节点覆盖账SHA4afb0b07350ff1e1b6961539237ab16e8016217134369b94291ece77fcd05a67核对5326唯一节点、未知0、未解决失败0及最终全部源码SHA。以下原未开始/运行中条目为历史账本，任务步骤已按真实证据勾选。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入真实13帧历史条件的temporal_extension_v1，完整保留时间轴与旧冻结协议。

**Architecture:** 纯时序预算与独立native事务/worker/观察分流，复用固定数值核心及既有下游入口。一次采样和成功latent解码恢复分开，静态窗口与完整动态chain分账。

**Tech Stack:** PowerShell bootstrap；父Python3.12 stdlib；既有嵌入式3.13/Torch2.13+cu130；固定LongCat核心和原模型/缓存；既有FFmpeg媒体与VCO-04策略。

**Spec:** `docs/task-designs/VCO-08-production-native16-design.md`

## Global Constraints

- **执行前置条件：** C四窗/320帧技术与真实静态已于2026-11-03通过，用户新完整动态回复“视频没问题，继续吧”，接受已绑定SHA。当前原4375 CPU回归退出前保持src/tests/scripts身份；随后直接执行以下源码任务，不新增确认。
- 用户已选“按建议直接推进，无需逐步确认”；资格通过后按本计划直接实施，不加入新的设计批准等待。
- 不写.git/reset/stage/commit/worktree，不关闭用户应用/改pagefile、不升级Comfy/生产Torch、不下载或复制权重、不重编码已有精确缓存。
- .git只读优先于skill默认worktree/commit流程；在已授权dirty workspace工作，命令/源码身份/裁决写本ledger及D:/VideoSi证据，不清理其他任务工作区。
- CPU测试/GPU串行；冻结的C27源不能修改。每窗最多一次；unknown不重采样、成功latent才decode-only。
- 执行时间/人工占用上限为null；原实际空闲余量守卫保持。生产长度由完整timeline推导，320仅实际观察范围，不能截短原叙述。
- native source固定768×432/16fps部署时钟、93原生帧/窗、13历史/4历史latent、50步/CFG4/官方scheduler；无LoRA/量化/compile/FFN切块/math回退。

## Review Focus

1. 原生输入确为父raw13像素，而非单图/审计字段；测试捕获13个不同帧的实际provider参数。
2. 生成请求不能预引用未来human接受；静态不升级动态，单次整链观看不伪造多次独立事件。
3. 旧schema/whole guard不能借新mode或未知对象放宽；旧预算/图/配置精确恢复。
4. unknown原进程及partial commit不重复采样；成功latent仅恢复解码。
5. 无执行时间/占用配额，但真实资源停止、源漂移/过期观察拒绝和完整PCM/字幕贡献保持。

## Ledger

- Task 1: complete — 纯native预算、schema2 execution/schema3提示/schema4 rendering identity及旧字段兼容，最终节点证据见C/regression-final-coverage.json。
- Task 2: complete — 复用既有27源固定bundle，当前8源五阶段资源与正常exporter生成独立ready准入；0模型下载/复制/文本重编码。
- Task 3: complete — 原生request/sample/result、raw13/RNG/static父绑定及静态/整链观察独立，最终native records/observations/chain验证通过。
- Task 4: complete — owned worker/prepare-cache、unknown不重试、成功latent仅解码、真实余量停止及allocator导入顺序；当前c8da3bd7五阶段complete/worker和runner真实exit0。
- Task 5: complete — 显式生产入口及320/334四/五窗流式CPU事务、每窗一次与同run重放0新增采样，fixture_only标记保持。
- Task 6: complete — 跨run整场景和局部父窗继承、混合新链观看、原事件不变、完整PCM/字幕和真实CPU媒体，以及计划旧兼容覆盖均通过。
- Task 7: complete — 正常生产准入、5326逐节点/最终源码核对、重要审查修复、diff --check及五项Acceptance完成，任务板IN_PROGRESS -> COMPLETED；无后继，不发布。
- Final: fixed Important1/2/3 — 已有各自真实RED→GREEN和最终覆盖，未处理Critical/Important/Minor均0；保留唯一独立review，不派复审。
- Final verification — 1768批1754 PASS/14 FAIL经108 GREEN解决；659批658 PASS/1 FAIL经21 GREEN解决；源码前后/列表SHA稳定，5326唯一节点全部有有效PASS证据，旧失败/中断历史保留。正常exporter与verify_final_coverage.py日志vco08-production-admission-final-49c1e3f00363453884d30eb4991be482均实际exit0。
- Workspace — 按既有.git只读和不commit/worktree约束保留当前工作区及所有证据，不执行整合或删除。

- Production builder check：native16_production_builder_check只读对照原五项Acceptance及context/预算/VCO-04/media guard/revision origin，结论 **nothing important left**；未运行测试/GPU或修改文件。schema精确字段/分流位置由本计划落实，不再请求用户逐步确认。
- Ruling：生产不加320帧硬上限。资格观察范围和请求完整timeline分开；原生每窗形状不变，超出观察长度仍unverified并须实际全chain观看。错误代价是更长新链质量可能下降，不能预宣称稳定或自动通过。
- Tasks 1..7当前均未开始；C四窗GPU已退出，320帧20秒链技术核验与新human_video接受完整，review4beaf4aca19f19e1a5d1a4c28deddb525fd118a8c5e32d20891b0ed35440421f。当前CPU回归精确4375节点运行（runner14148/pytest8068），详见C/live-run.json；期间不修改src/tests/scripts。
- 回归期间准备：`C/production-staging/test_scene_temporal.py`为Task1测试草稿，尚未复制进repo或运行，不宣称RED/GREEN或功能已实现。覆盖1..334/10001、多scene、严格协议/配置/schema3提示与PCM绑定；CPU退出后先复制为计划目标测试并实际运行RED，再实现。
- 真实资格汇总：`C/native16-qualification-assessment.json` SHA `afeee7f892bb36329a6d7afd4ffa297931ae3683c3149847b4d6602dbb40c947`，绑定case/software/model/cache/资源/四窗完整性/链/review及单例观察范围；production_wrapper_resources仍unverified，不是生产准入ready。
- Ruling：用户已接受新资格并要求继续；当前4375回归针对接入前源码。为实施生产后再验证最终源码，在真实下一节点开始边界受控结束自有批次，不以耗时设置上限。实际退出15/源码520项前后一致，2607个完整PASS/0FAIL，原751保留；剩余1768节点精确列表`C/regression-post-implementation-remaining-nodeids.txt` SHA1d461611f9cad13986a71fe242dd7bdb1018b7ab1445ef44ed3c1887773910b2，checkpoint包含最后完整PASS与下一未完成节点。错误代价为当前未完成节点需正常续跑；不重启旧4375、不把调度中断写成通过。未来产品变更需补跑新/受影响覆盖。
- Task1开始：CPU原批次已全部退出，准备把外部测试草稿复制到既定repo目标并实际运行RED；未先写实现。
- Task1主要行为已实现：真实RED39 failed/缺模块与未知模式（test-41287f68ae6842ea92a26c83f0bfecda）；新增scene_temporal纯预算/严格13历史与93原生映射、native execution schema2、prompt schema3、fast/advisory配置，原whole/segmented版本保持。新39项与execution/prompt/whole兼容共200项GREEN，test-149b15027e6a485d8644f29ef988e933，0.78秒。生产准入/运行器尚未实现，因此尚未可生产使用。
- Task1补充旧映射/预算/runtime execution records/prompt/whole契约198项通过，test-1fd60636152d4eadb17e831bf8c97995，130.58秒。Task1纯协议/版本入口完成；生产runtime schema消费者仍按Task6收尾，不将仅配置可解析称为生产启用。
- Task2进行中：首8项缺失/外国schema/无资源零输出、27源小bundle安装/幂等/漂移拒绝真实RED（c8f328e0491c4a4e95a000d5f993a478）→GREEN8（75b7d7c956954dc3bc82e4dd8b396cdb）。实际qualification/core安装脚本已运行，后续仍需完整生产资源/source/runtime闭包测试、冻结入口与exporter；Task2尚未完成。
- Task2实际核心安装通过：vco08-production-real-qualification-core-install-558002668af642eab02c73e655641325退出0。完整读取真实资格/实际三份KV bank与所有closure后，仅27小源码和model/download/license元数据安装到`D:/VideoSi/tools/video-ai-temporal-native/ae99bb7ed0ee399adb8dd4b23ef754900f844ce516348859664d0925e1c523f3`，bundle manifest SHA03603bbf0e2e755811aec79ebc9a809ee6744dadfd0e8326f20f88eacc19a057；0模型复制/下载/文本编码，parent未导入Torch。C/production-core-installation.json为收据。此安装不等于生产准入。
- Task2补充TDD：6项真实RED（27c455ba972d4085b12fa57e3817ec64）证明claimed-ready不能仅靠自报标志，新增当前worker源码/版本目录27源与模型清单/实际五shape/启动及运行余量/clock绑定后15项GREEN（b4e8f774e2f949bf8aedf4bc27f7939a）。冻结和active模型/图选择2项RED（4af67b0ce19f48a19a2d8e5bac485f10），首次GREEN尝试暴露fixture错误run目录被路径守卫拒绝（f04d3cdf91b34ed590fe17888fea5f82）；仅改用既有runtime_run后79项GREEN（9fbd7d0e62b1483daae584a3ecb0c5ea），未放宽生产PathPolicy。
- Ruling：native冻结须跳过无关Wan模型/图，实际消费者在jimeng_config.active_models/active_workflows和production_inputs角色列表；已按新mode显式分支并保留旧默认。这是落实独立原生准入，不删除旧配置/旧图。错误代价为native下游若仍隐含依赖Wan会在后续集成暴露，须由Tasks3..6实际分流消除，不能静默回落Wan。
- exporter入口已加无真实preflight零输出/外部target拒绝的真实RED（4b07e9cc869346758bfd6f7e5accc254）→GREEN；最新native预算/准入18项及旧execution/prompt/whole/config共241项通过，test-36c41d2ec3c344bf9b41b04acc62a329，2.60秒。Task2冻结函数/核心闭包/exporter已实现，actual production资源与最终ready仍等Task4；旧production_inputs/recovery/execution_records兼容批次运行中。
- Task2兼容批次已退出0：production_inputs/recovery/execution_records共70 PASS，142.60秒，test-5eba65cb78ce4adfb62c883424c5d7bf。当前无CPU/GPU运行；下一项Task3 TDD。Task2软件主体完成，真实生产资源准入按既定Task4后才能finalize；剩余1768及新增/受影响最终验证保持待办。
- Task3观察：13项缺模块RED9f72f2fa9aa047e1851362a38d027da7；首次实现复验3a171e50326c40c58397f9299d336b26暴露把Path交给JSON canonical比较器，明确根因为Path不能JSON序列化，只改为已验证Path对象比较；观察/准入/预算70 GREEN271b306a70bc48d1bcd48a298f2f4bb2。静态acceptable可保留camera/motion unverified，仅准续窗；末窗acceptable/allow_next=false可组装，无法动态通过。
- Task3请求：13项缺模块RED3df17a98a7f2460fa946b1f350473e21→83合跑GREENfbfa9969931c4067bd8fc058d5f4bb98，绑定父raw13范围/快照像素SHA、父result/Generator/静态接受，不引用未来chain接受。真实13帧像素传provider仍属于Task4实际输入测试，未用此元数据测试冒充。
- Task3上下文/提示：9组schema-mode矩阵暴露schema3误准旧segmented/schema1误准native；原生上下文经fixture入站修正后以Wan检查被禁止的明确REDc56bee9a620c4f42aeff5e82e79b683c留证。scene_context首处分流temporal_context，runtime prompt schema精确1/2/3并识别native绑定；181合跑GREEN1c2c0cdf847c4e189415320bf40a1086。该原先Task6提示消费者提前落实，是Task3实际消费需要，旧版本语义保持。
- Task3窗口事务：10项真实RED8ac7f18c0a774790b85d54816def0252→103合跑GREENf23ab7fc4cbd45b69e0e0f892f080a6b；intent/sample/request/workflow/artifact/历史/映射漂移拒绝，unknown不采样、已提交latent只decode。新增3项typed metadata RED0aec85a7c1874f2eb49fd7786eb74b04，修正Python bool/int/float值比较等价，194合跑GREEN852163cf6c7c4f1d9f15d0734f260711。
- Task3整链：4项联接测试先暴露归一化window缺request_sha256，补齐同一canonical请求指纹后真实聚合功能RED72385600474f4a0db7c0c2af666c61f5；已实现validate_temporal_chain/complete_temporal_value及schema4 index，一个完整chain acceptance对应所有window贡献，静态/组装不升级passed。五个native测试文件110 GREEN35a92df5c1da4c2284fc70142d5a3daf（4.15秒）。actual媒体解码在事务unit fixture中是明确外部seam，真实CPU320/334媒体集成仍留Task5，未称真实GPU生产通过。
- Task3软件接口已实现，当前Task4下一步TDD。必须由Task4补齐真实raw13快照读取/像素SHA与provider参数、真实KV manifest可追溯、owned-process/unknown/sample-only decode、实际生产五阶段资源。Task5入口/流式组装、Task6schema4/rendering identity/修订origin/media guard/VCO-04以及最终1768+影响范围均未完成。当前parent execution_guard仍完整重核admission闭包，Task6必须用独立严格native proof消除按帧重复上游大bank核验；不能借WholeExecutionCheck或放宽未知guard。
- Task4进程监督已恢复核实：原6项RED b07c842285d847029d029e224adbbd43→GREEN f64bd54f555c4bd288525154a06c3b04，含自有Popen、PID复用、unknown零启动、sample仅解码、无限总等待及实际3GiB commit停止样本。
- Task4 worker真实缺模块RED49a26d44548e4789b5a14378c2b9f3d4；补上fixture实际RunLock并移除其旧字节占位snapshot后，15项GREEN b4ae416c8ab842ef811af6f09c411c23。未放宽生产锁/allow_pickle=False或RGB验证。新增缓存/不截断tokenization两项RED c5f6ad154cb048c882732dc0bad24bc0→当前五个native协议文件与worker/process共127 GREEN46fb0e6803b6477aa6c46b2d42794aa3；补充partial-media恢复后worker/process18 GREEN8c7bf55c330f4deda23d72330fbe4270。
- Task4真实数值provider已接固定27源bundle的load_dit/load_vae/官方i2v/vc，读取13不同原生RGB帧、恢复父Generator，写独立48层KV manifest；原提示仅引用现有缓存，不调用编码；新提示需显式prepare-cache且先本地未截断tokenize。尚未宣称真实GPU封装通过。
- 生产五阶段资源运行器已备于C/production-staging/run_production_resource.py。两次准入检查均在worker启动前拒绝，零模型调用。首次缺用现有desktop_policy；补齐后仅WindowsTerminal.exe与D:/Program Files/Oray/AweSun/flutter/AweSun.exe未获桌面放行（均实际C+G），23708MiB显存空闲。现有gpu_desktop.desktop_approval_scope明确要求具体路径授权，已异步询问，等待时继续Task5 CPU工作；不改全局allowlist、不杀应用、不降低原余量。
- Task5组装3项缺模块RED c57acfba06bd4dfb8d8978ae549131e5→GREEN c9d8fa30fda04e1fa1ddeda789be229d。真实CPU原生320/334 RGB、raw/viewing编码及完整逐像素流式复验通过，实际末窗67和1，未用全链RAM数组。新增原入口两分流及原始拒绝中断保留3项RED9284790de77849828f61e8cb78fd116c→59项GREEN f9969d6373204277bcff6e4876a06ffa。
- Task4/5集成查实共享缓存位于D:/VideoSi/cache而非run，实际RED b7ce2c26ee62444d8a4139114716a051→定向55 GREEN d1625fb92687425ca976b432aac635c0：仅准精确cache key目录/资格原缓存，未放宽SceneClipStore.run_path。实际condition消费收据3项RED fe8335a819ea41b180cbf69a9cb9d76c→58 GREEN3e01fcd8ee4f493cb71fe57df7b22970；parent现在还核验原生KV48层manifest/逐层来源/shape/BF16/完整SHA。
- Task6独立TemporalExecutionCheck缺模块RED2810948097134e469ed01e2b1511fd6e→75 GREEN d1345f1a055a48be8bb871cc2836d5b4（含旧whole coverage）。使用已验证ByteGuard和Windows原生输入共享句柄机制，类型/方法/来源/闭包精确，拒绝未知或替换proof；不借WholeExecutionCheck。native writer启用既有底层输入保护窗口，仍待native媒体context接入完成。
- Task6纯映射schema4/旧schema降级RED4c0b273dc3524be3bab7e947818d1050→映射/旧media/execution91 GREEN b6880cec5e2349b595606ddb04fc95e1。rendering identity4/源execution2/模式变化失效3项RED adc91c445d0b4f1caa73a4a1c888ac03→新旧revision/execution/temporal177 GREEN61ef26747a904cda98c6928cc8234b61。原runtime revision snapshot/origin接入尚待完成。
- Task6 VCO-04 native binding/完整链可作自身prefix2项RED7d6c700036024c818547469023fbd998→46 GREEN5468076502c74d62b53053b153ec7c0e；新增outer _finish原生分流RED d5b5879bd4f44f5b865c5dfd40ff46ed→native flow与旧continuity24 GREEN aafc69b8ffcb4d60bc02e0b7cc4b306f。仍须真实风险报告/回应和媒体端到端覆盖，不能仅用该定向测试称VCO-04已整体通过。
- Task5生产事务CPU fixture_only 320四窗/334五窗完整流程与同run重放2 PASS，test67565c6c208a49b083bc16869492b61f，134.37秒；真实编码/解码/末帧检查，捕获13个不同RGB条件，每窗一次provider采样，完整chain单次观察后重放0新增。明确外部数值seam是fake provider和KV bank验证（该fixture不分配4GiB真实KV）；真实GPU资格/五阶段资源另账。未冒充新模型视频或真实人工观看。
- Task6常规native修订真实RED e358ad119a0347e5ae57e5f121bc35bc（configuration_identity尚未绑定native准入）；补齐native evidence/runtime身份及继承路径后aab86232344242d58759187ad08e3872已实际revision_ready，PCM/原选图/新execution2断言通过，最后仅fixture预期误写[13,3]而原scene确为[13,2,3]，已修正。新的全媒体测试7ab6cd14b76b43eea7ca492086619174实际RED暴露manifest仍要求native resolved Wan workflow；现只在明确native raw/mode下允许完整{'upscale'} resolved工作流，旧模式契约不变。
- 当前全媒体CPU复验cc3598cd330f4b8e9344f300595d39aa/session45766正在运行；实际native目标20261103-085024-c67a6a5a8028三窗与三scene chain及complete均已写出（全为fixture_only数值/观察），暂未有upscale目录。程序尚未退出前不编辑源码，不计通过。
- cc3598cd330f4b8e9344f300595d39aa已实际退出1/323.34秒：source fixture三窗三链完成后，upscale真实RED为把外部bundle当run路径拒绝。已给schema4媒体源增加独立完整ByteGuard捕获及严格native文件覆盖，不放宽通用PathPolicy。
- Ruling：75a2da4c477a416a9161b24b85d72d40的新媒体复验在已定位重复整个闭包核验缺陷后受控中断自有pytest（PID4424/birth2026-11-03T08:56:41.3151180Z/实际退出-1），不是时长预算。当前集成节点unknown，45个未带终态dots不计PASS。完整中断/4源码SHA收据C/production-staging/native-media-duplicate-proof-interruption.json。错误代价为该节点须在最终源码重新完整运行，不能复用此前未完成结果。
- 对上述重复核验与CLI早调用两个缺陷写行为测试真实RED76447a2752014b539e333b8d0e749459→59 GREEN c6280a23620f4ad6a340071df97f2160。每个已准入文件只复核自己的真实文件/连续原生句柄，不逐个重跑全闭包；已捕获run内raw/KV同样不再重复全量SHA。CLI main调用移至dispatcher定义后，真实runpy CLI已触发provider操作。
- native coverage行为RED bc449e82e6a842338b7752513542c5a8暴露replay传错FileIdentity类型；修为精确原身份字段后真实coverage缺失RED507f81a6d8d541a0be0ded3c0fb9a776→新旧coverage/worker60 GREEN454a87eec1a4416e832b646f2ee76f62。新_TemporalCoverage独立类型/完整闭包子集/原回调及执行证明绑定，旧WholeExecutionCheck识别规则未放宽。
- 新提示cache异常不可编码RED0d11e838a34747949e65e35e8557519e→worker14 GREENde5278f7b5844c40af0b56869047ba32。补齐正常生产必须在任何视频intent前，以独立owned prepare-cache作业准备不同的新提示，原精确缓存直接复用；unknown cache作业不自动重编码。2项RED4fa7cd89e6ba4c9a9f6090e9efbc636f→process/worker22 GREENeafa569fd55a4016900efbc7b409a7db；真实CLI prepared-run缓存路径RED3260dfc68d2f40daae5b139285f6227d→27 GREEN9e42a5b8034e46f9a9cd70a3fc36aebe。CPU fixture显式替换编码边界，不做新真实编码。
- 真实资源源码绑定漏掉worker的records helper：RED24453c644e92402a98f6f430774be845→新旧相关87 GREEN d8e68d3efe164cc2b7cfdf4c2f33bbfa。扩为7个实际worker/protocol/helper源码，并在resource provider纳入实际records导入足迹；尚未实际GPU预检，不复用未来会漂移的资源结果。
- Worker foreign protocol/run/clip/input-clip4项RED67f3fd8cdc0845c1ae1f333213cf0dc0→相关50 GREEN27c5f7abeac240e586cffbb8bcee3484；首窗所消费原图与审计selected不一致REDb9cd9968ac394ed1aa9da1bd7154b162已修复，等待当前定向批次终态。当前生产包装GPU仍0调用、真实文本编码0、权重下载/复制0。
- 上述首窗修复及新旧coverage/admission/process/worker定向94 GREEN8cd6707b83ca492795f59d7420074aff（13.49秒）；native source snapshot不能读旧Comfy输入schema的RED e6cde954cdfa4e33ac9e6426332bc79e→48 GREEN71a256dd1f894becb5c17390d8b7167e，按原生scene范围读原生事务视图；runtime origin继承正在接入。
- 用户已真实回复“允许，直接继续（推荐）”，明确允许本次VCO-08在Windows Terminal及AweSun保持运行时继续GPU预检和生产验证；原余量守卫/不关闭应用保持。C/production-desktop-authorization.json保留确切观察路径与回复，资源runner已使用run作用域desktop_approval_scope，不再询问该放行，不改全局allowlist。先完成影响worker身份的原生origin源码，再串行运行真实资源预检；GPU尚未启动。

### Task 1: 纯预算、提示和版本化入口

**Files:** Create planning/scene_temporal.py、tests/unit/test_scene_temporal.py；modify config.py、planning/scene_execution.py、scene_clip_continuation.py、scene_video_prompts.py。

**Interfaces:**

- `derive_temporal_clips(plan, timeline) -> list[dict]`；每scene首窗min(93,N)、其后min(80,remaining)，global范围连续。
- `validate_temporal_clip(clip) -> dict`；精确BUDGET_FIELDS加protocol=longcat_native16_v1，首窗head0/selected_scene_image，后续head13/parent_native_tail_13，generated93。
- `temporal_frame_mapping(clip, *, actual_generated_frames) -> dict`；沿通用mapping字段/native_fps16/output_fps16并明确clock policy，generated_to_retained等完整唯一。
- `build_scene_temporal_plan(frozen,bible,plan,timeline,image_inputs,*,prompt_contract,prompt_binding_context,execution) -> list[dict]`；共享视觉/原文/narration绑定，native参数steps50/cfg4/seed规则独立于Wan。

- [x] 写纯测试并运行`./scripts/test_windows.ps1 -q tests/unit/test_scene_temporal.py`；Expected RED缺模块或未知mode。
- [x] 覆盖N=1/13/80/93/94/173/174/253/254/320/321/333/334/10001、多scene及非法bool/float/负数/缺口/未知protocol。334为5窗，保留93+80+80+80+1，不能拒绝或截短。
- [x] 实现execution schema2/scene_execution_v2仅native；旧两mode继续schema1原算法。parse_scene_rendering native只增temporal_evidence精确绝对D:/VideoSi JSON字段，要求fast与advisory_v1。
- [x] prompt schema3只绑定native与execution clip SHA；旧schema1/2原渲染字节保持，审计JSON/坐标/未来父姿态不得进入正向提示。
- [x] 同一命令GREEN，保存命令/源SHA及结果；不生成模型/图片/音频。

### Task 2: 资格与生产准入、稳定数值bundle

**Files:** Create runtime/temporal_scene_admission.py、tests/unit/test_temporal_scene_admission.py、scripts/export_temporal_evidence.py；modify runtime/scene_execution_records.py及production_inputs的实际冻结入口。

**Interfaces:**

- `load_temporal_evidence(path, *, reader=None) -> dict`：严格root/closure/case/window/bank/chain/human-review/资源/模型/运行版本，缺项或漂移拒绝。
- `install_temporal_bundle(qualification, *, tools_root) -> dict`：复制C27小源码/许可/清单到tools版本目录，仅相同内容复用，0权重/网络/编码。
- `freeze_temporal_evidence(config,run,identities,*,save)`、`verify_temporal_frozen(frozen,*,reader=None) -> dict`：当前环境独立闭包，不借whole evidence。
- `finalize_temporal_evidence(qualification,runtime,production_preflight,*,target) -> dict`：必须Task4实际生产封装资源证据匹配后才ready；安装资格核心不等于生产准入已通过。

- [x] 写缺少/failed/unknown/unverified、错shape/clock/backend/model/code/cache/review范围/来源的拒绝测试，Expected RED。
- [x] 固定schema1 evidence精确字段：algorithm、qualification_root、observed_visual_scope、model_manifest、runtime_bundle、native_python、package_versions、production_worker、production_resource、artifacts、assessment。Artifact均path/bytes/sha256，scope诚实记录C单例四窗320；不自行标新视频passed。
- [x] 资格/生产资源两个身份分账；Task4前只允许安装已资格小核心和准备资源输入，最终生产evidence缺resource则拒绝激活。
- [x] 运行`./scripts/test_windows.ps1 -q tests/unit/test_temporal_scene_admission.py`，Expected GREEN，正常缺资格输入零模型调用。

### Task 3: 原生窗口事务与静态/整链观察

**Files:** Create `src/video_ai/runtime/temporal_scene_records.py`、`src/video_ai/runtime/temporal_scene_observations.py`、`tests/unit/test_temporal_scene_records.py`、`tests/unit/test_temporal_scene_observations.py`；modify `src/video_ai/runtime/scene_clip_records.py`。

**Interfaces:**

- `temporal_context(frozen,units,timeline,*,paths=None,lock=None) -> dict`消费Task1 execution/schema2和Task2独立准入；在Wan模型/WorkflowTemplate检查前分流。
- `expected_temporal_request(context,row,input_record,parent) -> dict`绑定native workflow、当前父技术/static/raw13/RNG；不包含尚未发生的完整动态接受。
- `validate_temporal_window(context,row,parent=None) -> dict`核对intent/sample/result/媒体/父链与实际输入收据。
- `collect_temporal_progress(context) -> dict`、`complete_temporal_value(context,records) -> dict`输出显式protocol的schema4 index；完整chain观看和VCO-04门禁之前不能source_clips_ready。
- `build_temporal_observation_template(context,record,*,scope) -> dict`、`validate_temporal_observation(value,expected,now) -> dict`区分`temporal_window_static`和`scene_temporal_chain_process`。

- [x] 写`test_static_does_not_pass_chain`：acceptable静态只准下一窗，完整动态仍unverified；末窗acceptable/allow_next=false可以组装。写`test_future_review_not_in_generation_request`和`test_rejected_history_cannot_be_overridden`。
- [x] 写`test_raw13_parent_rng_drift_refused`：逐一改变父result、[80,93)像素SHA、Generator或screening，验证零provider启动；旧index/schema不能借protocol字段走新validator。
- [x] 运行`./scripts/test_windows.ps1 -q tests/unit/test_temporal_scene_records.py tests/unit/test_temporal_scene_observations.py`，Expected RED缺模块/行为。
- [x] 实现上述接口；沿现有SceneClipStore不可变Artifact/原子记录，不伪造Comfy submission。chain模板绑定全[0,N)、所有窗口/result/range和三处实际边界，单次完整观看只生成一个事件。
- [x] 同一命令GREEN；记录实际日志、退出码和源码身份。

### Task 4: 自有子进程、真实条件与成功latent恢复

**Files:** Create `src/video_ai/runtime/temporal_native_process.py`、`src/video_ai/runtime/temporal_native_worker.py`、`tests/unit/test_temporal_native_process.py`、`tests/unit/test_temporal_native_worker.py`。

**Interfaces:**

- `recover_or_start_native_window(store,request,workflow,*,worker_factory=None) -> dict`返回持久状态与结果路径，持有真实进程对象；存在unknown intent不发起采样。
- worker CLI：`--operation resource-preflight|prepare-cache|one-window|decode-only --request <absolute-json> --output <absolute-directory>`；父进程导入模块不得导入Torch。
- `execute_native_operation(request,*,operation,output,provider=None) -> dict`供测试注入provider；真实provider导入Task2固定bundle，使用官方i2v/vc和稳定数值核心。

- [x] 写`test_thirteen_distinct_raw_frames_reach_provider`捕获13个不同父raw帧和num_cond_frames=13/use_kv_cache=True/offload_kv_cache=True/enhance_hf=False；验证生成历史不是viewing或last-frame。
- [x] 写`test_unknown_never_starts`、`test_pid_reuse_is_not_owned`、`test_sample_commit_only_decodes`、`test_partial_media_resume_preserves_sample`、`test_allocator_set_before_torch_import`；中断点覆盖intent前后、sample/Generator提交、媒体晋升。
- [x] 写`test_no_total_timeout_with_resource_stop`：无总时限仍在真实4GiB commit下拒绝/停止并持久化触发样本，不终止非自有进程；有限cleanup等待独立保持。
- [x] 运行`./scripts/test_windows.ps1 -q tests/unit/test_temporal_native_process.py tests/unit/test_temporal_native_worker.py`，Expected RED；实现后同一命令GREEN。
- [x] 相同正负提示/model/算法缓存复用；缺失现有精确缓存拒绝，不静默重编码。新提示编码单独操作，先本地tokenize拒绝截断，保存独立身份。
- [x] CPU检查通过后，GPU独占运行生产封装`resource-preflight`五阶段；Expected同源真实五shape/原余量通过，新增下载/文本编码/视频调用均0。用Task2 finalize导出独立生产准入，缺少真实资源收据必须拒绝ready。

### Task 5: 正式生成入口与完整链消费

**Files:** Create `src/video_ai/runtime/production_temporal_scene_clips.py`、`tests/integration/test_temporal_scene_flow.py`；modify `src/video_ai/runtime/production_scene_clips.py`、`src/video_ai/runtime/production_inputs.py`及实际options冻结入口。

**Interfaces:**

- `produce_temporal_clips(context,*,paths,logger,worker_factory=None) -> SceneClipResult`在现有RunLock/GPU ownership内生成/恢复，每窗技术+静态后才继续。
- `consume_temporal_observation(context,observation_path) -> SceneClipResult`消费Task3严格模板，最终链观察接受才允许后续连续性/媒体门禁。
- 现有`produce_scene_clips`/`consume_scene_clip_observation`签名保持，按冻结mode在Comfy事务前分流；显式native mode无Comfy POST。

- [x] 写四窗320与五窗334帧CPU集成fixture，标记fixture_only；Expected完整唯一贡献、13真实历史输入、末尾准确裁尾、同run恢复0新增采样。
- [x] 写`test_chain_review_required_before_ready`和`test_one_review_covers_all_native_windows`，拒绝静态代替整链及缺失/VCO-04未通过；写原始13条件/父screening/完整raw丢失时零启动。
- [x] 运行`./scripts/test_windows.ps1 -q tests/integration/test_temporal_scene_flow.py`，Expected RED；实现分流及流式组装，不一次性载入任意长链全部RGB；同一命令GREEN。

### Task 6: 媒体、修订与旧版本兼容

**Files:** Create `src/video_ai/runtime/_temporal_media_check_coverage.py`；modify `src/video_ai/planning/scene_media.py`、`src/video_ai/planning/scene_revision.py`、`src/video_ai/runtime/scene_media_records.py`、`src/video_ai/runtime/_scene_media_check_coverage.py`、`src/video_ai/runtime/scene_revision_records.py`、`src/video_ai/runtime/scene_video_prompt_records.py`和实际snapshot/origin消费者；extend Task5 integration及受影响现有unit/integration。

**Interfaces:** 新native guard只接受独立严格类型与完整来源闭包；schema4 index、execution schema2、prompt schema3、rendering identity4按Task1/3识别，旧版本精确字段和算法不变。

- [x] 写`test_native_guard_rejects_unknown_or_replaced_proof`、`test_temporal_mapping_preserves_pcm_subtitles`、`test_mode_revision_invalidates_video_descendants`和旧schema回放断言；新mode不得借WholeExecutionCheck接受未知对象。
- [x] 运行`./scripts/test_windows.ps1 -q tests/integration/test_temporal_scene_flow.py tests/unit/test_scene_media.py tests/unit/test_scene_media_check_coverage.py tests/unit/test_scene_revision.py tests/unit/test_scene_execution.py tests/unit/test_scene_video_prompts.py`，Expected新增行为RED。
- [x] 实现schema与mapping消费者和修订失效；原文/语义/选图/PCM/字幕合法继承，旧视频观察不继承。实际source仅新增区，last-frame来自保留区末索引，raw13另存条件。
- [x] 同一命令GREEN；再运行`./scripts/test_windows.ps1 -q tests/integration/test_whole_scene_flow.py tests/integration/test_whole_scene_recovery.py tests/integration/test_whole_scene_media.py tests/integration/test_scene_revision_flow.py tests/integration/test_scene_video_prompt_flow.py tests/integration/test_scene_continuity_flow.py tests/integration/test_scene_continuity_recovery.py tests/integration/test_scene_media_flow.py tests/integration/test_scene_media_recovery.py tests/unit/test_scene_media_without_rechecks.py tests/unit/test_scene_media_coverage_review.py`，Expected全部通过，旧whole重复检查不恢复。

### Task 7: 真实证据准入、最终回归和结项

**Files:** 更新`docs/task-designs/VCO-08-research-results.md`、本ledger、生产操作/验收记录和`docs/task-handoffs/video-continuity-optimization-task-board.md`；持久证据放`D:/VideoSi/projects/video-ai/vco08-preflight/`独立子目录。

- [x] 用正常准入入口验证真实C完整链/review、安装bundle和Task4独立生产资源证据。Expected准入只覆盖固定backend/model/core/shape/clock，视觉scope仍单白鹭四窗320帧；不把fixture或资源前向称作新生产视频。
- [x] 对照主设计原五项Acceptance逐项列出技术/软件/资源/完整动态/适用范围的真实证据；若尚缺真实生产验证，在当前授权和一次采样协议内先记录具体输入/操作及身份再执行，不捏造通过或无修复重复采样。
- [x] 最终源码collect/hash，保留M原751 PASS和timeout修复5项；以`regression-remaining-nodeids.txt`精确4375列表继续未获终态节点，逐节点完整日志。新增/受影响测试补跑，原结果仅在来源一致时复用；collection变化逐项归并，不机械重跑无影响前缀。
- [x] 所有最终批次检查真实退出码、完整终态及运行前后源码身份；真实失败按原因修复并验证，未知不能计PASS。GPU与测试串行。
- [x] 按executing-plans做一次独立最终审查，Critical/Important真实RED→GREEN修复；执行`git diff --check`只读检查，不stage/commit。Expected无未处理重要问题且必要验证通过。
- [x] 全部Acceptance有证据才更新VCO-08 COMPLETED；保留限制与失败血缘。无后继任务，不新造任务或发布。

## Plan pre-flight / current execution boundary

- 2026-11-04 00:05：659最终新增/受影响完整终态658 PASS/1 FAIL、9327.22秒、实际exit1，全部源码/精确列表前后不变。唯一FAIL为旧_prefix expected无video_expected时新增native分流提前KeyError；改为可选键读取让旧输入继续原历史来源拒绝。失败公共节点+native/旧continuity共21 GREEN/34.52秒，C/regression-final-repair-6d1e7f5cbd9645dab00f2b718969c4fe真实exit0/source_identity_unchanged=true。此前1768中14失败也已108 GREEN解决；所有已发现回归失败均有实际修复复验证据，不再重跑长批。正常当前源码五阶段资源已启动，完成后仍需正常exporter及5326逐节点/当前SHA核对、Acceptance结项。

- 2026-11-03 21:21：精确1768剩余完整终态为1754 PASS/14 FAIL，1300.17秒、exit1、全部源码前后不变，目录C/regression-remaining-final-ac534ed13ab54c3e89b020f46ca962ab。真实失败分为七个旧最小media对象缺config、四个whole祖先fixture误标segmented、一个execution=None旧服务分流、whole缓存准入公共入口未持有完整mandatory读窗口、旧continuity有限期限测试与用户正式生产无上限要求冲突。修复可选配置/None分流与公共verify_whole_scene_frozen保护，测试祖先明确whole，有限reader仅由测试注入，新增正式生产长preflight无deadline验证；没有恢复whole已移除的重复审核或生产时间上限。shared cache首窗/续窗workflow不同的边界真实RED7b62c44c→按实际创建cache的workflow身份匹配；成功视频不产生unknown效应也已覆盖。七文件108 GREEN63b6b9d2cbda4ddda126e1b3444d9f53/14.54秒、exit0。保留1754无影响PASS，仅补新增/受影响覆盖，不重启旧1768。
- Ruling：四个whole祖先测试的fixture按测试原意改为实际whole options/config；源strict consumer仍segmented，确保独立祖先reader必须live核验，不能通过恢复whole重复检查掩盖fixture错误。有限continuity reader在测试显式注入，正式生产仍null总时限。错误代价为错误fixture会让这些测试无法覆盖其声称的旧祖先或时间策略边界，已用完整正负断言及生产无上限补测约束。

- Final: fixed Important1（native launch/cache unknown遗漏）—公开修订入口RED6aed65a4→GREEN56f22a27a1ea4ad3a475090840b9b54c，one-window/prepare-cache两条2 PASS/186.78秒、实际exit0；61项相关定向7db928e0 GREEN。Important2/3也已完成各自RED→GREEN，尚待最终剩余回归和受影响套件，不派第二次review。

- 2026-11-03 20:51：两条跨run修订d79dfdc3193f4759afa3f9c36be52c05已实际2 PASS/3508.22秒、退出0。最终review Important2原生fresh active-role检查RED→29 GREEN1e39309fefa548668d047aef2c66ea05；Important3缺aggregate的schema4分流RED2a05fbb0→38 GREEN1c5e1ff4；Important1公开入口RED6aed65a4后接入native_revision_effects，request/launch/owner/terminal及独立cache未知效应完整核验、成功latent仅解码/已完成cache只读复用，定向61 GREEN7db928e038804bbdb15ec7ef7ba46a14。公开入口one-window/prepare-cache两条复验56f22a27a1ea4ad3a475090840b9b54c/session10652仍运行，不预计PASS。最后精确1768/受影响覆盖、最终源码资源与exporter、Acceptance仍待。

- Task1预算/版本 → Task3 request/index → Task5入口 → Task6媒体/修订：统一protocol longcat_native16_v1与版本2/3/4，旧schema不重新解释。
- Task2只安装资格数值核心，Task4取得生产封装资源后才能finalize；Task5不能先用缺resource的evidence激活。
- Task3静态只控制后继，Task5完整动态控制chain ready；不在生成请求中预引用未来review。
- 当前仅补齐已有关联spec的计划，Tasks1..7均未实施；C四窗/技术/实际静态/整链已完成，等待完整新动态接受。原4375 CPU回归已在GPU退出后启动，测试期间不改src/tests/scripts。

- Task4真实生产封装资源已核实：session73545实际退出0，worker8100/runner20072均结束；88e4a41c0c1745268d4bb686ae28930a/completion.json worker_exit_code=0/resource_trigger=null，production-resource.json complete=true，first/clean_history/continuation/vae_encode_13/vae_decode_93五阶段完整。8项生产源码SHA与当前字节一致；C/production-staging/resource-result-verification.json保存核验。native_diffusion_calls/new_text_encoding_calls/video_outputs均0，执行时间/占用上限null，实际余量正常。最终准入仍待Task6和最终源码身份，不预宣称启用。

- Task6媒体完整复验已取得GREEN：test-c0e3a23aeee84fd4a6f52d73d0a5979d实际退出0，2 PASS/1264.61秒。常规模式修订、原生三场景完整18帧真实超分/合成、完整PCM逐样本贡献、字幕字节和同run重放0新增采样均通过；fixture_only数值/观看/continuity seam仍明确，未冒充真实模型或人工观看。

- Task6来源闭包/丢弃媒体真实RED：fa7e96030eaf4b1eb564842a9c3e0c0b暴露未用媒体仍缺失拒绝，完善独立fixture提示角色后7a6f3e5405bc43fa9829a32861ea5288准确RED为upscale来源缺chain result。补齐原生chains快照及仅在origin_clip_scope明确丢弃集合内读取binary声明，JSON/事务/观察依然真实核验；需要继承的媒体缺失仍拒绝。6 GREEN7a591df182e24153abcbf37be0e74a91/1.02秒。修改temporal_scene_records后原88e4资源收据已不匹配最终helper；保留历史收据，最终准入前重新取得当前源码五阶段资源。跨run原生继承集成e26d11cf70974af3bb746262b57fee6d运行中，尚未通过。

- 跨run原生继承集成e26d11cf70974af3bb746262b57fee6d实际RED退出1/348.02秒：原生来源只冻结upscale的effective workflows子集，再修订被当成完整raw配置使workflows.wan缺失。真实小用例补全image fixture后RED5e825cb5a8ac4102bd4e67a4161f3ff9复现同因；仅native rehydrate保留原raw inactive workflow绝对路径，再叠加冻结active角色，未读取/冻结/启用Wan。新增原生风险回应/作者/prefix门禁覆盖后，native/旧revision七文件155 GREEN7fbe2fd4a04a4be8907df4dcde20abe5/4.98秒。跨run集成877c7e6fb7d74654b914b86d177db3ba/session83503复验中，尚未通过。

- Ruling：877c7e6fb7d74654b914b86d177db3ba在具体重复资格重建缺陷定位后受控中断自有pytest11528，bootstrap实际exit=-1/tool exit1；该节点unknown、0计PASS，C/production-staging/native-origin-admission-duplication-interruption.json保留来源/进程起点。不是执行时限，错误代价为节点必须重新完整跑。真实count RED62a0ed455da341ebad81b4b91ea14c3c证明同操作4次重建而非1次；加入原生独立operation-local memo，严格value/raw/reader完整契约和每次byte/inventory复核，不跨操作缓存。核心字节漂移仍拒绝，24 GREENcaf830184d15498db502a67f8fe35b98。

- 原生修订完整读保护REDa694966d7ec3471d82d0c41143ebddd3：创建修订期间原没有native input window。以ExitStack仅为native持有mandatory输入句柄和validation_session，target保持writable_validation_session可正常pending晋升；旧mode继续无该新window。native/cache/旧revision/whole guard共151 GREENca468aa5dc9946efa74cb1213efc512a/5.30秒。局部父窗继承的长PCM测试支持缺失REDb00b8e26422e4b3c9fe3340768ee8f45，已给测试helper增加可选speech_samples（默认原值不变）及明确fixture_only KV seam，raw13仍真实输入provider。两条跨run集成648334da137d4fbb9abc6b388500d73e/session1743运行中。

- 当前两条跨run集成仍在运行。为定位自有pytest15728的实际CPU路径，独立从既有pip缓存取py-spy0.4.1 Windows wheel至D:/VideoSi/tools/video-ai-diagnostics（SHA d92e522bd40e9bf7d87c204033ce5bb5c828fca45fa28d970f58d71128069fdc），没有安装到生产/Comfy环境。nonblocking dump成功；C/production-staging/native-origin-live-stack.txt显示已进入首条用例157行continued.admit_all，修订准备已越过，当前重建继承来源证明。10秒只读采样native-origin-live-profile.json为149有效样本/100非阻塞读失败，主要叶为stat/path身份核验，仅为诊断，不作验收或计PASS。

- 跨run集成648334da137d4fbb9abc6b388500d73e已实际完整退出1：2 FAIL/1541.62秒。首条已完成目标revision_ready、指定scene一次新采样、其余scene继承/complete，但最终原观察逐字段断言准确发现remap_media重写原事件中的路径；第二条仅测试helper写死首scene13帧导致长PCM提前失败，不是原生采样失败。事件投影unit完善独立空target fixture后真实REDf696366ec3764cc19167c172134ed766复现原request也被改写。

- 修复native媒体投影：remap_temporal_window/chain仅重定位技术媒体视图，原request/static_observation/chain observation/origin_template逐字段保留；两条实际native origin消费者都接同一函数。长PCMhelper只在默认fixture保留原13帧/5+4+4断言，默认行为不变。跨run测试的低层查询明确放入单次mandatory只读窗口，维持所有实际字节/目录核验。native/旧revision八文件120 GREENe765efccc4e746e4be8f0e7944098440/7.10秒。按partial先行、-x运行两条真实CPU集成d79dfdc3193f4759afa3f9c36be52c05/session36241，尚未终态。

- d79dfdc3193f4759afa3f9c36be52c05已输出完整节点PASS：test_native_revision_keeps_raw_parent_but_requires_new_mixed_chain_review PASSED [50%]。真实复制父raw93/Generator、13不同raw像素送provider、仅后继一次新采样、静态后仍未ready、混合链新完整观看、原静态/请求事件及源run不变均通过。第二条整场景继承仍运行，批次尚无终态。按executing-plans/requesting-code-review发起唯一独立最终只读review vco08_final_review，明确不得测试/GPU/写文件，包final-review-package.json含59 overlay文件/28 untracked；待全验证后处理重要发现，不将并行只读review当完成。

- Final independent review已完成（vco08_final_review / gpt-6-astra ultra，只读，覆盖59 overlay及全部28 untracked）：0 Critical、3 Important、0 Minor、Declined to judge为空。三项为原生video/cache launch-intent早于worker intent的unknown未纳入revision paid effects；fresh native production_preflight仍索引inactive Wan且model path checker同样未分流；coordinator缺source complete时通用complete_value误重建schema3。根agent接受三项Important，当前批次结束后一次RED→GREEN修复；报告C/production-staging/final-review-findings.md。真实provider/core/raw13/RNG及正常媒体路径审查未发现其他重要问题；待验证项未误算代码问题。
