# JIM-07 跨阶段恢复、修订运行与局部返工

## Goal

把已经完成的段落规划、即梦候选/参考图、邮件选择、Wan 过程观察、逐帧超分、候选及正式交付接入可续作的 `make-video`。普通续作只消费原任务和确切接受记录；显式返工建立新运行，只重新生成依赖变更的内容，保留原运行和原始观察。

前置任务 JIM-06 已于 2026-10-20 记录 COMPLETED：最终全库 3396 passed，历史 456 passed，退出 0，342 项文件身份匹配；详见 `JIM-06-verification.md`。本文规定后继实现，不声称 JIM-07 已实现或已测试。

## Scope

包含新策略的全流程协调、CLI 等待/续作、原阶段接口的跨阶段中断、只读完成重放、显式邮件重发、修订 DAG、来源可核验的局部媒体继承及其准入适配。保留 `paragraph_jimeng_v1`、原生 16 fps、cut、1920×1080、完整原文/PCM/字幕和现有模型。按用户最新澄清，视频总帧数不设上限，帧率不变；测试样例不是成片长度限制。

不实现自动收信、网页选择、自动付费返工、自动接受观察、插帧、变速、新模型适配或真实服务验收。不修改旧 shot/schema=1 的状态机、审核和交付协议；不把新策略阶段写成旧 shot 完成记录。真实账号、QQ 收信和实际连续影片质量属于 JIM-08。

## Approach

### 现有接口与必须保留的语义

- 公共入口为 `src/video_ai/production.py:make_video`、`src/video_ai/cli.py:main`。当前 `_run_generation` 仍拒绝新策略；当前 prepared-run `--image-selection` 会返回 `ImageSelectionResult`，不能通过改造旧 `ProductionResult` 的固定 schema 来接通。
- 共用前缀为 `production_storyboard.produce_units`、`production_speech.produce_speech`、`production_timeline.produce_timeline`。最后一项返回 `(timeline, automatic_slots)`；scene 路径只消费完整 timeline，不能把旧 slots/primary-unit 限制施加给 scene。
- `production_scene_plan.produce_scene_plan`、`image_selection_records.load_committed_plan` 提供已提交 Bible、plan、batches 和 clips。
- 无参考的 scene 调用 `jimeng_candidates.generate_candidates(frozen, scene_id, scene['image_prompt'], lock=held)`。**这里必须使用确切 `scene['image_prompt']`**：现有普通候选验证器按此重建请求；不能擅自附加参考版提示词。关联画面只调用 `production_reference_images.produce_reference_batch`，由它使用 `build_reference_prompt`、能力档案、TOS 和冻结参考模型。
- `production_image_selection.prepare_image_batch/consume_image_selection/retry_notification` 管理邮件和选择。已接受批次不重发；未知 SMTP 不自动重发。全部图片与整组观察通过后，还要有 `reference_image_records.require_reference_image_acceptance` 所验证的 Wan 首图清单。
- `production_scene_clips.produce_scene_clips/consume_scene_clip_observation` 管理各片及父子观察。等待父片不阻止可独立推进的其他 scene；不得由协调器自行选一个父末帧或替代其准入。
- JIM-06 的 `produce_scene_upscaled_clips`、`produce_scene_composition`、`consume_scene_final_observation`、`produce_scene_delivery` 和 `scene_completed.validate_scene_completed_prefix` 各自保持原有门槛。观察消费不推理、不编码、不自动发布；正式发布仍是单独动作。

### 公共入口与结果兼容

扩展 `make_video` 的关键字参数，已有参数含义保持：

```python
make_video(config=None, *, script=None, text=None, run_dir=None,
           output_path=None, cpu_planner=None, image_model=None,
           image_selection=None, reference_settings=None,
           email_settings=None, clip_observation=None,
           final_observation=None, retry_email=None,
           revision=None, publish=False)

# 新模块 runtime/production_scene_pipeline.py
produce_scene_pipeline(frozen, *, paths, logger, lock,
                       reference_settings_path=None, email_settings=None,
                       dependencies=None)
load_scene_pipeline_progress(frozen) -> dict  # 严格只读

# 新模块 runtime/production_scene_revision.py
create_scene_revision(source_run, request_path) -> SceneRevisionResult
# 新模块 planning/scene_revision.py
plan_scene_revision(snapshot, request, target_identity) -> dict  # 纯函数
```

`dependencies=None` 使用真实已有适配器；测试可注入固定字段的依赖对象：`planner/image_client_factory/reference_storage/reference_client_factory/smtp_factory/wan_client_factory/wan_service_factory/upscale_client_factory/upscale_service_factory`。不暴露任意 stage callback 来绕过验证器，注入边界仍由各阶段核对冻结身份。

Python make_video 的 reference_settings/email_settings 与 CLI 一样接收本地 JSON 文件路径；稳定读取、保存提交 Artifact 后，内部 produce_scene_pipeline.email_settings 才接收原 JIM-03 parser 产生的设置对象。publish 必须为严格 bool。revision 与顶层 config/output_path/cpu_planner/image_model 覆盖互斥，避免来源与目标配置混用。普通 baseline generate_candidates 抛出的错误由协调器包装为原 ImageSelectionResult 的 blocked/failed/interrupted，未知提交为 blocked；不伪装成只允许早期 stage 的 ScenePipelineResult。

