# JIM-06 验证记录

本文件记录 JIM-06 的结果级验收。2026-10-20 最终串行全库验证完成，3396 passed、退出码 0，342 个实现/测试/工作流/使用文档的前后 SHA256 匹配；协调者随后独立重算 342 项，全部匹配。设计以 `JIM-06-design.md` 为准。

## 验收证据

| 设计验收 | 实现与检验 | 最终结果 |
| --- | --- | --- |
| 原映射全部贡献帧、完整原文/PCM/字幕/停顿 | 独立 scene 保留帧规划、原生 RGB24 全像素比对；真实 200 帧链 93/92/15；真实候选的原声逐样本、静音、SRT/ASS/font、全媒体核验 | 通过；最终全库覆盖全部新用例，200 帧真实链重新通过 |
| 最终实际观察门槛 | 确切 candidate/SRT/composition、原图/基准/动态接受绑定；完整播放和逐 scene/join/unit 观察；unverified/failed 不交付 | 协议与拒绝门槛通过；测试填写的观察不代表真实视觉品质 |
| 确切接受版本与安全交付 | 原字节复制、file-ID+SHA 所有权、不可变临时尝试、不覆盖 rename、receipt 最后、中断恢复 | authentic 完整交付与两次只读重放通过 |
| schema=2 独立、旧行为保留 | 新模块/目录；旧 shot/schema=1 验证不放宽，历史与全库回归 | 456 项历史、3396 项全库通过，342 项文件身份匹配 |
| 状态和阶段内恢复清楚 | prepared-run API、只读 require/progress/prefix、原提交恢复、未知不重发、候选与观察/交付分离；使用文档已更新 | 执行验证通过；独立复审无剩余 Critical/Important |

## 最终串行命令

运行脚本 `D:/VideoSi/cache/video-ai/logs/jim-06-serial-validation.ps1 -Suite all` 自行 dot-source `scripts/bootstrap.ps1`、初始化环境并使用配置的 Python `-B`。专项、设计规定的二十项历史文件、fresh 全库按此顺序串行运行，pytest cache 在 `D:/VideoSi`。

| 批次 | 结果 | 日志 |
| --- | --- | --- |
| targeted 初次 | 189 passed、1 failed in 8718.12s；最后一个 authentic 用例的固定 10 秒准备预算先于预期中断耗尽，exit 1 | `D:/VideoSi/cache/video-ai/logs/jim-06-targeted-initial-timeout.txt` |
| affected-case 复验 | **1 passed in 269.18s**，exit 0；测试使用生产相同冻结预算，生产代码未改 | `D:/VideoSi/cache/video-ai/logs/jim-06-pending-conflict-recheck.txt` |
| historical | **456 passed in 3866.66s**，exit 0；342 文件前后 SHA 匹配 | `D:/VideoSi/cache/video-ai/logs/jim-06-historical-final.txt` |
| full | **3396 passed in 15981.10s (4:26:21)**，exit 0；包括全部 190 个新用例，342 文件前后 SHA 匹配 | `D:/VideoSi/cache/video-ai/logs/jim-06-full-final.txt` |

每项退出码保存于对应 `.exit.txt`。脚本记录全部 src/tests/workflows 的 Python/JSON 文件和使用文档的前后 SHA256，最终 `jim-06-verified-files-check.json` 为 checked=342、matched=true、changed=[]。协调者独立复核记录为 `jim-06-root-final-identity-check.json`，同样 342 项匹配；最终 review 包 SHA256 也重算匹配。验证后仅继续整理设计/验证/任务交接文档，不修改已验证源码、测试、工作流或使用文档。

初次专项在源码/测试冻结后启动：PowerShell session `89666`，环境日志 `jim-06-serial-validation-9a773b8a258540639959ef6a655f9870.log`。独立修复复审使用 `D:/VideoSi/cache/video-ai/logs/jim-06-fix-review-package.md` 的 22 文件 SHA256 快照；原首审快照保留。

初次专项的最后一例在构造故意 graph 冲突后、写 terminal 前中断的夹具时，`timeout=10` 提前触发 `SceneSubmitUnknown`，尚未到达它要验证的 `KeyboardInterrupt`。期限包括完整上游字节守卫，生产入口使用冻结 `timeouts.upscale_frame`（默认 180 秒）。修正仅让该测试使用同一冻结预算并补注释；没有放宽生产超时、守卫、冲突裁决或原有断言。独立 SHA 比较确认与初次运行相比，仅该测试文件变化，其余 src/tests/workflows/使用文档完全匹配。189 项已通过证据保留，受影响用例单独复验，随后要求运行包含全部新用例的 fresh 全库。不会把初次专项写成单次全绿。

修正后的独立审查快照为 `D:/VideoSi/cache/video-ai/logs/jim-06-final-review-package.md`，旧 fix 包保留。最终哈希以 fresh 全库前后核对为准。

