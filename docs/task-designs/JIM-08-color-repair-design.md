# JIM-08：提示输入修正与 20 秒连续镜头验证设计

日期：2026-10-22。状态：用户已批准修复方向；本书面设计待审阅，尚未实施、提交推理或改变生产策略。

## 目标与已确认事实

修正当前视频提示中无依据的光照变化、跨场景动作及审计文字污染；在隔离环境验证单次生成 20 秒的可行性。保留通用视频生成目标：主体、场景和动作来自输入，不能加入白鹭、湖面或某种颜色的产品特判。

2026-10-22 本轮重新计算三个 scene 的父末 PNG 与子 start.png SHA，均相等；同场景父子 positive 相同、seed 不同。实际查看 scene3 接缝采样：续段内部羽色逐渐偏冷、身体变暗。旧请求 scene1 包含“环境光线随时间自然变化”，所有 scene 的 positive 均混入完整追溯 JSON。基准图虽在 comparison_images 中记录，但 graph_for 实际只接收一张 start_image。

已有 VAE、保存路径及精度对照没有给出充分修复；增加历史、锁定历史、VACE、SVI 和 F1 的失败结论继续有效。不能将固定 seed、多帧输入、原始精度或固定参考单独宣布为保色方案。

## 决策与执行范围

选择分阶段方案：A 修正并冻结视觉提示输入；B 单次 20 秒隔离验证；只有 B 通过完整观看和资源验证，才进入 C 的生产整段策略集成。A 的软件检查通过不等于颜色修好；B 的单案例通过不等于任意题材或任意时长均可用。

原生产配置、冻结 run、原图、首片接受记录、失败续片和既有推理环境保持可核验。既有工作区有大量未提交实现，不能重置、批量暂存或覆盖。新代码在能保留这些改动的隔离工作区实施；原运行仅作为只读输入。正式 16fps、完整原文/PCM/字幕与观察/发布门槛继续有效。

## A：版本化视觉提示输入

新增可选 raw 配置 scene_rendering，初期支持精确字段 prompt_policy 和 prompt_contract；无该对象时仍走当前旧 renderer。prompt_policy 必须为 visual_v2；prompt_contract 为独立 UTF-8 JSON 文件路径，冻结时复制进新 run 的 production/scene-video-prompts.json 并绑定文件字节与 SHA。只配置一项、未知字段或未知 policy 均拒绝，不能自动回退旧提示。

契约 schema_version=1，精确顶层字段为 schema_version、production_strategy、binding、style、clips、review。其中 production_strategy=paragraph_jimeng_v1；binding 包含 scene_plan_sha256、visual_bible_sha256、wan_inputs_sha256，分别绑定已准入的语义计划、共享设定和实际选图。style 是已审查的非空视觉风格描述；不能照搬旧 global_style.description 中的配音/字幕保存说明。clips 必须按已提交 plan.clips 顺序完整且唯一覆盖，每项字段为 clip_id、motion、camera、lighting、changes。三个描述必须是非空字符串；changes 为数组，每项精确字段 kind、description、sources，kind 只允许 appearance/environment/lighting；sources 必须给出 unit_id、text_start、text_end、quote，按原文逐字核验。

review 精确字段为 reviewer、review_method、verdict、reason、content_sha256；review_method 为 human_text 或 agent_text，verdict 必须为 passed，其他文字非空。content_sha256 对除 review 外的整个契约作现有 canonical_digest。它证明提示文本已核对，不证明视频已观看。草稿与接受记录分开保存，不自动将草稿标为通过。

纯 renderer 使用契约 style，并按当前 scene 的引用 ID 提取以下视觉字段：实体 label/fixed_attributes；外观变体 attributes；环境 environment/time/lighting/spatial_relations。缺少正式 schema 必需字段时拒绝，不以审计 facts 或 source quote 补齐。旧 global_style.description、source_facts、creative_choices、sources、原文坐标、审计说明和其他 scene 的动作保留在证据文件，不串入模型 positive。

