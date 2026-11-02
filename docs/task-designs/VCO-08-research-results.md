# VCO-08 LongCat 研究实录

状态：**IN_PROGRESS**。用户对已验证读锁修复和独立新案例继续问题明确回复“继续完成当前任务”，已登记BLOCKED -> READY -> IN_PROGRESS。读锁修复部署到独立案例003，前两次失败冻结案保持。用户移除时间和内存占用上限的授权持续有效。合同为`docs/task-designs/VCO-08-design.md`；当前交接保留上次失败恢复历史。真实多窗、正式16fps生产及最终全库尚未通过。

## 当前操作入口

**native15整链接受、native16直接推进（2026-11-02 10:32+08）：** 用户明确指出`M/trial-001/chain-003/viewing.mp4`“这个视频没有问题”，依完整观看问题上下文记录human_video接受，`chain-003/dynamic-review.json` SHA `d31def417863db56f4f9e1487820f364ba66ecd6994c8ae2f9de80033a7dda43`；`M/native15-research-assessment.json`绑定技术/完整动态/适用单例，不改原不可变result的初始unverified。用户另对原生worker768×432/16fps/320帧路线明确回复“按建议直接推进，无需逐步确认”，授权收据`M/native16-route-authorization.json`，不再等待同一批准。研究接受不等于新16fps视频或生产启用。

新Q=`D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification`；资格合同/账本为`VCO-08-native16-qualification-design.md`与`VCO-08-native16-qualification-plan.md`。新case SHA `44bdb18c5eba8084a936b198d458d5b33f83bcd26f5fb11e010c4823fd5d0139`，27源软件SHA `e21f5a7ed34736e85acff28af8785a05a8b4a5837fd90dc69bcba898f65d96d8`。原25源先核对后复制，9份新副本适配+contract/pipeline两个模块；11份官方working源不改，模型/文本仍同路径/SHA，0新增下载/编码/权重复制/采样。四窗93+80+80+67=320帧/20秒；16fps是采样前部署输出时钟，模型无fps条件输入。子类只覆写尺寸方法，真实官方i2v/vc到shape检查入口RED→GREEN，无CUDA。

CPU协议、worker新case/缺缓存拒绝、资源旧shape/clock/KV七种漂移拒绝均实际RED→GREEN；真实tiny媒体raw/viewing的16fps/PTS/无损逐像素检查通过。独立只读review无Critical/Important/Minor，实际27源freeze和worker --check退出0（日志vco08-native16-final-software-freeze-f0420344406f45dbae58d820b1088160）。Q/live-run.json记尚未GPU；等待当前余项CPU回归session33919退出后，按新shape五阶段实际资源、布局/最终准入及每窗单次顺序执行，不重下/重编码/重启旧窗口。只读状态证实实际pytest41072/launcher28172运行、CPU约1246秒，诊断marker已到whole_scene_recovery，磁盘52,389,019,648字节；marker不冒充已完成计数，全部4375尚无终态。首次metadata脚本误用缺psutil的解释器、随后识别launcher+child需取叶worker；真实tiny媒体首次缺嵌入式脚本目录sys.path，均在模型调用前失败并已修正，原始日志保留。

**软件精确续跑已开始（2026-11-02 10:09+08）：** 原失败节点单点RED为`awaiting_review != failed`，1 failed/95.31秒，日志test-92729b033f754c1a8ebf3f8ecccfdceb。仅修改`tests/integration/test_scene_color_repair_recovery.py`目标master.mp4的timeout故障注入：临时monkeypatch.context内令`processes.command_timeout`返回1e-9，再调用真实run_logged；encoder故障、真实日志/failed终态/原片不变/同UUID不重试断言保持。生产无时限代码未改。两fault参数、formal无时限进程等待、普通真实failure/timeout日志共5项GREEN，139.56秒，session98891退出0，日志test-70fb977d06c14ee491ec4839fba34ce2。

`M/verify_regression_resume_sources.py`实际证明519份src/tests/scripts字节未变，唯一变化为该测试块；在内存还原旧块后整文件SHA精确等于原collection记录，其他测试函数/参数未变。4375-node文件与原manifest完全一致且无pytest选项/嵌套argfile，SHA `6d2a340b343b5110faeafa6507a37529e6b71c10e766255691ef2a954b9ef8a4`。新收据regression-resume-source-proof.json/日志vco08-regression-resume-source-proof-2b721a2082c24828bc796ae9ccc393ac退出0。随后仅启动`./scripts/test_windows.ps1 -q @M/regression-remaining-nodeids.txt`，session33919/日志test-0732aaf100b04cd6beee44013b8e3994；只监测本次，不重复已完成前缀。全库尚未通过，完整链及正式16fps问题仍待答复。

**三窗技术完成、整段待动态接受（2026-11-02 10:02+08）：** 第三窗session29654/worker40556退出0，4632.156秒，无资源停止；result SHA `cc06527eed75c86c555519874231e950354628625fe2c00eb024b3950c2bf2e3`，sample已提交后解码/落盘成功。`M/verify_three_windows.py`实际核对三窗所有artifact完整SHA、递归父链/intent/sample-complete及第二/三窗各48层96个真实BF16 KV文件完整SHA（各4,907,335,680字节），退出0；收据`M/three-window-integrity.json`，日志vco08-three-window-integrity-739891bcbbcb4d389f3cf26ff8fa9449。每窗仅一次原生采样，0新增模型调用。

已实际查看第三窗contact-sheet：白鹭/黄喙/黑腿及raw12→13边界姿态可辨，未见明显静态硬切；早段偏亮、后段背景变暗，主体逐渐偏左，部分下拍翼尖出画。真实观察保存`window-003/static-observation.json`，screening SHA `1471caad21be19bbfbd40e06a67c85191aa0d92881aa036f5b3d8a4b7dcc7c49`；allow_next_window=false仅因已到本case三窗上限，不新增第四窗。记录器首次误用不含Torch的3.12解释器、在任何写入前import失败；随后经bootstrap使用既有嵌入式3.13成功，未改冻结源/媒体或运行模型。

`M/assemble_chain.py --windows 3`退出0（日志vco08-assemble-three-window-chain-185712f4c4cf47dbbf6fb9752450c72e），`trial-001/chain-003`实际253帧、15/1fps、253/15秒，原生无损解码逐像素一致；仅追加[0,93)、[13,93)、[13,93)，边界frame93/173，无重复/混合/插帧/变速。整段viewing.mp4已提供并发出新的完整动态观察问题，当前visual_acceptance=unverified、production_enabled=false；首窗接受不替代全链。GPU已退出，开始串行单点复现原timeout故障，session56001/日志test-92729b033f754c1a8ebf3f8ecccfdceb；仍未修改测试、未宣布全库通过。正式16fps接口只读调查见`VCO-08-native16-interface-audit.md`，新路线答复仍待。

**第三窗运行中（2026-11-02 09:14+08）：** 首窗用户完整观看原话“完整观看后可接受，继续后续两窗”已绑定`window-001/dynamic-review.json`，不重复请求后两窗授权。第二窗session66767/worker28276退出0，4668.062秒；result SHA `670f6c5deac53c389a339cc4f86fa80a78aef6c478d6c0bc3033677a176ab69a`，screening SHA `23649b4fabac8921a3635e38ac31c60c37c9cb77edeb1173550217a051021b74`。原生93帧、13历史加80新增，链范围[93,173)，无损副本逐像素一致。实际clean KV为48层、96个BF16文件、shape[1,32,6240,128]，4,907,335,680字节。实际查看联系图后，主体/喙/腿和边界姿态未见明显静态断裂；进一步变亮/背景变浅仍保留为全链动态观察风险。历史重建MAE1.0593、首新增接缝MAE3.4531仅为未校准辅助统计。

