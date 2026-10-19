# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md
- **Completed task:** JIM-03，已记录 COMPLETED。
- **Next task:** JIM-04，按预定义 Order=4 选择。
- **Design document:** D:/code/py/video-ai/docs/task-designs/JIM-04-design.md
- **Expected next status:** READY；设计关联与本交接写入后由 NOT_STARTED 转入，不启动实现。

## Next Task

JIM-04：参考图存储与关联画面一致性生成。将已接受固定基准原图实际用于关联图片请求，再复用邮件选图/全组观察，产生精确 Wan 首图清单。

范围：配置的现有私有 TOS 桶、内容寻址上传/GET 预签名、明确核对的模型能力档案、受控 image_urls 与共享视觉设定、单次提交恢复和参考来源重验。已冻结但缺参考设置的 JIM-03 运行可以用显式 reference_settings_path 补齐并在首次云请求前冻结，不修改原冻结文件/基准。无参考能力或配置时等待，不能猜测能力/自动换模/退回纯文字。

验收：① 实际替身请求含确切已选基准，全部主体/背景用途保留，同主体直接引用固定图。② 未选、缺配置/能力、数量/尺寸/字节/TTL 不合规时零关联付费提交。③ 本地 SHA/TOS 对象/来源可核验，签名 URL 不进普通记录或日志，不创建桶/改权限。④ 未提交可刷新 URL，有任务只查原 task_id，unknown 不自动补单。⑤ 完整选择及全组 passed 实际观察后才产生有真实参考 provenance 的 Wan 输入，任何本阶段路径不请求 Wan。

本交接是实施入口，不代表参考生成/TOS 已实现或任何新增 JIM-04 测试通过。

## Dependencies

### JIM-01

- **Artifact:** D:/code/py/video-ai/src/video_ai/adapters/jimeng.py、adapters/external_https.py、runtime/jimeng_candidates.py、runtime/production_inputs.py；运行内 production/jimeng/<scene_id>/candidates.json 及每请求的原图/下载收据/request/result。
- **Decision:** 通用官方异步协议、冻结用户所选模型/参数、scene 内局部 candidate ID、已接受任务查原 task_id；原图 SHA256/尺寸真实核验。
- **Rationale:** 参考输入扩展不能造成重复出图费用、模型暗换或错误候选复用。
- **Constraint:** 保留原纯文生图/schema1 行为；不传播 AK/SK、Authorization 或签名 URL；新参考请求用单独逻辑身份和来源，不伪装旧纯文字 request。
- **Usage:** 显式受控 reference 参数扩展 JimengClient；查询、下载及完整候选行继续既有契约。外部 HTTPS 仅增加有限 PUT/HEAD 及只读 ownership hook，保持无重定向/重放/原始秘密日志。
- **Readiness evidence:** 任务板 JIM-01 已 COMPLETED；原专项79、历史74、当时全套2628通过；JIM-03 完整覆盖2889包含相关历史，新实现无需重做旧候选生成。

### JIM-02

- **Artifact:** D:/code/py/video-ai/src/video_ai/planning/production_scenes.py、planning/visual_consistency.py、runtime/production_scene_plan.py；同运行 production/visual-bible.json、scene-plan.json、scene-plan-commit.json。
- **Decision:** 固定 entity/variant/group 基准和多用途 reference_bindings，按稳定拓扑 batches 推进；完整原文/units/timeline/计划规范摘要绑定。
- **Rationale:** 多画面主体一致性必须直接消费固定基准及共享设定，不能以相邻随机候选累计误差或丢掉用途。
- **Constraint:** 不改原文、PCM、字幕或既定基准关系；要求有效 commit 并重验，结构正确不代表视觉一致性通过。
- **Usage:** 根据当前 batch 和精确 uses 找已选基准，按 bible 基准顺序去重图片而保留用途；构造参考 prompt context，生成与 scene 对齐的 Wan 输入。
- **Readiness evidence:** JIM-02 已 COMPLETED，原专项267、全套2757通过；最新JIM-03完整覆盖保留规划历史，任务设计及验证分别为 D:/code/py/video-ai/docs/task-designs/JIM-02-design.md、JIM-02-verification.md。

