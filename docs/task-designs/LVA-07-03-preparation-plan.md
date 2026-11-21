# LVA-07-03 环境与资源补充方案

2026-11-19。用户随后对本文具体四阶段清单回复“同意”，四阶段已实际完成；最新结果见 [执行报告](LVA-07-03-preparation-execution.md) 与 `LVA-07-03-preparation-execution.json`。LVA-07-04仍为NOT_STARTED；节点/服务/完整模型/GPU尚未运行。

以下正文保留**授权前的方案快照**，其中“本轮未执行”“尚待授权”等是当时状态，不代表最新执行状态。准备命令中的三处Git调用现已按实际发现加入局部LF配置，修正依据见执行报告；不会重复取得已获的同一授权。

## Goal

将源码、独立 CUDA runtime 和新增依赖的身份、实际字节预算、路径和命令固定下来，使下一次授权对应具体操作。完整模型实际应用与 40/4 步采样不是本轮环境准备的通过结果。

## Scope

计划只写入新目录 `E:/VideoAI/scratch/benchmarks/LVA-07-04-environment`。复用既有 Python 3.13.14 / torch 2.14.1+cu130 / CUDA 13.0 的独立文件副本，不对生产执行 pip，不重下 PyTorch，不复制或更换六个已有推理模型。完整 Wrapper 源码自带的 `fantasyportrait/models/face_landmark.onnx` 为 2,865,751 bytes，计入源码下载；不会加载该可选模型，不能将完整源码下载说成没有任何模型格式文件。

本轮只运行了元数据收集、runtime 二进制只读摘要、命令语法检查和 `--stage inspect`。安装及源码获取尚待本清单的具体授权，之后按四个阶段顺序执行；失败保留现场，不自动删除、重试或转用生产。

## Approach

建议先准备独立环境，再在该环境中完成节点接口和受限模型方案验证。现有 CUDA runtime 的 87 个分发保持原版本，固定补齐 15 个 wheel；无需重新解析/下载整个 CUDA PyTorch 栈。另一选择是继续完全只读直到完整模型方案也通过，这会推迟真实节点验证。这里的建议只针对环境准备，不提前改变完整投入决定。

### 固定来源与证据

- Wrapper 上游固定 `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`，完整递归 Git tree 非截断：241 blobs、47,250,651 bytes、无子模块/符号链接。逐文件 Git blob SHA1 见 `docs/task-designs/LVA-07-wrapper-tree.json`。这些是远端文件身份，不是已经获得完整本地 checkout。
- Comfy 固定 `2c75dc1b379a59e0880619d029607af5169a62ef`，本地 commit 可用；1332 个已跟踪文件共 49,602,446 bytes，观察时 tracked 工作区无修改。计划从该 commit 导出，不复制生产的 custom_nodes、模型、user、input、output 或未跟踪文件。
- 来源准备命令产生**完整固定源码快照**，不是带远端历史的 Git checkout。快照逐 blob 验真后，核对已有 18 份审查基线、应用固定 mixed-delta.patch 并复制三份修复/策略文件；最终文件 SHA256 写入新目录的 `sources.json`。不把 21 文件 CPU 副本的本地 commit 冒充完整快照 commit。
- Runtime 来源为 `E:/VideoAI/shared/tools/ComfyUI_windows_portable/python_embeded`；清单排除 `__pycache__` 与 `.pyc`，其余 45,784 文件共 4,157,540,147 bytes，无观察到的链接。381 个 exe/dll/pyd/zip 共 3,354,508,172 bytes 已只读计算 SHA256。其他文件记录 stat 与包 METADATA/RECORD 摘要，未宣称全部 payload 已哈希。
- 目标 `python313._pth` 显式绑定独立目录的 zip、解释器目录、site-packages 和相邻 ComfyUI；另一个 `.pth` 只包含 setuptools 的本地 `_distutils_hack`。不继承生产或用户 site 路径。
- 详细原始记录：`E:/VideoAI/scratch/benchmarks/LVA-07-03-planning/metadata.json`、`archive-binary-metadata.json`。内容 SHA256、收集器及命令文件摘要绑定在 `LVA-07-03-preparation-evidence.json`；未来来源变化必须刷新方案，不能套用旧身份继续。

### 依赖清单

