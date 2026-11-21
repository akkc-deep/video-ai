# LVA-07-04 隔离 worker、workflow 与恢复 harness 设计

## Goal

交付一个仅用于新实验的可执行Wrapper后端：固定源码/环境/模型/工作流身份，完整mixed-delta准入可以在fast视频POST之前执行，保留原ID恢复、标准媒体和owned退出契约。此任务只实现、做CPU/离线验证和受限CPU节点探测，不执行真实14B加载、GPU采样或生产接入。

唯一任务板：`docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`，任务 `LVA-07-04`。本设计是作者依据实际证据形成的工程选择，执行授权来自用户原始“完成任务LVA-07-04”及后续连续“同意，继续吧”；不冒认用户逐条指定了技术细节，也不为同一已授权的可逆代码工作重复索取许可。不能把本文件当已经实现或GPU已获授权。

## Scope

包括独立profile/能力和身份封存、原生T5到Wrapper的现有桥接、单专家私有构建/静态覆盖、双侧原子准入、40/4步图、owned worker、原ID提交/恢复、MP4/完整帧/PTS/末帧数据、CPU故障与媒体验证。复用已经安装的独立环境和原六份模型，不再下载、安装、换模型、修改现有Wrapper修复/CPU政策或生产默认。

不包含真实完整模型准入、视频采样、人工质量、1080P超分/合成实测、冷1热3或父子GPU矩阵。这些留在LVA-07-05/06；代码必须能执行相应门槛，但本项用小型真实CPU模块证明机制，不能将其结果升级为14B通过。原生workflow、即梦文件/协议、旧run、原CPU RED证据和暂停生产保持。

## Approach

### 已建立的直接输入

1. `LVA-07-03-preparation-execution.json/.md`：完整244文件修复快照、独立CUDA runtime、102个固定分发和pip check通过。Comfy commit `2c75dc1b379a59e0880619d029607af5169a62ef`，Wrapper上游 `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`。实际为完整固定源码快照，不伪造Git checkout。
2. `LVA-07-03-node-probe-results.json`：首次9个节点及针对现有原生桥接的另4个HTTP schema均通过；两个进程为41668/42348，均结束，8297关闭，峰值RSS分别908124160/908550144 bytes。均为CPU模式，CUDA构建的torch实际被导入，不是GPU设备运行；日志的“VRAM 31801MB”是CPU模式主机RAM，不能作为GPU显存。
3. `LVA-07-02-applicability-results.json/.md`、固定 `patches/wanvideo-wrapper/lva07_img_policy.json`：High1500/Low1459适用输入的真实CPU数学及精确Low290不适用。实际14B/forward/offload仍未验证。原helper六个模型所有者约79.88GiB base文件代理，不允许调用该helper处理14B或抬高256MiB限制。
4. `LVA-02-design.md`及原恢复协议：intent先落盘、唯一原client/prompt ID、unknown不重发、完成媒体先验真复用；本项不改核心生产恢复代码。
5. `LVA-07-04-contract.json`：由固定源码真实函数体的CPU执行得到control/fast float32 sigma和实际int64时间步、源函数摘要及内存组成。原始回执为 `E:/VideoAI/scratch/benchmarks/LVA-07-03-planning/wrapper-contract-cpu.json`，不是实际采样调用数证明。

### 方案选择与新发现

采用“原生T5编码+上游已有文本桥接、一个活动专家、私有小型静态覆盖、双侧receipt原子发布”。这些是作者的实现建议，不冒认用户已经选择。

- 原有Wrapper T5节点**不能**直接加载本机T5：有界48848-byte header有 `scaled_fp8`，固定 `LoadWanVideoT5TextEncoder.loadmodel` 明确拒绝。原生 `CLIPLoader(type=wan,device=default)` 已用于原质量图；上游 `WanVideoTextEmbedBridge` 已提供原生CONDITIONING→WANVIDEOTEXTEMBEDS，真实HTTP schema和原函数CPU数值传递均已确认。沿用原模型/分词/提示词语义，不转换或重下T5。
- 全量deepcopy方案超过RAM且违背CPU helper限制，排除。merged已数值复现漏modulation，排除。私有构建保留原始只读mmap权重，只对静态增量涉及约11MB/9MB目标建立独立存储；动态矩阵继续使用已审定CustomLinear数学。
- 不在sampler之后修补静态值，不放宽legacy guard。准备后的静态张量写入**私有** `sd` 覆盖层，使原sampler每次 `load_weights` 都读到“原值+delta一次”的同一值；offload转meta、再reload不会丢失或累加delta。

