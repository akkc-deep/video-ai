# VCO-07：经实测准入的版本化整段生产模式

## 2026-11-01 用户明确覆盖：移除媒体阶段的重复检验

用户在看到实际222.071秒/帧、模型仅0.827秒/帧的诊断后明确要求：“把这些检验都去掉，没有用”。本指令覆盖下文及旧性能计划中“whole媒体每次写入/发送都重核全量原始依赖、父目录、inventory、模型/工具”的规定。whole媒体在上下文入口完成源片/人工观察准入后，不创建continuity ByteGuard，不在逐帧写入或发送时重跑这些审计，也不再逐帧请求object_info。历史分支保持既有行为。原任务身份/RunLock、不可变写入、原intent恢复、PNG实际输出验证、最终人工观看和独立发布继续使用。具体变更及证据见VCO-07-remove-media-rechecks-plan.md；旧逐写漂移拒绝要求不再作为whole媒体的验收条件。

## Goal

将 `scene_rendering.mode=whole_scene_v1` 作为显式新模式接入现有 `paragraph_jimeng_v1` 生产链；每个语义scene只生成一次，完整覆盖原时间轴。默认及历史冻结run保持 `segmented_v1` 的原预算、graph、观察与恢复行为。

任务身份和顺序以 `docs/task-handoffs/video-continuity-optimization-task-board.md` 的Order 7为准。2026-10-30用户要求纠正VCO-06状态并完成下一任务准备；本轮只完成设计与交接，不开始产品实现、真实推理或发布。VCO-06的软件/研究结项不提供生产校色资格，也不是本任务的直接输入。

## Scope

包含配置/冻结、真实准入证据验证、独立执行预算、全消费者接入、视觉提示覆盖、渲染身份、局部失效、一次提交恢复、原生媒体、VCO-04观察准入、超分/合成/最终观看与显式发布的贯通。

当前工程包络仅为VCO-05证明的Wan2.2双专家、fast 768×432、16fps、40步、CFG3.5、Euler/simple、15步切换、batch1及已记录硬件/模型/工作流。每scene保留1..320帧，请求 `_wan_frames(F)`，上限321；少于320帧是这一保守工程上限内的执行预算，不表示所有较短内容已经实测通过。quality/1280×720、超过320保留帧、其他后端/精度/工作流、跨窗、自动回退分段或自动重试均不在本版本内。

当前真实视觉接受仅覆盖VCO-05确切的20秒鸟类跟拍片；其他主体、材质、运镜和任意时长能力均未验证。通用实现和CPU夹具可以覆盖不同题材，每份新生成媒体仍必须取得自己的实际完整观察，不能继承首例结论。更长scene在任何新POST前明确拒绝，不截短、变速、补帧、循环或私自切镜。原JIM-08独立多片续接验收继续未完成。

## Approach

### 1. 已确认输入、选择与验收边界

直接依赖只有VCO-04与VCO-05，二者不存在冲突：前者规定每份生产媒体的当前诊断/风险回应/完整观看，后者只允许依据真实首例开始有限范围的整段集成。隔离首例 `production_eligible=false`、`production_mode_enabled=false` 不是失败，也不是现有生产就绪证明；它的 `vco07_first_case_evidence_ready=true` 是本任务集成设计的输入。

采用独立执行预算与版本化渲染身份。直接修改语义 `scene-plan.json.clips` 会使图像和原文继承失效；单独放宽96帧guard会让映射、超分和修订继续消费分段预算，因此均不采用。工程决定是增加纯预算模块和持锁预算账本，让所有clip消费者使用同一份派生预算。沿用当前Python/PowerShell/NumPy/OpenCV/FFmpeg及已有模型，不安装依赖，不新建worktree，不写 `.git`。

### 2. VCO-05证据及准入读取

唯一已接受证据根为 `D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/`。读取顺序：`completion-check.json` → `final-assessment.json` → `user-observation.json`、`result.json`、`evidence-summary.json` → `playback-review.json`、`mapping.json`、`native-frame-identities.json`、原始媒体 → `case.json`、`prepared.json`、`graph.json`、原意图/受理/HTTP与resources。

