# JIM-03 Verification

## Outcome and boundary

实现准备运行的候选邮件、基准/后续批次选择、等待续作及完整图片准入。使用真实 PNG/JPEG 等媒体和本地 SMTP/官方图片 HTTP 替身；没有真实收费生成、云上传、QQ 邮件、Wan 请求或模型服务启动。后续参考图生成、连续视频和完整新文案协调器仍属于 JIM-04 以后任务。

## Acceptance evidence

| 任务板验收 | 已实现的结果 | 验证来源 |
|---|---|---|
| ① 实际图片、可复制编号、完整原文、基准用途；完整 MIME 默认 15 MiB | 确定 Message-ID/boundary/CID，纯文本与 HTML 转义正文，原图附件、四级副本及多页对照图；当前待选与已接受基准用途分别保留 | `tests/unit/test_selection_email.py` 的本地 SMTP DATA、真实不可压缩 PNG 分页、实际 WebP/BMP/TIFF/GIF/PPM/JP2/TGA、整组分页/来源/超限用例；`test_selection_sheet.py` 的真实 ffmpeg 完整解码与 contain 像素观察 |
| ② 成功不重发，unknown 不自动重发，配置修复不出图 | MAIL/RCPT 后持锁写 intent，成功回执后永久复用；unknown/明确拒绝需指定原 intent 原始字节摘要显式 retry，新 Message-ID 保留历史 | `test_image_selection_flow.py` 的 unknown、认证修复、分包部分成功、中断、显式 retry 测试；SMTP 总期限、迟到 DNS、同步取消竞态专项 |
| ③ 每 scene 一张且身份精确，草稿不接受 | commit/run/source/units/timeline/原图/下载收据/候选任务/基准全部只读重验，复制用户原始提交，accepted 不可变 | `test_image_selection_records.py` 的同名局部候选、循环外键、缺项/重复/跨 run、提交或原图/基准篡改；集成草稿、重复接受、重选拒绝 |
| ④ 编号不生成一致性通过，无完整准入不请求 Wan | observation 默认为 null，逐图身份精确绑定；全组 passed 实际观察与全部选择齐备才写 complete；所有新路径均无 Wan 调用 | records 的观察 scope、failed/unverified、viewed_images 缺漏/伪造、SMTP 回执缺失测试；真实两批集成仅 explicit 全组观察产完整记录 |
| ⑤ 等待释放所有权，续作保留原图和基准 | 自有 RunLock/SMTP 有限连接释放，外部锁保留；每次提交与工作线程 MAIL/DATA 前重验所有权；prepared CLI schema2 等待码3 | flow 的锁持有/释放/失锁、CLI 等待/消费、intent/data/回执中断、active-pointer 及 CLI 异常收尾测试 |

## Executed commands and results

所有 Python 前执行 `. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment <name>`，运行既有 `$VideoAiPython -B -m pytest`，不安装新依赖。

- 新运行时 14 项先观察缺模块失败，然后 **14 passed in 63.60s**。
- 邮件/相关配置最终模块验证 **79 passed in 4.42s**（含 52 个邮件测试）。媒体 **11 passed in 14.57s**，记录 **42 passed in 28.19s**。
- 指定历史回归：`tests/unit/test_jimeng_inputs.py tests/integration/test_jimeng_candidates.py tests/integration/test_scene_planning.py tests/unit/test_model_visual_prompts.py tests/unit/test_production_review.py tests/integration/test_make_video_cli.py tests/integration/test_make_video_recovery_contract.py`，**114 passed in 225.54s**，退出码 0，输出 `D:/VideoSi/cache/video-ai/logs/jim-03-regression.txt`。
- 修复后新专项（最终 CLI 修复前）：邮件/媒体/记录/流程四文件 **129 passed in 155.93s**，退出码 0，输出 `D:/VideoSi/cache/video-ai/logs/jim-03-final-focused.txt`。
- 最终 CLI 审查两项先失败（schema1 越权错误记录、AttributeError），修复后定向 **2 passed in 11.83s**；锁释放另加 OSError 用例随完整测试执行。
- 完整测试：枚举所有 `tests/**/test_*.py`，144 个模块各执行一次，按排序下标取模划分四个 pytest 进程，均使用 `-q --tb=short`。初次为 **2886 passed、2 failed、1 error**，1228.41 秒，保留退出码 1 的真实原报告 `D:/VideoSi/cache/video-ai/logs/jim-03-full-summary.json`，没有将它改写为成功。
- 三个异常节点在所有分组结束后串行复跑，**3 passed in 10.12s**，退出码 0；代码未改。完整覆盖 **2889 个唯一用例均有通过证据**，其中最后新增的 CLI 锁退出 OSError 用例也通过。覆盖汇总 `D:/VideoSi/cache/video-ai/logs/jim-03-verified-coverage.json`。

串行复跑命令（bootstrap 后）：

```powershell
& $VideoAiPython -B -m pytest `
  'tests/unit/test_preflight.py::test_local_fixture_doctor_passes_and_keeps_inference_and_space_unverified' `
  'tests/unit/test_production_composition.py::test_incomplete_technical_command_uses_fresh_attempt_directory[False]' `
  'tests/unit/test_publication.py::test_copy_failure_and_commit_drift_preserve_partial_files[nested_drift]' -q --tb=short
```

原并行异常：旧预检测试的全局 runs 集合断言观察到另一个进程创建目录；旧合成测试打开共享字体硬链接进行同步时收到 Windows PermissionError；旧发布测试的候选验证准备未通过。串行复跑日志为 `D:/VideoSi/cache/video-ai/logs/jim-03-isolated-regression.txt`。前两项有目录变化/字体访问的直接错误证据；发布准备错误的底层原因未在本轮确定，不将其强行归因于并发。没有为这三个旧测试改生产逻辑，也不宣称单次并行命令零失败。

## Independent review and fixes

模块交叉审查及最后独立整体审查均已执行。最后整体 Critical=0、Important=2、Minor=0；两项 CLI 问题已 RED→GREEN。模块阶段额外复现并修复：SMTP 超时取消和发送之间的竞态、工作线程 DATA 前失锁、媒体与 media.json 同时变化造成错误来源复用、observation 非对象以及回执数字布尔混淆。活动指针 run/schema 伪造也由失败用例固定。

可选 `baseline_roles` 补充当前待选基准的确切 kind/id 用途；可选只读 `ownership_check` 供工作线程重验 MAIL/DATA 权限，写意图仍在持锁调用线程。没有已准备批次的普通 Jimeng 续作保持既有全流程 blocked 保护；显式选图或登记批次使用独立 schema=2。

## Practical limits

SMTP 2xx 证明服务器接受，不代表真实 QQ 收件箱投递。真实授权码、账号、云参考输入及实际图片/视频质量由后续真实验收验证。观察测试中的 passed 是明确提供的测试用户记录，程序不会根据编号或哈希生成看图结论。显式重发 unknown 可能产生重复邮件，普通续作不会重发。

工作目录改动保留供审阅；Git 元数据只读，本轮没有创建分支、提交或推送。