每个 clip 的正向提示由上述视觉字段与该 clip 的 motion/camera/lighting 确定性组成，文本以明确标签分隔并用 JSON 字符串引用，防止换行伪造字段。不从句子中用关键词替换删除“金光”等词。契约草拟与文本审查根据原文、原图和动作阶段判断内容：无原文依据时不添加光照变化；原文明示日落、灯光切换、变装等变化必须保留并在 changes 中绑定依据。禁止用一个全局“冻结背景/主体/曝光”规则覆盖有意运动或光照变化。

首片描述从实际选图姿态开始；续片描述从父片当前状态继续，不重复完整动作起点或跨场景动作。续片具体内容若依赖尚未生成的父片状态，契约应采用不预设翼姿/速度等未知状态的持续动作描述；不能伪造对未来父末帧的观察。

接入点为 planning/scene_clip_continuation.py 的 build_scene_wan_plan 和 runtime/scene_clip_records.py 的 scene_context。新增 planning/scene_video_prompts.py 承担 schema/绑定校验与纯渲染；新增 runtime/scene_video_prompt_records.py 处理文件冻结、审查准入和新鲜 SHA。config.py、production_inputs.py 只增加可选配置和新输入身份。旧配置下 options、inputs、parameters、graph 及请求重建必须保持原值。

提示契约或 policy 变化属于视频内容变化，必须建立新修订：所有相关源片及其后代、观察、超分、合成、最终观察和交付失效；可复用已验证原文、配音、timeline、语义计划和选图。scene_revision.py 及对应运行层增加版本化渲染身份：旧身份 schema 按旧函数重建，新身份把提示契约 SHA 与 policy 独立绑定，不能把它们混入 planning_sha256 而迫使重新出图，也不能删除后漏掉失效。未知或部分缺失的新身份拒绝恢复。

## B：单次 20 秒隔离验证

采用独立证据目录 D:/VideoSi/cache/video-ai/logs/jim-08-color-repair-<唯一编号>/，不调用旧 run 的 make-video 来绕过 96 帧保护。初次案例只读使用原 run 20261021-014723-4ebdc1fecab2 的 scene3 所选原图及其首片已适配 PNG；实际 path/bytes/SHA 从原准入记录读取，绝不把题材写入通用 runner。该测试仅生成无声的长镜头诊断样片，不延长原旁白或替换原 scene 时间轴。

冻结 case.json、graph.json、模型/工作流身份、输入图和本次视觉提示。现有 Wan2.2 双专家、768x432、16fps、40 步、CFG3.5、Euler/simple、15 步切换保持原设定；seed 使用该案例原首片 seed，记录改变 length 后噪声张量不同，不能声称逐元素同噪声。请求 321 帧，精确保留原生 [0,320)，只丢最后一帧，得到 20 秒；不得把输出裁成多段后冒充独立续写成功。

执行前重新核对资源、权重和输入身份、空闲显存/内存及服务拥有权；只能启动自己的服务，不终止桌面或外部进程。本轮只读显存快照为 RTX 5090 D v2，24455 MiB 总显存、1623 MiB 已用；这不是 321 帧可装入显存的证明。由现有 frozen 配置读取有限推理期限，不设无限等待；执行时采集真实显存/内存、耗时与服务日志。

仅一次 POST；意图、UUID 和原始 HTTP 先持久化，结果不明只查询原任务，不补单。OOM、超时、非法输出或明显外观失败均保留现场并停止；不自动降低分辨率、帧率、时长、精度或重试 seed/CFG。原始模型输出、原始帧、精确保留映射、审阅副本和播放时间戳分别保留。

已有原片与本次样片同时改变提示和生成长度，因此 B 只验证整个候选方案是否可用，不用于声称某个变量独自解释改善。原始帧提取不做调色、混合、稳定、居中、冻结、循环或插帧。

## 颜色与动态验收

