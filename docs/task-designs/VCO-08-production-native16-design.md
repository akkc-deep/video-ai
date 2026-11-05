# VCO-08：原生时序后端生产接入合同

状态：**COMPLETED（2026-11-04）**。C技术/实际静态/完整动态通过，显式生产接口及最终独立准入已验收。用户已明确“按建议直接推进，无需逐步确认”，C四窗320帧完整观看接受已绑定dynamic-review SHA4beaf4aca19f19e1a5d1a4c28deddb525fd118a8c5e32d20891b0ed35440421f。原生跨run修订、完整PCM/字幕、媒体与旧兼容通过；独立最终审查三项Important已真实RED→GREEN，回归发现的失败均已定向修复。当前8源五阶段真实资源 complete/exit0，普通exporter导出生产准入SHA1e56f31d5bb2c885342d250daaf9209bc38ff21383c9f3226cfbb30eac5c8d47；5,326唯一测试节点覆盖核对未知0/未解决失败0，最终源码SHA一致。主五项Acceptance和视觉适用范围见[验收记录](VCO-08-production-verification.md)，结项入口为[同任务记录](../task-handoffs/VCO-08-handoff.md)。

## Goal

在paragraph_jimeng_v1中接入显式`temporal_extension_v1`，实际消费多帧时序历史并完整覆盖原时间轴，具备一次采样、未知不重试、成功latent仅解码及版本化修订恢复。旧segmented/whole冻结配置、图、预算和观察继续按原契约读取。

## Scope

包括配置/冻结/纯预算与提示、独立原生workflow/事务/运行器、实际13帧条件、原生链观察、连续性/媒体/修订消费者和生产准入。沿用原文、PCM/字幕、语义计划、选图及已有超分/合成/交付入口。

初始支持fast768×432、16fps部署输出时钟、93原生帧/窗、13历史→4 latent、50步/CFG4/官方Flow scheduler。模型/软件/精度与已资格C固定版本一致。生产长度从完整timeline推导，不引入新的时间/占用/时长配额；实际观察质量范围仅C四窗320帧，任何新视频质量在实际观看前均unverified。

不自动把旧run改mode、替换Wan图/权重、降规格、改seed反复试验、切镜/插帧/冻结/循环补齐、不升级Comfy/生产Torch、不重新下载或复制权重、不重编码本次已有精确提示缓存。不写.git/commit/worktree，不关用户应用或改pagefile。CPU测试/GPU串行。发布仍走既有显式入口及真实最终观看，不由接入自动发布。

## Approach

### 选择与准入

采用独立native分支及小模块；旧Comfy分支保持。仅改mode标签无法让现有单图请求接收时序条件；把LongCat伪装成Wan图也不能证明实际条件，均不采用。

先完成C四窗、实际资源/原生映射/完整动态接受，再实现并生成独立生产准入证据。资格与生产准入分账：固定C原始case/software/model/input/window/bank/chain/review来源，以及新生产封装的源码/运行环境/实际资源检查。不同worker包装不声称与C全源SHA相同，明确证明相同数值核心，并对生产封装取得五阶段真实资源证据。

准入只证明指定backend/模型/数值核心/shape/clock协议可用；不把C的接受转成新输入的视觉通过。记录`observed_visual_scope`为四窗320帧/一个白鹭案例。新链超过该观察长度时仍记录范围差异及unverified，按实际全链观看准入，不截断原叙述或悄悄切旧模型。

### 预算、版本与提示

