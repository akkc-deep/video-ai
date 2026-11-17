# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`
- **Completed task:** LVA-05，已先登记COMPLETED，实际测量及不默认采用结论见 `docs/task-designs/LVA-05-completion.json`。
- **Next task:** LVA-06，按预定义Order=6选取，观察NOT_STARTED。
- **Design document:** `docs/task-designs/LVA-06-design.md`，已完整完成并关联任务板；独立fresh builder回答“nothing important left”。
- **Expected next status:** READY；本交接写入并关联后执行NOT_STARTED→READY，不启动实现或GPU。

## Next Task

LVA-06 — P2 / F：端到端复测、收益归因与性能回归。用原低/高/父子三类固定素材，复测最终quality/strict/serial/libx264本地链路及原ID恢复，交付分层JSON/Markdown、完整质量/资源/失败与可采用/实验/拒绝/未验证台账。

最终与baseline行为profile相同，复用一份新实际矩阵而非重跑相同“组合”；历史数据分开。采用现有分阶段batch编排，真实T0在本次选定素材交接后、适配/服务启动前；batch Tend、人工区间并集、非人工包络、单trial批次调度包络和native/超分局部冷/热P50/P95各自报告，不把重叠包络相加或冒充独立热片延迟。父片/子片/最终质量必须真实决定，审核前服务关闭；未知不盲发，完成媒体不重做。只有本项离线、另获授权的GPU矩阵和真实质量齐备，才可结束LVA-06/项目。

## Dependencies

### LVA-01 / 固定来源、真实基线与原观测协议

- **Artifact:** `docs/task-designs/LVA-01-design.md`、`LVA-01-completion.json`、`LVA-01-gpu-experiments.json`、`LVA-01-gpu-results.json`、`LVA-01-timing-evidence.json`；`scripts/benchmark_local_gpu.py`、`postprocess_local_gpu.py`、`observe_local_comfy.py`、`src/video_ai/runtime/local_video_metrics.py`、`local_comfy_metrics.py`。
- **Decision:** 原quality40步/CFG3.5、原seed/选中图片/旁白/字体/字幕及完整预算；low/high/parent各93保留帧，child生成81/贡献77，最终1080P/16fps。父/子按真实source_clip_id和requires_new_parent区分。
- **Rationale:** 已有真正选择及原生/超分/成片接受来源，适合冻结复测；原T0调度包络不能当本项新端到端墙钟。
- **Constraint:** 旧root只读；新的parent/child实际源和人工接受重新绑定。模型/node CPU调用不等于物理装载，设备样本不等于独占峰值；历史微基准不相加。
- **Usage:** 解析cases/frozen request建立新manifest；复用原intent/accepted/history、原质量graph、媒体规则及旁路计量。T0/审核等待本项实际记时，不沿用历史重建时间。
- **Readiness evidence:** LVA-01 completion供应16 native、1424超分帧、12份final1080P及真实接受；服务已退出，原生产未恢复。

### LVA-02 / strict及恢复边界

- **Artifact:** `docs/task-designs/LVA-02-design.md`、`LVA-02-results.json/.md`；`src/video_ai/runtime/scene_validation_pass.py`、`scene_comfy_transactions.py`、`scene_upscale_transactions.py`及既有恢复测试。
- **Decision:** 默认strict；guard候选不默认启用。首次准入/HTTP/证据/晋升/原ID与冲突检查保持；重启清空进程内证明。
- **Rationale:** 常规夹具逻辑入口减少但实际SHA/媒体工作未减、墙钟未获益；不可为最终组合擅自开启候选。
- **Constraint:** 不跨独立HTTP guard继承memo，弱保护严格回退，源/模型/工具/所有权变化和冲突accepted在POST前拒绝，unknown仅原GET。
- **Usage:** 新benchmark完成恢复直接计数0POST/producer/decode；离线覆盖部分中断/漂移和旧格式，不重新生成完成媒体。
- **Readiness evidence:** 214定向及具名真实媒体恢复交付；旧legacy模型/路径/continuity/交付reclaim缺陷已披露，不扩修或报全库通过。

### LVA-03 / 阶段生命周期、parent审核及采样边界

- **Artifact:** `docs/task-designs/LVA-03-design.md`、`LVA-03-results.json/.md`；`src/video_ai/runtime/scene_stage_preparation.py`、`production_scene_clips.py`、`scripts/benchmark_scene_preparation_gpu.py`。
- **Decision:** 既有owned阶段复用保留、准备候选默认关闭；一个GPU请求串行、协调线程写证据、不跨人工等待驻留；child仅在对应真实新parent接受后取实际尾帧。
- **Rationale:** 真实对照无可重复收益；节点缓存本来存在，不能再认领。严格所有权和有限关闭是最终编排必需边界。
- **Constraint:** 新native阶段cold/warm按各自进程定义，不能把child新进程算parent热；same-bytes质量绑定也须用户明确允许实际新媒体，不伪造观看。
- **Usage:** 保持default关闭，复用PID/start/服务实例核验、异常关闭、低利用采样的真实限定和新父子绑定流程。
- **Readiness evidence:** 32/32真实原生接受、完整父子连续性确认；88定向及真实阶段/恢复证据具名；owned测量及setup服务已退出，物理搬运未测。

