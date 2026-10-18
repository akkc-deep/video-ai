# JIM-03 候选图邮件、基准选图与等待续作

## Goal

把已持久化的基准及后续批次候选发到已确认的 QQ 地址；用户用文件作出选择，程序核验确切图片并保存接受记录，安全返回等待或批次接受结果。完整选图与整组实际观察齐备前不能准入 Wan。

## Scope

实现 SMTP SSL、可复制候选编号、原文/基准/候选对照、整组对照图、真实附件与 MIME 编码后拆包、单次发送恢复、选择草稿/接受及整组观察、`--image-selection` 续作入口。发件和收件均为 `318575094@qq.com`。

复用 JIM-01 候选和 JIM-02 已提交计划，使用测试准备后续批次；不实现参考图生成、TOS、Wan、动态观察或新策略完整协调器，不自动收信、部署网页、发真实测试邮件或以编号选择代写一致性通过。JIM-02 已先记 COMPLETED；本文件是后继实施契约，不是已实现或已测试声明。

## Approach

### 配置、版本和接口

仅新策略允许 raw 根字段 `selection_email`。纯 parser `parse_selection_email(value)` 返回不可变设置，字段为 `sender/recipient/smtp_host/smtp_port/smtp_security/smtp_password_env/max_mime_bytes/timeout_seconds`。默认依次为上述已确认邮箱两次、`smtp.qq.com`、`465`、`ssl`、`VIDEO_AI_SMTP_AUTH_CODE`、`15*1024*1024`、`60`。地址必须是确认值；拒绝 CR/LF、明文 SMTP、关闭证书验证、bool 数字、非正/非有限 timeout、无效端口/环境变量名及未知字段。密码值只在发送进程环境读取，不保存。

不增加改变旧 ProjectConfig 序列化形状的 dataclass 字段；解析冻结 raw，并在通知记录保存完整有效设置。冻结收发地址、MIME 限额和邮件内容。SMTP 凭证可轮换；修复 host/port/密码环境变量名使用下述 API 的显式 `email_settings`，限定地址、SSL 和既存 MIME 布局不变，保存新发送尝试的传输设置。修复通知配置不调用出图 API。旧 schema=1、视觉审核及 ProductionResult 字段集合保持原样。

新增公开接口（Python 3.12 标准库和既有媒体工具）：

- `runtime/production_image_selection.py: prepare_image_batch(frozen, units, timeline, candidate_manifests, *, batch_index, paths, logger, email_settings=None, smtp_factory=None, lock=None) -> ImageSelectionResult`。输入为同运行完整 units payload、ProductionTimeline，以及按当前 scene 顺序的 JIM-01 candidate manifest 路径列表；不负责生成候选。
- 同模块 `consume_image_selection(frozen, units, timeline, selection_path, *, paths, logger, lock=None) -> ImageSelectionResult`。
- `runtime/image_selection_records.py: load_committed_plan(frozen, units, timeline) -> tuple[dict,dict]`；`validate_batch(frozen, units, timeline, bible, plan, batch) -> None`；`validate_selection(frozen, bible, plan, batch, value, *, accepted_batches) -> dict` 返回规范 `selections/observation`；`require_complete_image_acceptance(frozen, units, timeline) -> dict` 从磁盘重验并返回完整接受记录，不提交 Wan。accepted_batches 为按 batch_index 排序的已验接受对象列表。
- `adapters/selection_email.py: build_messages(batch, media, *, created_at, sender, recipient, max_mime_bytes, attempt=1) -> list[dict]`，每行 `part/total/message_id/mime_bytes/attachment_bindings`；`SmtpSender(settings, *, smtp_factory=None).send(mime_bytes, *, before_data) -> dict` 成功仅返回 `smtp_code`。使用脱敏的 EmailPreconditionError（DATA 前）、EmailRejected（DATA 明确拒绝）和 EmailDeliveryUnknown（DATA 后结果不明）区分故障，不向调用方传播含 AUTH/密码的原始异常。
- `media/selection_sheet.py: prepare_email_media(batch, *, config, paths, logger) -> dict`，返回持久原图/邮件副本/对照图身份和来源。

