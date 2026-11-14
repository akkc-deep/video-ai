# 旅行者2号：审查入账耗时优化交接

用户最新指令：**暂停视频生成工作，把当前发现的优化问题交接给下一个任务。** 视频目标已暂停；本交接只交给后续任务优化，不授权自动恢复生成、启动模型服务或创建新修订。

当前状态、代码基线摘要与证据索引见[机器可读快照](2026-11-14-review-admission-optimization-evidence.json)。

## 运行已停止，素材保留

- 工作仓库：`E:/code/py/video-ai`；运行目录：`E:/VideoAI/work/0002-旅行者2号-即梦版/process/revisions/10`。
- 原生生产 PID `24596`，创建身份 `134391152048855622`；包装 PID `14804`；工具会话 `27228`。已确认两进程结束，会话返回退出码 **15**，原因为用户主动暂停，不是新的生成失败。
- 停止前只读堆栈位于 `_consume:519 → collect_progress → inherited_clip_record → source_clip_record → 参考图/修订来源校验`；没有视频推理。旧模型服务 PID `16072` 不存在，8188 队列端口拒绝连接。**manifest 中旧的 `healthy` 字段是历史信息，不能据此判断服务存活。**
- 先写入绑定当前 owner 的停止控制，再只停止身份核对过的自有原生 PID。没有按进程名批量终止，没有删除素材、意图、回执或 RunLock。
- 停止控制：`E:/VideoAI/scratch/voyager2-stop-after-clip.json`，当前 `run_id=10`、token `396cb07121f44edfa43b57d06a84e88e`。RunLock 保留已结束 owner，未来获准恢复后应由公共锁机制接管，**不要手工删除锁**。
- 暂停证据：[用户暂停记录](E:/VideoAI/scratch/voyager2-user-pause-20261114.json)、[停止前堆栈摘录](E:/VideoAI/scratch/voyager2-user-pause-stack-20261114.json)。
- 最新协调状态：[主状态](E:/VideoAI/scratch/voyager2-resume-state.json)、[审查状态](E:/VideoAI/scratch/voyager2-review10-prep-state.json)。两者均标为 `paused_by_user`，实际活跃进程字段已清空；只保留历史 owner 信息。

暂停时核对到：**11 个片段正式通过，1 个片段正式拒绝，29 份实际观察尚待正式回执**。其中通过数含从09版继承的8段。新正式回执包括第3镜续段 failed、第5镜续段 passed；已核对回执与当前 clip/request、原始观察字节的绑定，没有重复导帧或视频哈希。

实际观察保存在 `E:/VideoAI/scratch/voyager2-current-review10/<clip_id>/observation.json`；已发布到 `E:/VideoAI/scratch/voyager2-review-revision10/<clip_id>/observation.json`。**本地已写、已发布、正式接收是不同状态**，恢复时按真实回执和原字节判定，不能全部重新提交已失败的观察。

## 当前究竟在耗什么时间

当用户询问耗时和优化时，进程正在执行审查入账的来源重建与校验，GPU 并没有生成新画面。原日志：

`E:/VideoAI/scratch/logs/voyager2-10-after-verified-reboot-2b2174b44f224cbbb200fa9ee68b3d8c.log`

早先一次真实采样位于 `load_prepared_inputs → require_scene_revision → capture_origin → source_clip_record → scene_context → build_reference_image_acceptance → verify_reference_provenance`；停止前采样进一步看到 `_consume` 的全局进度扫描再次沿继承来源进入上述路径及多层 `RevisionGuard.verify_captured_bytes`。证据：[准备阶段采样](E:/VideoAI/scratch/voyager2-reboot-loading-stack-20261114.json)、[停止前采样](E:/VideoAI/scratch/voyager2-user-pause-stack-20261114.json)。

这些采样证明当时的调用位置和重复重建路径，不是各函数独占耗时测试，不能把全部等待时间都归因于某一个函数。回执 `accepted_at/rejected_at` 在 `_consume` 中途就取值，可能早于文件实际写出；不要直接用它当作接收完成时间。

## 优先优化点

### 1. 每份观察触发三次全局进度扫描

[`_consume` 第一轮](../../src/video_ai/runtime/production_scene_clips.py:519)、[保存原始观察后的第二轮](../../src/video_ai/runtime/production_scene_clips.py:537)、[`_finish` 第三轮](../../src/video_ai/runtime/production_scene_clips.py:325)。每轮 `collect_progress` 都会遍历片段和继承来源。

现有[批量入口](../../src/video_ai/runtime/production_scene_clips.py:609)共享一次入口准备，但仍逐份调用 `_consume`，不等于批量复用进度/来源重建；返回全局 blocked/failed 时还会提前结束批次。现有任务脚本自己循环调用 `_consume`，因此更不能仅把调用换成批量 API 就宣称解决问题。

后续目标：在受保护的同一批接收中共享已准入上下文和进度，逐份只重建受影响的记录，批次边界完成必要的来源变化检查。明确保留批量接口的早停契约，或设计清楚每份接收结果与整片状态的区别。不得跳过失败不可覆盖、父段准入和真实原始观察绑定。

### 2. 已有 `source_frozen`，继承片段仍重新加载源运行

[`require_scene_revision` 已保存 source_frozen](../../src/video_ai/runtime/scene_revision_records.py:649)，注释明确供消费者在当前修订作用域中复用；但 [`inherited_clip_record`](../../src/video_ai/runtime/_scene_revision_readers.py:63) 在[第71行](../../src/video_ai/runtime/_scene_revision_readers.py:71)再次 `load_frozen_inputs(proof['source_run'])`，随后重新构建源 clip 记录。

