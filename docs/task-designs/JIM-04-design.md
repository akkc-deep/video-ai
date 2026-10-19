# JIM-04 参考图存储与关联画面一致性生成

## Goal

把 JIM-03 已接受的固定基准原图实际送入后续即梦参考生成请求，并在选图及全组观察通过后给出可核验的 Wan 起始图清单。请求中的每张参考图必须能追溯到主体/外观/背景用途，不能把独立文生图冒充参考生成。

## Scope

包括现有私有 TOS 桶的内容寻址上传、HTTPS GET 预签名、明确的模型能力配置、参考输入及共享设定绑定、关联场景的单次提交恢复、复用邮件/选择及完整图片准入。继续使用 schema=2、paragraph_jimeng_v1，不改历史 schema=1。

本任务以已准备的 units/timeline/scene commit 和已选基准为入口，不实现新文案全流程、Wan 请求、尾帧续接、动态观察或正式交付。测试只使用本地/注入替身；不创建桶、不改权限、不发真实邮件/上传/收费生成。真实账号、参考图取图和视觉质量由 JIM-08 观察。

## Approach

### 模型与存储配置

新策略 raw 允许 `reference_generation`、`reference_capabilities`、`reference_storage`，均不新增改变旧 ProjectConfig resolved 形状的字段。parser 放在 `src/video_ai/reference_config.py`；freeze/load 保留原始配置并冻结能力文件的原始字节 SHA256。旧 schema=1 不补配置；凭证值仍只在进程环境读取。

JIM-03 已冻结的运行可能没有上述配置，必须能保留其基准后补配置。为此 produce_reference_batch 提供显式 `reference_settings_path=None`：文件精确为这三个根字段，不含凭证值；只能补冻结 raw 中原本为 null/缺失的字段，不能覆盖其已有值或改 image_generation。首次完整有效配置在任何云请求前持锁复制配置源及能力档案，写 `production/reference-images/settings.json`，精确字段 `schema_version/run_id/frozen_options_sha256/config_source_sha256/model_settings/capability/capability_sha256/storage`。config_source_sha256 是原始用户文件摘要，未使用文件为 null；capability 为完整档案、storage 为有效设置。该标志存在后所有恢复使用它，重新提供不同配置拒绝；仅环境中 AK/SK 值可轮换。不修改 JIM-03 原冻结文件、已选基准或原请求。缺配置时尚不写此标志，用户可补齐后续作。

`reference_generation` 为 null 或一份与 `image_generation` 相同字段的独立模型配置（复用其 parser 和预设规则），必须显式给出 req_key。没有它时只考虑用户已选的 image_generation，不按相似名称猜模型。

`reference_capabilities` 是 req_key 到绝对本地 JSON 档案路径的映射，路径文件在 freeze 时复制到 `production/reference-capabilities/<req_key>.json`；req_key 必须是 `[A-Za-z0-9_-]{1,100}`。档案精确字段：

`schema_version/req_key/input_field/max_images/max_image_bytes/min_width/min_height/max_width/max_height/formats/max_prompt_bytes/evidence`。

schema=1，input_field 只接受 `image_urls`；所有数量/尺寸为正整数且拒绝 bool，最小值不大于最大值；formats 是非空无重复的 `png/jpeg/webp` 子集。evidence 精确为 `source_url/source_sha256/verified_by/verified_at`：source_url 必须是无认证信息/fragment 的官方 HTTPS 文档，host 为 docs.volcengine.com 或 www.volcengine.com；对应材料原始字节的小写 SHA256、非空核对者、带时区时间。该档案是明确提供的已核对能力输入，不由模型名称或程序自行补写。没有档案、未提供核对证据或 req_key 不符均为能力不明；不内置未经本项目核对的模型数量/尺寸限制。测试档案中的限额是替身输入，不能宣传为真实服务限额。

模型选择算法固定为：image_generation 有匹配有效参考档案则复用；否则仅在用户显式 reference_generation 及其匹配档案同时存在时使用后者；再否则返回 `awaiting_image_model_configuration`，零关联图提交。更换参考模型或档案需新运行，不覆盖已有接受/生成历史。

