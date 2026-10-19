# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md`
- **Completed task:** `JIM-04`，已记录 `COMPLETED`。
- **Next task:** `JIM-05`，按预定义 Order=5 选择。
- **Design document:** `D:/code/py/video-ai/docs/task-designs/JIM-05-design.md`，已完成、全文审阅并关联任务板。
- **Expected next status:** `READY`；本交接写入并关联后执行 `NOT_STARTED -> READY`，不启动实现。

## Next Task

**JIM-05 — Wan 连续片段、末帧续接与动态观察。** 用户所选原图进入 Wan，同一长画面沿已观察父片的实际保留末帧续接；未观察或不一致时阻止后代提交。

实施 completed design 中的 prepared-run Python API、独立 schema=2 scene clip 记录、比例适配 PNG、原生指定帧提取、区间裁片、精确 frame/sample 映射、实际过程观察准入、独立 scene 推进和 Comfy 原任务恢复。复用既有 Wan 模型与冻结工作流，保持旧 shot/schema=1 契约。全流程协调、CLI、超分、合成、最终影片观察、交付与修订返工不在本项实施范围。

可观察验收：

1. 完整图片准入前零 Wan POST/模型服务启动；首片 actual graph 使用确切所选原图的受控 PNG 副本，固定主体/环境提示词完整保留。
2. 续片使用直接父片 generated 视频中最后一个实际保留 native 帧，绑定父片/PNG/观察身份；父片未观察或失败时不提交 child，独立 scene 仍可推进。
3. 200 帧例生成 `[93,93,17]`，保留 `[93,92,15]`，原生保留区间为 `[0,93)`、`[1,93)`、`[1,16)`；末帧零基索引为 `[92,92,15]`。最终恰好覆盖 `[0,200)`，原文、PCM、字幕和停顿覆盖不变，不循环、冻结或截短补时。
4. 每片包括叶片均需实际完整过程观察；截图/相似度/技术通过不能替代观看。等待返回 `awaiting_continuity_review`，未核实或不一致不产生完整源片准入。
5. 中断恢复使用确切原 Comfy intent/UUID/graph；未知提交不重发，父片身份变化拒绝旧 child。全部媒体和观察有效后才有可只读重新核验的 `production/scene-clips/complete.json`。独立 scene 的等待/失败互不混淆，自有服务和锁按契约清理。

本轮仅完成设计和交接；上述为待实施验收，尚无 JIM-05 实现、测试或真实动态观察结果。

## Dependencies

### JIM-02

- **Artifact:** `D:/code/py/video-ai/src/video_ai/planning/production_visual_plan.py:plan_scene_clips`；`D:/code/py/video-ai/src/video_ai/runtime/image_selection_records.py:load_committed_plan`；每个 prepared run 的 `production/visual-bible.json`、`production/scene-plan.json`、`production/scene-plan-commit.json`；契约 `D:/code/py/video-ai/docs/task-designs/JIM-02-design.md`。
- **Decision:** 区分 unit/scene/clip，固定 Bible 主体/外观/环境和直接基准；使用已提交的 native16、最多 6 秒 clip 预算，续片丢首、最后补齐尾帧可裁除。
- **Rationale:** 一个画面可覆盖多句旁白，长画面拆片不会增加 scene 图片；保持完整原文、PCM 样本和全局帧覆盖。
- **Constraint:** 不重新规划 scene 或修改已提交预算；不得放宽旧 shot 槽位校验。200 帧数值必须保持上述区间，父末帧不能取被裁掉的补帧。新 scene 是有意 cut，不自动接前 scene 末帧。
- **Usage:** 先通过 load_committed_plan 校验 commit 和完整输入，再从原 clips 重建 request、frame mapping 与 narration_bindings；沿 Bible 顺序保留共享设定和比较基准。
- **Readiness evidence:** 任务板已记录 `COMPLETED`；`D:/code/py/video-ai/docs/task-designs/JIM-02-verification.md` 记载修复后专项/相关历史 267 passed、全套 2757 passed，200 帧预算和样本覆盖已有验证。真实模型与视觉结果未在该项验证。

### JIM-04

