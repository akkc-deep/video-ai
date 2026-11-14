# 旅行者2号视频生成流程问题与后续修复交接

记录日期：2026-11-14，时区 Asia/Shanghai。仓库：`E:/code/py/video-ai`。素材根目录：`E:/VideoAI`。

用户要求：“把这些流程问题都记录下来，后续我会让其他任务修复”。用户最新又明确要求暂停视频工作并交接优化问题。本文保留已观察到的问题和历史证据；执行状态以当前暂停指令为准，后续修复任务按范围分别处理。

## 当前实际状态

**用户最新明确暂停视频生成。后续任务只处理优化交接，未经用户重新要求，不得启动生产者、模型服务或新推理。** 详见[审查入账优化交接](2026-11-14-review-admission-optimization-handoff.md)。

- 当前10版保留11个正式通过片段、1个正式拒绝片段、29份尚待正式回执的实际观察。正式通过数含09版继承的8段；第3镜续段已有失败回执，第5镜续段已有通过回执，均已核对当前 clip/request 与原始观察绑定。
- 运行会话27228已按用户要求停止，原生 PID24596（创建身份134391152048855622）和包装 PID14804均已结束，工具退出码15。停止前为只读审查扫描，未运行模型推理；旧服务 PID16072不存在、8188队列端口拒绝连接。manifest 中旧 healthy 标记不代表当前存活。
- 所有视频、图片、配音、原观察和回执保留；RunLock保留已结束 owner，不手工删除。已写入当前 owner 对应的停止控制。主状态及审查状态均为 paused_by_user，要求新的用户恢复指令。
- 第36镜在14:34:25+08:00的机器重启前已受理但未完成，无完整视频落盘，原任务仍未决；没有重新提交，也没有伪造服务终态。
- 当前五个实际画面失败目标为第3镜续段、第8、14、25、30镜首段；未执行的定向修订草稿为 E:/VideoAI/scratch/voyager2-10-failed-clips-revision-draft-v4.json。保留第3镜已通过首段及所有其他通过素材。
- 第2、7镜早先恢复成功，之后已正式接受；旧08版的 scratch 审查记录仍不等于正式接受。当前已实际审查的新片段至第35镜，后续生成、放大、合成、完整音画审查和交付均未完成。
- 当前优化只完成排查和交接，没有实施新的 src/ 优化，也没有新的优化测试结果。不要因本次“可以优化吗”的讨论自动恢复视频。

暂停证据：[暂停记录](E:/VideoAI/scratch/voyager2-user-pause-20261114.json)、[停止前只读堆栈](E:/VideoAI/scratch/voyager2-user-pause-stack-20261114.json)。最新协调状态：[主状态](E:/VideoAI/scratch/voyager2-resume-state.json)、[审查状态](E:/VideoAI/scratch/voyager2-review10-prep-state.json)。旧会话47763/PID30088已在机器重启后结束，不能再按它恢复或轮询。

历史恢复成功证据：[第2、7镜恢复日志](E:/VideoAI/scratch/logs/voyager2-09-local-recovery-admitted-inbox-295b3fc399914f219262cfd325d9eca2.log)、[第1镜末段接受与修订日志](E:/VideoAI/scratch/logs/voyager2-admit-final-scene1-and-revise-7ac557a07a3a413c9743b6567fa6f386.log)。以下各问题包含历史现场，不能把其中的旧进程、未发布状态或继续指令当成当前状态。

## P1 冷启动和校验成本仍然很高

**现象与影响：** 一处输入错误或恢复错误导致进程退出后，下次又从冻结输入、配音时间线、片段上下文开始准备。用户看到长时间重复“恢复”，实际视频生成被推迟。

本轮成功运行从进程创建 `00:53:21.7485605+08:00` 到第 2 镜技术产物时间 `01:05:46.114659+08:00` 相隔 **744.3660985 秒，约 12.4 分钟**。这个区间包含冷准备、恢复和技术处理，不能当作某一个函数的独占耗时。证据：[快照第 5 行](2026-11-14-voyager2-workflow-issues-evidence.json:5)、[第 13 行](2026-11-14-voyager2-workflow-issues-evidence.json:13)。

早前修复消除了应用层重复文件读取，但整轮只读准备仅从 384.438 秒降至 370.023 秒；对象重建、规范化和结构验证仍有成本。这是早前记录的 08 版测量，不能直接与本轮 09 版时长比较。证据：[既有结果](2026-11-12-repeated-reads-fix.md:5)。