对新策略保留阶段结果原类型和原序列化字段：图片等待返回 `ImageSelectionResult` 或 `ReferencePreparationResult`，动态等待返回 `SceneClipResult`，超分/候选/最终观察/交付返回 `SceneMediaResult`。不在这些固定 schema 内塞入协调器游标。仅新增早期错误结果 `ScenePipelineResult`，字段精确 `schema_version/production_strategy/run_id/run_dir/status/active_stage/log_dir/error`；schema=2，status=blocked/failed/interrupted，active_stage=preflight/units/speech/timeline/scene_plan；无已验证 run 时 run/log 身份均 null。error 沿既有 kind/message/evidence_paths，不能输出秘密或签名 URL。

CLI 保持 `make-video`，增加对应 `--reference-settings PATH`、`--email-settings PATH`、`--clip-observation PATH`、`--final-observation PATH`、`--retry-email PATH`、`--revision PATH`、`--publish`。所有消费/发布/修订参数要求 `--run-dir`；新运行仍只由 `--script` 或 `--text` 创建。image-selection、clip-observation、final-observation、retry-email、revision、publish 六种显式动作互斥，在创建 run、加锁或发送前拒绝非法组合。reference-settings/email-settings 只可用于新策略的普通续作，email-settings 也可配合显式 retry-email；revision 的目标配置只来自修订文件。

带 image-selection/clip-observation/final-observation 时只消费这一份原文并返回原阶段结果，**本次不自动推进下一生成阶段**，保留已有 prepared-run CLI 行为；用户随后普通 `--run-dir` 续作。带 publish 时只验证并调用新策略交付；带 revision 时只准备新修订。revision 路由必须位于来源 RunLock 和普通 completed 快路之前；不能把目标 config/output 传给来源 load_frozen_inputs。旧策略收到这些新参数时在副作用前拒绝，旧 `run/resume` 命令不改。

等待退出码均 3；image_batch_accepted/source_clips_ready/upscale_ready/final_review_ready/delivered 为 0；blocked/final_review_failed 为 2；failed 为 1；interrupted 为 130。不能把单个阶段的 0 当成全片已交付。CLI 显示实际 waiting 状态、当前模板/候选和续作命令；delivered 时由只读交付准入返回确切 movie/subtitle/receipt 路径，不能猜路径或把 candidate 标成正式输出。

### 普通协调顺序和停止条件

1. 新运行沿现有冻结/预检和共用 units、speech、timeline 事务准备完整旁白。共用 `ProductionStateStore` 仅用于这些既有阶段，不伪造后续 shot/storyboard 完成状态。新策略在 `make_video` 构造旧 delivered 结果之前分派。
2. 已有 prepared-run 若无协调器记录，只能在完整读取冻结输入、已有 units/timeline 报告、committed plan 和全部原 PCM 后登记 `source_mode=prepared`；调用既有 prepared 报告及 scene 原文/时间轴验证，另逐项核对 PCM SHA/样本。只有一半前缀或有冲突则拒绝，不能覆盖成新前缀。此模式把 PCM 作为明确的 prepared 输入，不虚构原 TTS 提交。已有合法自动前缀则走 `source_mode=automatic`，核对原 speech/checkpoints。
3. 若无 plan，调用原 `produce_scene_plan`；若有，先只读重建并核验。只有原阶段写接口能补确切外围标志；协调器不手写 complete 或接受记录。
4. 按 plan.batches 顺序寻找首个未接受批次。有 reference_bindings 的批次调用 `produce_reference_batch`；无 reference_bindings 的批次依 scene 顺序生成/恢复原候选，再调用 `prepare_image_batch`。同一批次混合两类的非法计划拒绝。返回等待、模型配置缺失、邮件未知或错误即停止；已接受批次继续下一批，不重新出图或发信。
5. 全部批次和全组观察已经接受时，使用 `build_reference_image_acceptance` 生成确切 Wan 输入并通过原 `require_reference_image_acceptance` 核验。独立小 writer 仅持锁提交该纯推导记录，不能借机访问新模型/TOS 或刷新已受理任务。这样也覆盖全片没有参考批次的合法计划；有完整记录则只读核验。
6. 调用 `produce_scene_clips`。awaiting_continuity_review 原样返回并列出其 observation_templates；blocked/failed 原样返回。source_clips_ready 后显式再 require 完整源片接受，再进入超分。
7. 超分成功后调用候选合成。候选始终返回 awaiting_final_review、final_review_failed 或 final_review_ready。即使历史已有 passed 最终观察，普通续作也停在 final_review_ready；只有显式 publish 才调用交付。
8. 已正式完成运行的普通续作和重复 publish，走**加锁、创建日志和 invocation 之前的只读快路**：完整 `validate_scene_completed_prefix`，重建 delivered 结果，无服务、POST、邮件、提取、复制、编码、锁文件或记录写入。已有 completed 交付证据损坏时只读 blocked，不退回生成路径； publishing 前缀只能由显式 publish 恢复。已完成运行收到新的观察/选择/修订外的变更动作时拒绝，不覆盖旧接受。

同一次普通调用至多推进每个可新提交 logical node 一次；循环仅遍历有限 batches/clips，不对 unknown/failed 再试。阶段内部有限 GET/原任务恢复沿原实现。已有有效外围收据允许原 writer 恢复，不能因协调游标缺失再生成。后面阶段的本地冲突在任何新的较早阶段副作用前预检；已知终止/坏媒体/孤立原文按各阶段现有裁决保留，不自动删除。

