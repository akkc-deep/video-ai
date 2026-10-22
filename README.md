# video-ai

## 即梦段落视频：邮件选图、连续观察与发布

`paragraph_jimeng_v1` 已接通官方候选图片、固定基准参考、QQ 邮件选图、Wan 连续片段、逐帧 RealESRGAN 超分和成片。每批图片、每个动态片段及最终影片都需实际查看并提交观察；最终观察通过后显式 `--publish` 才正式交付。完整操作和故障恢复见 [候选图片说明](docs/jimeng-candidates.md)，配置字段见 [配置说明](config/README.md)。

先依据 [jimeng.example.json](config/jimeng.example.json) 准备自己的运行配置，保留已确认的声音、工具、权重及工作流绝对路径，并设置 `production_strategy=paragraph_jimeng_v1`。样例中的 `jimeng_t2i_v40` 仅演示参数，不代表已选择或验证该账号模型。关联画面还需要经核验的参考能力档案和已有 TOS 桶；样例留空的参考设置会返回配置等待。

AK/SK 和 QQ SMTP 授权码只通过运行进程的环境变量提供。样例变量名为 `VIDEO_AI_VOLC_ACCESS_KEY`、`VIDEO_AI_VOLC_SECRET_KEY`、`VIDEO_AI_SMTP_AUTH_CODE`；QQ 发件及收件均为 `318575094@qq.com`，SSL 465。配置只存变量名。将完整 UTF-8 文案保存为独立文件后启动：

```powershell
.\scripts\start_windows.ps1 make-video --config D:/VideoSi/projects/video-ai/config/jimeng-acceptance.json --script D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance.txt --json
```

上述两个文件须先由使用者准备。首次调用可能已经生成基准候选并发送邮件。收到结果后，以返回的实际 `run_dir` 续作；选择和观察文件均按返回的模板、身份及路径填写。

```powershell
$sceneRun = 'D:/VideoSi/projects/video-ai/runs/<返回的实际运行编号>'
# 查看本批图片后，提交自己的选择文件；每批重复处理。
.\scripts\start_windows.ps1 make-video --run-dir $sceneRun --image-selection D:/VideoSi/projects/video-ai/inputs/selection.json --json
.\scripts\start_windows.ps1 make-video --run-dir $sceneRun --json
# 每片完整连续播放后提交观察，普通续作才生成后继片段。
.\scripts\start_windows.ps1 make-video --run-dir $sceneRun --clip-observation D:/VideoSi/projects/video-ai/inputs/clip-observation.json --json
.\scripts\start_windows.ps1 make-video --run-dir $sceneRun --json
# 候选整片观看、试听并核对字幕后，提交最终观察。
.\scripts\start_windows.ps1 make-video --run-dir $sceneRun --final-observation D:/VideoSi/projects/video-ai/inputs/final-observation.json --json
# 只有返回 final_review_ready 后执行。
.\scripts\start_windows.ps1 make-video --run-dir $sceneRun --publish --json
```

选择及观察命令只消费输入；普通续作推进生成。图片编号选择还须配合完整的整组一致性观察；静帧不能代替动态观看。`failed/unverified` 结论保留问题，不会正式发布。输出保留完整原文、PCM、字幕、原生 16 fps 和完整时长，最终为 1920×1080、硬切；不限制视频总帧数。

| 状态 | 操作 |
| --- | --- |
| `awaiting_image_model_configuration` | 补齐参考模型、真实能力档案和 TOS 设置，通过 `--reference-settings PATH` 续作 |
| `awaiting_image_selection` | 查看实际邮件及图片，填写返回的选择和整组观察模板 |
| `email_delivery_unknown` | 核对原 Message-ID；需要重发时按说明显式 `--retry-email PATH` |
| `awaiting_continuity_review` | 完整连续播放片段，对照固定基准，提交 `--clip-observation PATH` |
| `awaiting_final_review` | 完整观看候选、试听旁白并核对字幕，提交 `--final-observation PATH` |
| `final_review_ready` | 显式 `--publish` |
| `delivered` | 使用返回收据核验的 MP4/SRT 路径；同 run 完成续作及重复 publish 只读核验 |

等待退出码为 3；阶段 accepted/ready 或 delivered 为 0，正式完成以 `delivered` 及有效收据为准；blocked/final_review_failed 为 2，failed 为 1，中断为 130。SMTP 接受只证明服务器接受，实际 QQ 收信需使用者确认。未知图片/Wan 提交仅恢复原任务，不自动补单。

