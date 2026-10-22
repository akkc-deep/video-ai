# JIM-07 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution, or superpowers:subagent-driven-development if the user selects delegation. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 接通新策略的可恢复全链路，支持显式修订、正确的局部失效与可核验继承，并保持原运行证据不变。

**Architecture:** 协调器调用原阶段 API，透传各阶段结果；内容依赖图和准入图分别决定重做范围与观察门槛。修订准备独立于执行，通过目标冻结 options → commit → imports → 原来源/本地副本绑定继承证据；读取器只对已注册视图启用继承。

**Tech Stack:** Python 3.12、pytest、PowerShell bootstrap、既有 RunLock/PathPolicy、HTTP/SMTP/TOS 替身、真实 ffmpeg/ffprobe/PNG/WAV/MP4。

**Spec:** `docs/task-designs/JIM-07-design.md`，完整字段集合、签名、状态、路径和失败规则以此契约为准。

## Execution status

- 已读任务设计及 JIM-07 交接，核对任务板状态为 READY。
- 用户已明确“那就按原计划执行吧”，本会话原生实现和验收已完成；最终全库3552通过，364项身份一致，详见 `JIM-07-verification.md` 和进度账本。
- 修订证明、冻结加载和各阶段读取器相互依赖，由当前会话集中实现；不派发逐任务实现代理。
- Git 元数据按交接为只读；使用 C:/Program Files/Git/cmd/git.exe 只读核对。保留现有 checkout 和前序成果，不创建分支、提交或改变 Git 元数据。

## Global Constraints

- 保留 `paragraph_jimeng_v1`、原生 16 fps、cut、1920×1080、完整原文/PCM/字幕和现有模型。视频总帧数不设上限，帧率不变。
- 不修改旧 shot/schema=1 的状态机、审核和交付协议；不把新策略阶段写成旧 shot 完成记录。
- 普通 schema=2 不增加字段；`scene_revision` 仅在新建修订冻结分支存在，不迁移旧 options。
- 原任务未知时只核对原 ID，不自动重复 POST、刷新原请求 URL 或重发邮件；显式返工才建立新 logical node。
- image-selection、clip-observation、final-observation 只消费原文并返回；普通续作不自动发布；publish 才交付。
- 来源目录只读；目标写入须持目标真实 RunLock，遵守调用线程、路径限制、不覆盖晋升和 file-ID+SHA 所有权检查。
- 任何有效修订都重新产生 composition/final_review/delivery；内容复用不能绕过当前整组/全片准入。
- 不实现自动收信、自动付费返工或自动观察通过；不调用真实云/模型/SMTP。真实账号及观看验收属于 JIM-08。
- 每次 Python 调用先 bootstrap、使用 `-B`；运行、媒体、缓存、日志存于 D:/VideoSi，Python/media 测试串行。
- 所有新增结果、请求、记录及视图使用设计规定的精确字段；拒绝额外字段、bool 数值、跨运行身份及路径逃逸。

## Review Focus

1. 已交付证明损坏时在加锁、日志和 invocation 前只读 blocked，不能回退到生成；Task 7/8 设置全部副作用失败哨兵。
2. 来源只有部分分支合法时，按节点及必要祖先验证；失败分支不能污染独立已接受分支，也不能遗漏目标分支的失败原文；Task 2/5/8 覆盖。
3. 来源为空日志、缺失路径、同 stat PCM 或目录清单在准入后变化必须停止；Task 2/3/5 在捕获和复制/提交之间注入变化。
4. 二次修订的合法共享祖先不算循环，真正循环/冲突 commit/丢失 owned 原证据必须拒绝；Task 3/5/8 验证。
5. 失锁、清理或最终记录失败不能继续返回 ready/delivered 或由过期线程写 invocation；Task 6/7/8 检查结果降级及主异常保留。

## File Structure

