# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`
- **Completed task:** LVA-02，已记录COMPLETED，结果 `docs/task-designs/LVA-02-results.json` / `.md`。
- **Next task:** LVA-03，按预定义Order=3选择，观察状态NOT_STARTED。
- **Design document:** `docs/task-designs/LVA-03-design.md`，已完成并关联任务板。
- **Expected next status:** READY；写入本交接并关联后执行NOT_STARTED→READY，不启动实现。

## Next Task

LVA-03 — P1 / C：Comfy模型生命周期与依赖感知准备重叠。保持原质量和父子审核，测量同phase的实际服务/模型准备及GPU空闲，验证有界只读图谱/选图预读候选。模型默认管理与图像适配/证据写入保留在原路径；单GPU单Wan、同链串行，不跨人工审核驻留。真实授权冷/热实验是本项完成条件，离线pool测试不能代替GPU结果。无收益保持默认串行。

## Dependencies

### LVA-01 / 原质量与分阶段基线

- **Artifact:** `docs/task-designs/LVA-01-completion.json`、`LVA-01-gpu-results.json` / `.md`、`LVA-01-gpu-experiments.json`、`LVA-01-timing-evidence.json`；节点观测 `src/video_ai/runtime/local_comfy_metrics.py`、`scripts/observe_local_comfy.py`。
- **Decision:** 沿用40步、CFG3.5、768×432、16fps、high15/low25及完整帧预算；使用相同固定输入/seed，父片真实末帧与人工接受不得跳过。
- **Rationale:** 四类各冷1热3共16次原生、1424帧超分、12份1080P已实际技术/人工接受；high/low采样为主要原生耗时。已有模型方法调用不等于物理权重全量重载。
- **Constraint:** 所有owned服务已关闭，旧生产暂停。LVA-01的T0包络含排队/审核及观察延迟，不可相加当吞吐；本项需要新实验及明确GPU授权。
- **Usage:** 复用固定素材/环境/阶段口径，比较冷/热节点与设备采样，物理装载无法测得时明确未知，不由方法数猜测。
- **Readiness evidence:** 任务板LVA-01 COMPLETED；最终父子1080P已于2026-11-15T09:50:34.724Z获用户接受，所有owned实验服务关闭。

### LVA-02 / 作用域、恢复与采用门槛

- **Artifact:** `docs/task-designs/LVA-02-design.md`、`LVA-02-results.json` / `.md`、`LVA-02-plan.md`；`src/video_ai/runtime/scene_validation_pass.py`；`tests/unit/test_scene_validation_pass.py`、`test_scene_validation_boundaries.py`、`tests/integration/test_scene_validation_recovery.py`；`scripts/benchmark_scene_validation.py`、`tests/scene_validation_helpers.py`。
- **Decision:** 默认生产guard保留strict；`candidate_scene_validation()`仅离线显式启用，不能随LVA-03默认开启。每个独立callback必须自己fresh flush，不跨socket/响应写共享证明；worker不继承scene memo/capture/reader。
- **Rationale:** 四对正常严格工作12876→8982，实际SHA/解码不减，墙钟18.908746→20.756011秒（+9.77%），所以否决默认采用。放大样本128→32及目录4→2不代表生产收益。
- **Constraint:** 原schema/intent/accepted/queue/history/全部帧及晋升边界不改；unknown仅GET原任务、已有产物先验真再复用。模型/tool stamp保留，不把metadata调用当模型SHA。新worker只读且有界，所有不可变证据由持锁协调线程写。
- **Usage:** 以真实墙钟与空闲证据决定采用；复用隔离配置与真实FFmpeg/内存transport，保留strict baseline和单变量归因。现有 `_produce` 已同phase懒创建一个service、finally关闭，不重做这一优化。
- **Readiness evidence:** 214定向证明/事务/socket测试、5真实媒体/超分恢复及22媒体性能测试通过。原恢复64通过/6失败/6排除，补充50通过/3旧路径fixture失败全部具名披露；五legacy模型夹具、无效run入口、continuity路径及旧output reclaim清理不属已修复结果。完整聚合观测无错误，normal原始明细超限、直接producer计数未测/receipt推导有明确限制。当前任务COMPLETED，无生产/GPU加速声明。

## Start Here

按序读：① `docs/task-designs/LVA-03-design.md`；② 本任务板LVA-03及本交接；③ LVA-01 GPU结果/固定输入、LVA-02结果与默认strict决策；④ `production_scene_clips.py` 的 `_OwnedService` / `_produce` / `_input` 与 `scene_clip_records.py::graph_for`；⑤ `scene_comfy_transactions.py`、`adapters/scene_comfy.py`、`adapters/comfyui.py`；⑥ `local_comfy_metrics.py`、既有恢复与socket测试。

具体第一步：在 `tests/unit/test_scene_stage_preparation.py` 写单worker/单槽/预算、parent拒绝及已有handle退出/PID复用拒绝的失败用例，随后实现设计规定的数据对象和pool；不再选择另一种驻留或证据协议。任务仍需显式启动；本交接不授权真实GPU或恢复旧生产。

## Risks

- 服务同phase复用已存在，真正可省的装载/空闲程度须测量，不能把方法调用当物理搬运。
- 预读可能增加CPU/内存而无收益，默认关闭；图像适配仍在协调线程，不把未覆盖步骤登记已并行。
- 父片未接受的子片不能预取未来尾帧或提交，人工审核返回时释放owned服务并丢弃准备结果。
- 旧测试夹具/交付reclaim问题保留具名限制；不得扩大范围改生产路径策略或默认启用LVA-02候选来追数字。
- 用户原有冷准入及LVA-01工作区改动保留；不reset/clean/整体暂存，无额外推理授权。
