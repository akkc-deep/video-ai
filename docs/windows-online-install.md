# 全部联网下载，一键安装

新电脑准备 Windows 10/11 x64、本地 D: 盘和已安装兼容驱动的 NVIDIA 显卡。建议 D: 盘至少有 150GB 可用空间，实际生成还需额外空间。脚本会检查 `nvidia-smi`，具体 CUDA 兼容性在工具安装后检查。

从本项目下载源码后，双击根目录 `install_online.cmd`。也可以只下载单个 `scripts/install_online.ps1`，在 PowerShell 中执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_online.ps1
```

脚本自带全部下载地址，不依赖旧电脑的文件。安装成功后会要求输入文案或 UTF-8 文案文件路径，并调用项目的 `make-video`。以后双击 `D:\VideoSi\projects\video-ai\generate_video.cmd` 即可进入生成。模型和工具下载较大，首次安装可能持续数小时；下载中断后重新执行同一命令，继续已有 `.part` 文件，已完成下载按记录复用。若指定来源不支持 Range 续传，curl 会报错并保留文件，此时检查来源或删除对应 `.part` 后重新下载。

部分系统组件安装会弹出 Windows 管理员授权。如果系统要求重启，脚本会停止；重启后再次执行即可。脚本不修改显卡驱动，也不重启电脑。GitHub/Hugging Face 需要可达；curl 使用当前系统提供给进程的代理环境变量。

## 在线安装内容

| 内容 | 下载来源与版本 |
| --- | --- |
| 项目源码 | GitHub `akkc-deep/video-ai`，默认固定公开提交 `242f8a05f2ac69bb3ec3aa6d79c9a3257f1760b3` |
| Python | python.org，3.12.10 x64，安装到 D 盘并创建独立调度虚拟环境 |
| 运行库、中文字体 | 微软 VC++ 官方安装程序；缺少微软雅黑时从 Windows Update 安装简体中文字体组件 |
| 解压工具 | 官方 `ip7z/7zip` 26.05 便携程序 |
| ComfyUI | 官方 `Comfy-Org/ComfyUI` v0.44.0 NVIDIA Windows 便携包 |
| 配音环境 | `lj1995/GPT-SoVITS-windows-package` 的 `GPT-SoVITS-v2pro-20250604-nvidia50.7z`，固定仓库修订 |
| 配音模型 | `lj1995/GPT-SoVITS` v2 GPT/SoVITS、中文 RoBERTa 和 HuBERT，固定仓库修订 |
| 本地图片 | `stabilityai/stable-diffusion-xl-base-1.0` 的 SDXL 基础模型，固定仓库修订 |
| 本地视频 | `Comfy-Org/Wan_2.2_ComfyUI_Repackaged` 的 Wan 2.2 I2V 14B 高/低噪声 FP8、UMT5 和 Wan VAE，固定仓库修订 |
| 超分、合成 | 官方 RealESRGAN_x4plus、Gyan FFmpeg 9.0.2 |
| 文案和分镜模型 | 官方 Ollama v0.40.14，随后 `ollama pull qwen3:8b` |
| 参考音频 | 公开 `QwenAudio/CosyVoice` 示例 `asset/zero_shot_prompt.wav`，固定公开提交；参考转写为“希望你以后能够做的比我还好呦。” |

所有软件、权重和参考音频都在新电脑在线获取。源码 ZIP 解压、下载文件安装和写入新配置属于本机安装操作，不是从旧电脑拷贝。字体作为 Windows 组件使用系统安装路径。模型默认通过 `https://hf-mirror.com` 下载，可改为官方 `https://huggingface.co`。公开样例声音不是旧电脑的私人音色，使用时请遵守样例及各模型的使用条款。

## 可选参数

```powershell
# 使用 Hugging Face 官方站点，并只安装，不进入生成。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_online.ps1 -HfEndpoint https://huggingface.co -NoLaunch

# 安装后立即使用指定文案文件。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_online.ps1 -Script D:\my-script.txt

# 自己的公开/授权 HTTPS 参考音频，需要提供准确转写。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_online.ps1 -ReferenceAudioUrl https://example.com/reference.wav -ReferenceText '对应音频中的准确原文'

# 选择 GitHub 上已有的其他提交或分支。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_online.ps1 -SourceRef main
```

默认安装项目已有的本地 SDXL → Wan 制作流程，不需要即梦账号、TOS 或 SMTP 密钥。配音固定 GPT-SoVITS v2/CPU/非半精度，保持项目当前要求。原有起始图审核和后续生成行为保留；安装完成不是自动跳过审核生成正式影片。依赖历史本机资格资料的实验/原生时间扩展路线不属于这个全公开的新装配置。

源码只能下载 GitHub 上已有的版本。本机尚未提交或尚未上传的代码、私人参考音频和运行记录不会自动出现在网上。这里生成的联网安装脚本也只有上传到仓库后，才会出现在该仓库的下载 ZIP 中；上传前可直接下载本次提供的单个脚本运行。

安装不会覆盖未知已有工具目录或已有生产配置。请用于新的目标电脑；中断的同版本安装可以重复执行。若需要重装其他版本，应先处理相应旧安装，脚本不会替你删除。

开发验证仅检查脚本、下载状态处理、配置生成和小文件；没有在第二台电脑完整下载几十 GB 模型并进行真实视频推理。脚本安装时仅检查 CUDA、包启动及配置，不反复哈希大型模型，也不运行耗时的生成样片。
