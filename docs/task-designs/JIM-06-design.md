# JIM-06 新时间轴合成与成片一致性交付验收

## Goal

把 JIM-05 已完整观察接受的 scene/clip 源片按确切帧映射超分为 1080p，合成保留完整原文配音、字幕、停顿与总帧覆盖的候选片。最终连续影片只有在绑定确切候选、原图/基准和全部动态观察的实际观看结论通过后才允许正式交付。

JIM-05 已先记录 COMPLETED；其最终字节全套为 3206 passed、21 个文件哈希匹配，具体见 `JIM-05-verification.md`。本文是 Order=6 的实施契约，不是 JIM-06 已实现或已验证的声明。

## Scope

包括 prepared-run Python API、独立 schema=2 的逐帧超分事务/完成记录、候选合成、最终观察、交付事务、只读完成前缀验证和阶段内中断恢复。使用原有 RealESRGAN、字幕布局、PCM 拼装和 ffmpeg 编码规则。源片准入、超分、候选与正式输出具有各自明确的完成门槛。

不重新生成图片或 Wan，不修改选图、Bible、scene/clip 预算、原文、PCM 或字幕文本；不增加插帧、转场、变速、循环、冻结、背景音乐或新模型。沿本策略既有 native16/cut、1920×1080、烧录字幕约束；不接通全流程协调/新 CLI，不实现重选/修订/自动返工（JIM-07），不执行真实收费或视觉质量验收（JIM-08）。旧 shot/schema=1 消费者与正式交付规则保持原样。

用户后续澄清：“视频的长度帧不限制，帧率也不变”。因此保留原生 16 fps 和完整时间轴，不增加 30 帧或 200 帧的视频总长度上限。本文的 200 帧仅是续接映射回归样例，不能用于截短实际视频。

## Approach

### 复用与版本边界

`runtime/production_upscale.py` 和 `planning/production_visual_plan.py:plan_production_upscale` 仅接受 shot 和旧帧映射；`runtime/production_composition.py:_contribution_plan` 也会重建 shot 顺序。`runtime/production_completed.py` 强依赖 SDXL/shot/旧 manifest，`production_delivery.py` 的 schema=1 收据允许 human_review=unverified。以上均不能直接接收 scene ID，也不能放宽以适配本任务。

新增独立模块及目录，不把新记录写入旧 `production/upscaled-clips.json`、`composition.json`、`technical-checks.json`、`delivery.json` 或旧 stage checkpoints。`planning/final_review.py` 的旧 requirement/cue/human_full_film 协议保持；本任务新增适配 scene、固定基准和动态链的实际连续影片观察协议。后续 JIM-07 显式按 frozen strategy 分派，不能调用旧 completed-prefix 验证新运行。

复用 `WorkflowTemplate`、`validate_fixed_visual_template(...,'upscale')`、受控 `SceneComfyClient`、`production_comfy` 的纯 graph/queue/history/output 比较、RunLock、PathPolicy、自有 ServiceManager、`write_production_narration`、`plan_subtitle_events/srt_text/ass_text` 和现有媒体核验。旧公共签名、workflow/mapping 文件不改。

### 公共接口及结果

新增接口，frozen/units/timeline 均为同一个已准备运行：

```python
# runtime/production_scene_upscale.py
produce_scene_upscaled_clips(frozen, units, timeline, *, paths, logger,
                            client_factory=None, service_factory=None, lock=None) -> SceneMediaResult
# runtime/production_scene_composition.py
produce_scene_composition(frozen, units, timeline, *, paths, logger, lock=None) -> SceneMediaResult
# runtime/production_scene_delivery.py
consume_scene_final_observation(frozen, units, timeline, observation_path, *, paths, logger, lock=None) -> SceneMediaResult
produce_scene_delivery(frozen, units, timeline, *, paths, logger, lock=None) -> SceneMediaResult
# runtime/scene_media_records.py, all read-only
load_scene_media_progress(frozen, units, timeline) -> dict
require_scene_upscale_acceptance(frozen, units, timeline) -> dict
require_scene_composition(frozen, units, timeline) -> dict
require_scene_final_acceptance(frozen, units, timeline) -> dict
require_scene_delivery(frozen, units, timeline) -> dict
```

写入口自动获取 RunLock；传入时核对同 run 的真实所有权，不释放调用方锁。未知/未准备 run 在赋 run/log 身份及加锁前拒绝。记录、日志、媒体晋升仅在持锁调用线程写入；网络线程只读 guard/I/O。自有服务在 finally 释放，外部服务不借用/停止。清理或释放失败保留主错误及证据，不返回 ready/delivered。client_factory 与 service_factory 签名沿 JIM-05（base_url/request_timeout/ownership_check 和 frozen/paths/logger/lock）。

`scene_media_records.py:SceneMediaResult` 精确字段为 `schema_version/production_strategy/run_id/run_dir/status/active_stage/upscaled_clips/candidate/final_observation_template/delivery_receipt/log_dir/error`。schema=2、strategy=paragraph_jimeng_v1；stage 为 upscale/composition/final_review/delivery。路径为绝对路径或 null；仅通过其准入的已有产物才填值，candidate 是可查看 MP4，upscaled_clips 是超分 complete.json。error 为 null 或精确 kind/message/evidence_paths。

