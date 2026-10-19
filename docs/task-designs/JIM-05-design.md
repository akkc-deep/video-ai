# JIM-05 Wan 连续片段、末帧续接与动态观察

## Goal

消费 JIM-04 已完整接受的原图和 JIM-02 已提交的 scene/clip 预算，生成可逐帧核验的 Wan 源片。首片使用所选原图的比例适配副本；续片仅使用已通过连续过程观察的父片最后一个实际保留原生帧。保存确切输入、父子关系、观察与帧映射，供 JIM-06 超分和合成读取。

本设计对应任务板 Order=5。JIM-04 已先记录 COMPLETED，其最终验证为新专项 118、相关历史 186、全套 3012 项通过；这不是 JIM-05 的实现或测试证据。本轮只设计，不启动实现、模型、云请求或测试。

## Scope

包括 prepared-run Python API、独立 schema=2 源片记录、既有 Wan 工作流调用、比例适配 PNG、指定原生帧提取、非零起点裁片、旁白样本与逐帧映射、通用父片/叶片过程观察、观察等待、独立 scene 推进和原 Comfy 提交恢复。

保留 `paragraph_jimeng_v1`；不修改原文、PCM、字幕、scene 划分、选图、基准或既有图片请求。不实现新文案协调、CLI 新参数、超分、合成、最终候选观看、交付、修订运行或自动返工；这些分别属于 JIM-06/JIM-07。不给既有 Wan 增加图像参考插槽、额外视觉模型或即梦视频调用。普通自动测试使用本地替身和真实媒体工具，不启动真实推理服务。

## Approach

### 已核对的复用边界

`planning/production_visual_plan.py:plan_scene_clips` 已给出完整父子预算，必须原样消费并重新推导校验。旧 `ProductionSourceClipPlan`、`production_frame_mapping` 和 `production_visual_records` 只接受 shot/prefix 映射；不能把 scene clip 伪装成 shot。

`runtime/production_visuals.py:_Stage` 和 `adapters/comfyui.py:ComfyClient.submit_once` 绑定旧 manifest 的 `shot_attempt`、schema=1 checkpoint。新增独立 scene 事务，复用其 once-only 协议及 `production_comfy.py` 的纯 graph/queue/history 身份比较函数，不给旧 `validate_unit` 增加宽松 ID 分支，不把新记录塞进旧 `production/source-clips.json`。

复用 `WorkflowTemplate.load/instantiate/validate_remote`、`validate_fixed_visual_template(...,'wan')`、模型路径校验、ServiceManager 的自有服务生命周期。工作流仍是冻结的 `wan22_i2v_14b_api.json` 及 mapping：起图 `97.image`，positive `129:93.text`，尺寸/长度 `129:98`，fps `129:162.value`，seed high/low `129:86/129:85.noise_seed`，输出 `108` 的 `images` collection。节点、连接、模型、负面词、采样参数、编码和开关均受既有固定模板校验约束。

`media/frames.py` 现有提取器提取全序列，编码器仅支持 1080p；本任务增加独立指定帧提取函数。`media/video.py` 的旧 trim 仅保留前缀；增加独立区间裁片函数。`runtime/_source_clip_review.py` 硬编码旧 shot 对并允许历史 user_acceptance，本任务不改该协议，新增通用 schema=2 实际观察准入。`planning/final_review.py` 留给后续最终影片验收。

### 公共入口和结果

新增 `runtime/production_scene_clips.py`：

```python
produce_scene_clips(
    frozen, units, timeline, *, paths, logger,
    client_factory=None, service_factory=None, lock=None,
) -> SceneClipResult

consume_scene_clip_observation(
    frozen, units, timeline, observation_path, *, paths, logger, lock=None,
) -> SceneClipResult
```

第二入口只保存/验证用户或具备实际播放能力的审查者提供的观察，不提交 Wan，也不自动继续下一片。继续生成由显式再次调用第一入口完成。两入口自动获取 RunLock；传入锁时验证同 run 的真实所有权并由调用方释放。全部记录提交在持锁调用线程进行。

新增 `runtime/scene_clip_records.py`：

```python
load_scene_clip_progress(frozen, units, timeline) -> dict
require_scene_clip_acceptance(frozen, units, timeline) -> dict
```

均为只读：从原输入、原提交证据、实际媒体及观察重建结果。后者要求全部 clips 和全部过程观察通过，并返回已存在且逐项一致的 `production/scene-clips/complete.json`；不启动服务、不创建缺失记录。

`SceneClipResult` 精确字段为 `schema_version/production_strategy/run_id/run_dir/status/active_stage/scenes/observation_templates/source_clips/log_dir/error`。schema=2，strategy=`paragraph_jimeng_v1`，stage=`source_clips`。scenes 按 plan 顺序，行精确为 `scene_id/status/completed_clip_ids/accepted_clip_ids/waiting_clip_id/error`；completed 指技术媒体完整，accepted 指过程观察通过。顶层 observation_templates 为本次待观察 clip 的模板绝对路径数组，按 scene/ordinal 排序；失败场景也保留可查看的媒体路径于其错误 evidence_paths。source_clips 只在 `source_clips_ready` 时为已验证 complete.json 的绝对路径，其余为 null。

顶层状态/退出码：`awaiting_continuity_review=3`、`source_clips_ready=0`、`blocked=2`、`failed=1`、`interrupted=130`。scene 状态为 `pending/awaiting_continuity_review/continuity_failed/submit_unknown/blocked/failed/ready`。error 为 null 或精确 `kind/message/evidence_paths`。未知 run 不填虚构 run/log/媒体路径。自有锁释放和服务清理错误也返回本阶段独立结果，不进入 schema=1 的失败写入逻辑。

