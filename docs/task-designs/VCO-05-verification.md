# VCO-05 验证账本

日期：2026-10-27。当前记录软件检查；真实首例结果完成后追加。全部Python先dot-source `scripts/bootstrap.ps1` 并 `Initialize-VideoAiEnvironment`；全库按既定安排留到VCO-08。

## 软件

- 最初缺失实现：19用例中1 failed/18 errors，退出1，确认为缺失实验接口；日志 `D:/VideoSi/cache/video-ai/logs/vco05-red-9a85441c5afa4386a3d0b621a1c1ddae.log.pytest.txt`。
- 首次媒体RED：5 failed，退出1，缺失媒体模块；日志 `vco05-media-red-4a5f08a5857840d4a6ae9558cf7de07f.log.pytest.txt`（下述短日志名均位于同一logs目录）。
- HTTP证据适配首次GREEN前发现缺少HttpClient要求的event方法；原4失败保留，补齐后19 passed/退出0：`vco05-unit-green-199ff4a60f2f4b35a794c21acfc240a4.log.pytest.txt`。
- 媒体首轮发现环境没有Pillow，改用项目已有continuity可选依赖NumPy/OpenCV，不安装新包。保留原1失败/4通过日志 `vco05-media-green-8abba801a3b04860a2c407d483a1e13a.log.pytest.txt`。
- 独立审查四项复现：4 failed/24 passed，退出1：`vco05-review-red-a430095ed1e54f128bd313f2bbda222b.log.pytest.txt`；全部修复并加入桌面GPU上下文用例。
- 最终软件定向命令：`& $VideoAiPython -B -m pytest tests/unit/test_whole_scene_experiment.py tests/integration/test_whole_scene_media.py tests/unit/test_scene_video_prompts.py tests/unit/test_scene_clip_continuation.py -q --basetemp "D:/VideoSi/cache/video-ai/temp/vco05-final-$VideoAiCommandId" -o cache_dir=D:/VideoSi/cache/video-ai/pytest`。**120 passed in 7.44s，退出0**；日志 `vco05-final-targeted-191c495487dd4b7b8a38e1c80fb1b815.log.pytest.txt`。
- 包含旧生成集成文件的首次合跑：114 passed/25 failed，退出1：`vco05-targeted-5439d854e0ec4abdb0ae3e3872768000.log.pytest.txt`。全部失败同源于旧测试首次导入别名污染，见review文档。测试修正后的原顺序两用例回归 **2 passed/退出0**：`vco05-order-regression-41a6fe6e82a54faca08ddb256b4c9d41.log.pytest.txt`；不掩盖首次失败。
- 另一次完整旧生成文件兼容运行 `vco05-compat-clips-97bce0ffe478462b888fbe4216a5b921.log.pytest.txt` 在历史反复篡改审计阶段耗时过长，已Ctrl-C终止，外壳退出1、没有最终pytest汇总；**该部分运行不登记通过**。本任务没有修改旧生产源码，测试范围收窄为本次新增实验工具和旧测试隔离相关入口。之后明确重跑结果schema、继承绑定测试、未准入图零服务/零POST三项，**3 passed/退出0**：`vco05-focused-compat-d5be464915fb41b2a484cb7f5569a44f.log.pytest.txt`。全库及旧文件完整执行仍未在本任务完成，不据此宣称旧文件全通过。

## 冻结案例