入口自行持 RunLock，或消费同运行已有锁；所有请求、意图和文件提交前重新核验 owner。调用方提供的锁仍归调用方；公开 CLI 的 with 块在等待返回前释放。只运行有限期限的 ffmpeg 和 SMTP，不启动 Ollama/TTS/Comfy；本阶段没有可遗留的模型服务。

### 消费计划与候选、建立批次

读取 JIM-02 三个产物：要求 commit 存在、精确字段/schema/run/source/units/timeline/settings 匹配，按 `canonical_digest` 核对两个 JSON 的 SHA256，再用带冻结 run/source 身份的 units 调用 `validate_scene_plan`。不能仅凭文件存在或传入对象准入；不得把 schema=2 放进旧 StoryboardSlot 校验。CLI 从 `production/units.json` 和 `production/timeline.json` 的已校验 payload 恢复参数；缺少准备输入时明确 blocked，不隐式发起规划/配音/出图。

`batch_index` 是 `plan.batches` 的从 1 起整数，ID 为 `image_batch_0001`。候选 scene 覆盖必须精确等于该批；依赖的较早 scene 必须已有接受记录且原图 SHA256 仍匹配。JIM-01 每个候选的 `candidate_id/request_id/task_id/req_key/path/bytes/sha256/width/height/format` 原样保留，ID 只在 scene 内唯一。核对该 scene 的 `candidates.json`、request/result、下载收据与原图真实身份，不仅信任传入列表；不得重新调用 generate_candidates 来做只读核验。基准批次可以独立文生图；后续批次在本任务用相同真实记录结构的测试素材模拟，参考模型准入在 JIM-04 扩展，不能声称已经引用基准生成。

`production/image-selection/<batch_id>/batch.json` 精确字段为 `schema_version/production_strategy/run_id/batch_id/batch_index/source_sha256/units_sha256/timeline_sha256/scene_plan_sha256/visual_bible_sha256/baseline_bindings/scenes/delivery`。schema=2、strategy=paragraph_jimeng_v1。`delivery` 为固定 `sender/recipient/max_mime_bytes`。scene 行精确字段为 `scene_id/summary/unit_ids/text_start/text_end/original_text/reference_bindings/candidate_manifest/candidates`；manifest 身份为 `path/bytes/sha256`，候选行为上述 JIM-01 精确行。`original_text` 必须为 frozen.script.text 的 scene 字符包络，summary 单独显示。

`baseline_bindings` 是当前批依赖已选基准的 `kind/id/scene_id/candidate_id/sha256` 列表，按 bible.baselines 顺序；当前批尚待选择的基准不伪造 candidate 或 SHA，原计划关系仍由 bible.baselines 提供。同一基准图多用途全部保留。manifest 全部数字严格拒绝 bool。候选/计划/地址或已接受基准变化时拒绝覆盖；显式重选/返工留给新修订运行。

`scene_manifest_sha256` 在选择文件中表示 batch.json 的规范 JSON SHA256；新记录统一使用 sort_keys、紧凑分隔符、ensure_ascii=False、allow_nan=False。原始媒体、MIME 和用户文件使用原始字节 SHA256，不能混用。

### 邮件内容、对照图及大小

邮件纯文本和 HTML 均包含 run/batch、页码、scene 摘要、完整对应原文、基准用途、候选编号和整组一致性要求。编号直接使用 `scene_0001=request_01_image_01` 这种真实 scene/candidate 组合，可复制；每候选还提供包含原图 SHA256 的可复制 JSON 选择行，用户选择编号后复制对应行，无须手打哈希。HTML 内容转义，不嵌入远程 URL。选图骨架附在批次目录并在正文说明其路径与编辑方法。