第三窗已绑定第二窗result与screening启动一次，session29654/worker40556，开始08:42:18+08；监督日志`vco08-progress-io-native-window3-5ed59e5bbe2d477788407cecc88deab6`，worker日志`M/trial-001/window-003/worker-2d398d9501a64d31ad7fb6405832529f.log`。当前约19/50步，物理/commit/GPU空闲均正常，不设时间或占用配额，不重启采样。先监测此进程；GPU退出后才运行CPU核验与回归。最终第三窗技术核验、253帧全链组装和新的完整动态反馈尚未完成。

**精确回归断点补证：** `M/regression-checkpoint-boundary-proof.json`已保存末个已完成节点与下个独立tmp_path开始setup的边界证据；751个已报告PASS保留，1个失败单点待复现，4375个未完成nodeid仅从实际collection生成。只读审查发现timeout故障注入会被用户要求的production无时限策略覆盖；`M/timeout-failure-review.json`记录假设及最小测试注入修复建议，尚未修改测试。先在GPU退出后保留原节点真实RED堆栈，再决定修复；不恢复生产时间上限。新的正式16fps路线问题待答复，当前15fps研究持续，不把等待当批准。

**第二窗运行中、回归精确续跑（2026-11-02 07:22+08）：** 为纠正全库过早阻塞已授权续窗的执行顺序，已先独立collect-only两次，均5127个nodeid、顺序及520源文件身份完全一致，并验证所有源mtime早于原pytest启动且当前hash未变。随后只结束自有pytest40232/其子进程，session5241退出，日志script_exit15为调度中断，不冒充全库终态。EOF释放完整已报告前缀752项：751 PASS、1 FAIL，剩余4375项；精确绑定收集顺序/源身份/原日志SHA的`M/regression-resume-manifest.json`、remaining/failed-nodeids.txt均已保存。末个完成节点为whole_native_320_mapping_uses_real_decoded_media，下个为whole_protocol_to_upscale_full_pcm_final_review_and_idempotent_delivery。失败精确节点`test_scene_color_repair_recovery.py::test_actual_ffmpeg_failure_keeps_original_and_never_retries_same_uuid[timeout]`；调度中断前无最终堆栈，后续单点复现、按实际原因修复，再只跑余下节点，不重跑已报告通过的751前缀。日志vco08-regression-exact-resume-manifest-2963314f65b74386bdb8e69bf4665434。

CPU退出后新快照物理18,991,476,736/commit25,993,297,920/GPU23,838,326,784/磁盘64,215,891,968字节，满足门槛（vco08-progress-io-window2-host-snapshot-477df54ed95b4a6a97c30403f849dbd0）。监督stage2唯一一次，session66767/worker28276，日志`vco08-progress-io-native-window2-bfe05e7b8da24766a22dd7e0fa00e8c0`，worker日志`M/trial-001/window-002/worker-602495f0198f45f2a53b12a2b7ef9eee.log`。继承首窗RNG和13历史帧，仍93总帧/80新增、50步/CFG4/15fps，无时间或人工分配配额；资源检查保持。首窗用户接受及继续后两窗授权有效，无需再询问。最新活动入口M/live-run.json；以下全库“仍在运行”均为调度中断前历史。

**全库及空间维护（2026-11-02 04:54+08）：** 全库session5241/pytest40232持续推进到场景媒体恢复相关真实集成，当前可见约8%且已有1个F，详细堆栈待最终汇总，绝不预记通过。CPU/GPU串行，后两窗已获用户接受/继续授权，待本轮CPU批次退出后执行。回归夹具使磁盘余量接近32GiB保留线，已检查并完成可逆旧测试字体去重归档：只处理2026-11-02之前、具有scene-fixture-config.json或test-config.json且wan/text/vae/upscale路径明确指向models/tests的离线测试运行中的msyh.ttc副本；当前批次/真实生产/模型及研究视频证据均保持。1,745份副本34,384,094,240字节逐文件哈希一致，归档保留1份19,704,352字节完整字体和每份原路径/mtime/模式清单，净回收34,364,389,888字节，磁盘空闲66,841,567,232字节。收据M/closed-test-font-archive/receipt.json及journal.jsonl，归档日志vco08-archive-closed-offline-test-fonts-3a6a4ce35a9a449294fec1ab9beb34c6；单份恢复后字节/mtime往返复核退出0，日志vco08-closed-test-font-restore-roundtrip，具体ID见日志目录。可经bootstrap运行M/archive_closed_test_fonts.py --restore恢复原副本，归档内容保留。没有递归移动/删除生产目录，未触碰当前测试资源或原失败研究银行。

**首窗完整观看已接受、继续两窗已明确（2026-11-02）：** 用户对已披露的曝光变化问题明确回复“完整观看后可接受，继续后续两窗”。M/window-001（实际为M/trial-001/window-001）已新增绑定父result SHA091d3423…和观看副本SHA91949cee…的dynamic-review.json，保留曝光变化事实，限定只接受该首窗、不外推全链/正式16fps。screening.json以agent_image模式绑定同一父result/contact-sheet/static-observation/dynamic-review，allow_next_window=true。不得再问同一首窗接受或继续两窗授权；当前全库session5241仍运行，CPU测试/GPU串行，待该批退出后立即监督stage2一次。曝光观察旧“等待答复”仅为历史，不据此保持阻塞。

**第三案例首窗技术成功、曝光观察待裁定（2026-11-02 02:21+08）：** session75394/worker30428均退出0，监督elapsed4428.968秒、stop_reason=null，50/50步完整，sample-complete和result已提交。93帧/832×480/原生15fps/93÷15=6.2秒，无损raw副本解码逐像素一致；result SHA `091d3423b9fe1d45e54cff2f4b719dab3a947a71c0762001733282866d909e9a`，intent `18320a0726f0f40e3ed8826c337d7e1216bf81a41ee0ef20dec41834d73aa4a6`，latent SHA a42b5e69…；峰值GPU allocation8,365,084,160字节。所有已提交artifact的完整SHA复核通过；原生采样仅1次。

已实际查看原选图及contact-sheet的raw帧0/12/31/46/62/77/92：主体及侧向飞行构图基本保持，翼位有变化，但后段画面明显变亮、背景变浅。全画面RGB均值首176.20/138.32/104.45→尾225.32/194.21/160.14；这只是未校准全画面辅助统计，不伪造阈值/主体掩膜或动态通过。观察已绑定父result和contact SHA保存在`M/trial-001/window-001/static-observation.json`，验证日志`vco08-first-window-static-observation-fd17eeb04a9f4c71b0c08a448e730560`退出0、CUDA未初始化/新模型调用0。尚未签发screening.json，未启动stage2；已提供6.2秒viewing.mp4并请求用户完整观看、裁定曝光可接受性。前两次技术失败及所有冻结证据保留，当前无活动GPU。以下“首窗运行中”是启动时历史。

**收尾软件验证决策：** 现有产品源码已完成无时限及GeometryDecoder定向修复、此前全库没有最终通过结果；等待必要动态反馈时推进固定源码的完整全库是独立必要收尾。GPU已退出后串行启动`./scripts/test_windows.ps1 -q`，不是重启未修复基线，也不机械重复已过定向批次；实际结果另记，不预记通过。未来若正式16fps接入另有源码变更，仍须对最终源码完成相应验证，不能挪用当前结果。

