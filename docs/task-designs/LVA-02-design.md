# LVA-02 重复校验精简与断点恢复正确性设计

## Goal

减少默认 `paragraph_jimeng_v1` 路径中同一次同步检查重复解释、核验共同依赖的成本。新生成与恢复保持原请求、原 ID、全部媒体帧、人工观察和不可变证据；已有产物先验真再复用，未知任务不重发。

任务板：`docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`，任务 `LVA-02`。直接输入为已完成的 LVA-01，完成依据 `docs/task-designs/LVA-01-completion.json`。本文件完成设计，不实施代码，不授权恢复旧生产。

## Scope

- 修改 `SceneClipStore` 和默认 `SceneMediaStore` 的重复 Artifact 检查、同一同步检查中的重复目录集合核验，以及 composition 捕获前后的共同检查。
- 保留 `verify_global` 调用及全部所有权、执行策略、连续性、模型/tool stamp、当前 request/graph、父片接受检查；将其内部可证明相同的工作复用。模型 stamp 是 metadata 检查，不认领数十 GB 模型重复哈希收益。
- 仅在现有 Windows whole-input 原生保护窗口内做有界、线程内、单次同步检查的复用。不增加 immutable roots，不保护当前可写输出、manifest、HTTP body 或临时文件来换取命中。
- 用故障注入验证完整恢复链；以隔离真实 FFmpeg 媒体及内存 Comfy transport 比较调用数、实际哈希/解码及墙钟。
- 不改即梦模块、配置/持久化 schema、采样/帧数、服务生命周期、并行调度或发布；不实现 LVA-03～06。
- `_technical` 已有 `@inspection_reuse()`；本项保持其 producer/source_info 代码原样，用新生成/恢复测试确认已有内容与工具身份缓存有效。不再实现一次相同优化。
- 不重做已有 object_info/轮询缓存、批量 PNG 证明、帧复制批次检查、音视频完整解码合并、revision/protected-read 冷准入优化，不覆盖用户现有 `reference_image_records.py` 等冷准入改动。

## Approach

### 实施实测后的采用门槛（2026-11-15）

完整候选已实现并按本设计执行四次strict/candidate真实FFmpeg对照。正常fixture严格Artifact工作12,876→8,982，但墙钟18.908746→20.756011秒，实际SHA和解码不减；因此采用下文原定“候选无收益保留strict”分支。生产窄guard默认不创建新read-pass、保持strict；新增 `candidate_scene_validation()` 仅在离线实验上下文显式启用候选接线，`scene_validation_pass()` 的显式作用域及所有strict传播规则保持。新增内部 `scene_guard_validation(*stores)` 在每次回调时读取实验标志，避免构造guard时冻结启用状态。没有新增配置或持久化字段。

生产规划硬性限制fast 768×432/quality 1280×720；真实生产fixture使用原768×432而非下文预想的128×72，未更改生产约束。常规benchmark未直接spy producer，保留null并从原receipt提供限定来源的成功统计；实际逐帧PTS从本次原probe记录提取。原样本直接glob扫描计数不完整，不作目录收益依据；另有同规则目录放大样本4→2、弱保护4→4。细节及原数据见 `LVA-02-results.json` / `.md`。这些限制不改变未知请求、所有媒体帧及恢复验真要求。

### 已确认依据与方案选择

总体方案第4节已决定可靠内容证明、作用域复用和弱保护严格回退。技术设计选择复用现有 `ByteGuard`、native input window 和 `protected_read_pass`，只加薄的同步检查作用域。长期缓存验证成功标志无法保留写入、目录集合和线程边界；删除 guard 会丢失独立拦截价值，均不采用。

LVA-01 离线真实生产 fixture：正常 hash_file 入口13,545、实际文件 SHA 6,704、媒体进程79；恢复分别1,383、1,771、34。global 依赖循环有6,030次 `validate_artifact` 调用，send guard 有6,270次。入口数不等于物理读取；主 profiler 的开关扰动约2.5倍，不能拿其耗时当未观测性能。真实 GPU 报告显示 high/low 采样为主要原生耗时，因此本项不承诺整片倍数。

### 新增内部接口与寿命

新增 `src/video_ai/runtime/scene_validation_pass.py`，只提供内部接口：