修正单例已通过，完整预检确实在任何较早帧的新 POST/服务启动之前拒绝原始 graph 冲突和孤立 body，原证据未被改写。之后通过 `D:/VideoSi/cache/video-ai/logs/jim-06-resume-validation.ps1` 串行继续 exact 历史和 fresh 全库；每批继续由原 runner bootstrap、Python -B、保存退出码并核对前后 SHA。历史哈希另存 `jim-06-historical-verified-files*.json`，全库使用最终 `jim-06-verified-files*.json`。

历史批次通过，`VERIFICATION_COMPLETE checked=342 matched=true suite=historical`。全库随后在同一 PowerShell session `97259` 启动，bootstrap 日志为 `jim-06-serial-validation-f47c6e8b3a734809a2ca07ac830a3c99.log`；2026-10-20 完成为 3396 passed，`VERIFICATION_COMPLETE checked=342 matched=true suite=full`，PowerShell 与 pytest 均退出 0。源码/测试/工作流/使用文档自测试预算修正后保持不变。

最终专项执行产生的真实媒体证据目录（用例最终结果仍以日志为准）：

- `D:/VideoSi/projects/video-ai/runs/20261019-160736-9df32e4f284a`：原声非零样本、完整 SRT/ASS/font 和六帧 1080p 候选。
- `D:/VideoSi/projects/video-ai/runs/20261019-161513-f09c613c2801`：materialized、原 encode/probe 完成、候选准备/晋升/commit 及外围收据丢失恢复。
- `D:/VideoSi/projects/video-ai/runs/20261019-162857-af215841019f`：测试填写的最终观察接受、证据晚变更阻断、owned 输出恢复和完成前缀重放。
- `D:/VideoSi/projects/video-ai/runs/20261019-171142-94c4f99730f7`：真实 200 帧首场景长链，实际 93/92/15 提交与贡献映射断言通过；包含其他场景的全运行共有 203 个技术帧。
- `D:/VideoSi/projects/video-ai/runs/20261019-215853-4ac122fa7e88`：最终全库重新执行同一真实 200 帧长链，全部 203 个技术帧和完整超分记录保留，93/92/15、第三片 generated 1..15 及全局贡献断言通过。

## 诊断与修复证据

第一项实现测试按设计先 RED（缺 `planning.scene_media`，1 failed in 0.15s），再 GREEN（1 passed in 0.12s），使用既有真实 JIM-05 的 200 帧预算和 mapping。后续原导入诊断包括 upscale 11 passed in 672.44s 和 authentic composition 1 passed in 325.86s，均不是最终工作树验证。

完整增量 RED/GREEN、真实运行诊断及命令见 `JIM-06-upscale-report.md`、`JIM-06-composition-report.md`、`JIM-06-delivery-report.md`。一次 authentic delivery 准备暴露 string/Path 边界，随后 preserved run 暴露已晋升 staging 缺失；均修复并由保留的真实源运行只读重建检查。最新该检查为 ADMITTED 6 frames、284 positive Artifacts、93 empty files、12 promoted paths，exit 0；不会替代新的完整 flow。

独立首审 `JIM-06-review.md` 的 I1–I4，以及后续准入快照竞态和原始 command_finished 证明守卫，已由 `JIM-06-review-followup.md` 逐项静态闭合。fix 包 SHA256 为 `79CB7291FB28E5A3DC9DFAA9D9D15105BE9554B16A74981150D894DBEE197174`；包含测试预算修正的 final 包 SHA256 为 `DC293E4FBBF90F2C603FCF1BECE5DEB515A4C9E15E5F6A2E1167C6271847B9E5`。两次审查各自独立核对 **22/22** 当时文件与包内 SHA 匹配，未发现剩余 Critical/Important，13 个生产文件在两包间完全相同。Minor 可读性和替身覆盖边界保留，不扩展无关重构。审查者未运行 Python/媒体/测试，静态通过仍须配合本文件的最终执行结果。

## 验证边界

用户最终澄清“视频的长度帧不限制，帧率也不变”：保留既有 16 fps、完整旁白时长及总帧覆盖。未缩减长链测试、未截短时间轴，也未改变源片或成片帧率；200 帧是回归样例的总帧数。

本任务使用本地 HTTP/服务替身与真实 ffmpeg/ffprobe/PNG/WAV/MP4 媒体。没有真实收费推理、TOS/云操作、QQ 邮件投递或实际观看结论；测试填写的 passed 不能代表真实画面质量。真实模型效果和完整实际影片观看保留给 JIM-08。全流程协调与修订/局部返工由 JIM-07 实现，本任务提供 prepared-run 阶段 API。

已有 checkout 中前序改动保留；Git 元数据只读，没有 commit、merge 或 PR。

## 完成与后继准备

2026-10-20 根据上述结果级证据，任务板先将 JIM-06 记录为 COMPLETED。随后按 Order 选择 JIM-07，完成并关联 `JIM-07-design.md`，写入/全文核对并关联 `../task-handoffs/JIM-07-handoff.md`，最后将 JIM-07 从 NOT_STARTED 准备为 READY。交接 33 个现有引用路径核对通过，设计中的新测试仅是计划，未创建或运行，未开始 JIM-07 实现。此阶段仅整理任务设计、验收和交接文档，未改变已验证实现/测试/工作流/使用文档。
