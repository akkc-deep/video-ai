# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md
- **Completed task:** JIM-01，任务板已记录 COMPLETED。
- **Next task:** JIM-02，按预定义 Order=2 选择。
- **Design document:** D:/code/py/video-ai/docs/task-designs/JIM-02-design.md
- **Expected next status:** READY；本交接写入并关联后由 NOT_STARTED 转入，不启动实现。

## Next Task

JIM-02：段落关键画面、共享视觉设定与时间预算。

读取完整文案、冻结旁白单元和实际 PCM 时间轴，归纳可跨多句的少量关键画面。实现独立 scene 规划/校验 API、共享视觉设定、固定基准依赖图、scene 与旁白关联、clip 预算及持久化恢复。产出 visual-bible.json、scene-plan.json 和可校验的 scene-plan-commit.json；每段目标画面数默认 3，单请求时长默认上限 6 秒。

可观察验收：

1. 至少一个画面覆盖两句旁白；画面数由语义分组决定。
2. 原文、完整配音及字幕不变，画面连续覆盖 0 至 total_frames，包括首尾和停顿；各语音单元 PCM 样本恰好覆盖。
3. 同主体使用稳定 ID，原文事实与创作选择分开记录；外观、场景变化具备原文依据。
4. 固定基准取最早实际 scene，依赖图可稳定拓扑排序；循环、错误来源和缺项拒绝。
5. 长画面增加 clip 不增加图片；默认 200 帧贡献为 [93,92,15]，生成帧为 [93,93,17]。历史槽位限制保持严格。

不提交即梦、Wan、TOS 或 SMTP，不实施选图和视觉验收，也不开放尚未完成的新策略全流程协调器。上述验收和 JIM-02 测试是待实施要求，尚无通过结果。

## Dependencies

### JIM-01

- **Artifact:** D:/code/py/video-ai/src/video_ai/jimeng_config.py；D:/code/py/video-ai/src/video_ai/runtime/production_inputs.py；D:/code/py/video-ai/src/video_ai/manifest.py；D:/code/py/video-ai/src/video_ai/runtime/jimeng_candidates.py。候选接口说明为 D:/code/py/video-ai/docs/jimeng-candidates.md，验证证据为 D:/code/py/video-ai/docs/task-designs/JIM-01-verification.md。
- **Decision:** 新策略为 paragraph_jimeng_v1；新策略 options/候选采用 schema=2，配置与模型选择冻结到 run。旧策略仍为默认，旧 schema=1 保留原字段集合。候选 API 独立于尚未完成的段落/邮件/视频协调器。
- **Rationale:** 新场景语义与旧单主旁白槽位不同；通过独立版本边界保留历史制作与恢复行为。冻结输入防止恢复时模型和参数被替换。
- **Constraint:** 不改变已有 options/候选身份，不向旧 resolved 快照增加字段，不放宽旧 StoryboardSlot 校验。新增 scene_planning 只在新策略读取冻结 raw 配置；不因规划完成绕过选图或协调器保护。
- **Usage:** 使用新策略身份与冻结输入建立 scene 规划记录，独立保存有效 settings、算法版本和源身份；规划输出只为后续候选/选图/视频提供数据，本任务不调用候选生成。
- **Readiness evidence:** 任务板 JIM-01 已记录 COMPLETED；专项 79 passed，历史配置/制作 CLI 专项 74 passed，修复后全套 2628 passed in 3758.32s，退出码 0。全套输出 D:/VideoSi/cache/video-ai/logs/jim-01-full-verified.txt。独立复核确认两项 Important 关闭。以上是 JIM-01 的结果，不是 JIM-02 的验证结果；未调用真实收费接口。

## Start Here

按顺序阅读：

1. D:/code/py/video-ai/docs/task-designs/JIM-02-design.md（完整实施契约）。
2. D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md 的 JIM-02 定义和本交接。
3. D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md，重点内容与时间轴、共享设定与参考图。
4. JIM-01 依赖中的冻结输入、配置、序列化及候选接口说明。
5. D:/code/py/video-ai/src/video_ai/planning/production_units.py、production_timing.py、production_timeline.py，以及 D:/code/py/video-ai/src/video_ai/runtime/production_timeline.py，核对原文与 PCM 事实来源。
6. D:/code/py/video-ai/src/video_ai/planning/production_visual_plan.py 和 D:/code/py/video-ai/src/video_ai/runtime/production_storyboard.py，保留旧帧预算与槽位约束。

收到明确的 JIM-02 开始请求后记录 READY -> IN_PROGRESS。第一个实施动作：按完成设计在 tests/unit/test_production_scenes.py 中建立同段两句共用 scene 的固定提案，并用真实 ProductionTimeline 断言完整原文、PCM bindings 与总帧覆盖；运行看到接口缺失的失败后，再实现独立 planning/production_scenes.py。

## Risks

- LLM 输出通过结构与来源检查仍不等于实际视觉一致，后续图片、动态过程和连续成片观察不能省略。
- 原文上下文超限时必须停止，不能裁掉原文；失败最多一次修正，未知请求需按设计消费原证据。
- 默认 6 秒按 Wan 的 4n+1 约束最多生成 93 帧；续 clip 需申请并丢弃一个衔接首帧，不能超预算或增加 scene 图片。
- 规划双文件以 commit 最后提交；中断只能由持久提案补齐缺项，冲突文件不能覆盖。
- 当前仅完成后继设计和交接，JIM-02 尚未实现，其新增测试尚未创建或运行。