- **Artifact:** `D:/code/py/video-ai/src/video_ai/runtime/reference_image_records.py:require_reference_image_acceptance`；每 run 的 `production/reference-images/wan-inputs.json` 及其重新核验的选图、整组观察和参考来源；契约 `D:/code/py/video-ai/docs/task-designs/JIM-04-design.md`。
- **Decision:** Wan 只消费所有图片选择及整组实际观察通过后的原图清单，行包含确切 scene/candidate/原 task 身份、unit_ids、baseline_bindings 和 reference_provenance_sha256；同主体跨画面直接引用固定基准。
- **Rationale:** 保证动态起点对应用户接受的原图和共享视觉设定，防止邮件预览、邻近候选或独立纯文字图冒充已接受参考结果。
- **Constraint:** 必须调用只读 require_reference_image_acceptance，不能仅信任清单存在。原图/来源/接受记录变化即拒绝；不修改原图、选图、模型或补齐配置绑定。JPEG decoder 的 mjpeg 视为 JPEG；不同 primary/reference 图尺寸各自验证，不能强套主模型尺寸。只在本项确定的 native profile 适配副本上处理，保留原输入身份。
- **Usage:** 将清单规范摘要绑定 inputs.json，每个 scene 原行绑定 selected_image；从原图生成首片受控 PNG。按 Bible 引用顺序绑定固定比较图，续片仍保留同 scene 的 selected_image，同时另绑定父末帧和父观察。
- **Readiness evidence:** 任务板已记录 `COMPLETED`；`D:/code/py/video-ai/docs/task-designs/JIM-04-verification.md` 记载最终新专项 **118 passed in 360.71s**、相关历史 **186 passed in 200.44s**、串行全套 **3012 passed in 3840.59s**，均退出 0；独立审查无剩余 Critical/Important，20 个验证文件 SHA256 未变。证据为本地真实媒体和 HTTP/SMTP/socket 替身，未验证真实云上传、QQ 投递或视觉质量。

两项输入的 scene/plan/Bible 摘要均须指向同一个 prepared run。预算规定时间与原生帧来源，图片清单规定固定选图和比较依据，二者不存在已知未解决冲突；新 schema=2 记录应同时绑定两项，不能以其一替代另一项。

## Start Here

1. 全文读取 `D:/code/py/video-ai/docs/task-designs/JIM-05-design.md`，这是全部精确接口、字段、事务和失败规则的实施依据。
2. 读取 `D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md` 的 JIM-05 行/详情及总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md`，核对任务边界。
3. 读取 JIM-02 的上述规划/commit 接口和 `D:/code/py/video-ai/tests/unit/test_scene_clip_budget.py`，再读取 JIM-04 的上述准入接口和 `D:/code/py/video-ai/docs/task-designs/JIM-04-verification.md`。
4. 读取 `D:/code/py/video-ai/src/video_ai/runtime/production_comfy.py`、`runtime/production_visuals.py`、`media/frames.py`、`media/video.py` 与 `D:/code/py/video-ai/workflows/wan22_i2v_14b_api.mapping.json`，按设计复用纯规则并保留旧入口。

**Concrete first action:** 用户明确启动 JIM-05 后，在 `tests/unit/test_scene_clip_continuation.py` 建 `test_200_frame_retained_native_mapping`，由既有 plan_scene_clips 生成 200 帧预算，调用设计确定的新 mapping API，断言保留/生成帧、head/tail null、末保留索引和全局恰好一次覆盖；bootstrap 后运行设计 Tests 中第一条 pytest 命令，先记录缺新接口的 RED，再实现纯规则。不要重新设计预算或启动真实推理。测试按设计串行执行，Python 使用 `$VideoAiPython -B`，临时/缓存/日志置于 D:/VideoSi。

## Risks

- 固定基准和父末帧不能保证 Wan 的身份/动作连续性；真实过程观看是每片门槛，明确失败阻断后代，修订返工留给后续任务。
- Comfy 原 history 遗失或接受不明时只能保留未知状态，不自动重发。服务操作必须有可验证 run ownership；等待或本地完成回放不启动服务。
- source.mp4 有损重编码可能改变像素，续片 PNG 必须从 generated 的实际保留 native index 提取并与观看版本同时绑定。
- 真实 Wan、云存储读取、QQ 收信和画面质量未验证，仍需后续真实验收。JIM-04 的替身测试结果不能登记为 JIM-05 或真实视觉通过。
- 当前会话 Git 不可用且 .git 只读，JIM-04 变更保留在提供的 checkout；不要声称已提交或创建 PR。只在用户启动本项后实施，不因 READY 自动运行。
