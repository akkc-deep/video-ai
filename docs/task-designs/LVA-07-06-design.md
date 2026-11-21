# LVA-07-06 条件扩展矩阵与实验结论设计

## Goal

完成 Wrapper control/fast 的低运动、高运动、新父片和子片冷1热3实验，给出质量接受后的性能、恢复和研究建议。保留原生质量默认，不恢复生产、不自动推广。

2026-11-20 用户明确要求“完成任务LVA-07-06”，随后对本文及最多32样本/约10–12小时的具体方案回复“同意”，批准按本文实施。实施计划为 `docs/task-designs/LVA-07-06-plan.md`；批准不替代后续真实视频的人工质量接受。任务板为唯一状态来源。

## Scope

- 直接输入：`LVA-07-05-completion.json`、`LVA-07-04-results.json/.md`、`LVA-01-gpu-results.json/.md`、`LVA-01-gpu-experiments.json`，以及 `LVA-07-wrapper-backend-design.md` 全文。05两份真实媒体和人工接受已经成立。
- 扩展实验harness，保留05的v1两样本协议；支持固定四类fixture、两mode、冷1热3、真实采样、父片接受、原ID恢复、逐trial证据与统计。
- 使用既有独立runtime和六模型，不安装、下载、换模型或修改固定Wrapper/repair/policy。保留05的head/text/VAE/offload/RGB修复及18GiB提交额度。
- 全部质量通过时，使用既有RealESRGAN全保留帧超分、原音轨/字幕及1080P技术/人工验收，单列与native边界。未执行1080P不能宣称端到端加速。
- 不修改即梦模块、原生workflow、生产配置、旧实验intent/ID/审核/媒体/锁，不清理其他进程，不将历史测试结果登记为本任务新结果。

## Approach

### 方案与实施边界

推荐在现有Wrapper实验模块增加**显式v2矩阵协议**，共用已经验证的数值与恢复实现；v1根和授权语义保持。另建一套模型加载器会重复05的兼容修复；直接循环旧CLI会反复读同一 `control_1`/`fast_1`、固定错误seed/帧数，并触发两样本保护，因此不采用。这是用户本次“同意”已批准的实施方案。

先批准本文，再写实施计划和有界离线失败测试；离线实现与审查通过后封存新matrix及确切profile/source/graph摘要，再开始真实推理。授权记录引用真实用户请求及对本文的批准，不能借用05的 `max_samples=2` 许可，也不能伪造已批准字段。新增设计本身不启动实验。

### 既有样本复用决定

