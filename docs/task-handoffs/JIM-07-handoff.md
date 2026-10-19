# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md`
- **Completed task:** `JIM-06`，已记录 `COMPLETED`。
- **Next task:** `JIM-07`，按预定义 Order=7 选择。
- **Design document:** `D:/code/py/video-ai/docs/task-designs/JIM-07-design.md`，已完成具体设计、全文自审并关联到任务板。
- **Expected next status:** `READY`；本交接写入、核对并关联后，才将观察到的 `NOT_STARTED` 转为 `READY`。不启动实现。

## Next Task

**JIM-07：跨阶段恢复、修订运行与局部返工。** 目标是多轮选图、动态观察及显式返工从确切进度续作，只重新生成受变更影响的内容，保留原运行和历史接受记录。

范围为 `make-video` 新策略协调、等待/CLI 消费和显式发布、跨阶段中断、内容与准入双依赖图、新修订冻结、来源可核验的局部继承、原 SMTP 未知后的显式重发。复用各阶段已经实现的 once-only、原 ID/graph 恢复和观察准入，不重做这些协议，不放宽旧 shot/schema=1。保持原生 16 fps、cut、1080p 和完整原文/PCM/字幕；用户最终澄清“视频的长度帧不限制，帧率也不变”。

验收条件：各阶段中断后不重复付费或发送；重选基准/返工父片和模型变更产生新冻结运行及正确失效闭包，无关已接受前缀可实际复用；原运行不变；两次完成重放严格只读；图片配置/选择、SMTP 未知、动态观察和最终观察等待状态清楚；当前字节的新专项、相关历史和全库结果落盘。真实服务和实际观看质量留给 JIM-08。

## Dependencies

### JIM-04

- **Artifact:** `D:/code/py/video-ai/docs/task-designs/JIM-04-design.md`、`D:/code/py/video-ai/docs/task-designs/JIM-04-verification.md`；`D:/code/py/video-ai/src/video_ai/runtime/production_reference_images.py`、`D:/code/py/video-ai/src/video_ai/runtime/reference_image_records.py`、`D:/code/py/video-ai/src/video_ai/runtime/reference_settings.py`、`D:/code/py/video-ai/src/video_ai/runtime/image_selection_records.py`、`D:/code/py/video-ai/src/video_ai/runtime/production_image_selection.py`。
- **Decision:** 固定已选原图与基准用途；关联图片必须有实际参考输入、模型能力和 TOS 对象来源。图片选择/整组观察与邮件送达是不同门槛。普通候选使用确切 scene.image_prompt，参考候选由 produce_reference_batch 构造固定 Bible 提示词。
- **Rationale:** 同一原图 SHA、用途和真实参考请求才能追溯一致性来源；不能靠模型名称或邮件成功推断已经观察通过。
- **Constraint:** 未知能力/缺配置返回 awaiting_image_model_configuration，不自动换模或退回文字生成。既有任务只查询原任务，未知 SMTP 不自动重发；凭证仅环境变量，签名 URL 不泄漏。普通 schema=2 记录及原 prepared-run --image-selection 消费结果不改。
- **Usage:** 协调器按已提交 batches 调用候选/参考生成与原邮件选择 API；所有批次和整组确认后生成并 require 确切 Wan 首图清单。修订仅通过新冻结绑定的 import 证明读取未变图片/选择/late-bound 配置，保留原原文与对象身份，不复制改写旧接受记录。
- **Readiness evidence:** 任务板 JIM-04 为 COMPLETED；其最终专项 118 passed、历史 186 passed、全库 3012 passed，退出 0，20 项身份匹配，详见所列验证文件。JIM-06 最终 fresh 全库 3396 passed、342 项文件前后和独立核对匹配，覆盖当前这些接口。HTTP/SMTP/TOS 替身及真实图像解码证据可用；真实上传、QQ 收信和参考服务读取未验收。

### JIM-05

