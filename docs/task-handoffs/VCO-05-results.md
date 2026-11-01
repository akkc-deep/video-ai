# VCO-05 首例隔离验证结果

2026-10-27。任务板 `docs/task-handoffs/video-continuity-optimization-task-board.md`，设计 `docs/task-designs/VCO-05-design.md`。

**当前结论：本次授权首例验收通过，VCO-05完成。** 新版片交付后用户回复“没问题，继续吧”，按前序完整20秒与四项动态观察询问的上下文，记录该样片human_video接受。只适用于本次确切案例和资源范围；跨题材、更长时长、多窗续写未验证，未启用生产模式。

**请使用兼容播放版：[review-playback.mp4](D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/review-playback.mp4)**，标准H.264 High/yuv420p、320帧/20秒、2,863,820字节，SHA256 `ae175cc0e6819039a524f23c7642e0a667ada071ea61486adbf717155eb71ca6`。它是CRF16压缩副本，明确不是无损文件。

原无损审计片：[review.mp4](D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/review.mp4)，20秒，61,665,726字节，SHA256 `8f72cf4840d79b2180048a057cad2512699329f9a80b09a5f3ab02ed29aa67f9`。该文件使用High 4:4:4 Predictive/gbrp，用户报告播放器无法打开；文件SHA及完整解码复核均正常，不能将FFmpeg可解码等同于系统播放器可用。原件保留作逐帧RGB证据。采样图：[samples.png](D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/samples.png)。

## 证据入口

- 最终证据根：`D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321`。
- 原任务ID：`c76c898d-303f-460e-912e-e54e384efbda`；实际POST受理时间2026-10-27 03:58:02 UTC（北京时间11:58:02）。
- `case.json`、`graph.json`、`prepared.json`、`prompt-contract.json`：冻结输入/模型/工作流/软件和文本审查。
- `intent.json`、`acceptance.json`、`http/`：原请求身份及原始HTTP；不追加请求。
- `service.json`、`service.stdout`、`service.stderr`、`resources/`：自有服务、完整日志及连续资源采样。
- `source-inventory.json`：3011个原run文件的bytes/SHA/mtime；1107项模型、工具及源码依赖另绑定在case，结束后全部复核不变，result.json的source_unchanged=true。
- `result.json`：真实技术结果与自有服务收尾；`evidence-summary.json`：单次POST、完整资源采样及媒体汇总；`sample-screening.json`：实际静帧查看记录，不是视频观察。
- **最新验收** `user-observation.json`、`final-assessment.json`：确切新版SHA、用户原话、验收上下文、原片/无损/映射血缘及限定范围。旧result/media/playback内的unverified是当时历史快照，原字节保留，后续结论以新receipt为准。
- 软件验证与已保留失败/中断记录见 `docs/task-designs/VCO-05-verification.md`，独立审查处置见 `docs/task-designs/VCO-05-review.md`，只读状态入口见 `docs/task-designs/VCO-05-operations.md`。

## 分项结论

| 项目 | 当前事实 |
|---|---|
| 软件 | 新增工具及相关单元/实际CPU媒体检查122 passed；聚焦旧接口兼容3 passed。旧生成文件完整扩展运行中断，未登记全文件或全库通过。 |
| 固定请求 | Wan2.2双专家，768×432、16fps、40步、CFG3.5、Euler/simple、高噪声15步切换；原首片seed264244520399004，低噪声seed0；请求321，计划保留[0,320)。 |
| 输入 | 只读原run `20261021-014723-4ebdc1fecab2` 的scene3已准入原图与首片适配PNG。 |
| 真实技术结果 | passed：原始H.264 321帧/20.0625秒；321张原生解码PNG保留，审阅片320帧/20秒，实际逐帧PTS=i/16、[0,320)映射和全部RGB逐帧framemd5相等。 |
| 资源 | 1874/1874采样verified；峰值总GPU占用21657MiB（含桌面）、最小空闲2379MiB；自有服务RSS峰值16056832000字节，系统内存占用峰值33298898944字节，接近33346146304字节物理总量。未发现OOM、执行错误或超时。 |
| 采样外观 | agent_image实际查看0/16/64/128/192/256/304/319帧缩略图，未见明显重大变色或主体突变；另显示丢弃帧320，仅作诊断。不据此接受连续动态。 |
| 完整动态观察 | human_video passed：新版交付后用户“没问题，继续吧”，结合原全片四项询问登记；不声称独立采集了播放器进度、逐秒日志或观看时间。 |
| 生产准入 | 当前首例可作为VCO-07实测输入；production_mode_enabled=false，未启用whole_scene_v1，也未完成其生产接入验收。 |
| 跨题材 | 本轮未追加授权，不执行，不外推能力。 |

