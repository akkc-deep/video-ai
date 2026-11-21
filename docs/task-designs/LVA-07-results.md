# LVA-07 Wrapper 实验结果

## LVA-07-06 最终完成（当前）

LVA-07专项六个执行任务及项目任务板12项均已完成。LVA-07-06的新矩阵8组×冷1热3共32份原生、24份1080P画面/原音轨/字幕/父子衔接均获真实人工接受；最后用户原文“没问题”，六组同字节重复成片已按实际许可关联，不声称重复独立观看。2290个唯一逐帧请求，父cold帧按设计复用；8个Wan+26个后处理owned合作exit0、未强制、端口关闭。

固定fixture原生热中位配方比12.388～13.636倍，n=3，不是稳定泛化、纯后端或端到端倍数。完整pair回执约38～40分钟，后处理实际墙钟3249.544秒；交接/排队/人审/资源及原中断2份历史样本边界详见[06结果](LVA-07-06-results.md)、[完成记录](LVA-07-06-completion.json)和[24份交付索引](E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-02/final-delivery-index.md)。原生生成任务总34上限完整遵守，完成档案实际原ID恢复0HTTP/submit/producer。

保留原质量默认，不恢复生产、不自动推广，无付费调用。没有预定义后继任务。以下05及此前内容为保留的原始历史快照，旧“06未开始/等待确认”等不代表当前状态。

---

# LVA-07 Wrapper 实验结果

## LVA-07-05 最终完成

用户先回复“接受”control，随后对独立展示的fast回复“视频没有问题”；两份真实人工接受分别绑定原prompt/profile/fixture/graph/media，记录于本轮 `reviews/control_1.json` / `reviews/fast_1.json`。完整原双专家准入、两份原始媒体技术、资源与计时、owned合作退出均已齐全，LVA-07-05已执行IN_PROGRESS -> COMPLETED，剩余验收为None。完成映射：`docs/task-designs/LVA-07-05-completion.json`；完整实际记录：`E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-06/experiment-assessment.json`。

| 原样本 | 执行墙钟 | 技术 | 人工质量 |
| --- | ---: | --- | --- |
| 40步control | 1255.786秒（约20分56秒） | 通过 | 已接受 |
| 4步fast | 96.539秒（约1分37秒） | 通过 | 已接受 |

本组低运动结果支持继续研究候选，但各仅一个样本、配方不同且fast复用同epoch缓存，不声明稳定倍数、纯后端或1080P收益。提交峰值约16.29GiB低于18GiB额度；owned服务exit0、未强制、端口关闭，历史pair不再放行新请求。本轮收尾只读取既有证明，未重复生成、解码或测试矩阵。

执行决定：两份媒体持久化后提前释放GPU服务，fast人工审核使用本地产物；代价是该epoch不能复用，原预算也不允许额外样本或重发。原输入/六模型与生产保持原范围。LVA-07-06仍NOT_STARTED，扩展需要用户另行选择；下方各阶段“等待确认/IN_PROGRESS”均为历史快照。

## 最新继续执行：原 VAE 输出的 RGB 连续布局修复

**当前状态：control 已获真实用户接受，fast 技术通过，fast 人工质量待确认；GPU 服务已正常退出，任务仍 IN_PROGRESS。** 用户对展示的 control 明确回复“接受”，已写入绑定原 comparison/profile/fixture/graph/prompt/media 的 `reviews/control_1.json`。随后同 epoch 首次提交 fast `1dafecde-bd7a-493d-8c39-7bc1bfb4e4ae`，CLI exit0，原4步/CFG1、高2低2前向，双侧 head_full_delta_installations=1，正向664完整上下文；CFG1仅消费正向，原负向512缓存仍保留。

实际 fast：`E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-06/output/lva07/fast_1.mp4`，SHA256 `d91f6677739b3fd6672744297e6fa1befd6345a4dfade185d9704c1bd261e8f5`，768×432/93帧/CFR16/5.8125s，93PTS、末帧和非黑屏证明通过；未重复解码。