- 最终软件：追加服务退出立即停止与全局GPU锁复现2 failed/退出1，修复后最终 **122 passed in 8.12s/退出0**，日志 `vco05-software-final-63c6db8a196f45319ef094a890f81e50.log.pytest.txt`；先前120项结果保留为历史。
- 最终证据根：`D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321`。先前 `vco05-20261027-first-trial` 是发送前源码完善的历史冻结，已有superseded.json，POST=0；不是第二次GPU尝试。
- 提示契约：`D:/VideoSi/cache/video-ai/logs/vco05-inputs-20261027/prompt-contract.json`。完整七clip、三scene绑定，实际只执行scene3；文本审查绑定内容SHA，实际查看首片适配PNG，飞行已开始，不再重演起飞/行走/展翼开场。
- 已调用prepare成功/退出0：日志 `vco05-prepare-6f440094c4c54a74a801a7ffc0310e6a.log.prepare.txt`。冻结321/320/[0,320)、原图/适配PNG、原首片seed与固定模型/graph，未改生产预算。
- 最终重新冻结成功/退出0：`vco05-prepare-final-a6f8ccef9abe4d0f9fd1ad79c9a62cd5.log.prepare.txt`。保留完全相同案例输入与seed、模型；仅将完善后的runner源码纳入最终冻结。3011原run文件、1107项依赖。
- 只读资源预检成功：24455MiB总显存、20915MiB空闲、GPU利用率1%；物理内存33346146304字节、可用15646560256字节，页提交可用10210836480字节。最终根preflight含Windows桌面上下文身份及GPU/内存快照，未终止桌面进程。该快照不代表321帧可成功装载。
- 案例中的 `source-inventory.json` 保存源run全文件bytes/SHA/mtime；`case.json` 保存模型完整SHA、工具与Python/Comfy源码身份；`software` 保存实际源码副本，`prepared.json` 绑定case与独立input/prompt副本。

## 真实验收

唯一真实execute命令：`& $VideoAiPython -B scripts/experiments/vco05_whole_scene.py execute --root D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321`。CLI退出0，status=awaiting_video_observation、technical=passed、resources=recorded、source_unchanged=true。日志 `D:/VideoSi/cache/video-ai/logs/vco05-single-trial-a4c6fe36315b439e9e7d8235776576df.log.execute.txt`。

- 原任务 `c76c898d-303f-460e-912e-e54e384efbda`，3798.752秒，history success；一次POST，未重试、未降规格。1874/1874资源采样有效；峰值总GPU21657MiB、最小空闲2379MiB，系统内存峰值33298898944字节，接近物理总量，不能表述为余量充分。
- 原片1741348字节，SHA256 `4916b39184f19b083415a81ccf923eb5db10d415591014dae2389af3be98abe7`；321帧、768×432、16fps、20.0625秒。真实完整解码及所有PTS校验通过。
- 全部321张原生解码PNG与SHA已保存；mapping.json只保留[0,320)。无损RGB review.mp4为320帧/20秒、61665726字节，SHA256 `8f72cf4840d79b2180048a057cad2512699329f9a80b09a5f3ab02ed29aa67f9`；320帧实际RGB framemd5逐项相等，没有插帧/变速/补帧/调色。
- 逐帧码值亮度/色度/截断统计、采样图、实际颜色元数据和全部命令/原始probe齐全。Comfy声明及MP4标签为bt709 primaries/matrix、sRGB transfer、tv range，按原probe记录，不据此发明颜色一致性通过。
- 实际查看9格采样图，其中8帧属于保留段、源帧320为丢弃尾帧。暂未见明显重大变色或主体突变；仍未声称完整动态通过。记录sample-screening.json。
- 原run3011文件及1107依赖结束后bytes/SHA/mtime复核一致；自有服务已停止，未管理外部桌面进程。主动terminate后的Windows退出1与原模型history success分别报告。
- 汇总证据 `evidence-summary.json`；最终文档 `docs/task-handoffs/VCO-05-results.md`。缺少真实完整播放反馈，full_video_observation=unverified、production_eligible=false，跨题材未执行。任务尚未登记完成。

首轮收尾用 `git -c core.autocrlf=false diff --check` 改变了仓库的行尾解释，导致CRLF被误报为逐行尾随空白、退出2；没有据此重写历史文件。应恢复仓库原配置执行普通 `git diff --check` 并以其实际结果收尾。

最终已按仓库原配置执行普通 `git diff --check`，退出0。另调用缓存媒体审计重新核对原片/审阅片/映射及321张PNG身份，退出0；case/GPU锁均不存在、自有PID43340已结束。最终闭包 `D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/closeout-check.json`，命令日志 `vco05-closeout-e2ca3c1641a7472d90ded4e09efbc89c.log`。未收到完整播放反馈，已先写pause handoff，再将任务登记BLOCKED；这不否定软件、技术视频和资源已完成事实，也不将其改成视频通过。

