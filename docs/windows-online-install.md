# Windows 联网安装

新电脑需要 Windows 10/11 x64、兼容 CUDA 12.8 / BF16 的 NVIDIA 显卡与驱动、Git for Windows（安装后重新打开 PowerShell），以及足够容纳工具、模型和生成数据的磁盘空间。默认运行根 `E:/VideoAI`，可用 `VIDEO_AI_RUNTIME_ROOT` 指向其他本地目录，包括带空格路径。

使用包含 TTS-VOX-10 的当前完整源码。声音固定为用户批准的 `provided-reference-narration-v1`：从原运行根复制 `shared/assets/voices/provided-reference-narration-v1` 目录，必须带 `voice.json`、`reference.wav` 和 `approved-production-20261128.wav`。工具和模型联网下载，私人声音资产不能从公共模型仓库重新设计或替代。

```powershell
# 在当前源码根运行；仅安装，不启动视频。
.\install_online.cmd -VoiceAssets 'F:/approved-voice/provided-reference-narration-v1' -NoLaunch

# 可更换运行根和 HF 下载站点。
$env:VIDEO_AI_RUNTIME_ROOT = 'F:/Video AI'
.\install_online.cmd -VoiceAssets 'F:/approved-voice/provided-reference-narration-v1' -HfEndpoint https://huggingface.co -NoLaunch
```

也可执行 `scripts/install_local.ps1 -VoiceAssets ...`，使用当前源码直接安装。单独下载的安装脚本必须通过 `-SourceRef` 指定实际包含本次代码的固定 GitHub 提交；尚未上传的代码不会自动出现在远端。推荐直接携带当前源码。`install_windows.ps1` 只安装调度器开发环境，不承担模型部署。

安装保留现有下载器：HTTPS、`.part` 续传、完成回执和固定版本。未知已有工具目录拒绝覆盖；Vox 安装器记录自有源码/环境的 installing 状态，创建中断后可重跑。已通过完整依赖版本检查的 Vox 环境直接复用。缺少 Git、批准参考不匹配会在大型下载前停止。

| 内容 | 来源与固定版本 |
| --- | --- |
| Python | python.org 3.12.10 x64，运行根 shared/tools/python312 |
| VC++、字体 | 微软运行库、Windows Update 简体中文字体组件 |
| 解压、ComfyUI | 7zip 26.05、ComfyUI v0.44.0 NVIDIA Windows 便携包 |
| VoxCPM2 | 官方源码 `300e4260b509066151d623dc9c0aa922cf82232b`，保留 tags/history 复现包版本 |
| Vox 模型 | openbmb/VoxCPM2 revision `7936080b41163874f38610f46f438e2c0757f9fd` |
| Vox 环境 | 独立 venv、torch/torchaudio 2.9.1+cu128、仓库完整依赖锁；不启用编译或候选加速 |
| CPU 对齐、旧任务兼容 | GPT-SoVITS 工具环境；FunASR 1.0.27；timestamp 模型 v2.0.4，固定文件身份见 config/voxcpm2-alignment.json |
| 视觉及合成 | 既有固定 Wan 2.2 I2V/UMT5/VAE、SDXL、RealESRGAN_x4plus、FFmpeg 9.0.2 |
| 规划 | Ollama v0.40.14，qwen3:8b |
| 音色 | 导入已批准的私人资产，绝不选公共示例音色 |

配置先写入 `shared/config/production.pending-vox10.json`。Vox/CPU 对齐依赖、本地模型与批准资产验证通过后，才备份旧正式配置并原子发布 `production.json`。旧 voice.json 和已有 tts-api.yaml 保留；兼容元数据另存 voice.vox10.json。失败不发布候选，不静默改用旧声音。安装完成记录仍标记 `inference_verified=false`；不把环境可启动当成整片验收。

默认配置使用即梦候选图与既有视频链路；即梦/TOS/SMTP 凭证及参考能力需另行配置。安装器不补写视觉资格或审核结论。日常生成使用 `generate_video.cmd`，无需再选声音。

已部署机器只补齐或迁移 Vox 依赖、默认切换与回退的命令见 [Vox 安装迁移说明](voxcpm2-installation.md)。离线搬运见 [迁移说明](windows-migration.md)。目前没有第二台干净机器从零下载全部视觉模型的验证结论。
