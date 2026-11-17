# LVA-03 Comfy阶段生命周期与依赖感知准备设计

## Goal

在原质量、原请求身份及父子审核门槛下，测量并减少授权阶段的服务/模型重复准备和GPU空闲。任务板 `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`，任务LVA-03。只准备本设计，不在LVA-02会话实施或运行GPU。

## Scope

- 直接消费LVA-01冷/热节点/模型方法、设备采样和固定素材，以及LVA-02的严格默认与实验门槛。
- 审计并记录 `_OwnedService` / `_produce` 的真实阶段生命周期。当前 `_produce` 已在一次调用中懒创建单个service，并在finally关闭；`ensure()`已有handle时返回。不得把这个既有复用重新实现或计为新收益。
- 实现一个有界、只读的独立场景准备候选：图谱构造和选图文件预读。图像适配、输入晋升、request/graph/HTTP及所有不可变证据仍由持锁协调线程执行。首轮不把FFmpeg适配/写证据搬到worker；若这些步骤才是瓶颈，报告尚未覆盖，而不是引入第二种媒体receipt协议。
- 单GPU只允许一个Wan执行；同连续链串行。父片未接受的子片不预读其未来尾帧、不提交请求，不预造接受记录。
- 不跨人工审核驻留，不改Comfy采样、CLI显存/缓存参数、模型/LoRA、40步CFG、schema、旧unknown/accepted、不启用LVA-02候选校验。

## Approach

### 阶段与服务身份

新增诊断 `ScenePhaseMetrics`，内部接口 `event(name, *, clip_id=None, service_identity=None, seconds=None)`、`report()`；只接收脱敏标识和数字，不增加hash/stat/probe。记录phase enter/exit、ensure request/actual start、close、prepare queued/ready/consumed/discarded、submit/tracking和人工审核返回；原node-metrics继续区分CPU墙钟方法调用与实际权重装载，不能把loader节点或load_models_gpu调用数等同物理全量重载。

`_OwnedService.ensure()` 的已有handle分支先调用既有 `capability_identity()`；退出/PID复用/启动身份变化拒绝，不在存在旧intent时偷偷启动替代服务。现有首次ensure、manager所有权、close/finally、外部服务占用拒绝保留。默认生命周期已满足一次启动/一次关闭时只做验证与计量，不增加另一层常驻管理器。

新增阶段统计采用 `logs/production/scene-clips/performance/<uuid>.json`，由协调线程在原finally关闭服务后写入。仅诊断，不进入请求/冻结身份，不用于跳过任何恢复验证；异常关闭也记录异常类型及已完成统计，不能覆盖原错误或伪造成功。

### 有界准备候选

新模块 `scene_stage_preparation.py`：

- `PreparationJob` 为不可变数据：`clip_id`、完整source Artifact、`parameters_sha256`、`workflow_sha256`、预先验证的graph字节、`parent_required`。
- `PreparedSceneInput` 为不可变数据：原job key、source字节、实际SHA256、graph字节、读取秒数。`source_bytes`只用于预读及校对，不能作为已准入持久化媒体证明。
- `ScenePreparationPool(*, enabled=False, max_source_bytes=64*1024*1024, max_graph_bytes=32*1024*1024)`；`submit(job)` 返回bool，`take(job)` 返回匹配结果或None，`close()`。默认关闭，只有新的独立实验入口显式enabled。一个worker、最多一个未消费job，source+graph不超过96MiB。无后台GPU、服务、网络、store、RunLock、logger、reader或ByteGuard引用，不复制协调线程ContextVars。
- `submit`拒绝parent_required、非首片、过预算和占用槽位的job并返回False，回到原串行路径。graph仍用现有template和graph_for生成，原JSON_LIMIT保留；不改变其参数。worker只用普通文件读每块1MiB，同时计算SHA；最多读声明bytes+1且总量不越预算，读前后检查打开文件metadata和声明长度，SHA不匹配返回失败结果，不信任mtime。
- 协调线程在当前独立场景的首片提交/跟踪前，选择**计划顺序中下一独立场景的首片**作为唯一候选；不预取同场景子片、不重排执行。先按原guard验证job来源和工具/workflow，再启动worker与当前GPU等待重叠。取回时重核当前source Artifact、row parameters/workflow key及当前依赖；source漂移原路拒绝，准备超时/资源失败则丢弃结果走原串行读取，不伪造成功。
- 命中的graph在协调线程deepcopy后用于原request/graph写入；图像适配仍调用原 `_input`，同一producer/receipt/晋升逻辑不变。预读不能宣称减少严格hash；只有实际磁盘等待/空闲时间测量可报告收益。无收益时保持默认关闭。
- `close`置取消Event，worker每块前后检查，清空source/graph引用，最多等待2秒。不能取消的OS读取标记为未完成，worker不得发布结果或写任何证据；不得为等待跨过人工审核而保留服务。只有协调线程持久化诊断，late future无效。

