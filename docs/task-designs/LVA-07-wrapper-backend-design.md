# LVA-07：WanVideoWrapper 后端兼容与 LightX2V 加速实验设计

## Goal

在不修改即梦生图、不破坏原生 ComfyUI/Wan2.2 质量路径的前提下，验证 Kijai ComfyUI-WanVideoWrapper 是否能正确加载当前 Wan2.2 I2V 14B 双专家、处理 LVA-04 失败的 LightX2V 4-step high/low LoRA，并在 RTX 5090D V2 上带来可接受的端到端加速。

本任务首先是独立后端兼容性实验，不是立即迁移生产，也不预设 Wrapper 一定能加载该 LoRA 或一定更快。只有完成完整模型/LoRA准入、实际采样、技术验收和人工质量验收，才能报告可用候选。原生 quality 工作流继续作为回退和对照。

## Scope / Non-goals

- 只覆盖即梦图片已经人工选定之后的本地生成：Comfy 服务、Wan I2V、视频技术检查及现有片段输出接口。即梦 API、图片候选、下载、选图和通知完全不改。
- 新增独立 Wrapper worker / workflow / adapter / 实验记录；不在现有 Comfy 安装的 custom_nodes 中直接安装或覆盖，不升级当前生产 Comfy、Python、PyTorch、CUDA、Triton 或其他依赖。
- 不修改原生工作流 workflows/wan22_i2v_14b_api.json、mapping、已有 LVA-04 fast graph、原始生产配置、旧 run 的 request/intent/accepted/unknown、媒体和锁。
- 不把 Wrapper 引入生产默认，不把新节点直接加入生产服务，不恢复暂停生产；实验在新的 scratch root、独立端口、独立进程和独立服务所有权下运行。
- 保留原输入图片、prompt、seed、768×432、16 FPS、生成/保留帧预算、父子尾帧绑定、人工连续性门槛、完整帧与PTS证明、超分和1080P输出要求。
- 不把切换 Kijai 重打包 base model、改变量化/精度、改采样器、减少帧数或换分辨率所得的速度差，归因于 Wrapper。

## Evidence and rationale

- LVA-04 在原生适配器 LVA04LoraPair 拒绝了官方 LightX2V high/low 权重：混合包含 diff、diff_b、diff_m 类型；high 权重发现41个 diff_m 未加载。请求 66cd1918-4276-4ee6-ac84-8d6235b70ba3 未进入采样、没有 fast 视频。见 docs/task-designs/LVA-04-results.md 与 LVA-04-native-rejection-evidence.json。
- LVA-04 质量基线：RTX 5090D V2，768×432/16 FPS/93帧，原生 Wan2.2 I2V 14B FP8 scaled，40步、CFG3.5、Euler/simple、high15/low25；热 P50 约470.598秒（计时含提交跟踪和技术处理，比较时必须复用同一边界）。LVA-01 提供低/高/父/子素材与更完整阶段基线。
- Wrapper 官方仓库 README 明确说明其为持续 WIP / sandbox，作者建议原生已有功能优先用原生；只有原生未提供的模型/功能才考虑 Wrapper。README 提供 Windows portable 安装方式、Wan 模型目录和 offload 注意事项。风险必须通过隔离环境与固定 commit 控制。
- Wrapper 源码存在 WanVideoModelLoader、WanVideoLoraSelect、WanVideoSetLoRAs、WanVideoSampler 等节点；采样器代码明确处理未合并 LoRA patch，并说明 FP8 matmul 与 unmerged LoRA 有限制。这证明存在独立加载/采样路径，不证明它一定支持当前权重中的每种混合 delta；必须做实际逐项准入审计。
- 参考来源：
  - Wrapper 仓库及 WIP / 安装 / 模型路径 / VRAM说明：https://github.com/kijai/ComfyUI-WanVideoWrapper
  - 模型加载节点：https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/main/nodes_model_loading.py
  - 采样节点：https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/main/nodes_sampler.py
  - Wrapper 官方 FP8 scaled 模型集合：https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled
  - LightX2V 权重及参考工作流固定版本见 docs/task-designs/LVA-04-source-research.json / LVA-04-design.md。

## Architecture

### 1. Isolated backend boundary

新增实验专用入口：