本次同时改变提示与生成长度，不能将任何改善归因于单一变量。原JIM-08多片连续链验收不因整段候选而自动完成。

## 时间与边界

Comfy原任务execution_start→execution_success为3798.752秒，服务日志显示01:03:18，未超过冻结的7200秒期限。runner记录3893.203秒包括服务准备和媒体处理，其finished_at早于最后源码/源run身份复核；不将两种耗时混为一项。自有服务成功产生输出后由Popen.terminate收尾，Windows退出1是该主动终止码；原模型任务history为success、CLI退出0，不登记为模型失败。

实际仅验证并接受当前模型/软件/硬件、该768×432/16fps/20秒鸟类飞行案例，且内存余量很小。不同主体/材质、另一种镜头运动和更长时长均未验证。未启用whole_scene_v1，未生成修订/超分/正式成片或发布，未改原run。

## 用户反馈与范围限制

已向用户提供具体审阅片并询问：完整播放20秒后，主体颜色、光照、构图和动作是否均正常。用户先报告“视频损坏无法打开”，仅记为播放兼容问题。修复并交付新版后，用户回复“没问题，继续吧”；按这次样片验收的完整上下文接受其肯定反馈，绑定兼容副本SHA及playback-review.json原无损片/原始输出血缘。原话原样保存，不增加用户未提供的逐项具体评语、观察时间、观看次数或独立播放器事件。

本轮授权首例范围已完成。跨题材/另一运镜/更长时长保留为尚未验证、未授权追加的范围，不能据单例外推。原JIM-08独立续接、生产集成与发布均保留各自验收条件。

## 验收对应

1. 软件边界：预算/身份漂移/一次提交与恢复/失败停止/源run不写回均有定向检查及真实原run复核；34项播放修复回归与此前122项/3项结果、旧扩展回归中断和全库后移均独立记账。
2. 真实执行：冻结资源/模型/输入/自有服务身份，仅一次POST；原任务3798.752秒成功，无OOM/超时/规格降低或重试。
3. 证据齐全：原始MP4、全部321原生解码PNG、320帧映射、SHA、审阅副本、原始日志/HTTP和1874资源样本均可定位。
4. 动态结论：技术与资源已有闭包，后续用户肯定反馈绑定新版SHA。首例证据可供VCO-07设计消费，但未自动启用生产。
5. 能力范围：只接受本案例；未授权跨题材明确留作未验证范围，不替代原独立续接验收。

## 播放修复证据

原片和RGB无损片SHA均未变且完整解码退出0；根因线索为RGB无损编码的播放器兼容性。新播放版保持全部320帧、精确PTS=i/16、20秒、尺寸和原有bt709矩阵/原色、sRGB传递、tv range。原YUV帧与新副本配对PSNR平均50.721dB，属于明确记账的编码损失，不用于动态质量接受。回归34 passed；证据playback-review.json、playback-quality.json、playback-probes及media-commands，实际未重新生成模型视频。

本轮修复更新了当前whole_scene_media.py，旧推理case保存的源码身份是历史执行版本，并保留在software归档；没有将历史case的SHA改签为新源码。新副本单独绑定本轮后处理代码身份。