全局输入不合法、失锁或 KeyboardInterrupt 立即结束。单个 scene 的明确模型失败、提交不明或观察失败只停止该链，记录后继续其他 scene。正常遍历完后，顶层按 `failed > blocked > awaiting_continuity_review > source_clips_ready` 汇总；continuity_failed 和 submit_unknown 归 blocked，未观察归等待。每个 scene 的状态独立保留，不能把另一链的等待标成自己的失败。

### 图片和全局请求前置校验

首次执行先核对 `load_frozen_inputs`、`load_committed_plan(frozen,units,timeline)`，再调用 JIM-04 `require_reference_image_acceptance`；全部选择和 all_selected_images 观察有效才允许任何 Wan POST 或模型服务启动。只读取该函数返回的精确原图，不用邮件预览、拼图、URL 或相邻候选代替。

重新计算原图 SHA256、完整解码和尺寸；JPEG 的 decoder 名 `mjpeg` 归入 JPEG 格式检查，但保留候选原元数据。不以主图片模型的输出尺寸校验关联模型原图；JIM-04 返回的每一行已选图及其实际解码结果分别为依据。继承总体方案首版横向 16:9 要求：`width*9 == height*16`，不符在任何 Wan 提交前拒绝，不裁切或拉伸。

按冻结 `media.profile` 取 native16 尺寸：fast=768×432，quality=1280×720；16 fps、cut、无过渡的约束保持。冻结 workflow/mapping 字节摘要、模型 ArtifactStamp 及真实模型路径、服务地址、ffmpeg/ffprobe 路径和总空间预算；不引入新的模型默认。模型大文件继续沿用冻结 ArtifactStamp 的现有语义，媒体及输入图片必须额外用 SHA256。

全批预检包括所有 selected originals、全部 clip 数值、最终共享提示词、workflow/template、profile、模型路径/戳和已经存在的父链记录。后面场景的本地错误不能在前面场景已经新提交后才发现。每次实际发送还须重验其直接输入、父片、观察收据、全局绑定及 graph。

### 目录、身份和绑定

新根目录为 `production/scene-clips/`，每个 clip 使用 `<scene_id>_clip_<ordinal:04d>/`；scene 和 clip ID 必须与 committed plan 的完整值相等，不能仅靠正则准入。所有路径经 run_path/PathPolicy 校验，拒绝逃逸、软链接替换和未知输出前缀。全局逻辑 JSON 使用既有 canonical_digest，原图/视频/PNG/原始提交文件使用原始字节 SHA256。

本任务媒体 `Artifact` 精确字段统一为 `path/bytes/sha256`：run 内绝对路径、严格正整数 bytes、小写 64 位 SHA256；每次读取重算 bytes/SHA，不依赖 mtime。timestamp 一律带时区；数字拒绝 bool、NaN、无穷。字段集合严格校验，不把缺省键自动补成接受记录。

全局 `inputs.json` 精确字段：`schema_version/production_strategy/run_id/algorithm/frozen_options_sha256/scene_plan_sha256/visual_bible_sha256/units_sha256/timeline_sha256/wan_inputs_sha256/profile/workflow/mapping/model_stamps`。algorithm=`scene_wan_continuation_v1`；profile 精确为 `name/width/height/native_fps`；workflow/mapping 为 Artifact；model_stamps 是冻结的 wan_high/wan_low/text_encoder/vae 四个原角色 ArtifactStamp 映射。wan_inputs_sha256 是已验证 JIM-04 清单的规范摘要。inputs 必须先于任何请求持久化；以后仅完全一致复用。

每 clip 的静态规划条目精确为 `budget/parameters/narration_bindings/comparison_images`。budget 是 plan.clips 原行，字段不改；parameters 见下节。comparison_images 按 Bible baselines 顺序列出此 scene 实际引用的实体/变体/场景组基准，包括基准恰好是本 scene 的项，行精确为 `kind/id/scene_id/candidate_id/image`，image 为已接受原图 Artifact。相同图片可对应多个 use；不得遗漏主体或环境。所选 scene 自己的原图也独立绑定于下述 selected_image。

所有新 JSON 采用同目录临时文件、fsync、持锁原子改名；已有最终文件一致才复用，冲突拒绝覆盖。媒体先写唯一 staging 文件，完成解码、hash 与源文件前后校验后写准备收据，再晋升为固定名字；准备收据包含最终身份和实际 staging 身份。恢复只允许把该收据绑定的相同字节晋升，不能把偶然存在的文件认作已生成成果。未提交前的无收据技术临时文件可以保留在 staging 并另建新临时文件；已有 Wan intent 后不得因此重新生成。

准备收据路径为 clip 目录下 `media-ready/<operation>.json`，operation 只允许 `input/generated/source/last_frame`。精确字段为 `schema_version/run_id/clip_id/operation/source/staging/target/recipe/evidence/created_at`；三媒体路径为 Artifact，target 的 SHA/bytes 必须等于 staging；source 是该操作直接读取的 Artifact；recipe 精确为 `algorithm/parameters`，algorithm 对应本设计的 copy/contain/native-index/trim 规则，parameters 是实际执行的完整 filter、尺寸或半开帧范围，identity copy 为 `{}`；evidence 为命令/核验文件 Artifact 数组。晋升前有 staging、晋升后有 target，两者都在则均须一致；两者均缺失或任一冲突拒绝。input 的直接源为已选图或父末帧，generated 的直接源为 submission.output，source/last_frame 的直接源为本 clip generated。有效准备收据可恢复晋升和外围 JSON，不重新执行已经得到有效字节的操作。

### 提示词和固定 Wan 参数

新增 `planning/scene_clip_continuation.py`：

