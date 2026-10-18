# JIM-02 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; independent pure modules may use dispatching-parallel-agents. Steps use checkbox syntax.

**Goal:** 完整原文的 scene 规划、共享视觉设定、时间预算与可恢复原子提交。
**Architecture:** 纯规划与图校验独立于持锁运行时；clip 预算独立于历史槽位规划。
**Tech Stack:** Python 3.12 标准库、pytest、既有 OllamaPlanner/HttpClient。
**Spec:** docs/task-designs/JIM-02-design.md

## Global Constraints

保留原文、PCM、字幕与历史 schema=1 行为。新 schema=2，algorithm=scene_planning_v1。无收费请求、上传或邮件。无 Git 元数据，不建仓库或分支。请求与持久写入必须持锁，恢复无重复规划请求。新策略全流程入口继续保护。

## Review Focus

非整帧切点的相邻 PCM 覆盖；未来来源及身份伪造；丢失锁的请求/提交；原响应缺失与修正请求中断；有效 settings 恢复与部分提交冲突。由纯规划、图、运行时测试分别覆盖。

### Task 1: 完整文案与视觉依赖纯规划

**Files:** planning/production_scenes.py、planning/visual_consistency.py 及对应 unit tests。
**Interfaces:** Spec 的 paragraphs_from_script/make_scene_schema/build_scene_plan/validate_scene_plan/validate_reference_graph。settings 从 config 导入。纯 API 身份消费 units 顶层 run_id/source_sha256（如存在），否则用原始 UTF-8（含 BOM）摘要及空 run_id；运行时传入冻结身份。
- [x] 同段两句共用 scene 的真实 ProductionTimeline 测试，运行 RED。
- [x] 实现精确 schema、来源、稳定 ID/固定基准、拓扑批次、完整 sample/frame 校验。
- [x] 运行两个新 unit 文件，预期全部 PASS。

### Task 2: 配置与 clip 预算

**Files:** config.py（包含纯 settings parser，无需额外配置模块）、planning/production_visual_plan.py、tests/unit/test_scene_clip_budget.py、tests/unit/test_scene_planning_config.py。
**Interfaces:** config 导出 ScenePlanningSettings/parse_scene_planning；plan_scene_clips(scene_plan, *, max_clip_seconds)->list[dict]。
- [x] 默认/非法配置与 200 帧精确 [93,92,15] 测试，运行 RED。
- [x] 实现 immutable settings，仅新策略允许 scene_planning；独立 clip 预算。
- [x] 验证边界、上限、历史配置序列化，预期全部 PASS。

### Task 3: 持久规划与集成

**Files:** runtime/production_scene_plan.py、tests/integration/test_scene_planning.py、Ollama request ID 支持、示例和文档。
**Interfaces:** produce_scene_plan(frozen, units, timeline, *, paths, logger, lock=None, planner=None)->tuple[dict,dict]。
- [x] 本地 HTTP 往返、完整原文、一次修正、原响应恢复、提交中断和输入冲突测试，运行 RED。
- [x] durable intent/response/proposal，服务 ownership 与锁，commit 最后写入。
- [x] 专项、设计指定历史回归和全套 pytest，预期全部 PASS。
- [x] 独立审查；修复重要问题后记录完成证据，完成 JIM-03 设计和交接。

## Execution ledger

2026-10-18：用户明确要求“JIM-02 完成这个任务”，已有完整设计及 READY 交接，按授权执行。未发现 AGENTS.md、Git 元数据或可用 git，沿用 JIM-01 原地实施。

Pre-flight：Task 1 消费 Task 2 的 settings/clip API；Task 3 消费二者纯数据 API，身份通过 units 顶层 run_id/source_sha256 传递，不改变 units 落盘结构。接口明确，文件职责无冲突。

Task 1: complete — 同段两句和三句共用画面、段落/来源/身份/PCM/图校验，50 个纯规划测试通过，先观察 RED。
Task 2: complete — 默认/非法设置、Wan 上限与帧预算、旧序列化专项 173 passed；50 个缺失 API 测试先 RED 后 GREEN。
Task 3: 实现与专项完成 — runtime 18 个缺失模块测试先 RED；本地 HTTP、原始证据恢复、事务中断、完整输入身份、锁与服务清理均验证。新增截断测试先 RED 后拒绝 length 响应。新功能与设计指定历史回归及 Ollama 共 263 passed in 29.54s，退出码 0。独立审查及全套待完成。

Final: fixed 未来服装/场景事实首用泄漏 — test_first_use_cannot_display_future_clothing_or_location_fact 两项 RED→GREEN。
Final: fixed Ollama 隐式输入截断 — test_model_context_explicitly_reserves_room_for_full_prompt_and_output/test_oversized_full_context_refuses_before_intent_and_http RED→GREEN；仅 scene 请求固定上下文并保守准入。
Final review: 独立审查 Critical=0、Important=2 已修复、Minor=0；修复后专项与相关历史/Ollama **267 passed in 31.29s**。完整审查边界与验收映射见 JIM-02-verification.md。

Task 3: complete（后继准备另记）— 最终全套 **2757 passed in 3790.62s (1:03:10)**，退出码 0，`D:/VideoSi/cache/video-ai/logs/jim-02-full-verified.txt`。JIM-02 已先记录 COMPLETED，再处理 JIM-03 设计和交接。

Successor preparation: complete — 按 Order=3 选择 JIM-03，完成并关联详细设计；自审修正实际历史测试路径、精确函数/记录接口、重发 MIME 身份与活动指针更新规则。交接已写入并关联，任务板真实转入 READY；没有启动 JIM-03 实现或运行其未创建的新测试。