已确认身份：

| 证据 | SHA256或事实 |
|---|---|
| final-assessment.json | `527f08dd69d51b4c7f176284a768dbf9387deb273d644244920be70c79fcb653` |
| user-observation.json | `6f844667e7210e16545d12b910b3e7098bdad86b5252482f8451bbd573422a5b` |
| review-playback.mp4 | `ae175cc0e6819039a524f23c7642e0a667ada071ea61486adbf717155eb71ca6`，320帧/20秒，CRF16观看副本 |
| 原始output/candidate_00001_.mp4 | `4916b39184f19b083415a81ccf923eb5db10d415591014dae2389af3be98abe7`，321帧 |
| mapping.json | `8bcb5d3ef297e881b3b63cf8aaf35ba8339a92725ca344016093fc6bbfc6130f`，保留[0,320)，仅丢源帧320 |
| 实际资源/任务 | 1874份有效采样；单次POST；3798.752秒成功；峰值总GPU21657MiB、系统内存33298898944 bytes |

准备阶段已核对2211项输入身份（含全部321原生PNG及1874资源JSON），不重新测量视觉或资源。核对记录：`D:/VideoSi/projects/video-ai/vco07-preparation/20261030-015108/input-check.json`。490个源码/测试/脚本的准备前库存也在该记录中，不能把本次读取称为重新执行VCO-05试验。

新增 `runtime/scene_execution_records.py` 的 `load_whole_scene_evidence(path, *, reader) -> dict`，使用既有严格JSON、Artifact、绝对路径和原始字节SHA校验。输入路径是准确的 `final-assessment.json`，不接收glob/latest/手写passed开关。验证上述原记录的字段和交叉引用，检查技术/资源/完整观看passed、确切播放SHA与范围[0,320)、321张PNG身份、原映射、单POST与资源记录；旧result中的当时unverified保留，由后来的final-assessment解释，不能改写旧result。不得只检查一个布尔值或只读取 `completion-check.verified`。

冻结时保存原final-assessment字节为 `production/scene-rendering/whole-scene-evidence.json`，并持久化 `evidence-closure.json`，精确字段 `{schema_version,algorithm,root,artifacts}`：schema_version=1，algorithm=`whole_scene_admission_closure_v1`，root为冻结根Artifact，artifacts为本次实际读过的外部证据Artifact按规范路径排序去重。根和closure分别作为 `whole_scene_evidence`、`whole_scene_evidence_closure` 加入本run的input_identities；外部原件不搬移、不重签。每次writer与提交前重核闭包、目录inventory及当前模型/推理工作流/Comfy执行环境身份，漂移则拒绝，不重签历史证据。当前产品Python模块属于新实现，单独记录其身份，不要求它们与旧实验runner相同。新实现不得执行归档源码。

Artifact沿用 `{path,bytes,sha256}`；冻结input_identities沿用既有FileIdentity格式。JSON16MiB、同调用元数据64MiB，流式文件哈希；模型/工具重核沿用现有ArtifactStamp，不能因代价大只检查size/mtime。原始作者反馈及其来源照录，不补造观看时间、逐秒事件或第二审阅者。

### 3. 配置与旧版本分派

`scene_rendering`不出现时完全保留旧分支；现有精确两字段 `{prompt_policy,prompt_contract}` 仍按VCO-01处理，不补mode或新文件。新增两种精确结构：

```text
{mode:"segmented_v1", prompt_policy:"visual_v2", prompt_contract:PATH}
{mode:"whole_scene_v1", prompt_policy:"visual_v2", prompt_contract:PATH,
 whole_scene_evidence:ABS_FINAL_ASSESSMENT_PATH}
```

相对prompt路径继续按config目录解析；whole_scene_evidence必须是D:/VideoSi下的准确绝对本地文件。unknown/null/部分prompt配置、segmented带whole证据、whole缺证据、未知mode均拒绝，不自动退回旧renderer。whole另要求显式 `scene_continuity={schema_version:1,policy:"advisory_v1"}`，避免绕过VCO-04；历史run不强加新策略。

