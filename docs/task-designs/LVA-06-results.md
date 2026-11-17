# LVA-06 端到端复测最终结果

状态：**COMPLETED**；完成时间 `2026-11-16T19:23:23.328032+00:00`。

按授权完成一份 quality／strict／serial／libx264 矩阵：**16 次原生请求、1,424 次逐帧超分、12 份1080P成片**。三类各cold1/warm3，全部技术通过并获得真实新媒体质量决定；7个owned服务均exit0/finalized，原进程身份已退出。

最终配置与baseline行为相同，共用这一份实测，没有为对照表重复生成。前项候选没有形成可默认推广的新组合，保持原质量路径；不声称整片提速或因果加速倍数。

## 实际批次端到端

| 类别 | 批次墙钟 s | 人工区间并集 s | 非人工包络 s | 接受的试验视频秒 | 每可用视频秒成本 s |
|---|---:|---:|---:|---:|---:|
| 低运动 | 9407.449 | 6911.003 | 2496.446 | 23.25 | 107.374 |
| 高运动 | 3818.370 | 1343.260 | 2475.110 | 23.25 | 106.456 |
| 父子连续链 | 6498.514 | 2027.951 | 4470.562 | 42.50 | 105.190 |

全固定队列共89.00试验视频秒、非人工包络9442.118s，混合素材成本106.091s/接受的试验视频秒。这是12次预定重复样本、3种唯一成片内容；不是89秒独立故事，也不是107场景整片预测。

T0为本次选定素材交接后、复制/准备/启动前；Tend为最后一份最终媒体技术完成。人工审核取区间并集并在T0/Tend内裁剪；最终质量等待另记。各trial完成包络互相重叠、包含批内排队，不相加，不当独立热片延迟。历史LVA-01计时/环境/调度不同，单独保留。

## 原生／超分局部冷与热

| 类别 | 阶段 | 温度 | n | P50 s | P95 s |
|---|---|---|---:|---:|---:|
| 父子连续链 | native_child | process_cold | 1 | 380.536 | 380.536 |
| 父子连续链 | native_child | warm_process | 3 | 377.478 | 377.492 |
| 父子连续链 | native_parent | process_cold | 1 | 480.872 | 480.872 |
| 父子连续链 | native_parent | warm_process | 3 | 477.964 | 477.981 |
| 父子连续链 | upscale_chain | process_cold | 1 | 165.210 | 165.210 |
| 父子连续链 | upscale_chain | warm_process | 3 | 167.217 | 167.249 |
| 高运动 | native_high | process_cold | 1 | 472.653 | 472.653 |
| 高运动 | native_high | warm_process | 3 | 469.471 | 469.606 |
| 高运动 | upscale_high | process_cold | 1 | 93.027 | 93.027 |
| 高运动 | upscale_high | warm_process | 3 | 92.506 | 92.953 |
| 低运动 | native_low | process_cold | 1 | 472.225 | 472.225 |
| 低运动 | native_low | warm_process | 3 | 469.185 | 469.473 |
| 低运动 | upscale_low | process_cold | 1 | 91.343 | 91.343 |
| 低运动 | upscale_low | warm_process | 3 | 92.386 | 93.158 |

cold仅指新Comfy进程，不清空OS缓存；热n=3只作线性插值描述，不作统计置信。child81生成/77贡献，与parent93帧的工作量不同；child来自新的服务冷样本，不能称作parent热样本。native局部含原请求追踪及技术处理；upscale局部为各trial原提交/追踪，均不等于完整独立热片延迟。

## 质量、完整性与恢复

- 低/高各4份93帧，父子各4份170帧（93+77），均1920×1080/16fps；原旁白、字幕、字体和x264 medium/CRF18保留。原生总1440生成帧、1424保留贡献帧，不减帧、不重复贡献。
- 16个原生＋1424个逐帧任务的1440个原ID均唯一，intent／accepted／POST response／原history／profile-binding一致，0已知失败、0重做；cold/warm计划重复不算重做。
- 所有新父片真实接受后，child才绑定对应新父片真实末帧和接受SHA。4份170帧原生连续预览为无重编码拼接，完整帧数/PTS通过。
- 7次真实阶段性group决定绑定当前媒体；3次最终group决定接受12份实际成片。每组4成片逐字节相同，明确展示单份并请求接受整组；没有伪称12次独立观看。最后连续组用户回复“视频没问题”。
- 全帧PNG/RGB/顺序、每帧PTS和最终音视频证明保留；每最终成片仅一次完整FFmpeg AV/RGB验证，不为填统计重解码。
- 三个实际完成批次从原root恢复均0HTTP／0producer／0decode／0模型启动。必要真实性SHA读取仍执行，stage操作计数的0SHA不代表0物理I/O。实际未知扩散中间态未发生，也不声称可恢复；原ID-only/拒绝重POST/漂移由隔离测试覆盖。

