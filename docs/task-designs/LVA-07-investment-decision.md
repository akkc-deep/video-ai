# Current decision — 2026-11-19

**worth_isolated_attempt，仅限LVA-07-04有界CPU/离线实现。** 固定环境及9+4个实际HTTP schema通过，两owned进程已结束。原生CLIPLoader/CLIPTextEncode/现有Bridge解决scaled_fp8 T5直接loader不兼容；不换模型。单专家私有静态覆盖与固定sigma/资源方案见LVA-07-04-design.md/contract.json。GPU/14B应用及质量未验证、未授权。以下保留历史决策快照，不再作为当前状态。

# LVA-07-03 投入决策与环境/GPU资源清单

2026-11-18 原始决定为 **`insufficient_evidence`**。2026-11-19 用户同意补齐环境与资源方案；[补充方案](LVA-07-03-preparation-plan.md)和[结构化证据](LVA-07-03-preparation-evidence.json)现已固定完整源码获取、独立 CUDA runtime 副本、15 个新增 wheel 与具体命令。环境准备可据该清单单独审阅授权，尚未执行。完整模型原子所有权/内存及真实 sampler 静态增量衔接仍未解决，完整投入决定保持 **`insufficient_evidence`**，LVA-07-04 仍不准备为 READY。原始 merged 的遗漏保留，不能借安装环境绕过。

机器可读交付为 [environment manifest](LVA-07-environment-manifest.json)，决定、身份、预算、未知项和动作以其中的同名字段对应。当前任务的验收允许交付“证据不足”；LVA-07-04 需要继续决定和具体授权，因此保留 `NOT_STARTED`、Design document=`None`、Handoff=`None`，不创建部分后继交接。

**最新执行补充（2026-11-19）：** 用户对具体环境清单另行回复“同意”，sources/runtime/wheels/install四阶段已完成，详见 [执行结果](LVA-07-03-preparation-execution.md)。完整244文件修复快照、独立45784文件CUDA runtime副本、15个固定wheel及102个实际分发齐备，pip check exit0。解释器路径隔离通过；实际节点注册、完整模型和GPU仍未验证。下文尚未执行/授权的描述属于此前决策/提案快照；现有环境前置不再未知，但U3～U6及实际导入门槛仍保留，不因此把LVA-07-04或完整投入决定改成已通过。

## 2026-11-18 基线证据与条件矩阵

证据按任务设计顺序读取；大 JSON 只投影直接消费的状态、身份、计数、依赖和限制，未重复输出逐 tensor 大台账。manifest 的 `evidence` 记录 19 个小型文档/结构化证据与工作流文件的 SHA256；模型完整 SHA 沿用历史准入，另记录本次有界 header/stat 观察。

