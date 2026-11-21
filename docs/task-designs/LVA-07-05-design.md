# LVA-07-05 最小真实GPU对照设计

## Goal

在新的隔离比较组中执行完整双专家准入，然后一个低运动40步control；技术与真实人工接受后，才执行同输入4步fast。根据实际兼容、质量、计时和资源决定是否值得后续扩展。不用04的CPU机制证明替代本项实际结果。

## Scope

2026-11-20最新RGB布局修复：-05原40步和fp32VAE解码在18GiB下全部完成，Save108对非C连续RGB数组memoryview计算SHA时BufferError，发生于encoderintent/ffmpeg/帧落盘之前，无MP4。采用 `LVA-07-05-encode-layout-design.md` / plan，在rgb_frames已完成finite/round/clip/uint8之后只做np.ascontiguousarray，保持像素/通道/编码契约。原VAE CHWT->THWC布局RED2复现，69测试8.60s及真实93帧FFmpeg/回执恢复测试通过，一次审查无重要项。2文件交付/旧字节归档；先新-06同worker联合准备再新epoch pair/control，实际接受后fast；旧failed657eeab2不重POST。其他模型/精度/93帧/18commit24RSS20GPU预算不变。

2026-11-20最新Windows提交预算补充：-04原40步高30/低50前向全部通过，VAE解码conv2d在12GiB逻辑提交峰值附近失败（距额度160KiB、主机仍约16.8GiB空闲RAM）。原fp32/93帧/无tiling专项解码：12GiB失败、32GiB及选定18GiB均通过，测得commit14.23GiB/RSS2.84GiB。按持续用户本机预算/修复许可采用 `LVA-07-05-decode-budget-design.md` / plan：GPUJob逻辑提交18GiB、controller在Job外读取availablecommit至少26GiB，保留RSS24/GPUallocator20/启动RAM14与VRAM21/phase4与20/CPU4不变；不改模型、精度、tiling或帧数。68测试/独立审查无重要项，先新-05联合准备再新epoch pair/control，真实接受后fast；旧failedID不重发，当前无MP4/质量。

2026-11-20最新原生回迁修复：-03联合text/image准备和完整pair通过，controlb4d56a51首个block CPU回迁发生VCRUNTIME0xc0000005，原accepted保持unknown且不重POST。单独原始FP8块/AIMDO只读映射/相同12GiB额度，在5.25GiB空闲CUDApool下重现同栈崩溃；局部CPU源存储恢复适配器已在同压力下通过，原CPU存储指针完全一致。采用 `LVA-07-05-offload-design.md` / offload-plan.md；只在owned block.to回迁恢复frozenCPU参数与常量LoRA buffer并清空空闲池，mutable buffers仍原生回迁，native数学/模型/预算不变。67相关测试/一次审查fixpass及原生meta清理检查通过。新-04先联合准备，后新epoch pair/control；真实接受后fast，禁止重发-03原ID或以历史pair放行新epoch。

2026-11-20继续修复后的最新补充：-02原664/512文本和完整pair实际通过，control77da1e64在VAE编码后CPU回迁触及12GiB提交上限。采用 `LVA-07-05-vae-design.md` / `LVA-07-05-vae-plan.md` 的局部VAE返回/CPU回迁边界空闲池清理；同prepare-text阶段先联合准备原文本和图像，原图纳入同一持续只读SHAlease，VAE保持CPU、image条件逐trial复制。生成不再编码；nativeDecode同schema仅局部清理无数学改变。保持12GiB/24RSS/20allocator/原输入预算；61测试及一次审查fixpass完成，候选原VAE93帧fp32探针已通过。新-03先实际联合准备成功再pair/control，真实接受后fast；旧失败ID不重发。当前03尚在启动，真实联合准备/采样/解码/质量待运行。

2026-11-20 用户“继续修复吧”继续T5联合修复。采用 `LVA-07-05-text-design.md` / `LVA-07-05-text-plan.md` 的同worker prepare-text先行阶段、T5释放后缓存及逐条件664/512 padding；已测8GiB额度不足，私有commit调12GiB，RSS24GiB/allocator20GiB等保持。新20261120-02组先实际验证文本后才准入，原失败control无采样/视频但POST保留统计；修复后新组一次control/真实接受后fast，仍最多两份实际视频、不重发旧ID、不截断原文。