新mode只在新run或显式reconfigure修订生效。`production/options.json`现有schema1/2和旧精确required roles保持；仅显式whole分支要求两个新冻结role，显式segmented没有whole role。恢复只读本run冻结配置和证据，不能用外部当前config覆盖。

### 4. 纯预算、提示与无环身份

新增 `planning/scene_execution.py`：

```python
derive_scene_execution_clips(plan, timeline, *, mode) -> list[dict]
build_scene_execution_budget(plan, timeline, *, run_id, mode,
    rendering_identity_sha256, admission) -> dict
validate_scene_execution_budget(value, plan, timeline, *, expected) -> dict
```

全部为纯函数，不访问文件/模型。clips沿用 `scene_clip_continuation.BUDGET_FIELDS` 的精确字段。segmented使用原 `plan_scene_clips()` 和原96生成帧检查，结果必须等于已提交plan.clips；whole对每个scene输出一行：

```text
clip_id=scene_id+"_clip_0001"; ordinal=1; parent_clip_id=null
input_kind="selected_scene_image"
start_frame=scene.start_frame; end_frame=scene.end_frame; F=end-start
retained_frames=F; generated_frames=_wan_frames(F)
discard_head_frames=retained_source_start=0; retained_source_end=F
trim_tail_frames=generated_frames-F
```

scene按原序连续覆盖[0,total_frames)，F为正int且≤320，拒绝bool；不从6秒max_clip_seconds推导whole预算。`_wan_frames(F)=1+4*ceil((F-1)/4)`，所以F=1请求1；不擅自加一个最小帧数。321是本版本请求上限，不保证每个短请求都一定成功。

确定性样例：原三scene F=219/110/134，whole请求221/113/137，区间[0,219)/[219,329)/[329,463)，总463帧；F=320请求321，F=321在提交前拒绝。帧图仍为原 `scene_clip_frame_mapping`，只保留[0,F)，尾补帧不进入超分/合成；whole没有伪造同scene父链。

预算精确字段 `{schema_version,algorithm,production_strategy,run_id,mode,scene_plan_sha256,timeline_sha256,rendering_identity_sha256,admission,clips}`，schema_version=1，algorithm=`scene_execution_v1`；admission为冻结whole证据Artifact或显式segmented的null。保存到 `production/scene-rendering/execution-budget.json`，锁内exclusive临时文件+fsync+rename，存在时重新推导并逐字段相等，不覆盖。缺省历史分支不创建此文件。

whole不拼接旧分段motion描述。新增prompt contract schema2，顶层字段保持schema1集合；binding精确为旧三个SHA加 `{rendering_mode,execution_clips_sha256}`，mode=`whole_scene_v1`，后者为纯clips的canonical_digest。clips必须仅按whole一scene一行的顺序覆盖；每行仍使用原motion/camera/lighting/changes及原文引用规则、原文本审查，整scene动作从已选图姿态出发。schema1仍只配旧/segmented，不允许靠删旧clips绕过schema1完整覆盖检查。

依赖顺序固定：语义plan/timeline → 纯execution clips → schema2提示及其实际文本review → 冻结提示SHA与准入证据 → 渲染身份 → execution-budget。提示不绑定尚未生成的预算Artifact或rendering_identity，因此没有future SHA或循环依赖。`scene_video_prompt_records.prompt_binding_context()`跨修订只在已有完整plan/choice导入证明时寻找原绑定；whole还重算纯clips摘要，不能重新给旧review签SHA。

whole的seed_high沿用该scene在原语义plan中首clip的既有全局索引 `264244520398999+index`，seed_low=0；固定采样参数沿用原生产模板。索引由原plan推导并入request，不因减少clips悄悄换seed；seed相同也不承诺不同length有相同噪声或画质。

### 5. 消费者与记录分派