| 条件 | 已验证行为与层次 | 来源 | 未验证边界及解除条件 |
| --- | --- | --- | --- |
| mixed delta / 映射 | High1500、Low1459 个适用原始输入经真实 normalizer/mapper/parser 最终保留，并在 CPU 目标 fixture 应用；30/30 测试。High 包含41个 modulation，Low 原始1749中精确290项不适用 | [CPU最终结果](LVA-07-02-results.json)、[原始payload结果](LVA-07-02-applicability-results.md) | AST 函数/类主体及受限普通 LoRA 注册表，尚无完整节点注册或真实 Wan forward；需 U4、U6 的实际模型门槛 |
| unmerged / static | 小模型动态矩阵和静态 bias/norm/block/head modulation、strength/alpha/rank、重复拒绝/移除及私有 pair 异常原子性有 CPU 证据 | [修复设计](LVA-07-02-fix-design.md)、[payload JSON](LVA-07-02-applicability-results.json) | 每侧256 MiB的小模型 pair 接口不能直接 deepcopy 14B；需 U3 的新所有权/预算方案及实际两侧安装证据 |
| merged | 原始 `utils.apply_lora` 已执行；block/head 预期1.125、实际1.0，遗漏确立 | payload JSON 的 `merged_diagnosis` | 本项不选 merged。不能把“有合并分支”或改开关当作已修复 |
| FP8 / scale | 原始基模 header 为 E4M3 矩阵、F16 静态参数及 scale_weight/scale_input；scalar-scale CPU fixture 的顺序通过 | [环境审查](LVA-07-environment-review.md)、payload结果 | 完整 scaled-FP8加载/实际scale/forward未知。拟禁用fast FP8；compute dtype仍为null，不能从CPU FP32/float64外推，需 U4 |
| low_mem_load / offload | 源码显示路径存在；unmerged buffer可能随swap迁移；无完整路径运行证明 | 环境审查、[后端设计](LVA-07-wrapper-backend-design.md) | 拟 low_mem_load=false、CPU offload、GPU串行、不双专家常驻；swap/prefetch数未定，需 U3/U4。关闭 low_mem_load 不等于 offload 已验证 |
| 完整源码 / 节点依赖 | 固定上游a743；修复版本15ad为18份上游文本加3份修复/策略文件，共21文件部分副本 | CPU最终结果、[补丁清单](../../patches/wanvideo-wrapper/manifest.json) | 没有已审定完整checkout。Main/Sampler/ModelLoading/Utility/Cache必需导入未验证；需 U1/U2。CPU最小闭包不代替完整注册 |
| 双专家真实应用 | 2959项是CPU fixture应用，290独立不适用；完整模型 `verified=false` | payload结果、[精确CPU策略](../../patches/wanvideo-wrapper/lva07_img_policy.json) | 构造实际双专家后重新核对身份/schema、parser保留、静态安装、动态forward/scale消费与异常不发布，不能只数patch或看无告警；需 U3/U4/U6 |
| 硬件 / 内存 | 本次只查主机RAM/磁盘；历史GPU为RTX5090 D v2、24455 MiB | manifest.resources、[LVA-04结果](LVA-04-results.md) | 模型存储已经使双专家显存常驻不可直接假设；原模型+私有深复制代理下界高于物理RAM。无可信完整运行峰值，不能建议投入，需 U3 |
| 质量 / 可比性 | 历史原生低运动40步、CFG3.5、Euler/simple、high15/low25，93帧768×432/16fps已接受；LVA-04热P50为470.598s | [LVA-01 GPU结果](LVA-01-gpu-results.md)、LVA-04结果 | Wrapper无采样/技术/人工质量结果。原生与Wrapper scheduler/sigma未对齐，不宣称纯后端收益，需 U5。历史样本与授权均不授权新GPU |

前项状态无冲突：07-01的原始候选停止结论保留；07-02修复了限定CPU路径，未升级为完整环境可运行。merged受限不推出所有Wrapper配置受限，也不能因CPU成功删掉完整模型门槛。

## 固定环境、模型与拟用配置

上游 Wrapper：`a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`。本地修复：`15ad15c292831865886b4fa9a2316188b0820035`，位于 `E:/VideoAI/scratch/benchmarks/LVA-07-02-applicability/replay-wrapper`。补丁 SHA256：`9a3e8c090fddea78866b6bd516e59891380aa8a34c335e7294568e92dbfc31d2`。本次检查补丁清单中4个小型产物摘要一致；未制作完整checkout或激活生产节点。

Comfy固定参考commit为 `2c75dc1b379a59e0880619d029607af5169a62ef` / 0.44.0。拟用独立CUDA环境参考 Windows AMD64、Python3.13.14、cp313-cp313-win_amd64、torch2.14.1+cu130、CUDA13.0；这些是2026-11-17读取的生产参考元数据，并非已建立的独立环境。独立runtime路径和完整二进制库存为null。已执行CPU证据环境为torch2.14.1+cpu、CUDA=null，不能替代CUDA环境。

历史参考环境缺 accelerate、diffusers、peft、ftfy、gguf、pyloudnorm、protobuf、opencv-python 八项必需分发。manifest保留索引候选元数据，全部 `install_selected=false`；没有将最新索引版本拼成安装锁。已有CPU32-wheel锁仅证明CPU闭包。完整CUDA闭包、精确wheel URL/tag/SHA/字节/依赖影响尚未确定，所以没有可批准安装命令。不新增Triton、SageAttention或xformers，拟采用SDPA、不开compile；这仍需要完整导入验证。

