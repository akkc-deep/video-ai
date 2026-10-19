# 即梦候选图片、段落规划与邮件选图（JIM-01 至 JIM-03）

`config/jimeng.example.json` 显式启用 `paragraph_jimeng_v1`。它只保存 AK/SK 的环境变量名；真实值从运行进程环境读取，不能写进 JSON。模型使用智能视觉 AK/SK，不能填方舟 API Key。

JIM-01 提供可恢复的候选图片 Python 接口，JIM-02 增加独立段落画面规划 API，JIM-03 提供准备运行的邮件通知与选图续作。新文案的完整视频协调器仍待后续任务；对尚未准备批次的新策略调用 `make-video` 会在进入历史 SDXL 流程前明确返回 blocked。旧配置默认制作行为保留。

## 配置

`image_generation.req_key` 与 `model_parameters` 一起决定实际请求。默认每画面提交 2 次；每次返回的全部图片均保存，故最终候选数可能大于 2。不发送臆造的通用 `n` 参数。

`width/height` 或显式 `output_width/output_height` 给出预期输出尺寸，必须横向 16:9；原图完整解码后按该尺寸核验，不静默裁切。未知模型必须在配置中明确提供参数及尺寸，只承诺使用同一异步协议。内置切换预设包含 `jimeng_t2i_v30`、`jimeng_t2i_v31`、`jimeng_t2i_v40`，3.x 不携带 4.0 的 `force_single`；账号权限和具体模型限制以服务端响应为准。

新 run 可用 `make-video --image-model REQ_KEY` 选择预设；未知模型通过配置显式定义。已有 run 恢复时只能使用冻结模型；修改模型需新 run。`--image-model` 不覆盖旧 run 的参数。`request_timeout_seconds` 默认 60，`task_timeout_seconds` 默认 600，`poll_interval_seconds` 默认 2，查询退避上限 15 秒。任务等待预算按每次续作计算，预算到期不会自动创建新任务。

## Python 入口

在项目环境中运行下列代码会调用真实账号并可能产生图片费用；自动测试使用 HTTP 替身，无真实费用。

```python
from pathlib import Path
from video_ai.config import load_config
from video_ai.runtime.paths import RuntimePaths, create_run
from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
from video_ai.runtime.jimeng_candidates import generate_candidates

config = load_config(Path('config/jimeng.example.json'))
run = create_run(RuntimePaths.from_config(config))
frozen = freeze_inputs(config, run, text='湖水边，一只白鸟停在石头上。')
result = generate_candidates(frozen, 'scene_0001', '横向构图，湖水边的白鸟，写实摄影')
print(run)
print(result)

# 续作同一个 run、scene 和提示词；不得换成另一个模型。
frozen = load_frozen_inputs(run)
result = generate_candidates(frozen, 'scene_0001', '横向构图，湖水边的白鸟，写实摄影')
```

该入口自行获取/释放 RunLock；已有协调器持锁时传 `lock=held_run_lock`。不能在已有锁内省略该参数再次加锁。运行仍需有效的语音、Wan、超分及媒体工具资源以冻结配置，但不要求 SDXL 文件。

## 磁盘记录和恢复

记录位于 `production/jimeng/<scene_id>/`，最终 `candidates.json` 是 schema=2 清单；每候选包含 `candidate_id/request_id/task_id/req_key/path/bytes/sha256/width/height/format`。`request_id` 是本地稳定请求序号；官方 request_id 保存在 `accepted.json` 与查询诊断中。原始图片保存为 `.original`，格式由实际媒体探测记录，文件扩展名不表示编码。

每请求先写不可变 `request.json` 和 `intent.json`，受理后保存 `accepted.json` 的官方 task_id。查询诊断只保存脱敏响应，不保存 Authorization、凭证、图片二进制或带签名 URL。下载收据中的 SHA256 和 bytes 在原图可复用前持久化，然后保存原图和解码结果。

- 有 task_id：只查原任务。查询失败或下载失败后再次调用相同入口；已核验原图不重复下载。
- 有 intent 但无 task_id：返回 `submit_unknown`，普通续作不再提交。先依据请求时间、场景和服务端记录人工核对；本阶段没有自动补单或手填 task_id 的入口，不要删除意图强行重跑。
- `expired/not_found/failed`：保存明确终态，不自动补图。需要新的尝试时另建 run，保留原运行证据。
- 图片或冻结输入变化、跨 run/scene/prompt/model：明确拒绝复用。
- 下载 URL 到期：续作从原任务重新查询 URL；若服务端已过期，保留已有图片及终态。