**Control完全没有LoRA。** control只调用新建的unpatched owner：不解析/安装LoRA、不应用任何静态delta或动态patch，不使用CertifiedPair/静态覆盖，实际patch字典和CustomLinear LoRA buffers必须空，applied数量=0。fast才使用两侧strength=1及全部适用增量；固定六文件身份中列出LoRA只是比较组身份，不表示control使用了它们。后续LVA-07-05编排顺序仍为先执行独立pair gate再control，控制的是实验准入顺序，不改变control数学；control节点本身不以pair receipt为无LoRA构建的参数，误传覆盖/认证patch应拒绝。

### 组件及公共接口

新增模块均在 `video_ai.experiments`，不在生产入口接线；无torch的模块在普通项目解释器可导入。

| 组件 | 固定接口与职责 |
| --- | --- |
| `wan_wrapper_backend.py` | `WrapperProfile`不可变数据、`capabilities()`、`freeze_comparison(root,profiles,fixture)`、`prepare(root,profile)`、`WrapperExperimentClient.submit/recover/collect/close`。profile数据/graph/fixture/profile-binding均canonical JSON，SHA256与`write_once`沿用现有helper；禁止NaN/未封存字段 |
| `wan_wrapper_lora.py` | `admit_pair(factory,fast_profile,leases)->CertifiedPair`、`prepare_control_expert(factory,role)->PreparedExpert`、`prepare_expert(factory,role,certificate)->PreparedExpert`（仅fast）、`release_expert(owner)`；仅调用时导入torch，直接使用固定Wrapper真实normalizer/mapper/Comfy parser和repair数学 |
| `wan_wrapper_nodes.py` | `register_nodes(registry,worker_context)`，只在owned worker init_extra_nodes之后注册三个实验类；实现prepare、分段sampler、输出。不得改原Wrapper类或生产注册表 |
| `wan_wrapper_media.py` | finite IMAGE检查、受限raw RGB编码、调用既有一次全解码inspector、收集媒体/PTS/末帧证明。普通单元测试不导入torch |
| `observe_wan_wrapper_comfy.py` | controller/worker两个入口；配置在torch导入前完成，记录PID/start/argv/端口/job和源摘要；实现CPU探测及未来GPU模式的严格授权分离 |
| `benchmark_wan_wrapper.py` | `init`/`graph`/`probe-cpu`/`offline-selftest`/`recover`；未来 `admit-pair`/`run`路径有LVA-07-05专用许可检查。本任务不执行后两项 |

`WrapperProfile`字段固定为：schema_version=1、backend=`wan_wrapper`、kind=`experiment`、mode=`control`或`fast`、source/runtime/tool/model/policy身份、recipe、frame_contract、memory_limits。fixture摘要属于request/比较组，不纳入backend mode profile本身，避免父子因首帧不同被误判成不同backend profile。不得接受任意模型/LoRA集合。模型角色为base_high/base_low/t5/vae/lora_high/lora_low，路径/bytes/完整SHA沿用environment manifest；额外记录header身份与实际首次准入状态，不把历史SHA冒充本次payload已读。

#### 比较组、mode profile与请求的确切身份

control与fast的profile SHA **必然不同**。共同身份 `comparison_sha256` 是以下canonical对象的SHA：schema_version、backend、kind、全部source/runtime/tool/model/policy身份、固定文本/VAE/图像准备/编码配置、compute/attention/offload/memory配置、frame_contract，以及完整fixture摘要（图片/prompt/negative/seed/预算/parent绑定）。不含mode、两种recipe、派生graph、端口/PID或人工等待；后者分别在profile/request/service epoch记录。

比较函数只允许固定差异：mode；steps/CFG/split；sigmas/timesteps与预期forward次数；LoRA启用/strength（control关闭、0/0，fast开启、1/1）。这些差异必须等于contract两套固定值，不能接受任意白名单字段值。其他字段全量相同。原图/输入/seed/VAE/T5/精度/源文件任一变化都改变比较组并拒绝旧control接受。

一个新root对应一个comparison，不给control/fast分别创建互不关联的root。`init`一次封存 `frozen/comparison.json`、`frozen/profiles/control.json`和`fast.json`、`frozen/graphs/control.json`和`fast.json`、`fixture.json`；模板默认control只是builder默认选择。`experiment.json`包含comparison_sha256及两个mode profile SHA。只有两套文件完整且派生自同一common对象，worker才能启动。worker-attestation绑定comparison、两个允许profile SHA和本次owner epoch；各trial的profile-binding/intent/history/媒体只绑定自身mode profile及graph SHA。

trial ID当前仅 `control_1`、`fast_1`。control技术记录及人工接受文件 `reviews/control_1.json` 必须绑定comparison_sha256、control_profile_sha256、fixture_sha256、control_graph_sha256、原control prompt_id和实际媒体SHA，decision=`accepted`并有真实用户review证据；fast检查它**对应control profile**，不能要求它等于fast profile SHA。只要比较组/上述控制记录漂移，fast就拒绝。native W0或其他Wrapper profile的接受不复用。pair receipt绑定fast profile SHA、comparison SHA和当前live owner epoch，不能用control profile的记录冒充。

