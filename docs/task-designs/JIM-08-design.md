# JIM-08 全链路回归、真实样片验收与使用说明

## Goal

在JIM-07已完成的公共入口上建立通用视频生成与跨窗口续写的条件/状态/恢复方案，验证真实官方出图、TOS参考读取、QQ收信、用户选图、连续动态观察和正式成片，并交付可照做的配置与使用说明。主体、题材、动作与镜头意图由输入和模型能力决定，真实样片只作为验收案例；替身结果、真实服务事实、单例观看结论与跨题材验证分别记录。

前置已于2026-10-20记录COMPLETED：JIM-07最终裸全库3552通过、退出0；其中新增156项和指定历史195项全部通过，364项文件前后及独立重算一致。确切证据为 `docs/task-designs/JIM-07-verification.md`，本设计不声称JIM-08已执行。

## Scope

- 颜色与连续性继续修复（2026-10-21）：用户明确“那你继续修复吧，颜色也不对”，授权继续排查/修复，原图参考试验的一次停止不是永久禁止后续有依据的对照。本轮先做安装原生VAE无扩散采样的颜色往返检查（色条、已有三张选图和真实历史），再按结果决定一次同权重/同输入/同提示/同seed与同采样预算的FP8→原始FP16对照；使用已安装meta/lazy、mmap与DynamicVRAM加载，不下载/换模型、不新增结构素材、不自动改CFG/步数或色彩后处理。若原精度加载资源不足或仍失败，保留结果，不自动降低精度/尺寸/时长或重试；其他方向继续先按证据设计。既有run、观察和正式16fps保持；“颜色也不对”记为外观反馈，不推断用户已完整播放或接受动作。
- 通用连续性方案修订（2026-10-21）：用户明确“把这些调整一下在方案中试试，还有切记你要做通用的视频生成方案，而不是针对某一个视频完成工作”。授权将已讨论的固定参考与真实历史组合加入方案并作受控本地验证；本轮先复用已下载VACE，用原失败案例作单变量对照，不再索取该试验授权。目标是任意文案/主体/场景的生成与续写协议；白鹭、湖面、scene编号、色调、帧数和旧run只属于案例输入，不进入通用规则或生产分支。没有同时批准下载FramePack/其他模型、云视频或无限重试。下面此前单次VACE/SkyReels授权的停止规则作为历史保留，不覆盖本次新增明确授权。
- 分层约束：固定外观参考、真实运动历史、镜头意图、可选结构控制分别表达；固定镜头、跟拍、有意运镜不共用“背景零光流/主体完全不动”提示。图片保持身份/环境，历史保持动作上下文，两者均不是未来像素的硬性锁定。结构控制只有对应模型能力及引导序列已核实时可启用，不把SD/SDXL IPAdapter/FaceID、静态Canny、人像OpenPose、RAFT估计或LatentFromBatch当成通用Wan能力。
- 此轮通用性验收分开记录：参数化协议/CPU条件与预算验证、已有失败案例的真实GPU画质、其他题材/镜头/长链真实质量。不能由前两项通过宣布第三项已通过。禁止用裁切、防抖、插帧、静止/循环或反复换seed把拒绝样片转为接受；正式多片与原生16fps要求保持。

- 连续性试验授权（2026-10-21）：用户针对`JIM-08-continuity-repair-proposal.md`明确回复“同意”，允许下载/核验Wan2.1 VACE 14B并只做一个隔离scene3视频续写试验，不重复索取该步骤授权。即梦4.0、Qwen3 14B、原旁白/字幕/时间轴、三个已接受首片和原冻结run不变。模型固定为ComfyUI官方示例链接的fp16源权重，核对不可变版本/大小/SHA；必要本地加载精度与原生视频条件先验证并记录。试验输出不计生产接受，实际完整播放反馈后再决定生产策略及修订改造；本条不授权无限新增试验或静默换为其他模型。

- 真实参考续作暴露的容量修复（2026-10-21）：JIM-04旧设计把当前场景引用条目的完整追溯JSON送入提示词，实际2548/2533字节，不能满足已冻结800字节预算。保留旧renderer原样；仅无任何既有请求证据、旧格式超限时，尝试确定性紧凑视觉表示。逐字保留image_prompt、全局描述、主体标签/固定属性、变体属性/所属主体、环境/时间/光照/空间、全部事实name/value和创作name/value/reason，并保留归属关系；仅完全相同值可因式化。完整原文/坐标/引用证据仍保留于原Bible及原SHA绑定，不宣称模型收到的旧引用细节完全等价。模型/API/能力预算/基准/验收协议保持；仍超限则零上传、零付费等待。此项是JIM-08已授权的真实缺陷修复，明确兼容扩展JIM-04的固定格式，不把旧契约改写成原本允许紧凑格式。

- 提示词选择/恢复集中在只读函数：整批预检、输入校验、provenance及候选/Wan准入共用。所有已保存request.json必须使用同一可精确重建的旧或紧凑prompt，完整核对既有request/intent/submit-evidence/provenance；有孤立intent/provenance而缺必要request时拒绝，不当新场景切换格式，不重新提交未知任务。已有provenance还必须有全部原intent/submit-evidence/accepted，防止丢提交证据后补单。result存在时严格核验身份、task_id及候选结构；已有candidates manifest时result必须齐全，无manifest且缺result时允许查询原accepted任务恢复，即使原输入URL已过期也不重新签名或提交。旧格式能容纳时继续旧格式。紧凑字段区分事实F、创作C、理由R，字面分隔符/控制字符用可解码的JSON引用和转义。两个实际提示词以正式函数独立核对为799/784个UTF-8字节，冻结上限仍800字节；不预设所有文案均可容纳或真实视觉通过。

