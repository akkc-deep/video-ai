# JIM-01 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; inline execution with a final fresh review. Steps use checkbox syntax.

**Goal:** 实现 JIM-01 的官方图片任务与安全恢复。
**Architecture:** 配置、HTTPS/签名、候选存储独立；通过冻结输入和必要预检接入现有项目。
**Tech Stack:** Python 3.12 标准库、pytest、既有 ffprobe/ffmpeg。
**Spec:** docs/task-designs/JIM-01-design.md

## Global Constraints

旧配置/旧运行保持历史行为。无真实收费请求、邮件或云资源写入。不创建 Git 仓库。凭证与签名 URL 不落普通日志。已有 task_id 不重提。

## Review Focus

检查未知提交的再次进入、部分多图下载、冻结配置的 CLI 改模、旧快照兼容、含密钥/URL 的服务端错误脱敏。

### Task 1: 配置和冻结

接口：parse_image_generation(dict)->ImageGenerationConfig，override_image_model(config, req_key)；freeze_inputs/load_frozen_inputs 新增 image_model。
- [x] 写 test_jimeng_config.py、test_jimeng_inputs.py，先看到新字段/改模测试失败。
- [x] 实现配置、CLI 和 schema=2 options；旧 schema 保持原形。
- [x] 验证新策略无需 SDXL，改模拒绝，CLI 传值；运行相关历史测试。

### Task 2: HTTPS 和官方协议

接口：ExternalHttpsClient.request(method,url,body,headers,timeout,max_bytes)；JimengClient.submit/query/download；sign_request(body,action,access_key,secret_key, timestamp)。
- [x] 写 test_jimeng.py，验证固定签名、状态/错误解析、URL 和异常脱敏，先运行失败。
- [x] 实现独立外部 HTTPS 与官方签名，不修改本机 HttpClient 边界。
- [x] 运行新协议测试和既有 transport/config 回归。

### Task 3: 候选持久化与恢复

接口：generate_candidates(frozen,scene_id,prompt,client=None,inspect=None,sleep=...) -> dict。
- [x] 写 HTTP 替身集成测试，断言磁盘原图/哈希、请求次数和故障恢复，先运行失败。
- [x] 实现持锁、意图/accepted、脱敏响应和下载记录；支持每请求多图和缺项下载。
- [x] 运行新增测试、全套 pytest；最终独立审查后修复发现的问题。
- [x] 记录任务板完成证据，完成 JIM-02 设计和交接后将其准备为 READY。

## Execution ledger

2026-10-18：总体方案已确认，用户明确要求完成 JIM-01，按其授权连续实施。无 Git 元数据/可用 git，原地工作，不提交或建分支。接口预检：Task 3 消费 Task 1 的 frozen.config.image_generation、Task 2 的 JimengClient；保持一致。

Task 1: complete — 配置/冻结/CLI及历史制作入口专项74 passed。历史序列化集中于 thaw 保留旧字段集合；新策略允许省略 SDXL。

Task 2/3: 实现完成并持续验证。新增79 passed，含真实PNG完整解码与坏图拒绝。独立审查两项 Important 均已复现 RED，再修正 GREEN：下载收据先于原图暴露；外层有限等待覆盖OS解析阻塞，晚到的连接不能越过其过期检查发送HTTP。当时全套pytest最终回归运行中，最终通过结果见下一条。

Task 2/3: complete — 修复后全套 **2628 passed in 3758.32s**，退出码 0；独立复核4 passed，两项 Important 均关闭。JIM-01 已记录 COMPLETED，随后准备 JIM-02 设计和交接。

Successor preparation: complete — JIM-02 详细设计已完成、全文自审并关联；随后创建并关联 `docs/task-handoffs/JIM-02-handoff.md`，任务板由 NOT_STARTED 转入 READY。JIM-02 实现未启动，其新增测试未创建或运行。

Ruling: 图片下载保存扩展为 receipt -> original -> decoded candidate 的顺序 — 防止元数据前中断后接受替换图片 — 增加一份下载收据，恢复必须核验。

Ruling: 采用 daemon transport worker + 外层总期限 — Python同步OS DNS不可由socket计时器中止 — OS调用可能晚返回，但调用者按时释放；晚连接在发送HTTP前检查过期，不自动重试。