2026-11-20 当前组7873d50d7e9a8d594aee0412a6c22aa0de788d13ba8655b0088d7347855ce823已完整通过双专家/两head准入；随后唯一control原prompt在T5输出转CPU时遇8GiB提交硬限，原生分词另证实positive664/negative512，超过现有512条件守卫/默认text_len。已按失败停止，当前组服务/observer均退出，pair为历史证明；任务BLOCKED而非完成。下一步先形成并单独验证T5内存交接与664-token完整上下文联合方案，不截断原输入、不重发失败ID，也不直接重复整套pair。结果见LVA-07-results.json/.md和当前experiment-assessment.json。

2026-11-20 用户“继续吧”要求继续head兼容工作；具体适配设计/实施计划为 `LVA-07-05-head-design.md` / `LVA-07-05-head-plan.md`。采用隔离动态安装及采样reload作用域，不改固定Wrapper/repair/适用政策、不重新量化head、不遗漏增量；原资源/不限时/两样本与人工门槛授权持续。CPU验证和审阅后才封存新20261120-01组，旧-04明确失败不重POST或重启。

2026-11-19 -03组high1095参数物化后ValueError拒绝，原记录缺少具体message，不伪造原错误内容。固定Wan构造器原生original_patch_embedding/expanded_patch_embedding为patch_embedding同一模块；有界CPU复现原duplicate=False守卫误拒，RED1error后12CPU测试通过，44协议测试通过。仅精确归一化两条相同模块路径（无独立source key），其他别名仍拒绝；原政策/模型数学不变，未来failed回执保存具体error_message。-03已合作exit0/未强制/端口关闭，284.406s，峰值RSS1813954560 bytes；保留原ID失败。单独评估修复后用新-04组封存，不重POST原ID，累计视频0。

2026-11-19 首次实际-02组准入在high物化初始参数阶段因Comfy进度回调缺少last_prompt_id失败；已用原ID GET取得明确失败并正常退出服务（exit0/未强制/端口关闭），没有视频POST。单独评估确认是准入在首个prompt前的UI适配问题，非模型政策或数学不兼容；44相关测试验证线程范围进度适配及异常恢复。保留-02完整失败现场，修复源码交付后使用新 `LVA-07-05-low-20261119-03` 封存后续评估；不重POST旧ID、不复用旧pair、不生成替代视频。累计最多两个实际视频样本及control人工门槛保持。

2026-11-19 用户进一步要求“按照本机可以提供的来吧”，批准按本机容量继续。实施选择为RAM准入14GiB/显存准入21GiB；保留私有commit8GiB/RSS24GiB/GPU allocator20GiB/单owner。现有主机可用RAM16816201728 bytes、空闲VRAM23085449216 bytes已达新前置，available commit44772716544 bytes；这不是峰值适配证明。控制器 `--max-seconds 0` 仅在真实授权明确 `max_service_seconds=null` 时取消总时限，CPU仍有180秒上限。合同/源码变更前旧root未启动任何worker或请求；保留旧root，使用 `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-02` 封存新comparison和两profile并关联同一用户批准及容量补充，不沿用旧SHA或生成ID。以下26GiB/22GiB、4小时和未获授权表述均为历史方案，按本补充执行；模型/预算/失败/人工接受约束保持。实施计划为 `docs/task-designs/LVA-07-05-host-budget-plan.md`。

2026-11-19 用户后续明确回复“你再试一下，时间可以不限制”：已授权此前呈现的具体comparison重试，并取消总执行时限，优先于下文原4小时限制。授权保存于已封存root的 `authorization.json`，不再重复索取同一许可。26GiB可用RAM/22GiB空闲VRAM、原ID及失败停止、最多两样本和control真实人工接受门槛保持。当前控制器代码仍限制4小时，需在资源解除后、首次执行前适配并评估封存源身份；不得声称已实现不限时运行。下文授权未取得/4小时表述为原设计历史要求，以本补充和最新结果为准。

沿用任务板Order11既定范围，最多两次生成，768×432/93帧/16fps、原低运动图片/prompt/negative/high seed264244520398999/low seed0；control无LoRA，fast强度1/1。保留原六模型、固定Wrapper/Comfy/runtime/政策。没有下载、安装、换模型、降低预算、生产恢复、1080P、冷1热3或高运动/父子实际矩阵。未知请求只恢复原ID，不因失败另发候选。