1. `scene_validation_pass(*, reuse=True)`：contextmanager。最外层可复用scene scope必须显式建立 `protected_read_pass(fresh=True)`，即使已有上游native pass也不借用其退出责任；只有同线程嵌套的scene scope借用本scene scope自己的状态。这样每个独立guard都在返回前完成自己read-pass的flush。状态保留thread ID、现有whole-input window强引用、自己新建的read-pass状态/代次、store强引用、Artifact证明表及失效标志。退出清空全部表；异常不留下可复用状态。
2. `validate_artifact_once(store, value, strict_validator)`：返回原严格 validator 的 `Path`，不改变异常契约。`strict_validator` 是绑定方法而非另一个缓存入口。畸形 value 直接走严格路径，不能因构造 key 先改变错误类型。
3. `verify_inventory_once(directory, expected, *, recursive, strict_check)`：无返回值。复用同路径、同扫描规则、同完整 expected 集合的目录检查；失配沿用原拒绝异常/信息。无有效作用域时调用 `strict_check`。

缓存最多4,096个 Artifact 证明；单次capture上限沿用现有32,768文件/65,536 inventory entries，整个新scope累计证明的文件依赖边和inventory entries各不超过65,536。表容量/剩余预算不足时在新增capture前关闭该项复用，或在成功capture后不登记超出总预算的证明；不能保存不完整证明，不通过分批截断建立成功记录。raised CaptureLimit的规则另见下文。

`reuse=False` 仍创建可嵌套传播的禁用marker，即使外层尚无native窗口；但不创建新的native read-pass，不启用Artifact memo，也不调用新的inventory复用路径。所有helper直接走原strict validator/scanner。内层不能重新开启reuse；原项目本来存在的inspection/protected-read等优化保持原样。这是benchmark原路径基线，不是仅关闭Artifact memo的混合模式。

### Artifact 首次与命中路径

`SceneClipStore.validate_artifact` 保持签名，将原函数体原样移动到 `_validate_artifact_uncached`，经 `validate_artifact_once(self, value, self._validate_artifact_uncached)` 调用。`SceneMediaStore.validate_artifact` 的原有 repair-origin 与 lexical 校验仍先执行，再调用 super；不跨 store 共享语义结论。

首次候选先确认主Artifact已有现存native deny-write/delete lease且identity的path/bytes/SHA与value匹配；没有则直接strict，不为了memo额外打开/冻结文件或提升writable root。符合条件且没有外层capture时，把严格验证包在新增 `capture_reads` 中，成功后 `capture.finish()` 得到完整ByteGuard。非Windows、窗口关闭、其他rendering mode不缓存。

若进入cache miss时 `_captures.get()` 已非空，不叠加新的memo capture，直接执行原strict validator，使原外层完整观察它本来会观察的全部读。不登记该次memo。已有完整memo的命中仍可verify/replay到外层；replay使外层超限时必须传播，不能回退并声称外层证明完整。

key 包含：store 强引用、其实际类型、frozen 强引用、run/root、revision guard 绑定、严格实现的 function 身份、完整 `(path, bytes, sha256)`。相同 path 的另一身份不得覆盖既有成功记录。调用方提供的新/重绑 Artifact 必须重新严格验证；不只比较 path/mtime。

命中先核对作用域/线程/window/read-pass 仍有效、store 与 frozen/实现/根绑定未变、原主文件 lease 仍存在且身份相同，然后 `ByteGuard.verify()`，并 `replay_guard()` 向外层 capture 重放依赖，最后返回首次结果。ByteGuard 的可变/未保护附加依赖仍按现有完整字节/集合协议检查，不能因主文件已保护而省略。validator 的非字节义务不能隐含丢失：ownership/execution/continuity/tool/model 由下述外围保留；repair/revision来源若有现有 capture 观察不到的依赖，该验证形式保持 strict，不启用 memo，并用测试具名记录原因。

证明命中失败必须清空/失效并传播拒绝；不捕获后重新读取并把新内容登记为成功。ByteGuard的内容/集合失配转为 `ProductionRefused('cached scene validation proof changed')` 并保留cause；既有ProductionRefused/文件异常/取消/deadline原样传播。