**第三案例首窗运行中（2026-11-02 01:07+08）：** M五阶段预检session93062退出0，`full-dit-resource-probe-4aba38e2075343109e0328e2b660a0f7.json` complete=true，235.197秒；最低commit6,591,651,840/物理15,364,513,792/磁盘45,183,991,808字节。预检KV4,907,335,680字节在进程退出且case开始前释放，仅96个探针叶文件，48元数据及收据保留。新布局三个组件成功（`vco08-progress-io-checkpoint-layout-5bf639614c054ca98d12e2cb0d747a67`），25/11源及case/cache/admission/layout最终核对通过（`vco08-progress-io-final-admission-84f63ef7f86d4c449420b5211763991b`），独立只读review progress_io_review结论nothing important left，未运行测试/GPU。主机启动快照物理19,818,549,248、commit26,202,284,032、GPU23,822,598,144、磁盘50,091,102,208字节（`vco08-progress-io-host-snapshot-4f53512f2d0f4ad999d196234a490ba3`）。

通过bootstrap执行`Invoke-VideoAiNative $VideoAiPython @('-B','M/supervise_window.py','--stage','1')`，session75394/worker30428，日志`vco08-progress-io-native-window1-763237240dab43b193be5d38d5d0c9b1`，worker日志`M/trial-001/window-001/worker-e18f748801a6455e8835c125bb8824c6.log`，实时入口`M/live-run.json`。新首窗已且仅已启动一次，无执行时间/人工分配上限，资源守卫保持。不能因准备成功预记采样、视频/动态、多窗或正式16fps通过；不重启该进程/窗口。

**第三案例准备（2026-11-02 01:02+08）：** M=`D:/VideoSi/projects/video-ai/vco08-preflight/20261102-0102-progress-io`。用户“继续完成当前任务”明确允许已交付候选与独立新案例；M/prepare来源收据`preparation-provenance.json`绑定前两次失败。case003 SHA `c8164ea1f596f24f35e046579e166d631e84c8f2291b3e0e8c7a70ec571251c7`，25源软件SHA `71bd32426aed8afbeaa296a39acedc332286d3431bd8ec13930db45b82d4604a`；只替换已验证runtime_support读锁修复，其余24执行源与N相同。题材/seed/50步/832×480/15fps/93→173→253及空闲余量均保持，无时间/人工分配配额。模型/文本复用，0下载/编码/权重复制。准备日志`vco08-prepare-progress-io-trial-4388911dacf844718f4653dcf84ea8be`及freeze `vco08-progress-io-trial-freeze-765cbcb9691842f38ed55540d0e202b5`退出0。

已部署读锁probe实际3/3通过（`vco08-progress-io-deployed-reader-lock-5487933c6b16417688f70a2cd819ef1b`）；部署资源守卫probe通过21GiB历史峰值不拒绝及物理/commit/GPU/磁盘四项不足仍拒绝（`vco08-progress-io-deployed-memory-guard-4b48e706e77a44b4a5de498bb7be40b3`），CUDA未初始化/模型调用0。新的五阶段匹配身份完整资源探针session93062运行中，日志`vco08-progress-io-full-preflight-5c1e513650dc4d4889f22cb9e0e2b9b6`。当前M尚未开始视频采样；不等待原已退出86714，也不修改原N或R冻结源。以下“等待授权”仅为上一阶段历史。

**最新失败及候选（2026-11-02 00:05+08）：** session86714及worker24508退出1；监督elapsed1421.782秒、stop_reason=null。原生generate_i2v仅1次，16/50步后`BudgetGuard.check`的`progress.tmp.replace(progress.json)`触发`PermissionError: [WinError 5]`。这不是OOM、时间或资源停止；日志采样最低物理17,775,935,488、commit19,609,063,424、GPU空闲22,161,653,760字节，GPU allocation采样峰值8,365,084,160。没有sample-complete、成功latent、媒体/result或stage2/3。25冻结源已全部核对未变，观察收据`N/trial-001/window-001/failure-observation.json`，不是worker成功结果；记录日志`vco08-progress-failure-observation-ca7d1ef9d59d419894450a5866df9c6b`。

实际CreateFileW读锁禁止delete-share，已在CPU复现完全相同WinError5。监测进程并发读取快照可触发该Windows共享语义，无法从既有日志归属到某个具体读者。`N/progress-io-candidate-v1/{runtime_support.py,candidate.patch,proposal.json}`仅改可选快照replace：WinError5/32/33记录延后事件而不终止，下一次emission再发布；资源检查先执行、stdout已有本次资源数据，supervisor独立读取主机资源，故不放宽任何资源守卫，也不改数值/精度/采样。无关PermissionError继续抛出。候选SHA `f806827cbaf4a1fa84c5e0067f65dbf924f91029f059a63ab0d19329431e193b`，未应用到N冻结源。

`N/progress_io_probe.py`提取真实BudgetGuard执行（只替代CUDA查询，模型调用0/CUDA未初始化）：旧源RED读锁复现，日志`vco08-progress-reader-lock-red-c1828a320d094a998104cbab66bbbd02`；候选在3.12 GREEN 3/3（`vco08-progress-reader-lock-green-ef8cb13d995e4c33afec1d629f3a400d`）及worker3.13 GREEN 3/3（`vco08-progress-reader-lock-embedded-green-488b016eed6a4648b573d231e87d2948`），验证读锁不中止、释放后下一快照恢复、commit短缺仍拒绝、非共享权限错误仍传播。退出0；这些是候选定向，不是全库或视频通过。已向用户提交具体的新案例继续问题；待答复，不自动追加试验。以下“运行中”是启动时历史，原session已退出。

**新案例首窗运行中（2026-11-01 23:42+08）：** 新研究目录N=`D:/VideoSi/projects/video-ai/vco08-preflight/20261101-2314-allocator-unlimited`，case `vco08-longcat-native15-3w-002` SHA `a6580131999d4e7f308e88306c9784e26e1d7953d790968222a6d9ebaa0331e7`。实际命令经bootstrap：`Invoke-VideoAiNative $VideoAiPython @('-B','N/supervise_window.py','--stage','1')`，native session86714，worker PID24508，监督日志`vco08-new-trial-native-window1-8d7a4a6e143d4f2597a7b599fa849727.log`，worker日志`N/trial-001/window-001/worker-391a79539a044d4e860674dde2419a53.log`。唯一新首窗intent SHA `77aee0ae9b5244c489a80233e36329c0e2ed47165dcdd4968f105471c9edf3bb`。正在50步采样，不能重启或再调用；没有完成/视觉通过声明。

**新资源及身份已通过：** 完整五阶段探针session53703退出0，`N/full-dit-resource-probe-c45a733527024074a389b2cbe22fbd3f.json` complete=true，233.452秒，含真实合成条件1/13帧准备及FP32 sampling/previous-CFG驻留；最低commit6,570,909,696、物理17,361,801,216、磁盘40,289,021,952字节，峰值GPU allocation8,370,124,800，未施加人工池/峰值限制。此前无上限预检19b7f331…在VAE解码因空闲缓存累计导致commit余量不足退出1，未调用native diffusion/scheduler/视频。N新增71个VAE卷积前后空闲缓存释放hook，真实encode13/decode13对照`N/vae-cache-release-probe.json`输出和strides逐位相同；不改变精度/公式，不恢复配额。两次独立预检KV各4,907,335,680字节已在进程退出且case开始前清理，保留96层元数据文件及两份`released-resource-probe-kv-*.json`收据；只修正清理脚本PowerShell JSON数组展开，不改冻结运行源。

