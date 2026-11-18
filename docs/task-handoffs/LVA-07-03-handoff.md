# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`
- **Completed task:** `LVA-07-02`
- **Next task:** `LVA-07-03`
- **Design document:** `docs/task-designs/LVA-07-03-design.md`
- **Expected next status:** `READY`；设计已关联，写本交接后执行 `NOT_STARTED -> READY`。

## Next Task

LVA-07-03：是否投入的决策与具体环境/GPU资源清单。根据环境与 CPU 实测，交付继续、停止或证据不足的决定，以及 `docs/task-designs/LVA-07-environment-manifest.json` 和 `docs/task-designs/LVA-07-investment-decision.md`。只形成可审阅清单；不安装、下载、启动服务、GPU 或生成媒体。

验收要求固定来源/模型/拟用配置与资源预算；继续建议必须有具体动作和完整模型准入门槛，否则明确解除条件。最小 GPU 计划仅为未来 1 个 40 步低运动 control，通过技术与人工质量后才 1 个 4 步候选；本交接不授权执行。

## Dependencies

### LVA-07-01

- **Artifact:** `docs/task-designs/LVA-07-environment-review.json`、`docs/task-designs/LVA-07-environment-review.md`。
- **Decision:** 固定上游 a743 与 Comfy 2c75；原候选停止直接安装/推理，缺少完整节点环境证明。
- **Rationale:** 源码审查发现 mixed-delta 遗漏与必需依赖缺失；CPU 最小闭包不等于完整 runtime。
- **Constraint:** 不在生产补依赖/安装 Wrapper，不将源码符号存在视为注册通过。
- **Usage:** 建立环境/节点依赖、源码完整性及未验证配置矩阵，核定新投入清单。
- **Readiness evidence:** 原 18 文件小文本快照位于 `E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit`，只读保留；历史硬件观察 RTX5090D V2/24455 MiB，不是本轮空闲 VRAM 证明。

### LVA-07-02

- **Artifact:** `docs/task-designs/LVA-07-02-results.json`、`docs/task-designs/LVA-07-02-applicability-results.json`、`docs/task-designs/LVA-07-02-applicability-results.md`、`docs/task-designs/LVA-07-02-fix-design.md`；`patches/wanvideo-wrapper/manifest.json` 和 `lva07_img_policy.json`。
- **Decision:** CPU 任务已完成；支持的独立 unmerged/static 数学已有证据，原始 merged 的 block/head 遗漏已复现并继续禁用。精确 Low290 已获准不适用，不能通用扩展。
- **Rationale:** 30/30 测试，High1500/Low1459 原始输入通过真实解析最终保留及 CPU 目标 fixture 应用，290 不计消费/应用；小模型 pair 原子性、重复/移除和 scalar-FP8 顺序有证据。
- **Constraint:** 不冒认完整 14B、完整注册、low_mem_load、fast FP8 或视频通过；256MiB/侧的 CPU deepcopy pair 不能用于 14B。历史原生拒绝和原始 RED 保留。CPU 策略在真实模型上使用前须重新核对实际身份/schema及保留/应用证据。
- **Usage:** 判定哪些数学问题已解决、哪些完整 runtime/内存方案仍需设计；决定是否值得投入及明确后续前置门槛。
- **Readiness evidence:** 最终独立 21 文件部分副本 `E:/VideoAI/scratch/benchmarks/LVA-07-02-applicability/replay-wrapper`，commit `15ad15c292831865886b4fa9a2316188b0820035`，payload 时工作区干净；最终 exit0/44.81s/Windows峰值工作集1899302912 bytes，trace SHA `b2922754863c13a1e7737ea0cdfe2277e098e186115ffa6e1e54d8cff26c71f0`。原始证据位于同级 `final-payload-run`，不需要重跑。

### LVA-01

- **Artifact:** `docs/task-designs/LVA-01-gpu-results.md` 及其固定素材、原生质量/计时记录；比较细节辅以 `docs/task-designs/LVA-04-results.md`。
- **Decision:** 保留原素材、prompt/seed、768×432、16fps、93 帧和人工质量/连续性要求；后端切换不降低质量契约。
- **Rationale:** 原生实验提供既有基线，不能重复生成或用换模型/精度的差异冒充纯后端收益。
- **Constraint:** 历史 GPU 授权与样本不能授权新 Wrapper 运行；父子链继续遵守父片人工接受前不得生成子片。
- **Usage:** 准备最小两样本计划的输入、计时边界及可比性说明；不重跑已完成基线。
- **Readiness evidence:** 原生实际结果已交付；Wrapper 的技术、完整模型及人工质量尚无结果。历史基线只能用于规划比较。

## Start Here

依次读取 `docs/task-designs/LVA-07-03-design.md`、`LVA-07-wrapper-backend-design.md`、LVA-07-01 环境审查、LVA-07-02 最新结构化/文字结果、LVA-01 与 LVA-04 结果。

第一动作：在 `docs/task-designs/LVA-07-investment-decision.md` 建立设计规定的条件矩阵，将已通过的 CPU 数学、已知不支持的 merged 和未验证的完整环境/14B 准入分别填入来源与解除条件；随后据矩阵填写 manifest。无需重做设计或重跑 CPU payload。

## Risks

前驱证据层次不同但无冲突：07-01 的原候选停止结论未被 CPU 修复升级为生产可用。完整 checkout/节点依赖、14B 原子准入内存方案与拟用 FP8/offload 路径仍须评估；资源无法核定时应交付证据不足，不能猜数或直接启动实验。下一任务为 READY，只完成准备，不自动开始。