父子限制仍按同mode/backend profile检查，fixture/输入可以不同但必须有原父片接受与真实尾帧重绑；不能只比较comparison SHA放行跨mode父片。当前低运动比较组只生成control/fast两份；parent/child在本项仅验证恢复/拒绝规则，不扩展真实矩阵。

能力记录分 `observed_cpu_http`、`declared_experiment_node`、`verified_current_worker_http` 三种来源，不能混写。真实submit要求当前worker实际返回所用节点schema并绑定本次worker-attestation；目前13份历史CPU schema只能作为建图依据。缺任意必需类/输入/输出、错误模型目录、两个加载Wrapper源根、未知版本/依赖/别名均拒绝prepare/POST。

实际实验root必须新建在 `E:/VideoAI/scratch/benchmarks` 下；source root由入口自身文件位置计算并封存，不假定在另一个工作树中仍使用旧repo/src。普通unit/integration用临时root；fixture profile带 `kind=offline_fixture`，真实网络CLI无条件拒绝该kind。测试注入transport不成为生产CLI的跳过准入选项。

### 单专家所有权、原子发布及静态覆盖

Factory只能从固定owned Wrapper类/组件构建，接口为 `build_unpatched(role)->ExpertOwner`，包含patcher、transformer、original_sd及单独的关闭责任。精确调用参数：base_precision=`fp16`，quantization=`disabled`（按文件自动识别scaled FP8），load_device=`offload_device`，attention_mode=`sdpa`，lora=None、compile_args=None、vram_management_args=None、额外模型均None、rms_norm_function=`default`。硬检查实际 `fp8_matmul=False`、scaled FP8、40 blocks及来源；不能仅信传入选项。

Admission构建和数值探针都在CPU：对新私有transformer用原 `load_weights`、transformer_load_device=cpu、block_swap_args=None实现物化。构造器在GPU worker中可能先生成CUDA scale标量；admission owner明确使用其独立CPU副本，保持值/dtype，且不会将该admission模型返回采样。实际采样阶段新建owner，保留原loader对应设备的scale；不复用已经offload/meta或CPU探针改变设备的对象。

每个role按以下顺序处理，任何异常丢弃本role与未发布pair：

1. 在输入保护窗口中核对实际base/LoRA文件身份、header、normalizer/mapper/parser和policy身份。仅首次实际GPU任务准入完整哈希原六模型一次，保持deny-write/delete lease；CPU fixture/节点探测不触碰大模型payload。丢失lease、代码或身份变化一律拒绝，不反复每步扫描。
2. 原始LoRA全部1500/1749源项独立对账；精确290项只记不适用，不能算消费或应用。用固定source schema执行原政策的分类，另对实际transformer逐target验证shape/运行dtype、没有img目标。原CPU政策文件及函数保持不变。
3. 运行dtype转换只允许固定 `load_weights` 的已知规则：FP8有scale的矩阵保留F8_E4M3；普通静态值为FP16；`patch_embedding.weight/bias`为原函数规定的FP32。后两者从原F16精确扩展，不增加排除项；任何其他转换/未知key/碰撞/别名/非有限/shape冲突均拒绝。原SD shape/dtype与实际目标证据分别保存，不能用代理schema冒充实际目标验证。
4. 用真实normalizer→mapper→Comfy parser，验证每个适用源tensor被读取且是最终patch槽中保留的同一对象，不能被后项覆盖。只接受普通rank64 LoRA/diff/diff_b/diff_m标准化结果；strength两侧固定1。source数量不是patch数量，按逐项trace记2959适用及290不适用。
5. 预检用固定repair的 `_preflight(transformer,parsed,1.0,parameters=actual_named_parameters)` 数学规则；这是新单专家owner路径，不调用旧 `prepare_lora_pair` 或 `_model_info` 的小模型入口，不改它们的上限。保证actual owner新建/无已有patch、任何目标和patch状态不共享给其他模型。先完成预检，再允许写私有数据。
6. **先clone静态目标**，绝不向只读mmap/原SD tensor执行copy_。创建原SD字典的浅副本，对静态target建立独立parameter/存储，按repair `apply_static_deltas` 的FP32累计→目标dtype规则应用一次。保存独立prepared-static tensor到私有覆盖层，绑定source/target/recipe SHA；原SD/原文件不变。每次从认证缓存借给actual owner时再clone这些小张量，不能让可写parameter别名回到缓存。
7. 动态patch通过真实 `custom_linear.set_lora_params` 安装；真实CustomLinear CPU forward用一行确定探针，拦截其最终linear输入weight只记录固定四个坐标与scale/alpha/rank/strength证据，再调用原linear。坐标期望只做rank64小点积，不再生成第二个全矩阵。检查实际buffer槽与源payload对应、scale恰好一次、输出有限、无遗漏；探针后reset原_step=0。每个target只做一个准入边界探针，不加进denoise循环。
8. 将patcher.patches设置为**仅动态**patch，patcher.model['sd']设置为私有prepared SD，明确merge_loras=False/lora_scheduling_enabled=False。静态覆盖的重复应用/在原量化值上反向相减均拒绝；移除方式为释放owner并从不可变base重新构建。
9. 记录本role witness，释放patcher/transformer/原SD引用、卸载当前owned模型并gc。仅weakref跟踪活动owner；释放后仍存在强引用或第二个owner将被创建时拒绝。原生T5、VAE等对象不能被误算为第二个Wan专家，但不得保有上一侧Wan。