仅memo miss、进入前没有外层capture、失败后新增capture已完全退出且当前capture栈仍为空时，可以将 `CaptureLimit` 视为本次memo尝试失败：丢弃该次全部捕获，关闭当前scope后续memo新增，在新增capture之外执行原strict validator一次。若strict原路径自身仍报limit则原样传播。绝不清除现有Capture的failed标志，不修复/重建调用者外层证明；miss本来有外层、hit验证/replay、或退出后仍有活动capture时的CaptureLimit全部传播。其他异常没有重读回退。store的frozen/root/revision/实现绑定在同一scope内被替换时直接拒绝；只允许新增不同path的完整严格验证，不接受同path的新baseline覆盖。

### 目录与实际边界

有效作用域内部使用既有 `_Inventory` / `verify_read_inventory`：recursive 对应 `revision_json`，直接 `*.json` 对应 `json_direct`，expected 使用完整排序绝对路径集合。入口先保持原 lexical/path-policy 校验；不得以目录mtime代替扫描。第一次及作用域退出仍执行完整集合检查，同一 read-pass 内相同 spec 可借用现有缓存；遇到不同 expected 集合、重定向路径或新增/删除必须拒绝。向外层 capture 登记 `observe_inventory`，不遗漏传递依赖。无保护窗口时完全保留原 scanner/拒绝逻辑。

只在以下不包含实际写入或网络等待的同步区域建立 `scene_validation_pass`：

- `SceneClipStore.capture_guard` 返回的 `guard()` 整体。
- `SceneMediaStore.capture_guard` 返回的 guard 整体；保留其已有 global/paths 重叠过滤规则及 request/graph 绑定。
- `production_scene_composition._capture_composition_guard` 的完整同步只读/内存绑定过程，覆盖前后 base/store 检查。

不包装整个生产 entry、整片段 producer、整帧循环、HTTP request/response 生命周期或 `_record_http` 两次落盘为一个作用域。单独调用 `verify_global` 时无新 pass，保留严格原路，避免无重复时反而增加结束扫描。内部 Artifact/目录 helper 在上述区域受益，其他调用严格执行。

每次 socket headers/body 发送前的 guard 是独立作用域；guard 返回前必须完成 native read-pass 的退出检查。HTTP body 写前、metadata 写前仍分别 guard，之间不共享缓存。生产写入仍由持锁 caller 完成，线程限制和 fsync/rename 顺序原样保留。

现有 `invalidate_protected_read_pass` 在写入/checkpoint/window关闭时使借用的 read-pass 失效；helper 每次访问检查原状态仍是当前 active pass/代次。不重新激活被关闭的 scope。复制 context 到其他线程或原作用域关闭后，只能严格回退，不持有 reader/deadline 或打开额外服务。

### 必须保留及候选处理表

| 位置 | 本项动作 | 必须保留 |
| --- | --- | --- |
| `SceneClipStore.verify_global` | 共同 Artifact/目录进入上述 helper | 每次 assert_owned、revision/执行守卫、模型 stamp |
| clip/media `capture_guard` | 同次同步回调中借用证明 | 当前 request/graph 内容、父片观察集合、新子片连续性接受、每实际 socket 写前检查 |
| `SceneMediaStore.verify_captured_bytes` | 相同 Artifact/目录按同一规则处理 | continuity/read certificate、revision、empty/absent、tool/execution语义 |
| `_capture_composition_guard` | base/store 前后检查共享目录/read-pass，Artifact仅同store memo | merge冲突检查、来源/工具身份、所有晋升/commit调用 |
| `_technical` / `inspect_video` | 不修改既有 inspection_reuse；验证正常与恢复 | 恢复首次完整 probe/PTS/decode、trim及末帧准确位置 |
| `_record_http` / transactions | 不删 guard，不改格式与ID协议 | intent、body/metadata、重复/矛盾 accepted、queue/history一致性 |
| revision/公共 verification | 不更改已有低层实现/immutable roots | 同大小/mtime回滚、句柄/路径/所有权、弱平台严格回退 |

### 恢复与故障行为

新 public invocation、进程重启、线程切换都不能恢复本项内存 memo。原 durable intent→accepted ID→queue/history→媒体→提交路径完全保留。已完成视频/PNG先用原 receipt、完整技术/像素及身份链验真，再跳过 producer；未知 POST只 GET 恢复原ID，恢复不了则保持未知并拒绝替代提交。服务换 PID/启动时间不复用能力证明。

