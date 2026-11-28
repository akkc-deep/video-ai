# TTS-VOX-10 安装、迁移和默认切换

2026-11-28 完成。新视频固定使用 `provided-reference-narration-v1` 及旅行者2号完整重配音批准配方。参考续读、seed=42/cfg=2/steps=20、.95 变速、500ms 静音补足、-23dBFS 全篇 RMS 和固定可丢弃引导语均保持；历史冻结850ms任务保持自己的配方。

## 已部署机器

```powershell
# 检查已部署环境，不切换配置、不推理、不重哈希模型。
.\scripts\install_voxcpm2.ps1 -VerifyOnly

# 复用离线依赖，必要时从仓库批准副本显式升级默认配方并激活。
# 部署验收时一次性核对模型文件；生成过程不增加检查。
.\scripts\install_voxcpm2.ps1 -Offline

# 联网补齐专用环境和模型，导入原有批准资产目录。
.\scripts\install_voxcpm2.ps1 -VoiceAssets 'F:/provided-reference-narration-v1'

# 只部署检查，保留正式配置当前后端。
.\scripts\install_voxcpm2.ps1 -Offline -NoActivate
```

该入口依赖已安装的调度器 Python、FFmpeg 和原 GPT 工具环境（供 CPU 时间戳使用）。全新电脑使用 [联网安装入口](windows-online-install.md)。联网安装需要 Git for Windows；Vox 推理和离线迁移只读取固定 detached HEAD，无全局 Git 依赖。源/环境归属不明且版本不符时停止，不覆盖或无约束升级。

资产缺失或冲突会明确停止，不重新设计声音。`-NoActivate` 仍可显式安装/升级共享默认配方；已有正式配置中的内联配方与冻结任务不改变。模型 SHA256 仅部署验收使用；`-VerifyOnly` 检查文件存在、包启动、参考和配置身份。

## 切换与回退

```powershell
$videoPython = 'E:/VideoAI/shared/envs/video-ai/Scripts/python.exe'
& $videoPython -B scripts/configure_approved_narration.py --config E:/VideoAI/shared/config/production.json

# 使用命令实际打印的备份名；占位符需替换。
& $videoPython -B scripts/configure_approved_narration.py --config E:/VideoAI/shared/config/production.json --restore-backup E:/VideoAI/shared/config/production.before-vox10-<timestamp-id>.json
```

切换先核对批准声学身份、运行依赖和配置，再保存原始字节备份并原子替换。重复执行相同配置不新增备份。恢复只接受显式选择的同目录 before-vox 备份，先备份当前配置，再按原始字节恢复。回退可以恢复原后端，但必须由操作者显式执行；Vox 失败不自动退回旧声音。配置操作影响后续新任务，已有任务继续使用其冻结输入；历史视频换旁白应新建 revision。

## 验证记录

- 安装/迁移针对性测试：32 passed，涵盖批准资产、升级备份、缺依赖拒绝激活、候选发布、精确回退、中断恢复、带空格重定位与历史不变。
- 扩展回归：136 passed / 3 skipped / 5 failed。3项因本机缺符号链接权限跳过；5项均为既有 production_speech 字体夹具失败，与07记录相同。完整名称和日志见结果JSON；不声称全套通过。
- 当前机器执行 `install_voxcpm2.ps1 -Offline` 成功，固定模型一次性 SHA256 通过，重复激活 `Backup: None`。
- 独立迁移副本位于带空格的新根，实际复制可变配置、硬链接不可变依赖，修复 venv 后 Vox CUDA/BF16 与 FunASR 导入均成功；没有复制或重写历史视频。
- 正式语音函数实际生成两段、430060个正文采样点 / 8.959583秒，6个原文单元；测量正文边界并生成时间轴，完成恢复仍只有2个请求。
- 独立副本执行真实配置切换、重复激活和回退，原始字节相等；当前正式配置保持批准默认。
- 独立审查提出的提前覆盖配置、全局Git依赖、独立激活漏检查、源码/venv中断、浅取源码版本与迁移发布顺序均已修正。

复现命令：

```powershell
& $videoPython -B scripts/experiments/voxcpm2_migration_smoke.py
& $videoPython -B scripts/experiments/voxcpm2_production_smoke.py --task-id TTS-VOX-10
```

[完整结果](research/TTS-VOX-10-result.json)、[语音结果](research/TTS-VOX-10-speech-result.json)、[迁移结果](research/TTS-VOX-10-migration-result.json)、[回退结果](research/TTS-VOX-10-rollback-result.json)、[设计](task-designs/TTS-VOX-10-design.md)。本任务没有第二台全新机器完整下载与视频推理结论，没有新增主观试听结论，也不补记 TTS-VOX-08 完整视觉验收。
