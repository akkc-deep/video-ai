# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`
- **Completed task:** LVA-03，已登记COMPLETED，32次真实原生和人工质量/连续性接受，结果 `docs/task-designs/LVA-03-results.json` / `.md`。这只是顺序前驱，不是LVA-04的技术依赖。
- **Next task:** LVA-04，按预定义Order=4选取，观察NOT_STARTED。
- **Design document:** `docs/task-designs/LVA-04-design.md`，已完成并关联本板Design document。
- **Expected next status:** READY；本交接写入并关联后执行NOT_STARTED -> READY，不启动实现、下载或GPU。

## Next Task

LVA-04 — P1实验 / D：独立Wan高速配置与质量验证。创建隔离的fast workflow/mapping/provenance和实验task的quality/fast_experimental身份；先验证官方1022 I2V A14B high/low LoRA配对4步recipe，再逐项记录SageAttention、双专家缓存、compile/驻留与组合的支持或拒绝结果。原40步图/默认质量及旧任务恢复字节保持，严禁只打开原图的未配LoRA4步开关。

完成标准为专项设计的五条Acceptance：独立完整身份、真实单变量记录或明确拒绝、原帧/父子/恢复约束、实际技术与人工质量结论、局部和端到端边界。没有本项真实GPU不称fast validated；默认采用仍需另行确认。

## Dependencies

### LVA-01 / 原质量基线与固定输入

- **Artifact:** `docs/task-designs/LVA-01-completion.json`、`LVA-01-gpu-experiments.json`、`LVA-01-gpu-results.json` / `.md`、`LVA-01-timing-evidence.json`；观测 `src/video_ai/runtime/local_comfy_metrics.py`、`scripts/observe_local_comfy.py`。
- **Decision:** quality保留40步/CFG3.5、high15/low25、原seed、768×432/16fps及原帧预算；原workflow SHA `5f3768f6e83bf6be21287457c7c15e811d8f6949b7b5c5ac5460c267c8f98666` 不变。
- **Rationale:** 已有16次原生、1424帧超分和12份最终1080P技术/人工接受，是对照输入；方法/loader计数不等于物理权重搬运，原T0包络不可相加当整片吞吐。
- **Constraint:** 固定初始素材和帧预算；每profile子片必须用该profile新生成并接受父片的真实末帧，不能借quality父片掩盖fast接缝。旧生产暂停，历史GPU授权不自动覆盖新LVA-04下载/推理。
- **Usage:** 冻结原quality与新fast的独立实验身份，复用固定fixture/观测口径，分别比较冷进程1次/同进程热3次，人工质量单列。
- **Readiness evidence:** 本板LVA-01 COMPLETED，completion.json明确16原生及12成片已接受，所有原owned服务关闭；基线存在且不能被本项重写。

### LVA-02 / 冻结与恢复边界

- **Artifact:** `docs/task-designs/LVA-02-design.md`、`LVA-02-results.json` / `.md`；`src/video_ai/runtime/scene_comfy_transactions.py`、`scene_validation_pass.py`；`tests/scene_validation_helpers.py`、`tests/integration/test_scene_validation_recovery.py`。
- **Decision:** 默认strict保留；不把LVA-02候选默认开启，不跨独立HTTP guard共享memo/捕获，不继承worker中的协调线程证明。
- **Rationale:** 逻辑工作下降并未带来正常夹具墙钟收益，原报告明确否决默认采用；已完成媒体必须先验真复用，unknown只恢复原GET。
- **Constraint:** 原HTTP、intent/accepted、queue/history、模型/tool、晋升及父片接受边界不变。新profile只进入新实验task的冻结/request/graph/恢复证据，不修改原生产options/schema或旧任务身份。
- **Usage:** 新profile client包装已有durable协议；漂移在POST前拒绝、完成恢复0POST/0producer，不写第二种未知结果自动重发路径。
- **Readiness evidence:** 本板LVA-02 COMPLETED；214定向证明/事务/socket、5真实媒体/超分恢复及22媒体性能测试通过。已知legacy模型/无效run/continuity路径/交付reclaim缺陷具名披露，不当作本项已经修复。

### 官方来源研究 / 尚未下载或实测

- **Artifact:** `docs/task-designs/LVA-04-source-research.json` 及专项设计里的官方HF模型卡/固定revision参考图链接；revision `57adea585d1d21085e2dfc91ce3c7b646cdd9345`，两文件的精确bytes/SHA和4步sigma已记录。
- **Decision:** 第一候选为1022 I2V A14B rank64双LoRA、各强度1、原生Euler/simple/shift5/4步/CFG1/split2。新增进程内LVA04LoraPair双专家原子准入；不装WanVideoWrapper或merge原base。
- **Rationale:** 原图4步开关的model true/false都直连同一UNET，没有LoRA；官方参考实际为Wrapper图，不证明当前native适配成立，必须严格检查patch覆盖/shape/sigma并由真实质量回答。
- **Constraint:** 当前没有loras目录、sageattention或triton，原生无已核验TeaCache/MagCache。按设计缺失即unsupported/拒绝，不静默fallback或安装包，不填未运行数据，不预设提速倍数。
- **Usage:** 使用固定revision及LFS SHA写新provenance，先做小夹具RED/GREEN和离线强身份/恢复测试；权重下载/GPU在具体manifest和命令准备好后另获本项授权。
- **Readiness evidence:** 已只读查询官方metadata和本机模块/原生源码，没有下载权重、安装依赖或执行LVA-04图。此事实可开始实现/离线验证，不代表fast模式已兼容或验证。

LVA-01的原质量/素材与LVA-02的旧身份/严格恢复不冲突：fast仅是新的隔离实验身份，quality和旧任务不变。来源/参数由专项设计固定，未知兼容性有确定失败分支，不由下一工作者临场替换模型或采样器。

## Start Here

按序读：① `docs/task-designs/LVA-04-design.md` 全文；② 本板LVA-04与本交接；③ 上述LVA-01固定输入/基线与LVA-02严格默认/恢复结论；④ `LVA-04-source-research.json` 及原workflow/mapping；⑤ `runtime/workflows.py`、`scripts/benchmark_local_gpu.py`、`observe_local_comfy.py`、事务/HTTP验证测试。

第一动作：在 `tests/unit/test_wan_fast_profiles.py` 写缺LoRA/错SHA/high-low调换、quality原图SHA不变、新profile漂移拒绝的RED用例，然后实现设计规定的 `WanFastProfile` / `load_profile` / `freeze_profile` / `verify_profile`。不要从下载模型、启用4步开关或再次设计方案开始。任务需要用户显式启动；READY只是设计和入口已准备。

## Risks

原生LoRA与既有fp8_scaled兼容性、实际sigma和fast质量尚未验证；不同runtime例子不是本机成功证据。缺失Sage/Triton与未核验cache有明确拒绝分支；TorchCompileModel关闭动态VRAM可能OOM。CPU局部、方法调用、设备采样和整片吞吐不能混称；不跨审核驻留、不重复大模型hash、不重发unknown、不改即梦或原生产。本交接未给予下载/安装/新GPU授权。