| 本轮原始阶段 | control | fast |
| --- | ---: | ---: |
| execution_start→execution_success | 1255.786s | 96.539s |
| high_sample | 468.5191s | 40.8615s |
| low_sample | 771.9310s | 40.5699s |
| vae_decode | 7.3655s | 7.3320s |
| encode_validate | 3.7086s | 3.3744s |

仅一个样本各一份，fast复用同服务文本/图像缓存；control40步CFG3.5与fast4步CFG1+LoRA配方不同，不能归因纯后端、稳定倍数或1080P收益。服务总时长12145.312s含人工等待/空闲、准入和两trial，不与嵌套阶段相加。详细时间边界、两份媒体与节点证明、全epoch资源见 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-06/experiment-assessment.json`。

两份媒体持久化后，在 fast 人工审核等待期间合作释放 owned46888：exit0、forced=false、graceful=true、port_closed=true；该pair成为历史证明，不再用于新请求。两份技术成功不替代fast真实人工质量；没有fast接受文件、不自动启动06或生产。以下进度段为历史快照。

-06 原 control `11ebef23-82f0-40a4-916d-104f026993ea` 已技术完成（CLI exit0）：40步、高30/低50前向、664/512完整文本、LoRA0；原生fp32 VAE解码及RGB打包/FFmpeg保存均通过。实际 MP4 为 `E:\VideoAI\scratch\benchmarks\LVA-07-05-low-20261120-06\output\lva07\control_1.mp4`，SHA256 `8ec6419f88729213893300402e5a4e1edc556cbf98f05ed7679f677e8370dd50`，768×432/93帧/CFR16/5.8125秒，93PTS及末帧证明已保存，suspect_black=false。复用已有完整媒体proof，未重复解码。

原执行start-to-success1255.786s；高采样468.5191s、低771.9310s、VAE解码7.3655s、编码验真3.7086s。当前epoch原生peak_pagefile17489293312 bytes（约16.29GiB）/peak_working_set20193505280 bytes，10秒观测全设备显存峰值12395MiB（含其他应用）、主机可用RAM最低1094725632 bytes；这些范围不等于独占kernel或采样瞬时GPU峰值。完整原始阶段和资源见 `E:\VideoAI\scratch\benchmarks\LVA-07-05-low-20261120-06\control-assessment.json`。

**当前仍IN_PROGRESS：** control人工质量待真实用户结论；fast未POST、没有人工接受文件。owned46888/epochf111b74f-385c-40d9-b394-7ad0a9c9017d继续保留以维持pair，退出证据尚未产生；不把技术成功当质量或完整任务完成，不启动06。

本轮 -06 同 epoch 双专家准入已实际通过，两份完整 witness 和 client-accepted 保留；原 control `11ebef23-82f0-40a4-916d-104f026993ea` 已首次提交并进入高噪声采样。fast 尚未提交，当前尚无实际媒体或人工质量结论。

-05原control657eeab2完整40步/高30低50前向和fp32VAE解码通过，实际nativecommit峰值17489768448低于18GiB；Save108对CHWT->THWC非连续数组memoryview做SHA时BufferError，发生于encoderintent/ffmpeg之前，没有帧文件或MP4，不能在服务退出后伪造恢复。服务36488合作exit0/unforced/portclosed3868.047s，原失败保留、不重POST。

修复在finite/round/clip/uint8之后只做np.ascontiguousarray，保持原像素和RGB顺序。原布局RED2复现；69相关测试8.60s、同布局真实93帧FFmpeg/单完整RGB解码proof及恢复测试通过，独立审查无重要项。仅2文件交付、旧字节归档，其他数学/输入/预算保持。

新组 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-06`，comparison `c7696ad7f8b484b4f84ca874bc12a3fd7c9be3108ed31e2889374d7ca3dff08d`，原授权与282源快照封存。原文本/图像联合准备6c13231a通过（1.5773362s/4.4642118s），当前新epoch原pair正在执行；成功后control，实际接受后fast。当前IN_PROGRESS，尚无原视频/质量认定。