## 2026-10-27 播放兼容修复

用户反馈“视频损坏无法打开”。重新核对原生成文件与无损review.mp4的原SHA均一致，FFmpeg严格完整解码均退出0。旧review为H.264 High 4:4:4 Predictive、gbrp，不能据FFmpeg可解码推断系统播放器兼容；原生成文件为High/yuv420p。没有将该反馈登记为内容失败或动态接受。

新增兼容副本创建与旧证据不覆盖回归，先RED 2 failed/退出1：`vco05-playback-red-5b46a7cfe12b4709a50c1ae9d57315bd.log.pytest.txt`。首轮修复33 passed/1 failed，发现已有probe名称冲突，改为独立UUID诊断文件而非覆盖。最终命令 `python -B -m pytest tests/integration/test_whole_scene_media.py tests/unit/test_whole_scene_experiment.py -q`，使用独立basetemp及既有bootstrap，**34 passed in 9.59s/退出0**；日志 `vco05-playback-green-fc112c5eb4e443868708d806a801b31a.log.pytest.txt`。断言High、yuv420p、320帧/20秒、faststart、原证据不覆盖、缓存漂移拒绝；未执行全库或新模型推理。

实际创建 `review-playback.mp4`，2863820字节，SHA256 `ae175cc0e6819039a524f23c7642e0a667ada071ea61486adbf717155eb71ca6`，High/yuv420p、16fps、320帧/20秒、全部PTS准确、严格完整解码退出0。该文件为CRF16有损播放副本，原片、RGB无损证据与case均保留。新副本的bt709矩阵/原色、sRGB传递、tv range与源一致；逐帧配对YUV PSNR平均50.721dB，记录playback-quality.json，不用于动态验收。

尝试Windows Media Player后台COM解码探测，旧/新版均停留transitioning（playState=9、位置/时长0，无错误），属于本工具后台播放未启动，**结果不确定，不能登记系统播放器播放成功或完整动态观察**；原始探测windows-playback-probe.json已保留。新版已提供用户，实际用户播放器可用性和全片动态反馈仍待确认。

后处理函数本轮更新的源码身份单独绑定在playback-review.json；原推理case/归档源码、result/media/原生帧映射不改签。后续反馈须绑定兼容副本新SHA及原片血缘。任务保持BLOCKED，不把修复文件当作用户已观看。

## 2026-10-27 用户接受与首例收尾

新版20秒兼容片交付后，用户回复“没问题，继续吧”。结合前序全片及主体颜色/光照/构图/动作验收询问，记录为该确切样片的human_video肯定反馈，原话与上下文均封存，不补造独立播放器进度、观看起止时间、次数或逐项具体评语。

新 `user-observation.json` 绑定新版SHA `ae175cc0e6819039a524f23c7642e0a667ada071ea61486adbf717155eb71ca6` 及原始输出/无损/映射；`final-assessment.json` 将已有技术passed、1874有效资源采样和用户接受组合为本次授权首例通过。旧result/media/playback中当时的unverified字节保留。只形成VCO-07可消费的首例实测输入，production_mode_enabled=false、跨题材/更长/多窗未验证。

恢复时复核上述媒体、映射与probe SHA均相符；命令日志 `vco05-feedback-verify-a95d434f8aa44e22890766f4154d2d21.log`，用户接受落盘日志 `vco05-user-acceptance-441b7f224bcc4a75acb911c85d5bc9a2.log`。无代码修改、无新模型请求，不重复跑已通过的软件检查。

收尾闭包：`completion-check.json`复核用户receipt、技术结果、资源摘要及所有引用媒体/映射身份；命令 `vco05-completion-check-4b4fa4491341472abc4eb625cd06c5a0.log` 退出0、普通git diff --check退出0。随后真实执行IN_PROGRESS -> COMPLETED。再按Order选VCO-06并核对输入，发现已交付检测阈值不含安全修复幅度校准；未假造后继READY或next-task交接。当前任务完成不受后继材料缺口影响。