每个候选有实际附件；内嵌预览和对照图是从持久原图生成的本地副本。使用既有 ffmpeg 完整解码、等比 contain，生成 JPEG 邮件副本（默认 960x540、q:v=3）；两列 480x270 单元格对照图，带安全 ASCII scene/candidate 标签，固定字体路径，动态文本经独立 textfile 输入。每页最多 8 个候选，含本批候选及直接引用的已选基准，超过即另起对照页；页码/清单串起整组，不丢用途或候选。使用源码可维护的 ffmpeg 代码，不新增 Pillow 等依赖。

媒体保存为 `mail/media.json`，精确字段 `schema_version/run_id/batch_id/scene_manifest_sha256/images/contact_sheets`。images 行为 `kind/scene_id/candidate_id/source_sha256/path/bytes/sha256/width/height`，kind 为 original/preview；contact_sheets 行为 `path/bytes/sha256/width/height/sources`，sources 行为 scene_id/candidate_id/sha256。基准先于本批候选，均按 scene/candidate 稳定排序，重复同图不重复单元格而保留用途。原图不修改。默认附件使用原图；若单张原图使整封 MIME 超限，改附有原图 SHA 来源说明的邮件副本，必要时按 960x540、640x360、320x180、160x90 依次缩小。最小副本和必要正文仍超限时停止并保留素材，不漏图发送。

使用 EmailMessage + policy.SMTP，Date 冻结在通知创建时，Message-ID 为 `<run_id.batch_id.part_0001.attempt_0001@video-ai.local>`，MIME boundary/CID 按该身份确定。按完整 `.as_bytes()` 字节装包，包含 Subject/正文/全部 MIME headers、base64 开销、对照图及附件；不能按原文件大小估算。贪心按 scene/candidate 顺序分页，最终 total 页数稳定后重编码并重新核验每封限额，必要时再次拆分直至稳定。每个候选恰好有一份附件归属，基准可为对照重复展示。

### 发送意图、回执与恢复

先持久化媒体及全部完整 `.eml`，再提交 `notification.json`：精确字段 `schema_version/run_id/batch_id/scene_manifest_sha256/created_at/parts`；part 行为 `part/total/message_id/path/bytes/sha256/attachments`，attachments 行为 `scene_id/candidate_id/original_sha256/attachment_sha256`。SHA 和附件归属复核后才连接 SMTP。

逐 part 的目录 `mail/part_0001/attempt_0001/` 保存完整 message.eml、intent 和 receipt。SMTP_SSL 使用默认验证证书的 SSL context；密码缺失、连接、认证或 RCPT 明确拒绝发生在发送意图之前，普通续作可在修复设置/环境后继续，失败只生成独立安全日志，不冻结未发送的错误传输设置。完成 MAIL/RCPT 后、调用 DATA 之前由 `before_data` 持锁写 intent：`schema_version/run_id/batch_id/part/attempt/message_id/mime_sha256/transport/created_at`；transport 为当时完整有效非秘密设置。intent 不含密码、SMTP AUTH 字节或异常原始文本。

成功 DATA 2xx 后立即保存 receipt，字段为 intent 的身份字段加 `accepted_at/smtp_code`；不保存可能回显凭证的服务端自由文本。有 receipt 的 part 永不重复发送。intent 无成功/明确拒绝结果时返回 `email_delivery_unknown`，无论是进程中断还是响应丢失，普通续作都不再 DATA。明确 DATA 拒绝保存 `rejected.json`，不当作成功。SMTP 接受不表示邮箱实际收信。

提供显式 Python 操作 `retry_notification(frozen, batch_id, part, *, expected_attempt_sha256, email_settings=None, paths, logger, smtp_factory=None, lock=None)`：核对指定失败/未知 intent 的原始字节摘要，保留历史，创建下一 attempt 和新 Message-ID；调用该函数才授权再次发送，普通 CLI 续作不调用它。不增加自动重发策略。重发保持原 part/total、正文、地址和附件归属，重新编码该页的 Message-ID/Date，保存到新 attempt/message.eml 并重新核验限额；新的 MIME 摘要只属于新尝试，不覆盖原 notification 或其他页。