## 历史继续执行：原始解码的 Windows 提交额度修复

-04已实际完成原40步采样（高30/低50前向，664/512文本、LoRA0），用时high469.190755s/low772.960827s；随后node50原VAE解码conv2d CUDAunknown失败，native提交峰值距12GiB163840bytes。主机仍约16.8GiB空闲RAM，未查到对应驱动重置。服务39592合作exit0/unforced/portclosed3839.563s；失败原875719f4保留，无MP4或fast。

专项原VAE/fp32/93帧/无tiling、相同7GiB逻辑baseline：12GiB失败，32GiB及选定18GiB完整finitefloat32[93,432,768,3]CPU输出；测得commit峰值15282307072(~14.23GiB)，RSS3045511168(~2.84GiB)。这说明小的逻辑提交额度也限制CUDA分配，不等于物理RAM耗尽。选择18GiB提交＋8GiB余量的26GiB availablecommit启动门槛（controller在Job外读取）；RSS24/GPU20/启动RAM14/VRAM21保持，未改模型、精度、tiling、帧数或质量门槛。68测试8.41s、独立审查无阻塞。

新组 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-05`，comparison `04337a20dc43d93758d379eca2b8e92842532aeacc882de1b837efa5dc932e5c`。真实持续授权/282源快照已封存；controller availablecommit45034958848bytes达26GiB；联合准备95cdb413已通过（T5=1.5166723s/VAE=4.5390359s），本epoch原pair正在运行。成功后control、实际接受后fast；当前尚无视频/质量结论，任务IN_PROGRESS。

## 历史继续执行：原生 block 回迁内存修复

-03联合文本/图像准备和原双专家准入已通过2254.014s。control原b4d56a51-b8ec-43fd-b9dc-4a891277b7e9进入首个forward，在native model.py3298 block.to(CPU)处原生0xc0000005退出；WER为VCRUNTIME140.dll。0步完成、无终态history/视频/fast，保留原accepted为unknown、不重POST。owned8216异常exit3221225477/unforced/portclosed，2396.172s；不能记graceful或成功。

原FP8第一块47tensor/351515728bytes、实际AIMDO只读映射下，12GiB进程额度＋5.25GiB空闲CUDApool的短探针重现同栈崩溃；原崩溃瞬时内存未采到，不将短探针当作原进程峰值。局部适配器在相同压力下恢复原CPU参数/常量LoRA存储、清理空闲池后通过：CPU指针完全一致，private12622495744降到6839840768，CUDAreserved6006243328降到0。模型/scale/数学未改，mutable step/strength仍native回迁。67相关测试通过6.61s；审查meta参数异常清理P2及小buffer守卫已一次RED/GREEN修正；真实PyTorch2.14.1 CPUmeta清理检查通过，无GPU。

新组 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-04`，comparison `a0197ea328d4d7d044d7cbdbe475c07791738ab5f533d97415292789fc7288dd`。4任务文件交付及旧字节归档、282实际源快照、真实继续修复/本机预算/不限时许可绑定。先联合准备再新epoch pair/control，实际接受后fast；仍无完整视频/质量/性能结论。当前IN_PROGRESS，06不启动。

## 历史继续执行：VAE局部内存修复已交付

LVA-07-05已按实际修复证据BLOCKED -> READY -> IN_PROGRESS。原93帧/fp32 VAE短探针确认：编码后liveGPU约0.5GiB，CUDApool保留约7.7GiB；回迁前soft_empty_cache将private11766525952->4336513024，CPU回迁成功。候选实际适配器探针通过。61相关测试6.51s；独立审查1项图像绑定问题已RED/GREEN修正，原图在准备前纳入持续只读lease，无其他重要项。