```python
build_scene_wan_plan(frozen, bible, plan, timeline, wan_inputs) -> list[dict]
scene_clip_frame_mapping(clip, *, actual_generated_frames) -> dict
validate_scene_clip_frame_mappings(plan, timeline, mappings) -> None
```

positive 固定为 `scene.motion_prompt + '\nVISUAL_BIBLE_JSON\n' + canonical_json(context)`。context 精确为 `global_style/entities/appearance_variants/scene_groups`，与 JIM-04 相同，只选 scene 引用的 ID 行并保持 Bible 顺序；不添加新事实，不截断原文或共享设定。每个续片沿用该 scene 的相同 positive，不重新自由描写主体；该算法不承诺动作语义自动连续，需观察。

parameters 精确为既有 Wan 参数字段 `positive/negative/seed_high/seed_low/width/height/length/fps/batch/steps/cfg/sampler/scheduler/split_step/shift_high/shift_low/lora_enabled`。negative=现有 WAN_NEGATIVE；seed_high=`264244520398999 + 全局 plan.clips 零基序号`、seed_low=0；length=clip.generated_frames；fps=16、batch=1、steps=40、cfg=3.5、sampler=euler、scheduler=simple、split_step=15、两 shift=`5.000000000000001`、LoRA=false。width/height 取本运行 profile。种子只固定请求，不能视为一致性证据。

实例化模板只替换已映射的 positive/start_image/width/height/length/fps/seed_high/seed_low 和程序生成的 output_prefix；不得修改 negative 或其他固定节点。完整 POST body UTF-8 不得超过既有 JSON_LIMIT=32 MiB，超限在 intent 前拒绝，不截断。实际请求保存完整 graph，摘要不是 graph 的替代物。

### 起图副本和父片末帧

首片 `selected_image` 精确为 JIM-04 对应 scene 行（包含原 req_key/request_id/task_id、unit_ids、baseline_bindings、reference_provenance_sha256）；再由其 path/bytes/sha256 构成源 Artifact。选图身份不会因比例转换、PNG 编码或 Wan profile 改变而被替换。

首片复用 `media.images.adapt_image(...,production=False)` 和 `contain_filter(width,height)` 的现有比例缩放/居中黑色 padding/setsar=1/RGB24 规则，记录实际 filter 全文。源已要求 16:9，所以正常不会出现主体裁切或非比例伸缩。目标为 native profile 尺寸单帧 RGB24 PNG。即使原图尺寸相同，也保存独立受控 PNG；不覆盖原图。PNG/JPEG/WebP 原图均须完整解码，不能只改扩展名。

每 clip 的 `input.json` 精确字段为 `schema_version/run_id/clip_id/kind/source/target/rule/filter/width/height/pixel_format`。kind 沿 budget.input_kind；source/target 为 Artifact，pixel_format=rgb24。首片 rule=`contain_png_v1`、filter 为上述现有 filter；续片 rule=`identity_png_copy_v1`、filter=null，直接按字节复制父片已提取且核验为目标尺寸的 PNG，不重新缩放或编码。

目标路径固定为 `comfy/input/<run_id>/scene_clips/<clip_id>/start.png`；graph 中仅使用相对 `<run_id>/scene_clips/<clip_id>/start.png`。复制前后验证源和目标 SHA；不能只比较 bytes。生成输出前缀固定 `<run_id>/scene_clips/<clip_id>/attempt_0001`，不使用历史 shot 路径。

新增 `media.frames.extract_native_frame(source,target,*,source_frame_index,expected_frames,width,height,config,paths,logger,unit_id,timeout=300) -> (info,evidence_paths)`。先按现有视频规范完整核验生成视频；零基索引必须小于精确 expected_frames；从视频起点解码并按帧序号 `select=eq(n\,INDEX),format=rgb24` 提取恰好一张，不用 `-ss` 秒数寻址，不改变 fps，不取缩略图。固定 PNG 名 `frame_<INDEX+1:06d>.png`；完整 decode、RGB24 和 native 尺寸检查，源 hash 前后不变，目标 hash 持久化。添加独立函数，不改变原全帧提取器的 one-based 约定和 upscale 日志语义。

每 clip 均保存 `last-frame.json`，包括叶片以便准确审查其末帧。精确字段为 `schema_version/run_id/clip_id/generated/source_frame_index/global_output_frame_index/image/extraction_rule/evidence`；generated/image 为 Artifact，extraction_rule=`native_index_rgb24_v1`，evidence 为命令和媒体检查文件 Artifact 数组。`source_frame_index = budget.retained_source_end-1`；global_output_frame_index=`budget.end_frame-1`。从原始 generated.mp4 的保留范围选取，不从 discarded tail 取帧，也不从有损重编码后的 source.mp4 重新选帧。source.mp4 仍是该原生范围的一一映射，不能宣称其压缩后像素与原生成视频逐字节相同。

续片的父绑定精确为 `clip_id/clip_sha256/generated/source/last_frame_sha256/last_frame/observation_acceptance_sha256`。clip_sha256 为父 clip.json 规范摘要，generated/source/last_frame 是相应 Artifact，last_frame_sha256 为父 last-frame.json 规范摘要；observation_acceptance_sha256 为父 observation-accepted.json 规范摘要。parent=null 仅用于 scene 首片。parent 必须是 plan 中同 scene 直接前片，不跨 scene 自动连接；新 scene 是有意 cut，使用自己的 selected image，且输入不携带前 scene 的末帧。

### 精确帧映射和旁白