| 角色 | 优先复用文件（均在 `E:/VideoAI/shared/models/comfyui/`） | 字节数 | 完整SHA256（历史准入） |
| --- | --- | ---: | --- |
| high base | diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors | 14294742832 | `6122e79d55e0f235698d11d657f3b196c5273c830da00b2b013c5a048d5e6a42` |
| low base | diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors | 14294742832 | `5471a457b6ac404202a5fbe6c11595a3d5641fc766b00f38763f72303fffc21e` |
| T5 | text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors | 6735906897 | `c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68` |
| VAE | vae/wan_2.1_vae.safetensors | 253815318 | `2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b` |
| high LoRA | loras/wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors | 634645944 | `887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19` |
| low LoRA | loras/wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors | 739472104 | `8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1` |

模型身份来源为 [LVA-04 manifest](LVA-04-gpu-manifest.json) 的 `assets.fast_experimental`。LoRA来源revision为 `57adea585d1d21085e2dfc91ce3c7b646cdd9345`。本次六文件只读stat和有界header（每文件上限2MiB），全部大小匹配；manifest分别保存新观察的header SHA。两个base header仍与07-01记录的 `a904e26816259491a0bc1abf5446a8ba86deae8ff597539619280de3f456fcbb` 一致；相同header不代表相同payload，也未重复完整模型SHA。

拟用 profile：merge=false、非fast FP8、保留原scale、SDPA、compile=false、low_mem_load=false、CPU offload、GPU并发1、禁止假设双专家显存常驻，LoRA strength两侧均1。compute dtype、swap_blocks、prefetch_blocks为null，见U3/U4；所有非空值均是拟用约束而非完整运行通过项。

精确290策略SHA为 `9dbc2f5536bab2057147d0ebebc3af7f8a3db1a3c060f8bc41af6a4185dc2587`，仅批准固定CPU profile；原关闭提案继续保留。实际模型重新核对后才能适用；不得通用过滤img或将290计入消费/应用。W3重打包模型没有已选身份、字节或命令；BF16替代也未选择，已有header审查显示同样缺失Low290，不能以此为由自动换模型或下载。

## 资源预算与不可外推项

本次主机容量观察时间：`2026-11-18T12:36:41.228332+00:00`。方法为stdlib `GlobalMemoryStatusEx` / `shutil.disk_usage`，未查询本轮空闲VRAM或创建CUDA context。GiB=2³⁰字节，MiB=2²⁰字节。

| 项目 | 字节/值 | 含义 |
| --- | ---: | --- |
| 已有六模型复用 | 36953325927 | 约34.42GiB，原文件只读复用；不等于新增磁盘 |
| 其中双base | 28589485664 | 约26.63GiB，未证明能同时驻留GPU |
| 其中双LoRA | 1374118048 | 已有文件，无本项下载 |
| 拟新增模型下载 | 0 | 当前优先复用路径；若原base加载失败，重新决策W3，不能自动追加 |
| 完整源码/依赖下载 | null | 未锁定完整CUDA闭包与源码payload大小；不当作0 |
| 新副本 / 临时空间 / 磁盘预留 | null / null / null | 独立runtime库存、原子模型所有权与输出保留方案未定 |
| RAM预计峰值 / VRAM预计峰值 | null / null | 缺少完整模型准入、scale临时buffer、offload/激活测量，禁止填写猜测总峰值 |
| 本次物理RAM / 当时可用 | 33346146304 / 17494945792 | 约31.06 / 16.29GiB，瞬时容量，不是资源预留 |
| E盘当时空闲 | 1421776736256 | 不是本轮已分配空间，不能代替未知安装/临时预算 |
| 历史GPU总显存 | 24455MiB | 2026-11-17观察，约23.88GiB；本轮空闲值null |
| 历史原生cold设备采样峰值 | 22034MiB | LVA-04设备级样本，非Wrapper独占峰值 |
| 原模型+私有deepcopy的base文件大小代理下界 | 57178971328 | 约53.25GiB，已经超过物理RAM；尚不含对象/LoRA/T5/激活，不是推荐分配方案 |
| 双base全参数BF16展开分析下界 | 57155604736 | 由实际header形状推算，排除scale标量，不是替代模型下载字节或实测峰值 |
| 两份93帧原生RGB数据 | 185131008 | 仅 `2×93×768×432×3`，不含PNG/codec/latent/1080P及临时副本，不能充当临时空间总预算 |

