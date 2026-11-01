# VCO-08：LongCat 隔离研究阶段设计

## Goal

在本机 Windows / RTX 5090 D v2 24GB / 32GB RAM 上，先证明新的 LongCat 原生多帧时序协议具有可运行的隔离验证路径，再用真实多窗口输出判断是否值得继续生产接入。用户已对该前置研究明确回复“同意，继续吧”。

**本设计仅冻结当前前置研究；不是整个 VCO-08 的生产实施就绪合同。** 原五项 Acceptance 不变，真实多窗视觉结果、正式16fps接入及最终全库均未完成。后续生产接口/失效与恢复设计必须依据实测再完善，未通过不添加 temporal_extension_v1。

## Scope

包括：固定官方代码/权重清单、原生Windows单进程导入、稠密SDPA适配、CPU只读磁盘映射和逐组GPU加载、最小数值/协议探针、隔离依赖、单个新后端三窗口可行性案例的准备。研究目录中的程序均为可丢弃探针，不进入产品源码。

确切操作目录：`D:/VideoSi/projects/video-ai/vco08-preflight/20261101-1238/`。权重目标目录：`D:/VideoSi/models/vco08-longcat/03b55529b1d1d4045f5fbe14d65c8c6e8116b278/`，与既有模型分开。

不修改原run、生产Comfy节点/环境、产品配置、whole/segmented模式，不继承旧模型视频的观看结论。不更换题材、seed、模型或规格重试失败视频；不运行整份含多种模型调用的官方demo。新依赖只写研究目录的python-deps。

## Approach

### 已选择的路线与备选

用户已同意LongCat前置研究。保留官方原生generate_i2v / generate_vc、13像素历史帧、clean KV缓存和新增部分单独采样。官方torchrun/NCCL启动器不使用；库默认cp_size=1、cp_rank=0，其广播/同步已由cp_size>1分支保护，探针不伪造分布式进程组。

原生全量BF16整模型加载超过显存；VideoX-Fun虽提供卸载，但当前通用LongCat入口固定num_cond_latents=1，不能直接作为13历史帧续写。故采用官方协议加单进程内核/加载适配。MemFlow官方80GB/Linux要求不适合作为本轮本机首选；LongLive适用I2V权重尚未核实，保留备选，未同时试验。

### 固定输入

- 官方代码提交：meituan-longcat/LongCat-Video `6b3f4b8582a8bc3f20f795735f5383716c4ba794`；原始模块保存在upstream，运行副本在working。working的attention.py仅去掉禁用BSA的提前导入；实际attention方法由native_adapter安装稠密SDPA，禁止BSA及多进程分支。
- 官方权重提交：meituan-longcat/LongCat-Video `03b55529b1d1d4045f5fbe14d65c8c6e8116b278`。`model-manifest.json`选择dit/text_encoder/tokenizer/scheduler/vae及LICENSE，共77,577,230,776字节；排除两份LoRA、refinement和无关素材。逐文件大小/LFS SHA或Git blob身份冻结。HF直连超时后使用hf-mirror传输，官方文件页确认同一revision；不随main移动。
- DiT首shard实际header为F32；DiT数据54,324,285,696字节、1022项；文本编码器22,723,641,344字节、242项。元数据/配置/index已取得，六份小文件Git blob核对通过，不能把它们记为完整权重已下载。
- 研究首图采用VCO-07 scene3已接受原选图：路径由`D:/VideoSi/projects/video-ai/runs/20261029-202326-3adf41844095/production/scene-clips/scene_0003_clip_0001/input.json`的source读取，2,004,519字节，SHA256 `d29e1f201a58691c97eb221ff1c5bb5d675c7a0442c436d7fff8b3bb8fb5e94f`。使用原图，不使用第一场景水中站立图或旧失败视频。按官方480p桶计算实际尺寸并记录预处理，不静默继承768×432的生产适配。
- 研究正向提示固定：`The same white egret keeps flying steadily to the right above the same lake, with continuous natural wingbeats. Its white plumage, long neck, yellow beak and dark trailing legs remain consistent. Warm golden light, the same distant tree line, lake reflections and exposure stay steady. The camera tracks the egret smoothly at the same distance.` 来源为已接受scene3飞行动作、主体及晨光事实；不放入审计JSON或重讲起飞阶段。
- 负向提示使用已保存官方continuation demo原文；CFG4.0、Flow官方scheduler、50步、首窗seed42，不加载LoRA，不启用BSA/编译/量化/细化，enhance_hf=False保持基础50步schedule。后续窗口保留同一已编码提示，并恢复父窗保存的Generator状态，沿官方长链单Generator语义推进；不把seed视为抗漂移保证。