- 后续时长说明（2026-10-21）：用户明确“不用严格是30秒，实际多长就是多长”。允许完整实际配音/时间轴时长，无需再次索取容差；保存并报告实测时长，继续不截旁白、不变速、不设全局总帧上限。
- 后续授权（2026-10-21）：用户明确“同意，升级吧”，允许下载本地Qwen3 14B并在同一Ollama协议内补显式scene planner选择、冻结模型绑定和原8B请求恢复。新增可选`scene_planner_model`仅允许已核对的`qwen3:8b`/`qwen3:14b`，缺省8B；units与旧storyboard不换模型，即梦仍4.0。保持原文、32768输入/8192输出预算、一次纠正和全部人工门槛。下载及实测由现有启动请求继续授权，不重复请求同意；更大模型不预设解决规划问题。最新时长要求以上一条为准。
- 后续用户输入（2026-10-20）：用户表示不了解模型选择，并明确授权由助手准备验收文案，指定视频30秒。允许先准备可审阅的模型/完整配置建议及文案草稿；最终模型与文案经用户确认后才作为真实调用输入。30秒是本次样片时长目标，不是新增全局时长/帧数上限；须通过实际配音与时间轴核对，不预先声称草稿已恰好30秒，不截断旁白或变速凑时长。
- 执行现有替身全链路及相关历史回归；配置用户指定的即梦模型/参考模型、已核对能力档案、已有TOS桶和QQ SMTP；以用户确认的短文案完成真实全流程及同run重复续作。
- 按总体方案核验同一主体至少三个画面、至少一个含两个连续片段的长画面；完整原文、PCM、字幕和时间轴保留，原生16 fps、cut、1920×1080，视频总帧数不设上限。
- 更新 `README.md`、`config/README.md`、`config/jimeng.example.json` 及必要的候选说明；发现缺陷时在相应现有模块先加真实回归，再修复，不另造生产协议。
- 不新建网页、自动收信、自动付费返工、自动视觉通过或新模型协议适配；不创建桶或改变访问策略，不改旧策略默认配置与历史记录。
- 本次完成设计和交接不启动真实调用。实施者收到明确的JIM-08启动请求后才执行本契约。真实参数、凭证及文案是本任务配置阶段的输入，不假定已经提供或可用。

## Approach

### 1. 第一实施动作与证据目录

先创建 `docs/task-designs/JIM-08-verification.md`，按总体方案五项Acceptance建立表格，列固定为：验收项、替身证据、真实服务证据、观看/用户结论、确切run/文件、状态、问题与下一步。所有尚未执行单元格写未执行/未核实；只将JIM-07报告链接记为前置基线，不移植其测试观察为真实接受。

每次执行的命令、起止时间、退出码和脱敏输出落在 `D:/VideoSi/cache/video-ai/logs/jim-08-<用途>-<唯一编号>.*`。实际媒体、作者输入和冻结配置沿现有D盘路径策略。没有实际结果的项不写passed；工作流终止时保留所有现场。

### 2. 配置输入与调用前停止规则

使用用户明确指定的实际配置；任务专用配置的落点为 `D:/VideoSi/projects/video-ai/config/jimeng-acceptance.json`，文案原字节落点为 `D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance.txt`。已有用户文件按其确切路径读取或按字节复制到这两个任务文件，记录SHA，不覆盖默认 `D:/VideoSi/projects/video-ai/config/production.json`、用户原文或已冻结run。目录不存在时按既有PathPolicy创建。

实施者先核实下列输入；缺失时在verification列明具体缺项并向用户索取本地文件/配置，停止真实请求，不猜模型、桶或样本文案：

- `production_strategy=paragraph_jimeng_v1`；保留用户已确认的voice、Wan/RealESRGAN权重、workflow、工具与媒体设置，以 `load_config` 及原预检验证。
- 用户选择的 `image_generation.req_key` 和完整参数；只接受现有智能视觉异步协议。`config/jimeng.example.json` 中的示范req_key不视为用户已经选择。未知能力不按名称推测；禁止自动换模型。
- 参考模型由现有 `choose_reference_model` 选择：主模型有经核验的参考能力时使用主模型，否则必须有用户显式 `reference_generation`。能力档案按 `reference_config.parse_capability` 的精确schema、官方资料字节SHA、实际核验者/带时区时间填写；不伪造capability evidence。
- TOS按 `parse_reference_storage`：provider/bucket/region/endpoint/access_key_env/secret_key_env及既有可选预算；endpoint必须匹配region，URL时效覆盖任务、下载余量和时钟偏差。不创建云资源。AK/SK仅从配置声明的环境变量读取。
- 发件/收件均为已确认的 `318575094@qq.com`，QQ SSL 465；SMTP授权码只从配置的环境变量读取。示例默认环境变量名为 `VIDEO_AI_VOLC_ACCESS_KEY`、`VIDEO_AI_VOLC_SECRET_KEY`、`VIDEO_AI_SMTP_AUTH_CODE`，允许用户配置其他合法名字，不记录真实值。
- 用户确认的完整UTF-8文案和允许进行该样片真实生成的明确启动上下文。文案应覆盖同一重复主体至少三个画面及一处足够长的连续画面；不替用户编造最终验收文案。

实际配置值和作者选择是运行输入，不改变本契约。配置解析或能力不支持时停在现有blocked/awaiting_image_model_configuration；不扩大为新协议适配任务。凭证不写JSON、命令参数、邮件或普通日志，普通pytest仍只用替身。

### 3. 按现有CLI逐门槛执行