### 协调记录、锁与边界

新目录 `production/scene-pipeline/`，不把它交给旧 shot completed 验证器。

- `inputs.json` 精确 `schema_version/production_strategy/run_id/algorithm/frozen_options_sha256/source_mode/revision_commit_sha256`；algorithm=scene_pipeline_v1，source_mode=automatic/prepared/inherited，最后一项普通运行 null。首次登记后不变。
- `common-inputs-ready.json` 精确 `schema_version/run_id/inputs_sha256/source_mode/units/timeline/speech/pcm/created_at`。units/timeline 是原报告或明确继承视图的 Artifact；automatic 的 speech 为原报告 Artifact，prepared/inherited 的 speech 为 null，继承的原 speech 证明由 import 绑定，不伪造当前 TTS 报告；pcm 按 unit 顺序为 `unit_id/audio/samples`。所有原文、报告、48k mono PCM16、样本区间、零停顿和总帧覆盖从原数据重建，不由该 ready 标记赋予可信度。
- `logs/production/scene-invocations/<UUID>.json` 精确 `schema_version/run_id/action/inputs_sha256/submissions/result/created_at`。action=advance/image_selection/clip_observation/final_observation/retry_email/publish；submissions 是本次显式本地文件原始 Artifact 数组，result 为原阶段 to_dict。仅在持锁调用线程、阶段清理完成并再次核验所有权后写入。完成快路不写此记录。
- `load_scene_pipeline_progress` 精确返回 `schema_version/production_strategy/run_id/common/plan/images/clips/media`，各项由严格只读已有证据推导。common 精确 `status/record/source_mode/error`，plan 精确 `status/record/error`，status=pending/running/ready/blocked/failed，record 是已验证记录的绝对路径或 null；images 精确 `status/accepted_batch_ids/next_batch_id/selection_template/wan_inputs/error`，status 为 pending/running、原图片等待/未知/错误状态或 images_ready，ID 数组按 plan 顺序，路径绝对或 null。clips 等于原 `load_scene_clip_progress(frozen,units,timeline)` 的结果，media 等于 JIM-06 `load_scene_media_progress` 的结果；公共前缀尚未 ready 时 clips/media 为 null。error 统一 kind/message/evidence_paths。可变 stage/status 字段只是诊断，不能授权推理或交付。缺失、损坏和合法待完成前缀分别报告，不补写。

所有写路径依然是真实同 run RunLock、PathPolicy 和 caller thread。协调器持锁调用子 API，子 API 不释放调用方锁；每个阶段的自有服务作用域仍由该阶段关闭。无外部服务接管或后台预取。主异常和 cleanup/失锁错误均保留，不能返回成功：清理失败转 failed，并按结果类型撤销 readiness 字段（all_images_accepted=false、source_clips/wan_inputs/delivery_receipt 等置 null），保留已验证可供检查的候选路径。过期线程不写新 invocation。

新增 `boundary(point)` 位于 common-ready、pipeline-inputs、image-accepted、wan-inputs、clip-accepted、upscale-ready、candidate-ready、final-accepted、delivery-returned、invocation-written 之后，专供故障注入。阶段内部边界继续用原模块，不把网络替身放入生产业务分支。

### 显式 SMTP 重发

retry-email 文件精确为 `schema_version/run_id/batch_id/part/expected_attempt_sha256/reason`，schema=2，part 严格正整数，reason 非空。稳定读取原字节后调用原 `retry_notification`，其原 attempt hash 必须完全匹配；本次新 Message-ID 和 MIME、原未知证据均由原 API 保存。普通续作不调用此 API。email-settings 文件使用既有 JIM-03 邮件设置结构，仅作为原 `_transport_settings` 允许的传输修复；冻结收发地址、批次/图片/观察身份不变，凭证只读取环境变量。

### 修订请求和内容依赖图

修订文件精确 `schema_version/production_strategy/revision_id/source_run_id/source_options_sha256/requested_at/kind/scene_ids/clip_ids/choices/config_path/image_model/output_path/reason`。schema=2；revision_id 为规范 UUID；source_options_sha256 为原 options 原始字节 SHA；requested_at 带时区、不晚于当前时间；reason 非空。kind 为：

| kind | 必须提供 | 规则 |
| --- | --- | --- |
| reselect_images | 非空 scene_ids 和等长 choices | choices 每行精确 scene_id/candidate_id/sha256，来自原运行确切已完成候选；clip_ids 空，其余配置项 null。新选择只是新运行的待确认草稿，不自动 passed。与原已选候选完全相同则拒绝无效修订。 |
| regenerate_images | 非空 scene_ids | 其他目标/choices 为空、配置项 null。目标 scene 新请求，其参考依赖后继全部失效；不自动改 seed 或模型参数。 |
| regenerate_clips | 非空 clip_ids | scene_ids/choices 空、配置项 null。问题片及其 continuation 后继失效；不同 scene 的切镜不继承父子关系。 |
| reconfigure | config_path 为目标配置绝对路径 | 目标数组和 choices 空；image_model 可选覆盖，output_path 可选目标。对有效配置、模型戳和 workflow 原始字节的实际差异分类，不因显示名称相同复用旧模型结果。完全无差异则拒绝。 |

