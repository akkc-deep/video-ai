# 即梦候选图片与段落规划（JIM-01、JIM-02）

`config/jimeng.example.json` 显式启用 `paragraph_jimeng_v1`。它只保存 AK/SK 的环境变量名；真实值从运行进程环境读取，不能写进 JSON。模型使用智能视觉 AK/SK，不能填方舟 API Key。

JIM-01 提供可恢复的候选图片 Python 接口，JIM-02 增加独立段落画面规划 API。邮件选图及新视频协调器仍由后续任务实施；当前对新策略调用 `make-video` 会冻结并预检，在进入历史 SDXL 流程前明确返回 blocked。旧配置默认制作行为保留。

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