先high释放，再low释放；两侧witness都通过、身份/策略一致后，才atomic rename临时pair receipt为 `admission/pair.json`。high成功/low失败的诊断文件不构成任何可用单侧/pair，不发布模型对象或可POST令牌。CertifiedPair只持有只读源payload/parsed引用、约20MB独立静态覆盖和逐项证据，不持有完整模型；按profile/lease寿命失效。允许同一受保护worker复用准入数学，实际每次采样仍新建一个owner、核对实际安装/对象shape并使用认证覆盖，不重复全模型全量数学/哈希。

以上是fast准入/准备分支；`admit_pair`只接收fast profile，control不得进入此分支。Sampler在fast时从prepared SD重载，静态值已含一次delta；不再调用apply_static_deltas，set_lora_params只见动态patch。control始终从原始未改SD重载，原sampler空patch分支只清理LoRA。offload转meta后两种mode都必须恢复各自准确数值，不能从fast缓存污染control。CPU测试真实调用固定load_weights和offload/等价meta迁移证明此不变式，不以一次赋值或patch计数代替。

### 三个实验节点与图

只在独立worker后置注册，类名/输出固定：

| 类 | 必需输入 | 输出/行为 |
| --- | --- | --- |
| `LVA07Prepare` | start_image:IMAGE；positive_prompt/negative_prompt/clip_name/vae_name:STRING；width/height/num_frames:INT | `(WANVIDIMAGE_EMBEDS,WANVIDEOTEXTEMBEDS,WANVAE)`。在单GPU mutex内完成原生CLIPLoader(type=wan,device=default)、两次CLIPTextEncode及现有WanVideoTextEmbedBridge；再卸载/释放T5、文本tensor转CPU；随后调用Wrapper VAE loader及I2V encode，避免图缓存保有T5模型与Wan并存 |
| `LVA07Sampler` | role:high/low；mode:control/fast；model_name:STRING；image_embeds/text_embeds；seed:INT；optional samples:LATENT | `(LATENT,)`，仅调用原WanVideoSampler首个samples输出。持单专家mutex，进入owner上下文、按角色recipe调真实sampler、记录实际forward次数/实际sigma/设备/耗时、finally释放owner，模型对象不进入图缓存 |
| `LVA07SaveVideo` | images:IMAGE；fps:INT；filename_prefix:STRING | OUTPUT_NODE=True、RETURN_TYPES=()。先finite和帧/shape检查再uint8/编码，返回 `{'ui':{'images':[{'filename':..., 'subfolder':..., 'type':'output'}]}}`，使原ExperimentClient输出108契约可复用 |

LVA07Prepare对每侧原生CONDITIONING要求恰好一个条目、batch1、token数1～512、末维4096、有限，拒绝多段scheduled/区域/其他未支持语义而不静默取第一段。正负prompt原文不改、不替换模型；Native bridge逐值传递既有张量，metadata无调度才可使用。T5的scaled marker保留，禁止调用Wrapper直接T5 loader。GPU真实编码留待LVA-07-05。

VAE为现有wan_2.1_vae.safetensors、precision=fp32；I2V固定start_image、noise_aug_strength=0、start/end_latent_strength=1、force_offload=True、fun_or_fl2v_model=False、tiled_vae=False、其余可选输入None/默认零；num_frames必须93，不能接受上游四舍五入为另一预算。解码enable_vae_tiling=False、tile_x/y=272、stride_x=144/stride_y=128、normalization=default。VAE精度作为明确profile变量保存，不能将本套native-T5/Wrapper-VAE配置外推纯后端收益。

图节点固定：97=`LoadImage`；10=`LVA07Prepare`接97；30=high `LVA07Sampler`接10的0/1；40=low sampler接10的0/1和30的samples；50=`WanVideoDecode`接10的VAE和40；108=`LVA07SaveVideo`接50。文本和图像准备在一个节点中串行；low依赖high，最多一个Wan owner，默认不跨场景并行。

