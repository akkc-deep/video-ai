# VCO-01 Implementation Plan

**Goal:** 落地 visual_v2 并保持旧冻结请求兼容。
**Architecture:** 纯契约校验/渲染与运行层文件身份分离；视频内容身份独立于规划身份。
**Tech Stack:** Python 3.12、标准库、pytest、现有离线媒体集成替身。
**Spec:** docs/task-designs/VCO-01-design.md；既有 JIM-08-color-repair-design.md 的 A 阶段。

## Global Constraints

精确 schema_version=1；production_strategy=paragraph_jimeng_v1；仅显式 visual_v2；原生 16fps 和 96 帧 guard 不变；无真实推理；.git 只读，当前工作区实现且不提交。

## Review Focus

重复/缺失/乱序 clip；布尔 schema 与坐标；提示标签换行注入；冻结后同 stat 字节漂移；旧修订身份回放和新身份降级/部分字段拒绝。各阶段测试均覆盖对应输入。

## Task 1: 契约与纯视觉渲染

- [x] 新建 tests/unit/test_scene_video_prompts.py，验证 schema、review digest、changes 原文、绑定、完整 clip、多题材与纯渲染。
- [x] RED：运行新增文件，缺失模块失败。
- [x] 新建 planning/scene_video_prompts.py，输出 validate_scene_video_prompt_contract 和 render_scene_video_prompt；config.py 接受精确可选 raw 配置。
- [x] GREEN：新增单测全部通过，输入保持不变。

## Task 2: 冻结与源片接入

- [x] 新建 tests/integration/test_scene_video_prompt_flow.py，消费真实准入的计划/选图及离线 Wan；验证冻结、读回、漂移零提交和旧 graph 原值。
- [x] RED 后新增 runtime/scene_video_prompt_records.py，production_inputs.py 增加可选冻结身份；build_scene_wan_plan 消费验证后契约，scene_context 新增输入/发送 guard。
- [x] GREEN：单元及源片集成通过，comparison_images 不进入模型。

## Task 3: 修订与恢复

- [x] 扩展 test_scene_revision.py、test_scene_video_prompts.py 集成：提示变更仅使视频后代失效，不重出图，恢复身份漂移拒绝。
- [x] RED 后版本化 identity_from_options，configuration_identity 读取实际契约，非 reconfigure 继承冻结路径；恢复按已提交身份版本重建。
- [x] GREEN：修订、pipeline recovery 和新契约集成全部通过。

## Task 4: 验证与交付

- [x] 定向测试及裸全库 pytest；独立 basetemp/cache，保存日志和退出码。
- [x] 代码审查，必要问题 RED/GREEN 修复；记录限制。
- [x] 完成 VCO-01 板状态与证据；按顺序完成 VCO-02 设计和交接，后继准备 READY，不开始其实现。

## Execution Ledger

- 2026-10-23：旧 continuation/revision 基线 94 passed；仓库 pytest cache 写权限告警，后续缓存改用运行 temp。日志 vco01-baseline-713b99a1581a4fe2a6633aaa4a1b8bad.log。
- 用户完成指令作为实施授权；沿既有 A 阶段合同执行，未启动真实推理。.git 只读，不能建立 git worktree/提交，采用当前工作区保留未跟踪输入文档。
- 来源绑定决策：只在全部 common/plan/image_group/choices 都有 import 证明时沿源链验证原契约，不重签 review；否则漂移拒绝。
- 修订/纯契约/旧续片145 passed；新增直接冻结字节测试并修正合法策略下的配置拒绝用例。
- 离线 pipeline RED/GREEN 运行层目前 3 passed；review 发现的祖先契约闭包缺失以 guard 修改字节用例复现（1 failed，DID NOT RAISE）。补齐仅 visual_v2 clip/upscale 的冻结契约捕获；旧来源闭包不变。日志 vco01-runtime-flow-8ddbefc7148d41deb697072e7c870266.log。
- 补查连续修订的中间 Wan 汇总未落地边界：先以 FileNotFoundError 复现，再限定完整 import 的中间修订可只读重建，已有记录仍严格验；单元/旧续片/修订151 passed，日志 vco01-binding-green-deacaa406fab430693c3567996f2b09d.log。
- 最终裸全库完成：3715 passed in 19118.06s (5:18:38)，退出 0；日志 `D:/VideoSi/cache/video-ai/logs/vco01-full-85499112ee604420b26fd6fb13e22ba4.log`。仅运行这一轮最终全库，没有重启或以中断定向运行代替全库。运行后 13/13 源码与测试文件均匹配 `D:/VideoSi/cache/video-ai/logs/vco01-source-snapshot.json`，git diff --check 通过。具体验收与限制见 VCO-01-verification.md。
- 先记录 VCO-01 COMPLETED，再完成并关联 VCO-02-design.md；随后写入 VCO-02-handoff.md、关联任务板并将 VCO-02 准备为 READY。未启动 VCO-02 实现，其他任务与原 JIM-08 任务板不变。