**已做处理：** 任务脚本在同一进程中保留片段上下文并批量消费观察；格式预检移到了冷准备之前。

**后续任务需要解决：** 保留必要的来源和变化检查，减少同一受保护操作内的重复对象构造与校验；让局部输入错误可以局部处理。给实际阶段加入时间戳及累计耗时，分别报告冷准备、恢复、技术处理、审核入账和生成耗时。仅运行与改动相关的必要验证，遵守 [AGENTS.md](../../AGENTS.md:1)。

后续创建 10 版时，做了一次只读实时堆栈采样：主线程处于 `_capture_origins → whole_input_protection` 退出检查，再逐个执行 `_WholeInputWindow.verify → _NativeInput.verify → _canonical_path`。[采样原件](E:/VideoAI/scratch/voyager2-revision10-live-stack-20261114.txt:6)。这证明采样时在进行来源捕获和受保护句柄校验，不能据此把整段等待时间都归因于这个函数。该次采样之后保留原进程继续运行，未因输出安静重启。

本次修订随后真实返回 `revision_ready`：从包装脚本保存准备修订阶段的 `01:33:02.108478+08:00`，到成功返回后的状态更新时间 `03:37:22.326837+08:00`，相隔 **7460.218359 秒，约 2 小时 4 分钟**。该区间涵盖来源捕获、复制、目标冻结、准入及最终校验，不能当作某一函数独占耗时。接近结束时的一次只读采样已到 `create_scene_revision:499` 的最后来源字节核对；保留原进程后最终正常返回。数据与口径见[结果快照](2026-11-14-voyager2-workflow-issues-evidence.json:1)。

直接继续 10 版时，还观察到两处独立的导入片段进度读取：`04:41:17+08:00` 在任务脚本 `advance:141 → collect_progress` 读取 `scene_0004_clip_0001`，`05:36:16+08:00` 又在原生产入口 `_produce:364 → collect_progress` 读取同一片段。说明继续入口的初次读取之后，原生产入口还会重新构建导入来源记录。这两个采样点不是单函数独占计时，也不是重复提交视频推理的证据。ComfyUI 在 `05:05:49+08:00` 已健康启动，但 `05:20:37+08:00` 新续段的 request/intent 仍不存在；服务就绪不能作为新渲染已开始的证据。[现场摘录](2026-11-14-voyager2-workflow-issues-evidence.json:1)。本次仅补记调用位置，不扩展核心校验优化。

另有一个待后续验证的候选热点：[继承片段读取](../../src/video_ai/runtime/_scene_revision_readers.py:62) 每次调用 `load_frozen_inputs(proof['source_run'])`；`require_scene_revision` 已保存 `source_frozen`，并注明供消费者复用。应检查此处重新加载的必要性及其依赖证明边界，不能未经验证直接替换所有模式。本轮只记录调用结构，没有修改这个核心路径，也没有把它量化为全部耗时的原因。

机器重启后的接续进程也出现同类准备成本。`15:44:31+08:00` 对原生 PID `24596` 做了一次只读采样：`load_prepared_inputs → require_scene_revision → capture_origin → source_clip_record → scene_context → build_reference_image_acceptance`，之后递归进入 `verify_reference_provenance`，采样末端正在做路径拼写/保留名称检查。[本次采样与限制](E:/VideoAI/scratch/voyager2-reboot-loading-stack-20261114.json)。这证明采样时在重建继承来源和参考图来源关系；不是新视频推理，也不能据此把整个准备时长归于该调用。原进程保留继续运行，本轮仍不做核心优化。

## P1 审查收件箱缺少完整的重启幂等处理

另一个已定位的耗时来源在正式观察接收本身：`production_scene_clips._consume` 在读取观察前和保存观察原件后分别调用 `collect_progress`，最后返回 `_finish(context)` 时又扫描一次。批量接收 API 也逐条调用 `_consume`，只共享入口准备，并不合并这三轮进度扫描。因此仅保留暖进程并不等于避免重复构建导入来源记录。这里记录的是已读到的调用结构，不是三轮独占耗时测量；本轮未改核心接收逻辑。

**现象与影响：** 前一轮已经正式入账的第 3 镜失败观察仍在待处理收件箱。重启后再次提交同一失败观察，接口返回 `explicit failed clip requires a revision run`，恢复尚未开始就退出，已支付的冷准备成本再次浪费。