换模型、重选基准或重做父片使用 `--revision PATH` 建立独立冻结运行，格式见 [修订说明](docs/jimeng-candidates.md#显式重发与修订)。`revision_ready` 只准备新运行；普通续作新 run 才推进。不原地编辑旧 run 配置或接受记录。省略 `production_strategy` 的配置仍使用下述历史策略。

## 带画面核验的自动制作（历史默认策略）

在 PowerShell 中进入 `D:/code/py/video-ai`，直接提供文案：

```powershell
.\scripts\start_windows.ps1 make-video --text '晨光照亮平静的湖面。一只白鸟从湖边起飞。'
```

也可以将文案保存为 UTF-8（允许 BOM）的文件，使用默认配置制作：

```powershell
.\scripts\start_windows.ps1 make-video --script D:/VideoSi/projects/video-ai/inputs/my-script.txt
```

默认配置为 `D:/VideoSi/projects/video-ai/config/production.json`，复用已安装的声音、模型和工作流。程序自动完成无损语义分段、GPT-SoVITS 配音、时间轴、分镜和 SDXL 起始图；提交任何新 Wan 批量请求前，必须实际查看起始图并对照原文。缺少审核时停止于 `source_clips`，保存 `production/visual-review-required.json`，其中逐镜列出实际 PNG 路径、SHA256 和完整原文要求。文件、尺寸和帧数通过不会生成视觉通过结论。

实际查看全部所列图像后，由审查者提供 `production/visual-review.json`：字段严格为 `schema_version: 1`、`review_method`（`human_image` 或 `agent_image`）、非空 `reviewer`、`viewed_images: true`、`verdict: "passed"`、实际观察依据 `reason` 和原样复制的 `binding`。失败或未核实不得填写 passed。程序保存独立 accepted 回执，生成报告及检查点绑定两份审核文件，图片、分镜或回执改变将拒绝续作。审核准入后才制作 Wan 动态镜头、逐帧 AI 超分、原文旁白与中文字幕合成；静态审核不等于视频语义或整片质量通过。

旁白和字幕始终使用你提供的完整原文。新运行使用 `model_visual_v2`：原文事实由冻结 schema 恢复作为证据，模型只生成最多 160 字符的英文场景和动作描述。SDXL/Wan 请求不包含中文事实锚点、实体 ID 或 style/color_palette 字段标签；显式旅行者场景使用同一套白色碟形天线、金色机体、细杆和 RTG 外观说明。模型获得有顺序的邻近原文、明确指代来源、前镜头英文场景及全片实体来源；抽象旁白承接有依据的场景，不能字面化为无关物体。SDXL 新起始图采用 1280×720，Wan fast 仍为 768×432/native16。采样器、步数和模型不变。提示词和尺寸仍不能保证探测器科学外观或跨镜头几何一致，必须查看实际画面。

独立的真实模型样片入口为 `scripts/preview_visuals.py`，先 dot-source `scripts/bootstrap.ps1` 并调用 `Initialize-VideoAiEnvironment`，使用 `$VideoAiPython -B` 执行。`--phase plan --source-run PATH --shot-ids shot_0001,shot_0054,shot_0067` 只读旧运行并建立新预览目录；随后分别执行 `--phase images --run-dir NEW_RUN` 和 `--phase videos --run-dir NEW_RUN`。限制 3～5 个镜头，无批量、交付或自动恢复，所有媒体与请求独占保存。视频前要求 `samples/image-observation.json` 绑定逐图实际观察；样片允许保留 failed/unverified 观察用于问题展示，这种 `preview_only` 记录不能通过正式制作审核。历史证据不覆盖。

已有运行继续按其保存的原始分镜请求恢复。新分镜请求将实体 ID 限制为冻结实体表中的值；未注册的原文主体仍保留在事实和画面描述中，实体引用可为 `[]`。旧批次的初始和纠错响应若均已完整保存、核验后仍因未知实体 ID 失败，恢复会保留旧证据，并用独立 `entityrepair` 请求进行一次有明确约束的修复；再次恢复只核对这次修复的原响应。其他失败和未知提交不自动重发。要应用精简规则，请使用原文启动新运行。

默认交付单版 1920×1080、原生 16fps、H264/yuv420p、AAC 48kHz 单声道，硬切、烧录字幕和独立 UTF-8 SRT，无背景音乐。所有原文范围及完整旁白样本保留，字幕按原文排版。正式文件默认位于 `D:/VideoSi/output/video-ai/<run_id>.mp4`、同名 `.srt` 和 `.delivery.json`。自动交付收据记录技术检查；人工观感、画面语义、主体一致性、发音和实际动作同步仍未人工验收。

指定输出及读取机器结果：

```powershell
.\scripts\start_windows.ps1 make-video --script D:/VideoSi/projects/video-ai/inputs/my-script.txt --output D:/VideoSi/output/video-ai/lake.mp4 --json
```

`--output` 必须位于配置的正式输出根内；同 stem 派生 `lake.srt` 和 `lake.delivery.json`，已有外来文件不会被覆盖。`--json` 的 stdout 只有一个最终 JSON 对象，包含 `run_dir`、状态、三条正式路径、技术检查和错误；进度及服务日志写 stderr 和 D 盘日志。普通模式显示阶段、镜头、超分 frame/total 和耗时，完成后显示正式路径。耗时从本次生产 logger 创建起算，不包含入口预检。

失败或中断时保留 run 和已完成产物，按输出的实际 run 路径续作：

```powershell
.\scripts\start_windows.ps1 make-video --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --json
```

将 `<run_id>` 替换为结果中的实际编号。恢复省略选项时使用冻结设置；显式 `--config`、`--output` 或 `--cpu-planner` 必须与原 run 相同。已完成 run 返回相同交付；完整前缀不再次请求模型或编码。已接受的 Comfy 请求依据原 ID 或唯一 client+graph 恢复；未知 TTS/Ollama/Comfy 提交会阻塞并保留诊断。遇到这种诊断先查看 `error.evidence_paths` 和实际服务/请求日志，不能靠重复命令重发未知请求。另用原文启动会创建独立新 run，并重新制作。

退出码为 0（全部交付且状态一致）、1（模型、媒体或 I/O 失败）、2（输入、配置、路径、锁、外来服务或不安全恢复被拒绝）、130（中断）。端口冲突指出实际 URL，程序只停止本次真正拥有的服务。每次模型请求及媒体命令有有限期限，整条管线没有总超时；Wan 和逐帧 AI 超分可能等待数小时，时长随文案增长。空间不足会明确失败并保留证据。

`make-video` 是自动制作入口；下文旧 `run`、`resume` 和 `.publication.json` 流程继续要求其真实审查证据。自动 `.delivery.json` 不替代旧人工接受。恢复以文件大小/修改时间 stamp 识别变化，不提供媒体全文 SHA 级完整性保证。

任务13提供固定阶段顺序的 `run` / `resume` 管线。新制作先检查原文单一画面语义分段，再预检和配音；遇到真实作者审查缺项就停止，完成自动检查后默认停在 staging。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 run --config D:/VideoSi/projects/video-ai/config/production.json --script D:/VideoSi/projects/video-ai/inputs/script.txt --unit-review D:/VideoSi/projects/video-ai/inputs/unit-review.json --json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 resume --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --reviews D:/VideoSi/projects/video-ai/runs/<run_id>/logs/pipeline/reviews.json --json
```

`run` 可选 `--image-inputs`、`--settings`、`--output` 和 `--cpu-planner`。`resume` 可用 `--changes PATH` 显式返修，或 `--retry-failed` 对确切失败请求授权一次新尝试；未知/仍运行的请求只核对原提交，不能重发。返修及部分恢复建立独立 child run，完成前缀保持真实原来源，原运行的终态、提交和文件保留。只改一个 video_prompt 时，仅该镜头及其超分重新生成，新的分镜原意与连续视频仍须重新审查。配置或任意来源漂移不能靠刷新 hash 获得复用许可。

声音接受、时刻标注、分镜文本、静态图、源视频与超分连续视频各有独立检查点。`waiting_for` 与 `logs/pipeline/result-*.json` 列出缺项及规范作者路径；已完整生成的 running 草稿只调用 finalize。作者记录须绑定当前确切文件身份，程序不替作者填写 passed 或接受。`unit-review`、`reviews`、声音接受和 `changes` 的字段见 [config/README.md](config/README.md)，完整契约为 `D:/VideoSi/docs/task-designs/VAI-13-design.md`。

已存在的 completed 候选只重新消费来源并返回 `awaiting_acceptance`，不重新生成或编码。正式发布必须显式 `resume --publish --reviews PATH` 并通过任务12全部最终审查和 `human_full_film` 接受门槛；`--publish` 与 `--changes` / `--retry-failed` 互斥。退出码：0 = 本轮 candidate_ready / published，3 = awaiting_review / awaiting_acceptance，1 = 执行失败，2 = 准入或审查拒绝，130 = 中断。旧单阶段 CLI 保留原退出契约。

后续生成不进行 GPU 采样、租约、准入或 `/free`，仅管理本进程真正拥有的服务。无累计管线或镜头期限；单请求、服务启动和每个媒体操作仍有有限期限，媒体操作上限300秒。未知提交、外来锁及孤立产物会停止恢复；默认保留所有诊断和恢复帧，不清理历史目录。

任务12新增自动成片检查与严格发布接口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 validate-candidate --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 publish-candidate --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --review D:/VideoSi/projects/video-ai/runs/<run_id>/logs/validation/final-review.json --acceptance D:/VideoSi/projects/video-ai/runs/<run_id>/logs/validation/full-film-acceptance.json --json
```

`validate-candidate`仅首次运行pending validation：完整重新消费composition来源链，再独立检查1080p H264/CFR/帧预算、AAC完整解码与连续包，以及UTF-8无BOM/LF字幕的原文、布局和绝对时刻。`candidate-validation.json`只证明候选可供审查，三个最终语义/同步/整片接受状态仍为unverified。后续消费者必须使用`load_committed_candidate`重建验证，不能只读取passed。

`publish-candidate`要求本run `logs/validation`中的完整最终连续视频review、声音/画面cue观察和`human_full_film`接受。逐要求六项结论必须passed；每条连续播放区间、原PCM与最终候选身份须精确关联；声音标注不确定性与帧量化合计最多一个输出帧。人工接受必须确认完整观看、完整试听及SRT，绑定全部review/观察和确切MP4/SRT。缺失、failed/unverified、身份漂移或接受后重新编码均拒绝，保存唯一诊断，publish仍pending。JSON记录检查不代替实际观看；程序不会生成passed或人工接受。

默认输出为`D:/VideoSi/output/video-ai/<run_id>.mp4`、同stem `.srt`与`.publication.json`标记；可用`--output PATH`指定同一正式根中的MP4。只复制已接受字节，独占run与输出stem锁，拒绝任何同名文件/标记/外来锁，逐字节重新核验。中断或失败保留partial文件；仅匹配标记且manifest.publish=completed才可通过`load_committed_publication`消费。退出0=阶段completed，1=开始后的failed，2=准入/路径/接受拒绝，130=中断。两个阶段均不能重跑或重置终态。

人工输入的精确schema和要求见`D:/VideoSi/docs/task-designs/VAI-12-design.md`与[config/README.md](config/README.md)。当前26.1875秒真实候选只用于自动校验和缺接受拒绝；任务14仍需完成双档30～60秒完整观看试听验收。

任务11将已正式接受的超分镜头、原PCM和统一时间轴合成为烧录中文字幕的staging候选：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 compose-clips --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/20261004-231837-23363b5fff74 --json
```

仅pending且没有合成锁、旧报告或staging/composition目录可执行一次。已执行命令不应重跑；失败保留媒体和诊断。逐输出帧登记已验PNG来源和cut/fade权重，24fps采用previous-native重复采样；原PCM逐样本保留，外加静音及末padding由同一时间轴决定。可选音乐明确登记循环交叠、淡化和实际增益。字幕原文及绝对样本事件保持，用私有已验证字体排为最多两行，输出UTF-8无BOM/LF的subtitle.srt和烧录用subtitles.ass。FFmpeg使用独立argv和滤镜文件（本机新版参数为-/filter_complex），每命令期限300秒。

可用`--settings PATH`指定独立样式设置，例见config/composition.example.json；省略键采用默认值，字体文件和音乐仍来自冻结主配置。不会修改production/voice配置或原视频。完成后composition.json绑定全输入、逐帧贡献、13项画面关联、cue计算、音频/字幕/编码原始证据；consumer为runtime.composition_checks.load_committed_composition，重新核对来源、样本、字幕、帧序和实际候选完整解码。退出0表示技术候选可消费，1为开始后的失败，2为参数/路径/配置或状态拒绝，130为中断。

候选文件固定为本run的staging/composition/candidate.mp4和subtitle.srt。staging_only=true；最终实际画面语义、音画同步和整片观看试听接受仍unverified，合成技术通过不能代替后续实际观看或发布。任务11不发布到正式输出。详细契约：D:/VideoSi/docs/task-designs/VAI-11-design.md。

任务7提供分镜草稿与文本审查提交入口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 plan-storyboard --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/20261004-045454-0d3e35636717 --timing-review D:/VideoSi/projects/video-ai/runs/20261004-045454-0d3e35636717/logs/storyboard/timing-review.json --json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 finalize-storyboard --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/20261004-045454-0d3e35636717 --review D:/VideoSi/projects/video-ai/runs/20261004-045454-0d3e35636717/logs/storyboard/semantic-review.json --json
```

模型请求前必须通过时刻证据和单一语义审查。保留人工标注分支；用户接受原音频并明确委托技术标注时，可通过 `create_automated_timing_review` 生成带委托身份和完整测量依据的自动信号估计。48kHz PCM16使用1/2/4/8幅度阈值、阈值位置范围中点及240样本guard，消费时重新测量；它不是人工审听或词级对齐。候选切点与估计误差共用一帧预算。程序冻结原文、槽位、真实PCM交集和Wan预算；模型仅填视觉字段、数量/否定及有原文跨度的上下文指代。不同短语不为凑时长合并。

生成阶段只写 `storyboard-draft.json`，返回1 / `review_required`，不进入生图；独立11435 owned Ollama、模型manifest/blob新鲜SHA、有限请求原始证据均必需；按后续GPU政策不执行GPU采样或准入。仅明确done但内层JSON/Schema错误允许一次格式修正；总生成POST最多2次，响应或证据不明确时停止。逐项文本审查绑定草稿、timeline与timing身份，全部passed后 `finalize-storyboard` 返回0并提交正式 `storyboard.json`。读取者须使用 `load_committed_storyboard`，每次重新核对全部输入、标注、审查和产物身份。

桌面GPU并存时可在 `plan-storyboard` 加 `--cpu-planner`，POST明确 `num_gpu=0`，有限单次期限为 `max(configured, 1800)` 秒，依据真实CPU约8～9token/s与8192输出上限设置，仍要求独立owned服务，不改正式配置或释放外部进程。Ollama线上以所有键必填的shot_id/unit_id对象传输固定镜头与要求；保存原始wire结果后按冻结顺序无损还原数组。模型每镜头只描述主句，并消费已准入的单句语义理由；相邻量化边缘由程序原样复制最近同原句主镜头的要求，所有PCM bindings保持，最终每个非静音binding恰好一个完整原文要求。`primary-content.json`及`binding-expansion.json`保存模型原文和复制关联，提交及消费重新推导并逐字段比较，拒绝静默改写。上下文支持的完整原单元跨度/引用为const；模型不能漏主句或编写字符范围。

可在请求前提供本run规范路径 `logs/storyboard/visual-contract.json`：逐单元记录 `agent_source` 原文解释，绑定script与timing身份，完整覆盖所有原句及上下文指代。存在时，八项来源事实由Schema const固定，模型继续生成构图、相机、动作起终点、两阶段提示词与视觉表达；不存在时兼容原接口。契约新增、删除、替换或身份漂移会阻止提交及消费。契约接受的是原文解释，实际模型文字仍须另做完整文本审查，不能以事实const代替模型结果验收。

契约v2增加 `depiction_policy=grounded_prompts_v1`，要求模型直接在画面字段和提示词里生成原文事实前缀，再补充非空的可视表达。相机从明确路径中选择，视频提示词尾部路径须与该选择一致；Schema与程序共同检查。程序不替换模型文字，前缀后的实际表述仍须核对是否矛盾或增加无来源事件。旧v1保持兼容。

实际画面语义和视频同步保持 `unverified`；后续连续视频审查与最终人工完整观看试听接受仍是正式发布门槛。原文/配音/timeline/声音接受/配置保持；失败、孤立产物和外部锁不覆盖，终态不重置。无合格timing时不能执行真实模型，开发测试通过不等于任务7实机验收完成。

任务6从已完成的配音run建立统一时间轴：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 plan-timeline --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/20261004-045454-0d3e35636717 --json
```

`timeline.json`保存原文跨度、独立PCM身份、48kHz整数样本位置、字幕事件、显式静音、绝对16/24fps帧位置和尾部padding。默认句间0.8秒、段间2秒、片头2秒、片尾3秒；单换行/CRLF/空行仅插一次段停顿，末段没有额外句停顿。`planning.timeline.budget_slots`提供双侧fade覆盖/native16/Wan4n+1预算，槽位和画面内容由后续任务决定。24fps是普通转换，不是原生24fps动作或AI插帧。

该命令仅运行一次已有run的pending timeline阶段；既有锁、产物或已开始阶段拒绝覆盖。读者使用 `load_committed_timeline` 同时核对完成manifest及新鲜artifact SHA。配音、原文、声音接受记录和正式配置不改写；失败诊断保存在run的logs/timeline。退出0表示自动时间轴校验通过，`listening_accepted`单独来自可核验的用户记录；时间轴不证明实际画面语义已通过。此阶段不生成拼接WAV、SRT或视频。

Python 3.12（64位）轻量调度骨架，源码位于 D:/code/py/video-ai，实际配置、素材、运行结果、独立环境、日志及缓存位于 D:/VideoSi。目前提供严格配置、Windows路径隔离、doctor 预检，以及运行记录、服务通信和资源拥有权；制作阶段将在后续任务接入。

任务5配音阶段入口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 synthesize-speech --config D:/VideoSi/projects/video-ai/config/production.json --script D:/VideoSi/projects/video-ai/inputs/verification/VAI-05-script.txt --json
```

严格UTF-8/BOM原文保留CRLF和Unicode字符位置；标点分句/短语、空白与纯标点skip，TTS直接消费原文跨度。每个新run冻结固定v2 CPU声音/参考/模型身份，只使用本次启动的TTS，外部9880实例保留并拒绝接管。每单元仅一次有限POST，响应不明确时停止后段并保留已验收音频与证据。原始WAV完整解码后转为48kHz单声道PCM16，验证整数样本、时长及完整性；不裁剪或额外插入停顿。

run内`segments.json`保存全文覆盖、每段原始/PCM身份、样本数和状态；`audio/listening-preview.wav`仅按原顺序逐样本拼接用于试听，`reference_replay`是本次固定参考文本重放。退出0仅表示自动配音验收通过，`listened=false`仍需用户明确试听接受，结论保存在`voice-listening.json`。时间轴和完整视频编排由后续任务接入。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/install_windows.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 --help
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 doctor --config D:/code/py/video-ai/config/production.example.json --json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/test_windows.ps1
```

安装可指定 `-Python <Python312的绝对路径>`，离线依赖可用 `-Wheelhouse <wheel目录>`。独立环境为 D:/VideoSi/envs/video-ai，运行依赖仅标准库；pytest 为 dev extra。脚本在 Python 执行前重定向临时目录和缓存，将 stdout/stderr 与退出码持续保存到 cache/video-ai/logs。启动保留调用目录；测试使用源码工作目录与独占 pytest 临时/缓存目录。

doctor 返回0表示本地资源、映射和FFmpeg能力枚举通过，1表示检查失败，2表示配置/参数错误，130表示中断。资源未迁移时样例预期返回1。报告始终保留 inference_verified=false、full_run_space_checked=false、fast_profile_verified=false；它不验证服务在线、模型推理、完整磁盘预算、NVENC实际编码或字幕渲染。

配置中的路径以所属文件为基准；命令行路径以调用目录为基准。C盘可作只读来源，任何运行写入必须在对应D:/VideoSi子树。Windows UNC/设备路径、ADS、drive-relative、保留名、尾部点/空格和逃逸junction拒绝。运行编号为本地时间加12位随机hex，镜头使用shot_0001式正整数编号；正式MP4/SRT任何一项已存在都拒绝覆盖，并发发布由VAI-12实现。

职责边界：config保存严格输入；runtime负责路径、环境、预检及后续运行/进程管理；planning负责原文/分镜；adapters负责服务通信；media负责时间轴与媒体；pipeline协调阶段。任务板与正式设计/验证文档位于 D:/VideoSi/docs。

任务3接口：`create_run` 后用 `create_manifest` 保存原始/解析配置及文件身份，用 `RunLogger` 保存独占证据。manifest 采用独占写锁、fsync 和原子 replace；既有锁、坏记录和终态重置均拒绝。配置快照与提交身份不能被后续更新清除。运行证据在 `projects/video-ai/runs/<id>/logs`，实际提交图在该run的 `workflows`；API原始body、HTTP/进程元数据、异常、资源样本均保留。`run_logged` 持续写stdout/stderr，非零退出和超时由调用者判定失败。

`HttpClient` 只访问配置的本机HTTP源，禁用环境代理与自动redirect，单次请求和JSON体均有预算（JSON最大32MiB）。错误分为 explicit、ambiguous、invalid_result、unavailable。`ComfyClient` 先远程校验 `WorkflowTemplate`，然后 `submit_once` 原子保存intent并只POST一次；prompt_id落盘后 `wait_for` 只跟踪该ID。丢响应、写盘失败或期限耗尽时保留证据，重新调用同一单元会拒绝再次提交。history成功只证明生成服务报告完成，媒体还须后续完整验证。

`ServiceManager.ensure` 返回已存在服务的 `owned=false` 句柄；只登记本次启动的Popen为owned，`stop` 不接受伪造句柄或持久化PID。`GpuLease(paths, manifest, logger, service_manager=manager)` 使用当前管理器的活进程登记区分己方GPU任务，批量只允许整数1；未知查询、外部compute PID或现有GPU锁会拒绝进入。使用 `with lease.acquire(stage, unit_id):`，只释放自己持有的锁。`ResourceSampler` 可作为上下文持续采样，JSONL与查询原文留在run；未知资源不视为空闲。Comfy模型释放须活的owned句柄、已验证资源和新鲜空队列；不释放外部Ollama/TTS模型。

任务3通过故障注入与真实轻量子进程验证；工具迁移、生成服务实机验证、run/resume和完整视频编排分别留给后续任务。

任务4提供迁移和组件验证入口（实际迁移/推理状态见 D:/VideoSi/docs/video-ai/VAI-04-progress.md）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 migrate --inventory D:/VideoSi/docs/video-ai/VAI-01-inventory --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 migrate --inventory D:/VideoSi/docs/video-ai/VAI-01-inventory --execute
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 verify-components --config D:/VideoSi/projects/video-ai/config/production.candidate.json
```

`--dry-run`只写独占run的计划/容量/manifest，不创建工具模型副本；`--execute`逐文件完整SHA、fsync后独占发布，已有相同副本重新校验后跳过，不同目标拒绝覆盖。中断和冲突保留副本、临时诊断与逐文件JSONL；重跑新鲜扫描并校验续复制。容量计入工具根与外置模型的重复份数、最大临时副本、组件工作空间和20GiB保留量。

`verify-components --only environment|ollama|tts|sdxl|wan|upscale|media`可独立检查一个组件；upscale/media只消费同一候选与声音配置的已验收产物，并重新核对SHA。完整序列通过迁移、环境、模型、API、媒体、资源和写入隔离门槛后，才独占生成正式`D:/VideoSi/projects/video-ai/config/production.json`；此前候选配置不能作为迁移完成证明。新Ollama固定11435，保留外部11434服务。用户批准的任务4桌面并存例外保存新鲜OS身份、NVIDIA类型及可用显存证据；未知任务仍拒绝，默认GPU租约仍保持严格策略。组件样片不发布至正式output，不代表多镜头、快速档或主观试听通过。
# 起始图（任务8）

已完成分镜后执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 prepare-start-images --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --json
```

默认1280×720；`--image-width`、`--image-height`必须是64以上、8的倍数且严格16:9。可选 `--image-inputs PATH` 指定JSON：`{"schema_version":1,"run_id":"<run_id>","shots":{"shot_0001":"D:/素材/图片.png"},"entities":{}}`。只使用明确映射，用户图优先，缺图调用固定SDXL；未知ID在生成前拒绝。用户横竖图等比contain、居中黑边，原字节归档，不裁剪或拉伸。实体参考通过entities映射提供；当前SDXL没有图像条件节点，参考仅作实际图片比较，生成复用共享描述。

起始图生成遵循用户最新GPU约定：不检查GPU资源或申请GPU租约，不采样或调用模型释放接口；只启动和停止自己拥有的Comfy服务，外部端口仍不得接管。后续任务同样遵守 `D:/VideoSi/docs/video-ai/2026-10-04-gpu-policy-revision.md`。

真实图片静态审查失败后的独立尝试，可在prepare之前准备 `logs/start-images/visual-directions.json`：schema_version=1、run_id、storyboard_identity、review_basis_identity、shots。每个修正镜头含positive、negative、reason、requirement_ids（原主要求，禁止邻句边缘）；依据必须绑定先前failed审查及同一原文要求。具体静态表达置前，原提示词/风格/实体完整保留，固定模型与采样参数保持。该文件、依据、实际参数/workflow在prepare、finalize及consumer新鲜校验；方向记录不等于实际图像通过。

prepare成功准备全量图片后退出1，状态review_required。打开每个 `shots/<shot_id>/start.png` 及references中适用主体参考，逐条对照images-draft.json.requirement_images的原文要求，核对可见主体、场景、数量、否定和指代对象。quantization_edge_preview检查关联的主场景图，不要求前镜头提前插入下一场景。将直接审图观察独占保存在logs/start-images的JSON，字段为schema_version、run_id、draft_identity、review_method、reviewer、viewed_at、references（草稿原值）、entries（原requirement_images条目加observation实际观察）；保存其FileIdentity。媒体摘要不能冒充该观察证据；按详细设计的精确Schema写 `logs/start-images/semantic-review.json`。缺项、failed、unverified或任一图片/原素材/配置/分镜/模型/证据漂移均拒绝。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 finalize-start-images --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --review D:/VideoSi/projects/video-ai/runs/<run_id>/logs/start-images/semantic-review.json --json
```

全量静态审查通过才退出0、提交images.json及ready_for_source_clips=true；正式consumer为runtime.start_image_checks.load_committed_start_images。静态图片不证明持续运动或音画同步，这两项仍unverified，留给实际视频与最终成片审查。图片使用独立units.image，保留后续Wan的units.shot一次提交空间。现有锁、孤立产物、未知提交和已执行阶段不会自动覆盖或重POST；只管理本次启动的服务，外部8188服务仍拒绝接管。

详细契约：`D:/VideoSi/docs/task-designs/VAI-08-design.md`。

任务9准备固定 Wan2.2 FP8 动作源片：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 prepare-source-clips --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --json
```

入口消费同一 run 已正式接受的 images、storyboard 和 timeline，并重新校验配置、完整 workflow/mapping、Task4 库存和四个模型字节。使用原 video_prompt、风格与实体描述，保留原中文 negative；40 steps、CFG3.5、euler/simple、split15、batch1。源片固定 native16；fast 为768×432，quality 为1280×720，输出16/24由冻结 timeline 决定。当前七镜头请求69/45/49/85/57/29/93帧，完整解码后按预算保留68/45/47/84/55/27/93帧，共419帧。每镜头保存 generated.mp4、source.mp4、全部 PTS/probe/decode/trim 证据和即时 checkpoint。

每个独立尝试只 POST 一次。只有成功 history、完整解码且尺寸/CFR16/无音频均正确的已知短片，才允许一次独立补生成；65<68时69→73，同 seed，仅增加长度，不拼接、循环、冻结或插帧。attempt_0001/0002 是镜头本地名称，submission.attempt_id 是独立 UUID。未知提交停止并保留证据。只停止本次拥有的 Popen，确认停止后才保存草稿；外部8188拒绝接管，不检查GPU、申请租约、采样或调用/free。

prepare 全量成功后仍退出1、status=review_required。实际连续观看所有 requirement_clips 对应的完整 source.mp4 区间，记录起点、过程、终点、相机路径、主体/场景/数量/否定/指代/顺序及质量；2/7核对枝叶风动，3/4核对灯光倒影与细波纹摇动，5/6核对第一人称沿同一路径前进与脚步视觉来源，并比较3→4、5→6末端到起点的连续性。静态图片、三张截图、diff或仅启动播放器无法代替 continuous-video review。

直接观察 JSON 独占保存在 logs/source-clips，精确字段为 schema_version、run_id、draft_identity、review_method（human_video或agent_video）、reviewer、viewed_at、entries；entries 为草稿 requirement_clips 完整原条目，加 playback_frames（等于完整 local_frames）、非空 start_observation/process_observation/end_observation/quality_observation。viewed_at 带时区且在草稿创建与 review 之间。该记录的 FileIdentity 必须绑定实际观察文件。

两次跨镜头比较必须显式写在正确的主条目：clip_shot_id=shot_0004且role=primary的quality_observation以`[continuity:shot_0003->shot_0004:passed]`开头；shot_0006主条目以`[continuity:shot_0005->shot_0006:passed]`开头。标签后必须有实际前镜头终点/当前起点的比较和质量观察。结果词只允许passed/failed/unverified；缺少比较或unverified保持待审查，failed拒绝。不得只在边缘条目或错误镜头填写，不得重复/矛盾标签或只有标签而无观察。标签仍需实际连续观看证据。

用户明确接受当前候选片继续开发时，可使用同一canonical semantic-review.json的`review_method=user_acceptance`回执。精确字段为schema_version（严格整数1）、run_id、draft_identity、images_identity、storyboard_identity、timeline_identity、review_method、reviewer、reviewed_at、accepted（必须字面true）、acceptance_text（实际用户接受原话，非空）、acceptance_scope（恰为`source_clips_for_upscale`）、unverified_checks（恰为有序`["video_text_semantics","motion_semantics","quality","cross_shot_continuity"]`）、entries（草稿requirement_clips全量有序原值，不添加verdict或观察字段）。该分支不要求或生成直接观看观察文件；所有媒体、模型、提交和身份校验仍执行。正式报告ready_for_upscale=true，但video_text_semantics_passed/motion_semantics_passed仍false；质量及跨镜头连续性明确unverified，最终同步/整片验收仍unverified。原human_video/agent_video观察与连续性门槛保持不变。

human_video/agent_video 的 `logs/source-clips/semantic-review.json` 精确字段为 schema_version、run_id、draft_identity、images_identity、storyboard_identity、timeline_identity、review_method、reviewer、reviewed_at、global_verdict、reason、entries；每个 entry 是 requirement_clips 完整原条目加 evidence_identity、verdict、reason。所有原关联及半开范围保持原值，此观察分支须全量13项实际动作与质量均 passed 后再提交：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 finalize-source-clips --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --review D:/VideoSi/projects/video-ai/runs/<run_id>/logs/source-clips/semantic-review.json --json
```

缺项/unverified仍 review_required；failed、错误绑定或漂移不能提交。只有正式 source-clips.json 与七个主镜头/stage 在同一个 manifest 事务 completed 后退出0、ready_for_upscale=true；主镜头 submission=null，独立 attempts 终态保留。正式消费者为 runtime.source_clip_checks.load_committed_source_clips，重新核验媒体/HTTP/观察/模型/配置/预算/映射和完整报告 FileIdentity。source-level通过时 final_video_sync 与 full_film_acceptance 仍 unverified。CLI退出1为失败或待审查，2为参数/阶段拒绝，130为中断；既有锁、孤立产物和终态不覆盖。详细精确Schema见 `D:/VideoSi/docs/task-designs/VAI-09-design.md`。

任务10逐帧 PyTorch AI 超分与1080p镜头编码：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 prepare-upscaled-clips --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/20261004-231837-23363b5fff74 --json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/code/py/video-ai/scripts/start_windows.ps1 finalize-upscaled-clips --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/20261004-231837-23363b5fff74 --review D:/VideoSi/projects/video-ai/runs/20261004-231837-23363b5fff74/logs/upscale/semantic-review.json --json
```

先prepare，完成独立实际视频审查并保存规范回执后才finalize。入口重新消费已正式接受的source-clips.json及冻结配置/模型/完整workflow身份。按已裁source.mp4的原帧序抽取七镜头68/45/47/84/55/27/93帧，共419个独立frame提交；不使用原generated_frames裁尾前的帧数。fast768×432或quality1280×720输入均为native16，保持帧数、帧序、时长和16fps，不插帧、不改变fps、不补循环或冻结帧。

固定五节点为 `LoadImage → UpscaleModelLoader(RealESRGAN_x4plus.pth) → ImageUpscaleWithModel → ImageScale(lanczos,1920,1080,crop=disabled) → SaveImage`，PyTorch模型真实4倍超分后等比缩小到1920×1080，单图batch1串行。使用 `D:/code/py/video-ai/workflows/upscale_api.json`，mapping从同目录派生为 `upscale_api.mapping.json`；配置没有 `upscale_mapping` 键。全部PNG完整校验后以libx264/CRF18/yuv420p/native16编码 `shots/<shot_id>/upscaled.mp4`，完整probe/PTS/decode核对1:1帧映射。每frame只POST一次，独立UUID intent/prompt_id、即时checkpoint及原始请求/响应保留；超时、未知提交或媒体失败停止，无自动重试、普通放大降级或覆盖。现有锁、帧、checkpoint、MP4、草稿和正式报告均不覆盖，prepare 不自动恢复；下述授权入口仅处理经核验的未提交前缀。

保留全部原source/generated视频、配音、时间轴、分镜、起始图、配置、模型、旧日志和登记的临时帧。源接受记录“我觉得没问题，继续吧。这个项目后续还会微调的”仅允许当前source用于超分；原source_validation和source_review_method/identity完整保留。原source文本/运动语义false、画质/连续性unverified不能自动变成新片passed；任务10只接受新的 `human_video` 或 `agent_video` 实际审查，不自动使用 `user_acceptance`。不进行GPU查询、准入、租约、采样或/free，只启动独立owned Comfy并停止自己实际拥有的Popen；外部8188拒绝接管，确认owned进程停止后才保存草稿。

prepare技术全量完成也只写 `upscaled-clips-draft.json`，返回1、status=review_required、passed=false、ready_for_composition=false；此时upscale阶段保持running。草稿的结构/媒体/帧映射校验true，新片文本语义/运动语义/超分质量/合成准入false。CLI JSON精确字段为 `passed, run_dir, draft_path, clips_path, clip_count, ready_for_composition, status`；普通输出同样报告ready_for_composition。退出0仅为正式completed，1为待审查或运行/I/O失败，2为参数/路径/配置内容/阶段拒绝，130为中断；配置文件无法读取属于I/O失败。CLI路径以捕获的调用目录为基准，run/review保留lexical拼写交给runtime核对重定向。

独立按草稿 `requirement_clips` 的原13项顺序，实际连续观看每项 `source_actual_artifact.path` 的source.mp4和 `actual_artifact.path` 的upscaled.mp4对应完整local_frames半开区间。保留每项原shot/requirement_index/primary-edge角色、原文和三个半开范围，不能以七主镜头数量代替13项覆盖；量化边缘仍审查对应主镜头全区间，不要求提前插入下句。逐条核对新片主体、动作、场景、数量、否定、指代和顺序，对照源片有无改变，记录新增彩噪、矩形接缝、闪烁、纹理跳变或人物/物体变形。几张截图、像素阈值或仅启动播放器不足；不能实际观看时给出上述两版MP4确切路径，保持review_required，不编造观察或passed。

直接观察文件独占保存在 `logs/upscale`（例如 `continuous-observation.json`），精确顶层字段为 `schema_version, run_id, draft_identity, review_method, reviewer, viewed_at, entries`。schema_version严格整数1；review_method仅human_video或agent_video。每个entry复制对应requirement_clips的全部原字段，另加 `source_playback_frames, upscaled_playback_frames, start_observation, process_observation, end_observation, comparison_observation, quality_observation`；两个playback范围都必须等于local_frames，五个观察字段必须是根据两版实际连续视频写下的非空文字。viewed_at/reviewed_at均带时区，满足 `draft.created_at ≤ viewed_at ≤ reviewed_at ≤ 当前时间`。

两次跨镜头实际比较放在正确的主条目：clip_shot_id=shot_0004且role=primary的quality_observation必须以 `[continuity:shot_0003->shot_0004:passed]` 开头；shot_0006且role=primary必须以 `[continuity:shot_0005->shot_0006:passed]` 开头。标签后须有源片/新片前镜头终点与当前起点的实际连续性细节；failed/unverified标签不能通过，错镜头、edge条目、重复标签或只有标签拒绝。

规范回执固定为 `logs/upscale/semantic-review.json`，精确顶层字段为 `schema_version, run_id, draft_identity, source_clips_identity, review_method, reviewer, reviewed_at, global_verdict, reason, entries`。每个entry复制对应requirement_clips的全部原字段，仅增加 `evidence_identity, verdict, reason`；全13项按原序完整绑定，evidence_identity绑定实际观察文件。所有身份均为完整FileIdentity对象，精确字段 `path, bytes, mtime_ns, sha256, verified_at`，由 `runtime.manifest.hash_file` 读取实际字节生成，不使用播放器启动日志、媒体摘要、虚构身份或旧收据。draft_identity绑定当前upscaled-clips-draft.json，source_clips_identity绑定当前正式源报告；观察与回执的方法/reviewer一致。拒绝未知字段、重复JSON键、bool冒充int、非有限值和任一文件身份漂移。

global_verdict及逐项verdict允许passed/failed/unverified；缺项或unverified保留review_required，failed或绑定漂移阻止提交并保留诊断。完整独立新片文本/运动/质量对照均passed后，finalize才独占发布 `upscaled-clips.json`，在同一manifest更新注册 `workflows.upscale_report` 完整身份并将upscale标为completed；passed/ready_for_composition及七项validation均true，原source_validation不改。正式consumer为 `runtime.upscale_checks.load_committed_upscaled_clips`，新鲜核验source、419个frame提交/checkpoint、全媒体/映射/模型/配置/HTTP与独立实际观察；源shot/attempt终态保留。后续整片音画同步 `final_video_sync` 和完整成片接受 `full_film_acceptance` 始终unverified，须由后续任务和实际整片审查完成。测试结果不证明真实419帧推理、画质或整片接受。

用户明确授权继续且不限制总耗时后，受限恢复接口为 `runtime.upscale_checks.resume_upscaled_clips(config, run_dir=...)`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_windows.ps1 resume-upscaled-clips --config D:/VideoSi/projects/video-ai/config/production.json --run-dir D:/VideoSi/projects/video-ai/runs/<run_id> --json
```

该入口仅允许没有草稿/正式报告/既有恢复收据的 ambiguous 阶段，以及规范连续 completed 帧前缀后最多一个 submission 严格为 null、artifacts 为空的 ambiguous 尾帧。任何 intent/accepted/unknown/rejected 等已有提交都拒绝；不提供重试、重置或第二次恢复开关。锁、完整配置/源报告/模型/实际 graph、原始 HTTP 和媒体证据、全部原图与副本、空间及独立 owned 服务准入通过后，专用原子事务才重开这个未提交尾帧。默认 prepare 的一次执行和终态保护仍保留。

恢复独占保存 `logs/upscale/resume-manifest-<uuid>.json` 原 manifest 字节快照和 `resume-<uuid>.json` 收据；原 completed 记录、事件前缀、视频、抽帧与旧 checkpoint 保留。收据记录授权、旧 manifest 完整身份、重开 unit_id、从此时冻结的历史输入/证据索引及执行政策。schema2 草稿增加 `execution_policy`：total_timeout_seconds=null、frame_timeout_seconds=冻结配置 upscale_frame、request_timeout_seconds=冻结配置 comfy_request、media_command_timeout_seconds=300，另有注册收据的完整 resume_identity。无镜头/阶段累计期限；单帧、HTTP、每媒体命令、服务启动仍有有限期限。复用旧输入副本时，以新 unit.started_at 与 copy.mtime 的较晚时刻回放帧窗口，旧副本字节和时间戳不改。

已有完整片直接复用，部分镜头复用有序原抽帧和完成 checkpoint，只首次提交剩余帧。schema1 保持原累计镜头期限规则，schema2 独立回放恢复收据及保留证明；两者正式提交均仍需新的全量实际 source/new 连续视频审查，技术完成返回 review_required/退出1。

详细精确契约：`D:/VideoSi/docs/task-designs/VAI-10-design.md`；本次授权恢复扩展：`D:/VideoSi/docs/video-ai/VAI-10-resume-design.md`。
