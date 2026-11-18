# LVA-07-02 隔离 CPU 原提案与执行记录

2026-11-17原提案，2026-11-18更新执行记录。用途是固定 Wrapper 的最小 CPU **负向复现**，先验证 high modulation / low bias 遗漏；不是已验证的完整节点运行环境。不得将这份清单视为兼容通过或完整任务完成。

## 2026-11-18授权后执行更新

用户已针对本提案回复“同意下載吧”，具体下载/安装和CPU复现授权已取得。32个固定wheel共154334412 bytes已下载并离线安装，32/32版本及安装归档hash与原锁一致，pip check通过。Python安装器合并执行命令被自动审批在执行前拒绝，工具仅返回blocked by policy，未给详细原因；没有下载或运行安装器。

实际采用更小副作用的portable隔离：从既有Python3.13.14复制31个解释器文件（20652143 bytes）到 `E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/runtime/`；仅设置scratch/runtime、stdlib zip和独立cpu-site的_pth，不复制生产_pth或site-packages。由现有pip的 `--python <scratch/runtime/python.exe>` 以 `--no-index --find-links <scratch/wheels> --require-hashes --target <scratch/cpu-site>` 安装同32个wheel。**实际不是venv**，没有系统登记/安装器/PATH改动。源清单、离线锁、pip报告及命令日志在同scratch目录，实际环境身份见 `LVA-07-02-results.json`。

检查得到torch2.14.1+cpu、torch.version.cuda=None，sys.path仅包含新scratch位置，未import Comfy。完整真实custom_linear/gguf_utils首批测试已执行；两批相同4例（复核dtype说明后重跑），均1对照通过、3遗漏失败、0运行错误。设计停止条件已触发；当前阻断是实际应用遗漏，已不是等待授权。以下未执行/待授权表述均指2026-11-17的原始提案和其中的安装器命令，不代表最新状态。

## 输入和导入边界

- Wrapper：`a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`；复用 `E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit/` 的原始源码快照，不安装 custom_nodes，不修改快照。
- Comfy：`2c75dc1b379a59e0880619d029607af5169a62ef`。本阶段不导入 Comfy 的顶层节点或服务；其路径仅为只读源码输入。
- High LoRA：634645944 bytes，历史 SHA256 `887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19`。
- Low LoRA：739472104 bytes，历史 SHA256 `8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1`。
- 两文件均在 `E:/VideoAI/shared/models/comfyui/loras/`，完整文件名见本项既有设计和 LVA-04 记录。复用历史身份，不重新全哈希、不下载模型；初始小张量负向复现不需要读取这些文件的完整 payload。

最小真实模块图为 `custom_linear.py → torch / accelerate.init_empty_weights / .gguf.gguf_utils → gguf / torch`。生产 site-packages 中未发现 accelerate、gguf 的安装元数据；这是静态阻断，尚未执行 import，不能冒称已捕获运行时 ImportError。新环境使用 CPU torch，同一 2.14.1 发布系列并不证明其与生产 CUDA 构建行为完全等价。

获准后，以仅设置 `__path__` 的 namespace package 定位固定快照，完整执行 `gguf/gguf_utils.py` 与 `custom_linear.py`，保留其真实强制导入、custom-op 注册和函数体。namespace 只避免进入无关的节点注册 `__init__.py`，不能替换 accelerate、gguf 或任何 patch 算法。记录模块 SHA、加载路径及 thin-shim 边界；自定义 op 若不支持 CPU，直接报告失败，不 mock CUDA 实现。

先运行 high block/head modulation 和 low linear bias 的 RED 用例，另用普通 weight delta 作对照；实际调用 `set_lora_params`、`CustomLinear.forward`，对输入模型副本和独立数学预期作比较。小张量参数维度与完整模型不同，不能认领 3249 个输入已消费/应用。出现设计定义的遗漏即停止并记录负面结果，再据实际证据写最小修复设计；本任务不改上游源码。

更完整的真实 `nodes_model_loading.py` 和 `utils.py` 模块导入还有另一闭包：`utils → comfy.model_patcher/lora/model_management/clip_vision`，`nodes_model_loading → utils / wanvideo.modules.model/t5/clip / wan_video_vae / folder_paths / comfy.sd/model_base`。其中包含图像、文本和量化传递依赖；现有18份源码快照也不是完整 checkout。**本阶段32-wheel锁不覆盖这一闭包**，不得以此宣称 merged / loader / key mapping / FP8 / 两专家原子性已验证。若第一阶段没有触发停止条件，必须先完成这部分闭包取证和具体授权，再扩展；不得静默装全套节点、删强制导入或用 mocks 冒充通过。

## 固定下载清单和资源

精确32项 wheel 的版本、文件名、URL、SHA256、字节数和目标标签均见 `LVA-07-02-results.json` 的 `environment_proposal.packages`，可执行哈希锁为 `LVA-07-02-cpu-requirements.lock`。全部 active Requires-Dist 约束在 Windows AMD64 / CPython 3.13.14 目标上成立，wheel 标签匹配 cp313 或兼容 abi3 / pure Python；这是索引元数据闭包检查，不是 pip dry-run、DLL 导入或运行兼容证明。