- src/video_ai/experiments/wan_wrapper_backend.py：只负责 Wrapper 环境/节点能力清单、模型与 LoRA 准入、workflow/profile identity 和实验 backend 构造。
- scripts/observe_wan_wrapper_comfy.py：创建/观察/关闭独立 owned Comfy 子进程；固定独立端口（从空闲端口分配并持久化）、argv、环境变量、Python executable、工作目录、Wrapper checkout commit、Comfy commit、节点源码 SHA、依赖版本及服务 PID/start identity。
- scripts/benchmark_wan_wrapper.py：离线模拟、能力探测、单片段 GPU benchmark 和原ID恢复测试入口。
- workflows/wan22_i2v_14b_wrapper_api.json、mapping、provenance：Wrapper 专用工作流；输入输出映射显式覆盖 positive/negative prompt、首帧、宽高、长度、FPS、seed、模型/LoRA角色和输出。
- tests/unit/test_wan_wrapper_backend.py、tests/integration/test_wan_wrapper_recovery.py：隔离的能力/身份/恢复测试。

生产侧若未来接入，只能由窄的 VideoInferenceBackend 协议适配，不在本任务修改 production_scene_clips.py 的默认实现。接口至少包括 capabilities()、prepare(profile)、submit(graph, durable_intent)、recover(original_identity)、collect(original_id)、close()；当前仅实验 harness 调用。

### 2. Version pin and environment isolation

- 不使用浮动 main 自动更新。准备阶段读取 Wrapper 当前 HEAD，检查提交历史、README、requirements.txt、pyproject.toml、__init__.py 必需模块与节点输入；选择经过审阅的完整 commit SHA，记录在 LVA-07-environment-manifest.json。本设计不伪造尚未验证的 SHA。
- 在独立 checkout（例如 E:/VideoAI/shared/custom_nodes/ComfyUI-WanVideoWrapper-LVA07）及独立 worker 配置中运行。依赖先做 dry-run / wheel 清单 / Python ABI、torch、CUDA、Triton、xformers、sage 等冲突审计；不对当前生产 embedded Python 执行 pip install。若依赖无法在独立副本兼容当前 CUDA 13 / PyTorch 2.14.1+cu130 / Python 3.13.14，则建立单独实验 venv/portable runtime，不能升级生产环境。
- 记录 GPU driver、GPU 名称/显存、Comfy commit、Wrapper commit、Python、PyTorch、CUDA runtime、关键包、所有节点源码与二进制 SHA。每次运行启动前核对身份，运行中 PID/start identity 绑定；服务关闭后确认 PID 不存活、端口不监听。
- Wrapper README 明确提醒 offload 与 LoRA buffer 会影响 VRAM；默认先用 offload-device/block-swap 保守配置，禁止未经测量强制两套14B专家同时常驻24GB显存。记录 swap blocks、prefetch、offload device 和峰值VRAM。不得将 README 中其他硬件演示数字当作本机预测。

### 3. Model / LoRA compatibility gate

按以下顺序进行，任何一项失败都必须在生成 POST 前拒绝：

1. 从 LVA-01/LVA-04 已冻结模型记录读取现有 high/low、T5、VAE 的准确文件名、字节数、SHA、dtype 和量化方式。不能仅凭同名认为 Kijai 模型与原生 Comfy 模型字节/结构相同。
2. 先尝试在 Wrapper 中加载与现有基线完全相同的 base artifacts。若 Wrapper 需要 Kijai 专用重打包模型，单独记录其来源、revision、文件 SHA、量化和结构映射；此时必须把它视为不同模型变量，不能与原生同模型做纯后端速度归因。先完成 Wrapper 40-step quality 对照，再测 fast LoRA。
3. 分别对 high 与 low LoRA 执行只读 safetensors header / key / shape / dtype / tensor count 审计；用 Wrapper 自身 converter/loader 在模型副本上加载，记录每个 LoRA tensor：输入key、映射目标、patch类型、shape、dtype、是否 consumed、是否 applied、未识别原因。任何未加载 key、静默跳过、shape不匹配、patch冲突、非有限权重或只成功一个专家均拒绝整个 pair。
4. high + low 作为原子组合：两专家均通过、实际patch应用数量与来源预期一致，才可创建可提交 graph。保留 LoRA strength、merge/unmerge 策略、FP8 matmul兼容策略；若 unmerged LoRA 与 FP8 matmul 不兼容，需使用 Wrapper 明确支持且已记录的配置，不可静默改变权重或忽略 LoRA。
5. 只有当原始1022 LoRA pair 被完整加载并应用，才允许进入4-step候选。LoRA加载成功不等于推理质量通过。

### 4. Experiment matrix (single-factor)

每个实验使用新 root / 新 profile identity，单 GPU 串行；低运动、高运动、父片、子片素材沿用 LVA-01 fixture。冷1次、同一 owned service 热3次；先完成技术验证，再进行人工质量审核。