OS DNS 调用可能晚于应用期限返回；HTTPS 外层会按总期限返回并释放调用者，晚到连接会在发送 HTTP 前检查过期。未知提交始终不自动重试。

测试命令与逐项证据见任务设计和任务板。替身通过不表示已验证真实账号权限、实际服务取图或画面质量。

## 段落画面规划 API

`scene_planning` 仅用于 `paragraph_jimeng_v1`；默认每段最多 3 幅关键画面，短段可以减少，多句可以共用同一幅画面。默认 `max_clip_seconds=6` 限制未来每次 Wan 请求。设置只从冻结 raw 配置解析，不扩展历史运行的 resolved 字段。

规划需要已经完成的无损 `units` payload 和实际 PCM `ProductionTimeline`。旁白和字幕仍使用原始 source spans，不能把画面摘要作为配音文本。调用独立入口：

```python
from video_ai.runtime.production_scene_plan import produce_scene_plan
from video_ai.runtime.logging import RunLogger

# frozen/units/timeline 来自同一运行的冻结输入、完整分段和实际配音时间轴。
bible, plan = produce_scene_plan(
    frozen, units, timeline,
    paths=RuntimePaths.from_config(frozen.config),
    logger=RunLogger(run, production=True),
)
```

默认入口管理本次自有的 Ollama 服务，使用既有 `qwen3:8b`；可注入绑定同一冻结本机地址和 production logger 的 `OllamaPlanner` 用于测试。已有外部服务会被拒绝，异常或完成时只停止本次自有服务。入口自动持有 RunLock；已有协调器持锁时传 `lock=held_run_lock`，调用后该锁仍由调用方负责。

产物为 `production/visual-bible.json`、`production/scene-plan.json` 及最后提交的 `production/scene-plan-commit.json`。均使用 schema=2、`scene_planning_v1`；下游必须要求有效 commit，核对规范 UTF-8 JSON（sort_keys、紧凑分隔符、ensure_ascii=False、allow_nan=False）SHA256 以及原文、units、timeline、run 和 settings，再运行 `validate_scene_plan`，不能只检查文件存在。

`production/scene-planning/` 保存完整输入身份、有效设置、请求意图、原 HTTP 响应 SHA256/证据以及有效提案。普通续作复用原响应，提交中断后从原提案补齐缺失文件，已有文件不一致时拒绝覆盖。已提交且匹配时零模型请求、不重写规划文件；即使代码默认值后来变化也使用原有效设置。意图存在但原响应缺失或不完整时停止，不重新发起普通请求；已确认完成的格式/分组错误最多修正一次，修正也始终携带全文。截断响应、身份冲突不会授权自动重试。

scene 请求固定 32768 token 上下文、8192 输出预算及 2048 模板余量，用完整 prompt/schema 的 UTF-8 字节数作保守输入上界，超限在请求前明确停止。该检查可能比实际 tokenizer 更严格，长材料也不会被偷偷裁短。实际本机模型启动及硬件容量仍需部署时验证。

共享实体、外观变体与环境组各自绑定最早实际画面的固定基准；scene 记录引用用途、依赖和稳定拓扑批次。服装与场景事实不能提前引用未来剧情。规划结构校验不构成图片或视频一致性验收。长 scene 只增加 clip，不增加图片；6 秒上限下，200 帧画面保留 `[93,92,15]` 帧，分别生成 `[93,93,17]` 帧，续片丢首衔接帧、尾片裁掉多余帧。父片末帧输入与实际观察由后续 JIM-05 实施。

## 邮件通知与选择续作

`selection_email` 仅适用于新策略。默认发件、收件都是 `318575094@qq.com`，通过 `smtp.qq.com:465` 和校验证书的 SSL 连接。密码只从 `VIDEO_AI_SMTP_AUTH_CODE` 环境变量读取；填写 QQ 邮箱 SMTP 授权码，不把授权码写入配置、选择文件或日志。默认每封完整 MIME 上限为 15 MiB，超限自动拆页；原图过大时邮件附有原图 SHA256 来源说明的缩小副本，原图保留。

准备同运行的 units/timeline、已提交 scene 计划和本批候选后，调用：

```python
from video_ai.runtime.production_image_selection import prepare_image_batch

result = prepare_image_batch(
    frozen, units, timeline,
    [run / 'production/jimeng/scene_0001/candidates.json'],
    batch_index=1, paths=RuntimePaths.from_config(frozen.config),
    logger=RunLogger(run, production=True),
)
print(result.to_dict())
```