`reference_storage` 精确字段为 `provider/bucket/region/endpoint/access_key_env/secret_key_env/key_prefix/url_ttl_seconds/download_margin_seconds/clock_skew_seconds/request_timeout_seconds`。provider=volcengine_tos；bucket/region/endpoint/两项凭证环境变量名必填；bucket 3..63 位小写字母数字连字符且首尾为字母数字；endpoint 为无路径/查询/认证信息的 `https://tos-<region>.volces.com`。key_prefix 默认 `video-ai-references`（安全 ASCII 路径、无空段和点段）；其余默认 3600/120/60/60 秒，均有限正数，前三项为整数；TTL 在 1..604800，作为本程序保守上限。缺项/无效项返回配置等待，不访问云服务。

预签名 TTL 必须至少为所选参考模型 `task_timeout_seconds + download_margin_seconds + clock_skew_seconds`；每次实际提交前，剩余期限仍须覆盖这段预算。超出上限、数量、格式、字节或尺寸限制都在任何关联付费提交前拒绝。AK/SK 读取失败是本地前置条件，不创建生成 intent。TOS 与图片凭证可独立轮换；桶/模型/原图身份不能轮换。

### 公共接口与结果

- `adapters/reference_storage.py: ReferenceStorage(settings, *, http=None, clock=None, ownership_check=None)`。
- `ensure_original(original, *, run_id, before_put) -> dict`：original 是已校验的 `path/bytes/sha256/width/height/format`；返回 `bucket/region/endpoint/key/bytes/sha256/content_type/etag`，etag 为服务端实体标记字符串，不作为 SHA256 使用。before_put 由持锁调用线程保存上传意图；ownership_check 只读，网络线程在请求前/期限后复核。
- 同类 `presign_get(object_record, *, expires_seconds) -> dict` 返回仅在内存流转的 `url/issued_at/expires_at`；不上传、不写日志。
- `runtime/production_reference_images.py: produce_reference_batch(frozen, units, timeline, *, batch_index, paths, logger, reference_settings_path=None, storage=None, client_factory=None, smtp_factory=None, email_settings=None, lock=None) -> ReferencePreparationResult`。
- `runtime/reference_image_records.py: require_reference_image_acceptance(frozen, units, timeline) -> dict`：重验 JIM-03 complete receipt 与每个关联 scene 的实际参考来源，返回 `production/reference-images/wan-inputs.json` 的已验内容，不请求 Wan。
- `runtime/jimeng_reference_candidates.py: generate_reference_candidates(frozen, scene, bible, references, *, settings, capability, client, paths, logger, lock) -> dict`，返回与 JIM-01 相同候选清单形状，差别由下面的来源记录承担。

ReferencePreparationResult 精确字段为 `schema_version/production_strategy/run_id/run_dir/status/active_stage/batch_id/selection_result/wan_inputs/log_dir/error`；schema=2、stage=start_images；status 为 `awaiting_image_model_configuration/awaiting_image_selection/email_delivery_unknown/image_batch_accepted/images_ready/blocked/failed/interrupted`。等待码3、批次接受/images_ready码0、blocked2、failed1、interrupted130。selection_result 为 null 或真实 JIM-03 ImageSelectionResult 的完整字典；wan_inputs 仅 images_ready 时为已核验清单绝对路径；无正式成片字段。未验证的 run 不填虚构路径。

入口自动持 RunLock，传 lock 时只消费本运行现有锁并由调用方释放。所有磁盘提交在持锁调用线程；后台网络只读检查 ownership。与 JIM-03 一样，错误收尾/退出锁失败也返回本阶段独立结果，不能落入 schema=1 错误写入路径。此阶段不启动模型服务。

### 固定参考绑定与共享提示词

先调用 JIM-03 `load_committed_plan` 及 `load_accepted_batches`，读取 plan.batches[batch_index-1]。本入口针对带 reference_bindings 的关联批次；基准无依赖的首批仍由既有候选与 prepare_image_batch 准备。批次索引不得跳跃，全部直接依赖必须有经过重新核验的 accepted 和原图。

按 bible.baselines 的顺序收集当前 scene.reference_bindings 声明的精确 kind/id，用源 scene 的不可变已选原图。相同 `(scene_id,candidate_id,sha256)` 只占一个模型图片位置，所有 uses 都保留；不自动增加相邻图，也不漏掉主体/背景。任何基准未选或来源不匹配时零生成提交。

逻辑 reference 行精确字段：`scene_id/candidate_id/sha256/bytes/width/height/format/uses/object`，uses 是 kind/id 行数组，object 是上述存储回执。URL 顺序与该数组一致。每个主体跨景直接读取同一固定基准，不沿上一张候选累积外观误差。