### JIM-03

- **Artifact:** D:/code/py/video-ai/src/video_ai/runtime/production_image_selection.py、runtime/image_selection_records.py、media/selection_sheet.py、adapters/selection_email.py；测试素材与工具 D:/code/py/video-ai/tests/image_selection_helpers.py；验收 D:/code/py/video-ai/docs/task-designs/JIM-03-verification.md。
- **Decision:** batch/accepted/complete 与原图、提交副本、真实邮件回执精确绑定；选编号不产生视觉通过。prepare_image_batch 消费候选清单，consume_image_selection 消费用户文件；require_complete_image_acceptance 重新校验所有后备。
- **Rationale:** TOS 发布和后续请求必须使用用户确切接受的原图；邮件问题不能重新出图，全组观察不能由技术检查代写。
- **Constraint:** 所选基准和 accepted 不可变；原始用户文件复制后以副本为证据；unknown 不自动重发；当前批一 scene 一张；所有提交/SMTP 前持锁。JIM-03 的后续纯文生图测试素材仅模拟，不是已实现参考生成证据。
- **Usage:** 调用 load_committed_plan/load_accepted_batches 取得已验基准；生成关联候选后调用 prepare_image_batch，等待时释放自有锁。完整选择和实际全组观察后先 require_complete_image_acceptance，再增加 JIM-04 reference provenance 准入。保留旧纯文字候选只读分支，同时支持新 reference_inputs 分派。
- **Readiness evidence:** JIM-03 已先记录 COMPLETED。新专项最终CLI修复前129 passed；独立整体审查两项CLI Important均RED→GREEN并补锁退出OSError；相关历史114 passed。144模块全量初次2886 passed、2 failed、1 error；三个旧测试不改代码串行3 passed，完整2889个唯一用例均有通过证据，D:/VideoSi/cache/video-ai/logs/jim-03-verified-coverage.json。原并行异常及发布准备原因未确定的限制如实保留。没有真实邮件、云上传、收费生成或Wan。

三项直接输入约束一致：固定原文/模型/计划/基准、已提交不重放、等待保留原图、视觉观察不自动批准。JIM-04 的可选补配置仅填此前缺失的参考阶段字段，不修改 JIM-01 主模型/JIM-03 选择；参考阶段首次绑定后也不可变。未发现未解决的直接依赖冲突。

## Start Here

1. D:/code/py/video-ai/docs/task-designs/JIM-04-design.md（完整接口、配置、协议、记录和测试契约）。
2. D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md 的 JIM-04 定义和本交接。
3. D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md 的参考图/一致性/恢复部分。
4. JIM-03 的 image_selection_records.py、production_image_selection.py、tests/image_selection_helpers.py，再读 JIM-01 jimeng.py/external_https.py/jimeng_candidates.py。
5. 官方 TOS Python SDK auth.py 与总体方案的官方即梦/TOS资料；实际模型限额必须来自显式核对档案，不能从测试档案推广。

收到明确实施请求后记录 READY -> IN_PROGRESS。第一动作：按设计，在 tests/unit/test_reference_storage.py 固定 UTC=2026-10-18T00:00:00Z、AK=test-ak、SK=test-sk、region=cn-beijing、bucket=test-bucket、内容寻址 key 和 GET TTL=3600，写独立 TOS4 签名向量测试；bootstrap 后先观察缺适配器失败，再实现纯签名及受控 HEAD/GET/PUT。不要再次设计或重做 JIM-03。

## Risks

真实模型参考能力、账号权限、TOS 桶、AK/SK、取图和 QQ 收信尚未验证；缺配置返回已定义等待，不能假装准备完成。能力档案由明确核对者提供，实际限额/效果仍需后续真实验收。TOS 签名 URL 是临时凭证，只在内存用于提交，普通日志不可保存。重选基准/改变已绑定参考配置需新修订运行。完整历史测试宜串行运行，避免已观察到的全局运行目录断言和共享 GDI 字体访问干扰。