证据：[前轮失败观察已入账](E:/VideoAI/scratch/logs/voyager2-09-local-recovery-d0c3973c8b904c4c9d98e7ce9a057777.log:8)、[重启报错](E:/VideoAI/scratch/logs/voyager2-09-local-recovery-fingerprint-a6e2c47d6f984597a05fceaadc6ffd37.log:8)、[正式接口的替换限制](../../src/video_ai/runtime/production_scene_clips.py:502)。

**已做处理：** 核对原始观察字节与正式 receipt 后，将五份已入账的 scratch 文件改名为 `admitted-observation.json`，保留正式原件；两个任务脚本也加入了对相同已验证 receipt 的跳过逻辑。[任务脚本](../../.tools/resume_voyager2_09_recovery.py:108)。

**后续任务需要解决：** 在昂贵准备前区分“完全相同的已入账观察”“新的观察”“企图替换结论”。对相同失败观察的重放应有明确结果，不能误走替换失败片段的分支；这不应允许把失败改成通过。

## P1 服务历史丢失时已有视频难以恢复

**现象与影响：** 第 2 镜 MP4 实际存在，但原 ComfyUI 进程丢失了任务历史，新服务的 queue/history 找不到原任务。普通路径只能报告提交结果未知，无法直接复用已完成文件。

原任务：`d1f4d7a7-09d1-4575-b4fa-b95831e05ce8`。现有本地恢复凭证包含该原身份、原 queue 证据、缺失查询证据、输入图身份和视频内嵌工作流。[当前本地凭证](E:/VideoAI/work/0002-旅行者2号-即梦版/process/revisions/09/production/scene-clips/scene_0002_clip_0001/local-output-recovery.json:1)、[恢复实现](../../src/video_ai/runtime/scene_local_output_recovery.py:212)。

**已做处理：** 用户明确授权后增加独立 `local_recovery_evidence`；原输出保留，未重发原任务。普通缺失历史查询已有有界退出。

**后续任务需要解决：** 明确生产入口中的服务生命周期、提交身份持久化、历史证据保存、结果未知和本地恢复状态转换。避免无限查询、盲目重发或在保全结果前关闭服务。成功返回的本地来源证明不得伪装成服务执行成功证明。

## P1 视频内嵌工作流存在运行时追加字段

**现象与影响：** 本地恢复最初要求内嵌图与提交图完全相同。ComfyUI 给 `LoadImage` 节点追加了 `is_changed=[输入图 SHA256]`，导致合法原视频被拒绝为 `embedded MP4 graph differs from original graph`。

证据：[失败日志](E:/VideoAI/scratch/logs/voyager2-09-local-recovery-d0c3973c8b904c4c9d98e7ce9a057777.log:13)、[ComfyUI 追加字段](E:/VideoAI/shared/tools/ComfyUI_windows_portable/ComfyUI/execution.py:100)、[LoadImage 指纹](E:/VideoAI/shared/tools/ComfyUI_windows_portable/ComfyUI/nodes.py:1809)。实际指纹与第 2 镜 `input.json` 的目标图片哈希一致。`16` 与 `16.0` 的数值等价已有单独兼容。

**已做处理：** 只对原图中对应的 `LoadImage`、精确输入路径、精确输入图哈希允许剥离这个运行时字段，再比较其余完整图。[对应实现](../../src/video_ai/runtime/scene_local_output_recovery.py:147)。

**后续任务需要解决：** 将“提交参数”和“服务执行时追加元数据”建模清楚；真实服务产物应有小型兼容样例。不能通过忽略所有未知字段或仅比较提示词来获得表面通过。

## P1 元数据已写出但恢复凭证未写出时的断点

**现象与影响：** 第一次图比较失败发生在不可变 `local-output-metadata.json` 已写出之后。最初实现只支持 receipt 已写出、submission 未写出的重放，未处理更早的 metadata-only 断点。重新探测会与已有不可变证据冲突。

证据：[第 2 镜元数据凭证](E:/VideoAI/work/0002-旅行者2号-即梦版/process/revisions/09/production/scene-clips/scene_0002_clip_0001/local-output-metadata.json:1)、[当前断点恢复分支](../../src/video_ai/runtime/scene_local_output_recovery.py:242)、[针对该断点的测试](../../tests/unit/test_scene_local_output_recovery.py:189)。

**已做处理：** 重用已有 probe、对应的四次原始缺失查询和早先原 queue 身份，完整重建验证后续写 receipt/submission；没有覆盖旧证据。两项新增正向场景先观察到失败，再修正；本地恢复和原事务相关测试合计 57 项通过。

**后续任务需要解决：** 明确每个不可变写入边界的恢复语义；后续异常不要只能靠人工移动正式证据解决。当前补丁的 FFprobe 单测使用替身，本轮真实产物已经通过了实际恢复路径。