新组 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-03`，comparison `b0ccddde4ce395e0d40d820d7f2d199137533b4b44b9b763f41763eb771a6f14`。原真实不限时/本机预算/继续修复许可绑定，保持12GiB private/24RSS/20allocator。先同worker联合text+image准备，成功后才pair/control/实际接受后fast；生成不重复编码，nativeDecode仍委托原数值路径，仅边界清理空闲池。实际联合worker/采样/质量结果仍待完成。以下为-02历史失败。

## 历史结果：T5与pair通过，VAE回迁触及12GiB额度

当前LVA-07-05 BLOCKED。-02原pair完整成功，2253.834s，high1500/low1459适用与290排除及两head证明保留。control原77da1e64-b42c-4c6d-8b4f-7f83b492faad已过原T5失败点，在固定Wrapper nodes.py:1155的vae.model.to(offload_device)分配15925248bytes失败；nativepeak12884893696距12GiB8192bytes。主机仍约16GiB可用，确定为进程额度峰值。没有Wan采样/媒体/fast。服务11824合作exit0/unforced/port_closed2422.25s。完整事实见当前experiment-assessment.json。下一步先独立诊断VAE回迁/allocator缓存，不先重复约38分钟完整pair。

## 2026-11-20 T5联合修复：原文本实际准备通过

当前LVA-07-05为IN_PROGRESS。修复交付后53项相关测试通过(6.51s)，独立最终审阅0重要/严重问题。新组 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-02`，comparison `e06d44b16e2fe8ffce1fefc647a4a7cbc2e07c4a10dd741d8ca27c926509c4cf`，原真实用户许可持续，无总时长限制，进程commit12GiB/RSS24GiB/allocator20GiB。

同owned PID11824、epoch `d5425839-da87-4be4-9832-b591bd9d580b` 的prepare-text原ID `3f13770f-1c2f-4809-bb89-bcf5f87e14c7` 实际成功：正向[1,664,4096]、负向[1,512,4096]，均float32，finite守卫通过；weakref确认T5已释放。原提示词完整保留，tensor只在同epoch内存中消费，磁盘safetensors仅归档。原生文本阶段1.6414728s不包含前置六模型hash/服务导入；进程观测native peak_pagefile11879981056 bytes，低于12GiB。实际资料见text/assessment.json。

原ID `dfac5207-c443-4464-b638-f1e1e61d8354` 已开始新epoch双专家准入，复用同保护lease/hash窗口。仅在成功后control，真实人工接受后才fast；当前无新视频、质量或性能结论。以下阻塞章节为旧组历史。

## 历史结果：完整pair通过，control在T5准备阶段失败

2026-11-20：**head兼容修复已在原完整双专家上通过；LVA-07-05仍BLOCKED，未生成视频。**

- 原准入ID404d7605-d9ea-40f1-9ab7-85a4454e1c01，当前组comparison7873d50d7e9a8d594aee0412a6c22aa0de788d13ba8655b0088d7347855ce823：high1500/1500保留，689静态/406动态目标；low1459/1459保留，648静态/406动态目标，精确排除290项。两侧head均执行真实CustomLinear前向，四个独立坐标与预期完全一致，scale只作用一次。完整pair与两份witness/SHA已落盘。
- 唯一control prompt fd677a68-086e-4fe5-8be2-47c03135c756在节点10/LVA07Prepare的原生正向T5编码输出转CPU时失败：DefaultCPUAllocator无法分配10878976 bytes。归档history明确仅节点97已执行；Wan采样/解码/保存均未进入，没有MP4、技术完成或人工质量。没有重POST失败ID，fast没有提交。
- 原生进程peak_pagefile为8589914112 bytes，只距8GiB Job提交上限20480 bytes，而主机失败后仍有约16GiB可用内存；说明是进程额度触顶，不是主机RAM耗尽。10s采样不能代替瞬时峰值；完整私有峰值用上述原生计数，GPU观察为全设备含其他应用。当前控制器RSS观察峰值19299463168 bytes，未触发24GiB RSS上限。
- 仅读取原T5文件的4548313-byte spiece分词数据、用原WanT5Tokenizer做CPU分词，未加载编码器或GPU：原positive为664 tokens，negative512；现有条件守卫及Wrapper默认text_len都是512。即使只放宽内存，下一步仍会被文本门槛拒绝或负长度padding失败。不能截断原提示词；机器回执text-budget-diagnostic.json给出精确664。
- 当前服务PID42320/epochb3be9116-7e05-4c47-ad4d-26050c81ec73合作exit0、未强制、8297关闭，服务2832.843s；只读资源observer也已退出（266条）。服务passed只指生命周期，原pair在服务退出后为历史证据，不作为新epoch放行。没有后台模型任务遗留。