### 加载与精度

编排沿项目bootstrap，研究运行器用现有嵌入式Python3.13.14 / Torch2.13.0+cu130；不替换生产Torch。研究隔离包固定diffusers0.35.1、transformers4.57.3、huggingface-hub0.36.0、accelerate1.8.1、loguru0.7.2、ftfy6.2.0；复用现有tokenizers0.22.2，补齐Windows loguru依赖。原官方transformers4.41/tokenizers0.19没有此Python的可用wheel，不编译Rust或覆盖现有环境；版本差异作为实测限制记录。

原始F32权重只读mmap，meta实例化后严格键/shape绑定，不先创建全量CPU参数。每组使用前复制到GPU，用后恢复原CPU映射引用；禁止每次卸载生成新CPU副本。文本编码、DiT、VAE分阶段使用。CPU KV缓存需计入实际资源；小模型通过不能外推实际全量峰值。

真实UMT5准备已发现Windows会保留读过的mapped页工作集，因此卸载时还须用`mapped_residency.py`回收自有只读映射页。仅在VirtualQuery确认CPU参数为MEM_MAPPED、PAGE_READONLY、MEM_COMMIT，连续页范围不跨其他区域后调用VirtualUnlock；处理文档规定的ERROR_NOT_LOCKED=158，私有Tensor/KV跳过，不操作其他进程或全局工作集策略。阻塞H2D已完成后才回收，文件及Tensor地址不变，重读可正常refault。该修复保持原数值和2GiB/4GiB资源阈值；真实文本缓存已独立完成，可复用。

DiT的普通运算权重采用BF16；t_embedder、每个block的adaLN_modulation以及final_layer的adaLN_modulation保持F32，以匹配官方代码显式FP32调制计算；外层BF16 autocast，final_layer.linear仍BF16。原始F32磁盘权重保留，不改写为量化模型。该明确混合精度路径与官方README软件栈有差异，须在真实证据中保留。

稠密SDPA保留原始scale、RoPE、历史/新增attention分离及packed文本分段；未调用BSA、FlashAttention插件或xformers。对照显式softmax(qkᵀ/√d)v及官方小DiT完整条件/缓存路径，分别记录实际误差。

真实CUDA路径仅允许BF16并以sdpa_kernel显式限制为Torch FLASH_ATTENTION / EFFICIENT_ATTENTION，禁止math回退。单独的`full_shape_attention_probe.py`须对CFG batch2、32头、head_dim128、I2V query35880/key37440及续窗query31200/key37440实际执行内核，分别覆盖strided/contiguous布局；任何不支持即停止，不借小shape代证。该核检查不加载预训练权重，tensor allocation上限4GiB、每例60秒。

### 研究时间轴与停止规则

拟冻结一个案例，最多三窗：首窗I2V93帧，续窗各93总帧，其中13帧为历史、80帧为新增；累计93→173→253帧。两条边界位于累计frame93和173。保存未混合RGB/PNG及各窗全部原生输出，只把output[13:]追加到已有链，历史只输出一次。

本探针按官方基础链**15fps**单独记账，253/15秒；不输入旧16fps视频，不执行refinement到30fps，不转码成16fps，不接生产PCM/字幕或冒充原生16fps通过。正式16fps适配仍是后续未决准入项，不因本研究被放宽。

