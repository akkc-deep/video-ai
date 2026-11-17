# LVA-06 端到端复测、收益归因与性能回归设计

## Goal

完成 `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md` Order=6：将LVA-01至05的实际结论与新的固定素材本地端到端复测汇总为可复现JSON/Markdown，明确可采用、仅实验、拒绝和未验证项。保留正常/恢复、阶段/端到端、冷/热及人工等待的真实边界，不承诺倍数或恢复原生产。本设计和READY均不授权本项GPU。

## Scope

- 沿用原三类fixture：低运动、高运动、父子连续链；每类4次实际样本（process-cold1/warm3）。四种native输入为low/high/parent/child，低/高/父各93保留帧，子生成81/贡献77；最终低/高各4份93帧1080P，父子4份170帧1080P，16fps。不得减少或重复贡献帧。
- 五项实际决策没有产生已推广的新候选：LVA-02 strict、LVA-03准备关闭、LVA-04原quality40步/CFG3.5无LoRA、LVA-05 serial/libx264 medium/CRF18。baseline与final的行为profile相同；冻结两条报告身份但引用同一份新实测，禁止为了填对照表重复跑相同矩阵。原LVA-01历史数据独立展示，因计时/环境/调度边界不同不直接称因果before/after收益。
- 新交付仅为实验冻结/编排/计时/报告及必要恢复测试；不再优化生产guard、采样、模型驻留、I/O或编码，不改旧schema/intent/accepted、即梦链路、TTS文本/旁白/字幕或原已暂停run。
- 原已选素材来自LVA-01实际cases/fixture/original-request，而非生成测试图。旧run只读；新的Wan、超分、成片仅在本项具体清单获明确许可后创建的新 `E:/VideoAI/scratch/benchmarks/LVA-06-*` 根中执行。LVA-05授权不继承。

## Approach

### 直接输入与最终组合

依次消费总体设计全文；LVA-01设计、completion、gpu-experiments/gpu-results及timing-evidence；LVA-02设计/results；LVA-03设计/results；LVA-04设计/completion/results；LVA-05设计/completion/results/gpu-results/recovery；历史 `video-generation-performance-results.md`。身份文件采用完整Artifact，父/子按source_clip_id和requires_new_parent区分，不以共同fixture_id覆盖。

生产已有能力缓存、受保护输入证明、批量提帧/复制/合成单次解码均为历史输入，不认领新收益。新的quality使用原 `workflows/wan22_i2v_14b_api.json`（SHA `5f3768f6e83bf6be21287457c7c15e811d8f6949b7b5c5ac5460c267c8f98666`）/mapping；超分用原 `upscale_api.json`（SHA `a647f05940ce6b59de9bde8d5d53b9300bfe6b5174d900b3324eb6cd01680533`）/mapping。seed、宽高、原图、prompt摘要、frame budget、split/sampler/scheduler/shift全部逐case从原frozen request读取并封存，不重新选择参数。strict和原生backend保持，独立fast/Sage/cache/compile/prefetch/writeback/NVENC均不进入最终组合。

### 实验数据接口

新 `src/video_ai/experiments/final_local_video_benchmark.py`，只供本项CLI调用，无生产开关：

- 不可变 `FinalBenchmarkPlan(schema_version, task_id, profile, assets, fixtures, trials)`：task_id固定LVA-06，profile固定`quality_strict_serial_x264`；assets为角色→完整Artifact；fixtures有low/high/chain及其native source clip引用、完整原参数、预算、旁白/字体/接受来源；trials固定cold_1/warm_1/warm_2/warm_3。`identity_dict()`/`digest()`使用既有canonical JSON，不携带工具/logger/ContextVars。
- `prepare_final_plan(output: Path)->dict`：只读汇集来源和实际采用/拒绝结论，验证同profile关系，生成 `LVA-06-experiment-manifest.json`、新根列表、确切命令/样本上限和环境身份；不加载torch/模型、不启动服务、不生产媒体。若实际文件/模型/接受记录冲突即拒绝，不能改旧记录凑齐设计。
- `FinalBenchmarkSession(root: Path, plan_sha256: str)`：`record_selection_handoff()`、`enter_phase(name, trial=None)`/`finish_phase(...)`、`begin_review(kind, media_artifacts)`/`finish_review(actual_decision_artifact)`、`resume_original()`、`finish_batch()`。使用perf_counter计当前调用时段、UTC计跨人工/进程等待；记录schema_version、batch/trial/stage、source/profile/manifest SHA、实际原prompt_id和开始/完成事件，不把旁路计时字段加入Comfy POST。
- `run_final_batch(plan_path: Path, fixture: str)->dict`：只运行指定新批次或原批次恢复。调用既有LVA-01 `ExperimentClient`及quality `prepare/run_trial/run_child_trial` 的原intent/accepted/history协议，复用LVA-03 owned身份检查/关闭原则及LVA-05已修正的pinned启动、listener就绪和kill-on-close做法；本项observer接受LVA-06身份，不能伪装成LVA-05 profile。全部HTTP、durable JSON、晋升及质量绑定在协调线程。
- `summarize_final_results(inputs: list[dict])->dict`：只读已存证据，建立defaults/experimental/rejected/unverified归因台账；按实际mode/temperature/scope分组，线性插值P50/P95，空分母/未接受质量返回null及原因，绝不填0或用历史微基准推算新收益。