| 项目 | 精确对象 | 下载字节 |
| --- | --- | ---: |
| Python | 官方 `python-3.13.14-amd64.exe` | 29225624 |
| torch | 官方 CPU `torch-2.14.1+cpu-cp313-cp313-win_amd64.whl` | 123995848 |
| 其余31 wheels | 包括 accelerate1.16.0、gguf0.19.0、numpy2.5.4 及其传递依赖 | 30338564 |
| 合计 | Python + 32 wheels | 183560036 |

Python 安装器 SHA256：`c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0`，来自官方 `.sigstore` 的 messageDigest；本轮没有下载安装器，也没有验证 Sigstore 签名或二进制。torch wheel SHA256：`4eec5a4fadd7a18f9c75b97fdb374fbb579ce4b1604bf66eeb14dc2201d54def`，来自官方 CPU 索引。本轮读取 PyPI JSON、PEP658 `.metadata`、Sigstore 元数据和 HTTP HEAD，不取 wheel/安装器 payload。

预计下载约175.06 MiB；为解释器、venv、解包和证据预留 **2 GiB磁盘、2 GiB RAM**。这是小张量阶段的保守预算而非实测峰值；不加载两个14B模型，GPU/VRAM预算为0。pip采用无缓存安装；不升级生产 torch、CUDA、Python，不挂载生产 site-packages。安装器禁用PATH、快捷方式、关联和launcher；其正常的当前用户安装登记仍属于本次待授权安装。

## 原提案的具体命令（保留审阅历史，安装器路径未执行）

以下为当时提交审阅的原命令，**该合并安装器方案未执行**。2026-11-18的实际portable方案见本页执行更新及结果报告；不要在已建立的目标上重跑以下初始化命令。工作目录 `E:/code/py/video-ai`，不覆盖或删除已有目标。

```powershell
$cpuRoot = 'E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu'
if (Test-Path -LiteralPath $cpuRoot) { throw 'CPU target already exists; inspect before proceeding' }
New-Item -ItemType Directory -Path $cpuRoot | Out-Null
$installer = Join-Path $cpuRoot 'python-3.13.14-amd64.exe'
Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.14/python-3.13.14-amd64.exe' -OutFile $installer
if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0') { throw 'Installer SHA mismatch' }
$pythonRoot = Join-Path $cpuRoot 'python'
$installArgs = @('/quiet', 'InstallAllUsers=0', "TargetDir=$pythonRoot", 'Include_launcher=0', 'InstallLauncherAllUsers=0', 'Include_test=0', 'Include_doc=0', 'Include_tcltk=0', 'Include_pip=1', 'PrependPath=0', 'Shortcuts=0', 'AssociateFiles=0')
$installProcess = Start-Process -FilePath $installer -ArgumentList $installArgs -WindowStyle Hidden -Wait -PassThru
if ($installProcess.ExitCode -ne 0) { throw "Installer exit $($installProcess.ExitCode)" }
& "$pythonRoot/python.exe" -I -m venv "$cpuRoot/venv"
if ($LASTEXITCODE -ne 0) { throw 'venv failed' }
& "$cpuRoot/venv/Scripts/python.exe" -I -m pip --isolated install --no-cache-dir --only-binary=:all: --require-hashes -r 'E:/code/py/video-ai/docs/task-designs/LVA-07-02-cpu-requirements.lock'
if ($LASTEXITCODE -ne 0) { throw 'CPU dependency installation failed' }
& "$cpuRoot/venv/Scripts/python.exe" -I -m pip check
if ($LASTEXITCODE -ne 0) { throw 'CPU dependency check failed' }
```

获准后才创建本项 CPU harness/tests，在独立子进程设置 `CUDA_VISIBLE_DEVICES=''`、禁用 bytecode 写回，并首先断言 torch版本为2.14.1+cpu、`torch.version.cuda is None` 和所有 fixture tensor.device.type 为 cpu。执行 `--help`、创建venv或pip安装成功都不代表实际数值测试通过。先复现负面用例，再依据结果决定停止或继续既有设计，禁止把这份第一阶段清单扩为GPU/服务/生产授权。

## 本轮取证与剩余工作

元数据 collector：`E:/VideoAI/scratch/benchmarks/LVA-07-02-dependency-audit/collect_dependencies.py`；原始证据同目录 `metadata-evidence.json`。执行命令：`.tools/python/python.exe -I E:/VideoAI/scratch/benchmarks/LVA-07-02-dependency-audit/collect_dependencies.py`，exit0，32项、全部活动依赖约束和目标wheel标签通过；0安装/下载wheel/目标import/CPU数值/GPU/服务。

2026-11-17当时尚未安装或运行CPU，collector零操作为该次元数据阶段的历史结果。2026-11-18具体授权已取得，实际下载/安装/CPU复现和修复设计已交付，见本页开头及结果报告。当前仍未完成全部验收：真实unmerged应用层已复现遗漏，按设计停止；逐tensor完整轨迹、merged/FP8和两专家原子性仍未验证，不准备 LVA-07-03，不重复索取已有授权。