workflow模板默认control，graph builder只按已封存mode/fixture构造control或fast图。mapping字段为positive/negative→10，first_image→97，width/height/generated_frames→10，seed_high→30、seed_low→40，model_high/model_low→30/40、T5/VAE→10、fps/prefix→108。provenance引用本contract和真实schema/source身份；拒绝用户向单个图临时注入节点/参数。

### 固定采样、计时和资源

低运动输入、prompt、negative、seed和768×432/16fps/93帧沿用LVA-01，profile读取原fixture摘要；复制选图只做一次准入，不打印prompt。high seed=264244520398999，low seed=0。不同fixture需新profile/root，当前不扩展高运动/父子真实矩阵。

- control：40步、CFG3.5、Euler、shift5、high [0,15)、low [15,40)；使用contract中真实native `simple_scheduler(ModelSamplingDiscreteFlow shift5)` 的float32完整41点sigma，不使用Wrapper默认线性生成。fast：4步、CFG1、high [0,2)、low [2,4)，sigma float32 `[1,15/16,5/6,5/8,0]`。
- 两侧均将完整sigma传给原 `get_scheduler`，由其按start/end切片，不能在high尾部追加0。实际time-step int64由原函数产生；fast `[1000,937,833,625]`，control值在contract。int截断与native浮点模型时间不严格等价，`pure_backend_equivalence=false`，不得改成true或宣称纯后端倍数。
- sampler固定riflex=0、batched_cfg=False、rope_function=comfy、force_offload=True、denoise_strength=1、add_noise_to_samples=False、cache/slg/feta/context/loop/其他多模态参数None。预期外层transformer forward control high30/low50、fast high2/low2；必须记录实际次数并匹配，不用UI步数替代。不同计数停止、不发布技术通过。
- 实际阶段计时从profile/选图交接开始：来源准入、服务导入、T5、VAE encode、每侧构建/应用/采样/释放、decode、编码、媒体验真单列。人工等待单列。设备GPU采样不说成独占kernel时间，嵌套节点时长不相加成总计。没有GPU样本则仅记录CPU/离线测试时间。

共同profile/来源/pair gate耗时只记为comparison的group_setup_seconds，不混作control的采样时间再从fast扣掉。每trial分别记submit-to-output、后处理、人工等待和实际elapsed_since_group_handoff；只有每个mode一个样本，不报P50/P95或稳定速度比。模式各自的cold/hot和共享准备收益按实际记录，不因同一service便声称同等冷启动。

mode/profile：fp16 compute、原scaled FP8矩阵与scale，SDPA、compile=False、merge=False、fast FP8=False、low_mem_load=False、block swap40/prefetch0/non_blocking=False、offload_img_emb/offload_txt_emb=True、vace_blocks=0；不启用DiffSynth额外offload。GPU实际任务禁用SDPA math fallback，flash/efficient不可用即失败，不改精度/注意力方式重试。

内存原理/预算列在contract：每侧动态输入623149056 bytes，静态输入/目标high11315328、low8837248 bytes，最大FP16有效矩阵314572800 bytes。动态payload私有副本/转换按最多三份约1.87GB；最大FP64预检临时约1.26GB，布尔/临时矩阵按另1.5GB、runtime/元数据/媒体余量计，预计私有工作量约6GiB；这不是实测峰值。base只读mmap约13.3GiB/侧、源LoRA映射最多约1.3GiB，不同时物化两侧模型，不将文件映射视为零RSS。

本项CPU注册/小张量测试仍以4GiB私有commit/RSS停止阈值、512MiB新fixture磁盘预留执行；不读取大模型payload。未来实际完整模型/采样单独配置：最少26GiB可用RAM、22GiB空闲VRAM；owned worker私有commit硬限8GiB、RSS停止24GiB、torch GPU allocator上限20GiB，单活动专家。CUDA activation/attention/workspace是否适配留给LVA-07-05实际门槛；显存来源沿历史24455MiB，不用CPU探测RAM冒充显存。未满足可用容量/限额就停止，不能自动结束用户应用或放宽上限。当前可用RAM不足26GiB不妨碍本项小fixture/CPU实现，但绝不授权或放行真实加载。

新增实现/回执/fixture磁盘预留512MiB，模型新增副本/下载为0。私有静态覆盖和LoRA临时在worker内存，不重打包两套14B；输出/最终1080P全链预算由后续任务单列。本设计建立的是有限投入和失败边界，完整模型实际峰值仍为null。

### Owned worker 与准入端点