没有 config 的修订继承原冻结配置及模型参数，output_path 使用新 run 默认正式路径；不能覆盖原 output_paths。源原文原始 UTF-8/BOM/换行字节保持。改变文案应新建独立运行，不借本请求重解释旧范围。所有 ID 唯一、按原 plan 顺序归一；未知 ID、bool 数值、额外字段或跨运行候选拒绝。

`plan_scene_revision` 的 snapshot 精确为 `source_options/bible/scene_plan/image_choices/clip_nodes/upscale_nodes/pending_effects`：这些是运行层已经验证的规范值；clip_nodes 为原 clips 与各自 accepted/rejected/pending 状态，upscale_nodes 为每帧技术接受和提交状态，pending_effects 为需要原任务核对的逻辑节点和原 intent SHA。target_identity 是目标有效配置、模型戳、workflow SHA、语音/字体/规划设置摘要；纯函数不访问路径或发请求。返回精确 `schema_version/algorithm/source_run_id/request_sha256/target_identity_sha256/content_edges/admission_edges/dirty/reusable/blocked_effects/reasons`，algorithm=scene_revision_v1。dirty/reusable 是固定域 `common/plan/images/choices/image_group/clips/clip_reviews/upscale/composition/final_review/delivery` 的有序 ID 数组；reasons 为 `node/cause` 行。

图中区分**内容依赖**与**准入门槛**，否则一次重选会错误地把所有无关片段都重做：

- 内容边：基准 choice → 引用它的 image；image → 本 scene choice；scene choice → 本 scene 全部 clips；父 clip → 其 continuation 子 clip；clip → 其过程观察/全部 upscale frame；全部帧、原 PCM/字幕/字体 → composition → final_review → delivery。引用关系直接取 plan.scenes[*].reference_bindings，父链直接取 committed clip budgets，不靠相邻 ID 猜。
- 准入边：全组图片观察 → 所有 clip；全部源片观察 → 任意 upscale；全部 upscale → composition；确切最终接受 → delivery。这些门槛变化会重新检查，但不把媒体内容不变的其他 scene 强行标成 dirty。
- 重选/重出图对上述内容边求传递闭包；有任一图片变化则新 image_group 必须重新观察，不能沿用旧整组通过。仅重做 clip 或超分、且所有图片/Bible 相同，可显式继承原图片组观察的来源证明。无关动态片只在其比较图、动作提示、父链、预算和模型全部相同且原过程观察通过时复用。
- image_generation 变化使全部 images 及其后继 dirty；reference_generation/capability/storage 变化使所有关联图片及其后继 dirty；Wan 模型/workflow/profile 变化使全部 clips 及其后继 dirty；upscale 模型/workflow 变化使全部 upscale 及其后继 dirty。语音、规划、字体、时间轴或其他影响公共输入的配置变化保守地使 common 开始的全部内容 dirty。新配置收发地址不同则拒绝，不扩展本项目已确认的邮箱范围。
- 每个有效修订都新建 composition/final_review/delivery，绝不继承最终候选接受或正式输出事务；字节巧合相同也不复用最终观察。显式重新生成是新 logical node，不伪称恢复原任务。
- reusable 仅包含内容闭包外且已通过该节点原有准入的节点。未接受、本地坏证据和失败节点不复用；尚未开始的节点可在新运行正常生成。新运行将要生成的节点若对应原未知/进行中的付费意图，放入 blocked_effects，先回原运行查询/核对，不能换 run 规避未知提交。未知邮件若仍需重新发送也等待原批次处理；已有确切选择的原邮件不成为新运行的待发送队列。

### 新运行准备与冻结绑定

纯计划中 clip_nodes 每行精确 `clip_id/record/acceptance/status`，record 为已准入的 owned clip.json 或 inherited clip 视图、尚无技术结果时为 null，acceptance 为原接受收据或 null，status=accepted/rejected/pending/unknown/running；upscale_nodes 每行精确 `frame_id/record/status`，record 同理为 owned frame.json、已验证继承视图或 null，status=ready/terminal/pending/unknown/running。pending_effects 行精确 `node/intent_sha256/status`，status=unknown/running。image_choices 为原完整已接受选择行。request_sha256 使用 `canonical_digest(request)`；原始请求文件 SHA 另由 intent.request Artifact 绑定，重复 revision_id 时原文件字节也须相同。

target_identity 精确 `config_sha256/image_generation/reference_settings_sha256/model_stamps/workflows/voice_sha256/font_sha256/planning_sha256`：config_sha256 为目标 raw config 的规范摘要，image_generation 为含 CLI 覆盖后的有效设置，workflows 为 role→原始文件 Artifact，model_stamps 沿现有 ArtifactStamp；其余均绑定有效内容而非文件名。reference_settings_sha256 包括模型、能力档案实际字节和存储配置；尚未绑定时为 null。没有 reference 重配置的修订可通过 import 显式继承原 late-bound reference settings，保留原凭证环境变量名；`reference_settings.py` 的 resolver 只在冻结 commit 证明下提供该视图。已有相关 import 时，后来不同的 supplemental settings 不能改变承诺身份；没有任何参考依赖 import 且原本未绑定时，仍可走 JIM-04 的正常首次补充配置。

reselect_images 的内容根是 **choice**：原目标候选集合仍可作为已完成的技术结果导入，目标选择只成为待确认草稿；引用该新 choice 的后继 images 才重新生成。regenerate_images 的根才是 image，并连带其 choice。image 域的技术候选完成不等于 choice 域的人工选择通过，不能混为一个 accepted 状态。