### 调度、人工门槛与真实端到端边界

选择与既有生产一致的**分阶段批次编排**。逐条跨人工等待保持Comfy驻留违反现有约束；新开fast/I/O方案又与已完成任务决策冲突，因此不另造第二条实现路径。这里的批次端到端是实际批处理链路，不冒充独立热片的全流程低延迟。

三类batch按low→high→chain串行，测量期间不运行其它batch/编码实验。每batch先持久化本次“已选素材交接完成”T0，随后才适配/复制图片、创建当前请求、启动服务。已有原选图/下载时间不计；不得沿用LVA-01旧时间或事后重建T0。预授权manifest身份研究单列，不当生成阶段收益。

low/high：一个新owned native阶段cold1/warm3→关闭→真实native审核→一个新owned超分阶段按四trial/全部帧串行→关闭→原字幕/旁白/libx264成片→技术检查→最终真实审核。chain：parent native四份→关闭/真实父片接受→child native四份（每份绑定对应新父片真实末帧和接受SHA）→关闭/真实子片及连续性审核→新owned超分阶段处理完整93+77×4→关闭→四份原旁白/字幕连续链成片→最终审核。不能预读未接受父片尾帧；没有用户决定不得自动把旧接受当新视频接受。同字节复用质量判断也只在用户明确允许并绑定实际新文件后记录，不能推断已观看。

每native阶段第一个实际请求标process-cold，后3个same-process warm；每超分阶段同样标注。不得把跨人工审核后新开的child服务称为parent进程warm。单GPU始终只有一个请求，不同时驻留Wan和RealESRGAN服务。全部三类batch常规共7个owned进程（native low/high/parent/child四个、超分low/high/chain三个）；失败setup单列。

Tend是该batch最后一份最终媒体技术完成，质量等待另记；同时保存每trial实际完成时刻。`batch_wall=Tend-T0`，`human_wait`为该区间内真实begin_review→实际决定的区间并集；`non_human_envelope=batch_wall-human_wait`仍保留协议/调度/非人工空隙。另列各非重叠阶段active span与idle/other waiting，不能把嵌套计时相加。每trial自T0到完成的envelope包含同批其它trial工作，明确标成批次调度包络；热native/超分局部P50/P95单列，不将包络称为独立热片延迟或累计吞吐。

最终质量全部接受后，batch有效视频秒为该批次接受的实际贡献帧合计/16，批次每可用秒成本用批次non_human_envelope/该值；未全部接受则null及missing条件。另列包含human_wait的batch_wall，不把各trial重叠包络相加。只对固定片段/连续链作局部端到端结论；未运行107场景整片就明确整片吞吐未验证。

### 媒体、计量与恢复

全帧提取/RGB/顺序/1920×1080证明复用已有批量实现；合成固定原字幕、旁白、字体、16fps及x264原命令。复用实际probe/PTS/完整解码证据；每份成片一次完整音视频验证，在同工具/同源强保护成立时复用，不能为填统计反复decode。帧hash/PTS必须覆盖全部贡献帧，不抽样、不删原history/raw来报存储收益。

记录启动/关闭、high/low采样、VAE/原生编码、trim/末帧、超分每帧/整批、合成/验证、实际hash/decode/producer/POST/GET计数、进程RSS、设备采样/低利用跨度、逻辑文件峰值。重计数不新增媒体读取；完整profiler诊断和轻量墙钟分开。物理装载/独占idle/kernel未测记null。原生方法和设备采样不可相加成墙钟。

恢复重建所有强内容/原所有权/父子和审核依赖；完成native/frame/composition receipt先验真后复用，direct POST/producer/decode均0（必要真实性读取不为0）。unknown仅查原ID，不建新POST或替换history服务；原扩散中间步无可靠持久化则标unknown/不可恢复，不能猜成功或创建热样本替代。已成功命令的完成receipt/相同工具输出可恢复提交，命令outcome unknown保留并拒绝自动重编码。运行锁丢失、模型/工具/来源/父片/接受冲突在新POST前拒绝。错误先保留，诊断/关闭失败只能附注；服务必须在向用户提出审核前退出。

### 授权矩阵和最终报告

离线先交付代码/fixture、full artifact清单、命令、新根与上限，再请求**LVA-06自身**许可；最多16次Wan（含父/子各4）、1,424次逐帧超分、12次x264成片；0新模型下载、0NVENC/fast、0旧生产恢复。baseline/final同profile只执行一矩阵；不同profile若实际发现则先拒绝冻结、不能临时多跑对照。遇真正兼容/质量失败可停止余下矩阵，如实列未执行，不能靠否决无关候选代替本项真实end-to-end缺失。