## P2 人工观察的格式错误发现过晚

**现象与影响：** 已查看画面后写出的 JSON 曾把 `issues` 写成字符串列表，接口要求每项具有 `check/description/frames`；另有观察加入了顶层 `review_evidence`，违反精确字段约束。第一种错误在完整冷准备之后才暴露。

证据：[issues 报错](E:/VideoAI/scratch/logs/voyager2-09-local-recovery-aded64d7ae53496b8fdb56984035398b.log:7)、[顶层字段报错](E:/VideoAI/scratch/logs/voyager2-09-local-recovery-c5b0d96c499f4ee78f69e9edc1bb5887.log:20)、[正式字段定义](../../src/video_ai/runtime/scene_clip_observations.py:24)。

**已做处理：** 改成规范 issue 对象；额外证据放入 sidecar；增加冷准备之前的预检。新写的第 2、7 镜观察直接由当前模板构造并在提交前校验。

**后续任务需要解决：** 提供单一的观察构造/提交入口，写出时即校验，清楚区分人工观察正文与附加证据。预检还应覆盖已入账状态，不能只覆盖 JSON 结构。

补充格式陷阱：`issues[].frames` 是两个整数构成的半开区间 `[start, end_exclusive]`，不是抽样帧号列表。后续任务应把这一要求直接放入模板说明，并在写出时用一次便宜的结构检查发现错误；不要再为格式错误重跑完整输入准备。字段约束见[观察实现](../../src/video_ai/runtime/scene_clip_observations.py:24)。

## P2 服务 manifest 字段假设不兼容

**现象与影响：** 任务脚本直接读取 `info['args']`，实际健康记录的参数在 `health.stats.system.argv`，出现 `KeyError: 'args'`，恢复流程立即退出。

证据：[原报错](E:/VideoAI/scratch/logs/voyager2-09-local-recovery-852b0662b1984bdcb6e7b9b984d4e3dc.log:18)、[当前兼容读取](../../.tools/resume_voyager2_09_recovery.py:56)。

**已做处理：** 任务脚本兼容两种已知位置，并继续核对 PID、进程创建身份和当前输出目录归属。

**后续任务需要解决：** 统一服务描述读取接口或版本化 schema。未知格式应在便宜的预检阶段清楚报错，不能凭 PID 或进程名称认领、关闭服务。

## P1 修订可能重复渲染旧素材且没有改变失败原因

**现象与影响：** 第 3 镜修订原先只请求重生成，没有改变提示词和种子；09 版再次得到与已失败的 08 版完全相同的 source 字节。重复生成消耗时间，却没有推进修复。

两个 source SHA256 均为 `8bc70d1789296868a30d60177fda5d94eae3e60eba7d8cb4a6801525a4caba9a`，已对实际文件重新计算。[快照第 16 行](2026-11-14-voyager2-workflow-issues-evidence.json:16)。固定种子和原 conditioning 构造位置：[构造器](../../src/video_ai/planning/scene_clip_continuation.py:210)。

同时，修订导入只认可正式接受的片段；旧片段虽技术完成，若没有正式接受，就不能自动复用。这是当前准入规则，不能直接当作可以绕过的错误；但会让“已生成”和“可复用”的差异转化为大量重复推理。[来源准入](../../src/video_ai/runtime/_scene_revision_origins.py:213)。目前没有对所有片段逐一统计重复渲染数量，不能把第 3 镜的证据推广为全部片段均重复。

**已做处理：** 已加入显式、目标片段限定的 `clip_prompt_overrides`，对第 3 镜首段及续段使用刚性连接、整体缓慢漂移的完整 positive；未改冻结的 09 版文件。相关实现通过 142 项定向测试及独立审查。10 版首段已实际生成、查看并正式接受；续段虽包含同一显式 override，仍在后半段出现碟面向左、主体和长杆独立留在右侧的明显黑隙。完整 77 帧及原生尾帧的既有实际观察记录为 failed，不能用提示词已传入或首段通过替代续段画面结论。[实际过程观察](E:/VideoAI/scratch/voyager2-current-review10/scene_0003_clip_0002/observation.json:149)、[实际图参数与状态](E:/VideoAI/scratch/voyager2-current-review10/scene_0003_clip_0002/evidence.json:32)。本次仅核对既有记录，没有重复导帧或审查。