生成视频必须恰好包含 budget.generated_frames，不接受“足够长”但数量不同的输出。完整 decode/PTS/CFR 验证继续要求 MP4、单 H.264 视频流、无音频、native16、正确尺寸和每帧时序。少帧或多帧均技术失败，保存原输出和原因，不自动再提交、循环、冻结、变速或补帧。

新增 `media.video.trim_scene_video(source,target,*,source_info,start_frame,end_frame,width,height,config,paths,logger,unit_id,timeout=300)`，半开 native 区间必须等于预算。用 `trim=start_frame=A:end_frame=B,setpts=N/(16*TB)`，沿现有 libx264/medium/crf18/yuv420p/passthrough 规则输出；不得增加 fps 滤镜、转场或音轨。目标精确 B-A 帧。完整检查和 SHA 前后校验；所有操作有总期限，并把实际参数/命令/检查证据绑定技术记录。

两个新媒体 helper 的 info 继续采用现有 `inspect_image`/`inspect_video` 的 SHA-bearing `identity` 结果形状（production=False），不使用仅有 stamp 的 production 检查结果；trim 返回 `(info,evidence_paths)`。调用方把 identity 中 path/bytes/sha256 投影为本任务 Artifact。`trim_scene_video` 的 source_info 是同一路径的 `inspect_video` 返回值，必须核对其全部媒体数字及 identity，不能信任调用者伪造的 frames。

mapping 精确字段为 `clip_id/scene_id/native_fps/output_fps/generated_frames/retained_frames/start_frame/end_frame/generated_to_retained/retained_to_generated/output_to_generated`。两 fps=16；generated_to_retained 长度 G，第 j 项在 A<=j<B 时为 j-A，其余 null；retained_to_generated=`range(A,B)`；output_to_generated 行精确为 `output_frame/generated_frame`，逐个列出 `(clip.start_frame+k,A+k)`。所有索引零基，区间半开，bool 拒绝。

200 帧 scene 的既有预算必须保持如下数值，不另算另一套长度：

| clip | 全局贡献区间（scene 从 0 开始） | 生成帧数 | 保留 native 区间 | 丢首/裁尾 | 末保留 native 索引 | PNG 文件 |
|---|---|---:|---|---|---:|---|
| 1 | [0,93) | 93 | [0,93) | 0 / 0 | 92 | frame_000093.png |
| 2 | [93,185) | 93 | [1,93) | 1 / 0 | 92 | frame_000093.png |
| 3 | [185,200) | 17 | [1,16) | 1 / 1 | 15 | frame_000016.png |

生成 203 帧，去掉两个续片首帧和最后一个尾帧，保留 200 帧=12.5 秒。第三片的 native16 帧被裁掉，不能代替 native15 作为末保留帧。第二片输入等于第一片 PNG，第三片输入等于第二片 PNG；这里两个 `frame_000093.png` 位于不同 clip 目录且分别绑定各自 generated SHA。

每 clip 的 narration_bindings 由 clip 全局样本窗 `[start_frame*3000,min(end_frame*3000,timeline.total_samples))` 与所属 scene.bindings 逐行相交，字段保持 `unit_id/text_start/text_end/text/semantic_member/start_sample/end_sample`，丢弃空交集。text 保留完整原 unit，不用 scene 摘要代替。不把旁白文本按视频帧机械切成新字幕。每 unit 的所有 clip 样本交集须恰好覆盖其 PCM 语音区间；停顿由 frame 覆盖承载，末尾不足一帧的 padding 不冒充语音。全局映射必须无重叠无空洞覆盖 `[0,timeline.total_frames)`，含首尾与句/段停顿。

### Schema=2 Comfy 单次事务

新增 `adapters/scene_comfy.py:SceneComfyClient(base_url,*,request_timeout,ownership_check,http=None)`。接口固定为 `object_info(*,timeout)`, `system_stats(*,timeout)`, `submit(graph,*,client_id,timeout)`, `queue(*,timeout)`, `history(prompt_id=None,*,timeout)`；返回精确 `status/headers/body` 的内存响应，body 为原始 bytes。client 不写盘、不生成/替换 client_id、不隐式重试 POST。默认只能使用 validate_base_url 允许的本机 HTTP；固定路由 GET `/object_info`、`/system_stats`、`/queue`、`/history[/UUID]` 与 POST `/prompt`，请求体仅 `prompt/client_id`，拒绝代理、重定向和 path 注入。

默认有限 transport 的网络线程只进行 I/O 和只读 guard；在连接前、连接/DNS 结束后、每次实际 send、响应接收完和总期限后检查 cancellation/ownership。总 deadline 必须约束 DNS 迟到线程，调用线程返回后其不能新发请求或写日志。请求/响应原始字节及元数据由持锁调用线程保存；不直接复用会在旧 manifest 写 submission 的 ComfyClient，也不以放宽既有 HttpClient 本机限制解决新需求。可复用既有 deadline/loopback 校验的纯部件，旧公共入口默认行为保持。

`client_factory` 调用参数精确为 `(base_url, request_timeout=..., ownership_check=...)`，返回上述客户端接口，注入测试不启动服务。默认请求超时为 frozen.config.timeouts.comfy_request，单次跟踪总预算为 timeouts.wan，轮询间隔 2 秒且受剩余预算约束。每次恢复可获得一次新的有限跟踪预算，仍跟踪同一提交。

新增 `runtime/scene_comfy_transactions.py`，接口 `recover_or_submit_scene_clip(store,request,graph,*,client,template,ensure_service,logger,timeout) -> dict`，store 为同 run 的持锁记录存储，request/graph 已完整本地验证。只在缺失任何 intent 时允许新 POST。输出为已验证原任务的提交回执和唯一模型输出 Artifact。

每 clip 文件与精确字段：