状态/退出码：upscale_ready=0、awaiting_final_review=3、final_review_ready=0、final_review_failed=2、delivered=0、blocked=2、failed=1、interrupted=130。候选技术完成默认 awaiting_final_review；已有完整 passed 接受可返回 final_review_ready。consume 不提交模型、不编码、不自动交付；produce_scene_delivery 才发布输出。未核实等待，明确 failed 保留候选且阻断本版本，修订留给 JIM-07。

只读 progress 精确为 `schema_version/run_id/upscale/composition/final_review/delivery`；四行精确 `status/record/completed_items/total_items/error`，从原证据推导。各行 status 为 pending/running/ready/awaiting_final_review/final_review_failed/blocked/failed/delivered 中与阶段适用者；record 为已验证完成记录的绝对路径或 null，error 沿结果结构。upscale 的 items 是全部保留帧，其余为 0/1。部分合法前缀可返回进度；冲突/损坏拒绝，不靠可变 status 或缺失标记猜完成。四个 require 分别返回确切已存在且重新验证的超分 complete、candidate-commit、final-observation-accepted、最终外部 receipt 字典；只读缺少该阶段门槛即抛 ProductionRefused，不写修复。不得以 progress 的 ready 代替 require 准入。

### 全局准入和记录规范

所有新写入口先加载冻结输入、`load_committed_plan`、`require_complete_image_acceptance` 与 `require_scene_clip_acceptance`；JIM-05 准入继续追溯 JIM-04 原图/参考来源。全部图片/基准/每个父片和叶片过程观察通过前，零超分 POST、零超分服务启动、零候选编码/交付。完整验证 timeline、units 与 frozen script 原文范围、PCM 身份/样本数、原字体和模型戳、冻结工具路径及本次调用的工具 stat 戳、frozen upscale workflow/mapping、空间及已有所有未完成超分事务，后面帧有本地冲突时不得先提交前面帧。现存 FrozenInputs 没有历史工具二进制戳，不能虚构已核对原冻结二进制；工具本次调用前后使用现有 ArtifactStamp 语义核验，原编码身份由保存的命令及媒体证据绑定，不改旧冻结格式。

媒体/原始文件 Artifact 使用 JIM-05 精确 `path/bytes/sha256`，严格正 bytes、64 位小写 SHA；JSON 绑定用 canonical_digest；时间带时区，bool 不充当数字，额外字段拒绝。HTTP 原始 body 唯一允许 bytes=0，沿 HTTP 专用验证。运行内路径经 run_path/PathPolicy，拒绝符号链接/junction/目录逃逸；最终外部输出另按冻结 output_paths 和 output_root 校验，不能套用 run 内路径约束。

新 JSON 先 fsync 同目录临时文件再在锁核验后原子提交，已有最终内容只允许相同复用。媒体沿 JIM-05 准备收据再晋升协议，未登记文件不认作成果；有有效最终收据的字节不重做。媒体只改 mtime 不改变 Artifact 身份，冻结工具/模型仍遵循原 ArtifactStamp 语义。每次公共读取重新完整准入；单次调用内可复用 SHA 绑定的 decode 结果，但每次复用重算字节哈希，无跨调用或仅 mtime 缓存。每次真正 POST/接受观察/输出发布前重核所有捕获的上游字节、JSON 目录清单与模型戳，不能只比较 complete 标志。

超分根 `production/scene-upscale/` 的 inputs.json 精确为 `schema_version/production_strategy/run_id/algorithm/frozen_options_sha256/scene_clips_sha256/image_acceptance_sha256/timeline_sha256/workflow/mapping/model_stamp/parameters`。algorithm=scene_upscale_v1；workflow/mapping 是 Artifact，model_stamp 为 frozen upscale ArtifactStamp；parameters 精确 `model/width/height/method/crop/native_fps/output_fps`，值为 RealESRGAN_x4plus.pth/1920/1080/lanczos/disabled/16/16。所有下游通过 inputs 摘要和各阶段完整上游摘要传递绑定，不能接受只换路径不换关联的清单。

### 原生保留帧到超分的一一映射

新增纯 `planning/scene_media.py:plan_scene_upscale(scene_clips)` 和 `plan_scene_contributions(scene_clips,upscaled,timeline)`。第一项按 JIM-05 clips 顺序及本地零基 k=0..R-1 建帧行，R=budget.retained_frames。行精确为 `frame_id/clip_id/scene_id/retained_frame_index/generated_frame_index/output_frame_index/source`；frame_id=`<clip_id>:frame_<k+1:06d>`，generated_frame_index=frame_mapping.retained_to_generated[k]，output_frame_index=budget.start_frame+k，source 为该 clip.source Artifact。所有输出恰好覆盖 [0,total_frames)，数量等于所有 R 之和；无第二次丢首或裁尾。