当前结果索引为 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-01/experiment-assessment.json`，完整pair、两侧head证明、原失败history、源码快照、资源与分词诊断均保留。已交付head隔离适配及15项CPU/44项协议验证，独立审阅无重要/严重项；未补显式用例为舍入敏感数值、setter自身抛错、同owner更换patch字典。

下一步需先形成并验证T5内存交接及原664-token上下文的联合方案，再评估新源身份/额度/失败原ID边界；不立即重跑完整pair、旧GPU矩阵，不通过截断输入或忽略检查继续。当前资源上限不在运行中修改，旧控制请求不重发；完整视频对照、人工质量和性能收益仍未完成，06不启动。


## 2026-11-20 head适配后的继续执行

用户“继续吧”明确继续head兼容。新增隔离wan_wrapper_head.py：精确验证head.head.weight的一份BF16全量diff，在原CustomLinear中动态安装；普通条目仍走固定repair。准入原forward已验证FP8base先scale、再加delta，原权重/scale不修改；实际采样在原setter调用后补装head，作用域异常时恢复，不加逐forward检查或重新量化。固定Wrapper/repair/适用政策原字节保持。

有界CPU新测试先RED2errors，再15项通过；44相关协议测试通过8.85s。独立审阅无重要/严重问题；次要未补为舍入敏感数值、setter自身抛错及同owner不同patchdict的显式案例，已有实现做相应计算/恢复/拒绝，不进行重复审阅。

新root `E:\VideoAI\scratch\benchmarks\LVA-07-05-low-20261120-01`，comparison `7873d50d7e9a8d594aee0412a6c22aa0de788d13ba8655b0088d7347855ce823`。已保存新真实授权、原源文件及实际执行源码快照，旧失败组/原ID不重发。容量18628698112 bytes可用RAM、23091740672 bytes空闲VRAM达14/21GiB前置。任务已BLOCKED -> READY -> IN_PROGRESS，启动一个无总时限owned GPU服务；真实完整pair、control/fast与质量仍待实际回执，不能由CPU结果外推。下面11-19阻塞章节为历史。


## 最新实际结论：head LoRA兼容阻塞

LVA-07-05当前 **BLOCKED，未完成视频对照**。按用户批准的本机预算已实际启动GPU服务，14GiB RAM/21GiB显存准入生效、无总时长限制、原硬上限保留。当前已不受旧26GiB/22GiB容量或授权阻塞。

-04原准入ID `af954a6a-768b-407e-9041-5a261318d210` 完成high侧1095参数CPU物化后，被实际固定策略拒绝：`UnsupportedPatch: diffusion_model.head.head.weight: upstream explicitly skips dynamic head LoRA`。45秒HTTP超时后仅GET该原ID，取得同ID明确失败，未重POST。实际模型中的该head是CustomLinear动态目标，而固定Wrapper的动态安装跳过head；不能静默漏掉这部分原LoRA或将CPU示例当成实际通过。

没有发布pair，没有进行low侧完整准入，也没有任何control/fast视频POST、媒体或人工质量。没有触发已知资源限制：本组服务观察RSS峰值17768230912 bytes（约16.55GiB），低于24GiB；完整私有commit/GPU allocator峰值未知。Wrapper日志“7,496,177.97 MB”来自其内存统计函数累计重复相加，不是本机实测内存峰值。

owned PID44436，epoch267d53a3-d3fb-4fee-b76d-304c3cdada2f，服务208.094s，正常合作exit0、未强制、端口已关闭。service-result的passed只指生命周期，不是模型/实验通过。结果、failed.json、原始stderr、授权/封存身份和failure-assessment.json均保留在-04；旧-01准备及-02/-03失败也保留，不删除或掩盖。

本轮交付了本机预算/不限时控制器、准入UI回调适配、两条固定同模块别名的精确规范化、失败具体message持久化。44协议测试及12固定函数体CPU测试通过；首次独立代码审阅无重要/严重问题，后续修复由作者RED→GREEN验证，未二次独立审阅。未补次要项：approved=False与空user_evidence的两个显式拒绝用例，当前代码已检查。

接下来需要单独设计并验证head权重应用方案，保留全部适用原增量与量化语义；不能通过删除head patch、改原政策、换模型或降低视频预算继续当前固定实验。任务按未满足完整验收登记BLOCKED，06保持NOT_STARTED，不推广或恢复生产。当前服务退出已核对，无后台模型任务遗留；当前授权保留，后续无需重索同一许可，但新的算法方案需形成明确设计。


## 当前组与第二次兼容修复

当前root：`E:\VideoAI\scratch\benchmarks\LVA-07-05-low-20261119-04`，comparison `cf59a6b273e8b9e83f58d32a9b47e4c3c9a533f640293f1270276f42f56f05eb`。-03原ID已知ValueError失败且正常退出，原message未留存；固定Wan构造器两同模块别名导致原守卫拒绝的原因已用小型CPU复现。只规范化 `original_patch_embedding` / `expanded_patch_embedding` 到同一 `patch_embedding`，不增加任何LoRA适用例外，未知/独立参数别名继续拒绝；12固定函数体CPU与44协议测试通过。未来失败回执会保存具体error_message。完整峰值、双侧准入和视频仍以实际结果为准，不以测试宣称通过。

-03服务284.406s、RSS观察峰值1813954560 bytes、exit0/未强制/端口关闭；原组、原ID及failure-assessment.json保留。新组关联用户既有许可，首次提交本组原准入ID，不重POST旧请求；累计视频仍为0。此前组号/进度章节保留为历史。

## 首次实际准入失败与修复

-02已启动实际GPU服务并观察13类当前HTTP schema。原准入ID `7465663b-8e54-4965-8090-422cfe65a53b` 在high物化最初参数阶段失败：固定Comfy的全局UI进度回调在首次视频prompt前读取不存在的 `PromptServer.last_prompt_id`。原ID GET确认AttributeError，无pair发布、无视频POST；不是模型数学或显存耗尽结论。客户端HTTP500非JSON解析错误为次生错误，原始栈保存在stderr.log。

owned PID29400/epoch70fcf4a5-45e2-4aa8-8882-9980f1ff0c4b正常合作exit0、未强制、端口关闭，服务154.047s、观察RSS峰值1815326720 bytes。service-result的passed=true仅表示服务生命周期，不表示模型准入成功。-02完整保留，并写failure-assessment.json。

退出后独立评估，修复仅在准入线程暂时隔离依赖prompt的UI进度回调，其他线程回调保留，异常后原回调恢复；模型加载、参数/数学/政策和视频预算不变。定向回归RED2fail后44PASS/8.12s；不做第二轮完整审阅。作者裁决：已知基础设施失败且尚无视频，可在修复源码的独立新封存组评估；不是重发旧ID或替代视频。如该裁决有误，代价为额外一次准入，仍无额外视频样本。

当前后续组为 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-03`，comparison `a504cfd077b0ab5e19fc65e01ac7ddcf06d8321d20ca76ec39ea72205f4b841b`；control profile `c8ea8a1ac96d4ba0fd0ae3616f644541ef0292b37751d4c7ebd7b3e83a8ac64d`、fast `903aa16f47f38cce3a96d675deda88b5fbf2d78e1af40f0c995700f67f11d142`。关联用户真实本机预算/不限时授权，旧失败记录不覆盖；详细当前状态以JSON和实际原ID回执为准。