最终freeze 25文件软件SHA `2a444e36df96e3cf8fddc1a1ae31461f92f905da4834eb8cf292d53e115ce9f2`（日志`vco08-new-trial-final-freeze-42153cae87f445569f7f3d828764eeac`）；三组件layout通过（`vco08-new-trial-checkpoint-layout-9504ffdc4ed54b29a88dedf77aec060b`）；最终25执行源/11官方源/case/cache/admission/layout匹配（`vco08-new-trial-final-admission-f87c77563df44aa98d4f3add0d6618fc`）。23:41:54主机快照物理19,755,614,208、commit25,710,596,096、GPU23,822,598,144、磁盘50,103,418,880字节（`vco08-new-trial-host-snapshot-8e942c6d8c6247e49283ee16b90dcdc6`）。所有命令退出0。文本SHA仍53c254…，新增文本编码/下载/权重复制均0。原研究R及其失败源/案/intent未修改。以下旧“当前/无活动”叙述均为历史阶段，以本入口为准。

**生产无时限软件及最终定向已完成（2026-11-01 22:21+08）：** 主production/scene和旧pipeline都已取消执行总时限，新冻结记录`unlimited_v1`/null，保留单次HTTP、所有权、媒体/资源检查及unknown不重POST。原冻结文件不重写；连续性引擎源码指纹变化仍按原规则要求重评/历史归档，不绕过。主独立review三项问题及legacy review两项均完成RED→GREEN。真实首窗失败之后完成了剩余相关软件验证：最终230 whole-file（其中legacy追加三文件56项）通过，日志test-b1033d47453b46108f8ffd030e2dbf35；精确7个tiny/恢复integration通过，494.91秒，日志test-0a81e2f4e676484290c597707e4f56bb；最后四文件19项通过，486.76秒，日志test-8ea07d5464eb482eb27bd143779d8a64，session25726及bootstrap退出0。后者与7项中的两个媒体守卫ID共同覆盖交接原21项，最终源码未改变后不重复这两项。此前legacy476项通过（1248.81秒，test-68c135fbf31b4684933477ed643148e6）、最新legacy16专项及真实旧finite首次恢复单项均有退出0证据，详见两份生产time-limits设计/验证文档。计数为逐批结果，不虚构无重复总数。

明确延期：原275项选择并非全部通过。test-06952...在5PASS后因未改动200帧原生映射大fixture按调度中断；相关无时限边界已由真实小case覆盖，剩余33个精确ID留至VCO-08最终全库，不预记通过。列表及所有中断批次见`VCO-08-production-time-limits.md`。最终git diff --check仅为格式验证，项目全库仍未完成。当前没有活动模型或测试进程。

**可审核候选未应用：** `R/allocator-candidate-v2/{candidate.patch,proposal.json}`准备移除人工8GiB池限制，并把真实条件准备、FP32采样latent/前步CFG驻留及32GiB磁盘门槛纳入完整资源检查。旧R的25个冻结源已重新核对完全未变；原失败案例不改、不重采样。三个候选源仅语法compile通过；CPU准入fixture先RED（旧候选误接纳BF16前步驻留，vco08-allocator-candidate-admission-red-19672bd7b94b4fd9935c545cf52bfbf6），修正后七项unsafe状态拒绝且匹配fixture接受（vco08-allocator-candidate-admission-green-b992b668045846aabd1aee6a04f76eea）。独立只读review指出的FP32/disk两项已修正，未再次启动GPU或模型；没有CUDA适配/全模型/视频成功声明。后续实际新采样需要明确的新技术复验授权和独立案例血缘，不能利用准备期修订覆盖已启动原案。

**真实首窗技术失败（2026-11-01 21:35+08）：** 在所有现有准入检查后，按既定一次机会监督stage1，session86229退出1，worker PID28200退出1。监督日志vco08-native-window1-ead25c86c17144fb982ffda1d848aaa1；窗口日志R/trial-001/window-001/worker-19f2cddce2e24299b82c1ec482fc1dca.log。intent SHAe83cbeef5e4591981cd0952abc722572e5ed4ac6ec9b960fa74fa611627684a2已落盘，实际generate_i2v调用1次，在0/50步第一次DiT FFN乘法处OOM（申请1.54GiB；Torch已分配6.23GiB、未分配reserved257.86MiB，8.00GiB allowed，GPU仍15.70GiB空闲）。supervisor elapsed12.078秒，stop_reason=null（worker自行失败，非监督资源/时间终止）。无sample-complete、latent、视频/result；无stage2/3，未重新采样。原因确认是冻结的8GiB分配池上限而非实际24GB显存用尽；具体预检/真实pipeline额外驻留及allocator碎片的字节贡献尚未实测分解。

随机latent完整五阶段的成功不能外推真实采样：预检DiT直接接收BF16随机输入，实际pipeline先编码条件图并保留FP32采样latent、执行CFG/调度前的额外tensor及不同分配顺序。真实OOM是完整案例资源不通过的直接证据，覆盖此前“可进入首窗”的准备结论。已存在case/window-start及intent，冻结软件/原case不得按准备期修订；本案例禁止再次调用模型，没有可供只解码恢复的已提交latent。当前先收尾用户已授权的生产无执行时限软件验证；后续任何解除8GiB池上限或新技术复验须明确记录为新的授权/案例，不伪装成原窗首次调用，不重下模型或重编码文本。

**最新资源准入已通过：** 无时限原FFN完整探针session86537退出0，结果R/full-dit-resource-probe-1acf48d3d9254b099a95a516b994f683.json，五阶段全部完成、247.783秒，最低commit12,392,964,096、物理16,430,608,384字节，峰值GPU allocation8,318,638,080；真实BF16历史KV4,907,335,680字节。已生成resource-admission.json。随后显式准备期修订冻结25执行文件为软件SHA1342e93c84b8047066b51cc825523114430846dcd7bff681442fee9dcd5e9359（旧软件原字节归档），日志vco08-unlimited-final-software-freeze-a3758793cf06438fb33b7c8418d7052d。checkpoint布局三个组件均成功，日志vco08-unlimited-checkpoint-layout-5d4b2d36176c417f8afbcf579f26a011。stdlib最终身份复核退出0，25/25执行源、11固定官方源、case/cache/admission/layout均匹配，收据R/final-admission-check.json，日志vco08-unlimited-final-admission-3eb9e3e1b20e4657838ca865b35ff767。独立只读review research_unlimited_review未发现active研究改动的重要问题；历史prepare_trial/text脚本不执行，真实采样及动态效果仍未验证。下一步先完成生产无时限软件定向，再串行监督真实首窗一次。

**时间限制解除（用户最新明确指令）：** “不用设置预算，时间多长就是多长，把预算解除”，并明确正式生产也无执行时间预算，覆盖下文待确认延长方案和原240/3600/10800秒限制。研究四个运行文件已支持无时限（None），保留持久起点/身份、原资源门槛和一次采样/未知结果不重试。clock真实RED为None减float的TypeError（日志vco08-unlimited-clock-red-4ac38ff887104a3783897a9f3cfb8837）；修复后GREEN（vco08-unlimited-clock-green-7e13a319b4af41c894debb59e42526b4）核对100年无到期、身份漂移/缺启动拒绝及历史有限记录仍到期。实际BudgetGuard模拟检查保留五项资源拒绝、未初始化CUDA（vco08-unlimited-resource-guard-10612f3e5bcc4d50a458f8ebddc16eaf）。准入fixture及七项恢复fixture均退出0（vco08-unlimited-resource-admission-fixture-2c4823d613ef42dd93d33b004a465c02、vco08-unlimited-recovery-fixtures-ea7de21a76614111baa73c9d46d6f419）。

已归档原case及text-context.json，仅case两个时间字段改null；新case SHA5db7a7a468bddc4aa21ac5282ef4788c5addcfe6402a2840bfff7cd28c214e23。原文本缓存SHA53c254...及mtime完全不变，核对全部其他case字段一致后重绑来源，新增编码0。收据R/time-limits-removed.json、日志vco08-remove-time-limits-a35471709137473abddeae071af31d2a。当前原FFN五阶段复验session86537运行中，日志vco08-unlimited-original-ffn-preflight-7dfb3377b42945b38ded3b79351e267e；尚无成功准入或真实采样。正式生产取消时间限制作为独立代码改动并行推进，测试仍与GPU串行，未改旧run身份。