所有 Windows 文件名使用 `token=canonical_digest({'domain':domain,'key':key})` 的 64 位小写十六进制串；import_id 只是逻辑 ID，不能把含冒号的 frame_id 直接作为文件名。role 来自受验证的媒体字段：pcm/generated/source/first_frame/last_frame/input/input_copy/model_output/output/selected_image，或按原列表顺序编号的 candidate_000001、comparison_000001 等；保留经过格式验证的原扩展名，不接受调用方路径片段。

新增 `SceneRevisionResult` 精确字段 `schema_version/production_strategy/source_run_id/run_id/run_dir/status/revision_commit/log_dir/error`，status=revision_ready/blocked/failed/interrupted，退出码 0/2/1/130。ready 只表示新运行已冻结并准备继承证据，**没有新云请求、邮件、Wan、超分或候选编码**。后续通过 `make-video --run-dir <new>` 开始执行。

来源目录只读，不创建来源锁、invocation 或反向指针。来源存在活的写锁则拒绝准备，避免复制正在变化的前缀。目标目录按 `requested_at` 转 UTC 的 `%Y%m%d-%H%M%S` 加 `-` 和 revision_id.hex 前 12 位，位于目标 config.project_root/runs；同请求重试定位同一目录，完整 UUID/原始请求 SHA 不匹配则拒绝碰撞。原始请求副本和源 options 在首次写入前稳定读取、核对传入 hash 和当前内容。

新目录 `production/scene-revision/`：

1. `intent.json` 精确 `schema_version/production_strategy/run_id/revision_id/source_run_id/source_run_dir/source_options/request/target_identity/invalidation/created_at`。source_options/request 为原始 Artifact（request 在目标保存原字节副本）；target_identity 为上节完整目标身份，invalidation 为纯计划。先持目标 RunLock 保存意图，再复制。
2. 将 reusable 原 PCM/技术完成候选/已选原图/片段/末保留帧/超分 PNG 按字节复制到 `media/<domain>/<token>/<role><extension>`，由每项唯一 staging/ready/不覆盖晋升收据证明本次所有权。不能用硬链接、重新压片或重提帧。缺少 ready 的未知文件不接管；另建唯一尝试，保留旧文件。只读验证失败不修补来源。
3. 每个导入证明 `imports/<token>.json` 精确 `schema_version/production_strategy/run_id/import_id/domain/key/source_run_id/source_options_sha256/source_identity_sha256/dependency_import_ids/source_json_snapshot/raw_files/source_artifacts/local_artifacts/view/view_sha256/view_artifact/created_at`。import_id=`<domain>:<key>`；domain=common/plan/reference_settings/image/choice/image_group/clip/upscale。common/plan/reference_settings/image_group 的 key=all，其他使用实际 scene_id/clip_id/frame_id。source_json_snapshot 精确 files/inventories/absent_paths，files 为原 JSON Artifact，inventories 为 directory/paths 行；只覆盖该节点和祖先的必要证据，其他 scene 的合法推进不能污染此范围。raw_files 使用独立 path/bytes/sha256 结构允许 0 字节原 HTTP/命令日志；普通 Artifact 仍要求正 bytes。local_artifacts 行精确 role/source/target，均为完整 Artifact、bytes/SHA 必须相等。
4. view 是**显式继承的规范视图**，不能复制修改旧 request/intent/submission/观察原文来冒充新任务。原 paid task UUID、graph、原观察者和时间始终留在 source_* 证明中。common/plan 视图可重建当前 run 与本地 units/timeline/plan 摘要；clip/upscale 视图保留原 run_id 和 inputs/request/submission/parent 的执行身份，只把渲染所需媒体路径映射为本地副本。当前祖先关系由 dependency_import_ids 与已验证内容语义建立，不能把原执行摘要改成尚未产生的当前请求。映射由 local_artifacts 一一确定，其他语义字段必须等于原节点；不重新去头、改帧序或改变样本位置。先按拓扑顺序写 `views/<domain>/<token>.json` 并 fsync，view_sha256=canonical_digest(view)，view_artifact 绑定该文件确切字节。视图不依赖尚未冻结的目标 options SHA，避免 commit→options→view 的摘要循环；实际新阶段 inputs 仅在目标 options 冻结后产生。不生成假的旧 checkpoints。
5. `imports.json` 精确 `schema_version/production_strategy/run_id/revision_id/imports`，imports 为上述 sidecar 的有序 Artifact 数组。`invalidation.json` 保存纯计划原值。`commit.json` 精确 `schema_version/production_strategy/run_id/revision_id/source_run_id/source_run_dir/source_options/request/target_identity/invalidation/imports/created_at`，source_options/request/invalidation/imports 为 Artifact，target_identity 为与 intent 相同的规范身份对象。commit 只在全部本地复制和原来源语义/快照前后复核通过后保存。
6. 为**新建修订运行**扩展 FrozenInputs schema=2 的条件字段 `scene_revision`，值为上述 commit 的 Artifact。普通 schema=2 字段集合不变，旧 schema=1 拒绝此字段。`freeze_inputs(..., scene_revision=None)` 仅在非空时走明确的新修订分支；loader 验证固定 commit 路径、完整 UUID、目标身份与实际冻结 config/模型戳/workflow、全部 import 摘要。不得在旧 options 中追加此字段。冻结后的 options 摘要因此递归绑定全部继承证明，防止以后替换 origin 而仍沿用旧候选观察。
7. 目标冻结前后重核 intent.target_identity；模型/配置/workflow 变化则停止，不冻结成另一身份。原 options 未落盘的中断只由绑定原 intent 的修订冻结恢复分支继续，逐文件检查自己的准备收据，不能放宽普通 freeze 的独占创建规则。options 已存在则严格 loader 核验，不覆盖。最后写 `ready.json`，精确 `schema_version/run_id/revision_id/commit/options/created_at`，两者为 Artifact。ready 丢失可从确切 commit/options 恢复，时间取 options.created_at。