`load_scene_execution(frozen,plan,timeline,*,reader) -> dict`只读核验已有预算；`ensure_scene_execution(...,lock) -> dict`仅由writer持锁建立。旧分支返回原预算的内存视图，零写入；显式mode已有预算缺失但下游已有持久化记录时拒绝，不能由status补写。writer在任何服务启动/POST前对所有scene整批预检，包括长度/资源/证据/输入漂移。

context保留 `plan` 表示原已提交语义对象，新增 `execution` 与其Artifact。严禁把替换clips的临时对象当作原plan计算SHA。clip枚举、parent链、frames枚举及映射校验全部消费execution.clips；叙事/参考图/Bible绑定继续读原plan。以下调用必须同步处理：

| 消费位置 | 确切处理 |
|---|---|
| `scene_clip_continuation._budgets/build_scene_wan_plan/validate_scene_clip_frame_mappings` | 可选keyword execution；旧调用原值，whole验证新预算；narration检查原时间轴不变 |
| `scene_clip_records.scene_context/complete_value` | store.clip_ids与rows来自execution；保留原scene_plan_sha256；inputs与完整索引按下面版本分派 |
| `production_scene_clips._input/_technical/_restore_outer` | whole每scene从选图开始；仅裁尾，一一映射；恢复同一request/graph/原任务 |
| `planning/scene_media.py`、`scene_media_records._scene_media_base_context` | 使用完整索引中的execution Artifact；超分逐原生保留帧，不重建分段plan |
| `production_scene_upscale`、`production_scene_composition`及其materialized读写器 | 同一execution闭包；完整逐帧映射、PCM/字幕覆盖，不由短片假设拆回多段 |
| `scene_continuity_records`、`production_scene_continuity` | 用真实whole记录/映射构建当前epoch的全scene前缀；不产生不存在的parent_join |
| `scene_clip_observations`、`scene_final_observations`、`production_scene_delivery`、`scene_completed`、pipeline恢复 | 每个whole源片完整观看，后续各门槛重新验证；最终成片也需独立完整观看 |
| `planning/scene_revision.py`、`production_scene_revision`、`_scene_revision_plan/_origins/_readers` | source clip/frame节点、import依赖与目录守卫使用源run的execution；不得使用目标预算替代历史源预算 |

版本分派：缺省历史的scene-clips/inputs.json与complete.json保持schema2及全部原字段。显式mode的inputs为schema3，字段为原inputs集合加 `execution_budget` Artifact，algorithm=`scene_wan_execution_v1`；显式mode的complete为schema3，字段为原complete集合加同一Artifact。prompt_policy/prompt_contract仍按实际存在情况使用原规则。没有明确mode的新schema3或有mode但返回schema2均拒绝。

request.json、技术clip.json、mapping、last-frame、原观察/HTTP事务保持现有schema2及原字段；request.inputs_sha256绑定schema3 inputs，clip.request_sha256、观察request摘要继续传递预算身份。不得增加未被验证的可选字段来绕过精确schema。upscale/composition/final/delivery可保持原schema2，因为其scene_clips_sha256及request/候选SHA已传递绑定；相关严格reader须显式支持新的schema3完整索引。任何下游身份、预算或总帧数冲突均在继续操作前拒绝。

### 6. 修订、继承与恢复

旧无版本渲染身份与schema2 visual_v2身份按旧函数严格重建。新增schema3：原IDENTITY_FIELDS加 `schema_version=3,rendering`，rendering精确 `{mode,prompt_policy,prompt_contract_sha256,whole_scene_evidence_sha256,execution_algorithm}`，最后固定 `scene_execution_v1`，显式segmented的whole证据SHA为null。配置变动不能只从planning摘要删字段：mode/prompt/证据变化必须使全部相关源视频及其clip_reviews/upscale/composition/final_review/delivery失效；语义plan、选图、原文、PCM/字幕及image_group可在证明相符后继承。