### LVA-04 / 被否决的独立fast配置

- **Artifact:** `docs/task-designs/LVA-04-design.md`、`LVA-04-completion.json`、`LVA-04-results.json/.md`、`LVA-04-native-rejection-evidence.json`及独立fast workflow/mapping/provenance。
- **Decision:** 原quality保留；native双LoRA混合diff/diff_b/diff_m不兼容，distill否决；Sage/cache/compile/combination不启用。
- **Rationale:** 真实首个fast原ID在原子准入拒绝，0fast视频、未进采样，不存在可接受高速成片或已证明提速。
- **Constraint:** 不忽略未加载权重、不换引擎/flags或擅自打开4步；不把独立fast图变成最终默认，不重试失败原ID凑样本。
- **Usage:** 作为最终“rejected/unsupported/unverified”归因输入，只用原quality图；不要再跑同一已拒绝配置。
- **Readiness evidence:** 实际quality控制4份技术完成、fast失败ID及0重POST恢复、79定向通过；两owned服务退出，否决结论已COMPLETED。未新造fast人工接受。

### LVA-05 / 有界I/O、实际计量和编码拒绝

- **Artifact:** `docs/task-designs/LVA-05-design.md`、`LVA-05-completion.json`、`LVA-05-results.json/.md`、`LVA-05-gpu-results.json`、`LVA-05-gpu-recovery.json`、`LVA-05-execution-manifest-v2.json`；新实验pipeline/manifest/observer/encoding脚本及测试。
- **Decision:** 保持serial/libx264。prefetch方向混合；writeback父片有局部1.56%批次改善、其它小幅或回退，未建立稳定通用默认收益。NVENC虽更快但93/93RGB不同，rejected_pixel_contract；组合未执行，未验证，不等于已测拒绝。
- **Rationale:** 实际4类×3因子、各cold1/warm3共12阶段/48完整样本/4272唯一请求及所有RGB证明支持明确不默认采用，而非离线推断。原模型loader缓存已存在；方法计数不代表物理搬运。
- **Constraint:** 96MiB为逻辑payload，非RSS；强身份/单槽/协调提交/原ID保留，pinned Python/Comfy和listener就绪、child先于supervisor关闭及Windows Job不能丢。源真实接受由全RGB证明沿用为来源，不声称新的观看/quality-accepted，也不自动给LVA-06新生成媒体接受。
- **Usage:** 最终profile不开I/O候选/NVENC；借用原ID恢复、真实资源/低利用/媒体证据及已修正的启动做法，不把LVA-05仪器化wall当生产整片吞吐。
- **Readiness evidence:** 98定向通过；12真实完成批次恢复0HTTP/0媒体/0GPU；1408预读/1424写回全成功；全部测量服务exit0/finalized、原PID不存活且8189无监听。原软件编码与原接受视频逐字节相同，硬编技术拒绝后未做视觉接受；两setup问题及5旧路径fixture失败具名披露。原生产未恢复。

上述直接输入无决策冲突：最终quality/strict/serial/libx264一致，frame/旁白/字幕/质量/父子门槛及旧记录只读相同。所有局部/历史限制进入最终报告，不把未测填passed。

## Start Here

按序完整读：① `docs/task-designs/LVA-06-design.md`；② 本任务板LVA-06及本交接；③ 上述LVA-01来源/计时；④ LVA-02至05的实际设计、结果与完成证据；⑤ 总体设计、历史性能报告和所列脚本的真实恢复/owned/媒体接口。

第一动作：按完成设计在 `tests/unit/test_final_local_video_benchmark.py` 写 `test_identical_final_profile_reuses_one_matrix_and_never_sums_trial_envelopes` RED，用T0=0/Tend=100、重叠人工区间[20,40]/[30,50]断言等待并集30、非人工包络70、未全部质量接受cost=null、同profile仅一矩阵；然后实现规定的plan/session/summarizer接口。不要重新设计、先跑GPU或改生产默认。离线及具体manifest/根/命令准备好后才取得LVA-06自身GPU许可；本交接不授权执行。

## Risks

端到端按真实分阶段batch测量，per-trial包络包含批内排队，不能叫独立热片延迟或相加算吞吐。原历史T0不作为新实际起点。3热样本仅描述，不作置信结论；真实质量等待不可预造。新父片若未接受必须停止child；同字节不自动等于新用户决定。环境/源码可能漂移，未来必须新manifest准入。已知旧路径/reclaim等失败不扩修；实际阻碍实验时具名记录，不绕过。LVA-06尚未实施、未取得本项GPU授权，原生产保持暂停。
