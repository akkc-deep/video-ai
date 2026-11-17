# LVA-04 独立 Wan 高速实验模式设计

## Goal

为任务板 `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md` 的LVA-04交付可追溯、可拒绝、可回退的独立高速实验。比较原40步quality与匹配Wan2.2 I2V A14B双专家的4步蒸馏候选，随后逐项记录attention/cache/compile的支持或拒绝结论。此设计和交接不启动实施、不下载权重、不安装包、不授权新的GPU实验或旧生产恢复。

## Scope

- 直接输入只有LVA-01固定素材/质量与观测基线、LVA-02冻结/HTTP/恢复规则；LVA-03只确定实施顺序，不启用其候选，也不把它作为本项技术依赖。
- 创建 `workflows/wan22_i2v_14b_fast_api.json`、`.mapping.json`、`.provenance.json`。原quality workflow SHA保持 `5f3768f6e83bf6be21287457c7c15e811d8f6949b7b5c5ac5460c267c8f98666`，原mapping和所有旧任务字节不变。
- 新模式先仅用于新的独立实验task：`quality`沿用原40步/CFG3.5/15+25；`fast_experimental`使用明确冻结的蒸馏recipe。不给旧生产options或原request/intent补字段，不把实验自动提升为生产默认。
- 既有原生Comfy为选定实现环境；官方WanVideoWrapper图只作来源对照，不安装Wrapper，不换base模型、不在线merge/量化原模型。若原生加载不兼容，候选明确失败并停止，不自行切换另一引擎或猜参数。
- 原输入、seed、768×432/16fps、全部生成/贡献帧和人工父子门槛保留；单GPU单请求串行，服务不跨审核，unknown只恢复原GET。

## Approach

### 已确认来源与第一候选