这是优先做小型复现的候选热点。先验证可否复用已准入的 `source_frozen`，再评估同一作用域内源 clip/context 的复用。不能只换成一个字典取值就认为所有模式安全：保留源冻结身份、guard、row 参数、parent 绑定、媒体重映射及 native/temporal 分支契约；返回可变记录时避免调用者修改污染缓存。

### 3. 参考图来源递归与祖先 guard 重复进入

[`verify_reference_provenance`](../../src/video_ai/runtime/reference_image_records.py:339) 会递归检查祖先场景/修订。停止前栈看到 `inherited_clip_record → source_clip_record → scene_context → build_reference_image_acceptance` 又进入此递归，并从 `_prior/_load_accepted/_run` 重新加载冻结输入、验证修订结构和祖先文件。

检查 DAG 中共享祖先是否在一次受保护读取/接收批次内只处理一次；缓存键和失效规则必须包含输入身份及依赖边界。已有 `_batch_revision_artifacts`、共享祖先 guard 和受保护字节缓存，应先复用/修正既有作用域，避免再叠加无边界全局缓存。不要仅按路径或文件大小缓存，也不要跨线程/跨作用域盲目复用。

任务临时补丁 `.tools/continue_voyager2_cached.py` 只在部分场景复用已准入字节；捕获依赖时仍回到原校验路径。停止前采样实际看到了这个回退路径。**它不是正式性能修复，也没有消除来源对象和参考图递归的重建。**

### 4. 暂停控制在初始审查批次中响应过晚

`.tools/resume_voyager2_after_reboot.py` 的初始 `admit_reviews()` 会处理收件箱；内部循环没有在每份观察之间检查停止信号，且 `_consume` 本身可能耗时很久。后面的停止检查到初始批次结束才可到达，模型服务的 `ensure()` 也位于该检查之前。

后续应在明确的原子写入边界及昂贵只读阶段之间响应暂停，并在启动服务/提交推理前再检查。不得把“已写停止文件”当作进程已停。本次为遵守用户明确暂停，在核对只读位置、进程身份及无模型服务后停止了自有 PID，保留了全部持久产物。

### 5. 阶段名称与通知需要表达真实工作

“准备原配音与时间线”阶段实际可能深入继承来源和参考图验证；健康服务、活进程及新的源片段是不同证据。增加粗粒度阶段、耗时和批次接收计数即可；同一状态的轮询留在内部记录，用户侧只报告阶段变化、实际新产物或异常。不要再用高频“仍在恢复/仍在加载”回复替代真实进展。

## 下一任务建议顺序与验证边界

1. 先读本交接和[已有18项流程问题](2026-11-14-voyager2-workflow-issues.md)，遵守 [AGENTS.md](../../AGENTS.md:1)：“生成视频的过程中不要过度校验”。此次不应重看已有完整帧序列，也不应重新渲染视频来验证纯读取优化。
2. 先用小型本地 fixture 复现“多层修订 + 多个共享祖先 + 连续接收多份观察”，记录 `load_frozen_inputs/source_clip_record/collect_progress` 调用量及分阶段耗时。分别测冷准备、首份接收、暖批次，不能只报整个脚本总时长。
3. 优先验证 `source_frozen` 复用及批内上下文复用这两个较小改动；有明确失败复现后再改生产代码。暂不扩大到规划器重构或视频质量修复。
4. 相关已有测试：`tests/unit/test_review_loading_performance.py`、`tests/unit/test_revision_guard_shared_ancestors.py`、`tests/unit/test_scene_clip_records.py`；按改动选择必要用例，补一个代表性的接收/修订流程集成用例。检查源内容变化、同字节文件替换、新增/缺失文件、祖先变化、参数/父段不符、跨线程/作用域复用仍被拒绝。不要把“更快”建立在删除身份/变化检查或伪造回执之上。
5. 当前仓库和旧 worktree `C:/Users/qzw19/.codex/worktrees/c372/video-ai` 都有大量既有未提交修改。隔离自己的改动，保留用户文件，不要 reset、批量覆盖或直接整体同步旧 worktree。本轮尚未实施新的 `src/` 优化，也没有新的优化测试结果可宣称。
6. 优化完成后仍保持视频暂停，交付改动、聚焦验证及实测对比。**只有用户重新要求恢复，才重新核对 owner/服务/回执并继续视频。**

## 保留的其他待办

- 五个实际失败目标：`scene_0003_clip_0002`、`scene_0008_clip_0001`、`scene_0014_clip_0001`、`scene_0025_clip_0001`、`scene_0030_clip_0001`。未执行草稿：`E:/VideoAI/scratch/voyager2-10-failed-clips-revision-draft-v4.json`。保留通过的第3镜首段及其他通过素材，不覆盖失败结论。
- 第36镜原任务 `5dac19bb-d662-46a7-b195-da34d8c757bc` 在机器重启前已受理但未完成，没有完整视频落盘，仍为未决原任务；它不是新的画面失败观察。不得重新 POST、删除 intent 或伪造服务失败历史来解除修订阻断。见原流程问题中的重启核对入口缺失。
- 全片原目标仍是137镜、265片段、17,824个原生16fps帧，后续还有1080p放大、合成、完整音画审查及发布；目前未交付。此范围保留，但执行已暂停。