每次复制先写 `copy-intents/<UUID>.json`，字段精确 `schema_version/run_id/import_id/role/source/staging_path/target_path/created_at`；路径均受目标策略限制。copy-ready 位于 `copy-ready/<token>/<role>.json`，字段精确 `schema_version/run_id/import_id/role/intent/source/staging/target/file_id/recipe/created_at`，intent 为原意图 Artifact，file_id 为原 staging 的 device/inode，recipe 精确 algorithm=identity_revision_copy_v1、parameters={}。写 ready 前完成流式复制、fsync、源前后及 staging SHA；不覆盖 rename 后确认 target 的同一 file ID 和 SHA。断在创建 temp 后、file ID 尚无 durable ready 时不得接管它；可另建 UUID 尝试，保留原 intent/temp。已有目标只有原 ready 的 file ID+SHA 能证明本次所有权时复用。各意图均要预检，不忽略孤立/冲突 ready。

reference_settings 是单独的上下文 import 域，key=all，沿同一 sidecar 格式绑定原 late-bound marker/能力档案和目标一致性；它不是媒体 dirty 数组。只有目标有效参考设置与原值相同才导入，否则走正常新绑定并按图使关联图片失效。SceneRevisionResult 在来源未验证时 source_run_id 也为 null，在目标尚未建立时 run_id/run_dir/revision_commit/log_dir 为 null；错误证据仅可指向已经验证的来源或目标根。

### 继承的准入适配与证据守卫

common.view 精确为 `units/timeline` 两个既有 payload；plan.view 精确为 `bible/scene_plan` 两个既有规范对象，重建当前 run、units/timeline 摘要和提交绑定。image.view 为原候选规范行组成的 `scene_id/candidates`；choice.view 为原选择规范行；image_group.view 为完整原接受对象的有证明视图；clip/upscale.view 为原 clip/frame 技术行的有证明视图。规范字段的媒体 Artifact 使用 local_artifacts 映射，新 PCM 的 stat 字段取本地副本真实值；样本/帧/文本/模型/提示/选择语义不得改变。原 HTTP、命令及观察证据保持来源路径和原始身份，只由下述 Origin guard 验证，不能被当作当前 run 的媒体 Artifact 随意接纳。

新增只读 `RevisionGuard`：`verify_captured_bytes()` 验证冻结 commit/imports、注册 view 摘要、指定来源闭包快照和本地副本；`verify_global()` 在此基础上验证当前锁及原有模型/工具约束。普通 stage store 只保存本 run 的 guard_paths，不把来源路径塞入它的 run_path。每个来源有严格限定根目录的只读 Origin store；相关 stage store 的 verify_global 和只读准入最后检查调用 RevisionGuard，并在 for_root/克隆/下游交接中传递同一比较绑定。注册表为确切 view Artifact/规范摘要→import_id，只对这些已证明子树走继承 capture；其他对象仍走原 capture，不能根据“路径在外面”自动信任。这样保留普通 run_path/Artifact 的限制，也防止递归解析继承技术行的 evidence 时错误地当成当前 paid request。

来源本身为修订运行时递归执行同样的原准入，保留直到实际 owned 请求的整条链；按当前递归栈中的 run_id/commit 摘要检测循环，同一 run_id 的冲突 commit 拒绝。已经验证完毕的同一祖先可被多个分支共享，使用时仍重核其捕获字节，不把合法 DAG 共享误判为循环。不得把一层已派生视图当作最初模型证据。

新增 `runtime/scene_revision_records.py`，公共只读接口：

```python
require_scene_revision(frozen) -> dict
require_revision_import(frozen, domain, key, *, context) -> dict
load_scene_common_prefix(frozen) -> tuple[dict, ProductionTimeline]
```

FrozenInputs loader 只验证 scene_revision 的固定路径、字节/记录结构、目标冻结身份和递归 Artifact 绑定，不调用会再次加载当前 FrozenInputs 的全语义入口。`require_scene_revision` 在已经加载的 frozen 上执行完整来源/节点语义准入并建立 RevisionGuard，避免 loader 与公共 require 递归调用自身。

普通运行没有 scene_revision 时完全沿原路径。修订运行的每个 logical node 只能有 owned 原阶段记录或一个有效 import：两者竞争、无 commit 的 sidecar、引用闭包缺项或 dirty 节点出现 import 均拒绝，不能使用“本地文件不存在就找来源”的宽松 fallback。

