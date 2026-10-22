# Pause Handoff

## Handoff Type

pause

## Task Link

- **Task board:** `D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md`
- **Task ID:** JIM-08
- **Transition:** IN_PROGRESS -> PAUSED
- **Design document:** `D:/code/py/video-ai/docs/task-designs/JIM-08-design.md`
- **Pause evidence:** 2026-10-21用户明确“现在还剩什么工作，交接给下一个任务吧”。供下一会话/实施者继续同一任务；JIM-08尚未完成，不创建JIM-09，不继续推理。

## Current State

**核心未解决项：长场景动态续接与外观稳定。没有正式成片或发布。** 本快照取代旧交接“14B未下载、未出图/收信、严格30秒”等过时状态。任务板是状态权威。

已具备：即梦4.0、Qwen3:14B、本地AK/SK/SMTP、北京桶`testvitest`、完整文案；真实官方基准/参考图片、TOS读取、QQ收信、三个选图及整组风格确认均已有证据，不再次索取。凭证文件为`D:/VideoSi/projects/video-ai/config/jimeng.credentials.local.json`，不输出值；CLI按既有机制同进程临时加载，不假定程序自动读取JSON。

原正式run：`D:/VideoSi/projects/video-ai/runs/20261021-014723-4ebdc1fecab2`。463帧/16fps=28.9375秒，48kHz PCM共1,387,200样本，三scene保留219/110/134帧，计划7片（3/2/2）。技术生成6/7，真实接受3/7：用户“三段都看完，正常”只接受三个93帧首片，human_video记录已消费；随后明确三个第二片均不连续，均未接受。scene1第三片34帧未生成。不能普通续作失败链补最后片；尚未超分、正式合成、最终观看/试听/字幕核对、发布或完成重放。

已选原图SHA256：

- scene1：`f94326fa819c7efdf6b1857d262d1fe0bd17b76f1d23803f30cd2b9b411e680e`
- scene2：`e6fd702191c50d58200c63dd5942c63f25aeca208b3df19c4bdea634a0b4492f`
- scene3：`d29e1f201a58691c97eb221ff1c5bb5d675c7a0442c436d7fff8b3bb8fb5e94f`

已定位限制：原父末原生PNG与续片输入SHA正确，但独立I2V没有继承速度、翼相、镜头状态，重复完整动作提示会重启动作。历史9帧APNG A/B未证明改善；latent locking C1高低采样边界残余噪声已定位，C2消除历史噪声后新增接缝仍失败。没有512 token截断证据。技术谱系正确不代表动态连续。

用户批准的唯一VACE14B scene3隔离试验技术完成后，用户明确“画面确实变了，有问题”，外观失败，停止追加。整场景一次生成方案只准备、未获执行批准，因长场景问题已限定为短场景候选，不替代原多片验收。

业界调研完成：SkyReels-V3、FramePack、LongLive/MemFlow是备选，非必须全部使用。用户“那就先验证第一个方案吧”授权的SkyReels-V3首窗已实测：官方BF16、8步、768×432、24fps，132真实新增帧=5.5秒，本窗含编码核验632.52秒。采样后半段暖金色树林/湖面逐渐转灰绿、羽毛阴影变冷，agent_image外观筛查failed，按约定停止第二窗。**未完整连续播放，动作连续性unverified，无human_video接受。** 结果只限此配置，不外推模型所有配置或任意长场景能力。

审阅副本：`D:/VideoSi/projects/video-ai/reviews/JIM-08-skyreels-v3-first-window.mp4`，205帧/24fps=8.541667秒，3.041667秒起新增；SHA256 `8a93779ffd1b1282c48853a4c2331da99041873376977f47ce6d6def98463c3f`。采样图为同目录`JIM-08-skyreels-v3-samples.png`。24fps显式历史时基适配仅为研究，正式原生16fps要求不变。不要求用户再次接受已筛查失败的样片。

18:41最终审计：全部10模型文件完整重SHA、17固定代码身份、原run3011文件字节/mtime及378生产基准身份一致，审阅副本字节一致。全部自有下载/推理已结束，无第二窗intent或新生产观察。`window_01.intent.json`已存在，不自动重跑。

旧交接原字节快照：`D:/VideoSi/cache/video-ai/logs/jim-08-prior-handoff-20261021-141e38e8bf42478d960866fa07f784ae.md`，SHA256 `bfef9985b1046c4f58c4b535fb4c00fa17e7bd87497e2cf1926f7acd9c1afc15`。

## Changed Files

本次暂停交接仅刷新本文件、任务板及verification暂停说明。所有既有源码/测试/文档修改保留，不reset/revert，不把前序变更算成本次新改动。