- **Artifact:** `D:/code/py/video-ai/docs/task-designs/JIM-05-design.md`、`D:/code/py/video-ai/docs/task-designs/JIM-05-verification.md`；`D:/code/py/video-ai/src/video_ai/runtime/production_scene_clips.py`、`D:/code/py/video-ai/src/video_ai/runtime/scene_clip_records.py`、`D:/code/py/video-ai/src/video_ai/runtime/scene_clip_observations.py`、`D:/code/py/video-ai/src/video_ai/runtime/scene_comfy_transactions.py`、`D:/code/py/video-ai/src/video_ai/media/frames.py`。
- **Decision:** Wan 首片消费确切选图，子片消费父片实际最后保留原生帧；父片完整过程观察通过后才可推进子片。独立 scene 可以分别推进。原 UUID、graph、原始 HTTP/history 和逐帧 mapping 是恢复依据。
- **Rationale:** 裁掉的生成尾帧和首尾截图不能证明连续动态；父片漂移会传递到续片，必须按父子内容依赖失效。
- **Constraint:** 保持 native16/cut；200 帧例的保留/生成数为 93/92/15 与 93/93/17，第三片实际 generated 1..15，不能再次去头或截短旁白补时。未知任务不新 POST，观察失败不原地翻案，普通 clip/schema=2 字段保持严格。
- **Usage:** 使用 produce_scene_clips/consume_scene_clip_observation 和 load_scene_clip_progress/require_scene_clip_acceptance；透传 awaiting_continuity_review 及 observation_templates。修订实现按设计提取原验证中的指定节点/祖先只读准入，核验原过程观察后继承不变分支，不能强求失败来源的整个 scene 已 complete，也不能忽略相关失败原文。
- **Readiness evidence:** JIM-05 已 COMPLETED；最终历史 212 passed、全库 3206 passed，退出 0，21 项身份匹配。JIM-06 最终全库重新通过真实 200 帧链与现有 Wan/恢复回归，全部 3396 passed。真实媒体/父末帧/映射与测试填写观察证明接口行为；没有真实 Wan 品质或实际动态观看结论。

### JIM-06

- **Artifact:** `D:/code/py/video-ai/docs/task-designs/JIM-06-design.md`、`D:/code/py/video-ai/docs/task-designs/JIM-06-verification.md`、`D:/code/py/video-ai/docs/task-designs/JIM-06-review-followup.md`；`D:/code/py/video-ai/src/video_ai/runtime/production_scene_upscale.py`、`D:/code/py/video-ai/src/video_ai/runtime/production_scene_composition.py`、`D:/code/py/video-ai/src/video_ai/runtime/production_scene_delivery.py`、`D:/code/py/video-ai/src/video_ai/runtime/scene_media_records.py`、`D:/code/py/video-ai/src/video_ai/runtime/scene_completed.py`。
- **Decision:** 全部源片观察通过后逐保留帧超分；完整原 PCM、停顿、SRT/ASS/font 和帧序列形成技术候选。最终连续影片观察精确绑定候选、选图/基准和动态接受；消费观察与正式交付分离。已接受字节经自有 file-ID+SHA、不覆盖事务复制，receipt 最后。
- **Rationale:** 超分/编码技术成功不能代表实际影片一致性，重新编码或来源变化会使旧观察失效；无所有权的相同字节目标不能接管。
- **Constraint:** 沿原 prepared-run API、SceneMediaResult 和独立 schema=2 目录。只读 require/progress/completed-prefix 不补标志；每次副作用前重核上游字节/JSON inventory/正或空原日志/原 PCM/模型/工具及锁。FrozenInputs 原历史没有工具二进制 SHA，不虚构它。新修订 scene_revision 仅在新运行按 JIM-07 设计冻结，不在已接受 options 中追加。
- **Usage:** 协调器透传 awaiting_final_review/final_review_failed/final_review_ready，显式 publish 才调用 produce_scene_delivery。完成入口在加锁/日志写入前走完整只读快路。继承适配要传播 RevisionGuard，并替换 composition 对当前 clip/request.json 的硬读为有证明的比较输入 resolver，不放宽普通 run_path 或原来源验证。
- **Readiness evidence:** JIM-06 已先记录 COMPLETED。最终历史 **456 passed in 3866.66s**；fresh 全库 **3396 passed in 15981.10s (4:26:21)**，均退出 0，覆盖全部 190 个新增用例。脚本及协调者独立核对 **342/342 SHA256 匹配**。日志 `D:/VideoSi/cache/video-ai/logs/jim-06-full-final.txt`，核对 `D:/VideoSi/cache/video-ai/logs/jim-06-root-final-identity-check.json`。初次专项的 189 passed+1 failed 和测试预算修正后单例通过均保留在验证记录，未冒称单次专项全绿。独立复审无剩余 Critical/Important。真实完整候选、200 帧 93/92/15、交付恢复及两次只读重放已通过；实际观看/付费推理/云/邮件未执行。