复用现有observe_local_comfy的“main导入后挂init_extra_nodes”结构，不改其文件：worker先设置argv/CPU或GPU目的，再runpy固定main。init_extra_nodes完成后找到唯一固定Wrapper模块，注册三个实验节点和HTTP路由，再由main启动服务。只允许本profile封存目录/解释器/源码，禁用其他custom nodes和assets，离线，不开浏览器；输入/输出/temp/user/database均落新root，模型目录只读。

controller持有原Popen handle和Windows Job，记录PID/start identity、argv/environment摘要、port/launch/profile SHA、worker-attestation；监听者PID/地址必须一致。CPU probe禁CUDA/生成/大模型加载，180秒、4GiB私有限额；未来GPU模式必须有单独的LVA-07-05授权记录并满足资源预检，默认CLI不允许GPU任务。退出只处理本次handle/job，不kill陌生PID，不恢复暂停生产。stop请求合作退出，超时才结束owned进程，记录真实退出码（强制退出不得标graceful/exit0）和端口关闭；unknown请求/队列状态先持久化，不自动重发。

准入接口 `POST /lva07/admit-pair` 只在未来GPU授权模式开放，body仅profile_sha256及唯一admission_id，不接收任意路径/模型。intent在处理前持久化；未完成/低侧失败不发布pair。响应丢失后只GET `/lva07/admission/<original_id>` 取原receipt/失败/unknown，不能再次执行POST。CPU模式端点必须明确拒绝，不创建模型。pair receipt包含原admission ID、owner epoch、profile/source/model/LoRA/policy身份、两侧逐项trace摘要及实际安装/forward probe结果。只在本live lease上下文有效，重启必须重建证明，旧receipt是历史证据。

### 视频提交、恢复及输出契约

客户端复用 `wan_fast_experiment.baseline_api().ExperimentClient` 的durable协议，新增Wrapper身份/图/receipt边界；不使用native FastProfile校验器来冒充Wrapper profile。

1. 先 `completed()`：有完整记录时，核对immutable profile/fixture/request、原intent→accepted ID→归档history和媒体SHA/内容/规则证明，返回原结果，0 HTTP/0 producer；记录或文件被替换则拒绝。重启清掉进程内证明，从durable证据严格重建，媒体至少重新验真一次。
2. 新control/fast请求写本mode profile-binding/frozen request、原durable intent后才POST。fast在POST前要求本worker的fast-profile pair receipt，以及上述**同comparison/input且绑定control profile SHA**的技术/真实人工接受记录；不比较两个不相等的mode profile SHA。技术检查/同字节不能自动构造人工接受。最多一个control及其后一个fast，用户未授权真实GPU则真实transport一律拒绝。
3. accepted UUID必须canonical、node_errors必须空；重复/冲突accepted、图/client/prompt/service身份冲突均拒绝。POST超时只查同client/graph的queue/history，唯一候选才绑定；零或多个候选保持unknown，不再次POST。poll/collect只读原ID，不取消/替换/换模型。
4. 服务重启先验证新的owned进程/source/profile和原ID证据。原归档history及已存在输出可以在新保护窗口验真收集；当前服务无原ID且无足够归档时保持unknown。没有持久化的扩散中间步不恢复、不重新生成；失败源/部分编码保留原ID，不当完成输出复用。
5. 集成测试包含父片绑定：保留既有接受/尾帧/同mode profile约束，通过Wrapper专用 `accepted_parent_binding/verify_parent` 适配器核对本后端封存布局；原native helper强制native profile路径，不能直接复用。requires_new_parent为真且没有完整binding时明确拒绝，child实际输入SHA须等于原接受尾帧。任何缺失或变化均阻止新child。当前不实际生成parent/child，也不泛化原生profile接受记录为Wrapper接受。

媒体输出：93×432×768×3的finite IMAGE先检查，再按与现有Comfy保存逻辑一致的uint8量化（clip(round(x*255),0,255)），禁止NaN/Inf经uint8掩盖。写唯一新partial路径；ffmpeg raw RGB24/16fps输入，libx264、preset medium、crf18、yuv420p、无音轨、faststart，禁止覆盖已有候选。argv/tool身份与源帧/encoder intent在发送帧前落盘。只有进程成功、完整93帧/PTS/尺寸/FPS/一次完整RGB decode及SHA通过才晋升输出；失败不改采样或重POST。

复用 `wan_fast_media.inspect_media` 所用的 `baseline_api.media_command`、`validate_video_probe` 和 `black_frame_summary` 原语，在新media模块组织唯一一次完整RGB解码并直接保留最后一帧；不再调用会隐藏RGB缓冲的原inspect_media整体函数，因而无需改老helper或做第二次解码。黑帧/末帧/统计共用此结果。既有retained==generated的本低运动样本复用同一媒体/检查证明，不重编码同样93帧。传给后续的是generated/retained/last_frame路径、SHA、frames、实际PTS、width/height/fps、原prompt ID和profile/fixture/request/graph摘要，质量状态为awaiting_human_review。

