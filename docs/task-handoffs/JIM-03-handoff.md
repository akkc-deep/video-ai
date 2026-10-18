# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md
- **Completed task:** JIM-02，已记录 COMPLETED。
- **Next task:** JIM-03，按预定义 Order=3 选择。
- **Design document:** D:/code/py/video-ai/docs/task-designs/JIM-03-design.md
- **Expected next status:** READY；交接写入及关联后由 NOT_STARTED 转入，不启动实现。

## Next Task

JIM-03：候选图邮件、基准选图与等待续作。

把持久候选发到已确认的 QQ 邮箱，核验用户的候选编号选择并保存基准/接受记录，安全返回等待。范围包括 SMTP SSL、实际附件/整组对照图、完整 MIME 编码后拆包、稳定 Message-ID、发送意图/回执、选择草稿/接受、整组观察绑定、--image-selection 及 schema=2 结果。发件和收件均为 318575094@qq.com；不自动收信，不做网页。

验收：① 本地 SMTP 替身收到真实图片、原文、基准用途、可复制编号和一致性要求，每封完整 MIME 默认 <=15 MiB 且无候选遗漏。② 成功页不重复发送，未知发送不自动重试，修复 SMTP 不重新出图。③ 当前批一 scene 一张且身份正确才接受，跨 run/批/候选、缺项/重复/图片变化拒绝；部分选择仅草稿。④ 编号选择不生成整组通过结论，完整选择和全组实际观察不齐则无完整准入收据，任何路径不提交 Wan。⑤ 等待/异常后公开入口自有锁及 SMTP 连接释放，已选基准保留。

本任务通过准备运行和后续批次替身实施，不实现参考图生成、TOS、视频或完整新文案协调器；没有批次的新策略仍保留未实施协调器保护。尚未创建或运行 JIM-03 新测试，没有真实邮件投递结果。

## Dependencies

### JIM-01

- **Artifact:** D:/code/py/video-ai/src/video_ai/runtime/jimeng_candidates.py；D:/code/py/video-ai/src/video_ai/runtime/production_inputs.py；D:/code/py/video-ai/src/video_ai/adapters/jimeng.py；实际候选位于运行内 production/jimeng/<scene_id>/candidates.json 及其 request/result/下载收据/原图。
- **Decision:** schema=2 冻结模型及参数；候选 ID 在 scene 内唯一，官方 task_id 不冒充 Comfy UUID；原图由 SHA256/尺寸及下载收据约束。
- **Rationale:** 通知/续作只能复用确切已有候选，不能因为邮件故障产生重复图片费用或错误接受另一张图片。
- **Constraint:** 保留原模型及既存记录，不借只读校验调用 generate_candidates，不记录 AK/SK、SMTP 授权码或临时签名 URL。旧 schema=1 保持原路径。
- **Usage:** 按设计只读核验并收集本批 candidate manifest，将原 scene/candidate/request/task/req_key/SHA256 关联到邮件附件和接受记录。
- **Readiness evidence:** 任务板 JIM-01 已记录 COMPLETED；其专项 79 passed、历史配置/CLI 74 passed、全套 2628 passed。JIM-02 修复后最终全套 2757 passed 也包含这些历史用例；真实账号能力不由替身测试证明。

### JIM-02

- **Artifact:** D:/code/py/video-ai/src/video_ai/planning/production_scenes.py；D:/code/py/video-ai/src/video_ai/planning/visual_consistency.py；D:/code/py/video-ai/src/video_ai/runtime/production_scene_plan.py；具体运行的 production/visual-bible.json、scene-plan.json、scene-plan-commit.json；契约 D:/code/py/video-ai/docs/task-designs/JIM-02-design.md，证据 D:/code/py/video-ai/docs/task-designs/JIM-02-verification.md。
- **Decision:** schema=2、paragraph_jimeng_v1、scene_planning_v1；完整原文、多 unit scene、固定 entity/variant/group 基准、reference_bindings 多用途和稳定拓扑 batches。下游要求有效 commit，重新核对规范 JSON 哈希及原文/units/timeline/settings/run。
- **Rationale:** 邮件和选择必须对应当前完整计划，先选择固定基准，再由后续任务生成其依赖画面；摘要不能替换原文，结构通过不能冒充视觉通过。
- **Constraint:** 不改原文、PCM、字幕、scene/clip 或基准图关系；不覆盖冲突计划，不接受未提交半成品，不把当前批选择当整组一致性。JIM-02 只规划数据，不提供图片接受或视频生成。
- **Usage:** 从已提交计划按 batches 建通知批次；原文使用 scene 的原始字符包络，使用 baselines/reference_bindings 显示确切基准用途；选择和观察绑定 bible/plan/批次及原图 SHA256。准备 CLI 输入时保留实际 units/timeline 报告，缺失时停止而不重新生成。
- **Readiness evidence:** JIM-02 已先记录 COMPLETED；专项与相关历史/Ollama 267 passed in 31.29s；修复后最终全套 2757 passed in 3790.62s (1:03:10)，退出码 0。完整输出 D:/VideoSi/cache/video-ai/logs/jim-02-full-verified.txt。未来外观/场景来源及上下文截断两项 Important 均有失败测试后修复；没有真实付费/上传/邮件。

两项输入的身份与恢复规则一致：冻结生成输入，复用持久原图及计划；通知配置/凭证修复只影响未确认通知，不改变图片、计划或已选基准。未发现直接依赖决策冲突。

## Start Here

1. D:/code/py/video-ai/docs/task-designs/JIM-03-design.md（完整实施契约）。
2. D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md 的 JIM-03 定义及本交接。
3. D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md 全文，重点候选图/邮件/等待/选图/版本恢复。
4. D:/code/py/video-ai/src/video_ai/runtime/jimeng_candidates.py、production_inputs.py 和 JIM-02 的 production_scenes.py、visual_consistency.py、production_scene_plan.py。
5. D:/code/py/video-ai/src/video_ai/cli.py、production.py、runtime/production_state.py、runtime/production_visual_review.py、media/images.py。

收到明确开始请求后记录 READY -> IN_PROGRESS。首个实施动作：在 tests/unit/test_selection_email.py 建立两 scene、同名局部 candidate ID、真实 PNG、固定原文和基准用途的批次 fixture，测试 build_messages 的实际 MIME，断言可复制 scene_0001=request_01_image_01、准确原文、附件解码和完整 MIME 限额；先观察接口缺失失败，再实现 adapters/selection_email.py 的纯构建部分。Python 前先执行 scripts/bootstrap.ps1 与 Initialize-VideoAiEnvironment。

## Risks

- QQ SMTP 启用、授权码、实际收件箱尚未验证；本任务测试必须使用本机替身，不能发真实测试邮件。
- SMTP 2xx 不是收件箱证明，未知 DATA 结果必须停止；显式重发可能重复邮件，需指定确切原尝试摘要。
- 实际看图结论须由用户或有查看能力的审查者提供，不可自动填写 passed；实际图片/视频一致性未被 JIM-02 自动验证。
- 后续参考生成尚未实现，本任务模拟其候选输入，不得悄悄退回全部独立出图或放开 Wan。