实际从 **source.mp4** 提取 R 张 RGB24 PNG（本片零基 k），不是从 generated 的所有 G 张重新超分；generated_frame_index 仅是原生成来源追踪。source 是已观察的保留范围，JIM-05 的有损裁片可能改变像素，不宣称 source 与 generated 解码逐像素相等。200 帧例必须只提交 93+92+15=200 次超分，不能提交 203 次或再次丢掉 child 首帧。

新增 `media/scene_upscale.py:extract_scene_frames(source,target_dir,*,expected_frames,width,height,config,paths,logger,unit_id,timeout=1200)`，返回 `(ordered_artifacts,evidence_paths)`。一次完整顺序 decode，用 map 0:v:0、format=rgb24、fps_mode=passthrough、start_number=1，精确得到 frame_000001.png..frame_R.png，无其他文件、无 fps/scale/裁切滤镜。检查 source 原尺寸/native16/帧数/无音频、所有 PNG 全解码及源 hash 前后不变。验证输入 PNG 与 source 中对应原生帧像素相等；只读重验可一次解码源顺序比较，不能重新写/提取已接受图片。

每 clip 的 extraction.json 精确为 `schema_version/run_id/clip_id/source/frames/recipe/evidence/created_at`；frames 行精确 `retained_frame_index/generated_frame_index/output_frame_index/image`。recipe 为 algorithm=scene_retained_rgb24_v1、parameters 精确 `expected_frames/width/height/filter/start_number/fps_mode`，filter=format=rgb24、start_number=1、fps_mode=passthrough。提取先写唯一 staging 目录，extraction-ready.json 精确为 `schema_version/run_id/clip_id/source/staging_directory/target_directory/staging_frames/target_frames/recipe/evidence/created_at`；两 frames 数组均采用上述帧行，只有 image.path 不同，所有字节/SHA/索引一一相等。target_directory 固定为 clip 目录下 input-frames，同父目录不覆盖 rename 晋升；staging 与 target 同时存在则逐文件都须一致，均缺失或任一冲突拒绝。由该收据重建 extraction.json，created_at 不变，恢复不得混合两次提取目录。

每帧 input PNG 按字节复制至 `comfy/input/<run_id>/scene_upscale/<clip_id>/frame_<k+1:06d>.png`；输出前缀为 `<run_id>/scene_upscale/<clip_id>/frame_<k+1:06d>/attempt_0001`。冻结 upscale_api.json/mapping 固定节点 1.image、5.filename_prefix、5 images 输出，只替换 image/output_prefix；节点 2 RealESRGAN、节点 4 的 1080p/lanczos/crop 和连接不改，不通过改后缀或 ffmpeg 普通拉伸冒充超分。

### 逐帧 Comfy 单次事务

新增 `runtime/scene_upscale_transactions.py`，接口 `recover_or_submit_scene_frame(store,request,graph,*,client,template,ensure_service,logger,timeout) -> dict` 及只读 `validate_scene_frame_submission(store,request,graph,*,template) -> dict | None`。store 为同 run 持锁、固定到当前 frame 目录的新记录存储。成功返回下述完整 submission 字典；只读接口无提交证据时返回 None，证据损坏/冲突抛 ProductionRefused；写接口原 ID 未知抛 SceneSubmitUnknown，明确终止抛带原 terminal 证据的 ProductionRefused，由外层映射 blocked/failed。复用 JIM-05 transport 和纯协议 helper；JIM-05 scene clip 的 request/ID/MP4 validator 保持，不添加任意后缀/ID 宽松分支。

每帧目录 `production/scene-upscale/<clip_id>/frame_<k+1:06d>/`。request.json 精确 `schema_version/production_strategy/run_id/frame_id/clip_id/scene_id/inputs_sha256/clip_sha256/observation_acceptance_sha256/mapping/source/input/input_copy/parameters/graph_sha256`；mapping 是上述纯帧行去 source 后的完整索引绑定，input 为提取原图，input_copy 为复制 PNG。graph.json 保存实际完整图。

intent 精确 `schema_version/run_id/frame_id/request_sha256/graph_sha256/input_sha256/attempt_id/client_id/output_prefix/created_at`，input_sha256 为 input_copy.sha256。accepted 精确 `schema_version/run_id/frame_id/intent_sha256/prompt_id/number/acceptance_evidence`。submission 精确 `schema_version/run_id/frame_id/intent_sha256/accepted_sha256/prompt_id/history_evidence/output`。terminal 精确 `schema_version/run_id/frame_id/intent_sha256/status/evidence/reason`，status=rejected/execution_failed/identity_conflict/invalid_media。与 JIM-05 同义的原始 http/<UUID>.request.json/.body/.response.json 字段只把 clip_id 换成 frame_id。原 UUID、number、完整 graph/client_id、输出 node=5 的 owned prefix 和唯一 PNG 均要核对。