**新增边界：** “修正参数实际生效”与“生成结果解决问题”必须分别记录。此次续段是生成运动仍不合格，不能再归因于 override 未接入，也不能据此撤销已通过首段。已另存[续段修订请求草稿](E:/VideoAI/scratch/voyager2-10-scene3-child-locked-pose-revision.json:1)，仅针对 `scene_0003_clip_0002`，改为锁定视角、部件相对位置及初始重叠，只允许轻微整体平移；已做字段预检，尚未调用修订 API 或重新生成。须在当前生产轮次结束并处理待发布观察之后交接，不能为执行草稿中断现有推理，也不能把草稿当成修复成功。[后续修正范围](E:/VideoAI/scratch/voyager2-current-review10/scene_0003_clip_0002/evidence.json:36)。

**后续任务需要解决：** 修订前展示真正变化的生成输入和可复用范围；同参数重试应有明确原因。统筹已有真实审查、正式接受与下一修订素材导入，减少无效重复生成。不得为了复用而替未查看或失败素材写通过记录。

## P2 恢复状态和任务脚本分散

**现象与影响：** 接管时 `voyager2-resume-state.json` 仍指向旧 session `72189`，实际任务已切换到其他会话；现有脚本分别处理接受、恢复、继续生成，手动协调原服务、锁和观察收件箱，容易把旧状态当成活进程。该旧值是本轮接管时直接读取的现场观察，旧文件随后已更新，不能用现在的文件内容证明旧值。

**已做处理：** 当前状态文件已更新为实际工具会话、生产 PID/创建身份、日志和协作停止令牌。接管必须轮询真实工具 handle 或核对实际进程；不能仅凭 state/lock 判定活跃或终止。[当前状态文件](E:/VideoAI/scratch/voyager2-resume-state.json:1)、[任务局部继续脚本](../../.tools/resume_voyager2_clips.py:27)。

补充现场证据：同一个状态文件已经列出第 2、7 镜为 `recovered_clips`，却仍保留第 2 镜的 `unresolved_clip`、`unresolved_reason` 和早期 `authored_observation` 等旧字段。这说明只更新部分字段仍会造成相互矛盾的接管信息；当前冲突已摘录到证据快照，后续不能仅按旧的 unresolved 字段再次恢复。

**后续任务需要解决：** 让一个持久化协调入口管理恢复、观察消费、继续生成和片段完成点切换；规范状态的更新时机、终态及恢复策略，减少依赖 scratch 文件和记忆。任何整体化改造应另开任务，不在本次记录任务扩展实施。

## P2 重复进度回复干扰用户且阶段命名不清

**现象与影响：** 等待同一进程期间反复发送“正在恢复/仍在加载”等低信息量回复；“恢复”又同时指任务接管、旧输入加载、本地视频凭证恢复等阶段。用户因此连续问“为什么一直在回复”“为什么一直在恢复”。[原话记录](2026-11-14-voyager2-workflow-issues-evidence.json:27)。

**已做处理：** 已承认提示过密；后续减少重复状态回复，只报告实际产物、阶段变化、失败或需要用户决定的事项。

**后续任务需要解决：** 去重同一进程、同一阶段、同一状态的通知；向用户区分“加载旧输入”“恢复原任务”“生成新片段”。单纯确认活进程的轮询应留在内部运行记录中，不能包装成新的生成成果。

## P1 完成点切换早于新片段的审查和正式接受

**现象与影响：** 协作停止在 `observation-template` 写出后立刻触发。它能先消费此前准备好的观察，但刚完成的新片段还来不及被查看和接受，进程就退出了。第 1 镜第 3 段曾因此已生成却不能被下一修订导入，后来另起进程重新加载原输入后才正式接受。

证据：[停止发生的位置](../../.tools/resume_voyager2_09_recovery.py:189)、[实际完成点退出日志](E:/VideoAI/scratch/logs/voyager2-09-local-recovery-admitted-inbox-295b3fc399914f219262cfd325d9eca2.log:15)、[新片段技术记录](E:/VideoAI/work/0002-旅行者2号-即梦版/process/revisions/09/production/scene-clips/scene_0001_clip_0003/clip.json:1)、[来源要求正式接受](../../src/video_ai/runtime/_scene_revision_origins.py:213)。这里只陈述已发生的退出和未完成的审查；尚未对额外冷准备实测计时。

**已做处理：** 保留新片段及完整技术证据，实际审查后由后续进程正式接受，未为迁移而伪造通过记录。[后续加载与接受日志](E:/VideoAI/scratch/logs/voyager2-admit-final-scene1-and-revise-7ac557a07a3a413c9743b6567fa6f386.log:4)。