| Trial | Backend | Model / LoRA | Steps | Purpose |
|---|---|---|---:|---|
| W0 | 原生 Comfy | 原 base / 无 LoRA | 40 | 现有基线（引用 LVA-01/LVA-04，不重复生成；若环境/边界不匹配则新测） |
| W1 | Wrapper | 同一 base / 无 LoRA | 40 | 隔离后端差异与 Wrapper 基线 |
| W2 | Wrapper | 同一 base + 完整 high/low LightX2V pair | 4 | 首选加速候选 |
| W3 | Wrapper | Wrapper 专用重打包 base + 无 LoRA | 40 | 仅当同一 base 不兼容时，用于建立替代基线 |
| W4 | Wrapper | Wrapper 专用重打包 base + 完整 high/low pair | 4 | 只有 W3 与 LoRA 来源均已验证才运行 |

不必机械执行所有行：W1 无法加载同一 base 时，记录拒绝后再决定是否准备 W3；W2/W4 的两个专家任一不完整加载，立即停止，不发送模型推理请求。不得为填矩阵重复生成已完成样本。

每次只变更一个因素：backend、base model、LoRA pair、采样 recipe 不混为同一个对照。若 base model 必须更换，则速度结果只能表述为“整套 Wrapper+新base+LoRA 配置”的整体差异，不能归因于 Wrapper。

### 5. Sampling / workflow contract

- 首先建立 Wrapper 40-step workflow，准确复现原生的图像尺寸、latent length、16fps、seed、prompt、negative prompt、CFG、shift、sampler/scheduler、high/low split 和 output frame contract。若 Wrapper scheduler / sigma 与原生不能严格对齐，明确标记 baseline 不等价，不能用来宣称纯后端加速。
- fast workflow 才使用 LVA-04 固定的 LightX2V 1022 recipe（4 steps、CFG1、split2、Euler、shift5、sigma points [1, 15/16, 5/6, 5/8, 0]），但需从 Wrapper 的实际 scheduler/采样记录核验真实 timesteps/sigmas，不因节点 widgets 显示4就认为只执行4次有效模型调用。
- 固定 seed 和完整输入；保存最终 graph、节点类名、节点输入、prompt/graph canonical digest、模型/LoRA身份。每个原始请求保留 durable intent、Comfy client_id、prompt_id、accepted/queue/history/输出证据。
- Wrapper 节点是 WIP，workflow schema 随版本可能变化；必须用实际 /object_info 验证节点/输入/输出类型，并将其绑定到 Wrapper commit 和节点源码 SHA。缺节点/字段或版本漂移在 POST 前拒绝。
- 禁止 fallback：Wrapper 报错后不得悄悄切回原生、改用不同 LoRA、降低帧数或变更 prompt；失败实验保留原 ID/error，不自动重新提交。

### 6. Output adapter and recovery

- 输出统一为现有 SceneClipResult 所需的标准 MP4/帧/PTS证据，不让下游知道 Wrapper 私有 latent 结构。只在实验适配器层做转换。
- 输出媒体必须完整核验帧数、尺寸、FPS、PTS、可解码性、RGB帧数、非有限数（在 VAE tensor 转 uint8 前）及文件 SHA；每个完整视频只做必要的一次全解码，复用同一事务结果，不重复全局扫描。
- 同一连续链严格串行；父片技术检查后必须获得真实人工接受，子片才可绑定该父片的真实尾帧 SHA 与接受记录。不同独立场景可以准备 CPU 侧素材，但 GPU Wan 推理单请求串行。
- durable intent 在 POST 前持久化；接受后立即记录原 prompt_id。HTTP 超时/连接断开时只用原 client_id / prompt_id 查 queue/history，无法唯一确认时进入 submit_unknown，禁止自动重发。Wrapper/Comfy 服务重启后先验证原 service identity 与 queue/history 真实性；未持久化的扩散中间步不承诺恢复。
- 中断后已生成且已验真的视频、已完成超分帧与合成产物必须复用；进程内缓存全部失效并从持久化证据重建。Wrapper 模型/profile/节点/依赖 SHA 任何变化均拒绝接续原实验任务，必须创建新实验 root。

## Performance instrumentation

从选中图片交接点开始计量本地链路，分别记录：