本文件和READY不授权启动GPU。必须先取得用户对本具体两样本/资源/失败边界的新GPU执行授权；旧04/早期原生授权不能外推。授权记录必须有真实用户证据，不自动生成同意字段。

## Approach

### 输入及先决条件

顺序读取04设计/结果JSON与MD、04review、07环境manifest及03执行/CPU注册结果、LVA-01-gpu-results.json的low_motion。代码在 `E:/code/py/video-ai`，独立环境 `E:/VideoAI/scratch/benchmarks/LVA-07-04-environment`。完整模型sha/header/字节由manifest固定，来源分类保留High1500/Low1459适用、Low精确290不适用；原CPU小模型helper上限不变。

04实际仅验证77相关pytest、10固定函数体CPU fixture、13实际CPU HTTP schema。RAM最近观察16747077632 bytes，低于26GiB要求；当前GPU空闲值及完整峰值未知。先只读观察容量，未满足不启动实际加载，不关闭用户应用、不改限额。后续须满足可用RAM27917287424 bytes/空闲VRAM23622320128 bytes、私有commit8GiB/RSS24GiB/GPU allocator20GiB、单Wan owner；原有512MiB预留覆盖两个低分辨率产物和回执，不增加模型副本。

### 精确准备与授权

使用现存 `E:/VideoAI/scratch/benchmarks/LVA-07-04-cli-fixture.json`：由原 `LVA-01-gpu-low-20261115-01/frozen/original-request.json` 和已验证input构造，图片SHA为57ca0f059560e5582888e3f7e0080a3d6b04ab5d47df246c572f738c125d7df2。先核对该文件与原source_request/prompt/image摘要，提示词不写到报告。若任何身份不符，停止，不替换输入。

拟用新root `E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01`，存在则拒绝覆盖。准备命令（只拷贝小图片/封存profile和图，不导入模型）：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper.py init --root E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01 --fixture E:/VideoAI/scratch/benchmarks/LVA-07-04-cli-fixture.json --port 8297
```

取得本比较组确切comparison_sha256、两profile/graph SHA和当前资源观察后，呈现上述具体操作范围供用户批准。只在实际批准后，写root下 `authorization.json`：`task_id=LVA-07-05`、`approved=true`、`user_evidence`为实际用户批准原文/来源时间引用、`comparison_sha256`等于新experiment.json、`max_samples=2`。不得从技术通过、旧“同意”或默认选项构造用户证据。原Comparison含fixture，两mode profile不同；不能把fast SHA填为control SHA。

### Owned服务及完整模型门槛

获得授权且容量满足后，在该root启动固定服务：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/observe_wan_wrapper_comfy.py --root E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01 --mode gpu --authorization E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01/authorization.json --port 8297 --max-seconds 14400
```

这是持续controller命令；后续CLI在同一新比较组调用，不能另外启动第二个worker。controller持有Popen/Job和真实PID/start/epoch；固定source/runtime/工具、实际模型搜索路径、当前13HTTP schema及授权不符均拒绝。GPU SDPA禁math fallback、compile/merge/fast_fp8/low_mem_load关闭，blockswap40/prefetch0/nonblocking false。窗口最多4小时，超时记失败/unknown并只结束owned handle。

先运行准入：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper.py admit-pair --root E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01 --mode fast --authorization E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01/authorization.json --port 8297
```

client-intent在POST前封存唯一admission ID/profile/epoch。首次完整哈希原六文件一次，保持deny-write/delete lease；先high实际构建/加载/分类/解析保留/私有静态覆盖/动态真实CPU forward witness并释放，再low。实际目标shape/dtype/精确无img例外均检查；只允许原load_weights的patch_embedding FP32规则。receipt必须包含原ID/current epoch、两侧完整逐项trace文件SHA和全部适用输入安装/探针结果。两侧未全部通过不发布pair、不发视频POST。不能抬高legacy cap或改政策。

完整门槛可能超过HTTP45秒；响应丢失时保留同client-intent，再调用相同CLI只GET原admission ID。unknown继续查询原ID，不能POST第二次准入，也不能把没有响应当失败后另起模型。高侧成功/低侧失败的诊断不构成可用单侧。

### Control与fast

完整pair门槛通过后，执行control（control构建仍完全不解析/应用LoRA）：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_wan_wrapper.py run --root E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01 --mode control --authorization E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261119-01/authorization.json --port 8297
```