05 root为 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-06`；comparison `c7696ad7f8b484b4f84ca874bc12a3fd7c9be3108ed31e2889374d7ca3dff08d`。

| 05样本 | 原prompt ID | 已接受媒体SHA256 | 用途 |
| --- | --- | --- | --- |
| control | 11ebef23-82f0-40a4-916d-104f026993ea | 8ec6419f88729213893300402e5a4e1edc556cbf98f05ed7679f677e8370dd50 | 兼容、质量及单样本历史计时 |
| fast | 1dafecde-bd7a-493d-8c39-7bc1bfb4e4ae | d91f6677739b3fd6672744297e6fa1befd6345a4dfade185d9704c1bd261e8f5 | 双专家实际应用、质量及单样本历史计时 |

原服务已exit0/端口关闭，pair不再可用。fast在control之后，不能标为fresh-process cold；两份都无法接续同epoch热3。v2还需新增trial/frame/seed合同，profile源身份不同。因此复用这些结果作门槛和历史证据，不重新解码/哈希大模型，不把它们充作v2连续矩阵。**新低运动组是独立的冷/热测量，不覆盖或重发05请求**。需要的32份是上限，不为缺表项额外重做；已完成v2样本一律恢复/复用。

### 固定环境、资源与预算

- 仓库：`E:/code/py/video-ai`；controller Python：`E:/VideoAI/shared/envs/video-ai/Scripts/python.exe`。
- 独立环境：`E:/VideoAI/scratch/benchmarks/LVA-07-04-environment`；worker Python为其中 `python_embeded/python.exe`，Comfy为其中 `ComfyUI`。
- Comfy commit `2c75dc1b379a59e0880619d029607af5169a62ef`；Wrapper upstream `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`、repair `15ad15c292831865886b4fa9a2316188b0820035`；完整修复树manifest SHA `f498198315ae6acac11f08fd44f6764ef2a9ba32548237308f18edc0b38ec312`，不能将它说成Git commit。
- Python3.13.14 / torch2.14.1+cu130 / CUDA13.0；实际已安装依赖及二进制身份沿用 `LVA-07-04-software.json` 与环境sources/runtime/wheels/install标记，不升级。实际启动须复用已有受保护源清单机制。
- 单GPU、单owned进程，Wan与超分串行。端口8297仅用于Wrapper，8189仅用于既有超分owned服务；被占用时停止并报告，不接管、不终止他人服务。
- 启动available RAM至少14GiB、free VRAM至少21GiB、available commit至少26GiB；phase RAM4GiB/VRAM20GiB。Job private commit18GiB、RSS停止阈值24GiB、torch allocator20GiB。CPU探针保持4GiB/180秒。沿用05不限服务总时长选择；不自动抬高资源预算。每次新owner启动前重新只读观察容量。
- 最多8个Wrapper服务组，每组4视频，共32视频；每服务prepare-text/image一次、完整pair一次；准入POST/视频POST分别统计。最多2848保留帧超分、24份1080P成片。原生生成总2880帧，全部保留原始生成媒体；只对子片依原预算裁去4帧。
- 原六模型零复制，合计约34.42GiB；身份沿用下表。新增实验磁盘预留32GiB，启动前核对E盘可用；不足停止，不删旧run。
- 05单样本执行1255.786s/96.539s、准入约38分钟，只能作资源排程参考。按8次准入及32个视频粗估约10–12小时计算，另加超分、启动及人工等待；不是承诺或实测。审核期间保留当组服务以维持热样本；若需要退出，保留缺项，不自动新开组补表。

原模型根 `E:/VideoAI/shared/models/comfyui`：

| 角色 / 相对文件 | 字节 | SHA256 |
| --- | ---: | --- |
| diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors | 14294742832 | 6122e79d55e0f235698d11d657f3b196c5273c830da00b2b013c5a048d5e6a42 |
| diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors | 14294742832 | 5471a457b6ac404202a5fbe6c11595a3d5641fc766b00f38763f72303fffc21e |
| text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors | 6735906897 | c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68 |
| vae/wan_2.1_vae.safetensors | 253815318 | 2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b |
| loras/wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors | 634645944 | 887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19 |
| loras/wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors | 739472104 | 8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1 |

### fixture与profile合同

只读原fixture、`frozen/original-request.json`、冻结图及原input；提示词原文不进入汇总报告。以原文件实际摘要和schema核对下表，禁止从媒体文件名或prompt推测fixture。输入SHA是适配后的实际生成图片，不混同selected-image SHA。

| matrix fixture | 原root下的fixture | 生成输入SHA / 政策 | seed high / low | 生成/保留帧 |
| --- | --- | --- | --- | --- |
| low | LVA-01-gpu-low-20261115-01/fixture.json | 57ca0f059560e5582888e3f7e0080a3d6b04ab5d47df246c572f738c125d7df2 | 264244520398999 / 0 | 93/93 |
| high | LVA-01-gpu-high-20261115-01/fixture.json | 422738d468f77c0022439db2a13892f12ad7b556300e69437b277dc54f233a33 | 264244520399048 / 0 | 93/93 |
| parent | LVA-01-gpu-parent-20261115-01/fixture.json | 317e2605d1c529d6ed50e166cd77adc13f8c478f86e31989e786d55383c281f3 | 264244520399004 / 0 | 93/93 |
| child | LVA-01-gpu-parent-20261115-01/child-fixture.json | 对应mode新parent冷样本被接受后的真实保留末帧 | 264244520399005 / 0 | 81/77 |

上述root均位于 `E:/VideoAI/scratch/benchmarks`。child保留生成帧索引[1,78)，即丢首1/尾3，真实尾帧取保留索引76（生成索引77）；PTS重新从0开始、16fps。保留81帧原视频及77帧retained视频，不插帧、变速或降低尺寸。父子成片93+77=170帧/10.625s。

v1 `WrapperProfile.from_dict`、seed264244520398999、93帧和两样本auth原样保留。v2 profile明示 `schema_version=2`，共同settings保留数值配置，但将seed/length绑定到 `fixture_contracts` 的上述四项，而不再把93写成全部fixture的固定值。两mode各一个不可变profile，parent与child使用**完全相同的对应mode profile SHA**；fixture、group/comparison及graph SHA另行绑定，不把不同输入冒充同一比较组。除mode/recipe外两profile共同身份一致。

v2 profile固定四种预算、seed、source fixture摘要和prompt摘要；具体child输入/parent接受摘要在子组封存时加入fixture。文本长度从各fixture的原T5 tokenizer按原编码方式在CPU离线读取确定，封存positive/negative预期token数（保留至少512的padding语义，完整上下文，不截断）。去除664/512作为所有场景的全局固定值；仅对v2使用该fixture预期长度，v1仍严格检查664/512。实际编码输出必须精确匹配各自封存值和float32/4096维/finite，T5释放后才准备VAE。

图像条件latent长度 `(generated_frames-1)//4+1`，93对应24、81对应21；shape分别[16,24,54,96]/[16,21,54,96]。VAE fp32、无tiling、768×432/16fps及原head/offload数学保持。control40步CFG3.5/split15，fast4步CFG1/split2/两LoRA强度1；sigma和integer timestep合同引用04原值，不重算不同配方。实际前向分别30/50、2/2，原2959适用输入/290精确排除规则不变。