## LVA-07-05 本机预算执行进度

用户“按照本机可以提供的来吧”批准按本机容量执行。调整仅为启动门槛RAM14GiB/显存21GiB及GPU显式授权后的无总时限（--max-seconds0）；私有commit8GiB/RSS24GiB/allocator20GiB/单Wan owner及原视频预算保持。26个基线测试通过，新测试RED3fail/2pass后，42相关测试GREEN；一次独立审阅无重要/严重问题。次要未补项：approved=False和空user_evidence的显式测试用例，代码已拒绝；不做第二轮审阅。

旧-01 root无GPU请求，完整保留。源码/合同改变后首次封存新root `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-02`，comparison `973736939def19675e5fbb92c10afd7304a14528573f99fe2516d09c22278ef2`；新授权明确关联用户真实回复、前组身份与本机方案。新control profile `855f7bcf558d4a0ff9b2bd97a7737179e0d37254dc3de76826b4f446cdd10e60`，fast `de0bee93c66fdaaa7869e761d4c6ecd3dff7c825f64385addbb0317632e19e3d`。

容量观察16816201728 bytes RAM、23085449216 bytes空闲VRAM达新前置，available commit44772716544 bytes不是使用峰值。任务已据授权和容量证据BLOCKED -> READY -> IN_PROGRESS。owned GPU controller已首次启动；节点注册、实际模型准入与采样结果按后续真实证据更新。完整机器状态见LVA-07-results.json；当前未取得任何新媒体或人工质量结论。旧准备/重试章节为历史。