intent 先于 POST；POST 不自动重试。接受响应已保存而 accepted 丢失只从原响应恢复；未知无 ID 只 GET queue/history 唯一找回原图任务。保留失败、graph/output 冲突和 queue/history 正常完成竞态的现有裁决；不能让后来成功抹掉旧冲突。新提交前 object_info.validate_remote；历史恢复不依赖新模板健康成功。request_timeout=冻结 comfy_request，单帧总跟踪预算=upscale_frame，轮询 2 秒受剩余期限约束，恢复可重新分配同任务有限跟踪时间。超分服务作用域复用 JIM-05 自有生命周期规则；不启动 Wan/其他服务。实际发送 guard 重核所有输入/映射、源片观察、上游记录库存、workflow、模型、锁和 deadline，晚到线程不能新发请求或写盘。

模型输出完整解码为 RGB24/1920×1080 PNG，保存原 owned 输出和本阶段字节副本。只有确切输出媒体格式/尺寸错误才持久 invalid_media；本地复制/检查工具临时失败保留原 submission 可恢复，不重新推理。输出准备收据沿 JIM-05 `schema_version/run_id/clip_id/operation/source/staging/target/recipe/evidence/created_at`，在此 schema=2 新域将 clip_id 替换为 frame_id；operation 仅 input_copy/output，recipe 为 identity_png_copy_v1、parameters={}。技术 frame.json 精确 `schema_version/production_strategy/run_id/frame_id/request_sha256/submission_sha256/mapping/input/input_copy/model_output/output/evidence/created_at`。全部帧验收后写 complete.json，精确 `schema_version/production_strategy/run_id/inputs_sha256/scene_clips_sha256/timeline_sha256/total_frames/width/height/fps/frames`；frames 为按 output_frame_index 排序的完整技术 frame.json 行。create 时间来自最后 output 准备收据，外围标志可确定性恢复。

### 完整音画与候选合成

根目录 `production/scene-composition/`。inputs.json 精确 `schema_version/production_strategy/run_id/algorithm/frozen_options_sha256/scene_clips_sha256/upscale_sha256/image_acceptance_sha256/timeline_sha256/units_sha256/pcm/font/settings`；algorithm=scene_composition_v1；pcm 按 timeline.clips 顺序为 `unit_id/text_start/text_end/text/start_sample/end_sample/audio`，audio 为原始 WAV Artifact；font 为原字体 Artifact；settings 精确为 media/subtitles 两项。media 精确 `output_fps/width/height/transition/transition_seconds/burn_subtitles/music`，值 16/1920/1080/cut/0/true/null；subtitles 为 thaw(CompositionSettings()) 的完整既有字段及默认值。令 subtitle_settings=CompositionSettings()，通过 PrivateFont(冻结字体,subtitle_settings.font_name,subtitle_settings.font_size) 测量并复用既有布局，不把媒体字段传入 CompositionSettings。

contributions.json 精确 `schema_version/run_id/inputs_sha256/total_frames/frames`，每帧精确 `output_frame_index/scene_id/clip_id/retained_frame_index/generated_frame_index/upscale_frame_sha256/image`；upscale_frame_sha256 是对应完整 frame.json 的规范摘要，image 等于它的 output。plan_scene_contributions 返回此 frames 数组。直接从两个已验 complete 推导，每 output 唯一，不能以 clip 时长猜帧或套旧 primary_unit 限制。按全局顺序复制为受控 staging 序列 frame_000001.png..frame_N.png，复制后重算 SHA，不用可被改写的硬链接。

复用 write_production_narration 按每个原 PCM 样本逐字节拼装，保留原声区间和规范首尾/句段停顿，末尾只补 timeline.video_padding_samples，总 WAV 精确 N*3000 个 48kHz mono PCM16 样本。新准入还用 SHA 绑定各原 PCM，不能只依赖该旧 helper 的 stat stamp；回读每语音区间比原始 PCM 字节、静音区间全零。字幕从原 timeline/units 经既有布局器产生，不从 scene 摘要或 clip 边界切文本；SRT/ASS 字节必须等于重新推导结果，全部原文范围覆盖。复制冻结字体并核对 SHA。

materialized.json 精确 `schema_version/run_id/inputs_sha256/contributions_sha256/sequence/narration/subtitle/ass/font/subtitle_events/evidence/created_at`；sequence 是有序 Artifact 数组；narration 精确 `audio/samples/speech_samples/silence_samples/padding_samples/clips`，clips 行为 `unit_id/start_sample/end_sample/samples/pcm`；其余三媒体为 Artifact。实际编码沿旧 _encode_args：16fps PNG sequence + narration.wav，subtitles.ass/fontsdir=fonts，libx264/medium/crf18/yuv420p/passthrough、AAC192k/48kHz/mono、faststart，零起点，不用 shortest/tpad/fps/变速掩盖数量不足。通过有期限 run_logged，命令前后验证输入和锁。

materialized 的全部确定性本地文件在同一唯一 attempt 目录完成并核验后，先保存 materialized-ready.json 再提交 materialized.json；两者字段和值完全相同，created_at 来自 ready。缺少两项的部分未接受目录可另建 attempt 重做，已有 ready 必须复用，不能混用目录；sequence 数组中每张图与 contributions 一一相同字节。字体/ASS/音轨位于该 attempt 目录，编码 cwd 为它，所有命令输入均为已核验路径。

