# Next Task Handoff

## Handoff Type

next-task

## Task Link

- **Task board:** `D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md`
- **Completed task:** `JIM-05`，已先记录 `COMPLETED`。
- **Next task:** `JIM-06`，按预定义 Order=6 选择，观察到 `NOT_STARTED`。
- **Design document:** `D:/code/py/video-ai/docs/task-designs/JIM-06-design.md`，详细设计已完成、全文审阅并关联任务板。
- **Expected next status:** `READY`；本交接写入并关联后执行 `NOT_STARTED -> READY`，不启动实现。

## Next Task

**JIM-06 — 新时间轴合成与成片一致性交付验收。** 按确切 scene/clip 保留帧超分、完整 PCM/字幕合成候选片，只有最终连续影片的实际观察通过后才正式交付确切版本。

实施设计规定的 prepared-run Python APIs、独立 schema=2 逐帧超分单次事务、候选技术提交、最终观察、输出事务和只读完成前缀；复用 RealESRGAN_x4plus、现有 1080p/native16/cut 编码、完整旁白及字幕布局。保持旧 shot/schema=1 验证和交付契约。全流程协调、CLI 接通、修订/局部返工属于 JIM-07；真实服务与样片质量属于 JIM-08。

可观察验收：

1. 多句共画面和 200 帧长链按既有映射恰好超分/贡献 200 帧；93/92/15 个保留帧不二次丢首、不超分被裁掉的补帧。完整原文、PCM、字幕和首尾/停顿覆盖保留。
2. 技术候选可查看，但未核实或失败的最终连续影片不产生正式输出/收据。观察精确绑定候选/SRT、选图/基准、动态接受、每 scene、每相邻边界与全部原旁白单元，不能用截图或技术通过代替。
3. 有效实际观察后才复制被接受的同一 MP4/SRT 字节；媒体、原编码或上游身份变化使旧观察失效。输出不覆盖外部文件，收据最后，原提交/本地成功证据支持阶段内中断恢复。
4. 新 schema=2 完成前缀独立；旧 shot/映射/审核/交付和 CLI 恢复不被放宽或替换。
5. 状态明确区分 upscale_ready、awaiting_final_review、final_review_ready、final_review_failed 与 delivered；完成重放不启动服务、POST、提取、编码或复制。

本轮只完成 JIM-06 设计与准备，没有 JIM-06 新实现、新测试通过或真实影片观察结果。

## Dependencies

### JIM-03

- **Artifact:** `D:/code/py/video-ai/src/video_ai/runtime/image_selection_records.py:require_complete_image_acceptance`；prepared run 的 `production/image-selection/complete-acceptance.json`、各批次原选择和整组观察原文/接受记录；契约 `D:/code/py/video-ai/docs/task-designs/JIM-03-design.md`。
- **Decision:** 每 scene 恰好一张已核验原图，基准与整组 all_selected_images 实际观察独立于邮件发送和编号选择；恢复必须核对原始选择身份。
- **Rationale:** 最终影片必须追溯用户实际接受的主体、环境与风格依据，不能把新候选、邮件缩略图或未确认编号当作视觉准入。
- **Constraint:** 不重选、不修改已接受记录、不发新邮件、不伪造整组通过。JIM-06 只读消费同 run/plan/Bible 的完整准入；实际收信与图像品质仍不能由替身测试推定。
- **Usage:** 入口重新调用 require_complete_image_acceptance，规范摘要绑定超分/合成输入、最终观察和交付收据。具体参考原图及 JIM-04 来源继续由 JIM-05 原准入追溯，不绕过它。
- **Readiness evidence:** 任务板已记录 COMPLETED；`D:/code/py/video-ai/docs/task-designs/JIM-03-verification.md` 保存专项、历史和 2889 个唯一用例覆盖（初次并行异常及串行复查分别记录）。当前 JIM-05 新鲜全库串行 **3206 passed in 7302.90s**、退出 0，包含这些现存依赖测试。真实 QQ 投递未验证。

### JIM-05