CPU payload历史峰值工作集1899302912 bytes（1.77GiB）来自分块零基底fixture，不能线性外推14B。磁盘充足并不解决RAM/VRAM或异常原子性。下一方案必须避免现有小模型整对deepcopy：预检两侧后顺序构建独立私有模型、明确同一时刻的权重/LoRA/cast/激活存量与offload上限、两侧成功后原子发布，失败丢弃未发布对象。这里只给约束；尚无完成的实现/预算，故资源总额仍null、结论仍证据不足。

## 完整模型准入门槛

manifest中固定 `enabled=true`、`before_fast_post=true`、`verified=false`。未来在独立worker按实际配置构造两专家，重新核对完整环境、模型/LoRA身份和schema；证明真实parser最终保留原始payload对象、静态bias/norm/block/head安装，以及实际动态矩阵forward/scale消费。精确290独立对账，其他任何未知key、覆盖、shape/dtype冲突、非有限、别名或不支持配置均拒绝整个pair。

必须验证低侧异常时原模型/patch未污染、不发布可用单侧；不能将256MiB/侧CPU deepcopy函数直接用于14B，也不能抬高上限假装解决。静态增量只能安装一次；重复/移除从不可变原始权重恢复，不在量化结果上反向相减。门槛在准入边界一次执行并落盘，同一受保护事务复用，不加到每个采样步或每帧；恢复时重建身份与证明。失败不发fast POST、不fallback、不重发未知请求。

## 最小GPU计划（未执行、未授权）

最大 **2个采样视频**，GPU单请求串行。低运动输入沿用LVA-01：图片SHA `0e3305d2d725c874d23c25c3271d027a342751832a2a8e301a0b2c7057ee6001`、prompt SHA `c779146f46af38ceabf88349a0e3e5f65334d6e0b785c8fd60f480ce78fad54e`、seed `264244520398999`、low seed=0、768×432、16fps、生成/保留93帧。源request和negative prompt摘要见manifest；不重复扫描旧媒体或打印prompt原文。原生workflow模板默认640×640/81帧，未来必须以fixture覆盖，不能直接拿模板默认值执行。

1. W1：同一已有base、无LoRA，40步、CFG3.5、Euler/simple、shift5、high15/low25。独立环境与资源门槛建立并获得具体GPU授权后，最多运行1份；参数无法对齐、技术或人工质量失败即停。
2. W2：仅在W1技术检查及真实人工质量接受、实际完整pair准入通过后运行1份；同输入和base，4步、CFG1、Euler、shift5、high2/low2，目标sigma `[1,15/16,5/6,5/8,0]`。实际Wrapper sigma/timesteps/模型调用数必须记录，不能用UI数字代替。任何失败保留原ID，不自动重试、换base或扩展矩阵。

Wrapper control实际sigma与原生simple的等价性尚未验证；不能把切换base/精度/scheduler的差异归因纯后端。1份样本不报告P50/P95或稳定倍数。人工检查主体/结构、动作、纹理、闪烁、颜色、尾帧，技术验收不代替观看。

计时按“选中图片交接完成、准入/准备前”起算；只有实际执行到1080P交付检查完成才报告该端到端边界。native单列提交前至收集/必要技术检查完成；加载、两专家、VAE、编码、一次必要全解码、超分和合成按实际发生层级记录，未执行层级明确缺失。人工等待单列，不能相减当GPU时间。冷1热3、高运动、父子链属于后续LVA-07-06获准扩展，不能为填表重做既有样本。

## 动作清单与解除条件

所有动作均列于manifest.actions。2026-11-19 的 A1/A2/A2W/A2I 已更新为具体提案，分别对应补充命令的 sources/runtime/wheels/install；尚未授权或执行。下载 payload 共 387087549 bytes，runtime 副本 4157540147 bytes，wheel 解压 455252138 bytes，含临时量的保守磁盘预算 6214544814 bytes，计划预留 8 GiB。以下 A0 保持可只读运行：