报告列：历史已采用优化、LVA-02/03仅实验且默认关闭、LVA-04不兼容、LVA-05局部观察/不默认采用与NVENC像素拒绝、最终新矩阵、正常/恢复、质量决定、计时/环境/样本局限。最终相关回归的历史路径夹具缺陷具名分列，不扩修即梦/交付reclaim等不相关行为。没有新GPU或人工决定不能把本项/项目标完成。

## Files

- 新 `src/video_ai/experiments/final_local_video_benchmark.py`：冻结plan、阶段/审核/批次clock、原ID恢复协调和归因汇总；不修改生产默认或schema。
- 新 `scripts/benchmark_final_local_video.py`、`scripts/observe_final_comfy.py`：offline/prepare-plan/获授权run-batch/recover/summarize入口；pinned owned服务及只读汇总。
- 新 `tests/unit/test_final_local_video_benchmark.py`、`tests/integration/test_final_local_video_benchmark_flow.py`：计时包络、同profile去重、纯数据、恢复/漂移、真实小型媒体与假transport。
- 新 `docs/task-designs/LVA-06-results.json/.md`、`LVA-06-experiment-manifest.json`、`LVA-06-gpu-run-state.json`：实施时才生成实际证据，当前只是指定交付路径，不声称已存在。
- 不改既有所有workflow/mapping、旧产物或原生产锁；仅在任务板回填本设计及后续真实结果。

## Tests

第一动作在unit文件写RED：`test_identical_final_profile_reuses_one_matrix_and_never_sums_trial_envelopes`。手工时钟T0=0、Tend=100、审核区间[20,40]和[30,50]时human_wait=30、non_human=70；四份完成包络不得相加，未全部质量接受时cost=null；profile相同只能请求一矩阵，任一身份改变在POST前拒绝。再实现上述类/接口。

另覆盖：父片未接受不能child请求/准备；native parent warm不能替代新child进程cold；审核前owned服务已关；PID重用/启动失败/监督进程退出关闭子进程；完成恢复0HTTP/producer/decode；unknown仅原GET；source同大小mtime回滚、工具/模型/parent/接受冲突；命令输出有文件无完成proof不得自动重编码；恢复时clock累计不重复记前次active span/审核区间，跨进程时钟倒退或缺失事件不得填0。

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_final_local_video_benchmark.py tests/integration/test_final_local_video_benchmark_flow.py tests/unit/test_local_video_metrics.py tests/unit/test_local_comfy_metrics.py tests/unit/test_scene_comfy_send_checks.py tests/unit/test_upscale_phase_lifecycle.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_final_local_video.py --offline --output E:/VideoAI/scratch/benchmarks/LVA-06-offline-results.json
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_final_local_video.py --prepare-plan docs/task-designs/LVA-06-experiment-manifest.json
```

期待新单元/集成通过；offline使用真实小PNG/FFmpeg、完整原序列和假HTTP，不导入Comfy/torch、不执行GPU；两份相同内容不同请求身份不混淆，normal/recovery直接计数可证，JSON/Markdown分层。prepare-plan只产具体可审查清单，不启动服务。真实run-batch命令在确切manifest/根/工具身份准备后写入本项命令文档并另获授权；本设计不伪造未来SHA或命令结果。已知旧flow初始化path-policy等失败保持具名，不把缺少GPU/质量写passed。

## Acceptance

1. 三类batch每类cold1/warm3完整固定输入和实际T0→Tend端到端数据可复现，阶段温度/人工区间并集/批次调度包络真实区分；12成片全帧/PTS/旁白/字幕/连续性与真实质量决定齐备。
2. 分层JSON/Markdown含阶段、局部P50/P95、批次可用成本或null原因、失败/重做、资源与物理未测边界。相同baseline/final复用一次新矩阵，不以阶段/包络相加、历史微基准或未接受视频伪称全片提速。
3. strict原ID恢复/异常拒绝和旧格式不退化，完成产物不重做；单GPU与审核/父子依赖及owned退出保持，normal/recovery直接计数有真实或明确离线边界。
4. 最终profile保持quality/strict/serial/x264；全部历史已采用/仅实验/拒绝/未验证决策有确切来源，无默认推广、付费、即梦修改或旧生产恢复。
5. 定向/离线及本项另获授权的实际实验、质量和完整最终报告齐备后才登记LVA-06/项目完成；缺失不填通过，未知/失败分支透明。

## Risks

真实GPU/人工时长尚未发生，环境可漂移；新manifest必须重新准入并记录。批次阶段化决定热样本端到端包络会包含同批排队，已固定单独报告，不作独立低延迟或全13306帧整片吞吐。三热样本分位数仅描述样本，不作统计置信。历史候选无稳定通用收益，最终复测可能仍无可采用新增优化，这是允许的实际结论，不能跳过本项真实测量。已知legacy fixture/交付缺陷不扩修；真正影响当前实验则先记录阻碍和恢复条件，不编造结果。没有未决定的产品功能或采用策略；未来GPU许可及真实质量是执行门槛，不是已获得的结果。
