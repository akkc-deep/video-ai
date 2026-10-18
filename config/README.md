# 配置样例

即梦官方候选图片接入见 [jimeng.example.json](jimeng.example.json) 和 [候选图片说明](../docs/jimeng-candidates.md)。该新策略目前提供 JIM-01 候选 Python API，段落规划/邮件/视频协调器仍由后续任务实现；旧配置缺省行为保留。

## make-video 自动制作配置

普通制作入口 `make-video --text TEXT` 或 `make-video --script PATH` 默认读取 `D:/VideoSi/projects/video-ai/config/production.json`，也可用 `--config PATH` 指定现有配置。配置复用已安装 Ollama/qwen3:8b、GPT-SoVITS v2/CPU/非半精度声音、SDXL、Wan、RealESRGAN_x4plus 和 FFmpeg；无需新增模型或审查文件。默认配置路径属于运行环境，源码中的 `production.example.json` 仅为配置样例。

首版支持单版 fast（768×432）或 quality（1280×720）源镜头，最终固定 1920×1080/native16、硬切、烧录字幕、无背景音乐。`media.fps` 非 16、最终尺寸非 1920×1080、transition 非 cut、burn_subtitles 为 false 或 music 非 null 会在预检指出确切字段并拒绝，不自动改配置。旧流程支持范围见后文。

文案原始字节、raw/resolved 配置、声音和工作流在新 run 中冻结；正常输出使用 `output_root`，所有运行日志/缓存/输入/临时媒体遵守 D 盘路径策略。`--run-dir` 恢复默认消费冻结设置，显式选项必须与原设置一致；调用者修改原文文件不会改动已有 run。工作流与模型身份变化、外来服务/锁或同名输出会给出实际诊断。

现有 `timeouts` 控制单模型请求/服务启动/单帧等待，媒体命令最多 300 秒，无整条管线总期限。`--cpu-planner` 使用既有 CPU 规划选项及至少 1800 秒的单次 Ollama 请求期限，不改变 GPT-SoVITS CPU-v2 路线。默认停顿及可选 `media.timeline` 见下文；保留完整 PCM 样本与原文字幕，实际语义、发音和动作同步仍为未人工验证。

## 管线作者输入（任务13）

作者输入独立于 production / voice 配置。所有身份均为完整 `FileIdentity`：`path`（规范绝对路径）、`bytes`、`mtime_ns`、`sha256`、`verified_at`（有时区且非未来）。JSON拒绝重复键、未知字段、非有限数字和 bool 冒充整数。记录必须根据当前实际文件和实际审查填写，测试 fixture 不可作为生产接受。

新 `run --unit-review PATH` 的精确顶层字段为 `schema_version=1`、`script_identity`、`review_method`（human_text 或 agent_source）、`reviewer`、`reviewed_at`、`verdict`、`reason`、`spans`。每个 span 精确包含 `unit_id/kind/text_start/text_end/text/single_visual_semantics/verdict/reason/context_sources/resolved_references`。有序跨度完整覆盖原文且不改字；speech 的单一画面语义必须经过实际审查并为 true / passed，skip 只允许不可发声的空白或纯标点，unit_id 与 single_visual_semantics 为 null。允许在原分段内进一步按短语细分，禁止合并需要切换画面的语义。上下文和指代沿用带原文来源的 semantic facts 格式。

`resume --reviews PATH` 索引必须位于本run `logs/pipeline`，精确字段 `schema_version=1/run_id/created_at/entries`。`entries` 为有序 role → FileIdentity；允许的 role 为 `voice_acceptance/timing/visual_contract/storyboard/start_images/source_clips/upscale/final_review/full_film_acceptance`。静态图、源视频、超分文件分别位于 `logs/start-images/semantic-review.json`、`logs/source-clips/semantic-review.json`、`logs/upscale/semantic-review.json`；分镜记录在 `logs/storyboard`，最终记录在 `logs/validation`。索引只传递作者输入，不产生审查结论。

新的声音接受精确字段为 `schema_version=1/run_id/segments_identity/reference_identity/preview_identity/audio_identities/review_method/reviewer/reviewed_at/listened/accepted/user_statement`。method 只能 human_audio，两个 bool 必须严格 true；参考重放和完整预览须绑定当前PCM，每个有序 audio 条目精确包含 `unit_id/text/raw/pcm/samples` 并覆盖全部 speech。消费后保存独立接受收据，不改旧 voice-listening.json 的 false；部分复用与新音频混合后需要新的完整试听。

`resume --changes PATH` 精确字段为 `schema_version=1/base_run_id/base_manifest_snapshot_identity/created_at/reason/script_identity/unit_review_identity/config_identity/shot_changes`。base snapshot 是本run `logs/pipeline/manifest-*.json` 中独占保存的原manifest；script / unit_review 的 null 表示保持，config 必须绑定当前配置。每条 shot_changes 精确包含 `shot_id/image_prompt/video_prompt/reason`，两个 prompt 可为 null，但至少一项非空，shot ID 必须已存在且不重复。只能修改提示词，不能改原文、unit ID、画面要求、数量、否定、指代或时序绑定；新提示词会先停在新的分镜原意审查草稿。

原文、声音、模型或制作配置的明确变更按依赖失效；只改字幕样式、音乐或编码时保留可验证的原音频及生成镜头。所有恢复和返修副本保留原来源、提交与审查版本；任何最终候选或观察集合变化都需要新的最终审查及整片接受。详细字段及故障规则以 `D:/VideoSi/docs/task-designs/VAI-13-design.md` 为准。

