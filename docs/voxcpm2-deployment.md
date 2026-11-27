# TTS-VOX-01 独立环境与模型部署

任务定义见 [接入设计 §9](voxcpm2-integration-design.md#9-实施任务)。本实验只部署官方 PyTorch 推理并验证 Windows / RTX 5090 D v2 真实生成；语音质量、六种情绪、长文案和 GPT-SoVITS 盲听属于 TTS-VOX-02。

## 固定版本与路径

- Python：3.12.10，独立 venv，`include-system-site-packages=false`。
- PyTorch / torchaudio：`2.9.1+cu128`，CUDA runtime 12.8；本机驱动 610.88。
- VoxCPM：官方提交 `300e4260b509066151d623dc9c0aa922cf82232b`，构建版本 `2.0.3.post46+g300e4260b`。
- 模型：`openbmb/VoxCPM2`，Hugging Face revision `7936080b41163874f38610f46f438e2c0757f9fd`。
- 大权重下载使用官方 `OpenBMB/VoxCPM2` ModelScope 镜像；下载后一次性核对 SHA256，与上述 HF revision 的 LFS SHA256 相同。生成过程不重算权重哈希。
- LM 使用 BF16，AudioVAE 沿用官方 FP32；`optimize=false`，避免 Windows 默认 `torch.compile` 的额外编译依赖。
- 生成参数、模型文件 SHA256 和源码版本保存在 [部署规格](../config/voxcpm2-deployment.json)。

目录均相对于 `VIDEO_AI_RUNTIME_ROOT`（本机 `E:/VideoAI`），继续使用既有 bootstrap 和 `VideoStorage`：

| 用途 | 相对路径 |
|---|---|
| 独立 Python 环境 | `shared/envs/voxcpm2` |
| 官方源码 | `shared/tools/VoxCPM` |
| 固定模型和 tokenizer | `shared/models/VoxCPM2` |
| 本次实验输出 | `scratch/benchmarks/TTS-VOX-01/<时间戳>/` |

## 复现部署

这是实验环境的手动部署记录，不接入生产安装器。先 dot-source 项目的环境初始化；不会修改现有 video-ai、ComfyUI 或 GPT-SoVITS 环境。

```powershell
. .\scripts\bootstrap.ps1
Initialize-VideoAiEnvironment 'voxcpm2-deploy'
$voxBasePython = Join-Path $VideoAiRuntimeRoot 'shared\tools\python312\python.exe'
$voxEnv = Join-Path $VideoAiRuntimeRoot 'shared\envs\voxcpm2'
$voxPython = Join-Path $voxEnv 'Scripts\python.exe'
$voxSource = Join-Path $VideoAiRuntimeRoot 'shared\tools\VoxCPM'
& $voxBasePython -m venv $voxEnv
& $voxPython -m pip install pip==26.3
& $voxPython -m pip install torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu128
# 复刻已验证环境时使用完整传递依赖冻结；首次探索安装使用 runtime-requirements。
& $voxPython -m pip install --no-deps -r config/voxcpm2-environment.lock.txt
git clone --no-checkout https://github.com/OpenBMB/VoxCPM.git $voxSource
git -C $voxSource checkout --detach 300e4260b509066151d623dc9c0aa922cf82232b
& $voxPython -m pip install --no-deps --no-build-isolation $voxSource
```

`voxcpm2-environment.lock.txt` 固定完整 CPU 依赖（包括构建工具）；torch/torchaudio 使用上面固定的 CUDA wheel，VoxCPM 单独从固定源码安装。上游包的完整 dependencies 还包含 Web UI、训练、ASR、文本归一化及降噪工具。本任务只安装真实验证所需的最小推理环境，用 `--no-deps` 安装官方包，因此完整包元数据的 `pip check` 不代表本最小环境的验收。不要直接升级或对本环境运行无约束的 `pip install voxcpm`。

下载模型可使用固定 HF revision（联网部署阶段）：

```powershell
& $voxPython -c "import os; from pathlib import Path; from huggingface_hub import snapshot_download; snapshot_download('openbmb/VoxCPM2', revision='7936080b41163874f38610f46f438e2c0757f9fd', local_dir=str(Path(os.environ['HF_HOME']).parent/'VoxCPM2'))"
```

本机权重实际来自官方 ModelScope 固定文件 revision：`audiovae.pth` 为 `ea02bd9a3599f1900705b80c8db371a72065dba2`，`model.safetensors` 为 `d5f1818d22a8a84a71ad99eed983cb786f33985f`。下载 URL 形式为 `https://modelscope.cn/models/OpenBMB/VoxCPM2/resolve/<revision>/<filename>`；两份权重 SHA256 分别为 `94b5d51e107e0507d4acc976cfdadb64edd6fd06d1f751dadbf2fd1594274bf1`、`f7f964cfa9da23653baec6e6f7750719977ad944ed9f95fe52fe3a620506891d`。其余配置及 tokenizer 从固定 HF revision 获取并与部署规格核对。

## 真实生成入口

```powershell
.\scripts\experiments\run_voxcpm2_smoke.ps1
# 可选：更换短文案；每次生成保存到新的实验目录。
.\scripts\experiments\run_voxcpm2_smoke.ps1 -Text '旅行者一号正在遥远的星际空间航行。'
```

可使用 `-Instruction '成年男性，沉稳自然，具有纪录片叙事感'`；`-ReferenceAudio PATH` 仅用于已有授权参考音频。本次部署样本采用自然语言声音设计，无外部参考录音。固定音色和可控克隆验收在 02 进行。

入口强制 CUDA，加载前设置 HF/Transformers 离线模式，模型只从本地目录加载。`cfg_value=2.0`、`inference_timesteps=10`、`seed=42`、`max_len=1024`；关闭归一化、降噪、内部重试及编译优化。`seed` 由锁定版本原生 API 支持，不声称跨设备逐字节一致。

每次保存 `sample.wav`、`result.json`、`environment.freeze.txt`。只检查输出数组有限且非空、单次 WAV 头及实际采样数，不执行 ASR、重复解码或生成期间权重哈希。报告包括模型加载和生成耗时、实际音频时长、RTF，以及本次实验的 PyTorch 峰值显存；生成进程退出即释放自身模型资源。

## 验收记录

**TTS-VOX-01 已完成（2026-11-24）**。用户明确要求完成本任务后，在 Windows 11 / RTX 5090 D v2（24GB，compute capability 12.0）上使用独立环境完成真实离线加载和中文生成，退出码为 0。

命令：`.\scripts\experiments\run_voxcpm2_smoke.ps1`。原始报告归档于 [TTS-VOX-01-result.json](research/TTS-VOX-01-result.json)；完整环境原始 freeze 与 WAV 位于 `E:/VideoAI/scratch/benchmarks/TTS-VOX-01/20261124-183516-213454/`。另在 `shared/config/tts/` 保存部署规格、原始 freeze 和结果副本。

| 实测项 | 结果 |
|---|---|
| 模型加载 | 9.442 秒，`cuda:0`，LM `torch.bfloat16` |
| 首次中文生成 | 8.363 秒，未 warm-up，未启用 compile |
| 输出 | PCM16 WAV，48000 Hz，单声道，430080 个采样点 |
| 音频时长 | 8.96 秒 |
| RTF | 0.933（生成耗时 / 音频时长） |
| 本进程 PyTorch 峰值显存 | allocated 5.38 GiB，reserved 5.65 GiB |
| 入口总耗时 | 30.576 秒，包含导入、加载、生成和记录，不含解释器退出 |

原文：“旅行者一号从地球出发，飞向遥远的星际空间。即使相隔数百亿公里，它仍在向我们传回宇宙的消息。”声音设计指令：“成年男性，沉稳自然，具有纪录片叙事感”。

官方代码直接支持 `seed`、`reference_wav_path`、括号内风格描述、`normalize`、`denoise` 和 `retry_badcase`，本次声音设计路径已真实执行。加载时上游会提示 tokenizer 声明为 `VoxCPM2Tokenizer`、实际加载类为 `LlamaTokenizerFast`，并有 Transformers cache / weight_norm 弃用提示；本任务保留官方代码，没有为消除提示修改 tokenizer 或模型。

版本冻结包括源码提交、模型 revision、部署时文件 SHA256、CUDA wheel 版本和全部已安装依赖。Torch wheel 一次性核对官方索引公布的 SHA256：`3a01f0b64c10a82d444d9fd06b3e8c567b1158b76b2764b8f51bfd8f535064b0`。生成脚本 Python 语法、PowerShell 入口语法通过；未改生产模块，因此没有运行完整视频或无关测试集。

RTF 0.933 是单个首次短样本结果，**未达到设计中的热推理目标 0.3，也不等于长文案基准**；该性能目标不是任务 01 的完成门槛。主观试听、漏读/重复/发音、固定音色、克隆和至少六种情绪仍标记为 `unverified_TTS-VOX-02`，不声称质量验收已通过。后续按设计先做 02 的真实对照验证，再决定是否正式接入；生产默认及既有 GPT-SoVITS/Wan/即梦链路保持原状。