| 新增 wheel | 固定版本 |
| --- | --- |
| accelerate | 1.16.0 |
| diffusers | 0.43.0 |
| peft | 0.21.3 |
| ftfy | 6.3.1 |
| gguf | 0.19.0 |
| protobuf | 7.36.2 |
| pyloudnorm | 0.2.0 |
| opencv-python | 5.1.0.95 |
| importlib-metadata | 10.2.0 |
| lazy-importer | 0.1.0 |
| wcwidth | 0.9.4 |
| zipp | 4.1.2 |
| comfyui-workflow-templates-media-image | 0.3.160 |
| comfyui-workflow-templates-media-other | 0.3.229 |
| comfyui-workflow-templates-media-video | 0.3.101 |

三个 media 包是当前 Comfy requirements 中固定模板包的实际传递依赖，不能把原先缺的八个 Wrapper 分发当完整新增数量。OpenCV 的本次选定值为 5.1.0.95；旧审查中 5.0.0.93 保留为历史索引候选。

`LVA-07-03-additional-wheels.lock` 固定 URL/SHA256；证据 JSON 包含各 wheel 的 tag、bytes、Requires-Python/Requires-Dist。按 Windows AMD64 / CPython 3.13.14 评估标记：Comfy+Wrapper 根依赖闭包 97 分发，未发现约束冲突；另五个已安装分发的活动依赖亦全部满足。拟安装结果为原 87 个版本加 15 个新版本，共 102 个分发。**这是元数据闭包核对，不是 pip resolver、真实 DLL/API、完整节点导入或 GPU 兼容通过。**

### 资源预算

| 项目 | 字节 / 预算 | 依据 |
| --- | ---: | --- |
| 新增 Wrapper 文件下载 | 47,250,651 | 完整固定 Git tree 的 blob size 合计 |
| 新增 wheel 下载 | 339,836,898 | 15 个已选 PyPI wheel 元数据 |
| 两者下载 payload 合计 | 387,087,549 | 约 369.16 MiB；不含 HTTP 头/协议开销 |
| 独立 runtime 文件副本 | 4,157,540,147 | 本次逐文件 stat，不含排除的缓存 |
| Comfy 本地源码导出 | 49,602,446 | 固定 commit 的 tracked blob size 合计 |
| wheel 解压内容 | 455,252,138 | HTTP206 ZIP central directory；不含生成的 entry point/RECORD/文件系统分配开销 |
| 计划磁盘预留 | 8,589,934,592 | 8 GiB：含上述持久内容、64 MiB Comfy tar、额外一份全部 wheel+解压内容的临时量、文件系统/日志余量 |
| 环境准备 RAM 规划预留 | 4,294,967,296 | 4 GiB 操作余量，非实测峰值；阶段不加载模型/节点 |
| 环境准备 GPU / VRAM 分配 | 0 | 只做文件操作和 pip 元数据检查，不导入 torch/节点、不启动服务 |
| 完整模型 RAM / VRAM 峰值 | null / null | 仍缺受限安装、forward/offload 实测；不能以预留量替代 |

本次容量观察 `2026-11-19`：物理 RAM 33,346,146,304 bytes，可用 RAM 16,994,021,376 bytes，E 盘空闲 1,421,776,560,128 bytes；时点容量不是资源预留。命令执行前再检查 E 盘至少 8 GiB 可用。已有六个推理模型共 36,953,325,927 bytes，只读复用，不计为新下载或副本；没有选择 W3/BF16 替代品。

### 四个具体阶段（本轮均未执行）

命令文件为 `docs/task-designs/LVA-07-03-prepare-environment.py`。所有阶段默认不运行；不带 stage 或显式 `inspect` 只读打印已绑定清单。其余命令只有获得本清单的具体授权后执行：

```powershell
& .tools/python/python.exe -I docs/task-designs/LVA-07-03-prepare-environment.py --stage sources
& .tools/python/python.exe -I docs/task-designs/LVA-07-03-prepare-environment.py --stage runtime
& .tools/python/python.exe -I docs/task-designs/LVA-07-03-prepare-environment.py --stage wheels
& .tools/python/python.exe -I docs/task-designs/LVA-07-03-prepare-environment.py --stage install
```