- `planning/scene_revision.py`：纯请求验证、内容/准入双图、失效/复用计划。
- `runtime/scene_revision_records.py`：只读 commit/import 校验、RevisionGuard、来源/视图解析。若需拆分，复制事务放入 `_scene_revision_copy.py`，节点来源准入放入 `_scene_revision_origins.py`，避免单文件承载全部职责。
- `runtime/production_scene_revision.py`：来源快照、目标意图、继承复制/视图提交、冻结恢复和 SceneRevisionResult。
- `runtime/scene_pipeline_records.py`：ScenePipelineResult、公共前缀、固定输入、invocation 和只读进度。
- `runtime/production_scene_pipeline.py`：阶段顺序、设置绑定、结果透传和注入边界。
- 修改 `runtime/production_inputs.py`：条件修订冻结和结构加载，不在 loader 递归调用完整语义 require。
- 修改 `runtime/image_selection_records.py`、`reference_settings.py`、`reference_image_records.py`、`scene_clip_records.py`、`scene_media_records.py`、`_scene_upscale_records.py` 和 `production_scene_composition.py`：显式 inherited resolver、指定节点准入及守卫传递。
- 修改 `production.py`、`cli.py`：入口分派、参数校验、consume-only、publish-only、revision-only 和完成只读快路。
- 新测试文件沿设计的六个专项模块及 `tests/scene_pipeline_helpers.py`；使用现有 `scene_clip_helpers.py`、`scene_media_helpers.py` 和历史公共入口恢复测试作参考。
- 使用文档 `docs/jimeng-candidates.md`；验收记录 `docs/task-designs/JIM-07-verification.md`；任务板仅记录实际状态和验证证据。

### Task 1: 纯修订请求与双依赖图

**Files:** Create `src/video_ai/planning/scene_revision.py`, `tests/unit/test_scene_revision.py`.

**Interfaces:** `plan_scene_revision(snapshot, request, target_identity) -> dict`，输入及返回精确字段见设计；纯函数不读取路径、不发请求。

- [x] 第一个实现动作是创建 `test_reselected_baseline_invalidates_reference_descendants_but_preserves_unrelated_scene`：完整有效快照含 S1→S2→S3 参考链、独立 S4 和各自 clip 父子链。重选 S1 已完成候选，断言 S1 技术候选 reusable、S1 choice dirty、S2/3 image/choice dirty，S1/2/3 clip/upscale dirty，S4 媒体 reusable；image_group 和所有 composition/final_review/delivery dirty。
- [x] bootstrap 后运行下文首条测试命令，保存缺模块/接口的 RED；随后实现纯算法，再运行同命令取得 GREEN。
- [x] 先补矩阵测试再实现 reselect_images/regenerate_images/regenerate_clips/reconfigure：clip 返工只传播 continuation 后继；无关 scene 切镜不形成父子边；准入边不传播内容 dirty。
- [x] 覆盖 image/reference/Wan/upscale/公共配置分类，实际模型戳和 workflow 字节变化、同显示名称、无效无差异修订、邮箱变化拒绝、unknown/running 阻止新重复任务。
- [x] 覆盖所有 ID/choices 精确字段、UUID/带时区时间、规范摘要、唯一性和 plan 顺序归一；未接受/失败节点不 reusable，reselect 不使目标技术候选集合 dirty。
- [x] 运行 `tests/unit/test_scene_revision.py`；保存命令、RED/GREEN、计数和退出码。

### Task 2: 指定节点来源准入与 RevisionGuard

**Files:** Create `runtime/scene_revision_records.py` and optional `_scene_revision_origins.py`; modify the JIM-04/05/06 readers listed above; create `tests/unit/test_scene_revision_records.py`.

**Interfaces:** `RevisionGuard.verify_captured_bytes()`、`verify_global()`；`require_scene_revision(frozen) -> dict`、`require_revision_import(frozen, domain, key, *, context) -> dict`、`load_scene_common_prefix(frozen) -> tuple[dict, ProductionTimeline]`。完整 require 在冻结输入已加载之后调用。