`SceneClipResult`实际是生产run聚合对象，会拒绝scratch run；本项不伪造此实例。collect返回与现有实验trial record兼容的标准媒体dict，供未来生产adapter消费；不改聚合schema或生产records。record用 `technical-complete.json` 原子落盘，明确未做1080P/人工验收。

## Files

新增：

- `src/video_ai/experiments/wan_wrapper_backend.py`：profile/schema/图/原ID客户端；从实际模块路径封存身份，torch延迟加载。
- `src/video_ai/experiments/wan_wrapper_lora.py`：上述单专家factory、私有静态覆盖、实际解析/安装/探针、原子pair与释放。
- `src/video_ai/experiments/wan_wrapper_nodes.py`：三个组合节点、与原Wrapper类的固定委托和准入路由。
- `src/video_ai/experiments/wan_wrapper_media.py`：finite/编码/一次decode/媒体证明。
- `scripts/observe_wan_wrapper_comfy.py`、`scripts/benchmark_wan_wrapper.py`、`scripts/verify_lva07_wrapper_runtime.py`：owned worker、offline/恢复入口、独立CPU fixture验证器。
- `workflows/wan22_i2v_14b_wrapper_api.json`、`.mapping.json`、`.provenance.json`：上述六节点模板、精确mapping、control/fast派生和身份/非等价说明。
- `tests/unit/test_wan_wrapper_backend.py`、`test_wan_wrapper_media.py`；`tests/integration/test_wan_wrapper_recovery.py`、`test_wan_wrapper_worker.py`；`tests/experiments/test_lva07_wrapper_runtime.py`（unittest、默认opt-in跳过tensor路径）。
- `docs/task-designs/LVA-07-04-results.json/.md`：实际结果、限制及预算/实际身份；实施计划在本设计确认后另写。

只更新LVA-07环境manifest、投入决定、当前任务板和已要求的设计/交接；不修改已验证patch/policy函数、生产模块/默认配置、原生graphs或旧run。实现工作树位置/临时fixture文件名、内部小型helper拆分和标准编码细节留给builder；上述接口、数学、生命周期、budget和拒绝规则不得由builder另选。

## Tests