编码与 probe 各存独立 commands/<operation>-<UUID>.intent.json，精确 `schema_version/run_id/operation/inputs_sha256/args/cwd/output/created_at`；success.json 精确 `schema_version/run_id/intent_sha256/command/output/evidence/created_at`，command 使用现有 COMMAND_FIELDS，命令总期限 300 秒。encode.output 是唯一 encodes/<UUID>/candidate.mp4 路径；probe.output 是唯一 probe 原始 JSON 路径；success.output 为相应文件 Artifact，stdout/stderr 也在 evidence 中。probe 的真实 stdout 原始字节由调用线程复制到该 JSON；中断时仅从完全匹配的命令完成日志绑定的 stdout 恢复该副本。编码的原输出永久保留；probe 还验证该原输出并绑定其 Artifact，不能只对后来替换的 candidate 检查。在 success 前中断可从唯一完全匹配的 caller-thread command_finished（args/cwd/成功退出/非 timeout/非 interrupted）及实际媒体恢复；无确切成功证据的未接受本地操作才可另建唯一 attempt 重试，保留旧临时文件。有有效 success/准备收据时不能重新编码或改变 created_at。

候选固定为根下 candidate.mp4；对原编码输出完成 probe/视频全解码/PTS/CFR/音频解码检查，再字节复制到唯一 staging，保存 media-ready/candidate.json 后晋升。该准备收据精确 `schema_version/run_id/operation/source/staging/target/recipe/evidence/created_at`，operation=candidate，source 为保留的原编码输出 Artifact，recipe 精确 algorithm=identity_mp4_copy_v1/parameters={}；staging/target 字节与 source 必须一致，晋升规则沿前述媒体规范。精确 N 帧、16fps、H.264/yuv420p/1080p，一个视频和一个 AAC 音频流、48kHz mono、起点 0，视频时长 N/16，音视频差不超过既有 0.1 秒；AAC 有损不与 PCM 逐字节比较，PCM 输入和编码命令独立绑定。candidate-commit.json 精确 `schema_version/production_strategy/run_id/inputs_sha256/contributions_sha256/materialized_sha256/candidate/subtitle/ass/narration/encode_receipt/probe_receipt/technical_checks/created_at`，receipts 为 Artifact、created_at 等于候选准备收据时间；technical_checks 精确 source_text_coverage/audio_samples/frame_mapping/subtitles/final_media，均 passed。只有该技术提交才能产生未验收候选；不在正式 output_paths 写任何文件或旧交付收据。

require_scene_composition 只读重建并核对全部原数据/receipts/实际媒体，不自动补标志。写入口可从确切成功 receipts 恢复丢失的外围标志。候选提交后禁止原地重编码或换文件；改变命令/上游/媒体需 JIM-07 新修订，即使新编码字节偶然相同，也不能沿用旧 composition/observation 身份。

### 最终连续影片的实际观察

新增纯接口 `scene_final_observations.py:build_scene_final_observation_template(frozen,units,timeline,candidate,scene_clips,upscaled,image_acceptance,clip_requests) -> dict` 与 `validate_scene_final_observation(value,expected,*,now) -> dict`。candidate 是已验 candidate-commit，scene_clips/upscaled/image_acceptance 是对应已验原清单，clip_requests 为按 committed clips 顺序的完整已验 request 字典列表；expected 精确为 `{template: 重建模板, created_at: candidate.created_at}`，沿既有 clip 观察协议携带观看时间的可信下界，不向观察原文增加字段。validate 成功返回原观察的深副本，失败抛 ValueError，不写盘。模板保存为 scene-composition/final-observation-template.json；文本为空、检查/结论为 unverified、review_method/reviewer/viewed_at=null。程序不能自动写 passed 或伪造观看。

观察精确字段 `schema_version/production_strategy/run_id/scope/composition_sha256/candidate/subtitle/scene_clips_sha256/upscale_sha256/image_acceptance_sha256/visual_bible_sha256/selected_images/comparison_images/clip_acceptances/playback/review_method/reviewer/viewed_at/full_film_watched/full_audio_listened/subtitle_checked/overall_observation/scene_observations/join_observations/narration_observations/checks/verdict/issues/reason`。scope=scene_final_film；candidate/subtitle 为确切 Artifact；selected_images 是 JIM-05 scenes 的 scene_id/selected_image 行；comparison_images 按 plan.clips 顺序为 clip_id/comparison_images（从对应已验 request 读取）；clip_acceptances 按 plan.clips 为 clip_id/clip_sha256/observation_acceptance_sha256。三个 full_* 为严格 bool，模板为 false；issues 模板为空，join.verdict 模板也为 unverified。整体文本和 reason 必须非空才是可消费观察。

playback 精确 `frame_ranges/sample_ranges`，必须分别为唯一完整区间 [0,N)、[0,N*3000)，以 `start/end` 对象数组表示；三个 full_* 字段必须 true 才允许 passed。review_method=human_video/agent_video，仅实际具备完整视频/音频查看能力者；reviewer 非空，viewed_at 不早于 candidate-commit.created_at、不晚于 now。未具备音视频能力的工具不能通过填写模板变成观察证据。