**后续任务需要解决：** 区分“视频技术完成后停止”和“当前片段已审查、接受后切换修订”。在等待真实观察期间保留暖上下文，或提供不重复全局准备的安全交接方式。切换前展示会遗漏哪些已生成但未正式接受的产物。

## P2 旁路审查记录与正式复用流程脱节

**现象与影响：** 等待修订时对旧 08 版完成了 85 段 scratch 审查（65 passed、16 failed、4 unverified），但这些观察没有在 08 版正式接受；10 版的导入清单仍只有来自 09 版的 8 个已接受片段。不能把“已查看、已写草稿”当成“已导入、已减少渲染”，也不能用草稿数量替代视频生成进度。证据：[只读审查索引](E:/VideoAI/scratch/voyager2-source08-review-index.json:1)、[本次证据摘录](2026-11-14-voyager2-workflow-issues-evidence.json:1)。没有测量这部分工作的独占耗时或节省的推理次数。

**已做处理：** 已完成分派范围的记录，停止扩大旧素材审查范围。现有记录保留为候选证据；集中处理当前生产版本的新片段，禁止未经当前字节、模板绑定及真实审查就转写通过结论。

**后续任务需要解决：** 在启动批量旁路审查前，先明确其结果如何进入当前版本的正式复用路径，以及是否会实际减少重复生成。待处理草稿、正式接受、已导入、仍需生成应分开计数；避免审查工作不断扩张而生产流程没有推进。本次仅记录，不实现跨版本合并或新的准入通道。

## P1 新修订的片段入口遗漏 Wan 输入汇总

**现象与影响：** 10 版已经正式 `revision_ready`，图片接受记录也已导入，但任务局部继续脚本直接进入 `clips._entry`。`scene_context` 要求本版本的 `production/reference-images/wan-inputs.json`，而该本地汇总由正常完整协调器在进入片段阶段前构建；创建修订本身不生成它。因此本轮又在冷准备后退出，尚未提交新视频任务。

证据：[实际失败日志](E:/VideoAI/scratch/logs/voyager2-admit-final-scene1-and-revise-7ac557a07a3a413c9743b6567fa6f386.log:1)、[正常协调器的准备步骤](../../src/video_ai/runtime/production_scene_pipeline.py:207)、[片段上下文入口要求](../../src/video_ai/runtime/scene_clip_records.py:193)。

**已做处理：** 只在任务脚本中接回现有 `build_reference_image_acceptance` 和受 RunLock 保护的 `RevisionStore.save`，缺失时从本版本已接受的图片构建清单；不复制 09 版清单、不改变图片、不重建修订、不重新请求即梦。实际运行已输出 `accepted Wan reference inputs ready`，当前 10 版清单包含 137 镜，并已进入原片段上下文构建；这不代表新视频已生成。[任务脚本](../../.tools/resume_voyager2_clips.py:85)、[新的运行日志](E:/VideoAI/scratch/logs/voyager2-10-wan-admission-and-clips-578d4277565b48fc8d2fd32a089d7165.log:1)。

**后续任务需要解决：** 明确“新修订就绪”和“片段入口就绪”的依赖差异；提供统一的、可复用的无付费准备步骤，避免任务脚本遗漏正常协调器的前置阶段。缺项应在便宜的入口检查发现。本次不扩展为协调器重构，不重跑已有代码功能的全套测试。

## P1 可变停止控制文件被只读输入保护锁住

**现象与影响：** 请求片段完成点切换时，原子替换 `voyager2-stop-after-clip.json` 返回 `PermissionError [WinError 5]`。文件属性为 Archive（32），不是只读属性。继续脚本曾通过 `config.read_json` 读取旧的 09 版停止请求；该读取在活动的 whole-input 保护窗口中进入 `protected_bytes`，把本应可变的控制信号当作只读输入保留，导致运行中无法更新它。

**已做处理：** 保留失败的临时请求与旧请求备份；只把任务脚本中的停止信号读取改为 `json.loads(STOP.read_bytes())`，没有关闭核心素材保护。旧进程既有句柄不能靠修改脚本释放，故按核实后的空闲点完成接管。新入口已实际读过停止信号并进入后续生产阶段；此时以 `r+b` 打开并立即关闭控制文件成功，未写入任何字节，证实其未再被永久锁为只读。证据见[事件摘录](2026-11-14-voyager2-workflow-issues-evidence.json:1)。

**后续任务需要解决：** 明确控制信号、协调状态与不可变生成输入的边界；动态停止信号不能被长生命周期只读句柄锁住。实际运行中验证控制文件仍可更新，不能仅验证 JSON 格式或启动前的读写。