- 新mode=`temporal_extension_v1`，protocol=`longcat_native16_v1`，clock policy沿C的`predeclared_deployment_clock_16_no_model_fps_condition_v1`。模型API没有fps条件输入，不能描述成模型接收16fps参数。
- 新execution schema2/algorithm scene_execution_v2；旧两mode保持schema1/原算法/精确字段。新clip预算沿原BUDGET_FIELDS加protocol；首窗input_kind=selected_scene_image/head0，续窗input_kind=parent_native_tail_13/head13，generated_frames始终93。
- 对scene N>0：首窗保留min(93,N)，剩余每窗min(80,remaining)。last trim=93-head-retained；只有末窗裁尾，所有非末父窗完整保留其新增区。父原生历史始终[80,93)。所有global范围连续、每帧贡献一次、PTS i/16；按原timeline保留全部PCM和字幕，不改语义scene切点。
- `scene_clip_frame_mapping`只对严格新protocol预算进入独立validator；旧budget validator保持。新index必须schema4且显式protocol/execution Artifact，旧index不得借新mapping接受陌生字段。
- prompt schema3严格绑定mode和execution clip SHA，保持VCO-01视觉字段/原文changes引用/审查；旧schema1/2渲染字节保持。不把审计坐标/参考JSON或未来父姿态送入模型。
- rendering identity schema4绑定native evidence/protocol/runtime和execution算法；旧2/3精确字段保持。模式/模型/协议/提示变化建立新视频身份，使相关视频及下游失效，合法继承文本/语义/选图/PCM/字幕，不继承旧视频观看。

### 稳定运行核心与真实输入

将C的固定27小源码及许可/模型下载清单按原字节安装到`D:/VideoSi/tools/video-ai-temporal-native/<bundle-sha>/`；保留11官方源声明及变更来源。复用既有嵌入式Python3.13/cu130与固定隔离包，不安装新版本、不复制权重。版本目录已存在只允许相同内容复用，不覆盖不同身份。

父进程3.12只处理记录/所有权/调度，不导入Torch。新子worker在任何Torch导入前设置并核对cudaMallocAsync，调用稳定核心的load_dit/load_vae/attention及官方pipeline子类；生产请求封装、缓存身份、预算/映射由新模块实现。固定首图/提示变更必须在intent前拒绝或合法新修订，不能改变已开始job。

首窗实际读已接受scene图。续窗读取父原生RGB frames的[80,93)，捕获独立13帧快照并绑定父result/frames/range/实际消费像素SHA，再传`generate_vc(video=13帧,num_cond_frames=13,use_kv_cache=True,offload_kv_cache=True,enhance_hf=False)`。记录真实48层clean KV shape/dtype/bytes。viewing.mp4、单张last-frame和comparison_images不当作13帧模型条件。

提示缓存key绑定确切正负提示、模型/编码算法/依赖；相同现有缓存必须复用。只有不同的新生产提示才允许新的独立编码，编码前本地tokenize拒绝截断；本次C提示不重编码。续窗恢复父Generator状态，不能重新按seed启动噪声序列；scene首窗seed使用既有run seed与稳定scene序号，纳入请求冻结。

### 原生事务和恢复

原生请求、native workflow、intent、sample-complete、result与Comfy POST/HTTP记录分开。每window排他intent一次；先固化实际输入与冻结case/software/runtime/model/parent/RNG身份，再首次模型调用。未知结果只检查原PID/创建起点/命令/产物，不新起采样；failed保留媒体和身份。采样成功先原子提交latent/Generator和sample-complete，后解码/媒体；成功latent才可同身份decode-only。

复用真实RunLock/GPU ownership机制，资源监督只终止自己持有的worker对象，不凭PID杀别的应用。执行/跟踪/编码总时限为null，保留有限单次网络传输和进程清理等待；启动空闲物理8GiB/commit10GiB/GPU18GiB、运行物理2GiB/commit4GiB/GPU1GiB/磁盘32GiB守卫。磁盘预检还计算剩余真实窗口KV/媒体的存储需求，不把低空间变成隐性截短。

source/raw/condition/result原子pending→验证→提交；相同已提交身份复用，冲突/漂移拒绝。optional progress快照沿已验证读锁defer语义，资源检查先执行，stdout保留，停止终态保存原触发内存样本/阈值。保留case/window原起点，不通过resume重置采样机会或预算。

### 静态与整链动态观察