control_1的固定40步/CFG3.5/high15-low25完整sigmas取04contract。native T5+现有桥接，T5释放后才VAE fp32/图像编码，单专家串行，预期实际外层forwards high30/low50；实际sigma/time步/计数不符停止，整数time步的非等价限制必须报告。

收集完整MP4/PTS/末帧和owned晋升回执，显示此实际control给用户审核稳定性、运动、细节、闪烁及输入一致性。技术通过不是接受。用户真实接受后才写 `reviews/control_1.json`，字段为decision=accepted、human_evidence、comparison_sha256、control_profile_sha256、fixture_sha256、control_graph_sha256、prompt_id、media_sha256，分别绑定真实原control产物。拒绝/无法确认时不生成fast。

用户接受后同服务/同pair epoch执行上面run命令，仅将mode改为fast。fast_1固定4步/CFG1/high2-low2，期望实际forwards2/2，所有2959适用输入应用。完整技术检查后再次展示实际fast并单独记录人工质量；不得用CPU示例或同字节自动接受质量。中途服务退出使pair失效，禁止绕过后再发fast；保留已完成结果和未执行事实，不自动restart原root或替换请求。

### 恢复、计时与退出

响应丢失/执行中/超时用 `recover --root <本root> --mode <原mode> --port 8297`，只跟原intent/client/prompt ID。已有原归档history及晋升媒体可离线收集；完成结果0HTTP/0producer，重启只重新验真一次媒体。不可恢复未持久化的扩散中间步。采样未完成或身份不明保持unknown，不重POST。

记录group_setup（身份/服务导入/pair）、每trial submit-to-output、T5/VAE/每侧构建应用采样释放/decode/编码验真、实际elapsed_since_group_handoff、人工等待和冷/热边界。collect节点耗时/设备采样不充当独占kernel时间，不加总嵌套阶段。各mode只一个样本，不报P50/P95、稳定倍数或1080P收益。

结束时写 `stop.request.json`，仅含原service-owner的pid和epoch，controller合作停止、超时才强制owned handle，并记录实际退出码/forced/端口。保留失败source、原ID及回执。退出异常不能记graceful/成功。没有批准本方案时上述GPU服务/准入/run均不执行。

## Files

- 新root：frozen comparison/profiles/graphs、fixture/input、授权、service-owner/launch/attestation/current HTTP、client/server admission intent/pair/tensor trace、trials原ID历史/技术结果、stage metrics、media/encoder/promotion、人工review和退出。
- `docs/task-designs/LVA-07-results.json/.md`：追加本项实际GPU兼容/质量/计时/资源、失败和未验证事实，保留前项结果。
- 任务板仅按实际结果迁移；不足完整验收则写相应pause/block handoff，不把未知或未运行fast伪装为通过。

## Tests

不为本项准备重跑04所有测试或旧payload/GPU矩阵；04证据已固定。真实执行验证以上exact CLI，预期正常分支exit0。准入必须两侧完整实际计数/trace/forward通过；原IDunknown分支只GET并保持同ID。control/fast媒体各93帧、768×432、CFR16完整PTS、finite-before-uint8和末PNG一致；人工结论独立且可追溯。实际worker退出/端口与Job可核对。

任何代码/环境/模型变动先退出本实验并另行评估，不能在运行中换源或以重试掩盖失败。若只是原archive/媒体恢复，不再生成、重新全模型准入或重复已有完整decode。

## Acceptance

完整实际双专家门槛有全部来源/目标/安装及完整witness文件证据；control、获真实接受后fast各有原ID、技术及真实人工结论；资源与计时边界明确，服务退出可核对、unknown无重发。技术/质量失败按本项失败停止条件记录后续未执行，不宣布通过或扩展。只有成功且用户选择继续扩展才准备06实际矩阵，不能自动执行。

## Risks

当前RAM未达26GiB、GPU空闲与14B峰值未知，GPU执行未获本项授权；这是明确前置而非允许builder自行放宽的参数。实际scaled FP8/T5/VAE/offload/SDPA可失败。整数time步与原生浮点不严格等价、VAE精度路径不同，收益不可归因纯后端。单样本不足稳定速度/质量结论，任何失败不换模型或降低93帧预算。