每窗进入模型前排他写intent，绑定首图/父窗、固定模型/软件/提示/预算；完成后保存实际输出/帧映射/资源/终态。已有intent且缺终态为unknown，只核对原进程和产物，不再次调用该窗。每窗最多一次首次生成；OOM、超时、技术失败或明显外观失败立即停止，不自动降规格或换seed。先做首窗静态筛查，无明显问题才允许下一窗；静态筛查只用于提前拒绝，完整动态通过须由真实播放反馈另行给出。

采样成功后先提交latent和Generator状态及sample-complete收据，再单独解码/提交媒体；已成功latent可在原剩余预算内只恢复解码，不重新采样。intent绑定当前父窗result、frames和静态screening的SHA；恢复时重新核对；result再绑定intent及sample-complete收据，沿最多三窗完整核对父链。媒体/数组/JSON均先写自有pending文件并验证后晋升，已有相同mapping复用，禁止覆盖不同或损坏的已提交证据；中断pending保留，不阻止从已成功latent完成提交。

下载前验证剩余空间足以容纳选定77.58GB及至少32GiB余量；不额外制作整套F32/BF16副本。校验已完成文件后复用，partial仅沿同一SHA/大小和严格Content-Range续传。下载GET恢复不等于模型调用重试。运行时不关闭用户应用，不改变桌面准入策略；资源不足停止并保留现场。

具体上限由执行器冻结：下载总壁钟4小时；真实每窗含加载、采样、解码及落盘至多3600秒，案例至多10800秒。每窗启动前可用物理内存至少8GiB、commit余量至少10GiB、空闲显存至少18GiB；运行中可用物理内存低于2GiB、commit余量低于4GiB、空闲显存低于1GiB或进程Torch峰值tensor allocation超过20GiB即停止。磁盘保持至少32GiB余量。外部CPU监督器每2秒检查系统内存/时限，显存每5秒查询，仅终止自己创建的worker；worker在组加载边界也检查预算并恢复CPU映射。检查为合作式资源控制，外部owned-worker终止负责卡住的调用，不声称对GPU内核实时抢占。预计48层BF16历史KV约4.9GB，须纳入CPU/commit实际账目，不能只统计权重。

case-start及window-start的起点持久化并绑定case/software；恢复只使用原壁钟剩余时间，不能通过重启重获3600秒。监督器创建这些记录，直接worker缺少记录时拒绝。

## Files

- `docs/task-designs/VCO-08-entry-audit.md`：历史入口核查。
- `docs/task-designs/VCO-08-design.md`：本研究阶段合同及尚未满足的生产门槛。
- `docs/task-designs/VCO-08-research-results.md`：实际命令、失败与修复、资源/技术/视觉分账，按真实结果维护。
- 研究目录的`resource_probe.py`、`model_manifest.py`、`runtime_shape_probe.py`：资源、固定权重清单和meta API/键映射核对。
- `upstream/`、`working/`、`adapter-sources.json`、`native_adapter.py`：固定源码、明确运行差异和隔离加载/attention适配。
- `tiny_adapter_probe.py`、`tiny_cuda_probe.py`及对应JSON：小型随机张量机制检查，不代表视频验收。
- `download_checkpoints.py`：23项固定GET下载及收据；`checkpoint_backing.py`：严格F32只读映射和零复制meta赋值。
- `prepare_trial.py`、`trial-001/case.json`：确切试验输入、三窗预算和RNG延续规则。
- `runtime_support.py`、`trial_worker.py`：分阶段文本编码、DiT加载、一次模型调用、latent提交/已知解码恢复及技术媒体。
- `research_state.py`、`supervise_window.py`：原子记录、持久化总/单窗时限及仅owned-worker资源监督。
- `mapped_residency.py`：仅在本进程回收只读checkpoint源页驻留；`mapped_residency_probe.py`验证实际RSS下降及原值/文件不变；`prepare_text_context.py`独立验证真实T5并准备本案例缓存，无扩散窗口启动。
- `trial_media.py`：未混合RGB证据、单独有损观看副本、逐帧时基核验和静态提前拒绝联系图。
- `freeze_software.py`、`checkpoint_layout_probe.py`：实际执行代码/版本冻结、完整下载后的真实checkpoint布局与共享alias绑定，结果必须指向同一case/software/模型/下载收据。