- Comfy/Wrapper 服务启动、节点导入、模型加载、LoRA加载/应用、卸载/换入换出。
- 文本编码、图像编码、high/low采样分别时间、实际模型forward调用数、真实采样timesteps、VAE decode、视频编码。
- CPU时间、GPU设备采样利用率、VRAM峰值、进程RSS、磁盘读写、offload/block-swap次数（若可观测）。
- 技术检查、trim、末帧提取、超分、合成、恢复成本；人工审核等待单列。
- 端到端指标：每质量接受的视频秒所需墙钟时间、单片段P50/P95、冷/热时间、失败率/重做率。不得把嵌套节点CPU时间直接相加或把GPU设备级采样说成独占kernel时间。

## Tests and acceptance

### Offline RED/GREEN

- Wrapper commit / node source / environment / model / LoRA SHA 任一漂移，POST 前拒绝。
- 节点缺失、字段变化、节点注册失败、重复 Wrapper checkout、依赖冲突、导入异常、错误模型目录均拒绝启动/提交。
- High/Low LoRA 任意一个 key 未消费、未应用、shape/dtype不符、patch冲突、NaN/Inf，整个pair原子失败。
- 40-step workflow mapping / 4-step workflow mapping / scheduler sigma / split step / prompt / seed / frame length 完整固定。
- POST超时只恢复原ID；未知结果不重发；完成恢复0 POST/0 producer；服务关闭确认PID退出和端口关闭。
- 原生 workflow/mapping/provenance SHA不变；即梦代码/协议不在 diff 中。

### Real media / GPU acceptance

- 先 W1 40-step 运行1个低运动93帧样本，证明 Wrapper 的输出契约与原生下游兼容；若 W1 的图像质量或基础参数无法对齐，停止，不执行 fast。
- 完成 W2 或 W4 的真实4-step样本，要求两个 LoRA 专家所有权重均被实际应用，真实 sampler调用/timesteps确认；输出完整93帧/PTS/尺寸/16fps。
- 低运动质量通过后，才测试高运动与父子链。父片真实人工接受前不得启动子片；子片使用同 profile、同 backend 的新父片真实末帧。
- 人工检查主体身份/结构、动作连贯、纹理细节、闪烁、颜色、镜头运动、尾帧与下一段接缝。技术检查不替代观看；不允许仅凭同字节或无异常日志自动记为质量通过。
- 只有全部技术/质量门槛通过且端到端中位耗时显著优于当前质量路径，才建议后续另开生产接入设计。无效、无加速或质量下降均可作为明确实验结论，不推广。

## Files / deliverables

- docs/task-designs/LVA-07-wrapper-backend-design.md（本文件）。
- docs/task-handoffs/LVA-07-handoff.md：仅在准备执行时建立；记录确切 commit、模型身份、隔离环境、GPU授权和命令。
- docs/task-designs/LVA-07-environment-manifest.json：实际审查后固定 Wrapper commit、依赖和环境SHA。
- workflows/wan22_i2v_14b_wrapper_api.json、mapping、provenance。
- src/video_ai/experiments/wan_wrapper_backend.py 与必要的隔离运行脚本、测试。
- docs/task-designs/LVA-07-results.json/.md：兼容、拒绝、GPU性能、恢复和人工质量结果。

## Task state and authorization boundary

初始化为 NOT_STARTED，设计完成后可由用户明确要求开始时转为 READY/IN_PROGRESS。写入设计/任务板不等于授权安装节点、安装依赖、下载/改写模型、启动Comfy服务、执行真实GPU推理或恢复原生产。实际下载、环境安装和新GPU试验必须先呈现固定commit、依赖、模型/LoRA大小与SHA、具体命令及预计资源占用，再取得该项单独授权。

## Risks and explicit stop conditions

- Wrapper 官方自述是持续WIP sandbox，不是稳定生产API；必须commit pin、隔离worker，不能安装到生产custom_nodes。
- Wrapper LoRA converter 能否处理 LVA-04 混合 diff/diff_b/diff_m 未经实测；必须以完整tensor consumed/applied证明，不得因为不报错就判定成功。
- Wrapper 推荐模型文件可能与当前native FP8 scaled base不是相同字节/结构；若更换base，必须分离变量和质量基线。
- Unmerged LoRA会影响显存；FP8 matmul和unmerged LoRA可能不兼容。24GB显存下需记录offload/block-swap，不假设两专家常驻。
- 若环境依赖需升级当前Comfy/PyTorch/CUDA，停止并建立独立runtime；不修改生产环境。
- 任何模型/LoRA/节点/环境身份变化、未知任务、父片未接受、质量失败、帧数/PTS缺失、OOM或服务所有权异常，均停止当前实验，不fallback、不重发、不自动推广。