三个输入的决策一致：原文/PCM/帧预算不截短，选择、过程观察和整片观察分别准入；原记录不可变，未知提交不能自动重试，正式交付独立且收据最后。JIM-07 的显式来源视图与新冻结绑定用于复用，不迁移旧运行或改写旧请求；当前没有未解决的依赖冲突。

## Start Here

按顺序阅读：

1. `D:/code/py/video-ai/docs/task-designs/JIM-07-design.md`（完整实施契约）。
2. `D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md` 的 JIM-07 与 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md` 的版本/返工约束。
3. `D:/code/py/video-ai/src/video_ai/production.py`、`D:/code/py/video-ai/src/video_ai/cli.py`、`D:/code/py/video-ai/src/video_ai/runtime/production_inputs.py`，核对新策略当前拒绝点、原消费路径和冻结条件。
4. 上述三个直接依赖的公共 API、只读 reader 与各自设计/验证；然后读 `D:/code/py/video-ai/tests/scene_media_helpers.py`、`D:/code/py/video-ai/tests/integration/test_make_video_recovery_contract.py` 和 `D:/code/py/video-ai/scripts/bootstrap.ps1`。

**第一实施动作：** 创建 `tests/unit/test_scene_revision.py:test_reselected_baseline_invalidates_reference_descendants_but_preserves_unrelated_scene`。用完整有效源快照构造 S1→S2→S3 参考链、独立 S4 和每 scene 的 clip 父子关系；重选 S1 的现有候选。断言 S1 候选集合仍可复用、S1 choice 与 S2/3 图片/选择及 S1/2/3 后续媒体失效，S4 内容保持 reusable，全组观察更新但不把准入边误当内容失效。bootstrap 后以 Python `-B` 运行设计中的首条测试命令，先观察缺新纯接口的 RED，再实现 `planning/scene_revision.py`。不先写协调器、不改上游已接受预算。

本次仅完成后继设计/交接；JIM-07 新测试和实现均未创建或运行。开始实现还需用户明确启动本任务。

## Risks

- 跨运行继承必须有新 frozen options→commit→imports→原始来源/本地副本的绑定，且内容 DAG 与准入门槛分开。不能改旧 run_id、伪造 paid intent/观察或仅凭相同字节复用。
- 来源本身可能为修订，必须追溯到实际 owned 请求；合法共享祖先不等于循环。原证据/模型丢失或未知外部任务尚待核对时保留来源并拒绝相应复用/再生成。
- 当前 Git 元数据只读，保留提供的 checkout 及前序未提交成果。Python/media 测试串行；每次 bootstrap、`-B`，运行/缓存/日志在 D:/VideoSi。
- 真实账号、QQ 收信、TOS 读取与实际观看仍未验收；本次没有新增外部发送或收费授权。JIM-08 承担真实服务及最终样片验收。