每次发送有 timeout_seconds 的总期限；若复用工作线程界定 OS DNS 阻塞，迟到线程在 MAIL/DATA 前检查总期限和锁，截止后不产生新 DATA，所有持久提交由持锁主线程执行。DATA 已发但主线程超时即 unknown，不等待无限网络调用，不写虚假成功；最终关闭本次 SMTP 连接。日志只记阶段、批次/页码、失败类别及安全代码。

### 选择、观察与不可变接受

导出的选择骨架精确字段：`schema_version/run_id/batch_id/scene_manifest_sha256/scene_plan_sha256/visual_bible_sha256/baseline_bindings/intent/selections/observation`。首次 intent=draft、selections=[]，身份/基准字段完整预填；用户复制所选候选 JSON 行到 selections，提交接受时改 intent=accept。selections 行精确为 `scene_id/candidate_id/sha256`，均为非空字符串且 SHA256 是小写 64 位十六进制；不接受空值占位的选择行。observation 默认为 null，不预填 passed、审核人或理由。

用户文件先稳定读取（前后文件身份不变），原样复制到 `submissions/<raw_sha256>.json`；后续以副本为证据，不能把用户可编辑文件本身当永久接受记录。所有外键/摘要必须匹配本批；重复 scene、重复行、跨批/run/候选、图片变化或伪造基准均拒绝。draft 可缺 scene，保存后返回 awaiting_image_selection，不产接受记录。accept 缺 scene 明确拒绝；当前批全部邮件均有有效回执、每 scene 恰好一张、原图 SHA256/尺寸重新核验后，按 scene 顺序写 `accepted.json`。已有未知发送状态优先返回 email_delivery_unknown，不能用选择文件隐式解决不明投递。

accepted 精确字段：`schema_version/production_strategy/run_id/batch_id/scene_manifest_sha256/scene_plan_sha256/visual_bible_sha256/selections/baseline_bindings/source_submission_sha256`。selections 是上述选择行加 `path/bytes/req_key/request_id/task_id`；baseline_bindings 包含既有已选基准及本批新接受基准的全部 kind/id 用途。choices 一旦接受不能更换，重入只能同一选择集合；新的观察文件可以附带相同选择，保留首个接受来源，不重写旧 accepted。

observation 精确字段为 `scope/review_method/reviewer/viewed_images/subject_consistency/style_consistency/verdict/issues/reason`。scope 为 current_batch/all_selected_images，method 为 human_image/agent_image，reviewer/reason 非空；viewed_images 行为 `scene_id/candidate_id/sha256`，必须无重复且精确覆盖所宣称 scope 的选择。subject_consistency/style_consistency/verdict 值为 passed/failed/unverified；issues 是非空字符串数组（允许空数组），passed 必须两项均 passed 且 issues=[]；failed 必须有具体 issues。程序只核验用户/有实际看图能力审查者提供的记录，不自动观察或补写结论。

基准批次接受不要求尚未生成的后续画面已观察；可产 current_batch 观察但不代表整组准入。最后全部 scene 已接受后，仍需 scope=all_selected_images、确切全组选图身份及 passed 实际观察，才写 `production/image-selection/complete-acceptance.json`。精确字段 `schema_version/production_strategy/run_id/scene_plan_sha256/visual_bible_sha256/accepted_batches/selections/baseline_bindings/observation/observation_submission_sha256`；accepted_batches 是 batch_id/accepted_sha256 行。失败/未核实观察保留在提交副本，不写 complete receipt。

