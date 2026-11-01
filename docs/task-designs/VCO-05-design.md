# VCO-05：20 秒隔离验证

## Goal

在当前资源下，以一次真实 Wan2.2 请求验证或否定 20 秒候选。用户 2026-10-27“完成任务VOC-05”按本项目唯一对应编号 VCO-05 执行，包含任务板规定的首例试验；跨题材追加仍须另行授权。

## Scope

实现通用、独立于生产预算的实验工具、必要定向测试及首例证据。只读源 run `D:/VideoSi/projects/video-ai/runs/20261021-014723-4ebdc1fecab2`，scene `scene_0003`，首片 `scene_0003_clip_0001`。不集成 whole_scene_v1，不追加推理、下载模型、发布或修改源 run。软件文件在现有工作区新增，.git 只读，不创建丢失未提交依赖的 worktree。

## Approach

沿用 JIM-08 B 阶段既定方案：独立 Python runner，冻结 case/graph/完整模型 SHA、源码、工具、已准入图片及视觉提示契约；不调用旧 make-video，不解除 96 帧 guard。其他方案（修改生产预算、复用历史失败窗口后端）不符合本任务既定范围。

`src/video_ai/experiments/whole_scene_case.py` 提供 `prepare_case(source_run, scene_id, contract_path, root)` 与 `verify_case(root)`：从冻结配置、计划、visual bible、wan-inputs 及首片 input/request 读取真实身份，校验 VCO-01 完整契约与纯视觉 renderer；原首片 seed=264244520399004，低噪声 seed=0。只更换 positive、start_image/output 相对路径、length=321；固定768×432、16fps、batch1、40步、CFG3.5、Euler/simple、15步切换和原模型。冻结源文件清单（bytes/SHA/mtime）及其副本；模型逐字节 SHA，服务代码/工具亦冻结。证据根为 `D:/VideoSi/cache/video-ai/logs/vco05-<唯一编号>`，禁止与源路径包含或重叠。

`whole_scene_runner.py` 提供 `execute_case(root)`：独占文件锁；校验冻结身份后，仅启动自己创建的 ComfyUI 子进程，独立 loopback 端口、input/output/temp/user/database。占用端口拒绝，不复用/终止外部服务。保存服务命令、日志、PID、启动与结束时间；每2秒采样 nvidia-smi、系统内存和自有进程RSS。启动有冻结配置 service_start=300秒期限，推理沿用 wan=7200秒绝对期限。启动前核对空闲内存及显存和活动计算进程；资源无法核实拒绝，不声称可装载。

发送前持久化 intent.json（case/graph SHA、UUID client_id、UTC期限）、精确 request 原文和 HTTP 记录。存在 intent 的任何重进只查询原 client/graph 匹配的 queue/history；不得再次 POST。服务不在时不得重启后补单。已知 ID 检查返回 graph/client；未知 ID 以两接口唯一匹配恢复。HTTP 原文、状态、错误持久化。错误、OOM、超时、非法输出均保留并停止，不降规格。锁竞争和崩溃不会打开第二次提交机会。终态保留独立 result.json，查询恢复另存 receipt，不覆盖原终态。

`whole_scene_media.py` 提供 `audit_output(root, output)`：只接受自有 output 中精确映射的单个 MP4，实际完整解码及 ffprobe 逐帧 PTS/尺寸/帧数验证。必须恰为321帧/16fps；解码全部原生PNG并冻结SHA，保留映射恰为[0,320)，源帧320仅为丢弃尾帧。以 PNG 0..319 编码无损 RGB 审阅片（libx264rgb/crf0），验证320帧、PTS=i/16及20秒，无调色/插帧/变速。记录所有命令和原始probe、输出SHA、原始帧SHA及逐帧RGB亮度/色度分布、通道均值、高光/暗部截断与采样图；源色彩元数据缺失保留unknown，明确未配对RGB码值统计不能判定颜色通过。没有输出时上述媒体项标为未产生，而非伪造空样片。

2026-10-27 播放兼容修复：用户报告无损review.mp4无法打开。实测SHA未变、完整FFmpeg解码成功，但profile为High 4:4:4 Predictive/gbrp，部分系统播放器不支持。保留这份无损审计证据，新增 `create_playback_review(root)`：从原生成YUV视频精确保留[0,320)，编码独立 `review-playback.mp4`（libx264 CRF16、High、8-bit yuv420p、faststart），验证320帧/20秒/逐帧PTS。该副本明确标记lossless=false，颜色解释字段沿用已验证原片，不缩放、改fps或校色。独立playback-review.json绑定原片、无损片、映射、新副本、当前后处理源码及工具身份；不重签原case/原media/result，不重新POST。新审计和旧审计重进都保证有兼容播放副本；缓存副本漂移时拒绝。

结果分记 technical、resources、sampled_appearance、full_video_observation、production_eligible、cross_subject。默认完整动态观察 unverified；实际视频观察须绑定审阅片SHA、方法human_video或具备真实全播放能力agent_video、完整覆盖、四项检查及审阅者。静帧/自动统计不能晋升passed。明确静态失败可直接否定候选并停止；失败任务交付不等于生产准入。

## Files

- 新增 `src/video_ai/experiments/__init__.py`、`whole_scene_case.py`、`whole_scene_runner.py`、`whole_scene_media.py`。
- 新增 `scripts/experiments/vco05_whole_scene.py`：prepare/execute/audit/status 入口，不编码具体题材。
- 新增 `tests/unit/test_whole_scene_experiment.py`、`tests/integration/test_whole_scene_media.py`：预算/身份/一次提交恢复与真实CPU媒体验证。
- 更新本任务板行及本任务详情；新增 plan、verification 和实际结果交付，保留所有历史文件。

## Tests

所有 Python 先 `. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment 'vco05-<stage>'`。使用 `$VideoAiPython -B -m pytest tests/unit/test_whole_scene_experiment.py tests/integration/test_whole_scene_media.py -q --basetemp "D:/VideoSi/cache/video-ai/temp/vco05-$VideoAiCommandId" -o cache_dir=D:/VideoSi/cache/video-ai/pytest`，预期退出0。先缺失接口RED，再GREEN；测试与真实GPU串行。必要兼容覆盖 `test_scene_video_prompts.py`、`test_scene_clip_continuation.py`、`test_scene_clip_generation.py`，不跑全库。

覆盖321/320映射、graph/输入/模型/提示漂移零POST、已存在intent/未知HTTP结果不重POST、失败不降规格、原run前后SHA/mtime一致、锁竞争、输出路径越界、损坏/错误帧数/错误fps、真实320帧无损审阅RGB及PTS。实际原例资源和HTTP记录单独登记，fixture不代表真实能力。

## Acceptance

对应任务板五项标准逐项报告。一次首例成功须有全部媒体/资源证据；有有效完整动态观察才产生准入。失败须有原错误、时间、资源、HTTP和原run不变证据，停止追加。跨题材未授权明确不执行，不作跨题材能力声明。无观看能力时保留unverified，不能用软件测试完成替代真实试验结论。

## Risks

24GiB显存可能无法完成321帧；7200秒不保证成功。服务退出会丢失内存history，未知任务仍不可补单。模型哈希需读取约36GB。当前没有可用的完整视频感知工具，成功样片完整动态观察可能需要用户实际播放反馈；这不阻止先完成软件和已授权真实首例。跨题材只在另行授权后执行。全库回归沿用户既定安排留至VCO-08。