revision snapshot新分支在原SNAPSHOT_FIELDS基础上增加 `scene_execution`（源run已验证budget）；旧snapshot字段集合不变。whole/显式mode源不得省略它；source clip_nodes/upscale_nodes与invalidation图使用源execution。reconfigure跨模式时所有源视频节点失效，不导入同名 `scene_*_clip_0001` 的旧源片或旧观看；目标execution在其新冻结身份和继承语义输入成立后另行派生。`_scene_revision_origins` 的祖先解析、relevant clips及guard inventory必须使用源预算，避免同名clip把分段观察误当whole观察。中间revision未生成视频时同样能核验common/plan/choices的合法导入。

whole证据及其closure须在 `configuration_identity()`、目标冻结、origin读取中都重核；非reconfigure修订把两个路径解析为源run冻结的准确文件，不从用户当前config找替代。whole→whole相同内容可按原导入证明复用；mode切换无论clip_id是否同名均不复用视频。

诊断算法变化仍只重建VCO-04 epoch/报告/当前回应，不重新POST原模型或重出图。相同原始媒体的failed观察及所有后来的失败原文永久保留，不能通过新epoch/修订隐藏。VCO-06研究候选仍不可作为生产原片、父片或超分输入。

事务沿用RunLock及既有scene_comfy_transactions：请求/graph/intent先持久化，结果不明只查询原prompt_id；完整输出恢复只校验不补单；HTTP受理前后崩溃、media暂存和预算落盘边界均保留现场。OOM/超时/非法帧数或显式质量失败停止，不降规格、换seed或回退segmented。推理沿冻结7200秒上限，服务启动300秒，本地媒体命令300秒，不在恢复时重置同一请求的推理期限；仅管理自有服务。

### 7. 实际执行与最终准入

本轮只准备。后续开始VCO-07实施时先完成定向与兼容检查，不运行全库；真实推理/超分与测试串行。实际生产验证须有确切的新修订与执行授权，不通过调用旧VCO-05 runner重复POST。原三scene预算219/110/134可作为已知完整时间轴案例，语义计划、已接受图、PCM与字幕按现有证明继承；新源片全部重新建立观察/诊断，不继承旧片接受。

源片：原始请求/输出/全帧PTS与裁剪映射、VCO-02声明、VCO-04当前报告/风险回应、实际完整观看分别记录。自动机器unverified可以在VCO-04契约下被完整观察回应，但不得篡改机器状态；无实际播放器或无观察时等待，不写passed。

超分：每个原生保留帧只有一个输出，沿原RealESRGAN及1080p目标链；合成完整原PCM样本/字幕，total_frames=ceil(total_samples/3000)，不截尾音频、不重配音。最终片重新完整观看并绑定确切候选、模型/预算/输入SHA。发布仍为独立显式 `make-video --run-dir ABS --publish`，没有该操作不写delivery通过；同run重放零新增POST、邮件或再次发布。

VCO-07的软件、实际源片、超分合成、最终观看与显式发布分项记录。全库回归按2026-10-24用户要求留VCO-08/项目收尾，不能因旧C稿提到fresh全库而在本任务提前执行或登记通过。没有真实生产链结果时VCO-07不得按本设计自动COMPLETED。

## Files

新增：

- `src/video_ai/planning/scene_execution.py`：上述纯预算、验证与模式分派。
- `src/video_ai/runtime/scene_execution_records.py`：whole证据、冻结闭包、预算持锁写入和只读重建。
- `tests/unit/test_scene_execution.py`、`tests/unit/test_scene_execution_records.py`：预算/严格身份/证据/只读行为。
- `tests/integration/test_whole_scene_flow.py`、`tests/integration/test_whole_scene_recovery.py`：真实CPU媒体、替身生产贯通及崩溃/漂移恢复；明确fixture_only，不计真实观看。
- 实施时新增 `docs/task-designs/VCO-07-plan.md`、`VCO-07-verification.md`、`VCO-07-operations.md`，据实记录阶段/命令/日志/限制。

修改：