## P1 工具会话结束不代表原生生成进程已经结束

**现象与影响：** 对会话 `65235` 发送正常中断后，工具立即返回退出码 1，但实测原生 Python PID `18160`、启动身份 `134390726509672171` 仍在运行，原 Comfy PID `16316` 也仍在。若只看工具终态就启动新生产者，会造成同时占用同一运行目录的风险。

**已做处理：** 未立即启动第二个生产者。重新核对原生 PID/创建身份、RunLock 所有者、当前空队列及仅有的两份已技术完成 intent；两段视频已经实际查看并发布观察。确认旧生产者处于只读审查点后只结束该原生 PID，保留 Comfy 与产物。随后通过已有缓存入口继续同一版本，公共 RunLock 负责归档已结束的旧 owner；没有手工伪造接受记录或重发原任务。[事件摘录](2026-11-14-voyager2-workflow-issues-evidence.json:1)。

**后续任务需要解决：** 运行器要区分启动外壳、原生生产者、服务和辅助导图任务的终态，保存并核实实际 PID/创建身份。中断后必须证明真正的生产者已结束，再交接锁与创建新任务；不能将外壳退出当作全部子进程退出。

## P1 观察入账的全局扫描挤占生成推进

**现象与影响：** 观察接收的三轮进度扫描已在前文记录；这是独立于收件箱重启幂等的问题。每完成一段就立即消费观察，会将后续独立镜头置于全局记录重建之后。代码位置为 [`_consume` 首轮](../../src/video_ai/runtime/production_scene_clips.py:519)、[保存后的第二轮](../../src/video_ai/runtime/production_scene_clips.py:537)、[`_finish` 扫描](../../src/video_ai/runtime/production_scene_clips.py:325)及[批量逐条调用](../../src/video_ai/runtime/production_scene_clips.py:620)。这里只确认调用结构；未测量该阶段独占耗时或声称所有等待均由它造成。

**本轮临时安排：** 新观察先保存在 `voyager2-current-review10`，拟在当前生产轮次结束、等待观察时集中发布到正式收件箱；这只是人工调度，并未修改核心 API，也没有减少每条接收内部的扫描。当前已保存的第 3 镜续段失败观察尚未发布或正式拒绝，必须在交接状态中明确列为待办。[保存的发布策略](E:/VideoAI/scratch/voyager2-current-review10/scene_0003_clip_0002/evidence.json:33)。

**安全与恢复边界：** 原生产循环在每个新技术片段后结束该镜内循环，且旧片段未接受时不会向后生成，因此延后发布不等于准许未审查父段生成后代。[父段准入](../../src/video_ai/runtime/production_scene_clips.py:389)、[新片段后退出镜内循环](../../src/video_ai/runtime/production_scene_clips.py:422)。但本地已写、待发布、正式接收是三个不同状态；不能依赖代理记忆补发。后续任务应解决接收的局部成本与待发布观察的持久化交接，并在必要边界验证，不扩大为生成期间反复全量校验。

## P1 默认视频提示词缺少当前镜头的动作与场景约束

**现场证据：** 第 8 镜当前选图是控制室中的人员与大屏，但实际 `graph.json` 的 `129:93.inputs.text` 为“无”加 `VISUAL_BIBLE_JSON`，正文包含探测器历程、通用纪实风格和“宇宙深处”分组；该字段没有控制室或锁定姿态描述。[实际生成图](E:/VideoAI/work/0002-旅行者2号-即梦版/process/revisions/10/production/scene-clips/scene_0008_clip_0001/graph.json:439)。这是当前图中的文本事实；图生视频仍接收选图，不能据此说模型完全没有场景输入。

**结果与限制：** 第 8 镜实际完整 93 帧观察中，大屏的碟面自行转向侧面，主体和长杆留在左侧，原生尾帧确认明显分离。已保存 failed 观察，尚未发布或正式拒绝。[实际过程观察](E:/VideoAI/scratch/voyager2-current-review10/scene_0008_clip_0001/observation.json:132)。当前证据不能证明提示词是唯一原因；第 3 镜续段已有显式约束仍会失败，也不能承诺仅补提示词即可解决。