**本次恢复：** 产品原SHA与交接一致（8b28f283...），沿已审查候选应用GeometryDecoder/packed_geometry三行初始化和两个媒体守卫fake更新；复用既有RED日志，不从头重跑候选研究。下一步运行交接指定实际定向批次，随后原FFN五阶段资源检查；测试和GPU串行。旧全库session已退出，不重新等待或重启未修复基线。模型和真实文本缓存继续复用。

**恢复定向复验（2026-11-01 19:36+08）：** 实际产品SHA现为8158c24859e38ee118a8a34f8098e489afc38a63779f0e0c33e753abcd89963f，与已审查隔离候选一致。`./scripts/test_windows.ps1 tests/unit/test_research_pair_report.py tests/integration/test_natural_repair_flow.py tests/integration/test_natural_repair_media.py tests/integration/test_research_material_flow.py tests/integration/test_scene_continuity_recovery.py::test_direct_media_context_cannot_bypass_current_guard tests/integration/test_scene_continuity_recovery.py::test_media_write_guard_rechecks_current_epoch_before_write -q`：21 passed，495.97秒，native/session与bootstrap均退出0，日志`test-69601399cb1142218249ad1076e87b3d.log`。这是实际定向通过，不代替最终全库；接下来原FFN完整五阶段资源准入。

**原FFN实测及时间预算缺口（2026-11-01恢复后）：** stdlib最新主机快照可用物理21,447,778,304、commit26,964,508,672、磁盘65,867,653,120字节（日志`vco08-resume-host-snapshot-d75f6c5d937246429dcd1b03d8f513e0.log`）。随后实际完整探针session53408退出1，日志`vco08-resume-original-ffn-full-preflight-abb94c69ed05432690cbe11f49bbda59.log`，结果`R/full-dit-resource-probe-723406d612844f1c8ead7fd4c8d54680.json`。首次完成三个独立预训练DiT前向及VAE编码；93帧解码/finite/postprocess也已执行，但最后Guard在246.402秒因超过240秒而拒绝，completed_shapes只有前四项，complete=false，不生成resource-admission。最低commit12,626,620,416、可用物理18,070,351,872字节，峰值GPU allocation8,318,638,080；本次不是内存失败，不能把解码已计算写成五阶段准入通过。

阶段首末Guard给出含有限值同步的保守耗时：首窗80.786秒、clean历史56.063秒、续窗94.858秒，VAE编码约0.933秒、释放/解码/postprocess约13.175秒。50步仅前向投影首窗4039.3秒、续窗4742.9秒，均超过3600秒，尚需worker启动、条件图编码、CFG/scheduler、latent及媒体提交/复核和余量。故不启动唯一真实intent，也不做无内存依据的FFN缓冲改动。提出只延长时间的待批准方案`R/time-budget-proposal.json`：准备240→360秒、每窗3600→7200秒、案例10800→21600秒，原FFN/画面/50步/seed/资源阈值不变。每窗按实测续窗前向×50加900秒其他开销，仍留约1557秒余量；这只是预算规划，非真实50步性能保证。当前case/software/文本绑定均未改；批准后需保留旧case与原文本来源，不重编码地验证/重绑预算变更下的同一缓存，再取同身份资源证据及freeze/layout。等待该明确预算修订选择；VCO-08保持IN_PROGRESS，未新增真实采样或最终全库。

**最新暂停现场（2026-11-01 19:17+08）：** 原全库session89796/PID7624按用户请求中止，launcher21160亦已退出；session返回1，原日志记exit_code/script_exit=-1，没有最终pytest总结。此前5FAIL/8ERROR保留为部分结果；下文“正在运行/等待退出”的叙述均为历史阶段，不能再等待旧session或当作通过。两类候选仍未应用，下一会话先按pause handoff核对SHA、应用已审查修复并定向复验。没有启动新的GPU探针/真实视频。最后只读主机快照为可用物理16,463,290,368、commit15,040,086,016、磁盘65,367,109,632字节，日志`vco08-runtime-snapshot-memory-clarification-9943e6fb56b34b0095ce554c75c8122f.log`；主因是Windows提交额度余量，旧完整模型门槛缺口约57.3MiB，并非磁盘不足。用户偏好释放其他应用内存后按原规格验证，未指定关闭应用，本会话未关闭用户应用。

研究目录：`D:/VideoSi/projects/video-ai/vco08-preflight/20261101-1238/`。

固定模型下载已于2026-11-01 **06:43:56 UTC完成**，native session2400退出0、原PID39904已结束，日志`D:/VideoSi/cache/video-ai/logs/vco08-fixed-checkpoint-download-chunked-1d26e01713d04445b4c465fc3cb27d78.log`。完成收据为研究目录`download-result.json`，23/23文件共77,577,230,776字节已按固定清单核对，目标`D:/VideoSi/models/vco08-longcat/03b55529b1d1d4045f5fbe14d65c8c6e8116b278/`。无需再运行下载器或重复全量哈希。

一次试验配置已冻结在`trial-001/case.json`：首窗93、续窗各13历史+80新增，总93→173→253，原生15fps；首图为原已接受scene3飞行图SHA d29e1f20...，首窗seed42、续窗沿父RNG状态，不继承旧观看。**尚无扩散视频调用、无窗intent/真实输出、无新的观看或生产启用。** 运行器/监督器及调用前检查仍在准备；不能因下载完成自动执行一个未完成审查的runner。

**历史软件准备登记：** runner/监督器曾完成独立增量审查，三个P2已解决，结论“nothing important left”，仅针对当时研究代码。21项执行代码的软件SHA `68501cce7639c3b049d240f4605871eaf20351065a4471b85d2b484b774134a4`及后续22项`97b69...`均为历史准备身份。当前正在集成下述资源修复，执行代码已与97b69不同，尚待新冻结及增量审查。**不能按历史“下载/layout后启动”直接调用视频；须先完成当前资源门槛，再冻结、layout、监督首窗。** 11份官方原始代码Git blob已核对，只有声明的禁用BSA提前导入/终行差异。

**更新于真实文本准备之后（2026-11-01 14:00+08）：** 上述68501冻结为准备期历史版本，已原字节归档。实际UMT5准备暴露只读mmap页面读后仍驻留工作集：6.49秒时RSS16.94GB、可用物理内存0.60GB，commit仍11.70GB；原guard正确退出，无扩散intent/试验起点。新增`mapped_residency.py`仅对当前进程的MEM_MAPPED/PAGE_READONLY/COMMIT参数页调用VirtualUnlock，私有Tensor/KV跳过，不修改文件/数值或其他进程。微软文档依据为`https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualunlock`；ERROR_NOT_LOCKED也会移出本进程working set。64MiB实际映射探针释放约67.10MB RSS、refault值及原文件SHA不变；tiny mmap/T5数值回归通过。确认无case/window-start、intent或layout后，显式准备期修订并保留revision JSON，当前22项软件SHA为 **`97b69cdde5da11b1815c7cce2805f6a45370f71890616e97cce2ffd72f79edeb`**。独立增量复核已通过。

修复后的真实文本编码25.01秒完成，观测RSS最高1,713,790,976字节、GPU tensor峰值2,143,301,632字节，物理内存始终约15.5GB以上可用；缓存`trial-001/text-context.safetensors` SHA `53c254856bcb45c0fd1cb8081bb5391538a9c0b672687e1605c1ef13404e77c5`。这只是两份文本提示准备，未开启case/window或扩散；真实首窗将复用该精确缓存，不重跑编码。源码/依赖/首图/案例数值协议未改变，只修复本进程映射驻留行为。下载仍为同一session2400/PID39904，尚待完整DiT和当前97b69身份的layout检查。