研究证据 `docs/task-designs/LVA-04-source-research.json` 是小型官方元数据快照，没有下载权重。官方来源：[模型卡](https://huggingface.co/lightx2v/Wan2.2-Distill-Loras)、[固定版本参考图](https://huggingface.co/lightx2v/Wan2.2-Distill-Loras/resolve/57adea585d1d21085e2dfc91ce3c7b646cdd9345/wan2.2_i2v_scale_fp8_comfyui_with_lora.json)。revision固定 `57adea585d1d21085e2dfc91ce3c7b646cdd9345`，参考图SHA `aecf199c8451c2272fb53f6a96854c12cd596297326f426a6d7bf4533c7383b8`。

第一候选只用官方I2V A14B的1022 high/low rank64配对，强度均1.0：

| 角色 | 文件 | bytes | SHA256 |
| --- | --- | ---: | --- |
| high | `wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors` | 634645944 | `887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19` |
| low | `wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors` | 739472104 | `8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1` |

实施时获授权后才从上述revision的resolve URL下载，分别置于 `E:/VideoAI/shared/models/comfyui/loras/<原文件名>`；先写新staging，核对bytes/完整SHA再晋升，不覆盖既有不同内容。缺失/错配/漂移必须在POST前拒绝，不自动下载或改用T2V/Wan2.1 LoRA。当前本机没有loras目录；base继续为LVA-01实际使用的high/low fp8_scaled、T5及VAE，身份从已冻结基线取得，不猜新的base文件。

参考图确实依赖WanVideoWrapper，不能由其“支持ComfyUI”推定当前原生支持；其中INT steps4/split2、LoRA强度约1、Euler和sigma `[1,0.9375001,0.8333333,0.625,0]`提供候选参数来源。原生候选固定Euler/simple、shift5、4步、CFG1、high0..2加噪/保留剩余噪声、low2..4不加噪/最终去噪。应记录原生实际sigma并与 `[1,15/16,5/6,5/8,0]` 逐项误差<=1e-6对照；不匹配则拒绝此recipe，不悄悄调整采样器或sigma。

### 原生图谱与双专家准入

当前原图 `129:131=false`；`129:116/117` 的true/false都直连原UNET，没有LoRA加载。**不能只打开这个4步开关。** 新图保留原输入/输出节点及seed/image/size/length/fps的mapping，删除131、116/117、118/119/120、122/124/125/126/127/128这些切换/常量节点，采样参数改为明确scalar；`129:104`为high、`129:103`为low。

新的诊断process内注册 `LVA04LoraPair`（ID `lva04:lora_pair`），仅在本项launcher加载，不编辑Comfy安装或生产node目录。输入为high/low两MODEL、`lora_high_name`、`lora_low_name`、`strength_high=1`、`strength_low=1`，输出MODEL[0]=high、[1]=low；接到104/103，再进入86/85两个sampler。两个LoRA都加载成功才返回，防止一个专家未准入就开始采样。

节点复用当前Comfy的 `lora_convert.convert_lora`、`lora.model_lora_keys_unet`、`lora.load_lora`及clone/add_patches；不自行转换权重数值。两侧patch集合必须非空、所有loaded patch key均被add_patches接受，任何“lora key not loaded”或shape不符立即raise，标记 `incompatible_lora`，保留原history/error、不重发。第一版本仅接受rank64普通LoRA的2D线性patch（up/down乘积与目标矩阵shape一致）；其他patch形式明确unsupported，不通过宽松忽略制造假成功。模型与LoRA仅完整准入一次，记录实际应用patch数，后续边界仍使用强内容/身份保护，不在每次HTTP重新hash大模型。

### 实验冻结与接口

新模块 `src/video_ai/experiments/wan_fast_profiles.py`：

- 不可变 `WanFastProfile`，字段：`schema_version=1`、`mode`、`factor`、base/LoRA完整Artifact、strengths、workflow/mapping/provenance Artifact、steps/CFG/split/shift/sampler/sigma_points、attention_backend、cache_backend、compile_backend、residency_policy、Comfy/node/Python/PyTorch/CUDA/driver/package版本与源码/二进制摘要。`identity_dict()`固定字段集，`digest()`为canonical SHA。
- `load_profile(mode, *, factor, assets, capabilities) -> WanFastProfile`；只允许下述有限组合，默认quality；缺权重、SHA错误、high/low调换、未知field/backend或未通过capability均拒绝。
- `freeze_profile(root, profile)`只为新实验root写 `frozen/profile.json`；`verify_profile(root, expected_digest)`在每次提交/恢复/证据写入前核验。新 `request.json`声明schema1、profile_sha256、fixture/request/graph SHA、原seed/预算和父片binding；每trial `profile-binding.json`将其绑定原intent/HTTP。不向Comfy POST body添加额外未知字段。
- 新client包装既有ExperimentClient，先检查profile、服务启动profile_digest、argv/environment版本及原graph，再委托既有durable intent/queue/history/accepted协议。既有intent只允许原GET，profile漂移拒绝；已完成原产物先验真返回，producer/POST为0。不修改旧client的既有质量路径行为。

新harness的 `build_trial_fixture(source_fixture, profile, graph) -> dict` 保留 `source_quality_graph_sha256`、原source request/clip ID、seed及budget；将新 `source_graph_sha256` 设为已冻结profile图摘要、`graph_file='profile-graph.json'`，parameters明确写入该profile的steps/CFG/split。这样复用既有技术处理时不冒充原quality图，也不调用只接受40步来源的旧prepare函数来生成fast身份。client命名 `FastExperimentClient(root, *, profile_digest, port)`；旧ExperimentClient保持原接口。

启动器仅在新 `LVA-04-*` scratch root注册上述节点，声明profile_digest与node源SHA到service-owner/启动记录；原生quality启动参数保持现状。旧prepared run、生产UI/config/schema不加fast开关；mode属于新实验请求身份。若将来要接生产，必须另有真实质量采用决定和专项设计。

### 单变量顺序与能力拒绝

1. `factor=distill`：quality40基线对fast4完整蒸馏recipe，只换这一组必须共同生效的LoRA/steps/CFG/split参数；attention=native/cache=none/compile=none/residency=native。技术和人工质量均通过才进入下一项。
2. `factor=sage`：对已接受fast4仅加入 `--use-sage-attention`，新owned process，版本/实际backend进profile。当前embedded Python检测sageattention不存在；能力检查失败即 `unsupported`，不得把静默回退native当sage成功。不在本项自动安装/升级CUDA或Torch，安装需另有明确授权。
3. `factor=cache`：当前原生comfy/comfy_extras未发现TeaCache/MagCache，custom nodes默认禁用，没有已核验双专家实现；本设计选择 `rejected_unsupported`、cache_backend=none，不安装未知cache实现、不猜阈值。记录来源/能力查询和未测结果，不能填0秒或声称提速。新增实现需要修订设计再实测。
4. `factor=compile`：仅原生 `TorchCompileModel` 的inductor后端，分别包装pair输出后的两个MODEL；node实际clone会disable_dynamic，必须记入profile，不说是默认模型管理。当前triton不存在，所以先拒绝此GPU编译候选；仅在另行获准且已安装兼容后端的实验环境执行。冷编译成本单列，最多3600秒，无盲目重试；OOM/graph break/非有限输出为失败。不得强制两专家同时GPU常驻、不开highvram；`residency_policy`本项只允许native，其他策略明确拒绝。
5. `factor=combination`：只组合已各自技术+人工接受且有SHA绑定结果的factor，重新冻结并独立实测；缺失/未验证项不加入。若组合与某个已测profile完全相同，仅引用同一数据并明确没有新的组合收益，不为填表重复生成。

当前能力缺失是已定失败/拒绝分支，不是让实施者自行选新引擎、缓存或安装包的空白。原生LoRA兼容性、sigma与质量是待**实验回答**的问题：失败即保留quality并明确拒绝，不伪称高速模式验证成功，也不自动改成另一个recipe。

### GPU、质量与报告

实现/离线测试完成后，先列出固定manifest、所需两权重大小/摘要、精确新root/命令，再取得本项下载/新GPU授权；LVA-03授权不外推到本项。复用LVA-01低/高/父子固定输入，帧/尺寸/seed不变。每个可执行factor在新process冷1/同process热3，父片人工接受后才读取真实末帧并由新服务生成子片；不跨审核保留模型。离线normal/recovery、真实GPU、编译冷成本和人工等待分别报告。

每个profile使用其自身实际生成并接受的父片；fast子片不能借用quality父片来掩盖接缝。两profile父片不同导致真实子片输入SHA不同时，如实记录派生依赖差异，不声称子片初始像素完全相同；初始选图、prompt/seed及帧预算仍固定。父片未接受即停止该链，不能造子片结果填表。

每份技术检查完整帧/PTS/宽高、完整解码一次，逐帧非有限像素/近黑全帧检测作为明显失败信号，不能代替人工质量。人工完整观看检查闪烁、角色/纹理、颜色、运动和尾帧接缝；同字节结果仅在实际完成并有明确授权后复用观看结论。技术/质量失败保留原ID与媒体，不重发未知请求，不自动降低分辨率、帧数或返回quality来掩盖失败。

非有限检查在Comfy VAE输出IMAGE浮点tensor转uint8前做一次 `isfinite().all()`，失败则本请求终止，不靠已编码8bit视频推测NaN。近黑检查复用唯一一次完整decode的RGB24流：连续>=2帧且每帧>=99.9%像素三个通道都<=1/255时标记 `suspect_black`，需人工明确判定，不能把合法黑色背景自动判成通过或自动删帧。上述阈值和检查实现SHA进入profile；quality/fast对照使用同一检查，不另起逐帧FFmpeg进程。

报告 `LVA-04-results.json/.md` 对distill/sage/cache/compile/combination逐项标明passed、failed、unsupported、not_run、rejected或quality_pending及实际证据；缺实际GPU不得说fast validated。正式采用始终另行决定，默认quality不变，不预设倍数，不把局部节点时间相加成整片吞吐。

## Files

- 新workflow/mapping/provenance三件套：固定原图SHA、官方revision/两LoRA SHA、选定recipe及node源码。
- 新 `src/video_ai/experiments/wan_fast_profiles.py`：有限profile、强身份冻结和原服务绑定核验；不修改production options。
- 新 `src/video_ai/experiments/wan_fast_nodes.py`：进程内 `LVA04LoraPair`、原生sigma记录/断言和patch准入，不导入或启动GPU于主协调进程。
- 新 `scripts/observe_fast_comfy.py`、`scripts/benchmark_wan_fast.py`：有时限owned服务、profile client、单变量/恢复实验；复用既有观测和媒体工具，不重写unknown协议。
- 新 `tests/unit/test_wan_fast_profiles.py`、`test_wan_fast_nodes.py`、`tests/integration/test_wan_fast_recovery.py`；新结果JSON/Markdown。源研究现已存在，不代表已安装/实测。

## Tests

先RED后实现。用小文件Artifact和fake MODEL/patcher测试准确profile字段/摘要、错配highlow、缺权重/错SHA、patch未全应用/shape错、两专家原子返回、4/2/CFG1/sigma固定、原40步图和mapping字节不变、capability缺失显式unsupported、不允许非native驻留。不要用真实大模型做单元夹具。

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_wan_fast_profiles.py tests/unit/test_wan_fast_nodes.py tests/unit/test_gpu_baseline_experiment.py tests/unit/test_scene_comfy_transactions.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/integration/test_wan_fast_recovery.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_fast.py --mode fast_experimental --factor distill --offline --output E:/VideoAI/scratch/benchmarks/LVA-04-offline-results.json
```

期望定向通过；fake HTTP lost-response只找原ID，profile/LoRA/node/backend变更在POST前拒绝；完成恢复0POST/0producer、所有证据在协调线程；unsupported不启动服务。离线全程拒绝网络/GPU；真实模型下载/GPU命令必须另获本项明确授权，不能把上述离线通过当本机4步质量通过。

## Acceptance

1. 三件套和双专家/recipe来源身份可复现；原quality文件SHA和旧恢复结果不变，新模式只创建独立新实验身份。
2. 实测或明确拒绝每个factor，真实环境版本、节点/LoRA应用、sigma/步骤/CFG、GPU峰值与冷/热/编译时间可追溯；未支持项不猜测。
3. 原输入及全部帧/PTS与父子门槛保持，无第二POST或已完成媒体重生成；漂移严格拒绝。
4. 每个实际候选有技术和人工质量结论；严重下降/不兼容明确否决默认采用。未运行GPU只能交付实现/离线部分，不能登记高速模式验证完成。
5. 最终结果区分局部/端到端和normal/recovery，实际采用需另行确认；默认quality及原生产暂停状态保持。

## Risks

- 官方参考用WanVideoWrapper和LightX2V原base文件，本机是native Comfy与既有fp8_scaled；“同架构”不证明patch数值/调度/质量兼容。选定原生验证和严格拒绝分支，不宣称已支持。
- SageAttention/Triton目前缺失，cache未核验；不因其他硬件经验安装或启用。TorchCompileModel关闭动态VRAM，24GB设备有OOM风险，编译冷成本可能抵消收益。
- 新API实验模式不等于生产可用快档。未知结果不能fallback伪装成功；保持原40步路径和原unknown/accepted是硬约束。
- LVA-01/02已披露的legacy模型夹具、无效run、continuity路径和交付reclaim缺陷不纳入本项扩修。不存在实际fast质量数据；这正是本任务实验对象，而非已通过前提。