后续第 30 镜完整 65 帧中，大屏上的圆碟探测器变成长条银色平面船体，原生尾帧确认该大幅结构替换；人物与控制室仍保持连贯。[实际观察及边界](E:/VideoAI/scratch/voyager2-current-review10/scene_0030_clip_0001/observation.json)、[导帧与发布状态](E:/VideoAI/scratch/voyager2-current-review10/scene_0030_clip_0001/evidence.json)。这是又一份画面失败证据，不证明所有镜头都失败或提示词是唯一原因。该观察已本地保存，尚未正式拒绝；已加入未执行的五目标定向修订草稿 `E:/VideoAI/scratch/voyager2-10-failed-clips-revision-draft-v4.json`，不覆盖原冻结输入或已通过素材。

**后续任务范围：** 查明当前镜头描述为何最终变成“无”，并明确哪些镜头应提供动作、镜头运动及结构保持约束。检查图中真正送给模型的简短提示词和选图是否相符，避免只看元数据完整就当作语义充分。本轮只记录；不修改冻结输入、不重构规划器，不在生成期间增加反复全量校验。当前第 3、8 镜失败目标已列入协调状态，待本轮出片与真实观察处理后合并定向修订。

## P1 机器重启后已受理但未完成的本地视频任务缺少终态核对入口

**现场证据：** 原服务日志停在第 36 镜后半段推理 `21/25`；`Win32_OperatingSystem.LastBootUpTime` 为 `2026-11-14 14:34:25+08:00`。原生产 PID `30088`、服务 PID `16072` 均已不存在，8188 队列端口拒绝连接。第 36 镜保留原 intent 与受理 UUID `5dac19bb-d662-46a7-b195-da34d8c757bc`，但目标输出目录及技术片段不存在。[证据快照](E:/VideoAI/scratch/voyager2-reboot-20261114-evidence.json)、[原提交意图](E:/VideoAI/work/0002-旅行者2号-即梦版/process/revisions/10/production/scene-clips/scene_0036_clip_0001/intent.json)。快照中的重启时间注明来源为实际只读系统查询的手工摘录，不是服务失败响应。

**现有边界与影响：** 原始 `execution_failed` 回执必须有匹配原任务的真实服务历史失败证据，不能用新造的历史或手填 terminal 代替；没有完整视频时，已有成功本地输出恢复路径也不适用。[终态验证](../../src/video_ai/runtime/scene_comfy_transactions.py:285)。未决效果会阻止创建正式修订，[修订阻断位置](../../src/video_ai/runtime/production_scene_revision.py:426)。因此机器已重启、任务已不可能继续的事实，仍不能通过现有接口把该原任务核对为可显式返工的终态。这是入口缺失，不意味着可删除 intent 或自动重发。

**本轮处理：** 已保存第 35 镜之前的真实观察；原进程确认结束后将原字节发布到收件箱，待新接续进程正式接收。任务入口移除单独的、遇到第一个未知原任务即退出的前置恢复循环，交由原 `_produce` 的逐镜处理执行 GET-only 核对并继续其他独立 scene；仍不改变全量计划或完成条件。[原生成器的错误处理](../../src/video_ai/runtime/production_scene_clips.py:424)。第 36 镜不重新提交，不伪造终态；本轮不增加核心中断凭证或重试 API。

**后续任务范围：** 为已确认机器/自有服务终止、原输出不存在且原内存历史丢失的本地任务设计显式核对凭证和返工入口。区分本地中断证据与服务执行失败证据，保留原任务身份、素材、受理记录及未知状态，允许用户授权的后续新尝试。增加必要的进程终止/重启窗口验证即可，不扩展生成期间的反复全量校验。

## 后续接手边界

1. 用户最新要求暂停视频工作并交接优化问题，后续修复另行分派。不要自动恢复视频，也不要把交接任务变成新的全量诊断、重构或测试项目。
2. 保留现有视频、图片、配音、正式观察和原提交证据；保持即梦 4.0。整片目标范围保留，但执行已暂停。
3. 工具会话 `36805` 已返回完成点中断终态（退出码 130），不要再把它当活任务；新的任务以实际 owner 和服务状态为准。不要按 Python 进程名批量终止，也不要因为日志安静重启。
4. 早先完成点停机属于历史修订切换；本次则是用户明确暂停，不能援引旧“继续”授权自动启动任何生产者。第2、7镜及第1镜新续段的正式接受记录保留。
5. 原 checkout 含无关用户修改；本轮代码未提交。隔离 worktree 为 `C:/Users/qzw19/.codex/worktrees/c372/video-ai`。后续仅集成自己负责的改动。
6. 相关旧交接：[审核加载耗时](2026-11-11-review-loading-performance-handoff.md)、[重复读取修复](2026-11-12-repeated-reads-fix.md)。旧状态和旧暂停指令须结合本轮最新授权解释。