**当前停止点（完整模型检查后）：** 全部权重已下载，但完整模型资源准入失败。未共享RoPE表时，`full-dit-resource-probe-487c14a46dce4bc6b930ddcd261f09c0.json`最低commit4,246,990,848字节；共享相同参数的频率表并通过逐位检查后，`full-dit-resource-probe-7d82981921dc4af19edf63e6578338f3.json`仍在首窗前向以最低commit **4,234,903,552字节（约3.94GiB）** 停止，低于4GiB 60,063,744字节。GPU tensor峰值8,318,638,080字节，可用物理内存最低14,336,954,368字节；并非已用尽24GB VRAM。两次均退出1，没有完整48层通过，clean历史/续窗完整前向未执行，**无真实视频采样/intent**。下一步需先释放外部提交内存并重新取得同规格完整模型准入；或另行设计/验证低内存路线，不能无限微调分配参数、降低资源阈值或据小探针放行。

软件仍以97b69为历史冻结身份，当前源文件已改变，未新freeze或layout。已新增`research_state.check_resource_admission`，缺少成功的三shape、同case/download/全部源码/版本、原阈值资源证据时，supervisor在创建任何试验预算/进程前拒绝，worker在intent前再次拒绝。完整探针只有全部通过才写根目录`resource-admission.json`，当前不存在。门禁RED/GREEN日志`vco08-resource-admission-red-0d19fad9084b49f3958d2f9bdd01008a.log`、`vco08-resource-admission-green-e72cda9ca50d4a21aa453dfd952c62bf.log`；缺失/失败/部分/源码版本身份漂移/余量不足拒绝，以及匹配fixture接受均通过。实际监督入口检查`vco08-supervisor-resource-refusal-7b860169bb804f61918fe9861c06d0f2.log`退出1并准确报“No successful full-model resource admission”，未创建case-start/window-start/intent。增量只读审查已复核该门禁及完整探针，无重要问题；不代表资源通过。

项目最终全库回归已启动：`./scripts/test_windows.ps1 -q`，日志`D:/VideoSi/cache/video-ai/logs/test-6cbc7cce122d44e49274cd71238e166e.log`。只读收集共5,079项，其中集成766项；当前已报告8个ERROR，位于既有`test_natural_repair_flow.py`及`test_natural_repair_media.py`的公共`natural_media`准备阶段，完整堆栈待本轮退出。没有修改产品源码或跳过失败，当前全库不能记通过。

进度输出到7%时另报告3个FAIL，按同一收集顺序定位于`tests/integration/test_research_material_flow.py`的完整CPU报告、自然基线和中断shard恢复三例，均调用同一研究窗口；实际堆栈仍待结束核对，已加入修复后的复验范围。

8%处又报告2个FAIL，独立复现日志`test-bd3b088e947c4a0a8debf45a599d5c45.log`已确认`test_scene_continuity_recovery.py`两个极小媒体门禁测试的旧fake不完整：缺`recheck_inputs`/`frozen`/`_media_check_coverage`，且一项仍替换旧require入口。真实构造器已初始化这些状态，当前入口为`capture_scene_continuity_guard`。只读复核支持更新测试夹具；研究目录`test_media_guard_candidate.py`补齐状态并保留原pending/调用顺序断言，两项GREEN，日志`test-36257d2fd5c64d629b2e9f108c956a33.log`。正式测试文件尚未更新，产品门禁没有改动；待全库退出后应用并复验。当前全库已报告5FAIL/8ERROR，仍未结束。

入口候选进一步让capture返回pending闭包，而不是在capture工厂内提前抛出，配合fake的`verify_captured_bytes`空实现，验证当前检查**确实调用所返回guard**且传播pending；原historical/current断言保持。该增强单项通过，日志`test-ab42e5f2a3744812a65f712cb32cfe2c.log`；实际测试文件仍未应用。

运行控制记录为研究目录`active-regression.json`：native session **89796**，Python PID7624（启动包装PID21160），本地14:48:41开始。仅等待该会话，不启动重复全库；进度行由PowerShell按完整行输出，单个点未刷新不代表停止。

耗时核查仅针对上述已确认PID：`py-spy==0.4.1`安装在独立`python-deps/profiling`，未改编排或数值环境。只读栈日志`vco08-regression-readonly-stack-a0d4510ab1ea4edf93262be17713da86.log`显示已进入校色恢复测试的fixture身份计算；10秒/20Hz采样`regression-profile.raw`共194样本、0采样错误，118样本（约61%）位于`hashlib.file_digest`，常见上游为colorimetry的身份重核验。日志`vco08-regression-readonly-profile-307ce9dd84b24e738ce9f3cc1a96b8c0.log`退出0。此诊断仅解释当前耗时，不跳过校验或修改正在运行的产品源码。

**回归排查与候选修复：** 只读审查已证明`_ResearchWindow`自定义初始化遗漏`geometry_decoder`，而继承的`AuditWindow.read_json`必访问此字段。`tests/unit/test_research_pair_report.py`新增普通/打包几何JSON两项回归用例，原源码RED均以该AttributeError失败，日志`test-befcb4cf1ee44b3eb542f72ee5ee3439.log`。为保留当前全库基线，产品源码尚未改；研究目录`candidate_research_pair_report.py`只补齐GeometryDecoder及packed_geometry初始化，在独立验证进程加载候选后两项GREEN，日志`vco08-research-window-isolated-candidate-27f278090437457080c0622619b4eaf5.log`，`geometry-candidate-result.json`记录原/候选SHA及产品源码未变。候选及测试已只读复核通过；待全库最终堆栈核对8个ERROR并实际应用/复验，不能把隔离GREEN记为产品已修复。

**未接入的内存假设：** 官方FFN的`F.silu(w1(x))*w3(x)`会为乘法另建中间量；已准备`ffn_buffer_probe.py`，拟检验不分块、不改变矩阵形状时能否原位复用激活临时量、保持预训练权重下两种全尺寸输出逐位一致并节省至少1GiB。先以CPU算子初筛全部65,280种有限BF16输入值、三种配对移位及连续/跨步布局，六例输出位模式一致（含符号位），CUDA未初始化，日志`vco08-bf16-buffer-operator-cpu-5832becee6d34430a0071e909a093df4.log`。这仅验证CPU逐元素算子，**真实权重/CUDA/内存峰值探针尚未执行，缓冲复用函数尚未实现或接入**；不把此假设当资源通过，GPU探针须等软件测试结束后串行执行。

主机状态随后有所回升：只读stdlib快照`vco08-runtime-snapshot-125a3df8107748d1a32aad88eb65b758.log`记录可用物理16,934,768,640字节、commit15,771,013,120字节、磁盘53,932,052,480字节；没有case起点或资源准入。该快照未加载Torch，不能直接当完整模型余量。软件测试结束后先重新核对环境并按**原FFN**重做完整三shape资源检查；通过则沿原计算继续，只有仍不满足才做未执行的缓冲复用CUDA候选验证。

为给后续测试/案例保留磁盘空间，已核对路径、非重定向属性、4,907,335,680字节大小及对应probe JSON后，移除本轮三个全零`synthetic-kv-<uuid>.bin`占位文件；逻辑总量14,722,007,040字节，收据`synthetic-kv-cleanup-f8f1e0fd20724d30bc8239a3c4d4afc6.json`。实际BF16 KV银行、预训练权重、文本缓存及各项JSON结果保留。清理后快照日志`vco08-runtime-snapshot-after-scratch-cleanup-49d6482e7ed04f89bffb186c883a644d.log`记录磁盘67,419,078,656字节、commit15,480,492,032字节；仍无案例起点/准入。后续完整模型预检已补齐导入`trial_worker`并调用纯验证`validate_case`，覆盖真实worker的Transformers/PIL/媒体模块基础内存；不调用run_window、scheduler或视频生成，尚待软件测试结束后执行。