- `request.json`：`schema_version/production_strategy/run_id/scene_id/clip_id/inputs_sha256/budget/parameters/narration_bindings/comparison_images/selected_image/input_sha256/parent/graph_sha256`。input_sha256 指 input.json 规范摘要，selected_image 始终为本 scene 的 JIM-04 原行，即使实际输入为父末帧也保留固定选图依据。
- `graph.json`：实际完整 workflow 对象，规范摘要等于 request.graph_sha256；实例化后逐节点重验，不能仅比较 class_type 集合。
- `intent.json`：`schema_version/run_id/clip_id/request_sha256/graph_sha256/input_sha256/parent_sha256/attempt_id/client_id/output_prefix/created_at`。attempt_id/client_id 为持久 UUID；parent_sha256 为 request.parent 的规范摘要，首片为 null。attempt 名永远 attempt_0001；失败后本任务无第二次 attempt。
- `accepted.json`：`schema_version/run_id/clip_id/intent_sha256/prompt_id/number/acceptance_evidence`。prompt_id 为标准 UUID，number 有限 int/float 非 bool；acceptance_evidence 为 Artifact，绑定实际 POST 接受响应或实际 GET 找回的完整 queue/history 响应。
- 每次 HTTP 记录存于 `http/<UUID>.request.json/.body/.response.json`。request 精确 `schema_version/run_id/clip_id/intent_sha256/method/route/body_sha256/started_at`；GET body_sha256=null。response 精确 `schema_version/run_id/clip_id/request_sha256/status/headers/body/finished_at/error`；body 为 `.body` Artifact，status 为 HTTP int 或无响应时 null，error 为 null 或 `kind/message`。原始 POST payload 可从 graph/client_id 重建并比 body_sha256；响应禁止静默截断，32 MiB 上限。
- `submission.json`：`schema_version/run_id/clip_id/intent_sha256/accepted_sha256/prompt_id/history_evidence/output`，history_evidence/output 为 Artifact；只在原任务成功并输出归属匹配后提交。
- `terminal.json`：`schema_version/run_id/clip_id/intent_sha256/status/evidence/reason`，status 为 `rejected/execution_failed/identity_conflict/invalid_media`；evidence 为 Artifact 数组，存在后禁止该链新提交。普通跟踪超时不是确定 terminal，保留 accepted/intent 后返回 submit_unknown 或 blocked 并可 GET 恢复。

顺序为 input/graph/request 完整验证→保存 intent→重验锁和所有 captured 身份→POST→先持久保存原 HTTP 响应→accepted→原 queue/history 跟踪→submission。成功响应已落盘但 accepted 缺失时从确切原响应补齐，绝不再 POST。intent 存在而无 prompt_id 时只能读取本地证据及 GET `/queue`、`/history`，按 client_id+完整 graph 唯一匹配原任务；0 或多个匹配返回 submit_unknown。

第一次新提交在 intent 前还必须 GET `/object_info` 并调用 template.validate_remote；可在同一次自有服务生命周期内复用有效结果。历史任务恢复不以再次 object_info 成功作为找回原 ID 的前提。健康和模板检查的原响应由调用线程保存到 `logs/production/scene-clips/service/`，沿既有服务日志格式，不冒充某个 clip 的提交证据。

复用 `production_comfy.metadata/matches/_same_history_graph/output_from_history` 的纯语义：允许无损 `16`↔`16.0`，拒绝 bool/精度丢失；同时核对已知 prompt_id、number、映射 output node=108 与完整 owned output prefix。queue/history 同一 prompt 冲突写 terminal，后来某一次成功 history 不能抹掉冲突。completed history 不得同时仍在 running/pending queue；唯一输出须为 owned output 类型、指定目录、前缀及 `.mp4`，不按最新文件或同名猜输出。GET 的瞬时失败可在总期限内继续查询；所有 POST 不重放，明确失败也不自动换参数/种子/模型重做。

### 服务、锁和有限恢复

默认生产实现沿 `production_scene_plan` 的模式持锁打开/创建现有 ManifestStore（verify_integrity=False），仅供 ServiceManager 保存服务与资源事实；核对其 frozen raw/resolved 与 run 身份，已有冲突拒绝。使用 `build_service_specs(...,production=True,frozen=frozen,store=manifest)['comfyui']`，run 专属 input/output/temp/user 与 database 参数保持原样。不往旧 manifest units/stages/checkpoints 写 scene clip 完成状态。

`service_factory` 注入签名为 `(frozen,paths,logger,lock)`，返回实现 `ensure()/close()` 的作用域对象；默认封装上述自有 ServiceManager，并由 coordinator finally 关闭。只在确有新 POST 或原任务 GET 需要时 ensure；已完成本地证据回放和仅等待观察不启动 Comfy。拒绝不属于本次运行可核实 ownership 的外部监听服务，不停止外部进程。恢复必须先处理现有 service ownership 记录，不能任意另起第二个占端口服务。

默认健康检查也经有限、本机、只读所有权 guard 的 transport；其结果由调用线程交给既有服务管理器，不能在网络线程修改 manifest。普通异常/等待/KeyboardInterrupt 都释放本次自有服务和锁；外部传入锁不释放。清理失败保留原错误及清理证据，不能报告 ready。

实际 POST guard 捕获并重核 request/graph/input/inputs 的 SHA、输入 PNG 和其原图、父 generated/source/末帧及父观察/accepted 摘要、workflow/mapping 和 frozen model stamps。后台 guard 不解码生成新媒体、不写日志、不提交状态。每个磁盘晋升前后在调用线程核验锁。失锁后已存在 intent 留作未知，不补发；迟到响应不会写 accepted。原 prompt 已受理时，只通过原任务恢复媒体；源图、父片或观察身份改变则拒绝复用整个后代，不自动把变化后的父片接到旧 child。