scene_observations 按完整 scenes 顺序，行精确 `scene_id/start_frame/end_frame/selected_image_sha256/baseline_bindings/identity_observation/appearance_observation/environment_observation/style_observation/motion_observation`；基准绑定等于该 scene 所选原行，五段文本均非空，比较最终影片与固定基准/原图，包括有依据的变装换景。

join_observations 枚举每个相邻 clip 边界（包括有意切镜），行精确 `from_clip_id/to_clip_id/kind/boundary_frame/played_frames/observation/verdict`。kind=continuation 当且仅当后片 parent 是前片，否则 cut；B=boundary_frame=后片 start_frame；played_frames 为精确对象 `{start:max(前片.start_frame,B-16),end:min(后片.end_frame,B+16)}`。至少覆盖两侧末/首贡献帧。observation 必须描述实际动作衔接或计划切镜；续接不能把动作重置说成正常 cut。

narration_observations 按每个原 timeline clip，行精确 `unit_id/text_start/text_end/text/start_sample/end_sample/pcm_sha256/audio_observation/subtitle_observation/semantics_observation/sync_observation`，保留全文和原音频范围，四段文本非空。不能仅审核 scene 摘要或一条总通过；字幕原文与完整旁白、时间覆盖都要比较。

全局 checks 精确 `subject_identity/appearance_structure/color_clothing/environment_space/time_lighting/style/motion_process/continuation_joins/scene_cuts/full_narration/subtitle_text/audio_video_sync/final_quality`；全为 passed 才可 passed。无 continuation/cut 时对应项仍需 overall_observation 说明无适用边界，不自动豁免其他检查。failed 至少一个 failed 且 issues 非空；unverified 无 failed、至少一个 unverified（或 full_* 未齐）。issues 行精确 `check/frames/description`，check 为上述键，frames 为 [0,N) 中非空半开区间对象，description 非空。整体通过还要求所有 join.verdict=passed；failed join 必须反映于对应全局 failed。身份/结构/范围错误直接拒绝，不降级成 unverified。

consume 先验证原始观察的完整身份/结构，再按原始 SHA 保存到 `scene-composition/final-observations/<raw_sha>.json`，保存前后完整复核上游和候选。接受收据 final-observation-accepted.json 精确 `schema_version/run_id/composition_sha256/observation/observation_sha256/accepted_at`；拒绝收据 final-observation-rejected.json 将 accepted_at 换为 rejected_at；observation 为原文 Artifact。passed 才接受，unverified 仅保存等待，failed 永久阻断该候选版本。崩溃只留下 failed 原文时也要阻断并可恢复确切拒绝收据；不得被后续 passed 绕过。重复相同语义幂等，已接受结论不被后续失败提交污染，已接受原文不替换。require_scene_final_acceptance 从所有原始观察/收据和完整上游重新推导接受，不只看 verdict。

### 正式交付和完成前缀

produce_scene_delivery 先 require_scene_final_acceptance，失败/未核实之前零正式目标创建/替换。目标仅使用 frozen.options.output_paths 的 movie/subtitle/receipt。新增 scene 专用输出锁，保持既有 run lock+output lock、PID/start-time/owner token、死进程可核实回收/活进程拒绝和不覆盖规则；不要把 schema=2 事务交给旧 validate_delivery_transaction。

事务存 `production/scene-delivery/transaction.json`，精确 `schema_version/production_strategy/run_id/transaction_id/created_at/updated_at/status/lock_record/composition_sha256/acceptance_sha256/sources/output_paths/operations/receipt`；sources 精确 candidate/subtitle 为 Artifact；operations 为 movie/subtitle/receipt，各行精确 `status/temp_path/file_id/temp/output/archives`，status=pending/prepared/published，temp/output 为 Artifact 或 null，file_id 为现有 file_identity 返回的精确 device/inode 对象或 null，archives 是自有中断临时文件的 Artifact 数组。tx status=publishing/completed。仅事务进度可原子更新；completed 严格不可改。输出锁记录精确 owner/intent_path/lock_path，owner 精确 schema_version/production_strategy/run_id/pid/process_started_at/token/target_movie，schema=2。

每次临时尝试先保存不可变 `scene-delivery/temp-attempts/<UUID>.json`，精确 `schema_version/run_id/transaction_id/role/temp_path/source/created_at`；source 对 movie/subtitle 是 Artifact，对 receipt 是最终收据对象的规范摘要。随后在目标同目录排他创建唯一 temp，流式复制并 fsync，核对源前后 SHA 和临时 SHA，持久记录 file_id/准备身份，再通过不覆盖 rename 晋升。断在排他创建后、file_id 落盘前的未知临时文件保留原位及原意图，不晋升/删除；可为同源另建唯一尝试。只有 file_id 已核实的本次中断临时文件可加入 archives。目标已存在仅在原事务精确 file_id+SHA 证明自有发布时复用；同字节但无原所有权也拒绝。断在 rename 后事务前用原 temp file_id 在 target 的相同所有权恢复，不猜同名/最新文件。外部目标或源变化保留证据并停止，不能删除他人目标。