- [x] 先测试孤立 sidecar、dirty 节点 import、owned/import 竞争、未注册视图和外部路径全部拒绝，普通 run 的 run_path 限制保持。
- [x] 从现有 reader 提取指定 image/choice/clip/upscale 节点及必要祖先的严格只读准入；核对原 request/graph/HTTP/history、实际媒体、比较图和接受原文，不要求无关失败分支已 complete。
- [x] 用变更故障测试驱动 guard：capture 原始字节及 JSON inventories/absent_paths/正或空日志/PCM；语义验证前后比较，不能将新字节重新绑定成基线。
- [x] 建立确切 view Artifact/规范摘要→import_id 注册；Origin store 只读且限定来源根；原 evidence 不当成当前 run Artifact。
- [x] for_root、store 克隆和下游交接传递同一 RevisionGuard；verify_global 检查锁和原有模型/工具约束，不虚构旧工具二进制 SHA。
- [x] 单元验证不调用网络、不补写证明；同字节新文件所有权、junction、空日志变非空和同 stat PCM 替换均拒绝。

### Task 3: 修订绑定的冻结加载与恢复

**Files:** Modify `runtime/production_inputs.py`; extend `tests/unit/test_scene_revision_records.py` and `tests/unit/test_production_inputs.py`.

**Interfaces:** `freeze_inputs(..., scene_revision=None)`；普通冻结字段集合不变，非空修订值是固定 `production/scene-revision/commit.json` 的 Artifact。

- [x] 测试 schema=1 拒绝 scene_revision、普通 schema=2 字段严格不变、旧 options 不可追加修订字段。
- [x] 测试后实现 loader 对 commit/imports/view 全部递归 Artifact、完整 UUID、固定路径、目标 config/model/workflow 身份的结构核验；loader 不回调当前 FrozenInputs 的完整语义 require。
- [x] 测试冻结前/后目标配置/模型/workflow 变化均停止；原文 BOM/换行原始字节保持，新输出默认新 run 路径。
- [x] 实现只受相同 intent 授权的修订冻结恢复：逐个检查已有小文件身份，未绑定的同名文件拒绝，普通 freeze 独占规则不放宽。
- [x] 测试合法共享祖先、多层修订、当前递归栈循环、同 run_id 冲突 commit 和替换中间 commit；缓存仅限一次调用且绑定 SHA。
- [x] 运行上述冻结及记录单元模块，保存结果。

### Task 4: 修订准备、身份复制和 durable commit

**Files:** Create `runtime/production_scene_revision.py`, optional `_scene_revision_copy.py`; create `tests/integration/test_scene_revision_flow.py`.

**Interfaces:** `create_scene_revision(source_run, request_path) -> SceneRevisionResult`；精确结果字段、目标目录、intent/import/commit/ready/copy-receipt 格式沿设计。

- [x] 先测试有效请求稳定定位同一目标、来源存在活锁拒绝、请求/源 options 原字节不匹配拒绝、准备期间零网络/邮件/编码且来源字节/mtime 不变。
- [x] 实现来源验证、target_identity、纯计划和目标持锁 intent；unknown/running 被影响任务不通过改 run 隐藏，原始请求在目标保存确切字节。
- [x] 测试驱动按 domain/key 摘要 token 和受验证 role/ext 复制，含带冒号 frame_id 的 Windows 安全名称；stream+fsync、copy-intent→copy-ready→不覆盖晋升，比较源前后 SHA、staging/target file ID。
- [x] 逐项故障注入：temp 创建但尚无 durable ready 时不接管，另建 UUID 保留旧尝试；孤立/冲突 ready、无所有权同字节目标拒绝；有确切 ready 可恢复晋升。
- [x] 按拓扑提交 views/import sidecars、imports.json/invalidation.json/commit.json；视图保留原执行身份，只重映射明示媒体，不改原请求或观察原文。
- [x] 调用修订冻结分支前后重核身份；最后写 ready.json，丢失 ready 时只从确切 commit/options 恢复，时间取 options.created_at。
- [x] 对意图、每个复制/晋升、view/import/index/commit、冻结小文件/options 和 ready 边界测试中断重放，同请求不重复创建新目标或覆盖来源。