## LVA-07-05 重试检查

用户回复“你再试一下，时间可以不限制”，已批准此前具体比较组，并取消总时限。真实授权证据已写入实验root的 `authorization.json`，无需再次询问同一许可；control仍须单独真实人工接受后才执行fast。

2026-11-19T06:50:50.957429+00:00再次只读观察：可用RAM17176109056 bytes（约16.00 GiB）、空闲VRAM23014146048 bytes（21.43 GiB），仍低于26/22 GiB要求，分别还差约10.00/0.57 GiB。没有启动GPU worker、加载模型或发准入/生成POST；任务继续BLOCKED，当前阻塞是容量不足。原始记录在准备目录的 `retry-observation-02.json`，最新机器汇总在 `LVA-07-results.json`。

不限总时长的用户要求已记录，现有controller仍有14400秒校验；尚未修改其源码或已封存profile。资源前置解除后，应在首次实际执行前适配时限及核对源身份，不使用现有4小时命令冒充无限制执行。当前主机QQLive约3.10 GiB、PyCharm约2.64 GiB工作集属于只读观察；未关闭任何用户进程，工作集合计不等于保证可释放容量。

## 首次准备记录（历史）

2026-11-19：**BLOCKED，未完成真实 GPU 对照**。已核对原低运动输入并初始化新的隔离比较组；容量前置未满足，且尚无绑定本比较组的具体 GPU 执行授权。没有加载大模型、启动 GPU 服务、提交准入或生成视频。前项 CPU/离线结果保留在 `LVA-07-04-results.json/.md`，不作为本项真实兼容或质量结论。

机器证据：`docs/task-designs/LVA-07-results.json`；原始准备回执：`E:/VideoAI/scratch/benchmarks/LVA-07-05-preparation-20261119-01/preflight.json` 和 `init-result.json`。原 next-task 交接已保存到该目录的 `entry-next-task-handoff.md`。

## 已准备的具体比较组