每次媒体晋升和最后 receipt 前重验原观察、候选、原文/PCM、全部图像/动态接受和锁。最终收据精确 `schema_version/production_strategy/run_id/transaction_id/delivered_at/composition_sha256/final_observation_acceptance_sha256/scene_clips_sha256/image_acceptance_sha256/movie/subtitle/media/technical_checks/actual_final_video_consistency/full_narration/subtitles`；movie/subtitle 为发布后外部 Artifact，media 精确 width/height/fps/frames/audio_sample_rate/audio_channels，后三状态均 passed。不得用 human_review=unverified 的旧收据冒充新正式交付。

receipt 最后按同样不覆盖协议发布，媒体字节必须与被观察候选及 SRT 完全相等，不再次编码。事务 completed 仅在三个输出均读回一致后记录。正式收据不能包含自身 SHA；事务 operations.receipt 绑定实际收据文件 Artifact。交付中断可留下本次自有部分输出并恢复，未完成不报告 delivered。完成重放只读验证原始全部证据、输出字节/所有权，不启动服务、POST、提取、复制或编码；失去原证明时拒绝，不能修饰旧接受/完成标志掩盖。

新增 `runtime/scene_completed.py:validate_scene_completed_prefix(frozen,units,timeline)`，按上述四个 require 顺序验证已有完整阶段，返回只读 progress；不得经旧 ProductionState/ManifestStore 的 shot stage 标成完成。服务 manifest 仍仅保存自有服务事实。JIM-07 以后调用本接口分派，不在本项修改 production.py 协调器。

## Files

- 新建 `planning/scene_media.py`：保留帧超分计划、全局贡献映射。
- 新建 `media/scene_upscale.py`：真实批量保留帧提取与原生像素核验；必要的共用只读 decode helper 可加入 `media/frames.py`，旧入口不变。
- 新建 `runtime/scene_upscale_transactions.py`、`production_scene_upscale.py`：独立 PNG once-only 事务及持锁超分。
- 新建 `runtime/scene_media_records.py`：精确记录、Artifact/准备收据、progress 和四项只读准入；可分私有 helper 文件控制单文件体积，公共契约不变。
- 新建 `runtime/production_scene_composition.py`、`scene_final_observations.py`、`production_scene_delivery.py`、`scene_completed.py`：完整候选、实际影片观察、不覆盖交付与完成前缀。
- 如提取 ServiceManager 作用域到 `runtime/scene_media_service.py`，必须保持 JIM-05 原签名与自有服务/有限健康/清理错误语义；不放宽旧 Comfy 或 manifest validator。
- 新建 `tests/unit/test_scene_media.py`、`test_scene_upscale_transactions.py`、`test_scene_media_records.py`、`test_scene_final_observations.py`；`tests/integration/test_scene_media_flow.py`、`test_scene_media_recovery.py` 和 `tests/scene_media_helpers.py`。复用 authentic JIM-05 fixtures，不能靠伪造 complete 绕过准入。
- 更新 `docs/jimeng-candidates.md` 的 prepared-run 超分、候选、完整观看、交付入口及等待/失败说明；完成时新增 JIM-06-verification.md 并更新任务板。旧文档命令不能把 JIM-07 尚未接通的全流程写成可用。

## Tests

第一实施动作：在 `tests/unit/test_scene_media.py` 建 `test_200_retained_frames_upscale_once_without_second_head_drop`，使用既有 200 帧预算和真实 JIM-05 mapping 调用尚未实现的新纯 API；断言 200 行、每 clip 为 93/92/15、第三片 generated 索引仅 1..15、global 0..199、child retained 0 映到 generated 1、无第二次去头/补尾。先观察缺接口 RED，再实现纯计划，不能修改上游预算。