原native收集器允许父**真实技术+静态**通过后生成下窗，不借用旧segmented的人审父绑定。每窗完成返回实际contact sheet的`temporal_window_static`模板；agent_image/human_image只能给出acceptable/rejected/unverified并决定后续窗口，不能标为动态passed。最终窗acceptable用于组装，allow_next=false仅表示没有后继，不等于失败。

全部技术窗口完成后按保留区流式组装scene chain，记录每窗原始/历史/新增/裁尾范围及global映射，不把整链一次性全装RAM。生成`scene_temporal_chain_process`动态模板：绑定完整viewing Artifact、全部window/result/mapping、原图和完整[0,N)播放范围，覆盖主体、色彩、构图、镜头轨迹、动作阶段和全部边界。只能由真实human_video或有完整播放能力的agent_video接受；一次真实整链观看映射到各片段，不伪造数个独立观看事件。

generation请求只绑定当时已经存在的父技术/静态证据，不预写未来human接受SHA。链接受后complete index明确引用同一chain receipt与各window范围。failed/unverified/缺项/漂移/历史显式拒绝不能升级passed；完整动态之前不写source_clips_ready。当前VCO-04诊断/观察/风险回应门禁仍需通过，新的scope必须被明确验证，不能绕过或把全图MAE当校准阈值。

### 下游与性能

保留原生RGB arrays/raw及被裁尾帧作为证据；generated/source/chain提供正确16fps可播放版本，编码色彩解释沿VCO-02记录，不把浏览副本当逐像素相同。每个source仅新增保留区，last-frame来自准确原生索引；后续真正条件使用独立raw13快照。所有超分/合成贡献按新mapping验证，完整时间轴/PCM/字幕保持。

native mode不能用名字借用WholeExecutionCheck。新模式如需初次准入后避免逐帧重复昂贵上游证明，使用独立严格类型/来源/闭包覆盖，测试未知或被替换guard拒绝；旧whole用户已移除的重复检查不恢复。不得加入每帧重哈希数GB历史KV或重新模型准入的循环。

## Files and Interfaces

新增：

- `planning/scene_temporal.py`：`derive_temporal_clips(plan,timeline)`、`validate_temporal_clip(clip)`、`temporal_frame_mapping(clip,actual_generated_frames)`、`build_scene_temporal_plan(...)`；纯预算/提示输入/精确贡献，无I/O或模型。
- `runtime/temporal_scene_admission.py`：`load_temporal_evidence(path,reader=None)`、`freeze_temporal_evidence(...)`、`verify_temporal_frozen(frozen,reader=None)`、`install_temporal_bundle(...)`；资格与生产环境闭包、无网络小源码安装。
- `runtime/temporal_scene_records.py`：`temporal_context(...)`、`expected_temporal_request(...)`、`validate_temporal_window(...)`、`collect_temporal_progress(context)`、`complete_temporal_value(context,records)`；独立原生记录/父链/状态，不调用Comfy。
- `runtime/production_temporal_scene_clips.py`：`produce_temporal_clips(context,paths,logger,worker_factory=None)`、`consume_temporal_observation(context,path)`；真实锁下生成/恢复/观察准入，复用SceneClipResult外层状态格式。
- `runtime/temporal_native_process.py`：`recover_or_start_native_window(store,request,workflow,...)`；持有进程对象/持久所有权、无总时限、资源监督与恢复，不重复未知采样。
- `runtime/temporal_native_worker.py`：独立子进程入口，支持resource-preflight/prepare-cache/one-window/decode-only明确操作；稳定核心调用与真实条件/采样/提交。父进程import不得加载Torch。
- `runtime/temporal_scene_observations.py`：严格static-window及dynamic-chain模板/验证；`build_temporal_observation_template(...)`、`validate_temporal_observation(value,expected,now)`。
- `runtime/_temporal_media_check_coverage.py`：新native guard闭包，不能让未知对象借旧whole proof。

