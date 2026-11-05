# 一键迁移到另一台 Windows 电脑

新视频按简单编号管理，续作可用 `generate_video.cmd -Video 0001`。迁移历史时须一并携带 productions、storage 索引及正式 output；disposable 为可清理生成物，不是公共模型或 Python 环境。旧 run 保持原冻结路径，不因目录新规划自动搬动。生成完成后的 close/clean 用法见 [项目说明](../README.md#视频目录与过程数据清理)。

如需所有资源都从网上下载，请使用 [联网安装脚本](../scripts/install_online.ps1) 和 [联网安装说明](windows-online-install.md)。以下是可选的旧电脑离线拷贝方式。

旧电脑双击项目根目录的 `export_migration.cmd`。默认生成 `D:\VideoAiMigration-日期时间` 文件夹。把**整个文件夹**复制到移动硬盘或目标电脑，再在新电脑双击其中的 `restore.cmd`。恢复成功后直接进入生成入口，输入文案或 UTF-8 文案文件路径，即调用现有 `make-video` 开始制作。以后双击 `D:\code\py\video-ai\generate_video.cmd` 即可生成。

目标电脑需要 Windows x64、本地 D: 盘、足够容纳整套模型和生成产物的空间，以及与当前 PyTorch/CUDA 兼容的 NVIDIA 显卡和驱动。导出时会从微软官方下载并携带 Visual C++ x64 运行库安装程序；新电脑缺少运行库时自动安装，Windows 可能弹出管理员授权。首次导出需要联网下载此安装程序。模型和 Python 无需重新联网下载；即梦出图、TOS、SMTP 等在线服务仍需网络、有效凭证和可用账户。GPU 型号、显存不足或驱动不兼容，无法通过文件迁移解决。没有 D: 盘时，本脚本会明确停止，因为项目当前在代码里固定了 D: 路径。

迁移包携带当前工作目录中的源码（包括尚未提交的修改）、`D:\VideoSi` 下的工具、模型、调度虚拟环境、项目配置和素材，并携带虚拟环境对应的基础 Python 3.12。恢复后固定写入 `D:\VideoSi` 和 `D:\code\py\video-ai`，修复 Python 对旧电脑用户目录的引用。额外的项目资源、native 视频资格资料，以及代码仍会读取的固定模型验收记录和关联源运行也会保留；普通运行目录、productions、历史正式成片、ComfyUI 输出和临时缓存默认不迁移。

**迁移包含私人配置与凭证，请只通过可信存储传输。** 脚本将配置引用的凭证环境变量及已有本地凭证合并到 `migration-secrets.local.json`，生成入口仅加载到当前进程，不打印凭证，也不写入系统环境。使用 `-WithoutSecrets` 可以省略标准本地凭证文件和凭证导出；自定义文件中的秘密需由你另外处理，并在新电脑配置相应环境变量。

可选命令：

```powershell
# 自选导出位置，例如直接写入移动硬盘。保留现有实际配置路径。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\migrate_windows.ps1 -Mode Export -PackagePath E:\VideoAiTransfer -Config D:\VideoSi\projects\video-ai\config\jimeng-acceptance-14b.json

# 同时迁移历史 runs、productions、正式成片和工具输出。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\migrate_windows.ps1 -Mode Export -PackagePath E:\VideoAiTransfer -IncludeHistory

# 新电脑恢复后立即使用指定文案；不传文案则交互输入。
E:\VideoAiTransfer\restore.cmd -Script E:\my-script.txt

# 只恢复环境，不进入生成入口。
E:\VideoAiTransfer\restore.cmd -NoLaunch

# 日后直接生成，也可以使用 -Text '你的文案'。
D:\code\py\video-ai\generate_video.cmd -Config D:\VideoSi\projects\video-ai\config\production.json -Script D:\VideoSi\projects\video-ai\inputs\my-script.txt
```

复制使用 Robocopy，不删除目标文件，不对模型反复计算哈希。建议使用 NTFS 格式的传输盘，以保留项目文件身份依赖的精确时间戳，并容纳超过 4GB 的模型文件。恢复只做 Python/包启动和 CUDA 可用性检查，不执行模型推理测试。“恢复成功”代表环境已复制并可启动，不代表目标电脑已完成真实视频推理验证。

默认拒绝合并到已有安装。被同一包中断的恢复可重新双击继续；若明确要合并到其他已有安装，可以传 `-AllowExisting`，它可能更新同名文件，应先备份。导出中断后也可使用原 `-PackagePath` 加 `-AllowExisting` 续传。只有导出全部完成才写入 `migration.json`；缺少此文件的迁移包不能恢复。导出前请先停止生成任务，避免复制期间文件被写入。

迁移保留项目原有的选图、观察、发布和失败恢复规则。即梦配置可能先生成图片并等待选图，历史配置也保留其起始图审核；迁移脚本不会代填审核结论。等待状态会提示实际 `run_dir`，按项目 README 的命令继续处理，不要重复新建相同任务。
