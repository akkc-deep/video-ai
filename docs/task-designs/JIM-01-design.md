# JIM-01 即梦官方图片任务实施契约

## Goal

使用配置或 `make-video --image-model REQ_KEY` 选定模型，经官方异步接口生成可追踪候选原图；任何恢复不得自动重复付费提交。

## Scope

实现配置、新策略冻结和必要预检、独立 HTTPS、AK/SK 签名、任务状态解析、候选请求/原图持久化。由 Python 测试/调用入口驱动候选，不在本任务接入尚未实现的段落规划、邮件、参考图存储或 Wan 新流程。新策略的自动制作在后续协调器就绪前明确拒绝进入历史 SDXL 流程。

## Approach

- 已确认总体方案：`docs/task-designs/jimeng-email-scene-design.md`。本轮“JIM-01 完成这个任务”是实现授权。
- `ProjectConfig.production_strategy` 缺省为 `legacy`，新值为 `paragraph_jimeng_v1`；新策略必须有 `image_generation`。配置只接受凭证环境变量名，不接受凭证值。
- 图片配置：provider 固定 `volcengine_jimeng`；req_key 非空；access_key_env/secret_key_env 为环境变量名；model_parameters 为 JSON 对象；candidates_per_scene 缺省 2。输出尺寸从参数 width/height 读取，也可显式配置 output_width/output_height，必须正整数、横向 16:9。v40 预设为 2560×1440、force_single=true；切换模型不继承另一模型参数，未知模型必须显式提供参数和尺寸。参数禁止覆盖 prompt、req_key、任务、参考输入和鉴权字段，禁止嵌套凭证/URL。
- `adapters/external_https.py`：单次 HTTPS 请求，TLS 系统验证、禁代理和重定向；拒绝带凭证、fragment、非 HTTPS URL；API 固定官方主机；下载允许官方响应提供的 HTTPS URL。有限总期限及响应字节上限，不自动重试 POST；异常不保留原始 URL/响应/凭证。传输可注入 HTTP 替身，不提供生产明文 HTTP 开关。
- `adapters/jimeng.py`：标准库 SHA256/HMAC-SHA256；固定 region=cn-north-1、service=cv、version=2022-08-31；canonical URI=/，排序 Action/Version；签名 content-type/host/x-content-sha256/x-date。JSON UTF-8 实际字节参与签名。提交 CVSync2AsyncSubmitTask；查询 CVSync2AsyncGetResult，冻结 req_key+task_id，req_json 请求 URL 结果。先检查 code=10000，再检查非空 data。状态 in_queue/generating/done/not_found/expired/failed 分别处理，未知状态拒绝。返回原始数据仅在内存；持久诊断删除凭证、任意 URL 和二进制数据。
- `runtime/jimeng_candidates.py` 提供 `generate_candidates(frozen, scene_id, prompt, *, client=None, inspect=None, sleep=..., lock=None) -> dict`。入口自行持有 RunLock，已有协调器可传入其持有的锁；scene_id 为安全标识。每 scene 下各 request 目录保存 schema_version=2 的不可变 request.json（run/scene/model/prompt/序号身份）、提交意图、accepted.json（task_id/request_id）、脱敏查询快照和 result.json；持久化任务与 Comfy prompt UUID 完全分离。intent 已写但无 accepted 时返回明确 submit_unknown 异常，不再次提交。记录成功任务 ID 后的中断从查询恢复。业务失败、过期、找不到不自动补图。
- 多图结果全部分配 `request_01_image_01` 等稳定候选 ID；先持久化下载字节 SHA256/bytes 收据，再把原图写入同目录临时文件并 fsync 后原子改名，然后完整解码并保存尺寸及原图路径。完整 manifest 写入后重复调用只核验。下载失败或 URL 失效从原 task_id 重新查询，只下载缺项；已有图片重新核对身份，改变拒绝。运行中任意失败保留已有记录。查询/下载期限为每次续作独立预算，耗尽后必须显式续作，不能以续作名义重新提交。
- 完整图片使用现有 ffprobe/ffmpeg `inspect_image` 验证单帧完整解码，按配置尺寸校验，不按 SDXL 1280×720 校验，不裁切或转换原图。测试可注入只处理替身图片的 inspect 函数。
- 新策略 options schema=2，保留源配置快照及 CLI override；恢复重新推导有效模型。显式修改模型/配置被拒绝；环境凭证只在实际请求读取，允许轮换。旧 schema=1 的 resolved 快照字段保持原形。新策略不冻结、读取或预检 SDXL 模型/工作流；其余检查保留。

## Files

- 新增 `src/video_ai/jimeng_config.py`：纯配置解析与模型预设。
- 新增 `src/video_ai/adapters/external_https.py`、`src/video_ai/adapters/jimeng.py`：外部传输与官方协议。
- 新增 `src/video_ai/runtime/jimeng_candidates.py`：可恢复候选生成与 schema=2 记录验证。
- 修改 `config.py`、`cli.py`、`production.py`、`runtime/production_inputs.py`、`runtime/preflight.py`、`runtime/production_visual_templates.py`：配置/CLI/冻结/预检分派。
- 新增 `config/jimeng.example.json` 和说明；新增 unit/integration 测试。

## Tests

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-01-tests'
& $VideoAiPython -B -m pytest tests/unit/test_jimeng_config.py tests/unit/test_jimeng.py tests/integration/test_jimeng_candidates.py tests/unit/test_jimeng_inputs.py -q
& $VideoAiPython -B -m pytest -q
```

HTTP 替身覆盖签名固定向量、中文原始字节、模型差异、业务错误/空 data/所有状态、多图；故障注入覆盖 accepted 后中断、响应丢失、查询超时、部分下载失败、过期 URL、文件变化及身份变化。冻结/CLI/预检覆盖改模拒绝和缺 SDXL 可运行必要预检。预期所有新增和历史测试通过；不访问真实收费接口。

## Acceptance

任务板 JIM-01 的五项验收逐项对应上述测试；候选原图、SHA256、尺寸和模型/任务身份实际写盘。完整历史回归保留旧行为。测试不能证明真实账号权限或真实图片质量，真实调用留待 JIM-08。

## Risks

官方新模型可能需要不同参数或协议，未知模型仅支持显式配置的本异步协议。提交意图与服务响应之间存在不可消除的未知窗口，采取停止并人工核对，不能宣称 exactly-once 服务语义。进程在任务 ID 持久化前被强制结束同样进入未知状态。

外层 daemon worker 和有限等待保证调用者不受 OS DNS 阻塞影响；OS 调用本身可能延迟返回，晚到连接在发送 HTTP 前检查其截止期限。自动测试使用替身，当前没有真实官方账号/图片质量验收。