请求提示词固定为 `scene.image_prompt + '\nVISUAL_BIBLE_JSON\n' + canonical_json(context)`，context 精确含 `global_style/entities/appearance_variants/scene_groups`，只取当前 scene 引用的稳定 ID 行并保持 bible 原顺序；没有引用的数组为空。不给原文事实新增断言，不改 plan/bible。以最终 UTF-8 长度按 capability.max_prompt_bytes 准入，禁止截断。

请求体沿 JIM-01 通用异步协议，实际 submit body 为所选模型参数加受控 req_key、上述 prompt、`image_urls=[...live_urls]`。model_parameters 继续拒绝自行写入 prompt/req_key/image_urls。只扩展 JimengClient 的显式受控 reference 参数，不让参数透传绕过能力验证；有参考时 query/download 仍查询原 task_id。

### TOS 协议与恢复

使用 Python 3.12 标准库和既有外部 HTTPS 边界，不引入 SDK 运行依赖。TOS 签名按官方 Python SDK `tos/auth.py` 的 TOS4-HMAC-SHA256：作用域 `YYYYMMDD/region/tos/request`，派生键依次 date/region/tos/request；规范请求为 method、编码 path、排序编码 query、规范 headers、signed header names、payload SHA256（GET/HEAD 可用 UNSIGNED-PAYLOAD）。上传以 host/content-type/x-tos-* 签名，GET URL 使用 X-Tos-Algorithm/Credential/Date/Expires/SignedHeaders/Signature。测试固定 UTC、AK/SK 与规范请求字节，和官方算法独立计算的向量一致。

仅扩展 ExternalHttpsClient 允许 PUT/HEAD，并仍禁止重定向、代理转发秘密、自动请求重放及原始 URL 日志；HEAD 为空 body，GET/PUT 校验总期限及受控返回字节数。现有 GET/POST 行为不变。上传/HEAD/GET 均用 `{bucket}.tos-<region>.volces.com`，对象 key 为 `<key_prefix>/<run_id>/<sha256>.original`；所有路径片段只含安全 ASCII。

上传设置 Content-Type 与 x-tos-meta-sha256；PUT 前保存 `production/reference-storage/<sha256>/intent.json`，精确字段为 `schema_version/run_id/object/source/created_at`，schema=2，object 为 `bucket/region/endpoint/key/bytes/sha256/content_type`，source 为 `path/bytes/sha256`，不含授权头或签名 URL。先检查对象：404 才 PUT；已有对象需 GET 实际字节核 SHA256/bytes 并核 metadata，一致才可复用，冲突不能覆盖。PUT 成功后 HEAD+GET 校验再保存 object.json，精确字段为 `schema_version/run_id/intent_sha256/object/verified_at`，object 为公开 API 返回的完整对象行（含 etag）；已有远端对象也写本地逻辑 intent 后再补验证回执，不虚构 PUT 已执行。仅 ETag 相等不够。后台发现需上传时向持锁调用线程回传 ready，before_put 在该线程写入，确认后网络线程才可 PUT；沿用 SMTP 的同步取消/发送状态规则。

PUT 结果不明时不产生图片生成请求；普通续作先 HEAD+GET 验证原 key。对象存在且身份一致则补回执；404 可对同一内容寻址 key 再 PUT（幂等上传，不是图片重新出图）；其他响应停止，不创建桶或调整 ACL。对象保留，不在选图等待时删除。

预签名 URL 仅在待提交时生成，普通记录只保存对象身份、issued/expires 时间和 URL 原始字节 SHA256。所有错误、diagnostic 和普通 HTTP 日志不能含 URL 查询参数、AK/SK、Authorization 或图片二进制。TOS 是否私有及真实取图能力留到 JIM-08；程序不调用权限变更 API。

### 候选记录与单次提交

每 scene 的 `production/jimeng/<scene_id>/candidates.json` 继续为原 schema=2 清单，原图行不改变。参考生成另外保存 `production/reference-images/<scene_id>/provenance.json`，精确字段 `schema_version/production_strategy/run_id/scene_id/scene_plan_sha256/visual_bible_sha256/model_settings/capability_sha256/prompt_sha256/references/requests`。references 为上述不含 URL 的逻辑参考行；requests 为本地 request_id/logical_request_sha256 行。

每 request 的逻辑 request.json 精确为 `schema_version/run_id/scene_id/request_id/prompt/image_generation/reference_inputs`，reference_inputs 为完整 references；不保存临时 URL。request_id 仍为 request_01 等；下载/result/candidate 命名及 SHA256 收据复用 JIM-01 规则。intent 另绑定实际 submit body 的 SHA256、按顺序 URL SHA256 和有效期，logical identity 不含临时 URL。