父片 accepted、observations 集合、真实末帧、子输入任一变化必须拒绝旧子绑定；新父片接受后只在原协议允许的新任务中重新绑定，不能改写原 intent 或把旧子记录迁移到新身份。正在执行的扩散步骤不承诺恢复。

### 对照基准与结果结构

新增 `scripts/benchmark_scene_validation.py --output <new-json> --repeats 4`。仅创建新的 `E:/VideoAI/scratch/benchmarks/LVA-02-*` fixture，复用测试的 `prepared_wan/OfflineWan/generate` 逻辑到独立可导入 benchmark helper；真实FFmpeg/FFprobe，内存transport，禁外网/GPU/旧run写。每种 normal/recovery、strict/candidate 各4个样本，fixture与内容一致；strict 用外层 `scene_validation_pass(reuse=False)`，不修改配置或持久化记录。

真实媒体固定128×72、16fps、至少3帧；另用32个共同Artifact、4次相同guard做受保护与弱保护的放大样本。benchmark内部只读计数 spy 记录 `_validate_artifact_uncached`、目录scanner、model stamp及guard边界；LocalVideoMetrics另记录真实文件哈希/字节与媒体进程。wall对照在关闭完整profiler下运行；详细调用报告单独采集，不把2.5倍观测扰动记为优化收益。

JSON固定包含 environment/tool SHA、source fixture/内容身份、模式、温度/重复号、wall_seconds、逻辑入口/严格验证/证明命中/实际SHA字节/scan/probe/full-decode/POST/GET/service确保计数、原ID/输出SHA/frames/PTS、拒绝及恢复场景结果。Markdown逐候选列before/after、实际减少项和未支持项。不扫描数十GB模型；身份引用LVA-01已有环境证据。候选无收益或无法保持保护时保留strict，具名报告，不承诺固定倍数。

## Files

- 新建 `src/video_ai/runtime/scene_validation_pass.py`：上述有界线程内证明复用接口。
- 修改 `src/video_ai/runtime/scene_clip_records.py`：拆出严格 validator、guard窄作用域、目录helper。
- 修改 `src/video_ai/runtime/scene_media_records.py`：默认路线 guard/captured-byte 目录接线，其他路线严格原样。
- 修改 `src/video_ai/runtime/production_scene_composition.py`：只包裹 `_capture_composition_guard` 同步捕获过程。
- 新建 `scripts/benchmark_scene_validation.py` 及小型 `tests/scene_validation_helpers.py`：独立fixture/内存transport/真实媒体基准，不导入或运行真实生产任务。
- 新建 `tests/unit/test_scene_validation_pass.py`、`tests/unit/test_scene_validation_boundaries.py`、`tests/integration/test_scene_validation_recovery.py`，扩充既有clip/media/HTTP恢复测试。
- 新建 `docs/task-designs/LVA-02-results.json` / `.md`，为 `LVA-01-validation-ledger.md` 各候选增加本任务最终去留依据，不覆盖原基线数字。
- 不修改 `production_scene_clips._technical`、即梦模块、已有底层 `verification.py` / `_protected_continuity_inputs.py`、用户冷准入文件或任何旧生产产物。

## Tests

先写失败用例，再实现对应接线。使用 `E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8`，全部新fixture，不启动GPU或付费调用。

| 定向场景 | 期待结果 |
| --- | --- |
| 同store、同callback、已有强lease的相同Artifact；嵌套capture | 严格validator一次；后续证明命中，依赖完整重放；外层证明仍能拒绝漂移 |
| 不同store/value/frozen/root/实现/原lease、畸形输入 | 不误命中；原错误/严格回退；无部分成功缓存 |
| 表预算、无外层的本地CaptureLimit、有外层或replay超限 | 预算预先回退；本地完全退出后strict一次；外层/命中超限传播，外层failed不能被清掉 |
| 已有native pass包住scene scope；独立guard连续调用 | 每个最外scene scope建立fresh=True并在返回前flush，嵌套scene scope才借用 |
| 外层无window时reuse=False，内层后来进入window | 所有新Artifact/目录/read-pass复用均保持关闭，strict基准不被新机制污染 |
| 非Windows/无window/原scope关闭/foreign copied context | 每次完整strict，不借用线程或过期状态 |
| 同大小替换、恢复mtime、symlink/junction/文件身份改变 | 原生保护阻止或原验证拒绝，不能通过清缓存重读接受 |
| 相同目录/不同depth规则；新增/删除/empty/absence变化 | 精确扫描语义、结束检查及相应原拒绝保留 |
| pass中写入、checkpoint、锁owner变化、模型/tool stamp变化 | memo失效/拒绝；headers/body/响应body/metadata每个边界仍检查 |
| 父片观察/目录/末帧变化，旧子输入、缺失或冲突接受 | 新子不能提交，旧绑定不能被悄然重建 |
| 新生成/generated成功后恢复/错误帧数/trim/末帧 | 既有inspection_reuse命中，新scope恢复完整验真，SHA/帧/PTS相同 |
| 提交前、POST后未记ID、执行中、成功未验收、晋升前后 | 原ID GET恢复或原拒绝；无第二POST、无重复producer |
| 超分N帧后、最终合成中断、新旧schema混合、服务重启 | 验真已完成prefix/候选；只补原任务未完成部分，重新审查队列/history |