资源门禁同步严格要求`worker_import_footprint_included is True`：缺失或False不接纳。新增负例在旧条件下实际RED（Unsafe resource evidence admitted），日志`vco08-resource-admission-worker-footprint-red-6b731f43a80f4624bacf0b3f47d42c49.log`；补条件后GREEN，日志`vco08-resource-admission-worker-footprint-green-40bae4c4bcaf49cea5c45011eefdeb7f.log`。增量只读复核确认导入不启动案例，源码/版本/case/download绑定保持，无重要问题；不代表资源前向已经通过。

随后补齐实际VAE窗口形状：完整DiT三形状后再做13帧合成历史编码、93帧解码及同worker的postprocess，分块检查finite，不保存媒体。门禁现在要求五项完整序列`first/clean_history/continuation/vae_encode_13/vae_decode_93`。缺VAE阶段的旧准入条件RED，日志`vco08-resource-admission-vae-shapes-red-ebf6706c4f774f269da13574b47e99d1.log`；五项条件GREEN，日志`vco08-resource-admission-vae-shapes-green-c18ba03ee7ea4a91b958b95ee410e2c3.log`。这些仍是stdlib门禁fixture验证；**真实GPU五形状预检尚未执行**，等待当前软件全库结束。

18:56只读现场复核：原全库session89796/PID7624仍在运行，栈已推进至`test_scene_upscale_flow.py::test_authentic_200_frame_chain_submits_only_93_92_15_and_contributes_every_retained_frame`，不是停留在之前的校色恢复用例；日志`vco08-regression-readonly-stack-current-186b3b716acf41f38295afc6fb9bcf25.log`退出0。产品研究窗口SHA仍为8b28f283...，上述候选尚未应用。五阶段probe与真实worker生命周期的增量只读复核未发现重要新缺陷；现有阶段首末Guard累计时间与finite断言同步可用于既有手动时限检查。取得成功实测后，须分别按首窗/续窗前向耗时×50，加上启动/校验、历史编码/KV、CFG/scheduler、VAE及latent/媒体写入复核和余量，核对3600秒/窗与10800秒/案例；不能仅因资源通过消耗真实intent。目前仍无成功五阶段证据或真实采样。

## 已完成的真实检查

所有Python先沿仓库`scripts/bootstrap.ps1`初始化日志/缓存，再使用Invoke-VideoAiNative与-B。纯stdlib用编排Python3.12；数值探针用现有嵌入式Python3.13.14 / Torch2.13.0+cu130。研究包只写独立python-deps，未覆盖生产包。

| 检查 | 实际结果 | 日志名（均在D:/VideoSi/cache/video-ai/logs/） |
|---|---|---|
| 系统资源/元数据 | 物理33,346,146,304字节、查询时可用17,633,955,840；commit余量18,238,980,096；磁盘余164,726,112,256。HF直连超时，Python经hf-mirror取得固定revision及30文件元数据 | vco08-resource-probe-38a9e16b82c8436b8847f2de815c1ff4.log |
| 模型清单/小配置 | 六项配置/index大小及Git blob正确；DiT1022项/F32数据54,324,285,696字节，T5 242项/22,723,641,344字节；受限Range读取首shard header证实F32 | vco08-model-manifest-d5633fac98474cf68fbc4c5398d77a41.log |
| CPU原生机制 | 未适配attention实际拒绝；SDPA/eager误差≤1.79e-7，4历史latent clean KV/full误差3.58e-7；更早历史改变新增输出，BSA拒绝 | vco08-tiny-adapter-probe-root-fix-c019b0d7e48b4d53a67bd8fce6ac56a0.log |
| CUDA小模型最终内核限制 | F32 tiny eager逐层加载与驻留误差3.58e-7；正式BF16 efficient-only路径本次驻留/卸载差0；cache/full差0.004971；失败层恢复CPU，峰值34,680,832字节 | vco08-efficient-only-tiny-cuda-f039f61152d3423bb75571d898c51de0.log |
| 只读mmap | 851,000字节随机小checkpoint的assign零复制、计算后原CPU data_ptr恢复、原SHA不变；缺key/错shape/重复tensor拒绝 | vco08-tiny-backing-probe-shape-fix-0855505c10e34919a1a3c230823ee085.log |
| 实际模型meta布局/API | DiT13,581,071,424参数/1022项；UMT5 5,680,910,336参数，唯一共享alias encoder.embed_tokens.weight→shared.weight；VAE126,892,531参数/194项；官方原图480p桶480×832。无预训练权重加载 | vco08-runtime-shape-probe-complete-deps-6a2e6940f19546188a7830e23d5d9398.log |
| 实际规模attention内核 | CFG batch2、32头、head128，q35880/k37440及q31200/k37440；flash不适用、efficient适用，math明确禁止；0.586/0.446秒、峰值3,874,291,712/3,531,603,968字节 | vco08-full-shape-efficient-attention-3eb3aa940427438da83266f6a6b134a6.log |
| UMT5卸载/alias | 随机小UMT5驻留/卸载差0、shared embedding对象与CPU引用恢复，prehook预算拒绝后恢复CPU | vco08-tiny-text-staging-probe-7daeb40be85649b89d8080a1dc7a022f.log |
| 实际VAE单图重建 | 官方VAE文件SHA d6e524b3...核对通过；latent[1,16,1,60,104]、decoded[1,3,1,480,832]有限；峰值3,335,620,608字节，0.477秒，RGB平均绝对重建差0.858。只是VAE，不是扩散/视频质量通过 | vco08-vae-roundtrip-probe-2574e46c4d5b48eb9ec729903b71448c.log |
| 冻结案例 | case.json与原选图副本已准备，模型manifest SHA 27bc85656592f2d99ebc29da08ef2b13fb78c669e653aa1170ef2933cad5425a；无视频调用 | vco08-prepare-trial-40ab70d687f84985a0ef08a2c41e9d54.log |
| 媒体格式 | 五帧合成RGB的lossless解码像素完全相同，viewing副本15fps/PTS/帧数正确；有损RGB差2.303，不宣称像素/色彩链通过 | vco08-media-io-probe-2b57fa849d884843a4468e44820538dc.log |
| 恢复故障检查 | 七项合成故障检查通过：持久化剩余预算/到期拒绝、电影pending中断后保留/重做提交、数组/JSON一致重放及漂移拒绝、父结果/sample收据绑定拒绝；没有真实模型调用 | vco08-recovery-fault-probe-7d283433ed8b4705a9a9714df1ba6f3e.log |
| runner结构 | --check退出0，报告93→173→253；明确完整下载尚未完成，真实模型调用0 | vco08-runner-structure-check-7bac4f9e16e44162bde4e488d2b4a7a6.log |
| 真实文本准备RED | 只读mmap驻留累积触发物理内存阈值，退出1，未产生文本缓存或扩散intent | vco08-real-text-context-preparation-743406848b784b4eba7ad7e8ac1ccd6e.log |
| 本进程映射回收 | 64MiB只读文件映射RSS下降67,100,672字节，refault数据和文件SHA不变，private tensor未触及 | vco08-mapped-residency-probe-c3ff253e51dc45b382599e7d7a3cd4df.log |
| 准备期软件修订 | 旧68501原字节归档，未启动试验前更新为22项97b69；案例/依赖不变，revision证据保留 | vco08-preparation-software-revision-5fdbe233074e4bf285ca65b409d9bae4.log |
| 真实文本准备GREEN | 25.01秒完成，RSS≤1.714GB、GPU allocation≤2.144GB，文本缓存SHA53c254...已绑定；扩散0 | vco08-real-text-context-residency-fix-e192819522324144b7a651c891d1ad63.log |