### 正常与恢复

不把pool或图谱内存缓存持久化。新invocation/重启为空；先走既有preflight/collect_progress/validate_clip，已有媒体验真后跳过producer。已有intent仅恢复原GET；服务变化重新审查queue/history，绝不将未知请求当新任务提交。准备失败不能覆盖已有请求或已接受尾帧。

### 对照与采用

新增 `scripts/benchmark_scene_preparation.py --output <new-LVA-03-json> --repeats 4`，使用LVA-02隔离工具/真实FFmpeg/内存transport，分别baseline/candidate及normal/recovery，墙钟关闭完整profiler，方法/节点诊断另采样。输入、原ID、source/generated SHA、实际帧/PTS、POST/GET/producer/ensure/start/close、worker峰值/丢弃/取消均记录。source读取和准备耗时是CPU时间，不称GPU吞吐。

真实GPU验证必须另有明确授权，仅新建 `E:/VideoAI/scratch/benchmarks/LVA-03-*`。沿用 `LVA-01-gpu-experiments.json` 的低/高/父子固定输入与40步质量，冷进程1次、同进程热至少3次，baseline/candidate逐项对照；父/子人工接受仍分阶段，不跨审核保留owned服务。沿用本机原生默认模型管理，不加未验证高显存驻留开关。输出阶段时间、装载/卸载方法记录、GPU设备采样、空闲区间、失败/重做和质量结论。方法次数不能证明权重搬运时明确写“未测得物理装载次数”。真实数据缺失不能记LVA-03完成。

LVA-02已经证明减少逻辑工作未必更快。候选只有在真实授权样本墙钟/空闲可复现改善、帧/身份/质量与资源预算均保持时才可提出默认采用；否则交付明确否决和保持串行的结论，不强推新worker。

## Files

- 新建 `src/video_ai/runtime/scene_stage_preparation.py`：上述数据对象、只读有界pool及阶段统计。
- 修改 `src/video_ai/runtime/production_scene_clips.py`：已有handle身份核验、协调线程的候选排队/消费/丢弃及finally统计；保留旧media/transaction协议。
- 新建 `scripts/benchmark_scene_preparation.py`、`tests/unit/test_scene_stage_preparation.py`、`tests/integration/test_scene_stage_preparation.py`。
- 复用 `local_comfy_metrics.py` / `observe_local_comfy.py`，仅需要新事件时增量扩展，不改原LVA-01产物。
- 新建 `docs/task-designs/LVA-03-results.json` / `.md`，记录离线与授权GPU各自证据及未支持项。

## Tests

先RED后实现。worker单元验证独立首片命中、parent拒绝、单槽/96MiB预算、同大小mtime回滚SHA拒绝、graph/workflow/source key失效、取消/late future、worker无store/日志写、主线程消费deepcopy。服务fake验证ensure一次启动、多次活实例核验、退出/PID复用拒绝、异常close一次；源/锁/父片变化不提交，已有intent只GET。

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_scene_stage_preparation.py tests/unit/test_scene_comfy_transactions.py tests/unit/test_scene_comfy_send_checks.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/integration/test_scene_stage_preparation.py tests/integration/test_scene_validation_recovery.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_preparation.py --output E:/VideoAI/scratch/benchmarks/LVA-03-preparation-results.json --repeats 4
```

期待新专项通过；同一phase start/close各一次，所有证据写在协调线程，pool<=1未消费job，恢复producer/POST不增加。既知legacy模型/无效run/continuity路径/交付reclaim缺陷不得以修改无关生产规则掩盖。真实GPU命令在明确授权后绑定新实验root、工具/模型身份及固定输入，未执行时不填写通过。

## Acceptance

1. baseline/candidate冷/热阶段及服务/模型方法记录可与LVA-01比较；无重复实现既有一次启动复用。
2. 父片观察、真实尾帧、同链串行、原请求身份及协调线程不可变写入保持；测试和真实实验均无第二POST或已完成媒体重生成。
3. pool资源、取消/退出/late结果、来源/工作流变化拒绝有具名测试，人工审核返回时服务关闭且准备结果丢弃。
4. 真实授权实验报告实际减少装载/空闲的程度和限制；未改善则明确保持默认串行/不推广。缺GPU实测不能完成本任务。
5. 报告区分预读/图谱局部开销、实际GPU节点/设备采样与整片吞吐；后者仍属LVA-06，不把局部节省相加。

## Risks

- 现有同phase服务已经复用，模型方法次数不等于物理装载；不得以无证据的缓存/显存策略冒进。
- 图谱与选图可能已经被OS/Comfy缓存，预读会增加CPU与内存而没有收益，故默认关闭并保留否决分支。
- worker不能承载父片接受或持久化证据；OS读不可立即取消时只失效结果，不借口终止非owned进程。
- LVA-02候选默认关闭，不能同时启用混淆归因。原生产暂停；本设计不授权真实GPU或旧run恢复。