从 JIM-04/05/06 的现有只读验证中提取**指定节点及其必要祖先**的语义准入 helper，供 import 使用；不降低原完整入口的整组/全片门槛。它必须重建原冻结配置、实际 request/graph/HTTP/history、媒体格式/像素/映射、已接受观察与比较图，而非只看一个 passed 标志。缺失原证明不修复、不 GET、不重发。capture 先记录原始字节和目录清单，再执行语义验证并比较；包括正/空日志、相关缺失路径、源 PCM SHA 和工具/模型语义，沿 JIM-06 的 compare-before-bind 守卫，不能把后来字节当新基线。

当前运行通过 import 取得规范视图后，仍须满足**当前**准入边：图片组尚未确认时不能把继承 clip 标 ready；全部源片未接受时不能把继承超分标 ready。源视图语义相同也不能凭原整组摘要跳过当前组的重新观察。相同内容、相同作用域的原选择/片段观察可作为明确的 inherited acceptance，保留原文和来源，不伪造新 reviewer/viewed_at/passed 原文。

具体适配点限于：`image_selection_records` 的 plan/candidate/accepted-choice 读取；`reference_settings/reference_image_records` 的有效参考配置、原图/参考来源读取；`scene_clip_records` 的节点收集、clip request 比较输入读取；`scene_media_records/_scene_upscale_records` 的已有帧读取；composition 的最终比较输入读取。由 resolver 返回 owned 原记录或带 commit 证明的 inherited 视图；不要在 `production_scene_composition` 中继续硬读当前 clip/request.json 而绕过 resolver。原 stage JSON 的普通字段规范不改；继承格式独立且只有冻结 scene_revision 才能激活。

已选基准图可保留来源对象的真实 bucket/key/etag，不改写成新 run 的 TOS 对象。关联画面需要新提交时重新核对实际对象及 URL 有效期；旧对象不可读则可由新运行按既有协议发布自己的新对象，不能假造原对象存在。已受理原请求的 URL 不刷新后重投。导入准备本身零网络。

公共只读和每次真正提交/接受/发布之前，复核 commit、imports、所需 source 快照和本地副本。缓存仅限一次调用并绑定 SHA；不得用 stat-only 或跨调用缓存。相关来源记录/原文/PCM/媒体变化、junction/符号链接/路径逃逸、同字节新所有权冲突或失锁均停止。来源模型/原始证据丢失时拒绝复用，不虚构历史工具二进制身份。

## Files

- 新建 `src/video_ai/runtime/production_scene_pipeline.py`：协调、结果透传、明确等待/发布、边界和清理。
- 新建 `src/video_ai/runtime/scene_pipeline_records.py`：公共前缀、pipeline inputs/invocation、只读进度和早期错误结果。
- 新建 `src/video_ai/planning/scene_revision.py`：规范修订请求、内容/准入双图、失效闭包与复用计划。
- 新建 `src/video_ai/runtime/production_scene_revision.py`、`scene_revision_records.py`：目标意图、复制/来源证明、冻结绑定、恢复、只读继承与视图。
- 修改 `production.py`、`cli.py`：按 frozen strategy 分派、新参数互斥、保留阶段结果、完成快路；旧生产分支及旧 run/resume 不变。
- 修改 `runtime/production_inputs.py`：只在新修订 options 中加入/核对条件 scene_revision，明确修订冻结恢复，不迁移旧文件。
- 修改上节列明的 JIM-04/05/06 reader 及 composition 比较输入 helper：仅增加显式继承分支与可共享的严格节点准入。原字段、协议裁决、once-only 和 caller-thread/锁规则不变。
- 新建 `tests/unit/test_scene_pipeline.py`、`test_scene_revision.py`、`test_scene_revision_records.py`、`tests/integration/test_scene_pipeline_recovery.py`、`test_scene_revision_flow.py`、`test_scene_pipeline_cli.py` 和 `tests/scene_pipeline_helpers.py`。
- 更新 `docs/jimeng-candidates.md` 的实际 CLI 等待/续作/修订示例，创建 `JIM-07-verification.md`；不得提前把真实服务验收写成通过。

## Tests

第一实施动作：在 `tests/unit/test_scene_revision.py` 建 `test_reselected_baseline_invalidates_reference_descendants_but_preserves_unrelated_scene`。固定 S1→S2→S3 参考链、独立 S4、每 scene 的 clip 父子链及原接受快照，调用尚不存在的纯 `plan_scene_revision`，先观察缺模块/接口 RED。断言 S1 的原技术候选可复用、choice 失效；S2/3 的图片与选择、S1/2/3 的片段/超分以及候选/最终/交付失效，S4 的内容仍 reusable；全组观察必须更新，但准入边不得把 S4 媒体错误地变成 dirty。再实现纯算法，不先写协调器。

自动验证均用 HTTP/SMTP/TOS/服务替身与真实 PNG/WAV/MP4/ffmpeg，不运行真实付费模型或发信。新 authentic fixture 在任何 plan/接受提交前构造正值 PCM 与冻结 `max_clip_seconds=0.5`，第一场景为 13 个原生贡献帧，断言真实预算 5/4/4、两次续接；另有独立场景。不能在已经接受的 timeline 上裁短，既有 JIM-06 200 帧回归保持。纯闭包矩阵覆盖完整大映射，不靠大量重复媒体准备代替断言。