`require_complete_image_acceptance` 重新核对 commit、每批 accepted、所有原图和观察，任何缺项/变化拒绝，返回上述完整记录；本任务任何路径都不请求 Wan。JIM-04 将消费这些选择/基准接口并增加实际参考生成来源，JIM-05 才实现视频请求。

### 结果、CLI 和事务

新增独立 `ImageSelectionResult`，schema_version=2，精确输出字段 `schema_version/production_strategy/run_id/run_dir/status/active_stage/batch_id/selection_template/all_images_accepted/log_dir/error`。active_stage 固定 start_images；status 为 awaiting_image_selection/email_delivery_unknown/image_batch_accepted/blocked/failed/interrupted。all_images_accepted 仅由有效 complete receipt 导出；单批接受不能伪装交付。还有未来批次时接受当前批返回 image_batch_accepted/all_images_accepted=false，供 JIM-04 调用下一批；全部选择已齐但全组观察缺失/失败时返回 awaiting_image_selection；有效完整准入时返回 image_batch_accepted/true。等待/unknown 退出码 3，批次接受 0，blocked 2、failed 1、interrupted 130。error 为 null 或既有 kind/message/evidence_paths 脱敏结构。selection_template 为当前批 `selection-template.json` 的绝对运行内路径。没有 movie/subtitle/receipt_path 等正式交付字段。

对于未准备批次等早期拒绝，batch_id/selection_template 可以为 null，all_images_accepted=false；run_id/run_dir/log_dir 只取实际已验证的运行身份。正常等待/批次接受必须有实际批次及选择骨架；error 仅在 blocked/failed/interrupted 或 unknown 时包含原因，不能伪造成功。

`make-video --run-dir RUN --image-selection PATH` 仅在新策略已准备批次上消费文件；禁止与新输入或旧策略组合。普通 `--run-dir` 在存在已登记批次时恢复该通知/等待状态；没有批次仍保留现有全流程未实现保护。为新分支先取得 RunLock、重读冻结输入，再执行选择续作；返回 schema=2 结果和日志，不修改旧 ProductionStateStore 的 schema=1 状态集合或把等待写为模型失败。不实现从新文案到图片的完整协调器。

写入顺序：校验计划/候选 → batch/选择骨架/活动指针 → 媒体/MIME → notification → 发送 intent/receipt → 选择提交副本 → accepted → 最后可选 complete receipt。所有 JSON/媒体用同目录临时文件、fsync、原子改名；不可变文件一致才复用，冲突停止，最后标志先核验全部后备。`production/image-selection/active-batch.json` 精确为 schema_version/run_id/batch_id/batch_sha256，指向已完成 batch 的活动入口。活动指针是唯一可原子替换的记录：先保存同内容的不可变 `active-batch-0001.json` 历史，只有前批已接受、旧指针身份匹配才推进到下一批；禁止回退和跳批，同一批内容不能换。等待、异常或中断时释放公开入口自有锁和连接；已经接受的基准不丢失。

## Files

- 新增 `src/video_ai/selection_config.py`：纯邮件设置；在 config.py 仅新策略允许并校验 raw 字段。
- 新增 `src/video_ai/adapters/selection_email.py`：MIME 构建、SSL SMTP、总期限及 before_data 回调。
- 新增 `src/video_ai/media/selection_sheet.py`：可追踪邮件副本/对照图，不修改原图。
- 新增 `src/video_ai/runtime/image_selection_records.py`：schema=2 批次/选择/观察/完整准入的纯与只读验证。
- 新增 `src/video_ai/runtime/production_image_selection.py`：持锁准备、通知、选择、显式重发、等待恢复及独立结果。
- 修改 `src/video_ai/cli.py`、`src/video_ai/production.py`：准备运行的选择分派，保持旧路径与全流程保护。
- 修改 `config/jimeng.example.json`、`docs/jimeng-candidates.md`：已实现配置、选择骨架和安全续作操作；不写入授权码。
- 新增 `tests/unit/test_selection_email.py`、`tests/unit/test_image_selection_records.py`、`tests/integration/test_image_selection_flow.py`。