## 资源与计数口径

- 累计stage操作：1440POST、9583GET、64producer、96FFmpeg decode类命令、108FFprobe命令。计数跟随已有调用，不新增媒体读取。首次准入和完成恢复验真在stage操作外，未伪称为0读取。
- 每owned阶段的节点/模型方法CPU墙钟、GPU/VRAM样本、低利用跨度、进程RSS、阶段末逻辑文件长度和原始metrics身份均在JSON。嵌套方法时长不相加，设备样本含桌面与启动，不当独占峰值。物理装载、kernel/独占idle、临时/文件系统真实峰值未测，保持null；没有删raw/history来报存储收益。
- 共用collector的raw backend字符串原先固定写超分；本报告依据冻结workflow及实际node/model事件标明native Wan或RealESRGAN，保留legacy字段和原始receipt不改，避免把该字符串当native后端证据。

## 归因及采用

| 类别 | 结论与来源 |
|---|---|
| 历史已采用 | 能力缓存、批量提帧/复制和一次AV解码是既有输入，见[历史性能结果](video-generation-performance-results.md)，不认领本轮新增收益 |
| LVA-02 | guard候选没有真实墙钟收益，默认strict；见[LVA-02](LVA-02-results.md) |
| LVA-03 | 准备重叠无稳定通用收益，默认关闭；既有owned阶段缓存不是新增优化；见[LVA-03](LVA-03-results.md) |
| LVA-04 | 当前native严格adapter不兼容官方recipe混合diff/diff_b/diff_m，0fast视频；Sage/cache/compile未支持或未验证，不启用；见[LVA-04](LVA-04-results.md) |
| LVA-05 | I/O方向混合，父片writeback局部1.56%观察不外推；保持serial。NVENC虽局部更快但93/93RGB不同而拒绝；组合未跑/未验证；见[LVA-05](LVA-05-results.md) |
| LVA-06 | 最终仍quality40/CFG3.5、strict、serial、libx264；一份真实矩阵闭环，新增稳定默认加速结论未建立 |

## 验证、限制与产物

- 实施定向77 passed／26.24s，含真实小CPU媒体、fake HTTP、漂移/未知原ID、父子门槛及CPU进程Job关闭。源/原workflow身份在收尾审计仍与授权清单一致，代码未改，因此不为收尾重复生成CPU/GPU样本。已知5项旧路径夹具失败保留前项披露，不声称全库通过。
- 本次新鲜只读[证据审计](LVA-06-evidence-audit.json)核对1440原ID、12完整成片、7质量group决定、7服务退出、三实际完成恢复与17源码/workflow身份；0新增媒体命令。
- 输入是原固定已适配素材的本次交接/复制；原选图/下载、清单身份研究及交接前准入单列，不能冒充本轮生成收益。原PCM历史stamp无SHA，当前完整准入不倒造历史SHA。
- 原生产继续暂停；0新模型下载、0NVENC/fast、0付费API、0默认推广。工作保留在现有v1工作区，已有前项未提交依赖及无关改动保留，未自动commit/push。

机器可读：[完整GPU报告](LVA-06-gpu-results.json) · [任务结果](LVA-06-results.json) · [原始只读summary](LVA-06-measured-summary.json) · [授权清单](LVA-06-experiment-manifest.json) · [实际授权](LVA-06-authorization.json) · [代码审查](LVA-06-review.md)。

真实完成恢复：[low](LVA-06-low-completion-state.json) · [high](LVA-06-high-completion-state.json) · [chain](LVA-06-chain-completion-state.json)。

阶段快照仅保留为历史；当前最终状态与结论以本报告、完成记录及任务板为准。