### 技术 clip 与过程观察

成功模型输出先复制到 clip 目录的 `generated.mp4`，核验完整 Artifact 和 exact G；裁出 `source.mp4`；提取最后保留 native PNG；生成 `mapping.json`。技术 clip.json 精确字段为 `schema_version/production_strategy/run_id/scene_id/clip_id/request_sha256/submission_sha256/generated/source/frame_mapping_sha256/last_frame_sha256/technical_evidence/created_at`；technical_evidence 为命令/媒体核验文件 Artifact 数组。最后提交 clip.json 才表示技术片段完整；这不表示动态一致性通过。

新增 `runtime/scene_clip_observations.py`，提供 `build_observation_template(frozen,clip_record,request,mapping,last_frame,parent_records) -> dict` 和只读 `validate_scene_clip_observation(value,expected,*,now) -> dict`。每个技术 clip 都产生 `observation-template.json`，叶片也必须观察后才可进入 complete。模板中的 authored strings 为空、checks/verdict 为 unverified、review_method/reviewer/viewed_at 为 null，不生成虚构观看或自动 passed。

观察文件精确字段：`schema_version/production_strategy/run_id/scope/scene_id/clip_id/clip_sha256/request_sha256/visual_bible_sha256/selected_image/comparison_images/generated/source/last_frame/parent/playback/review_method/reviewer/viewed_at/start_observation/process_observation/end_observation/quality_observation/continuity_observation/checks/verdict/issues/reason`。

scope=`scene_clip_process`；generated/source/last_frame 为 exact Artifact；selected_image/comparison_images 与 request 相等；parent 与 request.parent 相等。playback 精确 `clip_source_frames/parent_source_frames`：本片必须 `[0,retained_frames)`，有父时还必须为父 `[0,parent.retained_frames)`，无父时 null。全部实际播放范围不得用截图数组替代；无需把裁掉的头尾当最终贡献播放，但必须查看已绑定的确切末帧 PNG。所选起图/基准图片及末帧的实际比较由 start/end/continuity 文本逐项描述。

review_method 只接受 `human_video/agent_video`，reviewer 非空，viewed_at 带时区、介于技术 clip.created_at 和校验当前时间。agent_video 仅指实际具备播放查看能力的审查者，不启用任何新模型。五项 observation 和 reason 均非空，必须描述实际起点、连续中段、终点、画质以及与固定原图/基准和父片边界的比较。首片 continuity_observation 解释起图到本片过程，续片解释父末保留帧、child 起始与丢首后的动作衔接；不得复用旧硬编码 shot pair 标记。

checks 精确为 `subject_identity/appearance_structure/color_clothing/environment_space/time_lighting/style/motion_process/end_frame_stability/input_alignment/parent_join`；各值 `passed/failed/unverified`，仅首片 parent_join 必须为 null，续片必须三态之一。即使 scene 无人物，主体/外观项也应说明实际主要对象的检查，不能靠缺少 entity_id 自动设 passed。与剧情一致的变化只按该 scene 的 Bible/variant/change_sources 解释。

verdict=passed 需所有适用 checks=passed、issues=[] 且完整播放/身份/文本/时间有效；failed 至少一个 failed 且 issues 非空；unverified 无 failed、至少一个适用 unverified。issues 行精确 `check/frames/description`，check 必须是适用 checks 键，frames 为本片 retained source 范围内非空半开区间，description 非空。结构错误、身份错误和伪造范围不是 unverified，必须拒绝。

consume 在持锁线程读取观察源原始字节并按 SHA 保存到 `observations/<raw_sha256>.json`，保留原文和失败/未核实结论。重复相同提交幂等。每 clip 的 `observation-accepted.json` 精确 `schema_version/run_id/clip_id/clip_sha256/request_sha256/observation/observation_sha256/accepted_at`；observation 为源副本 Artifact，observation_sha256 为其规范摘要。仅完全 passed 才创建。已有接受不可覆盖；新的相同语义但不同原始提交不替换已接受观察。unverified 可由后续新的完整 passed 观察解除；明确 failed 保存 `observation-rejected.json`，字段同 accepted 但 rejected_at 替换 accepted_at，阻断该链，本任务不提供原地翻案或重新推理，修订留给 JIM-07。

观察接受需要重新验证所有媒体、输入、基准及父接受。不能仅检验模板 SHA 或 verdict。父 clip 技术完整但无有效接受时，不提交 child，也不把 child 标 failed。某 scene 当前缺观察时继续遍历下一独立 scene；每条链按 ordinal 串行处理，最多推进到下一未观察片。叶片无 child 也需要过程观察，避免“没有后代所以自动通过”的漏洞。

### 完整源片准入和只读进度

`load_scene_clip_progress` 返回精确 `schema_version/run_id/inputs_sha256/scenes`，scenes 使用 SceneClipResult 的 scene 行；状态从存在的事务/媒体/观察记录推导，不信任可变 status 字段。存在部分安全前缀可返回等待；非法/冲突文件直接拒绝，不删掉后假装 pending。

所有 clips 技术和过程观察通过后，produce 或 consume 的最终收尾重建并最后写 `complete.json`，精确字段为 `schema_version/production_strategy/run_id/inputs_sha256/scene_plan_sha256/visual_bible_sha256/wan_inputs_sha256/timeline_sha256/total_frames/scenes/clips`。