该操作会实际发送邮件。列表必须精确覆盖 `plan['batches'][batch_index-1]` 并保持场景顺序。先接受基准，再通过下面的参考批次入口生成有关画面。等待返回后释放本次自有 RunLock 和连接；传入 `lock=held_run_lock` 时由调用方释放。没有模型服务需要启动。

邮件含候选编号、可复制 JSON 行、完整原文、基准用途、预览和整组对照图。打开结果中的 `selection_template`，另存为自己的选择文件：保留所有身份及基准字段，复制每个 scene 所选的 JSON 行到 `selections`。`intent="draft"` 可暂存部分选择；完整接受改为 `intent="accept"`，当前批次每个 scene 必须恰好一张。`observation` 可以为 `null`，不会因选了编号而自动通过一致性审核。

```powershell
video-ai make-video --run-dir "D:/VideoSi/projects/video-ai/runs/RUN" --image-selection "D:/VideoSi/selection.json" --json
# 不提供新选择，只恢复已准备批次的通知或等待状态：
video-ai make-video --run-dir "D:/VideoSi/projects/video-ai/runs/RUN" --json
```

将 `RUN` 替换为实际运行名。入口要求持久 `production/units.json`、`timeline.json` 的有效同运行报告及 scene commit；缺少输入时停止，不隐式重新配音、规划或出图。新文案或旧策略不能组合 `--image-selection`。返回独立 schema=2 JSON：`awaiting_image_selection`、`email_delivery_unknown` 退出码 3，`image_batch_accepted` 为 0，`blocked` 为 2，`failed` 为 1，`interrupted` 为 130。单批接受不代表正式视频交付。

`production/image-selection/<batch_id>/` 保存批次、选择骨架、邮件原文 `.eml`、发送意图/回执、按原始字节 SHA256 保存的用户提交副本和不可变 `accepted.json`。只接受当前计划/批次/候选/原图的确切身份。已经接受的选择不能换图；需要重选基准时创建新修订运行，保留历史证据。

全部 scene 选定后仍需实际看图，提供以下观察；`viewed_images` 必须精确覆盖所有批次的全部已选图片（每行 `scene_id/candidate_id/sha256`）：

```json
{
  "scope": "all_selected_images",
  "review_method": "human_image",
  "reviewer": "实际审核者",
  "viewed_images": [],
  "subject_consistency": "unverified",
  "style_consistency": "unverified",
  "verdict": "unverified",
  "issues": [],
  "reason": "填写实际观察依据"
}
```

这是待填写结构，不是通过记录。真实观察通过时两项和 verdict 都填 `passed`、issues 为空；失败填 `failed` 并写具体 issues。将观察放入最后当前批次选择文件的 `observation`，保留原选择后续作。只有完整选择和全组通过观察齐备，才生成 `complete-acceptance.json`；`require_complete_image_acceptance(frozen, units, timeline)` 会重新校验计划、发送回执、提交副本和全部原图。任何本阶段路径都不请求 Wan。

## 邮件故障恢复

凭证缺失、连接/认证或收件人拒绝发生在 DATA 意图之前时，可以修复后普通续作。修复 host/port/密码环境变量名时，显式传入 `email_settings` 的完整或默认补全设置到 `prepare_image_batch`；收发地址、SSL 和 MIME 限额必须保持。邮件修复不会调用出图接口。

已有成功回执的页不会重发；有意图而结果不明时返回 `email_delivery_unknown`，普通续作和选择文件都不能解除它。核对原尝试后，只有显式 Python `retry_notification` 可以再发送该页：

```python
from video_ai.runtime.production_image_selection import retry_notification

result = retry_notification(
    frozen, 'image_batch_0001', 1,
    expected_attempt_sha256='原 attempt_0001/intent.json 文件原始字节的 SHA256',
    paths=RuntimePaths.from_config(frozen.config), logger=RunLogger(run, production=True),
)
```

显式重发会保留原尝试并使用新的 Message-ID；不明结果下可能收到重复邮件。SMTP 2xx 仅证明服务器接受，真实 QQ 收件箱投递留待 JIM-08 验证。自动测试全部使用本地替身，不发送真实邮件。

## 固定基准参考生成

基准批次接受后，`produce_reference_batch` 按已提交计划的关联批次生成图片，实际请求带已选原图的 TOS GET URL。每个主体和环境直接读取固定基准；同一张图的多个用途保留，主体与背景不会因为图片去重而遗漏。