命令与期待：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_scene_validation_pass.py tests/unit/test_scene_validation_boundaries.py tests/unit/test_scene_clip_records.py tests/unit/test_scene_comfy_transactions.py tests/unit/test_scene_comfy_send_checks.py tests/unit/test_scene_upscale_transactions.py tests/unit/test_protected_continuity_inputs.py tests/unit/test_continuity_byte_guard.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/integration/test_scene_validation_recovery.py tests/integration/test_production_comfy_recovery.py tests/integration/test_scene_clip_local_failure.py tests/integration/test_scene_media_recovery.py tests/integration/test_scene_composition_recovery.py -q -p no:cacheprovider
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 -m pytest tests/unit/test_scene_media_performance.py -q -p no:cacheprovider -k "not test_owned_service_cache_identity_rejects_pid_reuse"
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_validation.py --output E:/VideoAI/scratch/benchmarks/LVA-02-validation-results.json --repeats 4
```

期待专项全通过、benchmark有JSON/Markdown且四次身份一致；protected放大样本的相同Artifact严格验证从4次到1次，弱保护仍4次；正常/恢复POST与producer计数不因优化增加。默认生产fixture的真实减少量单列，不能把人工放大样本当生产倍数。既有 `test_owned_service_cache_identity_rejects_pid_reuse` 缺 `process_identity` 的fixture错误已有独立证据，本项不修改无关源码绕过；具名排除并在结果记录，不宣称全库无失败。所有命令为后续实施验收，设计阶段未执行。

## Acceptance

1. 每个启用的复用点有原台账、scope/key、强保护条件、失效及严格回退说明；没有未经证明的guard删除或持久化格式变化。
2. normal/recovery对照分别给出逻辑调用与实际哈希/解码、原ID/帧/PTS/SHA、无profiler墙钟及失败/重做记录；至少重复共同依赖的strict工作实际减少，弱保护等价。
3. 上述提交、响应落盘、晋升、父子接受和恢复故障矩阵全部保持拒绝/恢复语义，已完成产物不重生成，unknown不重POST。
4. 原质量/全部帧/1080P要求及生产暂停状态不变；历史优化与用户冷准入改动不认领、不覆盖。没有新真实GPU实验时明确只报告验证/媒体局部收益。
5. 交付实现、定向验证、benchmark JSON/Markdown及逐点结论；未支持候选保留strict。达到这些条件才可完成LVA-02，不以设计或READY表示已实现。

## Risks

- 目录在同步检查期间可新增；必须在guard返回之前完成pass退出复核，不能跨实际写入/网络等待延长窗口。
- 已有强保护覆盖范围有限，默认生产fixture可能大量落回strict；禁止扩大immutable roots或放松错误来追求数字。放大样本与实际fixture分别解释。
- capture不能自动观察任意裸stat/手写扫描。修复/继承来源的非字节义务不明时保留strict，只有证明依赖完整的形式才能启用memo。
- 现有首要GPU瓶颈不会由本项改变；不能把模型stamp的metadata调用数当重复模型读取，不能把profiled墙钟或局部收益外推整片。
- 原工作区包含用户其他未提交改动及LVA-01新文件；不重置、不清理、不整体暂存。设计无待用户选择的产品/协议要求，未决的运行结果只能由实施实测填写。