计划命令（本设计尚未创建/运行这些新测试；预期最终全部退出 0）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-06-tests'
& $VideoAiPython -B -m pytest tests/unit/test_scene_media.py -k test_200_retained_frames_upscale_once_without_second_head_drop -q --tb=short
& $VideoAiPython -B -m pytest tests/unit/test_scene_media.py tests/unit/test_scene_upscale_transactions.py tests/unit/test_scene_media_records.py tests/unit/test_scene_final_observations.py tests/integration/test_scene_media_flow.py tests/integration/test_scene_media_recovery.py -q --tb=short
& $VideoAiPython -B -m pytest tests/unit/test_scene_clip_continuation.py tests/unit/test_scene_clip_records.py tests/unit/test_scene_clip_observations.py tests/unit/test_scene_comfy.py tests/unit/test_scene_comfy_transactions.py tests/unit/test_scene_clip_runtime_recovery.py tests/integration/test_scene_clip_generation.py tests/integration/test_scene_clip_local_failure.py tests/unit/test_production_upscale.py tests/unit/test_production_upscale_plan.py tests/unit/test_production_upscale_records.py tests/integration/test_production_upscale_recovery.py tests/unit/test_production_composition.py tests/unit/test_production_composition_records.py tests/unit/test_production_delivery.py tests/unit/test_production_delivery_records.py tests/integration/test_production_delivery_recovery.py tests/unit/test_final_review.py tests/unit/test_pipeline_speech_final_review.py tests/integration/test_make_video_recovery_contract.py -q --tb=short
& $VideoAiPython -B -m pytest -q --tb=short
```

上述历史测试路径已按当前仓库核对存在。全部串行、Python -B、临时/日志 D:/VideoSi；保存真实计数/退出码、验证文件 SHA，不能把未运行或替身观察当真实品质通过。

场景：

1. authentic 三 scene、多句共画面、200 帧长链以及非整帧尾样本；源片/叶片缺观察时零服务/POST/编码。实际 HTTP graph、原生提取像素、200 个唯一 frame ID/提交及 200 个贡献帧；fast/quality 输入各自核验，最终均 1080p。1 帧 clip、非零 scene 起点、边界帧、布尔/额外字段拒绝。
2. 真实 PCM 拼装逐样本比对，所有规范静音零值，字幕完整原文/SRT/ASS 字节与既有布局一致，烧录字体真实使用；真实 candidate 全 decode、PTS/CFR、帧数/时长/音频规格核验。不得仅 mock probe/样本数字。
3. 候选技术通过但未观察时有可查看路径和 unverified 模板，正式 output_paths/receipt 均不存在。少播中段、只看截图、错 candidate/SRT/基准/父链、缺 unit 原文/观察文本、伪造时间、将 continuation 说成 cut 全部拒绝。failed/unverified 均不交付；正确 authored 替身观察才进入 final_review_ready，仍需显式交付 API。
4. 确切 passed 后发布电影/SRT SHA 与观察版本相等、receipt 最后、schema=2 全 passed。改 candidate 字节、同字节新 composition/encode 身份、PCM、subtitle、原图、动态观察、单帧输出均使观察/交付失效。交付前/实际复制/rename 前更改来源或失锁要拒绝；预存相同字节但非 owned 目标不能接管。
5. POST/原响应/accepted/history、提取准备/晋升、每帧输出/complete、materialized、编码成功/receipt、candidate commit、观察原文/accepted/rejected、输出 temp/rename/receipt/completed 逐边界中断；同帧 POST 一次，恢复原 UUID/graph/PNG，已接受本地媒体零再编码/提取。失败原文没 receipt 仍阻断，已接受观察不被后来失败污染。
6. 队列完成竞态、旧失败/冲突不可抹除、原任务未知/超时、错误输出 node/prefix/格式/尺寸、临时本地工具失败、迟到线程、caller-thread 写入、服务/锁清理失败分别覆盖；没有新 Wan/出图/邮件，未知提交不自动补发。
7. 完成前缀两次只读重放不启动服务/POST/编码/提取/复制，不写缺失 receipt；丢外围 commit 的写入口只从确切准备/命令证据补齐。无原输出或 conflicting 记录拒绝。旧 shot ID、mapping、schema=1 审核/交付、完成前缀、CLI 恢复全部维持旧行为。

## Acceptance

1. 多句共画面和 200 帧续接按原 mapping 恰好输出全部帧；完整 PCM、字幕、首尾和停顿逐样本/文本/真实媒体检查通过，无再次去头或静默补时。
2. 最终实际观察精确绑定候选 MP4/SRT、composition、所有选图/基准和动态接受；完整连续播放、逐 scene/join/unit 文本及 checks 齐备才接受。未核实或不一致只有候选，没有新策略正式交付收据。
3. 已接受版本按字节复制到冻结正式路径；媒体/编码身份变化使旧观察失效，不能重新编码后沿用接受。输出事务中断可核实恢复、不覆盖无关文件，收据最后且只在全部门槛通过时存在。
4. 新记录及 completed-prefix 独立 schema=2；现有 shot/schema=1 回归通过，没有放宽旧 validator、替换旧历史审核或偷偷迁移运行。
5. prepared-run APIs 和文档清楚区分 upscale_ready、awaiting_final_review、final_review_ready、final_review_failed 与 delivered；候选技术成功不能冒充观看/正式交付。阶段内 once-only 和中断恢复在本项证明，不推迟到 JIM-07。

## Risks

- 超分会改变画面细节，源片观察不能替代最终连续影片观察；真实模型品质/显存及实际观看留给 JIM-08。
- 严格全媒体核验及每帧超分成本较高；仅允许单次调用 SHA 绑定缓存/顺序解码，不能改为 stat-only 或跳过中间帧。
- 三个外部输出无法一次原子发布，因此必须有 owned 临时文件、文件 ID、逐操作记录和最后收据；中断部分输出不能标成 delivered。
- Comfy 原历史/输出丢失时宁可 blocked，不重复推理。最终 failed 候选只能走未来新修订，不能原地翻案。
- 没有尚待用户选择的功能需求；接口/记录是本任务确定的实施方式，scope、规格、完整旁白及实际观察门槛来自已确认总体方案和任务板。真实账号/播放结论不是本设计中虚构的准备证据。