- Root：`E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01`，新建成功，没有覆盖已有实验。
- Comparison SHA256：`d638a6abb9c2d40796fa438107eefcbcb5520f24dd4e1e51365b596065cf605f`。
- Control profile：`f360961c7aff85e7eeb683ec967405084b0672ee28403cd1daac4a8667e5a1eb`。
- Fast profile：`0c94105519244ef2d5115022d4b2db8e19be78e5ec64498cd0b0d34e9a72fd57`。
- Control graph：`1ac7eb835c697d7e12d043f169575475ba73e73740f965f2b3899b7317c29665`。
- Fast graph：`5321702efe6719baed36e580efba73b68bf47d29f1970b92473a63b770fd4f00`。
- Fixture：`4f01a950bbd61bb87510f5cb9bdcd7da7621577f6f8f5fae6e56902dbe16f84d`。

原请求文件 SHA、fixture 字段、prompt/negative 的原值及摘要、小图片 SHA、预算及 seeds 核对通过。原低运动图片 SHA 为 `57ca0f059560e5582888e3f7e0080a3d6b04ab5d47df246c572f738c125d7df2`，high seed264244520398999、low seed0。报告不保存提示词原文。新比较组的两 profile 和图通过现有 `prepare(root, control_profile)` 校验；没有重复04测试、全模型哈希或历史视频解码。

## 容量与阻塞

观察时点：`2026-11-19T02:23:24.401580+00:00`。RAM 来自 `GlobalMemoryStatusEx`，显存来自 `nvidia-smi memory.free`；均为当时可用容量，不是完整模型峰值或运行保证。

| 项目 | 实测 bytes | 要求 bytes | 结果 |
| --- | ---: | ---: | --- |
| 可用 RAM | 17039007744（15.87 GiB） | 27917287424（26 GiB） | 不足约10.13 GiB |
| 空闲 VRAM | 22726836224（21.17 GiB） | 23622320128（22 GiB） | 不足约0.83 GiB |
| E盘可用空间 | 1416317292544 | 536870912（512 MiB） | 满足 |

GPU 为 NVIDIA GeForce RTX 5090 D v2，报告总显存24455 MiB；8297可绑定，未启动监听服务。未关闭用户应用或修改限额。运行时仍保持私有commit8 GiB、RSS停止24 GiB、GPU allocator20 GiB及单Wan专家；实际峰值未知。

## 待确认的执行范围

设计依据：`docs/task-designs/LVA-07-05-design.md` 的 Scope 与“精确准备与授权”。原文要求“必须先取得用户对本具体两样本/资源/失败边界的新GPU执行授权”；本次“完成任务”记录为启动任务的证据，不生成 `approved=true` 或人工质量接受文件。

待批准范围为上述comparison：原六模型和同一输入，最多两次768×432/93帧/16fps生成；先完整high/low双专家准入，通过后一个无LoRA的40步control，真实人工接受后才一个强度1/1的4步fast。owned服务端口8297、最多4小时；失败停止，unknown只追原ID；不下载、安装、换模型、追加样本或扩展矩阵。整数time步与VAE路径差异保留，不声明纯后端等价或稳定加速。

初始化实际命令，exit0：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper.py init --root E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01 --fixture E:/VideoAI/scratch/benchmarks/LVA-07-04-cli-fixture.json --port 8297
```

已封存比较组，无需再运行init。资源达标且取得实际授权后，才按05设计创建该root下的 `authorization.json`，启动owned worker及原ID准入/control；本报告不是可替代的授权文件。若worker从未启动，本root仍可用于后续首次执行。

## 尚未验证

完整14B逐项安装及真实forward、control/fast采样和媒体、人工质量、阶段计时、完整资源峰值及worker退出均未执行。当前没有control或fast原ID，也没有unknown请求需要恢复；不得虚构exit0或速度指标。LVA-07-06保持NOT_STARTED，不准备扩展交接。资源和授权解除后仍须完成本项设计中的准入、control审核、fast审核及真实结果收尾。