- `docs/task-handoffs/JIM-08-handoff.md`：最新快照、验证边界、剩余工作和只读恢复动作。
- `docs/task-handoffs/jimeng-scenes-task-board.md`：本交接写入后JIM-08从IN_PROGRESS转PAUSED，保留设计/交接路径及历史事实。
- `docs/task-designs/JIM-08-verification.md`：五项验收、真实服务/观察/失败/回归的既有记录；顶部补暂停说明。
- `docs/task-designs/JIM-08-continuity-diagnosis.md`：原续片根因、A/B、C1/C2证据及限制。
- `docs/task-designs/JIM-08-continuity-repair-proposal.md`：此前批准的唯一VACE设计；结果见verification，不授权追加。
- `docs/task-designs/JIM-08-whole-scene-proposal.md`：未批准的整段候选及长场景边界。
- `docs/task-designs/JIM-08-industry-continuity-research.md`：官方实现、资源/时基/输入限制与备选方案。
- `docs/task-designs/JIM-08-skyreels-v3-validation.md`：加载适配、实际首窗外观失败与停止证据。
- `README.md`、`config/README.md`、`config/jimeng.example.json`、`docs/jimeng-candidates.md`：较早已更新的流程与合法示例，后续仍需与最终实际流程核对。
- 既有生产/测试修改涵盖planner模型冻结和旧恢复、scene-local transport、参考prompt紧凑表示及准入恢复。完整工作区含JIM-07等前序未提交文件，以git状态和378基准清单为准，不清理或覆盖。
- `D:/VideoSi/cache/video-ai/logs/jim-08-skyreels-v3-validation-20261021/`：隔离helper/依赖、RED/GREEN、加载错误栈及推理/筛查证据；未改生产Comfy包或workflow。不要自动执行helper。

## Verification

以下均为已有证据转录；本次交接没有重跑pytest、模型或媒体生成，不登记为新一轮通过。

已有最终裸全库命令（此前先bootstrap/Initialize，使用D盘Python，串行）：