先准备已存在的 TOS 桶、模型能力档案及本地设置。示例配置的 `reference_generation=null`、`reference_capabilities={}` 和 `reference_storage=null` 表示尚未配置，关联生成会等待。程序先尝试用户已选的 `image_generation`；只有它没有有效档案时才考虑显式 `reference_generation`，不推测模型能力。

`reference_capabilities` 是 `req_key` 到绝对本地 JSON 文件路径的映射。档案必须精确包含 `schema_version=1`、`req_key`、`input_field="image_urls"`、`max_images`、`max_image_bytes`、`min_width/min_height/max_width/max_height`、`formats`、`max_prompt_bytes` 和 `evidence`。限额均是正整数，formats 为非空、无重复的 png/jpeg/webp 子集。`evidence` 包含官方 HTTPS 文档的 `source_url`、材料原始字节的小写 `source_sha256`、实际核对者 `verified_by`、带时区的 `verified_at`。档案由实际核对者提供；本项目测试中的数值只用于替身，不表示真实模型限额。

`reference_storage` 必填 `provider="volcengine_tos"`、实际 `bucket`、`region`、对应的 `https://tos-<region>.volces.com` endpoint、`access_key_env`、`secret_key_env`。最后两项填写环境变量名，AK/SK 的实际值仅在进程环境设置。可选 `key_prefix` 默认 `video-ai-references`，`url_ttl_seconds/download_margin_seconds/clock_skew_seconds/request_timeout_seconds` 默认 `3600/120/60/60`。TTL 最大 604800 秒，必须覆盖模型 task timeout、下载余量和时钟偏差；原图数量、格式、字节、尺寸和最终提示词长度都在付费请求前校验。程序不创建桶或修改访问权限。

已有 JIM-03 运行缺少这些字段时，可以写一份只含三个根字段的本地 JSON：`reference_generation`、`reference_capabilities`、`reference_storage`，然后显式传入 `reference_settings_path`。只能补原冻结配置中缺失/null 的字段，不能修改已冻结模型、基准或已有设置。首次有效配置和能力原始字节保存于运行内，随后恢复无需原外部档案；再次提供不同配置将拒绝。凭证环境变量的值可以轮换。

```python
from video_ai.runtime.production_reference_images import produce_reference_batch

result = produce_reference_batch(
    frozen, units, timeline, batch_index=2,
    paths=RuntimePaths.from_config(frozen.config),
    logger=RunLogger(run, production=True),
    reference_settings_path=local_reference_settings,  # 已冻结完整设置时可省略
)
print(result.to_dict())
```

此调用会访问 TOS、付费生成关联候选并发送选图邮件；在准备真实配置和基准接受后使用。所有更早批次必须已经接受。缺配置返回 `awaiting_image_model_configuration`（退出码 3），候选邮件发出后仍为 `awaiting_image_selection`。继续使用前述选择文件/CLI 提交编号及实际整组观察，再调用参考批次入口复核；全部通过后返回 `images_ready`（退出码 0）和 `wan_inputs` 路径。其他等待、失败和中断码沿用本阶段结果定义。完整新文案协调入口留给 JIM-07，此处是准备运行的 Python API。

`production/reference-images/settings.json` 绑定参考模型、能力档案和存储位置；`reference-storage/<sha256>/intent.json` 与 `object.json` 绑定原图、内容寻址对象及实际字节验证；每个关联 scene 的 `provenance.json` 绑定用途、共享提示词和请求。每请求的 `submit-evidence.json` 绑定完整 intent 的规范摘要，读取时拒绝单独改动请求体、URL 摘要或时间证据。预签名 URL 仅在内存使用，持久记录只保存其 SHA256 和时间。已有生成 intent 却没有 task_id 时停止为 `submit_unknown`；已有 task_id 只查询原任务；邮件失败只恢复通知，不重新出图。

完整选择和整组实际观察通过后，`production/reference-images/wan-inputs.json` 按 scene 顺序列出确切已选原图、模型/task/request、单位和基准绑定。`require_reference_image_acceptance(frozen, units, timeline)` 每次重验原图、接受记录、能力与参考来源；旧纯文字模拟候选不能充当参考生成。该清单仅供下一阶段读取首图，不会提交 Wan，也不证明真实画面质量已通过；真实 TOS 取图、账号能力及视觉效果仍需 JIM-08 联调。
