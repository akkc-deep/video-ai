# JIM-03 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for independent modules and verification-before-completion for the final gate.

**Goal:** 已持久候选的安全邮件通知、不可变选图及整组观察准入、CLI 等待续作。
**Architecture:** 纯配置/MIME、媒体、只读身份验证独立；持锁运行时协调不可变记录，CLI 只分派准备运行。
**Tech Stack:** Python 3.12 标准库、ffmpeg/ffprobe、pytest。
**Spec:** docs/task-designs/JIM-03-design.md

## Global Constraints

schema=2、paragraph_jimeng_v1；不改变历史 schema=1。仅本地 SMTP 替身，无真实邮件/出图/上传/Wan 请求。不启动模型服务。原图、计划、已接受选择不可覆盖；unknown 不自动重发。Git 元数据只读，原地实施，不建分支或提交。

## Review Focus

跨 scene 同名 candidate；DATA 超时及迟到连接；MIME 编码后的实际限额；已接受原图/基准篡改；完整选择缺实际观察。分别由记录、SMTP、MIME、集成测试覆盖。

### Task 1: 邮件配置与发送边界

**Files:** selection_config.py、adapters/selection_email.py、config.py、tests/unit/test_selection_email.py。
**Interfaces:** parse_selection_email/build_messages/SmtpSender 及异常严格遵循 Spec。
- [x] 建两 scene 同名候选真实图片测试，先运行 RED。
- [x] 实现纯配置、确定 MIME、完整字节分页、SSL/总期限与 before_data。
- [x] 运行 MIME/SMTP/配置专项，全部 PASS。

### Task 2: 不可变身份与选图校验

**Files:** runtime/image_selection_records.py、tests/unit/test_image_selection_records.py。
**Interfaces:** load_committed_plan/validate_batch/validate_selection/require_complete_image_acceptance；辅助 build_batch/accepted_batches 供运行时复用。
- [x] 编写真实计划/候选的身份、草稿、观察与篡改失败测试，先运行 RED。
- [x] 实现只读验证，不调用生成或发送。
- [x] 运行专项，全部 PASS。

### Task 3: 邮件媒体

**Files:** media/selection_sheet.py、tests/unit/test_selection_sheet.py。
**Interfaces:** prepare_email_media(batch, *, config, paths, logger)->dict，精确媒体记录遵循 Spec。
- [x] 建原图不变、缩略图及多页对照图测试，先运行 RED。
- [x] 实现原子可追踪副本与带标签对照图。
- [x] 真实 ffmpeg 解码专项 PASS。

### Task 4: 持锁通知/选择事务与 CLI

**Files:** runtime/production_image_selection.py、production.py、cli.py、tests/integration/test_image_selection_flow.py、示例与文档。
**Interfaces:** prepare_image_batch/consume_image_selection/retry_notification/ImageSelectionResult 遵循 Spec；CLI 准备输入恢复，不启动全流程。
- [x] SMTP intent/receipt 恢复、批次选择/整组观察、等待释放及 CLI 测试先 RED。
- [x] 实现持锁事务、显式重发和活动批次推进。
- [x] 专项、相关历史回归、全套运行通过；独立审查及重要修复。
- [x] 记录 JIM-03 完成证据，再设计并交接 JIM-04。

## Execution ledger

2026-10-18：用户明确要求“完成JIM-03”。已全文读取设计/交接，任务由 READY 开始；授权本地实现与验证。

Pre-flight：Task 4 消费 Task 1 MIME 行和 SMTP before_data、Task 2 纯记录、Task 3 精确 media.json；共享结构均以 Spec 为准。Task 1/2/3 文件独立，协调器由主执行者维护。

Ruling: 已有实施契约和明确完成请求视为执行授权，直接实施，不重复设计批准；当前 Git 元数据只读，沿当前工作目录实施且不修改 Git 元数据。代价：无本轮独立 Git 提交，改动仍可由差异审阅。

