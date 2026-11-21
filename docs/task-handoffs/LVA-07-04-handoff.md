# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md
- **Completed task:** LVA-07-03
- **Next task:** LVA-07-04
- **Design document:** docs/task-designs/LVA-07-04-design.md
- **Expected next status:** READY

## Next Task

LVA-07-04：隔离 worker、workflow 与恢复 harness。实现固定身份、单专家私有覆盖、原ID恢复与标准媒体；以小型真实CPU数学、合成媒体、独立CPU HTTP注册验证验收。不得执行真实14B加载/GPU采样或恢复生产。

## Dependencies

### LVA-07-03

- **Artifact:** docs/task-designs/LVA-07-environment-manifest.json、LVA-07-03-preparation-execution.json、LVA-07-03-node-probe-results.json、LVA-07-04-contract.json
- **Decision:** 值得有界隔离CPU/离线实现；完整模型仍待后项。
- **Rationale:** 固定244文件快照、102分发和13实际HTTP schema；现有原生T5桥接解决scaled_fp8直接loader拒绝。
- **Constraint:** 不改固定源码/环境；原T5不换模型；整数time步不宣称纯后端等价；未来资源下限仍需满足。
- **Usage:** 封存profile、图及worker来源。
- **Readiness evidence:** 两CPU服务已结束/端口关闭；结果exit -1为强制退出，非graceful。GPU/完整模型未验证。

### LVA-07-02

- **Artifact:** docs/task-designs/LVA-07-02-applicability-results.json、patches/wanvideo-wrapper/lva07_img_policy.json、lva07_mixed_delta.py
- **Decision:** 仅修复unmerged；2959适用/精确290不适用，control零LoRA。
- **Rationale:** 实际源payload CPU证据；merged有遗漏。
- **Constraint:** 不放宽旧256MiB helper；不deepcopy14B；新单专家只clone静态目标，实际模型准入另做。
- **Usage:** 新owner/preflight/静态覆盖/动态安装及CPU小fixture。
- **Readiness evidence:** 原30项CPU验证通过，非14B应用证明。

### LVA-02

- **Artifact:** docs/task-designs/LVA-02-design.md、src/video_ai/experiments/wan_fast_experiment.py、scripts/benchmark_local_gpu.py
- **Decision:** intent先落盘，unknown不重POST，完成原媒体先验真复用。
- **Rationale:** 原ID恢复必须防重复生成。
- **Constraint:** 不改生产协议；重启失效进程证明；父片/尾帧/profile重绑。
- **Usage:** 只复用durable ExperimentClient协议和媒体原语。
- **Readiness evidence:** 前项COMPLETED，定向恢复验证记录见任务板。

## Start Here

按顺序读 LVA-07-04-design.md、LVA-07-04-contract.json、LVA-07-04-plan.md，再读上述直接输入。第一步为profile/graph漂移、control零LoRA和unknown不重发写失败测试，在隔离分支实施。

## Risks

完整模型内存、实际FP8/offload/采样及质量仍未知。CPU fixture不能升级为14B通过；LVA-07-05须独立GPU授权及资源满足后开始。