```powershell
& .tools/python/python.exe -I -c "import json,pathlib; m=json.loads(pathlib.Path('docs/task-designs/LVA-07-environment-manifest.json').read_text(encoding='utf-8')); print(m['decision']); print(m['resources']['existing_model_reuse_bytes']); print([(u['id'],u['reason']) for u in m['unresolved']])"
```

以下表格保留 **2026-11-18 历史快照**；不能用其中的 null 覆盖上述已完成的环境准备提案。

| 动作 | 2026-11-18 命令 | 当时解除条件 |
| --- | --- | --- |
| A1 完整源码及修复集成 | null，executable=false | U1/U2：完整固定commit清单、补丁整合身份、具体独立目录/来源和payload预算 |
| A2 独立CUDA runtime及依赖 | null，executable=false | U2：精确wheel锁及依赖影响、隔离二进制库存、下载/副本/临时字节和资源限额 |
| A3 worker/workflow/恢复及准入harness | null，executable=false | U1～U6：实现就绪的LVA-07-04设计及继续决定，特别是受限原子内存方案 |
| A4 owned服务注册/object_info | null，executable=false | U1/U2/U3/U5：完整节点环境、固定图、持久化服务端口/PID/start身份与退出方案 |
| A5 实际准入及最多两样本 | null，executable=false | U1～U6全部解除并有具体GPU授权；先control人工接受再fast |

原 A1～A5 当时均无审批就绪命令。当前仅环境获取/复制/离线安装提案已具体化；A3 后端实现、A4 owned 服务/object_info 和 A5 完整准入/采样仍未就绪。元数据根闭包97分发及其余已安装依赖均无约束冲突，不代替实际导入；87个已有版本保持、补15个，预计102分发。完整双专家预算未知值仍为null，不请求批准未知 GPU 投入。详细命令、来源身份、读写范围和剩余 U1～U6 见补充方案。

## 2026-11-18 验证与操作边界

本项只检查JSON解析/固定字段契约、MD/JSON一致、证据摘要、当前有界header/stat和改动范围以及 `git diff --check`。不跑产品测试、不重跑30项CPU/payload、不做媒体解码、全模型哈希或历史benchmark。完成时实际命令/结果记入任务板。

本项0安装、0依赖/模型下载、0 GPU torch/完整节点导入、0服务启动、0生成POST、0 GPU采样、0完整模型payload读取/全量重哈希。只新增本决策和manifest、更新当前任务板；原生workflow、即梦协议、模型、旧run和暂停生产保持原状。历史CPU安装及LVA-04/06授权不外推。

## 2026-11-19 补充结果与操作边界

完整 Git tree 241 文件/47250651 bytes，Comfy 固定 commit 的1332个文件/49602446 bytes；runtime 45784文件/4157540147 bytes，其中381个二进制完成只读SHA256，共3354508172 bytes。15个新增wheel的固定URL/tag/bytes/SHA及依赖影响已记录；成功的ZIP目录读取为30个HTTP206/227053 bytes，解压量455252138 bytes。没有重复大模型哈希或CPU数值测试。

首版取证脚本尾部范围过宽，对五个小wheel的计划请求可能覆盖完整文件（合计上限112970 bytes）；失败批次未持久化逐请求回执，不虚报精确次数。响应未保存、安装或执行，后续已收紧为EOCD/central-directory元数据；另修正ZIP字段下标与atime检查。不能把本轮笼统表述为“从未读取wheel payload”。实际完整源码获取、runtime复制、wheel文件落盘、安装、节点/GPU torch导入、服务、视频POST、GPU采样、模型payload/全量模型哈希均为0；环境目标目录不存在。具体源码和计数在补充证据中独立于昨日历史记录。

本轮不回滚已完成的 LVA-07-03，不开始 LVA-07-04，不写部分交接。后续先按具体环境清单授权执行，再根据真实节点与受限模型方案证据继续；CPU helper 六个所有者的 base 文件代理下界85768456992 bytes，及 sampler reload 可能覆盖静态增量的接口问题均已明确记录。