- **Artifact:** `D:/code/py/video-ai/src/video_ai/runtime/scene_clip_records.py:require_scene_clip_acceptance`；同 run 的 `production/scene-clips/complete.json` 及其完整 inputs/request/graph/intent/原 HTTP/accepted/submission/媒体准备/clip/mapping/last-frame/观察原文与接受证据；契约 `D:/code/py/video-ai/docs/task-designs/JIM-05-design.md`。
- **Decision:** 每个父片和叶片实际过程观察都通过后才完整准入；source.mp4 已裁为实际保留范围，generated 原生索引、父末 PNG、选图/Bible 与完整旁白样本映射共同绑定。
- **Rationale:** 超分和最终影片不能重新猜切点、重复边界、掩盖漂移或漏掉原文；最终观看版本必须有不可变的动态来源。
- **Constraint:** 不只读 complete 文件存在；每次调用 require 重建全部来源。200 帧生成 93/93/17、source 保留 93/92/15，超分只处理 source 的 200 帧；source 第 k 帧对应 generated 的 retained_to_generated[k]。续片的首帧在 JIM-05 已丢，不能二次去头。原生 PNG 来自 generated，source 有损重编码像素可不同，不混淆两者。原图/父片/观察变化拒绝旧下游，未知 Comfy 不重复提交。
- **Usage:** require 返回的全清单规范摘要绑定超分 inputs；按原 clips 顺序从 source 解码保留帧，记录原生成索引和全局输出索引；其 clip/观察摘要、selected_image/comparison_images 和 Bible 身份继续绑定最终观察与交付。
- **Readiness evidence:** 已先记录 COMPLETED，五项结果见 `D:/code/py/video-ai/docs/task-designs/JIM-05-verification.md`。原导入版本专项 **269 passed**，最终字节历史 **212 passed**，新鲜全库 **3206 passed in 7302.90s (2:01:42)**，均退出 0；全库包含最后补充的失败观察原文中断、临时裁片恢复和未知 run。**21 个文件 SHA256 匹配**，日志 `D:/VideoSi/cache/video-ai/logs/jim-05-full-final.txt`，核对 `jim-05-verified-files-check.json`。独立审查无剩余已确认 Critical/Important。替身与真实 ffmpeg 媒体不代表真实 Wan 品质通过。

两项直接输入必须指向同一个 frozen run、scene plan 与 Bible。JIM-03 提供完整选图及整组观察，JIM-05 提供源片与逐片动态观察，两者门槛叠加，不互相替代；目前没有已知未解决冲突。JIM-04 来源通过 JIM-05 准入继续验证，不另立与任务板不符的直接依赖。

## Start Here

1. 全文读取 `D:/code/py/video-ai/docs/task-designs/JIM-06-design.md`；精确接口、记录、观察、失败/恢复和测试均已确定，不重新设计本任务。
2. 读取 `D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md` 的 JIM-06 行/详情及总体方案 `D:/code/py/video-ai/docs/task-designs/jimeng-email-scene-design.md`。
3. 读取上述两个直接准入接口、`D:/code/py/video-ai/docs/task-designs/JIM-05-verification.md`、`D:/code/py/video-ai/tests/scene_clip_helpers.py` 与 `D:/code/py/video-ai/tests/unit/test_scene_clip_continuation.py`，核对真实已接受源片和 200 帧预算。
4. 读取 `D:/code/py/video-ai/src/video_ai/runtime/production_upscale.py`、`production_composition.py`、`production_delivery.py`、`production_completed.py`、`D:/code/py/video-ai/src/video_ai/media/production_composition.py`、`media/subtitles.py`、`D:/code/py/video-ai/src/video_ai/planning/final_review.py` 及 `D:/code/py/video-ai/workflows/upscale_api.json`/`upscale_api.mapping.json`；只复用纯规则和服务/媒体机制，不放宽旧 validator。

**Concrete first action:** 用户明确启动 JIM-06 后，在 `tests/unit/test_scene_media.py` 建 `test_200_retained_frames_upscale_once_without_second_head_drop`，用既有 200 帧预算和真实 JIM-05 mapping 调用设计规定的 plan_scene_upscale，断言 200 行、93/92/15、第三片 generated=1..15、global=0..199、child retained=0 映到 generated=1。bootstrap 后运行设计 Tests 的第一条 pytest 命令，先记录缺接口 RED，再实现独立纯计划；不修改 JIM-02/JIM-05 预算或启动真实模型。

## Risks

- 超分可能改变细节；源片已观察不代表最终候选通过。最终完整音视频观察是正式交付前独立门槛，替身 authored 结论只验证准入。
- 全量解码与逐帧超分耗时较高，仅允许调用内 SHA 绑定复用；不能用 mtime 或首尾帧代替完整核验。
- Comfy 原证据丢失、未知受理或输出冲突时保留诊断，不重发；媒体/输出中断必须从确切准备收据和 owned file_id 恢复。
- 三个外部输出不能同时原子发布，事务可能保留自有部分输出；收据最后且全套读回一致才报告 delivered，不能覆盖无关目标。
- Git 元数据只读，前序变更保留在当前 checkout；Git 只读命令可通过 `C:/Program Files/Git/cmd/git.exe` 使用。本轮没有提交、合并或 PR，不因 READY 自动启动 JIM-06。