参考 request 的 intent 精确字段为 `schema_version/run_id/scene_id/request_id/logical_request_sha256/submit_body_sha256/reference_urls/created_at`，reference_urls 按 references 顺序，行为 `sha256/issued_at/expires_at`。accepted/result/下载收据及原图候选 metadata 继续使用 JIM-01 精确结构，identity 为逻辑 request 的规范摘要；新只读分派核对这个参考 intent，而非套用纯文生图的 intent 字段。

提交前再次持锁核验原图/对象/能力/剩余 TTL，先写意图再发送；没有 intent 时可以重新签发 URL。已有 intent 无 task_id 返回 submit_unknown，不自动重新提交；已有 task_id 只查询原任务，已完成候选只读验证并恢复必要下载，不刷新 URL 重交任务。单请求失败不补发另一模型。每请求返回的全部候选仍保留，失败/过期不会自动重生成。

扩展 JIM-03 候选只读核验器：有 reference_inputs 的 request 必须用新 provenance 校验器重验完整参考配置/基准/对象/原图；没有该字段时继续原 JIM-01 校验，保证 JIM-03 模拟后续批次及旧记录保持可读。`require_reference_image_acceptance` 对计划中有 reference_bindings 的每个 scene 强制要求真实参考 provenance，所以单靠旧纯文字模拟记录无法获得 JIM-04 Wan 输入准入。

### 邮件、完整准入和 Wan 输入

本批候选全部持久校验后直接调用 JIM-03 prepare_image_batch；通知失败/等待只恢复通知，不调用生成 submit。基准与后续已接受选择保持不可变，unknown 邮件仍需要指定原 intent 摘要的显式重发。

全部 scene 有选择并提供 all_selected_images passed 实际观察后，读取 JIM-03 require_complete_image_acceptance，再重验每个关联 scene 的 provenance、所选 candidate 及参考对象。最后写 `production/reference-images/wan-inputs.json`。精确字段 `schema_version/production_strategy/run_id/scene_plan_sha256/visual_bible_sha256/complete_acceptance_sha256/scenes`；scenes 按 plan 顺序，行精确为 `scene_id/unit_ids/path/bytes/sha256/candidate_id/req_key/request_id/task_id/baseline_bindings/reference_provenance_sha256`。无依赖基准的 provenance_sha256 为 null，有依赖必须为有效 provenance 规范摘要；baseline_bindings 为当前 scene 实际需要的完整 kind/id/scene/candidate/SHA 行。

该清单只标识 Wan 首图，不生成 clips、不声称视频观察通过。require_reference_image_acceptance 每次从原 commit、接受、原图和来源重建清单并比较；任何变化均拒绝。候选原图变化使 JIM-03 complete 和本清单同时失效。

所有 JSON 使用规范摘要、原始媒体使用字节摘要。同目录临时文件 fsync 后原子改名；已有记录一致才复用，冲突不覆盖，provenance 在关联候选批次可通知前完整，wan-inputs 在完整验证后最后提交。中断时重建缺失标志，不修改已接受基准。普通 make-video 继续已有准备运行分派；新文案完整协调器仍未实现。

## Files

- 新增 `src/video_ai/reference_config.py`：存储/参考模型/能力档案纯 parser 和选择规则；修改 config.py/production_inputs.py 冻结 raw 和档案身份，保持旧 resolved 字段。
- 新增 `src/video_ai/adapters/reference_storage.py`；修改 external_https.py 的受控 PUT/HEAD 与只读所有权检查，保持有限总期限/无自动重放。
- 修改 `src/video_ai/adapters/jimeng.py`，增加显式受控 reference 参数；保留纯文生图已有签名/协议。
- 新增 `src/video_ai/runtime/jimeng_reference_candidates.py`、`reference_image_records.py`、`production_reference_images.py`，分别负责生成事务、只读 provenance/Wan 输入、持锁批次协调。
- 修改 `src/video_ai/runtime/image_selection_records.py` 仅增加参考候选分派，保留原 JIM-03 清单、选择、观察、SMTP 行为。
- 修改 `config/jimeng.example.json`、`docs/jimeng-candidates.md`，说明需要本地已核对能力档案及既存桶，不能填虚构桶/凭证或宣称配置即可证明质量。
- 新增 `tests/unit/test_reference_config.py`、`test_reference_storage.py`、`test_reference_image_records.py`、`tests/integration/test_jimeng_reference_flow.py`。