1. `sources`：新建指定 root；本地导出固定 Comfy commit；读取固定 Wrapper 241 个文件，逐一检查大小和 Git blob SHA1；核对审查基线并应用既有补丁/策略，落盘完整修复后源码清单。拒绝已有 root；不执行远端源码。
2. `runtime`：只读复制清单中的 45,784 个文件，核对源 stat 未漂移；目标 381 个二进制与事先 SHA256 一致后，绑定独立 `_pth` 并落盘副本证据。
3. `wheels`：只取得所列 15 份 wheel，逐一核对 bytes/SHA256。生成 `name==version --hash=...` 的**本地安装锁**，供离线安装；不让带 URL 的锁在安装阶段再次联网。
4. `install`：仅对独立 runtime 执行 `pip install --no-index --no-deps --no-compile --require-hashes --no-cache-dir`；随后 `pip check`，核对 87 个旧版本及 15 个新版本。失败保留现场，不启动模型/节点；成功也只记环境安装通过。

这四步的 source/runtime/wheel/install 标记是各自实际执行后产生的证据，当前均不存在。入口没有视频提交、服务启动或旧 run 修改功能。A4 节点探测和 A5 完整准入/GPU 命令仍未准备，不能在安装成功后自动接续。

## Files

本补充新增完整上游 tree、15 wheel 锁、准备命令、证据 JSON 和本文；更新现有 environment manifest、investment decision、本项设计和任务板的补充事实。没有实现 `wan_wrapper_backend` 或改写生产模块，也没有为 LVA-07-04 写部分 next-task 交接。

## Tests

实际只验证补充交付的语法、只读入口、元数据闭包、来源摘要及 MD/JSON 一致性：

```powershell
& .tools/python/python.exe -I docs/task-designs/LVA-07-03-prepare-environment.py --stage inspect
& .tools/python/python.exe -I -m json.tool docs/task-designs/LVA-07-03-preparation-evidence.json > $null
& .tools/python/python.exe -I -m json.tool docs/task-designs/LVA-07-environment-manifest.json > $null
git diff --check
```

验证器和实际结果见 `E:/VideoAI/scratch/benchmarks/LVA-07-03-planning/verify_supplement.py` 与 `verification.json`。没有产品代码改动，不重复 CPU payload、历史 benchmark、视频解码或全模型哈希。

## Acceptance

环境准备动作具备固定来源/版本/字节/SHA、独立路径、可直接调用的命令、磁盘预留和失败规则；安装授权可据此具体审阅。本次没有授权就绪的完整 LVA-07-04 实施设计，不将环境计划当实际安装或完整模型证明。

## Risks

U1/U2 的**环境获取/复制/安装方案**已具体化，实际完整源码准入、导入/注册尚待执行。U3～U6 继续保留：

- CPU helper 同时保有原始、base clone 和 private clone，即三份双专家。仅 base 文件代理为 85,768,456,992 bytes，约 79.88 GiB，还未含 LoRA/临时 buffer；禁止对 14B 调用此 helper 或抬高 256 MiB 上限。
- 可进一步设计“单专家私有构建、释放后处理另一侧、双侧证据齐全才发布 pair 描述符”的路径；必须明确采样时真正的单专家驻留与 T5/VAE 释放，不能把逻辑 pair 描述符当两个模型已同时准入。目前这只是待设计方向，未通过资源/实现验证。
- `nodes_model_loading.py` 的普通 scaled-FP8 路径保留 `patcher.model['sd']`；sampler 入口会重新 `load_weights`，之后安装动态 patch。CPU helper 的静态增量没有自动接入此时序。简单在 sampler 前先应用静态增量，可能被重新加载的原权重覆盖；既有 legacy guard 也会明确拒绝混合静态增量。后续设计必须验证一次静态安装如何跨 reload/offload 保持，不能删 guard 让旧入口继续。
- compute dtype、swap/prefetch 和真实 scale/forward、准确 scheduler/sigma/split、完整模型精确 Low290 对账仍未完成，不能虚填峰值或已应用计数。
- 因此完整决定仍为 `insufficient_evidence`；建议只批准上述环境准备。没有将 LVA-07-04 改为 READY，也没有准备采样任务。

本轮取证脚本首版错误使用 65,557 字节尾部区间，对五个更小 wheel 的计划区间覆盖整个文件，合计上限 112,970 bytes；这些响应只在内存中使用，未保存、安装或执行，失败批次未保存逐请求回执，实际完整响应数不伪造为精确值。后续改为只取末尾 22 字节 EOCD 与有界 central directory，成功批次 30 次 HTTP206、227,053 bytes，完整 wheel payload 为零。首版 ZIP 字段下标、以及误把读取引起的 atime 变化当内容漂移的本地检查亦已修正；不影响生产或既有模型。