明确修订后的 SDXL、Wan 和超分模型由各阶段投影到本run独占的 Comfy 模型目录，并通过同卷硬链接绑定授权文件。启动命令指定该目录并禁用第三方 custom nodes；绑定收据保留模型、授权、配置和实际加载器代码身份，提交及后续消费都重新检查。跨卷链接、额外模型路径配置或目录中的未知别名会拒绝执行。服务地址或操作期限修订同样须有当前配置的作者授权；旧执行证据按原冻结配置重验，新提交使用新配置。

production.example.json 使用批准的新 D:/VideoSi 目标，引用同目录的声音样例和源码工作流模板。样例可直接加载；工具、权重、参考音频与字体未迁入时，doctor 必须报告缺失并返回 1。

实际配置存于 D:/VideoSi/projects/video-ai/config。复制样例到该目录后，应将 workflows 中的路径改为源码模板的绝对路径，voice_config 改为实际声音 JSON。相对路径以各自 JSON 文件的目录解析；命令行路径以调用目录解析。实际素材位于项目 inputs，正式输出位于 D:/VideoSi/output/video-ai。

声音样例表达任务1盘点的当前 custom：v2 权重、CPU、非半精度、原参考转写与 SHA256。历史界面的 v3/v2ProPlus 选择未混入当前配置。模型实际加载及试听仍需后续验收。

默认 fast=768×432、16fps、1080p、硬切、烧录字幕，无背景音乐；快速档速度与画质仍待实测。quality=1280×720；24fps 明确标记为从原生16fps转换。doctor 检查本地文件及能力枚举，不能证明完整制作空间、推理、声音、NVENC 编码或字幕渲染已通过。
# 时间轴设置（任务6）

可选 `media.timeline` 保存 `sentence_pause_seconds`（默认0.8）、`paragraph_pause_seconds`（2）、`opening_seconds`（2）、`closing_seconds`（3）。对象或字段省略均使用默认；值必须为有限非负数字，允许0，拒绝null/bool/未知键。参数按Decimal half-up转为48kHz整数样本，并随时间轴保存有效值；旧配置及旧manifest无需迁移。

单换行、CRLF及多个空行仅加一次段停顿，替代句停顿。逗号不额外插停顿，最后单元之后只有片尾留白。保留PCM内部静音。首尾静音仍须由后续镜头覆盖。输出16fps为默认；24fps明确为native16普通转换。尾部不足一帧的padding由后续合成补静音，不拉伸或裁切配音。
# 合成样式设置

`composition.example.json`是任务11独立的可选`--settings`文件。省略文件或对象字段使用同样默认：Microsoft YaHei/54px、margin64、outline2、音乐增益0.12、首尾淡化0.5秒、循环交叠0.05秒。拒绝未知/重复字段、bool充数、null、非有限数和ASS控制字符。字体文件与音乐来源由主配置media.font_file/media.music固定；设置文件不能更换来源。全有效值及设置文件身份写入composition.json，不扩展或修改历史冻结ProjectConfig。
# 最终审查和人工接受（任务12）

这类文件是具体run的作者证据，不是production配置。所有作者文件必须独占保存在该run的`logs/validation`，不回写历史review；程序没有自动填写passed的入口。完整字段定义以`D:/VideoSi/docs/task-designs/VAI-12-design.md`为准，拒绝未知/缺少字段、重复JSON键、非有限数值、bool冒充整数和无时区/未来时间。

- `final-review.json`绑定candidate-validation、composition、candidate、subtitle、script_copy、timeline的完整FileIdentity。method为human_video或agent_video，entries严格按candidate.requirement_bindings覆盖所有primary和quantization_edge_review；旧actual_artifact改名upscaled_artifact，新actual_artifact为最终candidate。新增candidate_sample_ranges由帧范围×48000/fps推导；text_semantics/video_semantics/motion/sync/quality/continuity六个`_verdict`及global_verdict必须全部passed。
- 每条review引用独立连续观察JSON（允许一个文件多条关联），绑定同一candidate和作者/method/时间。观察保存完整关联、与贡献范围完全相等的playback_frame_ranges/playback_sample_ranges、起点/过程/终点及声音/画质/连续性描述。sync_observation明确requires_action_cue、action_cue_ids、onset_observation、interval_observation、reason；内部必须精确发生的动作需要对应action cue。提示词、起始图或三个静帧不能充当动作观看证据。
- cue_entries有序覆盖所有boundary，后接按要求/样本排序的action；绑定原PCM/timeline/candidate，保存绝对audio_sample、不确定样本数及半开actual_change_frames。独立cue观察method只能human_audio_video或agent_audio_video，full_interval_played=true，并说明真实发声/变化与保守误差来源。最坏误差使用整数计算，不能超过48000这个一帧分子；fade须包含两侧真实可见变化。
- `full-film-acceptance.json`的method必须human_full_film；full_film_watched/full_audio_listened/subtitle_checked严格true，verdict=passed，非空reviewer/reason，reviewed_at不早于任何观察。绑定final_review_identity，并在review_collection_identities按规范run相对路径精确列出final review及全部观察的身份，不遗漏或增加。FileIdentity固定path/bytes/mtime_ns/sha256/verified_at；发布重新核对当前字节及mtime。

作者应以实际当前报告的完整关联和重新读取的身份制作证据，不能拿示例或测试记录当真实接受。自动报告的最终unverified字段保持原样；后来的publication报告独立保存最终通过结论。仅有旧声音试听、源片接受、超分review或agent_video审查，仍不能正式发布。