### matrix、服务与trial身份

新顶层root建议 `E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01`，存在则拒绝覆盖。子组固定 `groups/{low,high,parent,child}-{control,fast}`；每个子组一个fresh-owned服务及一个mode，只接受 `cold_1,warm_1,warm_2,warm_3` 四个trial。执行顺序low-control→low-fast→high-control→high-fast→parent-control→parent-fast→child-control→child-fast，单组结束后关闭其owner，再进入下一组。

每组prepare、pair完成后首个视频为process-cold（首次视频，**已包含准入预热**），后三个在相同epoch为warm。启动/prepare/pair另记group setup，cold完整包络必须包含这些阶段；冷视频执行时间单列为admission-prewarmed first trial。不能声称磁盘冷、所有模型首次装载冷或无准入成本。fast独立fresh服务，避免沿用05的control后缓存边界作冷对照。

每个trial唯一graph，仅输出前缀 `lva07/{mode}/{trial}` 与受控trial token不同，其余固定。token同时进入实验Prepare/Sampler节点的输入和证据键，使相同seed的热请求真实执行，不允许Comfy缓存直接返回完成图；文本/图像仍复用同epoch准备缓存，逐trial复制可变conditioning。不能通过变seed或注入不同采样参数失效缓存。node-evidence改为按trial/role保存，stage-metrics每行含trial/mode/epoch，不能覆盖旧证据。新字段同步实际HTTP schema与其独立v2合同，v1 schema与旧根恢复保留。

matrix冻结 `matrix.json` 和 `frozen/manifest.json`：task、schema、ordered groups、每组trial清单/fixture、两profile摘要、固定源/模型/工具摘要、资源/生成上限、输入交接UTC与monotonic时间、逐组条件。`matrix_sha256`不包含未来输出/审核或其自身；`state.json`为可更新进度索引，不替代不可变intent/accepted/history/technical/review/exit回执。

### 授权与审核门槛

v2授权必须为 `task_id=LVA-07-06`、真实 `user_evidence`、`approved=true`、确切matrix SHA、group allowlist及每组最多4、总视频最多32、最多2848超分帧/24成片、`max_service_seconds=null`。group worker只接受自己的mode/profile/fixture/matrix身份；v1仍只接受05两样本。不能只放宽 `max_samples` 或把05 auth复制改task ID。

fresh POST前，controller与worker均核对sealed allowlist。每组每trial一次持久化claim，原ID重复调用进入GET恢复；分配新UUID不绕过32上限。prepare/admit各每epoch一次独立intent，双侧完整pair同epoch通过才能发视频。control无LoRA，fast的pair还须消费正确control审核：low/high/parent分别绑定对应control组已完成且已接受的cold_1；不是旧05审核。control warm、fast warm仍各需技术检查和真实质量结论才能计入接受样本。

child-control以新parent-control/cold_1真实末帧为固定输入；child-fast以新parent-fast/cold_1为固定输入。各child组四次均沿用同一被接受的对应父片，保持fixture固定；不是四组独立父子故事，不宣称所有parent重复都被消费。父片接受记录必须包含matrix、mode profile、parent root/trial/prompt、generated/retained/last-frame SHA及真实人工原文；子组封存和POST前核对该绑定。旧native父片、另一个mode父片或初始图片不能使用。