Task 1: complete — 最终模块/相关配置 **79 passed in 4.42s**，含 52 邮件测试；真实本地 SMTP DATA、实际图片、15 MiB 编码后分页与更小限额副本回退。初次缺模块 RED，SMTPDataError/中断、长 boundary、来源、当前基准用途、格式、取消与所有权逐项 RED→GREEN。独立模块审查 P1 SMTP 超时/发送竞态已复现并修复：共享同步状态防晚到 DATA。

Task 2: complete — **42 passed in 28.19s**。初次 27 项缺模块 RED；补非对象 observation、按确切用途筛基准、缺 SMTP 回执后先失败再修复。纯读候选/计划/提交/接受，完整准入重验所有来源。

Task 3: complete — **11 passed in 14.57s**，真实 ffmpeg；预览/对照图与 media.json 同时改动的两个审查用例先 RED，恢复从原图重渲染确定字节并拒绝冲突，未改素材时间戳保留。独立模块审查无剩余重要问题。

Task 4: 首轮 **14 passed in 63.60s**，缺运行时模块的 14 项先 RED；扩展活动指针 run/schema 2 项 RED→GREEN，回执 part=True RED→GREEN，SMTP worker 失锁时实际 DATA 复现后注入只读 ownership_check。相关历史 **114 passed in 225.54s**。修复后完整专项 **129 passed in 155.93s**（最终 CLI 修复前）。

Final review: 独立整体审查 Critical=0、Important=2、Minor=0。CLI 完成日志失锁后进入历史错误写入、退出锁错误读取 schema1 字段：两个测试 RED（错误 schema1/越权错误文件与 AttributeError），使用 schema2 专用异常收尾修复；退出锁另覆盖 OSError。

Ruling: 无已准备批次的普通 Jimeng --run-dir 保留旧协调器 blocked 保护；显式 --image-selection 和已登记批次进入 schema2。依据设计“没有批次仍保留现有全流程未实现保护”，代价：未准备普通续作的拒绝仍使用旧结果结构。

Ruling: build_messages 增加可选 baseline_roles、SmtpSender 增加可选只读 ownership_check，补齐当前待选基准用途和工作线程 MAIL/DATA 前所有权复核，既有调用保持兼容。代价：可选接口较原设计增加两个关键字，无持久 schema 变化。

Final declined-to-judge rulings: QQ 真实收件/账号留到 JIM-08；视觉结论真实性需真实审查者；参考生成/Wan/完整协调器分别属于后续任务。均保留现有范围，代价为这些能力本轮不实测/不实现，未据此宣称项目全部完成。

Task 4: complete — 144 个测试模块完整分组执行：初次 2886 passed、2 failed、1 error，1228.41 秒；三节点均为旧测试，在不改代码的情况下串行 **3 passed in 10.12s**。完整覆盖 **2889 个唯一用例均有通过证据**。真实原并行退出码1及复跑退出码0均保留，汇总 `D:/VideoSi/cache/video-ai/logs/jim-03-verified-coverage.json`。用户未要求或授权真实测试邮件；自动测试无真实发送/上传/收费生成。验收映射见 JIM-03-verification.md。

Ruling: 全量按模块分组后发现共享运行目录断言、共享字体访问及旧发布准备三个异常；不修改无关生产逻辑，所有组结束后串行复跑失败节点，三项通过。代价：本轮完整覆盖是分组加串行复查，不能描述为单次并行零失败；发布准备错误的底层原因未确定，完整证据保留。

Successor preparation: complete — JIM-03 先记录 COMPLETED，再按 Order=4 选择 JIM-04，完成并回填其详细设计。全文自审补齐旧运行保留基准后的 reference_settings_path、首次参考阶段配置冻结、TOS intent/object、参考 request intent 精确字段和固定签名向量。交接写入关联后真实转入 READY，JIM-04 未启动实现/新测试。