## Tests

所有命令先`. ./scripts/bootstrap.ps1`及`Initialize-VideoAiEnvironment <name>`，再用`Invoke-VideoAiNative <python> @('-B', '<script>')`串行执行，检查`$script:VideoAiExitCode`。纯stdlib元数据脚本使用`$VideoAiPython`；数值脚本使用`D:/VideoSi/tools/ComfyUI_windows_portable/python_embeded/python.exe`。

1. `resource_probe.py`：记录Windows GlobalMemoryStatusEx、磁盘及两个元数据transport结果，不下载/加载模型。失败如实记录。
2. `model_manifest.py`：六项小配置/index的大小/Git blob相符；index引用闭合、精确字节总量、受限Range读取首shard header，保存F32依据。
3. `runtime_shape_probe.py`：所有大模型只在meta构造，索引键/参数总量匹配，唯一缺项只允许已证明的真实共享embedding别名；原图官方桶尺寸明确。
4. `tiny_adapter_probe.py`：未适配attention实际拒绝；SDPA与显式eager、四历史latent的clean KV与完整条件路径相符；更早历史变化影响新增输出；BSA拒绝。
5. `tiny_cuda_probe.py`：逐组加载/卸载与常驻同权重计算相符，CPU原始引用恢复，异常路径恢复；记录F32/BF16误差及峰值，小探针限制256MiB tensor allocation。F32比较rtol1e-5/atol1e-6；BF16驻留/卸载rtol0.01/atol0.005，历史cache/full比较rtol0.03/atol0.025，不宣称位级相同。
6. 真实调用前须另有mmap/alias严格加载、runner未调用模型的导入/预算检查和完整下载收据；未满足不调用。产品代码未改变时不重复VCO-07已通过定向批次；最终全库仍未完成，不能以本研究小探针代替。

7. `tiny_backing_probe.py`验证F32只读mmap严格赋值、GPU计算后恢复同一映射data_ptr、原文件SHA不变，缺key/错shape/重复tensor拒绝；`full_shape_attention_probe.py`按上述实际规模执行高效内核，不允许math后端。

8. `tiny_text_staging_probe.py`核对UMT5共享embedding、卸载数值和预算prehook拒绝；`media_io_probe.py`核对合成像素的lossless/viewing15fps格式；`recovery_fault_probe.py`注入电影pending中断、数组/JSON重放与漂移、单窗预算过期和父结果/sample收据漂移，均不得触发真实扩散。`trial_worker.py --check`只报告结构准入状态；不能将下载未完成的结构检查当完整调用前通过。

## Acceptance

本研究阶段分项交付：固定可追溯输入；本机资源/加载/协议检查；最多一次三窗案例的真实结果或明确停止证据；真实技术和完整动态观察分开。任何一项失败保留准确失败结果；不能把完成研究报告等同于整个VCO-08完成。

原VCO-08结项仍需：真实条件协议身份、完整历史/新增分账与时基、真实多窗长链五类连续性观察、窗口失败/unknown/漂移恢复和模式失效、实验/生产准入分离，以及项目最终全库的真实结果。当前生产接入接口、16fps路径和长链/多题材适用范围未就绪，必须依据研究结果完善，不预造通过。

## Risks

77.58GB传输时间和实际全模型资源未实测；mmap并不消除磁盘吞吐成本。Python/Torch/Transformers与官方栈不同，SDPA和混合精度存在数值差异。15fps研究结果不能直接成为16fps生产资格；三窗口短探针也不证明任意长链稳定。原图在不同模型桶下的预处理不同，不能作单变量优越性归因。未取得完整真实播放反馈时视觉验收保持unverified。