每项JSON证据均在研究目录同名probe结果中。这里的数值探针不代表完整模型资源或视频动态接受。GPU测试串行，没有同时运行完整模型视频推理。

## 已知失败与修正

### 完整规模的Windows提交内存准备

单个真实预训练DiT块（随机激活、无扩散/视频）显示，限制因素还包括WDDM/CUDA的Windows commit，不能只看24GB VRAM。完整FP32 RoPE临时量、CUDA保留池和约4,907,335,680字节私有CPU KV会耗尽4GiB运行余量。

- FFN按2048 token分块的数值比较失败，最大差0.125，强制contiguous也未通过；该实验已拒绝，不进入runner，不放宽容差。
- Windows当前Torch不支持expandable_segments，已核实，不重复尝试。
- `rope_chunking.py`仅把同一FP32逐元素旋转公式放入2048 token切片；实际head128/BF16的连续及strided输入，输出值及strides逐位一致，证据`rope-chunking-probe.json`。
- `max_split_size_mb:128`、8.5GiB分配池、FFN前释放空闲缓存、VAE常驻的一次探针在前向阶段最低commit4,378,292,224字节，但完整隐藏张量finite检查后仅4,293,361,664字节，低于4GiB 1,605,632字节，退出1。改用有界检查的复测也曾在前向阶段低于阈值（4,274,167,808），说明环境波动，不能归为纯检查假象。
- 保持4GiB阈值及原FFN，分配池上限收紧到8GiB。首窗形状、真实VAE常驻、同一真实块连续重放48次通过：63.97秒、GPU allocation峰值8,300,647,424字节、commit最低4,565,618,688字节、物理余量最低14,332,227,584字节。日志`vco08-first-48-block-resources-665ae15d18e44c209f3bd4df33d54ffa.log`；这是重复一个真实块，不是完整48层或视频通过。
- 新增`disk_kv.py`，每层BF16 KV写入本次窗口独有文件后仅只读mmap，原生`.cpu()`复用同一映射，不形成全量私有bank。独立RED证实缺少适配器；实现后BF16逐位往返、MEM_MAPPED/PAGE_READONLY、重复layer拒绝及实际CUDA tiny DiT cache/后续输出逐位检查通过，日志`vco08-disk-kv-integer-mask-436af03817e546a7b4353e87c7478cad.log`。探针曾因CPU autocast调制dtype和浮点mask失败，已修正探针为CUDA原有混合精度和整型mask，未放宽数值检查。
- 完整48层容量的真实BF16 KV写入及续窗单块48次重放已退出0：114.32秒、KV4,907,335,680字节、GPU allocation峰值8,246,039,552字节、前向阶段commit最低4,385,423,360字节。日志`vco08-continuation-real-kv48-resources-8ed6c8c106994522b8c511c20c269d37.log`。该探针为逐位检查而触碰完整只读bank，RSS最高约6.64GB；commit未形成全量私有bank。仍不代表48个独立预训练层通过。
- 增量只读审查已核对KV hook位置/生命周期/算术和allocator/freeze边界，结论“nothing important left”，仅限代码；指出单块余量不足以代证48个独立RoPE缓存。已新增`full_dit_resource_probe.py`做完整48层随机latent前向，覆盖首窗/clean历史/续窗，240秒准备预算，不调用scheduler或视频生成。初次探针遗漏安装attention而正确拒绝，日志`vco08-full-dit-resource-preflight-b5b59945ee4646f28cd210b8ca146ce4.log`退出1。补齐同worker的`install_attention()`后以及共享RoPE表后的两次资源失败，见上方当前停止点。共享表的RED/GREEN日志分别为`vco08-rope-cache-sharing-red-8c1e574b0f514886a5c9b5c17308b19b.log`、`vco08-rope-cache-sharing-green-9d4a30f65f794f718cab60de9b296272.log`，频率/forward逐位相同且只读增量复核通过。没有case-start/window-start或扩散intent。

- 初始PowerShell传Python -c的嵌套引号被剥离，元数据命令SyntaxError；改用脚本文件，未触及模型。
- .NET/curl的HF直连超时、mirror Schannel凭据错误；Python OpenSSL访问mirror正常，不关闭TLS验证。仅使用固定源身份和受限Range。
- 嵌入式Python隔离sys.path最初不含脚本根，native_adapter导入失败；显式加入研究根后通过。
- 官方旧tokenizers0.19缺少本机Python3.13 wheel，pip尝试构建时maturin不可用，退出2；不继续编译Rust。最终隔离使用transformers4.57.3/现有tokenizers0.22.2，其余固定版本及Windows loguru、ftfy依赖已补齐。没有把失败安装记为通过。
- 最初CUDA FP32位级相同断言失败，最大差3.58e-7；改按数值容差检查，保留真实误差，不宣称位级相同。BF16本次实测差0也不外推所有输入。
- mmap探针最初取一维tensor再flatten，未真正制造错shape，断言失败；改为取多维tensor制造实际shape差异。只复用已核实同一随机种子内容的自有小checkpoint，未重复模型试验。
- 下载初次遇到合法chunked小文件HTTP200无Content-Length而拒绝，退出1；只修复该header处理，仍验证确切字节及Git blob/SHA。当前下载GET沿同一清单执行，传输中断仅恢复同一byte range，不是GPU重试。

## 独立只读审查

按brainstorming技能的builder check派发独立审查`vco08_research_review`。首轮指出：需禁止SDPA math回退，并冻结真实窗口时限/资源阈值。已补齐高效内核限制、实际规模检查以及3600秒/窗、10800秒/案例、物理/commit/GPU/磁盘阈值和owned-worker监督职责。增量审查结论为“nothing important left”，**仅限当前研究合同及机制探针**。完整下载、真实checkpoint绑定、runner/监督器实现与审查仍是实际调用前门槛。

随后对完整runner作独立只读调用前审查，指出三个P2：媒体提交中断恢复、重启预算重置、已成功latent的父链重绑定不足。已改为原子pending媒体/JSON、持久化case/window起点及收据/父链完整绑定；上述七项故障检查已退出0，正在收回独立增量复核。此前审查不代替这次runner审查，不提前记真实调用准入通过。

后续增量只读复核已返回：上述三项P2均解决，当前代码增量“nothing important left”；完整下载/真实checkpoint布局/效果仍未代证。源代码固定核对命令退出0（11/11），日志`vco08-pin-source-check-d60b439802c34875882f539ff4e115a1.log`；冻结命令退出0，日志`vco08-freeze-software-e4773178535c41968d5e6a7109b4b365.log`。最终结构检查`vco08-runner-final-structure-8b38e62717de469d91be0e9040c2c79f.log`退出0，明确download_complete=false、new_diffusion_calls=0。

## 尚未完成

真实多窗资源/技术/静态筛查与完整动态观看；正式16fps适配/生产准入/失效恢复；最终全库（包括明确延期的33项）。时间限制解除的软件改动与本次约定定向检查已完成，最终四文件19项和两个媒体门禁共同覆盖原21范围。随机latent五阶段/freeze/layout/身份虽通过，唯一真实首窗仍0/50 OOM且无latent/视频，不能记真实资源通过、恢复解码或自动重采样。移除8GiB池的可审核候选尚未应用，GPU验证/任何新实际调用需新技术复验范围明确；原失败案与全部证据保留。完整下载与原文本缓存继续复用，不再下载/编码，不从小探针或VCO-07观看推断本任务通过。