scenes 行精确 `scene_id/unit_ids/start_frame/end_frame/bindings/selected_image/clip_ids`，来自原 scene/选图；clips 按 plan.clips 顺序，行精确 `clip_id/scene_id/budget/narration_bindings/generated/source/frame_mapping/last_frame/clip_sha256/observation_acceptance_sha256`。frame_mapping 为完整已验 mapping 对象，last_frame 为完整已验 last-frame.json，generated/source 为 Artifact。全部 clip 数量与顺序、父子链接、native retention 和样本覆盖都重新推导。下游获得确切 source.mp4 和 generated native 帧对照，而非重新按时长猜切点。

`require_scene_clip_acceptance` 每次从 JIM-04 原准入、JIM-02 commit、原 Comfy graph/accepted/history/submission、媒体 SHA、mapping、末帧和完整观察源副本重建 complete 并比较。任一原图、父片、输入 PNG、观察、graph、输出或 mapping 改变均拒绝；原媒体仅改 mtime 而字节不变不改变本任务 Artifact 身份，但仍须满足冻结工具/模型的既有戳约束。完整本地回放零服务启动、零 Wan POST、零再裁片/再抽帧，只读核验。

中断后从确切原证据补齐缺失技术/complete 标志。已接受任务的原输出丢失且无完整 owned output 可读时停止，不能靠再次生成“恢复”；可重做的仅是尚未接受、来源完整且没有最终有效媒体收据的确定性本地转换，保留旧临时证据。任何有有效最终 Artifact 的转换结果不因缺少外围索引而重新编码。

## Files

- 新增 `src/video_ai/planning/scene_clip_continuation.py`：共享提示词/固定参数、clip 样本交集、原生与全局帧映射及完整覆盖校验。
- 新增 `src/video_ai/adapters/scene_comfy.py`：本机受控内存 HTTP、实际发送 ownership/deadline、无自动 POST 重放；不使用旧 shot manifest。
- 新增 `src/video_ai/runtime/scene_comfy_transactions.py`：新 schema=2 graph/intent/accepted/history/submission、原 ID 恢复与冲突证据。
- 新增 `src/video_ai/runtime/production_scene_clips.py`：两公共入口、自有锁/服务、全部前置验证、独立 scene 调度、技术提交与结果。
- 新增 `src/video_ai/runtime/scene_clip_records.py`：所有新精确记录验证、只读进度和 complete 准入。
- 新增 `src/video_ai/runtime/scene_clip_observations.py`：真实播放范围、固定原图/基准/父子对照、观察模板/接受/拒绝。
- 修改 `src/video_ai/media/frames.py`、`src/video_ai/media/video.py`：增加独立指定 native 帧提取及区间裁片 API，保留旧函数行为。修改 `media/images.py` 仅在需要为适配日志显式传 stage 时增加兼容可选参数；复用现有 contain 转换，不替换旧规则。
- 修改 `src/video_ai/planning/production_visual_plan.py` 仅在需要导出新纯 helper 时添加明确新接口；已有 plan_scene_clips 预算不改。`runtime/production_visuals.py` 仅允许增加显式新策略转发入口，旧 produce_source_clips 签名/输出和 validators 不变；新独立 API 本身即可供后继调用，不接通 production.py 全流程。
- 复用 `runtime/production_comfy.py` 的纯比较/输出归属 helper、`workflows.py`、`production_visual_templates.py`、`service_specs.py/services.py`；若提取共享纯 helper，旧消费者及契约须保留。不修改 versioned Wan workflow/mapping 内容。
- 新增 `tests/unit/test_scene_clip_continuation.py`、`test_scene_clip_records.py`、`test_scene_clip_observations.py`、`test_scene_comfy.py`、`tests/integration/test_scene_clip_generation.py`；在既有 `test_frames.py/test_video.py` 添加新媒体函数场景。
- 修改 `docs/jimeng-candidates.md`：说明 prepared-run 入口、观察文件、等待/失败/原 ID 续作、源片就绪与正式交付区别。不在本任务新增 CLI 或把尚未实现的全流程写成可用命令。

## Tests

第一实施动作：在 `tests/unit/test_scene_clip_continuation.py` 建立纯数字 `test_200_frame_retained_native_mapping`，调用既有 plan_scene_clips 得到 200 帧预算，再调用尚未实现的新 mapping API。断言 `[93,92,15]`、`[93,93,17]`、保留起点 `[0,1,1]`、末帧 `[92,92,15]`、generated_to_retained 的 head/tail null、全局 `[0,200)` 恰好一次覆盖及输入不变；先运行看到新接口缺失的 RED，再实现纯规则。不得以调整 JIM-02 预算来让新测试通过。