## Tests

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-04-tests'
& $VideoAiPython -B -m pytest tests/unit/test_reference_config.py tests/unit/test_reference_storage.py tests/unit/test_reference_image_records.py tests/integration/test_jimeng_reference_flow.py -q
& $VideoAiPython -B -m pytest tests/unit/test_selection_email.py tests/unit/test_selection_sheet.py tests/unit/test_image_selection_records.py tests/integration/test_image_selection_flow.py tests/integration/test_jimeng_candidates.py tests/integration/test_scene_planning.py tests/unit/test_jimeng_inputs.py -q
& $VideoAiPython -B -m pytest -q --tb=short
```

新测试尚未创建/运行，预期全部通过。完整测试用串行命令，避免 JIM-03 所记录的全局 runs/GDI 字体并发干扰。具体用例：

1. 从既有 `tests/image_selection_helpers.py` 建三 scene、两批真实 PNG/commit/基准接受；准备 fixture 参考模型档案 max_images=1、有效原图尺寸、明确多用途。替身记录实际 submit body，断言 image_urls 精确为所选固定基准，主体/背景共用同图但 uses 保留，两个关联 scene 直接引用同一基准；共享 context 和原文不变。
2. 未选基准、未知/缺能力、未核对档案、显式参考模型缺项、bool 数字、图片数/尺寸/字节超限、TTL 不足均零付费 submit；不支持不会退回纯文字，不会自动换 req_key。新的参考生成请求与纯文生图请求分别验证。
3. 固定时钟/凭证的 TOS4 header/presign 向量、中文源图及字节 digest；PUT/HEAD/GET 替身验证现有对象复用、缺对象上传、403/404/unknown、metadata 或实际字节不符、GET 重定向拒绝、禁止 create_bucket/ACL。secret/签名 URL 不出现在普通记录/日志。
4. URL 过期且尚未 intent 可重新签发；提交后中断查询原 task，unknown 无 task 则不再次 submit；下载失败只恢复下载，通知错误只恢复邮件。凭证轮换可读原任务，配置/模型/参考基准变化拒绝。
5. 多批邮件复用 JIM-03 真实 MIME/SMTP 替身；仅当前批选择/未核实观察无 wan-inputs；完整全组观察后产出逐 scene 精确原图，原图或 provenance 改变使 require 拒绝。纯文字模拟后续候选即使 JIM-03 接受，也不能过本任务参考来源准入。
6. 自有/外部锁、DNS/上传/图片提交前失锁、每个 intent/receipt/provenance/最终清单边界中断；迟到线程无新请求，退出不遗留自有锁，已有基准/原图不丢失。

## Acceptance

任务板五项分别由上述用例 1、2、3、4、5/6 证明；实际替身请求必须含参考 URL，不能仅断言逻辑 reference 行存在。重建有效 Wan 清单必须同时消费真实选图内容、全组观察和实际生成 provenance。本任务不以替身或哈希宣称真实图像一致性通过。

第一实施动作：在 `tests/unit/test_reference_storage.py` 用 UTC=2026-10-18T00:00:00Z、AK=test-ak、SK=test-sk、region=cn-beijing、bucket=test-bucket、key=`video-ai-references/fixture-run/` 加 64 个 a 加 `.original`、GET TTL=3600 建独立 TOS4 签名向量，运行观察缺适配器失败；随后实现纯签名和受控 HEAD/GET/PUT。JIM-03 已完成，不能再重做邮件/选择协议。

## Risks

本地实际模型能力档案、账号模型权限、TOS 桶和 AK/SK 仍待部署配置；缺配置的等待是已定义结果，不填猜测的真实模型限制。能力档案由明确核对者提供，其材料正确性和真实服务取图仍需 JIM-08 验证。URL 在内存中仍是临时访问凭证，必须避免原始异常/HTTP 日志。PUT 幂等恢复只针对同一内容寻址对象，不代表图片生成可重试。真实 QQ 收信/画面质量尚未验证；基准重选仍需新修订运行。

官方参考来源：总体方案的 Jimeng 4.0/4.6 与 TOS 预签名资料；本轮另只读核对官方 [TOS Python SDK auth.py](https://github.com/volcengine/ve-tos-python-sdk/blob/main/tos/auth.py) 的签名算法及 [README](https://github.com/volcengine/ve-tos-python-sdk/blob/main/README.md) 的对象 API。该核对未进行真实云请求，不推导任何未核对模型能力数值。