## Tests

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-03-tests'
& $VideoAiPython -B -m pytest tests/unit/test_selection_email.py tests/unit/test_image_selection_records.py tests/integration/test_image_selection_flow.py -q
& $VideoAiPython -B -m pytest tests/unit/test_jimeng_inputs.py tests/integration/test_jimeng_candidates.py tests/integration/test_scene_planning.py tests/unit/test_model_visual_prompts.py tests/unit/test_production_review.py tests/integration/test_make_video_cli.py tests/integration/test_make_video_recovery_contract.py -q
& $VideoAiPython -B -m pytest -q --tb=short
```

以上 JIM-03 新测试尚未创建或运行，预期全部通过，覆盖：

1. 本机 SMTP 替身接收实际 DATA，邮件解析后正文有真实编号、完整原文、基准用途和一致性说明；PNG/JPEG 附件可完整解码，副本可追踪到未修改原图，对照页有全部候选/基准用途。测试注入明文 localhost transport 替身，生产配置仍只允许 SSL。
2. 使用多张压缩后仍大的真实图片，核验每封完整 MIME <=15 MiB、所有候选附件恰好覆盖、拆页 total/Message-ID/CID 稳定；单图超限仅改邮件副本，最小副本不能容纳时零 DATA。
3. 在 intent 前、DATA 已发回执前、部分页成功后中断，验证无重复成功页发送，unknown 零自动重发；显式 retry 核对原尝试摘要且保留旧记录/新 Message-ID。缺凭证/认证失败修复后只发邮件，出图提交次数为零。
4. 同批完整选择接受，部分 draft 仅保存；accept 缺项、重复、跨 run/批次、未知候选、原图/计划/基准变化全部拒绝；同一候选 ID 在不同 scene 正确隔离。接受后输入文件修改不改历史副本，原图变化使完整准入失效。
5. 用真实 JIM-02 三 scene 依赖计划准备基准和模拟后续候选，基准接受可以驱动后续 API 批次；后续通知展示确切已接受基准。仅选编号、current_batch 观察、failed/unverified 或遗漏全组 viewed_images 均不能生成 complete receipt，任何步骤 Wan 提交为零。
6. 本次自有锁/SMTP 连接在等待/异常后释放；外部提供锁由调用方释放；失锁后无 DATA/接受提交。迟到 DNS/连接在期限后不能发 DATA，已发 DATA 的超时归 unknown。手改 MIME/摘要、双文件提交中断等只复用可核验历史，不覆盖。
7. prepared-run CLI 的 --image-selection 确实读入该文件，JSON 为独立 schema=2 等待/接受结果，等待返回码 3；旧 CLI/schema=1 审核/结果字段集合保持，未准备的新策略仍 blocked；不启动任何模型服务。

## Acceptance

任务板五项分别由 Tests 1/2、3、4、5、6/7 证明，并在真实本地运行目录保存可重入 batch/notification/accepted 记录。完整准入 receipt 必须消费真实用户文件内容及当前原图身份；程序不能因技术检查或候选发送成功而自动批准一致性。新增专项、历史回归及全套均运行通过后才记录任务完成。准备后继 JIM-04 时直接传递上述基准/批次接口，不把模拟参考生成说成已经实现。

## Risks

真实 QQ SMTP 启用、授权码和收件箱投递尚未验证，普通测试不得发真实邮件；SMTP 2xx 只证明服务器接受。MIME 限额不能保证 QQ 的所有实际服务限制，真实联调留到 JIM-08。视觉一致性仍依赖真实看图；人类输入的观察必须如实提供，哈希不能代替观察。DATA 结果不明时显式重发可能重复邮件，默认必须停住。参考图生成和新文案全流程协调仍分别由 JIM-04/JIM-07 完成；本任务使用准备运行及后续批次替身验收。