```powershell
& $VideoAiPython -B -m pytest -v --tb=short --durations=15 --basetemp D:/VideoSi/cache/video-ai/temp/jim-08-full-a1596fa456d04178b7cbbed7197dd9cc -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

2026-10-21 04:21:27–09:55:56 +08，**3651 passed in20068.38s（5:34:28），pytest退出0**。日志前缀`D:/VideoSi/cache/video-ai/logs/jim-08-grounding-full-regression-a1596fa456d04178b7cbbed7197dd9cc`，后缀`-before.json`、`-after.json`、`-pytest.txt`、`-result.json`；378项生产/测试/workflow/配置/使用说明身份前后一致。

原PowerShell外壳OrderedDictionary分组误报重复导致外壳退出1，原错误保留。独立审计`D:/VideoSi/cache/video-ai/logs/jim-08-root-final-full-audit-3605d610b6474dfb8cbfb8cbab6c9730-audit.json`确认3651唯一通过节点、零非通过和当前身份一致；不混淆pytest与外壳退出码。

SkyReels既有证据根：`D:/VideoSi/cache/video-ai/logs/jim-08-skyreels-v3-validation-20261021/`：

- `final-audit.json`：18:41重核10模型/17代码/3011原run/378基准及副本身份，不是新全库或生产接受。
- `window_01.technical.json`、`window_01-static-audit.json`：真实首窗、lossless RGB/PTS核验。
- `window_01.visual-screening.json`：agent_image外观failed，motion unverified，human_video=false，second_window=false。
- `disk-backing-red.json`、`disk-backing-green.json`及只读映射探针：小型真实GPU非零输出与原生对照误差0、重复相等、CPU指针恢复，只证明传输正确，不证明视频质量。
- VACE原话拒绝记录：`D:/VideoSi/cache/video-ai/logs/jim-08-vace-scene3-user-rejection-20261021.json`。

隔离模型试验未改生产源码/workflow，最近全库字节保持，未另跑裸全库。完整视频动态接受、超分合成、最终观察、发布和发布后重放尚未完成。

## Remaining Work

1. 解决三场景续片连续性与外观漂移。先消费诊断、调研及失败试验，形成具体可审阅的下一方案/验证条件；目前未批准重跑VACE/SkyReels、运行FramePack/LongLive、云视频或整场景生成，不因交接自动启动。
2. 下一方案须明确真实运动历史、固定主体/环境及跨窗口状态保持、原生16fps和完整实际时长兼容性；不把独立I2V改称滑窗当作修复。需改架构/验收时先形成具体选择，不静默放宽。
3. 若需生产修改，现有模块有意义的RED/GREEN、审查、新裸全库及身份核验；显式revision保护原run/选图/文案，受影响视频和下游观察重新失效。原首片接受不适用于替换片或未来片。
4. 完成同一主体三个scene及至少一条两片以上真实连续链的完整动态观察；6/7技术完成、3/7接受不足以完成，不直接补失败架构的scene1最后片。
5. 源片全部接受后做1920×1080超分、完整旁白/字幕/时间轴合成、整片观看/试听/字幕核对；最终接受后显式publish并保存收据，两次普通完成续作及一次重复publish验证无新增提交/编码/邮件，核对使用说明及五项验收证据。

## Resume Task

恢复同一JIM-08：完成真实服务、三场景/连续长场景和正式成片验收及使用说明。当前PAUSED，未完成，不建立假后继。用户明确继续后，先全文读关联设计与本交接，再在任务板记录`PAUSED -> IN_PROGRESS`和恢复证据；恢复不扩大试验授权。

## Start Here

阅读顺序：

1. `D:/code/py/video-ai/docs/task-handoffs/jimeng-scenes-task-board.md`中JIM-08行和最新详情。
2. `D:/code/py/video-ai/docs/task-designs/JIM-08-design.md`全文及本交接；设计中的初始输入缺项/30秒目标以记录的后续用户输入为准。
3. `D:/code/py/video-ai/docs/task-designs/JIM-08-verification.md`最新进展及验收矩阵。
4. `D:/code/py/video-ai/docs/task-designs/JIM-08-continuity-diagnosis.md`及`D:/code/py/video-ai/docs/task-designs/JIM-08-industry-continuity-research.md`。
5. `D:/code/py/video-ai/docs/task-designs/JIM-08-skyreels-v3-validation.md`及证据根`final-audit.json`、`window_01.visual-screening.json`；必要时再读未批准的whole-scene方案和原run。

**第一动作：只读核对首窗失败、原run连续性状态和方案限制，整理具体下一方案/待选择点；不运行helper、不重交intent、不普通CLI推进失败链。** 根据用户选择继续对应范围，不重复索要凭证/桶/4.0确认，不要求接受已失败样片。

若以后获准复用模型，保留这些细节以免重下载/重踩加载问题（本交接不授权执行）：

- SkyReels权重`D:/VideoSi/models/skyreels-v3/SkyReels-V3-V2V-14B/`，10文件40,468,106,151字节；HF revision `68def6119d5731ab5f11faeda18a4a6bf65ff52e`，源代码commit `28c771e8456341be6a213e3d1133ed1fd19bf75d`，DiT SHA256 `b139ceb9efa7b9fdc1de66659331999bb7991acf26475a1d1c36f108c99b2d16`。不含shot_transformer。
- 本机RTX5090Dv2 24GB/32GB RAM。默认FP32初始化约57.154GB不适用；隔离meta/mmap/BF16按块传输保留权重值。safetensors.get_tensor在Windows access violation，已用显式mmap.ACCESS_READ及CPU原存储恢复解决加载，探针和首窗证据保留；不改Comfy包。
- portable Python3.13.14、torch2.13.0+cu130、transformers5.15.1、safetensors0.8.0、av18.1.0；独立python-deps为diffusers0.34.0、accelerate1.8.1、ftfy6.3.1、wcwidth0.2.14；SDPA，无FlashAttention。
- 条件按父片mapping.json从generated.mp4取原生帧，SHA256 `e4aef0d3edc0787f3c89ff0038a25d6658ef515093e4ff75c8672d74c746c736`，尾帧逐像素匹配PNG；source.mp4重编码RGB不同，不能放宽为近似RGB。
- 研究历史真实PTS最近邻适配24Hz、73帧/末25条件，最大误差1/48秒，24次历史重复单独记账；非原生16fps。8步/CFG1/shift8/seed264244520399005，真实新增5.5秒，不裁剪或变速凑5秒。
- VACE官方fp16原权重`D:/VideoSi/models/comfyui/diffusion_models/wan2.1_vace_14B_fp16.safetensors`仍在，34,675,323,640字节，SHA256 `f202a5c59b8a91ada1862c46a038214f1f7f216c61ec8350d25f69b919da4307`，不重复下载。

## Blocker

None

## Risks

- 连续性仍未解决，可运行不等于外观/动作通过，短窗不证明长场景稳定。新方案未选择，不预设换模型成功。
- SkyReels24fps、FramePack30fps与正式16fps不同；没有候选已证明满足原生16fps任意长场景。云视频门槛/权限也未获生产准入，图片凭证不等于视频API权限。
- 用户已接受实际时长，不要求严格30秒。完整原文/PCM/字幕/时间轴保留，不变速、截短、全局帧数上限或循环冻结凑时长。
- 不覆盖原run、失败、模型身份和观察；未知提交只查询原ID，不重POST；未观察/拒绝版本不发布，不自动付费返工或追加试验。
- 工作区有大量前序未提交修改，Git元数据只读，不分支/提交/推送，不reset/revert。所有Python先bootstrap和Initialize，D盘Python加`-B`，Python/媒体/推理串行。
- 用户要求活跃执行每30分钟仅汇报进度，不贴明细日志；未创建外部定时器，暂停后不承诺后台继续。