### Task 5: 继承节点在原阶段中的可执行复用

**Files:** Modify the readers and composition helper from Task 2; extend revision unit/integration tests.

**Interfaces:** 原公共 require/produce API 签名保持；内部通过 `require_revision_import` 返回 owned 原记录或注册 inherited 视图。比较输入经 resolver 读取，替换 composition 第 336 行附近对当前 clip/request.json 的直接读取。

- [x] 先用新目标运行测试 common/plan/reference_settings/image/choice/image_group/clip/upscale 各域视图准入；普通 owned 路径历史用例继续通过。
- [x] 实现 common/plan 当前 run 身份重建、本地 PCM 真实 stat、clip/upscale 原执行身份保留；所有路径映射由 local_artifacts 一一证明。
- [x] 测试 reselect 保留原候选但选择仅为待确认草稿；图片变化后新整组观察必须重新提交。只 clip/upscale 返工且图片不变可显式继承原组观察。
- [x] 继承 clip 在当前组未通过时不能 ready；继承 upscale 在全部源片未接受时不能 ready；每个新提交/接受/发布前重核 RevisionGuard。
- [x] reference_settings 仅在 commit 证明目标有效内容相同后继承，后续冲突补充配置拒绝；旧 TOS 对象保留真实身份，新提交按原协议核对远端，不在准备阶段访问网络。
- [x] 真实媒体验证 S1 重选影响 S2/3，S4 已观察片段/超分零新推理；父片返工只传播其后继；二次修订追到最初 owned 请求，丢失来源原证据时零 GET/补写并 blocked。
- [x] 运行新修订专项及 JIM-04/05/06 受影响 reader/阶段回归。

### Task 6: 公共前缀、协调记录和阶段推进

**Files:** Create `runtime/scene_pipeline_records.py`, `runtime/production_scene_pipeline.py`, `tests/unit/test_scene_pipeline.py`, `tests/scene_pipeline_helpers.py`, `tests/integration/test_scene_pipeline_recovery.py`.

**Interfaces:** `produce_scene_pipeline(frozen, *, paths, logger, lock, reference_settings_path=None, email_settings=None, dependencies=None)`；`load_scene_pipeline_progress(frozen) -> dict`；ScenePipelineResult 仅允许设计规定的五个早期 stage 和错误状态。

- [x] 测试驱动 inputs/common-ready/invocation 的精确字段和幂等绑定；automatic 用原 speech/checkpoints，prepared 只接纳完整原报告/plan/PCM，inherited 用 commit 证明；半前缀拒绝，不虚构 TTS。
- [x] 构建 authentic fixture：接受前冻结 `max_clip_seconds=0.5`、正值 PCM，首 scene 为 13 个贡献帧，真实预算 5/4/4，并含独立 scene；不改已接受预算，保留历史 200 帧回归。
- [x] 接入 units/speech/timeline/scene_plan，再按批次推进 baseline/reference；baseline 使用确切 scene.image_prompt，混合非法批次拒绝。依赖注入仅限设计固定 adapter 字段。
- [x] 所有图片及组观察通过后，持锁生成/require Wan inputs；无参考批次也能形成合法记录。随后调用 clip→require clips→upscale→composition，最终普通续作止于 final_review_ready。
- [x] 任何等待/unknown/blocked/failed 透传原阶段结果，未知 SMTP 不自动调用 retry；本次每个新 logical node 至多提交一次；较晚阶段本地冲突先于较早新副作用预检。
- [x] 增加设计十个 boundary 点；单元测试逐边界中断后沿原接受恢复，invocation 只在清理和所有权复核后保存，过期线程不写。
- [x] progress 严格只读，由原证据推导精确 common/plan/images/clips/media；缺失、合法未完成和坏证明分别报告，不创建目录/标志。
- [x] 清理失败和失锁撤销 readiness 字段，保留主异常与清理原因及可供检查候选，不返回成功。

