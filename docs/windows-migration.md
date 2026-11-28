# 迁移到另一台 Windows 电脑

默认运行根 `E:/VideoAI`；源码使用当前 checkout。迁移包携带当前源码（含未提交修改）、shared 下的工具/模型/环境/配置/资产，以及调度器和 Vox 环境所需的基础 Python。Vox 包括批准参考和完整样本、当前默认配方、官方固定源码和 FunASR 时间戳模型。离线恢复不需要全局 Git，也不重新下载模型。

```powershell
# 在源电脑导出到运行根和源码目录之外。
.\scripts\migrate_windows.ps1 -Mode Export -PackagePath 'F:/VideoAiTransfer'

# 需要历史续作时，包含 work、output、原有 shared 历史和工具输出。
.\scripts\migrate_windows.ps1 -Mode Export -PackagePath 'F:/VideoAiTransferWithHistory' -IncludeHistory

# 将整个包带到目标机，在目标机恢复；不立即制作视频。
F:/VideoAiTransfer/restore.cmd -NoLaunch
```

目标机需要 Windows x64、兼容 CUDA/BF16 的 NVIDIA 驱动及足够空间。首次导出会携带微软 VC++ x64 安装程序；目标机可能需要管理员安装或重启。即梦/TOS/SMTP 等在线服务仍需要有效账户和网络。

目标机可在启动恢复前设置 `$env:VIDEO_AI_RUNTIME_ROOT='F:/Video AI'`。恢复使用包中相对配置路径，修复调度器和 Vox venv 的基础解释器；按依赖优先、主配置最后的顺序重定位当前共享配置和默认配方。恢复 Vox 任务时验证批准配方、Vox CUDA/BF16 包、CPU 时间戳依赖和本地模型，成功才写 ready。没有 Vox 配置的旧包仍走原 GPT 兼容路径，恢复不会隐式更换音色。

历史任务的冻结配置、参考和音频不改写。**需要继续历史任务时，目标机须保留原运行根和源码的绝对路径**；更改运行根的验证仅覆盖共享依赖与之后的新任务，不能据此承诺旧冻结任务跨根续作。默认导出不带 work/output；需要它们时必须使用 `-IncludeHistory`。已经清理掉的历史过程数据不能恢复。

迁移包含私人配置与凭证，请通过可信存储传输。`-WithoutSecrets` 省略标准凭证导出；自定义文件中的秘密需要另行处理。凭证只加载到当前进程，不打印或写系统环境。

复制使用 Robocopy，保留时间戳、无 /MIR 或 /PURGE，不删除目标数据。推荐 NTFS 传输盘以容纳大型模型。导出前先停止制作，避免复制可变文件。未知已有安装默认拒绝；同包中断可重跑。明确使用 `-AllowExisting` 合并前需自行保留目标备份。

恢复只做启动检查，不执行模型推理或代填审核。已在本机带空格的新根通过隔离文件副本的真实 Vox/FunASR 启动验证；该证据不等于第二台机器完整视频验收。详见 [TTS-VOX-10 结果及用法](voxcpm2-installation.md)。
