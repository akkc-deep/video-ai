# JIM-07 验证记录

状态：已完成。2026-10-20 最终裸全库、覆盖清单和独立文件身份核对均已通过；任务板完成状态以本记录的结果级证据为依据。

## 完成结果

公共 `make-video` 已接通原文、图片选择、片段观察、逐帧超分、候选、最终观察和显式发布。选择及观察只消费提交文件，普通续作保留原任务；修订建立新冻结运行，通过内容失效图与准入图确定重做和继承范围。

保留完整原文、PCM、SRT、原生16 fps、cut和1920×1080；没有新增视频总帧上限。HTTP、SMTP、TOS、模型和服务使用本地替身，PNG/WAV/MP4及ffmpeg/ffprobe为真实媒体与工具。

| 设计验收项 | 最终结果级证据 | 结果 |
| --- | --- | --- |
| 公共入口、各类等待、消费及独立发布，无重复提交 | 自动原文/TTS/大WAV三例；完整prepared公共流程及十个协调边界；movie rename中断、普通只读拒绝、显式publish恢复 | 通过 |
| 新冻结修订、正确失效及实际局部复用，来源不变 | 四种修订纯矩阵、后批返工、二次修订；实际只新增2个Wan片段和8个超分帧，继承10帧，完整18帧接受；原source字节/mtime不变，继承分支没有owned提取目录 | 通过 |
| 原记录恢复、未知副作用及身份冲突拒绝 | 逐提交/复制/冻结边界、unknown/running/伪造终态、同stat字节变化、空日志及清单变化、所有权/失锁、C→B→A祖先守卫和确切FrozenInputs绑定 | 通过 |
| 完成重放只读，旧接口兼容 | 两次completed replay、重复publish及损坏transaction/收据零写哨兵；旧CLI及原prepared APIs；历史200帧主链93/92/15及完整贡献 | 通过 |
| CLI、说明、当前字节测试和证据一致 | 参数互斥、原结果类型及退出码；`docs/jimeng-candidates.md`；最终3552项全库及364项独立文件身份核对 | 通过 |

最终公共流程source：`D:/VideoSi/projects/video-ai/runs/20261020-155728-728840375d5f`；主continuation修订：`D:/VideoSi/projects/video-ai/runs/20261020-083012-9d5deb33ba99`。200帧主链测试run：`D:/VideoSi/projects/video-ai/runs/20261020-174938-c291eacd9d51`，另含独立scene，总计203帧。上述均为自动测试现场。

## 最终正式验证

每个新PowerShell Python调用先bootstrap，使用`$VideoAiPython -B`；Python与媒体任务串行，缓存和日志位于D:/VideoSi。

最终实际命令由 `D:/VideoSi/cache/video-ai/logs/jim-07-final-v3-regression.ps1` 执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-07-final-v3-regression'
& $VideoAiPython -B -m pytest -v --tb=short --durations=15 -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

**3552 passed in 19130.96s (5:18:50)，退出0。** 开始2026-10-20 14:38:12 +08:00，结束19:57:03 +08:00；无路径选择的完整全库。实际命令、时间及退出码保存在 `jim-07-final-v3-all-pytest.json`，逐例输出保存在同名`.txt`。

逐例解析器 `jim-07-check-coverage.ps1 -Label jim-07-final-v3-all-pytest -RequireSuccess` 已独立核实：

| 最终全库中的集合 | 实际通过/节点数 |
| --- | --- |
| 全库唯一节点 | 3552/3552，无重复、无非通过项 |
| 新增六模块 | 156/156 |
| 设计指定九个历史模块 | 195/195 |

这些分组来自同一次成功全库，不冒充另一次独立子集命令。完整节点和日志SHA见 `D:/VideoSi/cache/video-ai/logs/jim-07-final-v3-all-pytest-coverage.json`。

完整公共流程单例5395.18s；200帧主链单例4500.48s。记录本机实际耗时，不据此添加帧数限制或宣称真实模型吞吐。

## 最终文件身份

脚本before/after及root重新计算的current清单均为 **364项**，路径、bytes及SHA256逐项一致，差异0；`git diff --check`退出0。

三份清单原始SHA256完全相同：`EC573A9CB9E8E32D30D49AD28577E0A6B2E834581EBDC37287E78AA1399F9FA8`。

- `jim-07-final-v3-regression-before.json`
- `jim-07-final-v3-regression-after.json`
- `jim-07-final-v3-root-current.json`

独立核对脚本及结果：`jim-07-final-v3-root-check.ps1`、`jim-07-final-v3-root-identity-check.json`。以上文件均在 `D:/VideoSi/cache/video-ai/logs/`，覆盖src、tests、workflows和`docs/jimeng-candidates.md`。完成记录与任务交接文档不在该被测文件清单内。保留当前checkout和只读Git元数据，未执行提交、合并或推送。

## 独立审查及失败修复

一次独立只读整体验证发现3项Important，无Critical/Minor：损坏transaction的publish回退、多层修订祖先guard丢失、继承首批后不能推进后批。均经实际RED和修复；同一修复通道补齐后批contact sheet的显式inherited baseline读取及确切冻结上下文绑定。当前全库重新覆盖这些用例。审查包：`jim-07-final-review-package.json`。

| 历次正式执行或修复 | 实际结果 | 处理与证据 |
| --- | --- | --- |
| 首轮独立新六模块、指定历史 | 156 passed / 195 passed，均退出0，分别5989.37s / 7441.58s | 锁兼容修复前版本；归档`jim-07-first-formal-before-legacy-lock-fix/`，不冒充最终字节独立命令 |
| 首轮全库发现未冻结run的活动锁拒绝回归 | 明确FAILED后停止，退出-1，不计通过 | 原用例1 failed in 0.21s；分派在options未提交且已有锁时只读blocked；定向32通过，完整旧CLI32 passed in 137.81s |
| v2完整全库 | 1 failed, 3551 passed in 19236.03s (5:20:36)，退出1 | 唯一旧identity_copy正例声明不同源/目标字节；原用例独立RED 0.22s确认 |
| 复制正例夹具校正 | 原片段记录与修订记录46 passed in 1.54s，退出0 | 只把正例source改成确切复制字节；保留全部原断言和生产严格校验；最终全库该用例PASSED |
| v3最终完整全库 | 3552 passed，退出0 | 当前最终版本，覆盖及身份核对均通过 |

v2完整逐例覆盖为新增156/156、指定历史195/195通过，唯一失败位于其外；before与失败后root清单SHA相同。v2到v3唯一变化为上述旧测试正例，生产源码、workflow和使用说明相同。v2失败与此前中止的媒体流程均保留原日志，不计为整组成功。完整RED→GREEN、夹具修正、命令、裁决与早期专项结果见 [进度账本](JIM-07-progress.md)。

## 实际服务边界

本项没有真实付费模型请求、TOS云操作、SMTP发信或实际观看通过结论。自动替身与真实媒体证据不证明真实账号权限、QQ收信或模型视觉质量；这些仍属于JIM-08。