- `src/video_ai/config.py`、`planning/scene_video_prompts.py`、`runtime/production_inputs.py`、`runtime/scene_video_prompt_records.py`：精确配置、prompt schema2与冻结role。
- `planning/scene_clip_continuation.py`、`runtime/scene_clip_records.py`、`production_scene_clips.py`、`planning/scene_media.py`、`runtime/scene_media_records.py`：统一执行预算和inputs/complete schema3。
- `runtime/production_scene_upscale.py`、`production_scene_composition.py`、`_scene_composition_materialized.py`、`_scene_upscale_records.py`：完整保留帧消费者和转交守卫。
- `planning/scene_revision.py`、`runtime/production_scene_revision.py`、`scene_revision_records.py`、`_scene_revision_plan.py`、`_scene_revision_origins.py`、`_scene_revision_origin_clips.py`、`_scene_revision_readers.py`：schema3渲染身份、源execution节点/继承和预算闭包守卫。
- `runtime/scene_continuity_records.py`、`production_scene_continuity.py`、`scene_clip_observations.py`、`scene_final_observations.py`、`production_scene_delivery.py`、`scene_completed.py`、`production_scene_pipeline.py`：新完整索引接入与准入恢复；现有观察协议不放宽。
- 对应既有测试按下节矩阵扩充。`production_visual_plan.py`的原 `plan_scene_clips()`、语义 `production_scenes.py`、实验VCO-05冻结证据和VCO-06 profile均只读复用，不为whole重写语义plan或重新封存旧profile。

## Tests

当前是设计，不运行尚不存在的产品测试，不预记passed。实施第一步只写RED，先证明原分段预算不能满足whole的320/321及三scene完整映射，再实现纯预算和证据接口。以下均为实施时命令，所有Python先bootstrap，以Invoke-VideoAiNative执行；每批退出非0即保留现场并停止后续批次。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco07-core'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_scene_execution.py',
 'tests/unit/test_scene_execution_records.py',
 'tests/unit/test_config.py','tests/unit/test_production_inputs.py',
 'tests/unit/test_scene_video_prompts.py',
 'tests/unit/test_scene_clip_continuation.py',
 'tests/unit/test_scene_revision.py','tests/unit/test_scene_media.py',
 '-q','--basetemp',"D:/VideoSi/cache/video-ai/temp/vco07-core-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $VideoAiExitCode
```

另起同样bootstrap的 `vco07-flow`，精确文件为 `tests/integration/test_whole_scene_flow.py tests/integration/test_whole_scene_recovery.py`；替身阻断所有真实模型/网络/SMTP；CPU FFmpeg生成原生16fps小画幅完整媒体（320帧及多scene），断言整片真实probe/decode、映射、PCM/字幕和观察状态。不得把测试合成视频当自然效果证据。

兼容分文件串行执行，避免合跑掩盖长链失败；每文件独立bootstrap/CommandId/basetemp，均使用以下参数向量形态：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco07-compat'
$Vco07CompatibilityFile = 'tests/unit/test_scene_clip_records.py'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',$Vco07CompatibilityFile,
 '-q','--basetemp',"D:/VideoSi/cache/video-ai/temp/vco07-compat-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $VideoAiExitCode
```

依次将上例文件替换为以下确切文件，逐项记录命令、退出码与用例数，不声称一次合跑：

1. `tests/unit/test_scene_clip_records.py`
2. `tests/unit/test_scene_clip_observations.py`
3. `tests/unit/test_scene_revision_records.py`
4. `tests/unit/test_scene_media_records.py`
5. `tests/unit/test_scene_continuity_records.py`
6. `tests/integration/test_scene_clip_generation.py`
7. `tests/integration/test_scene_video_prompt_flow.py`
8. `tests/integration/test_scene_revision_flow.py`
9. `tests/integration/test_scene_pipeline_recovery.py`
10. `tests/integration/test_scene_continuity_recovery.py`
11. `tests/integration/test_scene_media_flow.py`
12. `tests/integration/test_scene_media_recovery.py`
13. `tests/integration/test_scene_composition_recovery.py`

各批预期退出0、无缺依赖skip；允许按文件限时保留中断，不得计通过。全库不在本阶段命令中。

