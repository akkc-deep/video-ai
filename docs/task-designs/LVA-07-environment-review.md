# LVA-07-01 环境与 Wrapper 加载路径只读审查

审查日期：2026-11-17（Asia/Shanghai）。本项交付为源码审查，结论 **停止当前候选的安装/推理准备**：固定版本的 unmerged 路径明确遗漏非线性 weight 目标；merged 路径也有跳过 block/head modulation 的静态缺口。两专家完整应用尚无证据，当前环境还缺少必需依赖。不宣布 Wrapper 普遍不支持，也不宣布 CPU 数值、完整模型、GPU 或质量验证已通过。

候选 commit：`a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`，项目版本 1.4.8，提交时间 `2026-11-13T01:07:13Z`。通过 GitHub connector 查询 `commits/main` 一次后固定；后续全部取证绑定该 SHA，没有再次解析浮动 HEAD。该提交只更新版本；父提交 `fed3cfa7f323c9fed33e622dc2fb7ddaeb8b2857` 把 `Wan21/Wan22` 改为强制导入，移除了旧版 fallback；本机源码包含这两个类，但实际导入未验证。

以下 `W:` 均指同一固定版本：[Wrapper 源码](https://github.com/kijai/ComfyUI-WanVideoWrapper/tree/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00)。`C:` 为本轮本机 Comfy 源码，commit `2c75dc1b379a59e0880619d029607af5169a62ef`；相关文件另有本轮 SHA256，保存在 JSON，不能仅用 git HEAD 证明工作区内容。18 份源码文本快照及只读元数据原始记录保存在 `E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit/`；未将它们放入 custom_nodes，未运行远程代码。`README.md` 返回404，实际文件名为 `readme.md`，已读取，不能把404当作无README。

## 环境与依赖矩阵

历史值来自 `LVA-04-results.md`；“本轮”来自独立只读查询，两者分别记录。Python 使用 `-I -S`，包版本读取 `.dist-info/METADATA`/`WHEEL` 和 `torch/version.py`，没有 import torch、Wrapper、Comfy 或其他第三方包。`nvidia-smi` 仅查询设备，不执行采样。

| 项目 | 本轮观察 | 判断与边界 |
| --- | --- | --- |
| Windows / Python ABI | Windows AMD64；Python 3.13.14 / MSC v.1944；torch 安装 wheel 标签见JSON | 与历史Python值相同；Wrapper pyproject 没有 requires-python 或经过测试的平台矩阵，不能据此认证3.13兼容 |
| torch / CUDA runtime | `2.14.1+cu130` / `13.0`（version.py与元数据） | 历史值相同；本轮未加载DLL或创建CUDA context，Wrapper custom-op及Comfy内部API运行兼容未验证 |
| GPU / driver | RTX 5090 D v2 / 610.88 / 24455 MiB（nvidia-smi） | 历史设备与driver相同；不推断双14B驻留可行或峰值显存 |
| Comfy | 0.44.0 / 上述本轮commit | `Wan21/Wan22`、`get_key_weight`、`string_to_seed`、`stochastic_rounding`、`apply_rope1/apply_rope` 的源码符号存在；未做导入/注册证明 |
| accelerate >=1.2.1 | 未发现安装分发元数据；索引1.16.0，Python>=3.11，py3-none-any wheel | 必需：W:nodes_model_loading.py:15、custom_linear.py:3、t5.py:20；当前环境无法视为就绪 |
| diffusers >=0.33.0 | 未发现；索引0.43.0，Python>=3.11，py3-none-any | requirements要求；scheduler包含多个转入模块；一个局部try/except不能证明整个依赖可省略 |
| peft >=0.17.0 / ftfy | 均未发现；索引0.21.3 / 6.3.1，pure Python wheel | 声明依赖；未证明所有分支运行需求，也未擅自删除依赖 |
| gguf >=0.17.1 | 未发现；索引0.19.0，Python>=3.10，py3-none-any | 虽loader局部try可吞异常，custom_linear→gguf_utils和sampler→gguf.py却强制导入，不能按“不用GGUF即可不装”处理 |
| pyloudnorm / protobuf / opencv-python | 均未发现对应分发；索引0.2.0 / 7.36.2 / 5.0.0.93 | requirements声明；前者pure Python，后两者分别有cp310-abi3-win_amd64 / cp37-abi3-win_amd64 wheel，ABI标签允许3.13不等于DLL/API实测通过 |
| 已有其它要求 | einops0.8.2、sentencepiece0.2.2、scipy1.18.1；numpy2.5.4、safetensors0.8.0、transformers5.21.0 | 声明最低版本/Requires-Python没有显见冲突；没有跑完整resolver，不能保证与未固定依赖联合兼容 |
| Triton / torch.compile | 未发现triton或triton-windows；triton3.9.0索引没有Windows wheel，triton-windows3.9.0.post30有cp312-abi3 Windows wheel | 后者标签可覆盖3.13，但torch2.14/CUDA13联合兼容未验证；compile可不配置，不是基础SDPA必装条件 |
| SageAttention / xformers | 均未发现；索引有sageattention1.0.6及xformers0.0.36的py3-none-any wheel | wheel并不证明CUDA kernel兼容；Sage的可选导入受保护，选sage模式时loader会明确报错；可走sdpa，不为审查安装它们 |

索引只读取 PyPI JSON，没有下载wheel、安装、pip dry-run或锁定依赖版本。这些最新索引版本只是取证值，**不是推荐安装锁**。所有本轮实际版本、Requires-Python、Requires-Dist、wheel文件名/标签及查询URL见同名JSON；当前缺8项 requirements 分发，完整节点导入还有传递依赖风险。

节点注册：W:__init__.py:18–24 的 Main/Sampler/ModelLoading/Utility/Cache 为 required，失败直接抛出；其余 optional 模块失败仅告警。不能用 optional 容错概括整个注册过程。duplicate checkout检查只告警且自身异常被吞，并不是强制拒绝；本机生产custom_nodes只列出示例文件，未安装Wrapper。W:readme.md:33–46明确WIP/sandbox及portable安装方式，不代表批准在生产运行安装命令。

## converter → loader → patch 路径

| 类型 | 目标和实际源码链 | merged / unmerged 审查结论 |
| --- | --- | --- |
| 普通LoRA | W:standardize_lora_key_format（nodes_model_loading.py:109起）保留/标准化名称；SetLoRAs:772→load_lora_for_models_mod:706→model_lora_keys_unet:633→C:comfy.lora.load_lora:41；loader输入分支为add_lora_weights:966→C:load_lora_for_models | unmerged由CustomLinear以`U@D`、alpha/rank、strength加到weight（custom_linear.py:6–25、158–168、217–265）；只针对匹配线性weight，含head时还显式skip；merged委托Comfy adapter.calculate_weight。未核对全部输入对数/shape；weight tensor计数不是patch数 |
| diff | 同一名称标准化；C:lora.py:76–80将`<target>.diff`放入`('diff',(tensor,))`；norm例如`blocks.0.cross_attn.norm_k.diff`指向`.norm_k.weight` | merged由W:utils.patch_weight_to_device:246→C:calculate_weight:492做加性更新；shape不匹配只告警不保证失败。unmerged只查CustomLinear.weight，norm不是CustomLinear，故这些diff没有完整应用路径 |
| diff_b | C:lora.py:38–39、82–86把`<linear>.diff_b`映射到`<linear>.bias`；例如cross_attn.k.bias和ffn.0.bias | merged中叶层bias有遍历路径（仍需shape/消费核对）；unmerged不查询bias patch，forward直接使用原bias（custom_linear.py:89–123、247–265），因此两专家的bias delta明确unsupported |
| diff_m | W:nodes_model_loading.py:130将`.diff_m`改为`.modulation.diff`；W:model_lora_keys_unet:644–645给非weight状态建原名映射；C:lora.load_lora再生成modulation的diff patch | 映射存在不等于应用。unmerged没有modulation参数查询。merged的utils.apply_lora:281–291只收集不存在额外递归参数的模块，block/head有自有modulation又有子层，会被skip；随后1732–1747的loader分支清空patches，sampler不能补应用。静态缺口，尚未做CPU执行复现 |

可定位的固定源码入口：

- [标准化与映射](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00/nodes_model_loading.py#L109)、[SetLoRAs](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00/nodes_model_loading.py#L742)、[loader合并分支](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00/nodes_model_loading.py#L1724)。
- [unmerged的实际参数选择](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00/custom_linear.py#L89)、[merged的实际遍历](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00/utils.py#L277)。
- [block自有modulation及子层](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00/wanvideo/modules/model.py#L936)、[head自有modulation及子层](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00/wanvideo/modules/model.py#L1537)。block形状`[1,6,dim]`，head形状`[1,2,dim]`，与high历史header示例和本轮base header相符。

不能以“没有NOT LOADED”作为通过：W:load_lora_for_models_mod:716–718对已解析却未加入的目标只警告；C:load_lora对未知输入也只警告；W:SetLoRAs:776–778会在base没有img目标时过滤img输入；blocks/layer_filter还能主动删项；standardize_lora_key_format用字典赋值，名称碰撞需后续检测。某些同目标adapter/diff可相互覆盖，需逐tensor核对，不能按成功日志或patches长度认证。本轮不运行这些函数。

## 两专家与 FP8 / base 约束

沿用已记录的官方1022 revision `57adea585d1d21085e2dfc91ce3c7b646cdd9345`，没有重下或重新全哈希LoRA。以下SHA是历史来源身份，非本轮新验真。

| 专家 | 字节数 / 历史SHA256 | 历史header分类与本轮适用结论 |
| --- | --- | --- |
| high | 634645944 / `887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19` | 1500 tensors = weight810 + diff_b447 + diff202 + diff_m41；41个modulation映射有源码，但两个应用分支均存在上述缺口；当前候选不能宣布完整支持 |
| low | 739472104 / `8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1` | 1749 tensors = weight974 + diff_b531 + diff244；没有diff_m也不能推定通过，unmerged仍遗漏bias/norm；merged叶层有路径，全部消费/shape/数值未验证 |

本轮只读现有两个base的有界header（各180728字节，加8字节长度）：均有1908个tensor、`scaled_fp8`标记、`.scale_weight/.scale_input`，关键结构为dim5120、40层对应的Wan形态、patch_embedding`[5120,36,1,2,2]`、block/head modulation；没有读取tensor payload或重哈希28.6GB模型。两个header SHA相同只证明header相同，不能证明high/low内容相同。W:loader:1180–1216、1240–1266、1301–1304、1593、1704–1708具有相应结构/scale检测和映射，**没有发现必须换Kijai重打包base的源码强制条件**，但仅header审查不能认证完整load，T5/VAE也未加载。未来如换base，须独立列身份/量化及质量对照，不归因纯后端。

FP8边界：

- W:WanVideoLoraSelect:383等tooltip声称scaled FP8不能merge，但loadmodel的可执行分支未据scaled强制关闭merge：1107–1110读选项，1732–1747确有merged代码。不能把tooltip当实际拒绝依据，也不能把“有merged分支”当已正确应用。
- W:loader:1753–1755及sampler:133–137明确拒绝`fp8_fast`/FP8 matmul与unmerged同时使用；关闭fast只绕过这个报错，不能补齐bias/modulation。
- merged会反量化scale、float32计算再按原dtype写回（utils:246–275），精度/重标定语义需CPU和完整模型验证。`low_mem_load`还有异常continue（utils:305–327），不能作为无遗漏保证。
- W:readme.md:11–23指出unmerged buffer随block swap迁移、可能增加VRAM；本轮没有驻留/offload/显存峰值实测。SDPA、不开compile、非fast可以避开可选加速依赖，但不解决上述权重完整性问题。

## 决定、解除条件与证据层次

**当前配置停止（source-level unsupported / 完整兼容证据不足）**。不把默认SetLoRAs unmerged切到merged当作已解决，不删41个diff_m、不忽略bias/norm、不换LoRA，不安装或先跑40步“试试看”。环境缺依赖是独立阻断，安装它们也不能修复应用路径。

若后续另行决定开展CPU负向复现，可复用固定源码，先用真实函数验证high modulation与low bias的遗漏，再核对全部目标/shape/dtype及两专家原子拒绝；这不是本轮已执行的CPU证据。解除当前门槛须有固定版本实际处理函数的完整mixed-delta消费/应用证据（含41个high modulation），以及具体隔离CPU环境方案；需要安装时先列命令/依赖/资源并获得该项授权，不能改生产。若更换Wrapper commit或修复其遍历逻辑，要重新固定并审查，不沿用本轮兼容判断。

按任务板Order选出的后继为LVA-07-02，观察为NOT_STARTED；其“前项支持进入CPU验证”的前提本轮未成立，因此保留原状态、Design document=None、Handoff=None，未编造实现就绪设计或部分交接。当前任务的完成不受此影响。没有CPU数值结果、完整模型consumed/applied计数、实际节点注册、GPU输出、人工质量结论或加速指标。

## 命令、验证与操作边界

已执行的主要取证：GitHub connector只读fetch固定commit及源码；固定SHA raw文本保存；`python.exe -I -S -c 'import sys; print(sys.version); print(sys.executable)'`；读取torch/version.py、comfyui_version.py及包METADATA/WHEEL；`git -C <ComfyUI> rev-parse HEAD`；`nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader`；stdlib collector并发读取PyPI JSON和两个有界base header；`rg`定向核对本机Comfy接口。实际命令与原始证据路径汇总见JSON。

仅执行专项要求的JSON解析、文档/固定源码引用与改动范围检查；不跑产品测试、媒体解码或GPU基准，不用关键字命中代替上述逐路径审查。验证的实际退出结果记录于JSON和任务板。

操作计数：**0安装、0wheel/模型下载、0节点导入、0服务启动、0生成POST、0GPU采样、0远程源码执行、0模型全量重哈希**。只有审查文档和任务板被本任务写入仓库；保留进入本轮前已有的总体设计、Wrapper设计、任务板及本项设计增量，不恢复暂停生产。