计划命令（本设计阶段未运行、未宣称通过）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-05-tests'
& $VideoAiPython -B -m pytest tests/unit/test_scene_clip_continuation.py -k test_200_frame_retained_native_mapping -q --tb=short
& $VideoAiPython -B -m pytest tests/unit/test_scene_clip_continuation.py tests/unit/test_scene_clip_records.py tests/unit/test_scene_clip_observations.py tests/unit/test_scene_comfy.py tests/integration/test_scene_clip_generation.py tests/unit/test_frames.py tests/unit/test_video.py -q --tb=short
& $VideoAiPython -B -m pytest tests/unit/test_scene_clip_budget.py tests/unit/test_production_visual_plan.py tests/unit/test_production_visual_records.py tests/unit/test_production_visuals.py tests/unit/test_production_visual_templates.py tests/unit/test_workflows.py tests/unit/test_source_clip_generation.py tests/unit/test_source_clip_checks.py tests/unit/test_source_clip_user_acceptance.py tests/integration/test_production_comfy_recovery.py tests/integration/test_comfy_tracking.py tests/integration/test_jimeng_reference_flow.py tests/unit/test_production_delivery.py tests/integration/test_make_video_recovery_contract.py -q --tb=short
& $VideoAiPython -B -m pytest -q --tb=short
```

除第一步预期缺接口失败外，最终各命令预期退出 0、全部通过。全套串行运行，避免已知共享运行/字体资源并发干扰；记录实际输出/退出码和验证文件哈希，未运行项不能计为通过。

具体用例：

1. 真实 JIM-04 complete fixtures，至少三 scene，包含同一 scene 跨多句和 200 帧长链；首片 actual graph `97.image` 指向确切所选图的转换 PNG。基准 PNG 与关联 JPEG(mjpeg)、不同 primary/reference 输出尺寸分别进入 fast/quality，原图未改；非 16:9、缺选择/全组观察、变化原图均零 Wan POST/服务启动。
2. 用每帧可区分的真实 native16 H.264 fixture 验证 extraction；解码 PNG 的像素与指定 generated native 帧一致。93/93/17 的最后 PNG 为 093/093/016，child 输入 bytes/SHA 与实际父 PNG 完全相同；不得误取第三片补齐第 017 帧。裁片真实 PTS、帧数、无音频和尺寸正确，第二片去头、第三片去头尾。验证 scene 非零全局起点及 1/93/94/185 帧边界。
3. 完整 units/PCM timeline 有首尾、句间、段间停顿和非整帧尾样本；scene/clip 的多 unit text 和 sample 交集全覆盖，无丢词、重复样本或旧单主 unit 限制泄漏。全部 output 帧仅映射一次，无转场、速度变化、循环/冻结或额外首帧。
4. 首次调用只生成各 scene 可执行首片，长链 child 无观察时零 POST；另一个独立 scene 仍生成并独立等待。有效父实际观察后，child actual graph 使用其末帧，positive 保持同一 Bible 上下文。父 failed/unverified、错影片 SHA、少播中段、仅首尾截图、错误 parent_join、伪 reviewer 时间、额外/缺项拒绝；叶片同样需要过程通过。检查包括无实体/多主体/明确服装变化，通用任意 clip pair，不限旧 hardcoded shot 对。
5. HTTP 替身捕获真实 `/prompt` graph/client_id；POST 接受后、HTTP 落盘后 accepted 前、history 后、媒体 staging/晋升/clip/观察/complete 每个边界中断恢复；同 clip POST 总次数为 1。未知无 ID、graph 不同、同 prompt queue/history 冲突、失败、超时、输出归属错误、损坏或帧数不符都不能重发或换模。GET 恢复原 UUID/graph/number，允许无损 FLOAT、拒绝 bool/seed 精度丢失；已完成重入无服务/POST/编码/提取。
6. 失锁、连接延迟、总超时、KeyboardInterrupt、caller-thread 磁盘写入、晚到线程、服务启动/停止失败、外部锁/服务、错误收尾分别注入；失锁后无新 POST/新 receipt、没有后台磁盘写入，自有资源尽力释放且不误报 ready。父 source/generated/PNG/观察在 intent 后或 connect 阶段变化，actual send guard 拒绝。
7. 用 authentic 新 record fixtures 完整接受所有 clips 后 require 返回精确 complete；篡改单个 graph/intent/accepted/history/submission/input/mapping/PNG/观察原文/接受收据/complete 均拒绝。共享基准同字节不同路径仍逐 reference 独立校验。缺失外围 commit 可从确切原记录恢复，已接受媒体不重新编码；原输出遗失无自动推理。
8. schema=1 原 shot IDs、prefix-only mapping、旧审核/explicit acceptance、完成前缀与交付测试保持原行为；新 scene clip 不能被旧 validator 放行。完整新流程仍不调用超分/合成/交付，也不生成正式电影路径/收据。

## Acceptance

任务板五项分别由上述 Tests 1、2/4、2/3、4、5/6/7/8 证明。要求实际替身 HTTP body 和真实逐帧媒体 evidence，不以只有 planning 字典或 mocked hash 的断言代替输入/帧来源。

完成时 prepared-run API 能从完整图片准入生成可观察前缀；观察未齐返回 `awaiting_continuity_review`，父链等待期间其他 scene 可独立推进。有效观察后续作消费父末保留原生帧，准确去掉 child 首帧。全部 clips/实际观察通过才有可重新核验的 schema=2 complete 源片清单；完整原文、样本和总帧覆盖保持不变。

本任务的替身观察用于验证准入结构，不能登记为真实 Wan 视觉一致性已通过。真实重复主体三个画面、至少两段长链的实际播放效果以及最终影片观察按总体方案留在 JIM-08/JIM-06。

## Risks

- 现有 Wan 只有起图约束；固定基准文字和末帧不能保证模型动作/结构不漂移。无有效动态观察或明确失败时阻断后代，本任务不自动返工。
- Comfy 崩溃或历史被清除可能失去原任务证据；本任务宁可保留 submit_unknown，不重新提交。服务只有可核实的自有实例可操作，不能借用无法确认 run 输出目录的监听服务。
- 原生成视频到 source.mp4 的有损编码可改变像素，故 continuation PNG 从 generated 的确切保留 native index 提取；同时绑定 source.mp4 观看版本和 PNG，不能把编码后像素相等作为假设。
- 真实运行耗时、显存、模型权限和画面品质尚未验证。指定帧提取、SHA 与全量解码会增加 I/O，但它们是本阶段来源和观察绑定的必要检查；不要以性能理由改为仅 mtime 或首尾截图验收。
- 未发现需要补充用户选择才能确定的需求。scope、native profile、6 秒上限、观察门槛和返工边界均来自已确认总体方案/任务板及直接依赖；具体代码组织和新增记录结构是本设计确定的实现方案。真实服务/观察结果仍待实施和 JIM-08，不在此虚构。