从任务配置和原文创建新run，记录返回的实际run_dir；随后只使用该run的冻结设置。命令均在bootstrap环境执行，stdout JSON与stderr进度分开保存，立即记录真实退出码。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-08-real-acceptance'
$jim08Config = 'D:/VideoSi/projects/video-ai/config/jimeng-acceptance.json'
$jim08Story = 'D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance.txt'
& $VideoAiPython -B -m video_ai make-video --config $jim08Config --script $jim08Story --json
```

初次调用可能已生成首批基准候选；不能宣称公共入口提供了纯plan预览。到首个等待点读取真实plan、timeline和clips，核对至少三个同主体画面和至少一条两片以上同scene父子链。样本文案/实际规划不满足时停止继续付费生成及Wan，保留已产生证据，向用户确认修订文案并显式新建独立run；不改已冻结预算、不改原文、不截帧凑验收。

后续只消费CLI返回的选择、逐片、最终观察模板与确切路径，不猜模板或正式输出路径：

1. 保存官方真实task_id/request_id、实际req_key/参数和原图SHA。基准未选择前不得提交依赖图；关联请求须证明实际引用已选基准和既有TOS对象。
2. 保存SMTP实际尝试、MIME、Message-ID和接受结果，并取得用户QQ收信事实。SMTP接受不等于进入收件箱；用户需确认基准/候选/编号与实际附件一致。
3. 用户实际查看图片后填写返回的选择及整组观察。只告知编号不推定整组通过；可据明确用户陈述填入确切模板，不能代写未发生的观看。
4. `--image-selection PATH`只消费；再普通`--run-dir`推进。父片等待时实际连续观看对应视频、核对起点/过程/末帧及固定基准，按模板提交`--clip-observation PATH`；再普通续作才生成后继。仅首尾静帧不算动态观察。
5. 全部源片接受后执行现有逐帧超分和合成。候选MP4完整连续观看、完整试听旁白并核对字幕；按实际观看填写`--final-observation PATH`。failed/unverified保留候选和问题，不发布。
6. 仅final_review_ready后显式`--publish`，以收据验证返回的MP4/SRT路径。记录原脚本SHA、PCM样本/总帧、字幕文本和候选/正式文件身份及实际用户最终结论。

等待退出3、blocked/final_review_failed退出2、failed退出1、interrupted退出130；阶段accepted/ready退出0不代表全片交付。未知图片/Wan/超分提交只核对原ID，不补单；email_delivery_unknown先核对原Message-ID，需要重发时只有原retry协议及明确重发意图可创建新尝试。所有错误保留原文与原证据。

### 4. 重复续作、返工与故障处置

正式交付后保存run清单、SHA、mtime及输出file ID，执行两次普通`--run-dir`和一次重复`--publish`。应仍返回同一收据和路径；无新图片/Wan/超分意图、SMTP尝试、编码、invocation或锁记录，前后身份清单一致。记录用户未收到重复邮件的实际确认，不用本地发送回执替代。

模型切换、重选基准和父片变化的失效/原run保护使用JIM-07现有替身矩阵及本任务回归核验；真实运行如需返工，只消费用户明确的请求，以现有`--revision`准备新冻结run，再由用户决定推进。没有实际返工要求时不自动增加真实收费尝试。未知/失败不自动降低质量、换模型或无限重试。

任何真实错误或一致性问题都在verification逐项记录原证据、影响和明确恢复动作；如需生产修复，按相应原模块先RED后修复、再重跑受影响测试和完整全库。无法实看完整动态视频时等待用户/具备完整播放能力的审查者，不把看静帧或技术成功写成passed。

### 5. 使用说明与验收记录

README增加新策略入口、基准/参考选择、逐片观察、最终观察、独立publish及等待码，保留旧策略说明。config/README去掉已过时的JIM-01-only说明，明确新策略与旧配置缺省行为；示例保持合法、无真实凭证或伪造能力档案，未提供参考设置时明确会等待配置。候选说明与真实执行命令一致。

verification按下方五项Acceptance逐项引用测试日志、真实任务/对象/Message-ID、原图和输入PNG、完整观察原文及正式收据。未核实项保持未核实。完成前重新核对源码/测试/workflow/使用文档身份；用户配置与私密凭证不写入仓库。

### 6. 通用条件协议与本轮受控验证

**研究阶段边界。** 本轮在D盘独立研究目录建立参数化案例与临时验证器，不修改生产源码、Comfy安装或正式workflow，不把研究JSON当成已上线生产配置。旧run/请求/观察保持；后续生产集成须有按此证据完成的具体设计、恢复/修订测试及新裸全库。本节已批准的是条件组合的可行性验证，不是任意模型自动切换。

**通用数据分工。** 每份研究案例用外部manifest提供：`case_id`、源文件及SHA、`baseline_graph`及SHA、固定`reference_image`及SHA、真实`history_image_sequence`及SHA、原生`fps/width/height`、`history_frames/new_frames/generation_frames`、模型身份与加载精度、`camera_mode`（`locked/tracking/authored`）及案例来源。主体/服装/物体/环境/光照来自用户原图及已有视觉设定；当前动作与镜头来自本场景明确意图，不能从“稳定”推导成禁止位移。未来跨窗需要固定参考身份不变，历史取上一窗真正保留的原生帧，并保存来源映射/状态/RNG；有意换主体、环境或镜头时按新镜头明确重置，不继承错误锚点。缺意图/状态时记录未核实或停止，不猜未来动作。

**能力分派。** 必须按实际模型及workflow声明和核验首图、独立参考、历史帧/latent、结构视频、原生时基和帧对齐；不支持所需条件就停止，不能静默忽略。SVD的整数motion bucket、Wan各控制模型及蒸馏采样参数分别配置，不建立跨模型通用的motion=0.3、CFG4–6或48帧阈值。只有兼容控制权重及实际逐帧引导存在才启用mask/depth/canny/pose；固定镜头可有静态环境约束，跟拍须允许合理背景视差，鸟类不套人像骨架。因果缓存/记忆需要相应模型，不是额外串一个latent节点。

**当前唯一GPU对照。** 从此前已拒绝的VACE graph产生新graph，只增加独立`LoadImage(reference)`与`WanVaceToVideo.reference_image`，并将其第四输出`trim_latent`连接到采样后、VAE解码前的`TrimVideoLatent`。模型原权重SHA、FP8加载/FP16转换、20steps/CFG6/uni_pc/simple/shift8、原正反提示、seed、历史9帧、768×432、16fps全部保持。改变输出前缀仅隔离文件，不改变采样。若原参考图姿态与父末状态有冲突，结果仍必须保持历史动作，不以参考重启动作为合格。

本例预算是9历史+41新增，按4n+1向上补齐为53生成帧；参考图增加1个latent位置，先精确裁掉这个参考latent再解码，解码仍53帧。随后取`[9,50)`为41新增、丢弃3尾部补齐帧。这些数值来自案例manifest，临时验证器按H/N及模型对齐检查，不在通用代码写死。不同历史长度/新增长度/分辨率应走同一数据通路；只有本例有既有同参数失败基线，因此本轮只执行这一项GPU对照，不据此外推其他案例。

**提交与恢复。** 每个独立案例输出目录只允许一个intent/POST，已存在intent就拒绝重新生成；结果不明保留accepted/history，只查原任务，不能自动重POST。owned loopback Comfy仅用独立input/output/temp/user、禁用全部第三方节点、传递最小必要环境，结束仅清理自有进程。固定图与历史在提交前核验字节SHA、实际原生像素/顺序，使用同一固定源文件；记录graph/helper/原生节点/模型/输入/授权身份。原run及378生产基准前后全量核对。

**验证矩阵。** 通用协议先测任意node ID/参考文件名、不同H/N的4n+1预算、参考latent裁除与原采样/提示不变、缺少/冲突参考和已有intent拒绝。CPU执行安装原生VACE/TrimVideoLatent，用有区分的替身VAE编码检查参考与历史各入正确通道、正反条件均绑定、额外参考latent裁后维数一致，覆盖非9/41的时长和至少两种尺寸；这是条件路由/形状检查，不是模型质量。真实GPU只对照一例；采样外观明显失败即停，不追加窗口/换参数；无明显问题时也须用户完整播放才有动态接受。

**跨题材与长期门槛。** 正式推广前还须覆盖人物、非人主体、产品/静态场景，以及固定镜头/跟拍/有意运镜、主体或场景有依据切换、至少两个真实续写边界和更长链的外观/运动趋势。每类均需真实输入与完整观察；当前未提供/未执行的类保持未核实，不自动收费造样本。实验时长上限只是本次预算，不给产品添加全局时长上限。短对照即使改善也只作为集成候选，不把单视频交付冒充通用方案完成。

### 7. 色偏故障的分层诊断与精度对照

先核验源PNG/真实历史/图与输出RGB身份，再用安装原生VAELoader/VAEDecode执行真实encode/decode往返，不加载DiT、不做扩散。输入含通用灰阶/RGB色条、三张已有原图与9帧历史，保存输入/解码图、通道均值变化和像素差。均值仅排查全局通道/色域错误，不能代替局部外观或完整动态观察；若输入颜色已异常则先修真正负责的编解码模块并按生产规则回归，不给单题材加色彩特判。

若往返未复现明显蓝偏，单独检查此前主动将FP16源权重按原生UNETLoader转FP8的影响。新增隔离case从已完成的reference+history graph复制，只改变一个UNETLoader的`weight_dtype: fp8_e4m3fn -> default`，保存其余节点/参数/提示逐项相等证据；保留相同参考、历史、latent形状、seed、sampler与53/41帧预算。以checkpoint header核实源F16，并要求真实服务日志确认`model weight dtype torch.float16, manual cast: None`，不能用default参数或文件名代替实际精度。加载仍用安装原生meta/lazy及文件映射、动态显存，不修改Comfy或自建量化；启动前记录物理内存/commit余量，资源不足停止，不自动退回FP8。

独立目录`D:/VideoSi/cache/video-ai/logs/jim-08-color-diagnosis-20261021/`，`color-probe.json`和`precision-case-001.json`是案例输入，`probe_vae_color.py`为原生往返探针、`precision_trial.py`为唯一原精度对照、`test_precision_graph.py`核验仅加载精度变化、`precision-preflight.json`记录资源/权重/差异。旧研究helper/intent/结果保留，不改写旧文件或在旧目录重POST。原精度试验至多一个独立intent，完整结果未知时只查原ID。

对照输出仍需原生帧数/参考latent裁除/来源/像素/PTS核验。静态明显偏色/变形即失败并停止，无静态问题也只能记筛查通过、等待完整动态观看。单精度对照不能证明量化是所有色偏的原因，更不能证明通用生成/长链已完成。原run3011项、378项生产基准及原模型完整SHA前后核验；未改生产不虚报新裸全库。

后续证据驱动的时序输入对照：FP16样片仍复现蓝偏/形态变化后，不再调精度。此前真实历史只覆盖0.5秒首末时间间隔；在同一继续修复授权下，再用一个独立案例检查更完整运动历史。按原生fps计算`H=round(1.5*fps)+1`，本例H25，真实保留父帧索引[68,93)，逐帧原生RGB校验；原N41新增不变，按4n+1预算G69，参考增加1 latent后采样19位置，先trim1再解码69，取[25,66)为41新增、丢3尾帧。模型FP16、参考、提示、seed和sampler保持；改变历史及相应生成张量预算，不声称与旧形状逐元素同噪声。1.5秒是本次试验自变量，不是产品固定值或长场景上限；通用历史窗口必须按模型上下文容量、动作所需时域及新帧预算表达。`history_trial.py`接受外部case/G预算；原CPU节点覆盖H5/H9/H25并额外校验实际25帧LoadImage与原生父帧RGB一致，才允许此唯一GPU提交。结果仍失败则停止这条VACE输入组合，不叠加其他参数猜测或将局部调色当修复。

混合后端与初始生成的架构诊断：历史25帧仍有外观问题后，停止以旧Wan2.2父片直接验证VACE2.1续写，不继续拉长上下文/改采样参数。继续修复范围内用同一已下载VACE原FP16做一个独立首片探针：reference仍为原选图，去掉所有control_video/control_masks及其历史LoadImage，H0/N53/G53，参考latent仍trim1；提示删去不存在的历史/翼拍阶段承接语句，其余外观、环境与当前动作仍来自案例。它是reference-to-video初始生成，不是原片续片，不能与旧父片拼接冒充衔接，也不能继承旧首片接受。首片若静态外观失败即停止，不生成该新后端的续片；若仅静态无明显问题，等待实际完整播放反馈后再设计同后端跨窗验证。

通用实现须把“首片生产后端/权重身份、续写后端/权重身份、兼容性验证”与参考/历史一并记录；相同图片或帧率不证明跨后端运动/风格兼容。同后端是待验证方向，也不保证自身不会漂移。上述首片由`initial-case-001.json`外部提供内容、`initial_trial.py`执行；原生CPU额外覆盖H0的reference-only条件与动态trim，图检查必须证明旧历史节点完全移除。没有把VACE初始生成或混合后端续写未经证据注册为生产能力。

### 7.1 追加偏蓝定位：条件边界、文本与收敛

用户最新指示优先查明偏蓝、由助手选择修复并记录。因此当前先完成已有模型内的因果调查，第8节候选保持未执行；不把历史“停止追加”误当成禁止继续检查，也不静默改变原生16fps契约。

在图像/RGB与VAE往返证据之后，新增两个边界检查：①真实VAE分别执行安装VACE节点和捕获官方条件函数，经安装 `WAN21_Vace.extra_conds` 后逐分区比较模型实际96通道条件，含reference的第二半区归零与mask打包；官方VAE适配器的边界假设必须明示，不能把shape探针或共用VAE当完整官方推理等价。②用安装 `CreateVideo` 及其 `save_to` 写入路径，对灰阶/RGB色条、三原图和真实历史末帧做8bit/sRGB/H.264往返，报告均值、MAE及可查原件；这是编码路径诊断，不用全图均值替代局部外观验收。

文本比较先验证token。官方ftfy预处理若产生标点差异，应单独记录，再固定相同token对照已有原BF16编码和FP8编码，不能将清洗/量化/截断混为一个原因。原BF16条件以已有原生 `ConditioningLoader` 读入，固定原DiT/参考/真实历史/seed/采样器，不用新自定义节点覆盖安装包。真正推理后仍要核查颜色、形态和环境光照；partial改善不作生产能力。

采样收敛须先核查实际sigma序列及已存上游默认值，才定义一个单变量对照。当前原生20步/simple/shift8终止前sigma0.296296；已有官方VACE函数默认50步，但其flow UniPC、shift及CFG不能冒称与安装UniPC相同。唯一受控探针仅20→50步（本机末sigma0.140351），固定原FP16+FP8文本baseline，不叠加上述BF16文本、CFG/shift/新seed。若失败则停止此方向的参数迭代，记录尚未获得外观保持，而非将“每帧独立采样”作为已证实机理：视频扩散具有时序结构，当前问题是生成轨迹中的外观漂移，具体主因仍须由证据界定。

所有helper以外部case/graph供给题材和输入，独立证据在 `D:/VideoSi/cache/video-ai/logs/jim-08-color-trace-20261021/`；保留每次前置失败及修正，不重写旧intent、不重复POST，不以通用诊断helper等同跨题材长链画质已通过。

### 7.2 颜色失真：多分量指标与flow引导对照

用户将问题纠正为“颜色失真”并允许外部资料。蓝偏仅为此前样例表现；需区分色相/色度/饱和度变化、亮度与对比度、高光/暗部截断、纹理退化及运动/构图本身变化。既有B-R均值往返只能排查全局通道故障，不能因此宣布其他失真均不在编解码或采样路径。

外部[VACE#44](https://github.com/ali-vilab/VACE/issues/44)有相同复合退化的多方报告，维护者由mask猜测转向分别排查VAE/VACE。外部存在相互冲突的经验，须记录来源与适用环境，不复制“换loader/升分辨率/固定CFG”作为本机既定根因。[社区refine工具](https://github.com/bbaudio-2025/ComfyUI-SuperUltimateVaceTools)源码会混白、去饱和、模糊历史并可能作后期色彩匹配，当前只阅读，不能改已核验原生历史后仍声称像素不变或接缝通过。

新增标准sRGB/D65 CIELAB诊断，逐帧记录L、chroma分位、亮度对比度、截断比例、色相直方图与Laplacian方差；已知历史输入/真实VAE往返/DiT重建可配对DeltaE76，新运动画面只作不配对分布诊断。新帧的统计变化也受取景/运动影响，不以降低某个分数自动通过外观，更不把白色/某个主体的分割规则写入通用helper。

若已知历史重建与未来生成均出现对比度/色度改变，检查生成阶段CFG幅度。安装原生RescaleCFG明确具有CONST/flow分支，先用5维批/时序张量验证multiplier0等于原CFG、0.7等于独立公式、常量输入有限、被动审计hook逐值不改变返回及源model/options。只在CPU检查成立后，允许一个隔离对照：原FP16 DiT、FP8文本、20步、CFG6、shift8、seed/参考/历史/shape不变，唯一主动变更是原生RescaleCFG默认0.7；不得同时改文本精度、步数、seed或历史调色。白名单hook只记录同一采样轨迹内普通CFG与实际rescale幅度，不能称作重放完整未rescale轨迹。额外保存未裁参考latent、解码原始PNG和原视频，核对PNG中的graph身份，直接区分生成失真与视频编码误差。

其结果须同时评估主体/环境颜色、亮度、细节和真实运动，不把反饱和或整体变灰记为颜色忠实。若失败则停止此倍率方向，不做0.3/0.5/0.9的参数扫描；重新考虑经训练的外观/时序锚定机制。外部研究SVI Error Recycling可作为后续候选依据，但官方明确需要正确padding/模型版本和历史策略，不能把SVI LoRA直接挂到旧Wan/VACE工作流或继承旧接受。本轮只读其主分支/Wan2.2分支说明，未下载或运行新权重。

### 7.3 SVI Pro隔离可行性验证（Rescale失败后追加）

上段“只读”保留为研究初始时点。Rescale实际失败后，按用户此前“自己找方案修复”及本轮继续排查/外部资料授权，继续必要、可逆的本地隔离验证，不替换生产后端、不变更正式run或验收契约。只新增SVI Pro高/低两个LoRA到独立目录，上限3GB；Hugging Face镜像与官方README指向的ModelScope双清单已核对同一大小和SHA，两文件各1,226,928,552字节、合计2,453,857,104字节。HF revision `f9bdd50c57e4c28f0d088b6bad8afa3fdc3bc1ac`，高SHA `299b33006863194d077a43bc0abf16fc52963457657d867763f2b61fd6a9bd52`、低SHA `e8fcce153df0f5a2b49a17c2f82bd795002f0e3b35f25d6922da9cfe072b9c0b`；ModelScope逐文件不可变Revision及原metadata收据一并绑定。下载必须流式限长、完整SHA后原子改名，失败停止，不安装新包/覆写Comfy/下载其他基础模型。

复用现有Wan2.2 I2V高/低FP8-scaled、原Wan2.1 VAE和文本编码器；作者推荐FP16，故此可行性验证有明确量化限制，失败不能据此否定SVI官方FP16效果，成功也不能直接完成通用准入。原生示例16fps（附件SHA `f39087eb816320c9877e00b5f506d878d742f24431d94c9c289ebbff8f630660`）及固定版本KJ `WanImageToVideoSVIPro` 条件类已取得；只抽取审阅后的单个条件类到隔离白名单节点，不安装整个社区插件包。

先做CPU语义验证：anchor放第一个latent、续片只取上一段真实采样latent尾1、padding须为Wan21.process_out(0)，正反条件均绑定，源latent不变；不用重新编码尾部RGB代替latent。使用81生成帧、832×480窗口，首段81全部保留；续段按官方Pro示例丢前5个anchor/motion上下文像素帧，新增76，不做crossfade。不同窗使用各自冻结的不同seed，区别于此前单因素对照固定seed；它是此训练方案的协议，不能当泛用所有后端规则。最多3窗（81+76+76=233帧、16fps=14.5625秒）以覆盖两个真实接缝，任一窗明显颜色/身份/环境失败即停止，不产后续窗口。

首图与内容由外部case提供、阶段提示从实际状态构造，不在通用helper写主体/颜色特判。50步Euler/simple、shift5、CFG4、不加LightX2V或其他LoRA；高低模型切换按实际sigma首次低于0.875的位置推导并记录。保存每窗原始采样latent和PNG、完整graph/intent/原ID、raw色彩指标和不混合审阅轨。每窗一次POST，不确定只查原任务；前一窗静态筛查通过才允许下一窗，动态仍待真实完整观看。此处只验证新机制可行性，不替换旧选图、已接受首片、音频、463帧正式时间轴或跨题材验收。

通用生产集成的后续约束（本节隔离试验不等于已集成）：将backend能力、固定参考、真实latent状态、镜头/光照意图分别冻结。81帧/5上下文/不同窗seed是当前SVI Pro训练协议，不是给所有视频设置时长上限；任意更长场景仍按81首窗+76新增窗预算，最后一窗只保留所需新增内容。**终窗若丢弃尾帧，不得把含有这些未保留帧的完整末latent再传给后继**；终窗标为不可直接续接，扩展场景须显式新修订并重新规划，或另行证明可从真正保留位置恢复latent。不能用未显示的未来帧绕过原“只消费真实保留父帧”的规则。

缓存必须同时绑定scene/reference选择、VAE及其缩放/latent格式版本、基础模型/LoRA/采样profile、生成/保留帧映射和原任务ID；RGB容器/最后一张PNG与原采样latent不能互相冒充。新策略不能把没有原latent的旧Wan首片直接恢复为SVI续片；当前全新首窗不继承旧human接受。不同scene按各自已选图/明确的光照变化建立锚，不能把一个案例的暖光/白色、固定背景或静止镜头写进通用代码。不同窗seed仍需在冻结身份中可重复推导，恢复同窗保持原seed且绝不重POST。

### 7.4 SVI候选被否决后的颜色失真定位（2026-10-22）

用户真实反馈“这次画面颜色偏红，完全不对了”，7.3三窗候选颜色验收失败，不可纳入通用生产。旧内部静态筛查只用于控制实验，不能覆盖这次明确否决。失真范围涵盖背景/天空/曝光与主体材料，不以主体某些白色部分尚可判全幅通过。

不重复已有采样步数/seed/CFG盲扫、不调色减红。先保留用户意见和确切审阅SHA，核对原图/anchor、原始PNG/graph/cache及容器色彩信息。随后一个有界单因素首窗：相对7.3原首窗，只将正向提示的“清晨暖金色湖面上”改为“原图所示的湖面上”、“暖金色光线”改为“原图光照”。这检验预设暖光词是否把保持原图误变成文字驱动重染；不是已证实根因。保持原seed、同anchor/FP8模型/LoRA/VAE/负向词/50步/高低切换/81帧/16fps，graph归一仅这一个text字段差异。外部case保留题材词，通用runner不加颜色或主体分支。最多一个新首窗，不续接此前被否决的链，不自动执行第二窗或引入新权重。原始PNG和latent完整保存，结果不论成败均记录；首窗失败则停止该方向，不要求用户重复审阅明显失败样片。

新证据目录 `D:/VideoSi/cache/video-ai/logs/jim-08-svi-color-rejection-20261022/`。原始帧和4×4网格的CIELAB分量仅用于定位，运动/新景物使未来帧不是配对真值；不把全图红通道均值下降当忠实证明。FP8基础与文本仍未排除，也不由外部作者建议就断定根因。没有下载基础权重、修改正式运行、改变时基或放宽准入。

### 7.5 同架构基础模型来源精度的受控核验

7.4提示词对照失败后，依据作者FP8颜色问题提醒，只检验下一项尚未隔离的来源精度，不再对CFG/步数/seed扫描。真正FP16高/低Wan2.2 I2V基底各28,577,914,792字节、合计57,155,829,584字节；只读API固定revision `ee6f4a40737a995bf5818954cfce6d59443b0f04`，高SHA `c21c21efa368d529a982a7d89dd11d86608b5937cae9a125d0ffe5491918a100`、低SHA `edb89340c8a6fbf1a70e76a839ae01eaf7d289f05ea1ebd6b1a3fc6f533826e9`，路径由官方Comfy Manager交叉核对。用户既有自行找方案修复/继续排查授权下，在 `D:/VideoSi/models/jim-08-svi-pro/fp16-base/` 做可逆隔离新增；不覆盖现有FP8/生产配置，不安装包、不切新架构或时基。此次范围为两个基底且总下载上限60GB，传输预算15分钟，完整SHA通过才原子改名；部分文件保留并明确未就绪，不使用不完整权重。

D盘容量前检443GB可用，要求在确切下载量外保留10GB；旧VACE原精度28GB可运行只作资源可行性支持，不证明本双阶段模型的RAM/VRAM峰值。先核验新模型header架构/形状与现有LoRA400层兼容，再最多一个新首窗；加载失败/OOM直接停止，不默默降精度/尺寸/步骤。对照7.3原首窗（不是叠加7.4提示修改），同一原始暖光提示/seed/anchor/LoRA/FP8文本/VAE/50步/81帧/16fps，只替换两个DiT来源FP16。保持FP8文本是隔离变量，不能把此项叫作官方完整全精度复现。需要独立的generic runner仅增加由case模型目录驱动的搜索路径，采样图除两个模型名外应相同，先验证图差异再推理。

证据根 `D:/VideoSi/cache/video-ai/logs/jim-08-svi-fp16-validation-20261022/`，不得继承旧三窗或7.4颜色接受；原图/原始PNG/latent与完整来源身份、无混合审阅逐帧保存。结果仍需以参考外观/光照筛查及真实动态观察判定，失败即停，不扩大为无限模型试验，不宣称修好通用生成。

### 7.6 原精度DiT之后的文本编码路径核验

7.5的真实FP16 DiT首窗仍未通过参考外观/光照，不能把FP8 DiT认定为充分原因，也不能把仍有FP8文本的该试验叫完整原精度。复用已存在 `D:/VideoSi/models/skyreels-v3/SkyReels-V3-V2V-14B/models_t5_umt5-xxl-enc-bf16.pth`、SHA `7cace0da2b446bbbbc57d031ab6cf163a3d59b366da94e5afe36745b746fd81d`，不下载其他权重。先用已有探针读取本次实际首窗graph，强制相同native token IDs，分别取得native FP8和原BF16条件；记录token清洗差异、真实embedding数值/有限性。embedding不同不证明颜色根因。

后续最多一个首窗，相对7.5只把文本条件来源替换为原BF16路径缓存；原FP16 DiT/LoRA/seed/原prompt/anchor/50步/81帧/16fps保持。缓存经真实原生ConditioningLoader逐值验证，prompt SHA、token文件、encoder/缓存/graph身份全部绑定；不使用此前续片的旧embedding冒充当前首窗。native token IDs是为了隔离文本路径，和官方ftfy清洗的差异保留，因此也不声称完整官方独立复现。generic runner可消费外部冻结conditioning文件，不写题材/颜色分支。

证据根 `D:/VideoSi/cache/video-ai/logs/jim-08-svi-all16-validation-20261022/`。串行执行文本探针/加载检查/一次采样，不与GPU或其他Python任务并行；若加载、数值或外观失败即停该链，不继续扩大模型或参数扫描。没有正式后端/时间契约变更、没有生产源码修改或自动接受。

### 7.7 FramePack-F1隔离研究：不同参照/历史机制，不替换正式时基

三个SVI方向均未修复外观后，停止该组合的参数试验，调查F1的固定首图latent、SigLIP视觉条件及分层历史机制。用户明确授权为“自己找方案修复/继续排查”及通用视频方案；本节将其解释为允许必要、可逆、隔离的候选研究，不代表用户已确认30fps生产契约。原正式run的16fps/463帧、选图、音频/字幕和接受记录保持；研究原件使用模型真正30fps，不冒充原生16fps、不进入旧run。下节原先把研究也挂起的范围由本节有界研究替代，正式集成仍须独立修订、验证及实际观察。

代码pin `lllyasviel/FramePack@97fe5dbe06ac1f337ece08935b1076a35eefeeb9`。实际消费3仓库的25项资产合计42,866,789,142字节，revision及逐项身份在`jim-08-framepack-source-check-20261022/resource-inventory.json`；不下载原Hunyuan transformer或原版FramePack。上限60GB/900秒传输，落独立`D:/VideoSi/models/jim-08-framepack-f1/`，完整LFS SHA256/普通Git blob SHA1通过才原子改名。先下载非权重配置/分词文件；真实全模型meta状态1274键与checkpoint index完整一致、12,874,314,816参数对应25,748,629,632字节16位数据，文本/图像/VAE跨组件维度匹配、提示未截断后再传大权重。

预检发现真实依赖冲突及cv2缺失，已仅在D盘独立`python-deps`对齐diffusers0.33.1、transformers4.46.2、accelerate1.6.0、tokenizers0.20.3、huggingface_hub0.30.2及opencv-python-headless4.11.0.86；保留原失败收据，不覆盖Comfy或SkyReels依赖。Python3.13/Torch2.13与作者环境仍不同，不能声称完整官方复现。实际原类小尺寸CPU forward、UniPC4步、有限性、源历史不变及CPU generator状态恢复逐值相同检查通过；这些不算模型质量。官方`dit_common`会改进程内LayerNorm等，必须在专有子进程执行，禁止导入常驻Comfy进程或并行占GPU。

唯一采样配置：F1原BF16 transformer、原F16编码器/VAE、25步UniPC、CFG1、distilled10、rescale0、TeaCache关闭、官方native SDPA备用路径、保留6GB显存。使用case传入参考、动作/镜头/光照意图及caption；无主体/颜色特判。按640桶实际缩放，当前回归图应832×480。先参考VAE往返和首窗筛查，失败即停；最多9个9-latent窗，首37帧、后各36，最终325帧/30fps=10.833333秒，按实际核验，不是产品时长上限。首图后验采样seed与扩散CPU generator流分别冻结；每窗保存原latent/累积历史和RNG前后状态，不从RGB重编码回喂。

为适配32GB RAM，按阶段载入/释放文本、参考编码组件，再载transformer，避免GUI把全部模型常驻CPU。每窗内部静态筛查只允许继续实验，绝不代替human观察。审阅由完整累积latent的原生VAE解码产生，**不调用GUI的soft_append_bcthw生成窗混合**，不调色/冻结背景/插帧。官方VAE内部空间及时间tile合并属于解码算法，单独如实标明；不能声称底层完全没有tile加权。记录固定首latent与逐窗解码前缀变化，最终整段原样解码才是候选工件，不继承先前窗口的人为接受。该整场景渲染语义尚未集成旧逐clip生产/恢复契约。资源、数值、OOM或明显外观失败即停止，无自动换seed/尺寸/精度重试。

7.7首个隔离任务已在第二窗停止：73帧/30fps，主体右移并头喙出框，`failed_subject_framing`，没有第三窗或正式接受。短时颜色氛围较接近不能覆盖构图失败。追加唯一caption对照：优先描述与主体同步的跟拍和参考图像平面位置/尺度，再描述关节运动及真实背景相对运动；删除未证实的背景物名词。冻结原模型/profile/seed，首图latent和SigLIP条件从已核验缓存逐值继承，仅重新计算文本embedding并记录新case/缓存身份。先最多两窗筛查；若失败停止该方向，不自动扫seed/引导参数。若通过才继续原9窗研究预算，仍须更长链及其他内容/镜头意图回归。

7.7追加caption对照亦在第二窗停止，登记`failed_persistent_subject_tracking`：同一实际噪声/视觉条件下有减轻，但73帧时仍显著右移，未达到参考构图。两链技术审计、文本隔离及实际随机噪声逐值核验通过，不能覆盖外观失败；不再追加此方向的提示/seed/CFG扫描。当前没有满足本通用方案的已验证候选，跨题材及长链验证未开展。原版FramePack反向生成/未来上下文仅做官方源码比较，其训练权重和恢复语义另异，不能套用F1权重或直接替换正向历史；未新增该模型下载/任务。

### 8. 后续正式后端与时基选择（生产变更未执行）

本轮三个VACE原精度/历史/初始生成探针后，均未通过完整外观准入，停止继续换采样参数；同后端初始样片的白羽蓝偏明显减轻，但湖面/背景仍逐渐近白、光照漂移，因此不能把混合后端当作唯一原因或声明同后端就已解决。

建议下一候选采用已有调研的FramePack F1，从原选图建立统一首片/跨窗链，持续保留首图latent/视觉特征与分层历史。它不是已证实的修复，不能承诺所有题材或任意长镜头均稳定。通用协议同时保留身份/环境、动作/镜头、光照意图：只有本场景要求保持时才约束曝光/色调；叙事有依据的日夜/灯光变化要允许，不能把暖金色、固定背景或统一白平衡写入产品。

**须明确选择的时基变化：** FramePack F1原生30fps。建议通用后端按各自原生时基生成和保留运动历史，以真实PTS映射到最终16fps时间轴，保留完整原文/48k PCM/字幕及既定最终帧覆盖；源帧率/映射/补齐帧分别冻结和追溯，不把30fps标成原生16fps、不仅改FPS元数据或变速，不用最终重采样帧回喂原生历史。这将改变旧设计“所有源片原生16fps”的要求，必须用户确认后才能纳入实现契约。旧run仍按旧冻结配置恢复，新后端与时基只能走显式新修订，旧观看结论不继承。

**待批准的有限验证范围：** 复用[JIM-08长场景调研](JIM-08-industry-continuity-research.md#建议批准的一个探针)已写明的F1配置和最多9窗（推导325原生帧、约10.8333秒，实际按输出核验）。固定首图与历史、25步/seed/引导等不在试验中自动改动；逐窗先筛查，任一主体/背景/曝光失败即停止，明确保存未混合轨。原生30fps研究原件按实测时长交付，不裁到整数秒或换帧率冒充正式验收；只有真实完整动态观察后才能讨论正式集成及跨题材/更长链压力测试。本轮尚未执行该候选。

**资源范围历史与当前边界：** 此前HF超时、资源未核实和暂停研究是历史时点；当前仅按7.7推进可逆隔离研究，确切42.87GB清单及兼容检查已有收据。正式原生时基和后端集成的变更尚未执行，旧冻结契约保留；不以研究就绪替代实际质量、生产修订或最终接受。不下载未消费的原Hunyuan transformer/原版FramePack，不覆盖Comfy，不默默降精度/尺寸/时长。

## Files

- 隔离研究文件`D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/reference_trial.py`、`test_reference_graph.py`、`probe_native_conditions.py`、`evaluate_trial.py`：分别负责外部案例条件图/一次提交、原连接与参考裁除回归、安装原生节点CPU形状/路由、真实视频帧数/像素/PTS和采样对照；均为临时研究工件，不是生产模块。`case-001.json`绑定此次已有失败案例，`trial-001`保存唯一提交证据；这些案例专用数值不能写入生产路径。
- 创建 `docs/task-designs/JIM-08-verification.md`：五项验收表、命令及实际证据、失败/恢复、未核实边界。
- 修改 `README.md`、`config/README.md`、`config/jimeng.example.json`，必要时修正 `docs/jimeng-candidates.md`：实际可照做的流程与合法非秘密样例；不把 `config/production.example.json` 的旧默认策略改成新策略。
- 运行配置/文案及真实证据位于上述D:/VideoSi任务落点、原run目录和日志根；作者原文沿现有消费者提交，保留原时间和身份。
- 发现缺陷时只修改实际负责的 `src/video_ai/production.py`、CLI或原runtime/adapter/media模块和对应测试；不预先新建生产协调器、网络适配器、验收绕过入口或自选stage callback。
- 任务状态与后续记录仅使用 `docs/task-handoffs/jimeng-scenes-task-board.md`，本设计及入口交接为JIM-08准备工件。

## Tests

通用条件探针的独立目录为`D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/`，先bootstrap/Initialize，再串行运行以下命令；这些是隔离研究检查，不计作生产pytest或视觉通过：

```powershell
& $VideoAiPython -B D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/test_reference_graph.py
& 'D:/VideoSi/tools/ComfyUI_windows_portable/python_embeded/python.exe' -B -s D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/probe_native_conditions.py D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/native-cpu-recheck.json D:/VideoSi/tools/ComfyUI_windows_portable/ComfyUI
& $VideoAiPython -B D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/reference_trial.py D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/case-001.json D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/trial-001
```

图连接三项预期退出0；CPU收据必须使用未存在的文件名，证明两个尺寸/预算的原生条件及trim正确。第三条是本次已授权的唯一GPU执行命令；**其目录一旦存在，禁止重新执行来补单**，有intent只检查原prompt_id。退出0也只代表技术完成，仍须检查53帧/41新增/16fps、无混合审阅像素/PTS、实际外观和完整动态观察；原run3011项与378生产基准核对不变。其他案例的真实质量未运行时保持未核实。

每个新PowerShell Python调用先执行bootstrap与Initialize，均使用`$VideoAiPython -B`；Python/media串行，cache位于D:/VideoSi。以下为JIM-08实施计划命令，尚未运行，不复用JIM-07数量冒充新结果。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-08-regression'
& $VideoAiPython -B -m pytest tests/unit/test_jimeng_config.py tests/unit/test_reference_config.py tests/unit/test_scene_clip_records.py -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
& $VideoAiPython -B -m pytest tests/unit/test_scene_pipeline.py tests/unit/test_scene_revision.py tests/unit/test_scene_revision_records.py tests/integration/test_scene_pipeline_recovery.py tests/integration/test_scene_revision_flow.py tests/integration/test_scene_pipeline_cli.py -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
& $VideoAiPython -B -m pytest tests/unit/test_scene_media.py tests/unit/test_scene_media_records.py tests/unit/test_scene_upscale_transactions.py tests/unit/test_scene_final_observations.py tests/integration/test_scene_media_flow.py tests/integration/test_scene_composition_recovery.py tests/integration/test_scene_media_recovery.py tests/integration/test_scene_upscale_flow.py tests/integration/test_make_video_recovery_contract.py tests/integration/test_make_video_cli.py -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

预期各命令退出0，实际计数/时长/失败/修复逐次保存；缺陷回归先观察真实RED。若生产源码、测试或workflow变化，修复后另运行无路径`& $VideoAiPython -B -m pytest -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest`取得最终整组退出0与前后SHA。纯文档和合法示例调整用相关配置测试及链接/命令核对；未变生产版本的完整前置基线可引用JIM-07既有3552通过证据，并标明来源。

真实服务与观看按Approach逐步执行，不能放进默认pytest。至少核实：实际req_key与冻结值一致、TOS参考确被官方任务读取、真实收件与选择图片一致、三画面主体一致、两段连续完整观察、完整音频/字幕、两次完成重放与重复publish零新副作用。任何未执行项均不计通过。

## Acceptance

1. 替身端到端、故障及相关历史回归命令和实际结果落盘，发现的失败有修复与复测；不把前置或未执行测试冒充本轮结果。
2. 用户指定模型在真实官方请求/响应中可核对；原图、实际参考对象及官方参考读取成功有证据，能力不明时明确等待，不擅换模型。
3. `318575094@qq.com`实际收到含基准、候选及对照的邮件；用户实际选择和整组结论绑定确切候选/原图SHA，未接受时没有新Wan提交。
4. 同一主体至少三个画面及一个至少两段的连续长画面均实际完整观察，没有未解决的一致性问题；最终候选完整观看/试听/字幕核对后才显式正式发布，保留完整原文/PCM/时间轴。
5. 正式输出收据、两次普通续作和一次重复publish证明同run无新增图片、Wan、超分、编码、邮件或记录写入；模型/基准/父片变更失效及旧冻结恢复已有相应回归证据，使用说明覆盖等待、授权码、模型切换、选图/观察和显式返工。
6. 通用性补充：主体、场景、动作、镜头意图、固定参考、运动历史、时长预算均由输入/规划及模型能力决定；无白鹭/湖面/某run等产品分支。参数化条件验证、单案例真实质量和跨题材/镜头/长链真实质量分别有证据；后者未执行或未接受时不能宣称通用生成能力完成。已有五项正式交付要求继续有效。

## Risks

- 真实req_key/参考能力、AK/SK与SMTP授权、既有桶配置及最终文案尚未提供；它们由本任务配置阶段接收并核验，缺失即停止真实调用，不视作已验证或用示例替代。
- 账号权限、TOS URL可读取性、QQ投递及模型视觉质量只能实际联调/观察确认；技术与替身通过不保证实际画面或真实投递。
- 模型可能漂移，用户需要分批查看、完整播放及反馈；不通过不能发布，返工范围和收费动作保持显式。
- 本机真实推理/长片耗时未作保证；保留原有超时与无总帧上限，不改帧率或截短文案规避等待。
- Git元数据按当前约束只读；保留checkout，不创建分支/提交/推送。若后续用户明确改变约束，再按新授权处理。

设计自审：范围、接口、状态、输入缺失和恢复动作均使用已建立契约；没有新增产品选择或占位章节。模型参数、文案及观看结论是实施阶段真实输入，均有确定的接收/停止规则；READY只表示本设计可开始验收配置工作，不表示真实服务或样片已通过。