### Task 7: 公共 make-video、CLI 显式动作与只读快路

**Files:** Modify `src/video_ai/production.py`, `src/video_ai/cli.py`; create `tests/integration/test_scene_pipeline_cli.py`; extend pipeline unit tests.

**Interfaces:** make_video 添加 reference_settings/email_settings/clip_observation/final_observation/retry_email/revision/publish；CLI 添加同名设计参数，结果类型/原序列化字段保持。

- [x] 先写参数组合测试：六个显式动作互斥且要求 run_dir，publish 严格 bool，revision 与顶层配置覆盖互斥；旧策略及非法设置组合在 run 分配/加锁/发送前拒绝。
- [x] revision 在来源 RunLock/普通完成快路之前分派，只准备目标；目标配置不传入来源 loader。reference/email 设置稳定保存为提交 Artifact，SMTP 凭证仍只读环境变量。
- [x] consume-only 动作调用各原消费者后直接返回；retry-email 严格校验原 attempt hash 和原设置修复范围；publish-only 调用新策略交付，不顺带生成。
- [x] 新运行在构造旧 delivered 结果前分派；只共用前置阶段状态，不制造旧 shot 后续 checkpoint；旧 run/resume 命令保持。
- [x] completed 普通续作和重复 publish 在加锁/日志/invocation 前执行完整只读 require，返回收据验证的 movie/subtitle/receipt；坏交付证明只读 blocked；publishing 前缀仅显式 publish 恢复。
- [x] CLI 显示实际等待状态、模板/候选及续作命令；退出码等待=3、阶段 ready/accepted/delivered=0、blocked/final_review_failed=2、failed=1、interrupted=130；阶段 0 不宣称已交付。
- [x] 运行新 CLI 专项及既有 make-video/CLI/image-selection 回归，确认字段和 consume-only 行为兼容。

### Task 8: 全链路中断、篡改与回归验收

**Files:** Extend the six new test modules and helpers; retain existing authentic recovery suites.

**Interfaces:** 通过公共 make_video/CLI 执行，底层使用原 API 和真实媒体；用故障注入及计数断言证明恢复，不用任意 stage callback 绕过验证。

- [x] 跑完整原文→基准/参考图→真实 MIME→选择/组观察→两次父片等待→超分/候选→最终观察→显式 publish；验证完整 PCM/SRT/总帧覆盖和所有等待零越级提交。
- [x] 参数化覆盖 image submit/accept/result/download、TOS intent/object、SMTP intent/accepted、selection raw/accepted、Wan intent/raw/history/clip/observation、upscale frame/complete、materialized/encode/probe/candidate、final raw/accepted、delivery temp/rename/receipt 及协调器新增边界；同 logical node 原 UUID/graph/POST/邮件计数保持。
- [x] 两次 completed 续作和重复 publish，将服务/POST/邮件/提取/编码/复制/锁/记录写入全部设为失败哨兵；assert delivered 且清单、SHA、mtime、输出 file ID 不变；损坏证明同样零写 blocked。
- [x] 覆盖四种修订请求、真实配置/模型/workflow 变化及重新选择同字节候选的身份规则；核验正确 dirty/reusable、当前观察门槛、来源不变和继承阶段零新推理。
- [x] gate 后/复制前/POST 前改变 commit/import/source JSON inventory、空日志、PCM、媒体或锁；覆盖 junction、同字节异所有权、多层修订与合法共享祖先。
- [x] 依次运行新专项、设计列明的历史回归、全套 pytest；最终代码有变化时重跑对应验证，不把历史 JIM-06 数量作为本任务结果。
- [x] 保存实际命令、时长、计数、失败/修复和退出码，验证前后记录 src/tests/workflows/使用文档 SHA；失败保留原日志。