计划命令，预期最终均退出 0；新测试本设计阶段尚未创建/运行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-07-tests'
& $VideoAiPython -B -m pytest tests/unit/test_scene_revision.py -k test_reselected_baseline_invalidates_reference_descendants_but_preserves_unrelated_scene -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
& $VideoAiPython -B -m pytest tests/unit/test_scene_pipeline.py tests/unit/test_scene_revision.py tests/unit/test_scene_revision_records.py tests/integration/test_scene_pipeline_recovery.py tests/integration/test_scene_revision_flow.py tests/integration/test_scene_pipeline_cli.py -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
& $VideoAiPython -B -m pytest tests/unit/test_scene_media.py tests/unit/test_scene_media_records.py tests/unit/test_scene_upscale_transactions.py tests/unit/test_scene_final_observations.py tests/integration/test_scene_media_flow.py tests/integration/test_scene_composition_recovery.py tests/integration/test_scene_media_recovery.py tests/integration/test_scene_upscale_flow.py tests/integration/test_make_video_recovery_contract.py -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
& $VideoAiPython -B -m pytest -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

场景和必须断言的结果：

1. 从完整原文进入新策略，逐批基准/关联图、真实 MIME、确切选择与组观察、两次父片等待、超分、候选、最终观察及显式 publish；相同主体参考来源和完整 PCM/字幕/总帧覆盖均通过各原 gate。未选择/配置缺失/SMTP 未知/父片未观察/最终未观察分别在正确状态返回，零越级请求。
2. 对原 image submit/accept/result/download、TOS intent/object、SMTP intent/accepted、selection raw/accepted、Wan intent/raw/history/clip/observation、超分帧/complete、materialized/encode/probe/candidate、final raw/accepted、delivery temp/rename/receipt 和所有新增边界逐项中断。续作同 logical node 只一个 POST/邮件成功发送/原 UUID；原未知不补发，坏证据拒绝；新协调 invocation 不能改变原阶段裁决。
3. 两次完成续作，在调用入口把服务/POST/邮件/提取/编码/复制/锁和写记录工具全部设为失败哨兵，仍只读返回原 delivered；原文件清单、字节、mtime 和外部 file ID 不变。完成证明损坏时同样零写、blocked。
4. 真实 reselect/regenerate image、父 clip 返工、image/Wan/upscale 配置变更；失效闭包准确、原运行文件字节/mtime 不变、无关已观察前缀复用，继承阶段零新推理。新组观察和新最终观察不能由旧原文伪造；任一 dirty 祖先即使输出字节巧合同样也不能复用其后继。
5. 修订意图、每项 copy-ready/晋升、imports、commit、冻结小文件/options、ready 逐边界中断；同 request 定位同 run，原始证明不被改写，无关同名/同字节目标不接管。目标身份/原 bytes/JSON inventory 在 gate 后或 copy/POST 前变化、原日志由空变非空、原 PCM 同 stat 替换、junction 逃逸和失锁分别拒绝。
6. 原任务未知/仍进行中的节点不进入新运行重新生成；原来源证明丢失时不 GET/补标志/猜原任务。部分合法源运行可以只继承已接受且必要祖先齐备的独立分支，不能强求整个失败场景已经 complete，也不能忽略该节点的失败原文。二次修订仍追溯最初 owned task；伪造循环、替换中间 commit 或只保留派生视图均拒绝。
7. 旧 schema=1 全链、原 prepared-run --image-selection 的字段/结果、原 consume-only 行为和 JIM-04/05/06 公共 API/严格普通记录保持；没有 revision 字段/commit 时任何孤立 sidecar 不启用继承。CLI 非法组合先于 run 分配/锁/外部请求拒绝，cleanup 失败不返回 ready/delivered。

保存实际命令、计数、失败和修复记录、退出码以及验证前后 src/tests/workflows/使用文档 SHA；不把计划或替身观察登记成实际视觉验收。Python 始终 bootstrap、`-B`，临时/日志/媒体在 D:/VideoSi，媒体/Python 测试串行。

## Acceptance

1. 新策略可以经 make-video 走到明确的图片、动态和最终观察等待，再显式发布；普通续作没有重复付费或重复邮件，所有原门槛保持。
2. 重选基准、画面/父片返工和模型变更有新冻结运行、可复核失效 DAG 和来源证明；只重做受影响内容，无关已接受媒体可实际复用，原运行不变。
3. 修订准备与各阶段中断在确切原记录上恢复；unknown 等待核对，媒体/身份/所有权冲突停止，不用换 run 或新 intent 掩盖。
4. 已完成前缀重复两次严格只读，缺少证明不修补；旧策略和既有 prepared APIs 的回归通过。
5. 代码、使用说明、CLI 状态/退出码及验证记录一致；全部当前字节的新专项、相关历史和全库结果落盘。真实服务与实际观看仍明确留给 JIM-08。

## Risks

- 跨运行继承增加一类显式证据，必须由新冻结 options 递归绑定；仅复制旧 JSON、改 run_id 或根据同字节猜来源都会破坏准入，不能作为捷径。
- 内容依赖和全局准入门槛不同；混为一图会使全部媒体无谓失效，反过来只看像素相同会错误保留父链/模型变更后的接受。
- 原始模型/记录/媒体不可用时不能安全复用。保留原证据并返回 blocked；可另建无继承的独立运行，不伪造历史。
- 真实服务容量、TOS 可读取性、QQ 收信和模型一致性尚未验收；本项替身结果不能替代 JIM-08。
- 无待用户选择的新增产品需求。上述接口、记录、失效分类和测试是任务板既定范围的实施契约；本文不授权真实收费、邮件或自动返工。