修改：config.py、planning/scene_execution.py、scene_clip_continuation.py、scene_video_prompts.py、scene_revision.py、scene_media.py；runtime/scene_execution_records.py、scene_video_prompt_records.py、scene_clip_records.py、production_scene_clips.py、scene_media_records.py、_scene_media_check_coverage.py，以及实际修订snapshot/origin消费者。所有旧分支保持版本语义，首次native分支在Wan模型/graph事务之前分流。

新增unit：test_scene_temporal.py、test_temporal_scene_admission.py、test_temporal_scene_records.py、test_temporal_scene_observations.py、test_temporal_native_process.py、test_temporal_native_worker.py；integration：test_temporal_scene_flow.py。操作/验收文档与新证据exporter路径在实施计划固定。

## Tests

全部通过项目bootstrap/test_windows.ps1，测试与GPU串行，.git只读。先保存当前src/tests/scripts来源基线，再逐模块RED→GREEN，不拿fixture当真实模型/观看证据。

- `./scripts/test_windows.ps1 -q tests/unit/test_scene_temporal.py`：N=1/13/80/93/94/173/174/253/254/320/321/333/334及长链完整唯一贡献；非法类型/范围/协议/形状/时钟拒绝，旧预算精确不变。
- `./scripts/test_windows.ps1 -q tests/unit/test_temporal_scene_admission.py tests/unit/test_temporal_scene_records.py tests/unit/test_temporal_scene_observations.py`：缺失/failed/unknown/unverified/媒体或源码漂移零启动；static不能动态通过、父静态/原始13帧/RNG/source绑定、真实整链范围、历史拒绝保留。
- `./scripts/test_windows.ps1 -q tests/unit/test_temporal_native_process.py tests/unit/test_temporal_native_worker.py`：未知原进程不重复、结束进程不误认活锁、intent前后中断、sample提交后仅解码、部分媒体恢复、None执行等待/有限传输、4GiB原停止样本留证、先导入Torch入口正确allocator。
- `./scripts/test_windows.ps1 -q tests/integration/test_temporal_scene_flow.py`：真实CPU媒体fixture验证320帧四窗及334帧五窗完整映射、13个不同历史像素实际传给fake provider、完整PCM/字幕/超分合成贡献、模式修订/继承、同run零重复。fixture_only原始标签保持，不宣称真实GPU。
- 旧兼容至少执行实际受影响的whole/segmented、提示、修订、连续性和媒体用例；明确命令在plan按现有文件清单列出。最终源码完成后collect/hash/逐节点日志的全库回归，处理真实失败，不挪用旧源码结果。
- 实际GPU：C四窗/320帧完整新反馈；新生产封装五阶段资源检查对应自身源码，0文本重编码/下载/视频调用；生产准入导出并用普通入口核对真实C证据，不能仅靠新协议名字。

## Acceptance

1. C新完整链实际接受，生产准入另行验证并绑定当前backend/模型/源/工作流/shape/clock；实际13帧条件和48层clean KV可追踪，非审计图冒充。
2. 任意请求时间轴由预算完整覆盖、历史一次输出；原16fps/PCM/字幕与精确贡献无截短/冻结/插帧/变速。资格观察范围诚实保留，不承诺任意长度视觉稳定。
3. 每窗真实技术/静态与完整chain动态/自动报告分账；所有五类连续性方面和边界可查，未通过不写source_clips_ready或推进媒体。
4. failed/unknown不重复模型调用，成功latent仅解码，协议/输入漂移拒绝；模式变化正确失效视频后代，合法继承非视频资产；旧冻结run/96帧预算/图按旧契约恢复。
5. 定向、恢复、真实资源与视觉、最终源码回归有各自证据；同run重放零新增采样。生产mode为显式opt-in，不改变旧默认。

## Risks

C完整技术/动态已通过；启用仍需绑定当前生产源码的独立资源准入。单白鹭四窗不代表跨题材或更长链质量稳定，必须每个新链完整观看。原生包装与C原程序身份不同需独立资源/恢复检查。多消费者版本升级可能破坏旧闭包，须逐项兼容验证；不借机放宽旧guard或恢复用户已移除的重复核验。