child-fast的control质量门槛引用已接受child-control；同时显式记录control/fast父片输入可能不同，所以父子速度/画质是整条配方链对照，不是相同图片的单因素LoRA实验。子片生成前必须先取得本mode父片的真实接受。父片组服务关闭且原档案足够，才允许其子组开始。

每份输出先技术检查后提供实际媒体给用户审核。审核采用 `review --decision accepted|rejected --evidence <真实用户原文>`，保存prompt/media/profile/fixture/graph/epoch、作用域及时间；工具不能凭技术通过、相同seed、字节一致或其他视频接受自动填写。用户明确同意同字节关联时才可为列出的其他trial绑定相同接受，不声称独立观看。拒绝即停止矩阵；后续NOT_RUN，报告质量失败，不换seed重做。

### 建议CLI与恢复接口

新增 `scripts/benchmark_wan_wrapper_matrix.py`，下列为**待实现接口，不是已经可运行的命令**。统一使用controller Python、`-X utf8`，`--root`均为上述新matrix根：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper_matrix.py init --root E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper_matrix.py start-group --root E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01 --group low-control --authorization E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01/authorization.json
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper_matrix.py prepare --root E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01 --group low-control
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper_matrix.py run --root E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01 --group low-control --trial cold_1
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper_matrix.py recover --root E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01 --group low-control --trial cold_1
```

`init`只封存小fixture/源清单，不导入torch或读完整模型；对子组child只存输入政策模板，父片接受后 `seal-child --group child-control|child-fast` 写不可变具体fixture并绑定matrix先定政策，不改matrix。`start-group`启动前台持有Popen/Job的controller；外层后台启动须隐藏窗口并保存日志、真实PID/epoch，不能依靠shell PID冒充owned服务。`prepare`先原ID文本/图像，成功后原IDpair；长HTTP响应丢失只查同ID。

`run`严格一次trial；warm_n要求同epoch前序技术完成，不能跳号，不允许从退出服务补热样本。`review`仅写真实人工结论。`stop-group`写原owner PID/epoch停止请求，由controller合作退出并保存实际exit/unforced/portclosed；`report`只读原证据生成结果和缺项。不自动推进遇到的人工门槛。

恢复优先从原history/promoted artifact收集，足够档案时0HTTP/0producer；服务仍活着才查原queue/history。unknown保留原client/prompt ID，不重POST，worker死亡不恢复未持久化扩散中间步，不重启原root。已完成视频或超分帧验真后复用。同进程用已有受保护proof；进程重启仅在必要恢复边界重建一次媒体证明，不每次report重解码。

兼容边界：v1 profile的source.artifacts保存原仓库绝对路径，修改共享模块后正常transport的InputLeases会因原源SHA漂移拒绝，这是正确保护，不能取消。旧05已完成根只提供只读离线档案/媒体恢复（显式禁止HTTP和producer，必要时使用其已封存executed-source快照）；不启动旧root、不改旧profile，不把“保留v1兼容”解释为允许旧运行环境在新源码下继续POST。旧unknown仍保持unknown。

### 媒体、1080P与统计

`wan_wrapper_media.py`按v2 fixture预算检查生成尺寸/帧数/全部PTS/16fps/finite-before-uint8、黑帧及真实末帧；一次必要完整RGB解码同时保存后续全帧提取需要的PNG证据，避免技术验真后又完整解码仅为提帧。子片裁剪从该RGB/PNG序列保留[1,78)再编码，核对77帧/PTS，编码/验证计时单列；其余generated=retained直接复用。

新增 `wan_wrapper_matrix_postprocess.py` 只消费Wrapper技术结果及真实review，转换为既有超分/合成需要的显式输入对象，不伪造native的experiment marker或acceptance。复用 `postprocess_local_gpu.py` 的逐帧durable intent、RealESRGAN_x4plus→Lanczos1920×1080、原narration/font冻结及AAC48k/字幕实现；抽取小的结果/fixture验证回调让Wrapper可注入，不削弱原native验证。新CLI `postprocess --group <group> --trial <trial>` 需Wan owner已关闭、对应原视频人工接受、原时间线/字体来源绑定齐全；按既有LVA-01后处理root的冻结来源读取，不猜音轨、字体或字幕。

低/高各8成片、父片两mode各只超分被消费的cold_1（不单独交付）、子8份复用对应被接受cold父片的93帧超分，生成8父子链；未消费的父warm不为凑2848帧超分，因此**2848是上限**。按此父帧复用方案，实际新超分预算为16×93+2×93+8×77=2290帧；输出成片仍包含全部2848帧位置。已完成且来源相同的父帧复用，实际帧任务数单独记录，不伪称独立生成。每个成片输出帧源/PTS/音轨/字幕/完整解码及真实人工结论；下游服务身份/模型沿用LVA-01已建立路径，Wan与其不能同时运行。

JSON逐trial列出temperature定义、owner/epoch、fixture/profile/graph/prompt、生成/保留/末帧SHA、技术/质量、原始计时和资源路径、失效/缺失原因、恢复次数及实际POST/producer计数。输出cold单值、warm n=3的median和P95（线性插值h=(n-1)*0.95），缺样则保留n与缺项，不写完整矩阵。失败/重做/拒绝率按实际提交和审核分母分别报告，计划重复不算重做，审核待定不算接受。

分开setup、submit→技术完成、execution、两专家采样、VAE、编码/技术、trim/提帧、超分、合成、恢复和人工响应区间。人工等待取区间并集，不相减充当GPU时间，不把嵌套阶段相加；资源采样标为设备级且有采样周期，native peak commit/RSS另列。选图交接→1080P技术可用/质量接受分别报告，排队/准备/审核都保留包络。

W0直接引用LVA-01/04已完成原生结果，不重跑。整数timestep、fp32VAE、采样配方/CFG及历史工具环境边界不同，不归因纯后端倍数。热native时间和完整1080P吞吐分别评价；只有完整质量/连续性/端到端通过才可建议另开生产接入设计。n=3只能描述本机固定fixture观察，不写稳定泛化结论。质量失败/兼容失败/无收益可按停止分支完成结论；尚待执行或待审核不能当负面结果伪装完成。

## Files

- 新增 `src/video_ai/experiments/wan_wrapper_matrix.py`：不可变matrix/group/trial/fixture合同、审核/父子关系、授权上限和结果聚合。
- 新增 `scripts/benchmark_wan_wrapper_matrix.py`：上述CLI与串行调度，持久化原ID，不直接实现模型数学。
- 新增 `src/video_ai/experiments/wan_wrapper_matrix_postprocess.py`：Wrapper到既有全帧超分/合成的显式适配。
- 修改 `wan_wrapper_backend.py`、`wan_wrapper_nodes.py`、`wan_wrapper_media.py`、`wan_wrapper_text.py`、`wan_wrapper_vae.py`：显式v2分支实现固定多fixture seed/帧/token预算、多trial claim和证据；v1行为保持。
- 修改 `scripts/observe_wan_wrapper_comfy.py`：v2 profile/schema/授权、按group启动与原owner关闭，复用既有软件保护及Job；`scripts/postprocess_local_gpu.py`只抽取必要输入验证回调。
- 新增 `docs/task-designs/LVA-07-06-node-contract.json`，保留04原合同；原生workflow和Wrapper第三方源码不修改。
- 新增 `tests/unit/test_wan_wrapper_matrix.py`、`tests/unit/test_wan_wrapper_matrix_postprocess.py`、`tests/integration/test_wan_wrapper_matrix_recovery.py`；相邻测试仅补实际修改的v1/v2分支。
- 新增 `LVA-07-06-plan.md`、`LVA-07-06-results.json/.md`、`LVA-07-06-completion.json`（按实际进度建立）；专项总 `LVA-07-results.json/.md` 追加06最终入口，保留历史事实。
- 回填任务板本项设计路径；批准前保持NOT_STARTED，实际开始后依次READY→IN_PROGRESS；验收完成才COMPLETED。没有后继任务，不虚构交接。

## Tests

先以小fixture/注入HTTP/合成媒体建立失败，再实现；不运行完整模型payload的离线矩阵，不跑无关全库。以下命令在实现后执行，当前没有执行或通过声明：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_wan_wrapper_matrix.py tests/unit/test_wan_wrapper_matrix_postprocess.py tests/integration/test_wan_wrapper_matrix_recovery.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_wan_wrapper_backend.py tests/unit/test_wan_wrapper_cli.py tests/unit/test_wan_wrapper_media.py tests/unit/test_wan_wrapper_text.py tests/unit/test_wan_wrapper_vae.py tests/integration/test_wan_wrapper_recovery.py tests/integration/test_wan_wrapper_worker.py -q -p no:cacheprovider
```

