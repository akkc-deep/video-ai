# LVA-03 结果：阶段计量与准备重叠候选

**已完成。候选不默认采用：真实对照未证明可重复的墙钟收益，生产保持原串行、原质量和 strict 校验。**

实现、定向验证、32次真实GPU样本和人工质量/连续性验收已完成；8个测量阶段及1个提交前失败阶段的owned服务全部退出。原生产未恢复，无付费调用。

结构化证据：[LVA-03-results.json](LVA-03-results.json)；执行决策：[LVA-03-plan.md](LVA-03-plan.md)；服务/审核状态：[GPU状态](LVA-03-gpu-run-state.json)。

## 实际交付

- `scene_stage_preparation.py`：默认关闭的独立实验上下文、不可变job/result、一个空Context worker/一个槽、source64MiB+graph32MiB逻辑预算、每块1MiB读取/完整SHA、取消与最多2秒join；late结果不能发布或写证据。
- `production_scene_clips.py`：已有handle重新核验进程/PID创建身份及启动绑定；协调线程进行来源/参数/workflow核验、图谱deepcopy及所有原媒体/事务写入；阶段统计仅写diagnostic日志，不进入请求身份。现有一次启动/关闭复用没有重复实现或认领新收益。
- 离线与GPU对照脚本、针对性测试和只读结果整理脚本。LVA-02候选仍关闭；不改采样、模型/LoRA、旧schema/unknown/accepted或即梦路径。

## 真实GPU对照

RTX5090D v2，原40步/CFG3.5、768×432/16fps、原seed与完整预算。低/高/父片各生成并贡献93帧；子片生成81、按原规则贡献77。每类每侧冷进程1次、同进程热3次，单GPU串行。冷只指新进程，不保证OS缓存冷。

| 固定样本 | baseline冷秒 | candidate冷秒 | baseline热P50秒 | candidate热P50秒 | 热观察差 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 低运动 | 488.347 | 491.447 | 473.314 | 485.536 | +2.582% |
| 高运动 | 479.494 | 479.544 | 476.574 | 482.310 | +1.204% |
| 父片 | 482.131 | 476.243 | 470.293 | 470.362 | +0.015% |
| 子片 | 379.668 | 379.888 | 379.589 | 379.600 | +0.003% |

三类独立候选各3次预读均消费，无失败/丢弃；读取为毫秒级CPU I/O，实际逻辑峰值不足1MiB。子片没有独立预取候选，两侧worker任务均0，保持同链串行。所有对应trial的模型方法次数、retained视频和末帧分别匹配。**未测得物理装载次数**：loader节点/模型方法不能代替物理权重搬运计数。

整阶段设备利用率<=5%的相邻样本观察跨度（baseline/candidate秒）：低32.749/30.687、高20.459/24.528、父24.555/12.265、子24.555/14.343。最大相邻间隔6秒，包含启动/桌面/技术处理，非精确CUDA空闲。部分跨度较低但热墙钟基本相同，尤其没有worker的子片也出现类似变化，不能归因于预读。OS缓存、GPU频率和系统负载未控制；3秒轮询也有观察延迟。

各阶段模型/节点方法为CPU墙钟，存在嵌套；设备采样不独占进程。原始JSON保留分阶段时间、原ID、source/generated SHA、实际每帧PTS、预算、方法和设备证据。不得把局部节省相加或外推整片吞吐；整片仍属LVA-06。

## 身份、恢复与人工验收

- 32份实际推理全部技术完成并获接受：用户接受低运动基线、高运动及同字节候选、回复“没问题”接受新父片组和低运动候选绑定，最后明确接受子片与连续性及同字节候选绑定。所有接受receipt均在实际媒体存在并核对身份后写入，未预造接受记录。
- 子片使用新父片真实末帧SHA `606b69269c64164aedec402c3f9e91423cab4fa7e1ee6fc09b60e219bc000c92`。每trial保存parent-binding和人工接受SHA；父片服务关闭/人工接受后才启动新的子片服务。
- 一份无损stream-copy[连续性预览](E:/VideoAI/scratch/benchmarks/LVA-03-gpu-baseline-child-20261116-02/review/parent-child-native.mp4)包含93+77=170帧、10.625秒；单次probe验证PTS，用户已完整观看并接受。该两项QA命令单独记录，不混入测量阶段media计数。
- 七个阶段直接记录normal各4POST，共28POST；最初baseline-low的4份POST原回执单列，不能称直接计数。32个原prompt ID分别保留。所有8阶段完成恢复的POST/GET/媒体调用均0；未重新推理或重生成完成媒体。
- 全部实际帧数/PTS/宽高/证据SHA从既有probe/frames stdout整理，没有为补报告重跑probe/decode。结果生成时的 `summary.json` 质量快照不覆盖；最终JSON依据实际接受receipt重建当前状态。