先为缺失/漂移/静态reload/unknown恢复建立RED，再实现GREEN。下面是实施后的命令与预期，本设计阶段尚未运行产品测试。

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_wan_wrapper_backend.py tests/unit/test_wan_wrapper_media.py tests/integration/test_wan_wrapper_recovery.py tests/integration/test_wan_wrapper_worker.py -q -p no:cacheprovider
& .tools/python/python.exe -I scripts/verify_lva07_wrapper_runtime.py --wrapper-root E:/VideoAI/scratch/benchmarks/LVA-07-04-environment/ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper-LVA07 --comfy-root E:/VideoAI/scratch/benchmarks/LVA-07-04-environment/ComfyUI --cpu-python E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/runtime/python.exe --cpu-site E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/cpu-site --output E:/VideoAI/scratch/benchmarks/LVA-07-04-runtime-cpu
git diff --check
```

预期exit0；CPU验证器以builtin unittest驱动，无新pytest/wheel安装：将既有cpu-site、repo/src加到独立CPU解释器路径，完整使用审定CustomLinear/repair/parser实际主体，只有非算法的progress/logbook设施可替换。原load_weights等主体保持不变，可AST提取以避免向CPU旧site加入完整节点依赖；结果必须标明是实际函数体CPU fixture，不是全模型/完整节点。输出目录须新建；已有成功结果不为收尾重复运行。

| 验证组 | 必须观察到的结果 |
| --- | --- |
| 身份和图 | 所有角色/节点/环境/tool/policy/profile/source/graph任一变化在POST前拒绝；缺节点、重复源根/错误模型目录拒绝；40/4 sigma数组、实际切片/time步/seed/尺寸/93帧/16fps固定 |
| control/fast比较 | control静态/动态应用计数皆0、原base数值不变；fast才应用认证增量。两个mode profile SHA不同但共同comparison相同的control接受可以放行fast；common任何变化、错误control profile或非法recipe差异均拒绝，不能永久误拒或宽松比较 |
| 真实CPU数学/只读源 | static bias/norm/block/head/patch_embedding、FP8 scalar scale、ordinary rank/alpha/strength、BF16源→FP16和特定FP32目标；原SD/原模型/只读mmap不变，小private overlay无alias；真实dynamic forward坐标/scale/槽对应；所有未消费/覆盖/shape/dtype/NaN/Inf拒绝 |
| 原子性/内存 | factory记录同一时刻最多一个Wan owner；禁止whole-model deepcopy；大shape meta不能越过模型状态检查；低侧预检/应用/释放异常不发布pair，high诊断不成为可用单侧；可用内存/限额不足在加载/POST之前拒绝 |
| reload/offload | 调固定load_weights，静态delta一次后两次reload与meta/offload恢复数值相同不累加；动态buffer重新安装仍对应原payload，scale设备/值正确；重复prepare拒绝，移除从base重建 |
| 原ID故障矩阵 | intent前/后、响应丢失、accepted冲突、执行中、成功未验收、晋升前后、服务重启；未知0重POST，唯一原ID恢复；完成恢复0 producer/0 HTTP；损坏媒体拒绝；parent接受/尾帧/profile变化拒绝 |
| 媒体 | 单个93帧合成fixture技术通过且PTS全量可查；fresh一次完整RGB decode同时做black/末帧数据，完成路径不重做；进程重启的恢复重新验真一次；finite异常在编码之前拒绝，不改源/预算 |
| worker | 普通本地小fixture进程验证owner/Job/端口/超时退出；独立CPU真实注册三个新类并GET所用委托节点schema、记录当前attestation；CPU模式拒绝admit/视频POST，不读取14B/LoRA原payload，不启动GPU |

CPU探测只在新owned run按已获CPU能力探测范围完成；如实施改变了实际安装/下载/采样边界，先形成具体新清单，不能静默扩展。普通tests不跑全库，不重做前项30项CPU payload或历史媒体/GPU矩阵。每个新增保护有独立失败用例，不写仅镜像实现的测试。

## Acceptance

1. 文件/接口可运行，CLI能离线建图/模拟/恢复、独立worker CPU模式能注册当前实验及委托schema，真实HTTP来源与fixture声明严格分开，owned退出有原PID/start和端口证据。
2. 固定的六模型/源码/依赖、原生T5桥接及两套recipe可追溯；全量源分类2959适用+290精确不适用机制可执行，full-model gate在fast POST前强制。CPU小模型不冒充14B，生产未默认采用。
3. 单专家所有权/原子pair、只读来源与私有静态覆盖在真实固定函数体CPU测试通过；重复/移除、reload/offload不污染来源且静态只应用一次；不提升旧helper限制。
4. 原ID/unknown/完成媒体/parent边界的针对性测试和一次必要媒体验真通过，普通生成/恢复不增加重复全库或每帧模型校验。
5. JSON/Markdown报告实际成功、失败、未验证、资源及CPU/GPU证据层次；LVA-07-05未获得新许可时0实际大模型加载/采样。没有真实样本不认领质量/吞吐/1080P收益。

## Risks

完整scaled FP8参数安装/真实Transformer forward、native T5实际加载/编码、Wrapper VAE/图像编码、GPU offload/SDPA以及完整运行峰值均留待LVA-07-05，不用本项机制fixture替代。整数时间步导致baseline不严格等价已作为固定限制，不改上游scheduler伪装对齐。当前主机可用RAM未达到未来26GiB前置，不启动真实加载。任何真实门槛失败保留原ID/证据并停止，不换模型/精度/帧数/路径重试。

方案不含待用户补写的工程参数。独立builder审阅提出的control无LoRA分支和跨mode比较身份两个关键问题，已按原试验意图补齐。依据原任务执行及继续授权，记录实施计划后进行本项CPU/离线实现；完整模型/GPU许可始终另属后续任务，不能由代码实施授权推导。

## Implementation review refinements (2026-11-19)

Final review resolutions in LVA-07-04-review.md preserve the design's outcome contracts: worker POST envelope is exactly prompt/client_id and binds original durable intent, current epoch and one mode slot before enqueue (including /api/prompt); admission binds original client admission ID/profile/epoch. Pair receipt hashes complete role-witness files including trace and original admission ID, and actual transformer missing/img targets are independently rejected.

LVA-07-04-software.json records fixed Comfy Git blobs and a one-time current installed runtime content snapshot. Controller pins bootstrap binary/archive bytes before launch; worker pins native binaries/core source once and actual imported source before execution, retaining mandatory leases and avoiding unrelated pyc. App source/media/verification helpers are included in profile artifacts. No whole-runtime scan is added per video or sampling step.

SaveVideo seals media proof, encoder intent/result and original prompt/profile/graph/client/epoch binding. Collection compares actual bytes to that owned promotion and adopts its full-decode proof without a second decode; process restart clears live proofs and completed validation decodes once. Archived completed history plus promoted media can finish locally with zero HTTP/producer. Tool paths and dimensions come from frozen profile, never a mutable result. Controller success requires actual graceful exit0, closed port and no resource/timeout/crash error. CPU fixtures remain distinct from any full-model result.
