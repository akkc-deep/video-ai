# LVA-01 Implementation Plan

**Goal:** 交付旁路观测、正常/恢复台账、离线实测及可复现真实实验协议。
**Architecture:** 当前线程有界 profiler，不改生成函数；只使用现有返回身份和已有命令识别计数，不引入验证 I/O。真实 GPU 和内部节点缺失保持显式未验证。
**Spec:** `docs/task-designs/LVA-01-design.md`

## Global Constraints

保持 v1、paragraph_jimeng_v1、即梦协议、生产参数/帧数/人工审核不变；保全已有未提交改动；生成时不要过度校验。只创建新的 scratch fixture，不恢复生产。

## Review Focus

脱敏字符串泄漏；缓存入口误算实际哈希；嵌套耗时重复相加；异常后 profiler 未恢复；零成功样本或恢复样本污染正常基线。均由专项测试覆盖。

### 1. 观测与汇总

- [x] 先写 `tests/unit/test_local_video_metrics.py`，验证上述边界并确认缺少模块失败。
- [x] 实现 `LocalVideoMetrics`、`summarize_samples`、`write_report`；只输出白名单字段。
- [x] 跑专项单元，修正后记录结果。

### 2. 实际媒体与基准

- [x] 先写真实 FFmpeg 集成，确认 probe/解码准确、已有媒体重放不额外生成。
- [x] 新建禁网 scratch benchmark，4 次正常/恢复各开关对照，JSON/Markdown 保存身份和扰动。
- [x] 跑相关媒体/HTTP guard 定向回归，核对台账。

### 3. 证据与真实实验

- [x] 完成调用点价值台账、待冻结实验协议和结果报告，记录缺失项。
- [x] 真实新实验 run 三类冷1/热3并人工验收后才能满足任务完成条件；之前不推进后继。

## Execution evidence

2026-11-15 用户“完成任务 LVA-01”作为启动证据。原工作区增量实现，仅新增模块/测试/报告及修改本任务行；不自动提交用户现有改动。具体实验输入及许可待准备完成后确认。

27项专项/隔离整合通过，既有媒体22项通过、1项旧fixture错误具名记录；独立复查无Critical/Important。详细结果与未完成范围见 `docs/task-designs/LVA-01-results.md`。

## Latest experiment evidence

LVA-01 已完成：16次原生、1424帧真实超分、12份1080P技术及实际人工质量全部通过；全部owned服务关闭。选材T0、交付T1及审核响应从哈希绑定的当前线程日志和真实wrapper恢复，排队与重叠等待明确保留，无需额外GPU生成。见 `LVA-01-completion.json`、`LVA-01-gpu-results.md`、`LVA-01-timing-evidence.json`。后继准备是完成后的独立操作，不表示实施LVA-02。