### Task 9: 使用说明、完成证据和后继交接

**Files:** Modify `docs/jimeng-candidates.md`, task board; create `docs/task-designs/JIM-07-verification.md`; successor artifacts only after current completion.

- [x] 更新实际可用 CLI：新运行、普通续作、选图/过程/最终观察的仅消费调用、显式 publish/retry/revision，以及不同等待状态的解除方法。
- [x] 使用 verification-before-completion 及 requesting-code-review 工作流按实际实现检查五项 Acceptance，修复后验证；当前未选委派，不提前创建 reviewer 子代理。
- [x] 验证记录逐项绑定结果级证据，明确替身/真实媒体和真实服务/观看验收的界限；没有实测结果的项目不得标通过。
- [x] 开始实现时依据本次明确启动请求记录 READY→IN_PROGRESS；完成且验收证据齐备后先记录 IN_PROGRESS→COMPLETED。不得因为 JIM-08 缺真实账号而扣留已完成的 JIM-07 状态。
- [x] 按任务板 Order 选择 JIM-08，再按 managing-task-handoffs/designing-task-contracts 完成并关联其具体设计及 next-task handoff，最后准备 READY；如存在材料缺口，保留 JIM-07 COMPLETED，不写部分交接或虚构凭证/样片。

## Verification Commands

每个执行 Python 的新 PowerShell 调用均先执行以下两行；测试及媒体任务串行。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-07-tests'
```

首个 RED/GREEN：

```powershell
& $VideoAiPython -B -m pytest tests/unit/test_scene_revision.py -k test_reselected_baseline_invalidates_reference_descendants_but_preserves_unrelated_scene -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

新增专项、相关历史、全套顺序执行，分别保存日志和退出码：

```powershell
& $VideoAiPython -B -m pytest tests/unit/test_scene_pipeline.py tests/unit/test_scene_revision.py tests/unit/test_scene_revision_records.py tests/integration/test_scene_pipeline_recovery.py tests/integration/test_scene_revision_flow.py tests/integration/test_scene_pipeline_cli.py -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
& $VideoAiPython -B -m pytest tests/unit/test_scene_media.py tests/unit/test_scene_media_records.py tests/unit/test_scene_upscale_transactions.py tests/unit/test_scene_final_observations.py tests/integration/test_scene_media_flow.py tests/integration/test_scene_composition_recovery.py tests/integration/test_scene_media_recovery.py tests/integration/test_scene_upscale_flow.py tests/integration/test_make_video_recovery_contract.py -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
& $VideoAiPython -B -m pytest -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

以上保留原计划命令。首轮专项156/历史195通过后发现并修复旧CLI锁回归；v2完整全库3551通过、1处旧复制正例不合法；仅校正夹具并复测46项后，最终v3裸全库3552通过、退出0，含新增156及指定历史195全部节点。最终364项文件前后和独立重算一致；实际详细日志、失败/修复与命令见验证记录。

## Plan Self-Review

- 双图、复用根/模型分类→Task 1；原来源必要祖先/守卫→Task 2/5；冻结递归与恢复→Task 3/4；复制身份与提交→Task 4；阶段协调/前缀/记录→Task 6；CLI/消费发布/完成快路→Task 7；七组设计测试场景→Task 8；验收文档/任务状态→Task 9。
- 全部公共签名和字段约束引用同一设计，不另造第二份协议。内部辅助模块按职责拆分，不改变公共阶段 API。
- 五项 Review Focus 已逐项落入负责代码的任务及测试；旧策略兼容、unknown、清理失败和跨调用重新核验均有覆盖。
- 计划只安排实现及验证，不把任何计划结果记作通过或任务完成。