在超分/成片编码前检查原始生成输出。报告逐帧亮度/色度分布、高光/暗部截断和采样图；已知同内容重建可计算配对色差，运动后新画面只作不配对诊断。不能用全图直方图、白色主体分割或像素平均值自动宣布通过。

完整观看确认主体材质颜色、环境光照、构图和动作在 20 秒内没有无依据变化；正常受光面变化、新露表面或运镜不一律判错。静帧查看只能记录采样外观，human_video 或实际具备完整播放能力的 agent_video 才可给动态通过。若静态已明显失败则停止，不请求用户重复接受已知失败样片。

候选须同时有技术通过、完整视频观看通过和资源记录；任一缺少均不得接入生产，不继承旧首片的“正常”。本案例通过后仍需不同主体/材质与另一种镜头运动验证，才能表述跨题材能力；当前不自动下载新后端或追加这类 GPU 任务。

## C：有条件的后续集成

B 失败时止于失败证据和下一步架构判断，不启用 whole_scene_v1。B 通过后，沿既有 JIM-08-whole-scene-proposal.md 的执行预算、修订失效和全消费者适配设计，增加显式 scene_rendering.mode=whole_scene_v1；缺省 segmented_v1。预算必须统一用于源片、裁剪、映射、超分、合成和观察，不能只移除 96 帧 guard。

20 秒整段路径只代表该资源/时长的能力。原要求的多片连续链验收仍保留为未完成；不得以整段生成替代并标为通过。更长镜头若需要窗口续写，必须另有经训练支持的后端协议及真实动态验证；不重复把已失败的单帧、9 帧或 SVI 组合标为修复，也不默认改变时基、切镜或下载模型。

## 软件检查与交付证据

A 先 RED/GREEN：新增 tests/unit/test_scene_video_prompts.py 验证精确 schema、内容/审查 SHA、原文变化依据、完整 clip 覆盖、不同阶段提示、审计字段隔离、多题材纯渲染和不可变输入；新增集成用例验证旧请求逐字段保持、契约漂移时零新提交、渲染修改正确失效且不重新出图。既有 tests/unit/test_scene_clip_continuation.py 与 tests/integration/test_scene_clip_generation.py 的旧模式断言必须保留。

B 的通用预算与恢复 helper 单测覆盖 320 保留/321 请求/[0,320)映射、重复执行不二次 POST、输入/模型/graph 漂移拒绝、失败不降规格、不会写回源 run。替身测试不能登记真实 20 秒能力。

所有 Python 命令先 dot-source scripts/bootstrap.ps1，再调用 Initialize-VideoAiEnvironment；用 $VideoAiPython -B -m pytest，独立 basetemp 位于 D:/VideoSi/cache/video-ai/temp/。定向命令覆盖上述新增文件与 tests/unit/test_scene_revision.py、tests/integration/test_scene_revision_flow.py、tests/integration/test_scene_pipeline_recovery.py；集成完成后执行裸全库。测试与 GPU 推理串行，日志保存命令、退出码、当前源码和旧输入前后身份。

实施后的最低定向检查命令如下；新增测试名随实现提交，本设计阶段不运行不存在的测试：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim08-color-repair-targeted'
& $VideoAiPython -B -m pytest tests/unit/test_scene_video_prompts.py tests/unit/test_scene_clip_continuation.py tests/unit/test_scene_revision.py tests/integration/test_scene_clip_generation.py tests/integration/test_scene_revision_flow.py tests/integration/test_scene_pipeline_recovery.py -q --basetemp "D:/VideoSi/cache/video-ai/temp/color-repair-$VideoAiCommandId"
```

预期全部通过、退出 0；必须另补新契约冻结/恢复集成测试及 20 秒诊断 helper 的检查，再进行裸全库和真实 GPU 验证。

阶段交付分别报告：提示软件修正、20 秒技术结果、采样外观、完整动态观察、生产集成及跨题材能力。颜色修复完成必须有真实生成和观察依据；目前仅书面设计完成，尚无上述新结果。