## 验证与修正

- 88项定向单元/事务/发送边界/GPU编排/节点观测测试通过（6.85秒，`E:/VideoAI/scratch/LVA-03-unit-final.txt`）。
- 2项修正后的真实FFmpeg阶段正常/恢复测试通过（98.66秒）；组合运行中此前5项generated receipt/篡改恢复通过。原组合6通过/1失败发现Windows fstat ctime与path stat ctime含义不同；已失败优先修正，不重复解码原测试只为刷新计数。
- 读前后同一句柄完整metadata比较；跨API仅比较共同dev/inode/size/mtime，完整SHA始终保留。新增增长来源测试证明14字节文件不能因BufferedReader读入8192字节，最终以buffering=0限制返回字节<=声明+1。
- 独立审查四项GPU脚本问题已修正：stop-request写失败仍退出、诊断错误保留原异常、消费payload在下一submit前释放、补idle/direct/recovery证据。回归均先失败后修复，不重复派发审查。
- 子片首次准备因新driver与既有helper目录约定不符，启动15.7秒后安全关闭，未创建intent/POST、子片推理0次。该setup失败1次保留，不称GPU重做。改为在accepted parent root封存child定义，fresh root由原helper准入；完成恢复也走parent-bound helper。两个新增回归先失败后修正，真实文件测试验证原父片尾帧协议。
- 不宣称全库通过。前序已披露legacy模型、无效run、continuity路径及交付reclaim缺陷未在本项扩修；详见LVA-02结果。

## 离线候选与采用结论

真实FFmpeg/内存Comfy、禁止GPU/网络，四次交替顺序对照；完整profiler另采样。修正报告 `E:/VideoAI/scratch/benchmarks/LVA-03-preparation-corrected-results.json`：

| 模式 | baseline均值秒 | candidate均值秒 | 实际工作 |
| --- | ---: | ---: | --- |
| 正常 | 18.965071 | 18.774368 | 每侧3POST/12producer；candidate每次消费2个准备结果 |
| 完成恢复 | 3.791601 | 3.720468 | 两侧均0POST/0producer，没有worker |

逻辑峰值20,288字节，读取约0.0006~0.00095秒。正常观察差约-1.01%，但没有worker的恢复也有-1.88%差异，不作因果加速解释。原报告 `LVA-03-preparation-results.json` 中候选因ctime误判每次丢弃2个结果，作为回退诊断保留，不能代替成功预读的证据。

**否决默认采用。** 预读保持实验默认关闭，原串行/strict继续；已有服务复用不重做，未启用新显存驻留或模型缓存策略。

## 证据边界与剩余限制

- 当前模型size/mtime匹配LVA-01，沿用其一次完整SHA；未在生成中反复hash巨型模型。小软件文件另有SHA。首个baseline-low启动前未另捕获已加载脚本SHA，normal直接计数缺失如实为空。
- 首24次GPU控制器已导入此前buffered预读实现，最终源码之后改为无缓冲以保证增长来源的严格读取上限。固定输入/图谱/请求/媒体字节相同，但这些微耗时不冒称最终源码的精确耗时。最终资源边界由具名回归验证；环境 `final-read-mode-amendment.json` 记录差异，不为这一资源改动重做GPU。子片使用当前driver且没有预读job。
- GPU harness预读已适配固定图，生产原选图/协调线程成本另由离线夹具测量。96MiB是source+graph逻辑payload预算，不是RSS实测上限；正常请求图谱和小分配开销另计。
- 源码和脚本身份见 `E:/VideoAI/scratch/benchmarks/LVA-03-environment-20261115-01/environment.json`、read-mode及child-driver amendment。各phase的node-metrics、direct-counts、service-phase、idle-evidence、technical-complete和人工接受记录原样保留。
- 本项不修改原生产、模型、即梦、原40步质量路径、既有pending/unknown/accepted；不作新1080P或整片吞吐结论。

完成证据时间（UTC）：2026-11-15T17:12:13.867413+00:00。