必须覆盖：

1. v1只接受05两样本；v2拒绝伪造/错matrix/错group/超额/重复trial/跨mode授权，拒绝schema或源漂移。32上限不能通过新ID绕过。
2. 四fixture真实seed，81→77裁剪/末帧/PTS、21/24 latent及每fixture完整tokens；不能改prompt或压成93通用子片。CPU原tokenizer结果封存检查，不导入完整T5。
3. 同seed四图实际Sampler执行4次、证据独立、conditioning复制无累加，warm跨epoch/跳号拒绝；control零LoRA、完整pair未通过fast拒绝。
4. 父片未接受、wrongmode/profile/末帧替换/接受记录漂移均在child POST前拒绝；父warm不隐式替代cold；child-fast比较明确不同父图变量。
5. 超时、accepted冲突、post后未记ID、完成未收集只恢复原ID；完成恢复0POST/0producer，report不触发解码；重启失效proof只一次必要重建。小合成81/93帧真实FFmpeg验证，不生成额外GPU样本测试恢复。
6. 后处理拒绝无审核媒体/错误帧来源/错误字幕音轨；已完成父帧只复用、不重复POST，完整1080P音画/PTS可核对。统计n/分母/median/P95和人工等待并集准确，缺项不算通过。

真实实验仅按批准清单执行上述CLI，先每服务prepare+pair，再该mode四次；任何已完成trial优先复用。记录实际命令/退出和原始证据，不能用pytest代替GPU或人工质量验收。