必须覆盖：

- 旧无scene_rendering、旧精确两字段visual_v2、显式segmented和显式whole四种分支；旧options/inputs/graph/request/96guard逐字段等价。未知mode/schema/多字段/缺角色/用当前config改旧run拒绝。
- F=1/93/94/96/110/134/219/320及321拒绝、错序/间隙/重叠/缺尾scene、bool和不整帧；三scene463帧及VCO-05320/321原生映射，无 conditioning head 或重复输出。
- final-assessment/作者反馈/根SHA/原媒体/PNG/映射/资源/模型/graph任一漂移或缺项拒绝；只修改verified/ready布尔值无效；技术通过但实际观察缺失不准入；新生产片不能复用首例观察。
- schema2 whole提示与纯clips绑定，无循环SHA；schema1旧提示不能删行混入whole；changes来源及跨修订原review保持，审计JSON/其他scene动作不进入positive。
- whole↔segmented同名clip失效正确；不重新出图/配音、不继承视频观察；whole多代revision/部分common继承、源预算guard、late failed原始观察、VCO-06研究候选来源拒绝。
- 新budget落盘和每个旧持久化边界中断；重放同intent零第二POST，HTTP未知只查询原任务；media/aggregate缺marker只由原writer恢复，status零写入；旧completed-prefix/最终delivery重放不二次发布。
- 每份源/最终观察完整绑定实际媒体与请求；unverified/failed/漏回应/新增风险阻止推进；全帧超分与精确PCM/字幕、最终观看和显式publish分别有证据。fixture仅证明状态协议。

## Acceptance

1. VCO-05首例证据闭包被实际核验并冻结，当前只在上述有限工程包络内显式启用whole；缺证据/新内容未观看/超范围均不能发放生产ready。跨题材、更长和多窗的未验证限制始终可见。
2. 新执行预算统一贯通请求、裁剪、帧映射、观察、超分、合成、修订与交付；每个scene一次请求，完整原时间轴、16fps、PCM样本和字幕均保持，无额外或遗漏输出帧。
3. 缺省旧配置、旧冻结run、旧schema2提示/渲染身份/原96预算和原graph恢复逐字段不变。显式模式/预算/证据漂移在写入或POST前拒绝，恢复无重复模型请求或发布。
4. mode变化只失效视频与其后代，合法继承原文/PCM/字幕/语义plan及已接受图；同名clip不继承旧观看。源预算和所有原始失败记录保持可核验。
5. 新定向与规定兼容检查有完整日志；实际新生产源片及完整动态观察、逐帧超分、合成、最终完整观察、显式发布与重放各有独立证据后才可登记VCO-07完成。全库按用户要求留VCO-08，不预记其通过；缺真实执行授权/结果时仅交付软件进度或如实交接。
6. 未引入生产校色、跨窗后端或替换JIM-08多片续接验收；VCO-06完成和VCO-05单例不能代替本任务真实生产验证。

## Risks

- VCO-05系统内存峰值接近物理总量。上限是保守工程限制，不是装载保证；每次真实任务仍须资源预检、记录与失败停止，不能自动降规格。
- 跨题材/材质/运镜未验证。代码保持通用，真实质量必须逐新片观察；不写鸟类题材特判，也不把任意内容宣称为已通过。
- VCO-05原selected图在VCO-06色彩解释门槛可能unknown；本任务不通过换标签宣称sRGB。VCO-02报告必须保留unknown，VCO-04可按其契约接收unverified诊断并要求实际回应；若现有媒体消费者无法证明必需解释则等待，不绕过。
- 旧C阶段稿的裸全库要求已被用户2026-10-24决定覆盖；本任务只运行规定定向/兼容，VCO-08负责全库。原JIM-08及历史SHA保持。
- 本设计记录工程选择，尚无VCO-07产品实现、实际生产请求或发布结果；本轮用户只要求准备。实施中的真实输入、明确执行范围和作者观察按实际记录取得，不预造未来路径身份、观察或成功。
