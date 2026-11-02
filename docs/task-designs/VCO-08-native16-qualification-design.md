# VCO-08：768×432 / 16fps 四窗资格样片

## Goal

为正式16fps部署取得独立真实四窗证据，保留原生时序条件与完整20秒映射。用户已明确选择“按建议直接推进，无需逐步确认”，且接受既有253帧15fps三窗整段。该授权允许本阶段直接准备、验证和运行；不把15fps接受转录成新样片通过。

## Scope

独立目录`D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification`，案例`vco08-longcat-native16-4w-001`。复用案例003的25份冻结执行源作为可追溯起点，只在新目录做明确适配；旧三个案例/媒体/KV不改。模型revision03b55529与官方code6b3f4b8、共享R/python-deps及现有文本缓存不变；不下载、不重新编码文本、不复制模型权重、不升级Comfy环境、不写.git。

本阶段交付资格证据，不提前添加生产mode；生产接入仍属VCO-08剩余工作，依据本阶段实际结果完善独立协议、准入、事务、修订与媒体消费者。

## Approach

选择延续已实测的隔离原生worker。直接复用现有15fps视频只能改变播放速度，无法证明新shape/输出时钟；直接改生产Comfy链会扩大未经验证的接口范围，均不采用。保留官方采样数学，以独立子类覆写`get_condition_shape`固定返回432×768。调用时使用明确adapter分辨率标识`432p-native16`；拒绝其他标识及不能整除尺寸的空间scale，官方i2v/vc均调用同一方法。原始官方11源保持逐字等价于已核对的working副本。

16fps是本次采样前冻结的部署输出时钟，模型API没有fps条件输入，证据须直说。原生93帧/窗，首窗1像素条件，续窗13历史像素→4历史latent，余20latent新增；完整latent[1,16,24,54,96]，clean KV各层[1,32,5184,128]，48层96文件共4,076,863,488字节。以上shape/大小先按公式期待，再以实际前向/输出核对，不能用推导冒充通过。

四窗保留93、80、80、67帧，累计93、173、253、320。每窗仍采样93帧；续窗只读父窗最后13帧，丢弃本窗[0,13)历史；前三窗各保留新增到93，末窗仅保留[13,80)，丢弃[80,93)尾13帧。只有末窗裁尾，后续没有新的历史消费。三处边界frame93/173/253，PTS统一i/16，完整320/16=20秒。不混合、插帧、循环、补帧或变速。所有原生93帧及末窗未保留尾帧仍留证。

首图、提示、seed42、50步、CFG4、官方scheduler、单Generator父状态恢复及原数值/映射驻留/71卷积空闲缓存释放适配保持；禁LoRA/量化/compile/FFN切块/math attention回退。新worker只允许读取既有精确文本缓存，缺失/漂移即拒绝，删除本案例的文本编码fallback；新case绑定缓存来源与提示/模型/编码算法一致的原收据。

沿既有五阶段实际资源预检，但全部使用新shape和子类；记录准备latent、clean KV、VAE13编码和93帧解码的实际shape与时钟策略。先冻结全部27执行源（原25+contract+pipeline adapter），取得同身份五阶段资源/布局/最终准入，再真实采样。资源证据门禁显式检查新shape、KV字节和部署时钟，旧480p证据不能混入。完整探针没有scheduler、视频生成或输出媒体。探针自有KV scratch在进程退出、逐项核验后可释放，保留元数据和清理收据；实际窗口KV永不清理。

时间和人工占用配额为null；原启动物理8GiB/commit10GiB/GPU18GiB及运行物理2GiB/commit4GiB/GPU1GiB/磁盘32GiB空闲门槛保持。仅监督自有worker，不关闭用户应用、不改pagefile。CPU测试与GPU执行串行，先完成当前session33919，不中止或重复已完成测试前缀。

每窗排他intent最多一次采样，绑定case/software/模型/提示缓存/父result/父frames/screening及原生调用计划；未知或失败不重采样。已提交sample-complete时同身份只恢复解码。每窗成功后实际静态筛查才签发下一窗screening；明显失败停止，不换seed/规格重试。用户已授权四窗，无需逐窗确认；完整320帧新视频仍须完整动态观看接受。旧结果不可变，观看结论另以绑定媒体SHA的review保存。

## Files

新目录：`native16_contract.py`（纯预算/尺寸/时钟）、`native16_pipeline.py`（官方pipeline子类）、`prepare_native16.py`（只复制执行源与小收据/首图/缓存、建立新身份）、`native16_contract_probe.py`（CPU RED/GREEN协议验证）、`native16_pipeline_probe.py`（真实子类/官方入口形状调用核验）、既有worker/media/resource/state/supervisor/freeze/admission/assemble脚本的新目录副本。

主仓只修改本阶段文档及VCO-08实录/任务板。当前回归运行期间不修改src/tests/scripts。实施账本`docs/task-designs/VCO-08-native16-qualification-plan.md`。

## Tests

全部Python经`bootstrap.ps1`、`Initialize-VideoAiEnvironment`、`Invoke-VideoAiNative`。stdlib协议probe用$VideoAiPython；pipeline/数值probe用既有嵌入式Python。

- `native16_contract_probe.py`：先缺模块RED，后GREEN；精确四窗保留映射/边界/320覆盖、非法stage/shape/clock拒绝，缺缓存或准入shape漂移拒绝。无模型/CUDA调用。
- `native16_pipeline_probe.py`：先原类不接受显式新分辨率RED，后实际子类对官方i2v/vc入口均输出432×768；不调用模型采样，可在shape调用后用专用哨兵中止。验证不支持scale/标识拒绝。
- `full_dit_resource_probe.py`：五阶段新shape、实际KV/finite/原余量全部通过才写资源准入；CUDA真实前向，不生成视频。
- `freeze_software.py`、`checkpoint_layout_probe.py`、`final_admission_check.py`：全部27源/11官方源、case/cache/模型/资源/布局一致；新增文本编码/下载0。
- `supervise_window.py --stage N`（N=1..4）每次只运行该窗；每窗实际93帧、sample/result/真实KV/父链及raw逐像素检查，静态筛查分账。
- `assemble_chain.py --windows 4`：实际320帧/16fps/20秒、完整精确映射、raw逐像素、三个边界；所有历史只输出一次。

## Acceptance

27源/模型/文本/身份与实际五阶段资源证据一致；四窗各一次真实采样，历史与新增分账、真实KV和父链可核验；320帧/16fps/20秒技术完整；三边界及主体/色彩/构图/镜头轨迹/动作的自动诊断与新的完整动态反馈分别保留。仅通过此样片适用范围，不声称任意长度、跨题材或生产全流程通过。失败保留，不自动新增案例。

## Risks

新shape的资源、细节质量和16fps部署时钟下动作节奏未实测；15fps整段已接受的曝光/构图变化可能在新样片出现。原始模型没有fps条件输入；须靠新实际视频验收而非改名。四窗比现有三窗多一边界，不自动获得通过。生产接口仍需本任务后续实现及独立准入。