## Acceptance

- 成功分支：8组×冷1热3共32份原视频（保留全部2880生成帧）、对应保留预算和PTS、逐trial完整身份/技术/真实人工接受；新父片接受先于子片POST且同mode/profile，子片81/77及170帧连续链正确。
- 全帧超分和24份1080P低/高/父子交付、音轨字幕/技术/人工接受有实际证据；上限与实际复用数量分别报告。未执行该层不能标完整端到端通过。
- 计时边界、冷/热准入预热、分层资源/失败/人工等待与历史基线变量明确；原ID恢复无重发，完成产物不重做，所有owned服务实际退出/端口关闭。
- 若真实技术/质量失败：保存原失败/unknown及停止证据、已完成项、后续NOT_RUN和明确不推广结论，可按本任务失败停止分支收尾；没有发生失败而只是缺执行/审核时保持未完成。
- `LVA-07-06-results.json/.md` 与专项最终入口、任务板完成证据一致；未恢复生产、未改变即梦/原生默认、无付费调用。原始授权/审核不可由程序代替。

## Risks

原05成功只是单样本，不能证明高运动/81帧子片、其他文本上下文、长服务热运行或全部1080P可用。18GiB峰值或本机可用容量可能不足，沿用预算失败即停，不自动放宽或重试。cold是准入后的fresh-process首视频，不能抹去约38分钟pair成本。固定seed样本可能相同且不独立。parent两mode输出不同使child输入不同，必须按整链解释。新schema和多trial会影响Comfy缓存、所有权与恢复，必须保留v1测试。现有工作区有大量前项未提交文件，保留全部已有变更，不提交、重置或覆盖。

执行许可已由用户“同意”取得；按本文范围实施，源/profile实际摘要在封存时取得，不伪造未来SHA。后续视频质量接受仍需绑定实际媒体。

### 2026-11-20 实际中断与待决补充

原矩阵完成cold_1/warm_1两份并获用户“视频没问题”反馈；warm_2在POST前遇隐藏Windows子进程的OEM输出/UTF8解码异常，服务依失败规则exit0退出。监听检查已按bytes协议修复，118定向测试及实际隐藏子进程验证通过。详情与既有3项无关fixture失败见 `docs/task-designs/LVA-07-06-listener-fix-results.md`。

原epoch不能复活或拼接热3；源身份变更也要求新root。用户本次对32→34总上限及约80分钟增量明确回复“继续”，批准在新root `E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-02` 完整补齐32份新矩阵；原2份保留历史证据，不混入新epoch统计。每个新矩阵仍按32份/每组4份封存，任务总量为原2+新32=34；授权额外绑定此前root、已用2份与任务总上限34。资源/数值/人工质量门槛保持。
