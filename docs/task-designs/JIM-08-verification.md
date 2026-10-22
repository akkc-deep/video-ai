# JIM-08 验证与真实验收记录

## 2026-10-22 FramePack-F1 两窗筛查失败（当前续作）

**本轮终态：两条F1链均在第二窗停止，颜色与构图的通用修复仍未获得。** caption对照原任务`52bd2e82-76d2-4c94-85b9-fce91d78b7e4`退出0、73帧/30fps/2.433333秒；frame72主体虽尚完整在框内，但头喙与尾腿相对参考明显右移，估计约画面宽度一成（人工并排估计，不冒充跟踪器测量），右侧余量持续减小。新描述比`trial-001`同seed/同时长的头部出框有改善，却仍未满足参考位置的跟拍要求，登记`failed_persistent_subject_tracking`。第二窗stopgate绑定state SHA `771ddb67ea0894f37b26b70904e3d0b83b7cadbac76969c49838c536f88623c2`，无第三窗或重试。短前缀软雾/背景氛围较接近仍不足以证明颜色、翼下新表面或长链合格；不送明显未达标版本请求用户再次接受。

`trial-002/final-audit.json`退出0（日志`jim-08-framepack-trial-002-audit-8f075cd073b8498498a12d6be9460e0e.log`）：3011原文件大小/SHA/mtime、378生产基准、25资产/上游源/私有依赖/缓存均保持；文本条件确实变更、anchor/SigLIP逐值相同、PNG metadata/无损RGB/PTS、固定anchor/原生成latent追加/历史前缀/RNG继承正确，worker结束、无第三窗。最终`caption-control-comparison.json`和日志`jim-08-framepack-final-control-verification-e770b3d2526e468ca962419f6e776154.log`退出0：两试验两窗各自RNG前后逐值相同，从记录状态恢复的实际初始噪声逐值相同且恰好推进到记录after状态；17个研究helper语法通过。没有新裸全库pytest，也没有本轮生产源码/workflow修改；历史3651通过不冒充重跑。

本轮停止提示词/seed/CFG扫描。只读比较官方原版FramePack固定commit下`demo_gradio.py`110–310行：其反向填充与未来上下文、生成历史前插和最终插入首图，和F1正向追加不同；必须不同训练checkpoint/协议，不能靠F1改一个开关获得同样抗漂移机制。GUI另有生成窗混合，不能借用其平滑成片代替原样验证。收据`original-framepack-architecture-review.json`含确切来源、行范围与Git blob标识；未下载原版权重、未创建该推理任务，不以源码机制推导本机质量。当前尚缺同时通过参考外观、构图及持续动作的已验证后端；跨题材与更长链验证未开始，生产时基/集成未变。下方“下一项/第二窗执行”均为本轮较早时点。

`trial-001` 原任务 `fb146581-7496-4f24-9984-c61075633c3d` 已按第二窗gate停止，原进程退出0；没有第三窗。首37帧、第二窗累积73帧，真实30fps/2.433333秒。完整原始拼图及末帧显示主体向右移，头/喙出框，登记 `failed_subject_framing`。短前缀的雾气、背景及水面氛围较此前SVI接近，但不足以证明长期颜色保真，也没有human/production接受。不以白羽局部正常通过整幅光照。

该试验资源及输入编码已经完成；下文“只读/未下载/未执行”是此前时点。25项42,866,789,142字节资产完整校验，独立依赖未覆盖Comfy；1274个BF16权重张量以mmap赋值加载，无数值转换。输入VAE往返DeltaE76均值0.734只证明静态重建接近。每窗保留原采样latent、完整历史、RNG状态及原生全历史解码；VAE内部tile合并保留，无额外生成窗混合、调色、稳定或重新居中。独立`trial-001/final-audit.json`退出0（`jim-08-framepack-trial-001-audit-86af737513f14e7d90423e211f73524e.log`）：3011原文件大小/SHA/mtime、378生产基准、25资产/源/依赖/输入身份保持；逐窗PNG metadata、无损RGB/PTS、19个零padding、固定anchor、追加原latent/历史前缀与RNG继承一致，stopgate及无第三窗核对。该审计确认技术轨迹，不通过外观。

下一项有界假设：提示先强调世界坐标下横向飞行，可能弱化跟拍及图像平面构图要求；旧caption额外提及原图不明确的reeds，也有无依据补景风险。只改外部运动/镜头caption，保持模型、seed、采样配置及视觉缓存逐值相同，重新计算文本条件；最多先比较两窗，失败即停，不换seed/CFG盲扫。不将此假设预先登记为根因或修复，亦不把该单场景回归当通用方案完成。

caption对照`case-002.json` SHA `00a8ba2c5ce14bb7079f6d92ef25e24565d576e88810afc14174d35d84633bf5`，新文本实际156个wrapped Llama token/61个CLIP token，无截断；`inputs-002`缓存SHA `5fd77dc6d43b1037c95d928e8a485578410eb9dcdc29e77486354c1353158299`。首图latent/SigLIP特征与父缓存逐值/类型相同，原参考RGB/往返PNG SHA相同，文本向量确已变更；准备阶段退出0并复核原目录/生产代码。独立`trial-002`已启动，日志`jim-08-framepack-caption-control-chain-013199a6940642829c6d43fe32fde9fe.log`；当前尚无质量结论，不重启失败`trial-001`。

原任务`52bd2e82-76d2-4c94-85b9-fce91d78b7e4`首37帧已内部筛查：主体完整在框内、软雾/背景氛围较接近；新露出的翼下有强暖透光，无配对表面真值，不据此宣布保色。仅放行第二窗检验持续性，human/motion/production仍未接受。对照冻结并启动后补查到[F1跟拍讨论#618](https://github.com/lllyasviel/FramePack/issues/618#issuecomment-3059063030)，社区建议镜头描述前置但明确不完美；[#512](https://github.com/lllyasviel/FramePack/issues/512#issuecomment-2868024488)另报告8–15秒曝光退化。两者仅经验来源，不是本机根因证明或官方保证，完整收据在source-check目录`camera-research-20261022.json`及`f1-community-quality-comments.json`。未据此追加提示版本/seed扫描。

## 2026-10-22 用户否决SVI候选：偏红与颜色失真（当前）

**本节三组SVI对照终态：均未修复颜色/光照，已停止后继生成。** 最后原BF16文本路径任务`6ed066d9-2f04-4a75-9ebd-504a83e306d4`15分07秒技术完成，实际81帧/16fps/5.0625秒，raw graph/cache、无损RGB与PTS通过。与7.5原FP16 DiT基线相比，最终帧之间DeltaE76均值1.623、平均L差−0.481、chroma差−0.497（这是两结果之间的差异，不是参考保真分数）；实际并排及完整末帧仅小幅变化，强金橙高光与暗背景依旧，failed_color_lighting_fidelity。正向embedding约9.7%相对L2差并未转化成充分外观修复，不能由向量差倒推出偏色根因。首窗不是对原三窗红偏全部时间范围的复现，不将这一失败扩展成所有SVI配置均无效。

该阶段`final-audit.json`退出0（日志`jim-08-svi-original-bf16-text-final-audit-a79187b01df24c499db67e68e97ac3b6.log`）：原3011大小/SHA/mtime、378生产基准、旧新模型/原编码器/冻结contexts SHA保持，同token/graph/client/原ID、两个上下文输入拷贝和有限latent核对；采样图无FP8文本加载器，自有服务结束。所有3个新实验各一次POST，没有后继窗口、没有新human/production接受，无调色/混合/插帧或正式run修改。一次后续进度消息滞后误称最后任务仍在执行，原ID实际上已完成；查询已关闭PTY返回Unknown process id，未重POST，已明确更正。以原history/result和本审计为准。

**后续目前仅只读资源/依赖核查。** FramePack-F1官方3个实际消费仓库元数据已200，25个候选文件合计42,866,789,142字节，逐文件LFS SHA/小文件Git blob SHA及不可变revision在`jim-08-framepack-source-check-20261022/resource-inventory.json`；未下载这些权重。与此前metadata超时不同，当前清单完整，但运行兼容仍未通过：Comfy嵌入Python只有transformers5.15.1，未安装diffusers/accelerate，官方要求4.46.2/0.33.1/1.6.0，不能直接执行或覆盖当前环境。已保存官方F1演示、hunyuan/memory/sampler/vision源码；其GUI包含soft_append混合，未来若准入应验证完整原latent解码而不能把默认混合隐藏接缝。未执行FramePack、未改变正式原生16fps/463帧契约，JIM-08仍IN_PROGRESS、颜色未修复。

**当前原BF16文本路径对照首窗启动，尚无质量结论。** 原FP16 DiT对照仍失败后，复用本地既有原BF16 UMT5，无新增下载。针对本次实际首窗同native token IDs：正向117 token，FP8/原BF16 cosine0.995256、relative L2 0.097233；负向126 token、cosine0.997547、L2 0.069976，均有限。官方clean与native分别有4/27处token差异，已强制相同native IDs以隔离路径，不能称完整官方清洗复现或由向量差直接定颜色根因。

新根 `jim-08-svi-all16-validation-20261022/`，text-001保存这次实际prompt SHA、tokens与原BF16缓存；不复用旧VACE续片条件。真实原生ConditioningLoader读取F32保存的BF16值逐值相等；图仅替换text/positive/negative文本编码路径，模型/LoRA/原prompt/seed/anchor/50步/81帧/16fps与7.5保持。case SHA `980d7fcdd9080b42f61b024998e33ead87c21e7cb1fefde248f6ac1fbe2131a9`，采样图无CLIPLoader/CLIPTextEncode，即不再实际消费FP8文本。完整输入缓存hash在前置与每次原任务查询guard中核对，仍一次POST、最多一个首窗，不续接此前失败链。原生Comfy与官方完整网络/调度的独立数值等价尚未证明，不声明官方完整复现或通用修复。

**原FP16 DiT单因素结果同样未通过外观，停止续窗。** 唯一任务`d9283b1d-504d-41ad-b635-03e7ccb13de9`15分11秒技术完成。高/低实际均`manual cast: None`、27,251MB staged和400 LoRA补丁；高低阶段进程峰值工作集观测约16.1GB、GPU观测约18GB，无OOM/静默降精度。81帧/16fps=5.0625秒，原始PNG/graph/cache、无损审阅RGB和PTS精确通过；原latent SHA `a844e14a5663b66d875d954cf6297481121912adcefbf5257abb996d203a875b`。并排原图/原FP8首窗/新FP16首窗与完整末PNG仍有更强金橙高光和暗背景，failed_color_lighting_fidelity；没有第二窗/human接受/生产切换。首窗不是用户未指定秒数的第三窗红偏的直接测量，不能据此声称已排除全部量化/提示/实现因素。

`jim-08-svi-fp16-validation-20261022/final-audit.json`完整审计退出0，原3011大小/SHA/mtime、生产378和旧新全部基础/LoRA/参考/VAE/文本SHA保持；唯一任务/graph/client/输入cache/有限latent及服务结束核对通过。原FP16 DiT替换不是充分修复，FP8文本仍实际使用；下一个有界检查复用本机已存在原BF16 UMT5，先同token对照缓存，再只替换文本编码路径，不再下载模型。下方“采样执行/质量尚未核验”为历史。

**原FP16权重就绪，首窗受控执行已启动，质量尚未核验。** `jim-08-svi-fp16-validation-20261022/download-result.json`完整57,155,829,584字节、两个完整SHA通过；原文件独立，不覆盖旧FP8。`resources-ready.json`核验高/低各1095个原F16张量、无FP8权重，各400 LoRA目标形状与旧模型相同；case SHA `a8f2ff13f63c8ec3409ecf571c8ff48258a4a0bc462433f322b163c4cfb5be75`。新generic runner只追加由case模型父目录驱动的搜索路径，条件节点未改，图与7.3原首窗仅两个UNET文件名不同。首窗仍原提示/seed/anchor/LoRA/FP8文本/50步Euler/simple/高21低29/16fps；运行日志`jim-08-svi-original-fp16-first-window-`，独立window-001。下面“下载中/尚无采样”为更早时点。无生产集成或颜色通过声明。

**当前后续：原FP16双DiT隔离资源传输中，尚无新精度采样。** 7.4阶段最终审计`jim-08-svi-color-rejection-20261022/final-audit.json`退出0，原3011大小/SHA/mtime、378生产基准及既有权重保持、唯一提示词任务与PNG/latent/graph/客户端一致，自有服务结束。按主设计7.5，追加同架构来源精度单因素核验；`jim-08-svi-fp16-validation-20261022/download-intent.json`冻结2个精确文件/57,155,829,584字节、不可变revision/SHA、60GB上限和900秒传输预算。只落独立`models/jim-08-svi-pro/fp16-base/`，完整SHA前是`.part`，不覆盖现有模型。当前传输正常；兼容/资源/图隔离检查通过后才一个81帧首窗，原暖光提示恢复作真正原基线，不叠加7.4变更。下方“尚未下载”是本节前一时点；任务仍未修复或生产集成。

**提示词单因素结果：失败，停止该链。** 唯一新任务`18fc7f99-f083-42e5-a4d6-c3c28ffe3c0e`10分40秒技术完成；同seed/anchor/资源/采样，仅正向两处暖色描述改为原图光照。81帧/16fps=5.0625秒，原始PNG/graph/cache及无损审阅RGB/PTS核验通过；原latent SHA `fe490b9ae172dd5a9c66d583892fa8cc94e747d9775916d86379f2d30311c538`。实际查看上下并排原图/旧首窗/新首窗和完整末帧，金橙增强、背景/水面变暗仍明显；`evaluation-001/visual-screening.json`为failed_color_lighting_fidelity、motion unverified、无human/生产接受。未生成后续窗，不请用户重复审阅明显未解决结果。此试验说明该提示词修改不是充分修复，不等于排除全部提示或重现第三窗粉红的全部机制。

原图、缩放anchor PNG、首生成PNG均无iCCP/sRGB/gAMA/cHRM/cICP元数据，未发现中途遗失输入ICC的证据（`png-color-metadata.json`）。旧/新首窗81帧及4×4格CIELAB统计保存于`old-first-window/`、`control-first-window/`，未来运动内容无逐像素真值，不能由这些分布直接判正常或归因红偏。官方原生工作流[作者评论](https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/1718#issuecomment-3694469703)明确部分50步样例会改变color style；[FP8提醒](https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/1718#issuecomment-3702376700)仅作下一个精度假设依据，不作根因证明。

只读核实同Wan2.2 I2V的真正FP16基底清单：高/低各28,577,914,792字节，合计57,155,829,584字节，revision `ee6f4a40737a995bf5818954cfce6d59443b0f04`，SHA见`precision-inventory.json`，与官方Comfy Manager实际路径相同。D盘可用443,447,549,952字节、容量前检通过；尚未下载这些基础模型、尚无精度对照推理。将现有FP8张量cast到float16不能恢复被量化信息，日志manual cast float16不是全精度来源。PowerShell/curl的Schannel读取失败已记录，bootstrap后的Python只读metadata请求200成功，无需用户凭证。

用户对14.5625秒SVI原样审阅候选明确反馈：**“这次画面颜色偏红，完全不对了”**。绑定文件 `D:/VideoSi/projects/video-ai/reviews/JIM-08-SVI-Pro-color-continuity-review.mp4`、SHA `3d74ccf06801c1fcc524027230f012139542669dc9ca55ce259db5b3c73f3472`。登记 `human_color_acceptance: rejected`、`production_acceptance: false`；未提供具体起始秒数，不编造接缝/动作结论，旧待答问题已由本反馈覆盖颜色项。下方“待用户真实播放”和内部static_screen_pass是此前历史时点，不再是当前验收状态。

重新查看三窗原始PNG拼图，首窗金橙增强、续窗天空趋粉和背景变暗均需要作为失败现象追查；不能仅凭白羽尚白就通过整幅颜色/光照。此前把变化列作lighting watch不足以接受该候选。新诊断目录 `D:/VideoSi/cache/video-ai/logs/jim-08-svi-color-rejection-20261022/`。先核对原图/缓存/原始PNG/容器显示，再验证所有窗口重复首窗“暖金色”描述是否推动重染；量化基础模型仍是未排除因素，不把FP8视为已证实根因，不用后期减红代替生成修复。

外部补查 [SVI#47](https://github.com/vita-epfl/Stable-Video-Infinity/issues/47#issuecomment-3694243884)：作者说明Pro不兼容原普通工作流；本机此前用Pro专用条件类及原latent，不能把该报告的确切根因直接套用。[SVI#42](https://github.com/vita-epfl/Stable-Video-Infinity/issues/42#issuecomment-3655574000)涉及纯色背景和旧尾帧重编码，当前自然场景/原latent亦不同。继续检查本机实际差异，不盲装社区节点。JIM-08保持IN_PROGRESS，未修复、未集成生产。

## 2026-10-21 颜色失真：外部资料、分量测量与生成阶段引导（历史）

**23:58本轮终态：形成有改善的SVI原样审阅候选，颜色/光照/动态最终接受仍待用户真实播放，未推广生产。** 三窗分别原任务`af25fcb4-38d8-4fa8-a22f-fc2eec70e7b3`、`62c551a1-e5e8-4093-880d-e6898631c6e7`、`0eab4ee4-a14a-4d4f-a09e-7ce8c34ee66c`，各一次POST、全部技术成功；第三窗日志10分40秒。81+76+76=233帧，原生16fps=14.5625秒，两处真实接缝5.0625/9.8125秒，裁除的是各续窗前5个anchor/motion上下文帧，无crossfade/插帧/稳定器/后期调色。三个sample latent均保存、有限，两个后继确切继承前一原sample末latent，不经过RGB/VAE重编码；同一anchor SHA保持。

三窗采样图和两处接缝前后完整PNG中，主体白羽/材质色较旧VACE强异色明显改善；第三窗仍有冷色翼面阴影，背景/水面变暗及天空颜色变化是明确未关闭的lighting watch，不能声称颜色完全忠实或光照稳定。第一/二窗仅内部static_screen_pass，第三窗static_screen_pass_with_lighting_watch；全部motion unverified、human/production false。不能把多个窗口成功或静态较好解释成通用生成已完成，也不能将训练/协议整套替换的效果当作“仅传latent”单变量根因证明。

**完整无损原样副本：** `D:/VideoSi/projects/video-ai/reviews/JIM-08-SVI-Pro-color-continuity-review.mp4`，SHA `3d74ccf06801c1fcc524027230f012139542669dc9ca55ce259db5b3c73f3472`。源为`jim-08-svi-pro-validation-20261021/evaluation-003/raw-window-chain.mp4`，copy SHA相等。逐帧解码RGB严格等于233个原始PNG直接拼接、PTS严格i/16；source MP4有正常有损误差，原始PNG与其误差单独记录。三窗contact、raw最后帧及每处previous-last/first-new、完整CIELAB/对比度/截断统计、graph/cache SHA检查在各evaluation目录；未用统计替代实际观看。

**最终完整审计退出0：** `jim-08-svi-pro-validation-20261021/final-audit.json`、日志 `jim-08-svi-final-integrity-audit-3b7a02188eff4e578041a7e06f4c3473.log`。原3011文件大小/SHA/mtime、378生产基准、所有基础权重/原始及派生LoRA/anchor/node身份保持；三个intent/case/helper/graph/history/client和结果一致，两个raw latent继承边界核验、所有sample latent有限，各高/低模型真实日志均400补丁，8个SVI helper编译通过，自有诊断服务均结束。没有生产源码/workflow修改、没有新裸全库或新human接受；FP8基础/文本的量化限制和跨题材/更长链未验证保留。

已向用户提供确切14.56秒副本并询问完整播放后的颜色/亮度及5.06/9.81秒接缝判断。这是主设计7.3要求的真实动态观察，当前待答，不用预选项/沉默/时间经过充当接受。通用设计已明确模型能力与内容case分离、真实latent缓存身份、终窗丢帧不能回传未保留未来latent；实验3窗预算不设产品时长上限。旧run、已选图、旧接受首片、音频及463帧正式时间轴均未替换，JIM-08保持IN_PROGRESS。

**SVI第二窗完成；第三窗执行中。** 第二窗原任务`62c551a1-e5e8-4093-880d-e6898631c6e7`成功，裁前5上下文后76新增，与首窗组成157帧/16fps=9.8125秒，真实接缝5.0625秒；RGB/PTS与原始PNG严格相等。实际查看两窗采样、前末/后首/末三张完整PNG：接缝主体颜色和曝光接近，后续未见旧VACE大块异色，内部static_screen_pass。**背景/水面随着芦苇占比增加变暗是明确保留的lighting watch项**，尚不能区分构图内容变化与曝光漂移，绝不由静态图登记光照不变/动态通过。第二窗原sample latent SHA `151cb7bbdd0e173538364f0a06abaf2ad4b091a7c61845231f953760e96125d5`。`evaluation-002/technical-audit.json`及visual记录完整，审阅SHA `a2b927cc4b57ddabd759f3f35f3fd05c9673bb91433d0b7b440c5f6cfd3d680a`。

按原最多3窗预算，仅继续最后一窗，继承该原始latent和同一anchor、seed264244520399089，其余profile不变。`case-003.json/window-003/`，运行日志`jim-08-svi-third-window-0b1bbf9f64bc40c68e6a089b6337ef8a.log`；结果尚未核验。即便最后一窗静态无强失真，仍须真实完整播放检查两处接缝/光照与后续跨题材测试，不称通用生产已完成。

**SVI首窗已完成并通过内部静态筛查，第二窗原任务执行中。** 首窗`af25fcb4-38d8-4fa8-a22f-fc2eec70e7b3`日志10分42秒、runner退出0；81真实PNG/16fps=5.0625秒，sample latent `[1,16,21,60,104]`、SHA `b46eff3938abbf1e1a9356fc63b1ac085493b8aafc59c6e0eed01c3d037fbf5f`。原始图及高分辨率末帧白羽/自然阴影和暖环境未见此前强异色，标`static_screen_pass`仅允许继续探针，motion仍unverified，无human/生产接受。背景芦苇进入取景与跟拍相容，不把运动构图变化误算为配对色差。`evaluation-001/technical-audit.json`验证raw graph/输入cache SHA、81帧RGB无损审阅及PTS，副本SHA `86914fd9279b5a870a8961e62c7756c9755f3db9c8c38445bd3cc34eae4da8df`。

第二窗原任务`62c551a1-e5e8-4093-880d-e6898631c6e7`、`window-002/`已受理；输入直接绑定上述sample latent原文件SHA和同一anchor，没有RGB/VAE重编码；seed按协议变为264244520399047，其他profile保持。日志`jim-08-svi-second-window-3a6414f844a74f50abbebf0e0c44364f.log`。尚无第二窗颜色/动作结论，第三窗未提交。当前只证明首窗静态有改善，不称长链或通用已修复；下方“首窗执行中”是此前时点。

**SVI当前真实执行：首窗原任务 `af25fcb4-38d8-4fa8-a22f-fc2eec70e7b3` 已受理，尚无质量结论。** 独立证据根 `D:/VideoSi/cache/video-ai/logs/jim-08-svi-pro-validation-20261021/`，case-001/window-001；运行日志 `jim-08-svi-first-window-bb55569468094719a853afaed5340528.log`。CPU四种条件（320×192/832×480 × 首窗/续窗）实际执行固定KJ条件类及安装WAN21.extra_conds，anchor/原始尾latent/padding/正反/20通道mask数值通过；原生SaveLatent→LoadLatent逐值相等且格式标记存在。真实sigma50步/shift5首次低于0.875在step21（0.873494），冻结高21/低29阶段。

实际LoRA文件是原BF16的800个张量/400层；本机原生loader对原始`blocks.*.lora_A.default.weight`键名匹配0层。仅增加`diffusion_model.`命名空间前缀后，两模型各400层/800张量全部匹配、矩阵形状与实际FP8基础checkpoint一致；派生safetensors在独立`models/jim-08-svi-pro/native/`，逐张量torch.equal通过，不改dtype/值/秩/强度。`resources-001/report.json`绑定原/派生完整SHA、基础模型和anchor。真实参考图一次lanczos/center缩放832×480并编码anchor缓存，原生LoadLatent读回逐值一致；未来续片回收真实sample latent，不再编码尾部RGB。

3项临时SVI图检查RED→GREEN，首窗无previous、续窗必须原latent且不同seed、81帧协议/两阶段连接均核对。最多3窗、当前只交首窗一个intent；每窗原始PNG/sample latent/MP4全保存，静态失败即停，只有静态筛查通过才交后续窗，不伪造human_video接受。首窗使用既有Wan2.2 FP8基底及FP8文本、Pro双LoRA、50步Euler/simple、CFG4/shift5、16fps；没有加LightX2V/调色，量化限制保留。初始81帧全部保留，若后续获准执行则各裁前5上下文为76新增；完全独立于旧接受首片和正式463帧时间轴。

**当前进度：Rescale单因素已失败；转入SVI Pro隔离可行性，正式run保持。** Rescale原任务`16f57007-760e-4144-b75f-f5bdd6cdc703`221.73秒完成、退出0，53原始PNG和采样latent落盘。原始PNG中已存在强局部颜色/材质变化，因此不需依靠H.264画面推断；known配对DeltaE76均值3.06→3.52，平均L偏移−2.30→−3.04，未改善。未来L范围74.14–79.09相对旧71.62–79.58有局部变化，不等于外观忠实；静态appearance/color/lighting failed、motion unverified。20次真实CFG审计表明普通CFG/conditional标准差比1.0036–1.3576，rescale确实生效且有限，但不是充分修复；不扫描其他倍率。

基准分量测量`boundaries-001/report.json`：真实9帧VAE往返DeltaE76均值0.957、L均值差−0.116、chroma差+0.0115；旧DiT已知区域DeltaE76均值3.062、L差−2.295、chroma差+0.838。新增41帧亮度/对比度及局部材质变化更明显，但未来没有逐像素真值，不能由全图统计推出每个局部的因果或动态接受。原始PNG与H.264平均RGB差1.986/255，记录而不冒称有损编码无误差。

`rescale-evaluation-002/` 技术、分量及视觉记录完整；53生成取[9,50)41新增，父+新134帧/16fps=8.375秒，RGB/PTS精确。审阅副本 `D:/VideoSi/projects/video-ai/reviews/JIM-08-color-distortion-rescale-review.mp4`，SHA `daaa58f16fb70ac38b7d7f8d66623c7836d90e67616ccc267295c5228bb71241`。第一版PNG身份核对因Comfy给两个LoadImage增加`is_changed:[输入SHA]`而失败，非推理失败；原失败评估/脚本保留。修正为逐文件核实cache SHA后才去掉该字段，再严格比较整个graph，并以3项真实hash/改CFG拒绝检查验证；新目录评估完成退出0。一次内联Python检查受PowerShell引号处理影响而SyntaxError，转为文件helper后完成，未重交GPU。

Rescale阶段最终完整审计 `final-audit.json`、日志 `jim-08-distortion-final-audit-378ccbe4e1e2455a936b39a53fd52a4a.log`退出0：原3011项大小/SHA/mtime、378生产基准、VACE/VAE完整SHA保持，唯一intent/case/helper/graph/history/client及raw输入cache身份吻合，自有服务结束；13个helper编译通过，无新裸全库/生产接受。此审计只覆盖此前已完成阶段，不把后续下载/新脚本冒充已审计。

**SVI后续调查/资源：** 已读官方Wan2.2分支Pro推理与pipeline，及[官方置顶#51](https://github.com/vita-epfl/Stable-Video-Infinity/issues/51)、原生KJ条件类固定commit `f4bae1f9960e5d643573a2ecf7abd56453a21821`；原生条件类完整提取至`external/svi-kj-condition-class.py`，未安装全插件。示例工作流附件只读HTTP取得200、129222字节、SHA `f39087eb816320c9877e00b5f506d878d742f24431d94c9c289ebbff8f630660`，明确16fps、81帧窗口及anchor/motion latent协议。HF主站metadata超时；HF镜像与官方README指向的ModelScope清单一致，固定2个Pro LoRA各1,226,928,552字节，合计2,453,857,104字节。按用户自行找方案修复/继续排查授权，仅在独立目录`D:/VideoSi/models/jim-08-svi-pro/`执行可逆本地新增；`svi-download-001/result.json`记录两文件完整SHA通过，未下载基础模型或安装包。HF revision/ModelScope各文件revision、SHA和来源详见主设计7.3和`svi-mirrors-001/report.json`；不是生产后端替换许可或正式验收。

下一步先验证native条件类padding/上一段原采样latent继承及LoadLatent版本标记，才允许至多3窗的孤立试验；使用现有Wan2.2 FP8基础权重存在量化限制，作者优先FP16，结果不能泛化到官方全精度方案。当前尚未提交任何SVI GPU任务，不能称SVI已修好或失败；此前“本轮只读/没有新权重”均为前一阶段时点。

用户纠正：“这个应该不是偏蓝的问题，是颜色失真的问题，你按这个思路继续排查解决，可以查外部资料”。本轮将故障定义扩展为色相/色度/饱和度、亮度/对比度/高光截断及细节退化；蓝色只是此前案例的外观表现。不删除旧证据，不用B-R全图均值单独评判失真。证据根 `D:/VideoSi/cache/video-ai/logs/jim-08-color-distortion-20261021/`。

已实际读取并保存外部讨论与源码：

- [VACE官方仓库#44](https://github.com/ali-vilab/VACE/issues/44)，尤其 `3131450260` 对“blurred details, decreased contrast, increased color saturation”的描述；`3124285373` 区分已知区域重建轻微变化与未来外推强退化；`2998440751` 建议分别检查VAE和VACE重建。维护者先怀疑mask，后承认范围更广；多名使用者在正确mask和无损PNG下仍复现。这些是外部报告，不冒称本机精确根因已证实。
- 同讨论中有人用无损输出/FFmpeg loader缓解压缩误差，但另有人在官方独立实现与无损PNG仍复现；本机真实历史RGB与编码边界已有证据，不盲目替换已核验loader。
- [社区SuperUltimateVaceTools](https://github.com/bbaudio-2025/ComfyUI-SuperUltimateVaceTools) README与完整nodes源码已保存，GitHub blob分别`c7db63fd75becdff09b05baa39babca04089bb0f`、`34bad7daedf61ccd1a95d606ea693b3635583af8`。其refine会混白/去饱和/模糊历史控制并可另做colormatch，会改变真实历史与接缝；本轮仅静态阅读，没有安装/执行这份插件或把它冒充根治。
- [Wan2.1#302](https://github.com/Wan-Video/Wan2.1/issues/302)、[Wan2.2#172](https://github.com/Wan-Video/Wan2.2/issues/172)也有末帧链导致模糊、颜色变化的报告；[VACE#93](https://github.com/ali-vilab/VACE/issues/93)包含低shift/高步数个别经验，但没有统一实证修复。不把MPS/Apple Silicon特有损坏直接套到本机CUDA。

测量与下一受控假设：`distortion_metrics.py`实现标准sRGB→D65 CIELAB，报告L、chroma、对比度分位差、截断比例、色相直方图和Laplacian方差。已知历史才能做逐像素配对DeltaE76；未来帧只能作分布诊断，不能忽略运动/构图变化而给出颜色通过。4项颜色标准/曝光与色度分离/红蓝两方向/常量图检查通过，真实VAE与旧FP16输出的已知/未知边界分析执行中。首次绿色检查因嵌入Python不自动加入脚本目录而未导入本地helper，显式补目录后通过，未安装包。

本机原生 `RescaleCFG` 有明确CONST/flow分支，可在采样阶段约束引导的latent幅度，区别于给RGB结果补暖/减蓝。它是“引导是否放大失真”的待检验机制，不预先判CFG为唯一原因。准备相对原FP16+FP8文本20步baseline只加入原生RescaleCFG默认multiplier0.7，不叠加此前BF16文本/50步/新seed；额外只读审计hook与PNG/latent落盘用于定位。两项图检查RED→GREEN已通过；真实原生flow函数的5维CPU检查与审计hook逐值无影响验证须先通过，才提交一个新GPU任务。外部素材、标准色及已有案例通过外部case/graph供给，不在helper内写题材特判。

## 2026-10-21 先查偏蓝：条件数值与文本编码路径（当前）

**22:20结果：偏蓝仍未修复；本轮两个新增GPU任务都未通过外观筛查，不登记生产通过。** 原精度文本路径有局部改善，50步对照仍明显蓝/青；没有将两种未独立通过的方法继续叠加试运气。原生视频保存路径五组真实往返完成，blue-minus-red全图均值差最大约0.154/255，实际灰阶/RGB色条及父末帧未出现同等明显蓝偏。结合此前VAE、输入与条件核对，当前定位为**续写生成过程中的局部外观/光照漂移**，尚无证据锁定某个编码/接线bug或单一参数。也未证明训练先验、具体采样器实现、引导和运动姿态各自的因果贡献；不能宣称所有VACE配置都无效或后端更换必然修好。

50步原任务`04eca9eb-3938-44d7-af86-b01f0b755da0`完成539.30秒，runner退出0；原FP16日志确认、53帧取[9,50)41新增、134帧/16fps审阅RGB和PTS精确。接缝MAE9.76相对20步11.09较小，但后段仍有明显蓝/青羽毛和翼部形态改变，appearance failed、motion unverified。副本 `D:/VideoSi/projects/video-ai/reviews/JIM-08-convergence-review.mp4`，SHA `92d001fe804c4fbd299041b2a84bb4119728758a2f7d1d1e535f7a1c83b78f81`；源证据 `convergence-evaluation-001/technical-audit.json` 和 `visual-screening.json`。不再增80/100步或换seed来冒充排查。

编码路径 `probe_video_color.py` 在CPU执行安装 `CreateVideo` 和 `SaveVideo` 消费的同一 `video.save_to` 写入实现，8bit/sRGB/H.264，与任务保存设置一致；用原色条、三原图、真实历史末帧共5例，不加载VAE/DiT。`video-color-001/report.json` 记录逐例SHA、通道均值和MAE，均值B-R差0.034–0.154/255；H.264有正常有损误差，未宣称逐像素无损或排除所有局部误差/播放器色彩管理。实际查看解码色条及父末帧，未复现生成段的强蓝羽。日志 `jim-08-native-video-color-trace-20b69980049e4606a72014f81bec6f96.log` 退出0。

通用修复约束保留：未来必须解决生成时的外观/环境参考与跨窗时序保持，并用独立题材、镜头意图及多真实续接边界验证；当前没有可推荐为已通过的生产替换件。不得以“全局减蓝/补暖”、冻结所有背景、题材专用提示或把不合格段拼入成片来计完成。FramePack第8节仍为未执行候选，未下载、未变更原生16fps契约。

**22:21最终完整审计退出0：** `final-audit.json` 核对原3011文件大小/SHA/mtime、378生产基准及VACE/VAE完整SHA不变；两个intent对应各自case/helper/graph和原history/client，输出SHA及审阅RGB/PTS证据一致，自有服务均结束，无新human接受。15个诊断Python文件编译通过；无生产改动，不重跑5.5小时全库，也不挪用此前3651通过作为本轮新测试。审计日志 `jim-08-color-trace-final-audit-9c2b4bd7852642a893ec45cdf1a55ec5.log`。最后静态审阅发现采样图拒绝测试同时改变精度与步数，故将其拆成两个独立输入拒绝检查，另行最终回归，不改推理helper/已执行case。

拆分后的最终隔离图检查实际 **2+3=5 tests OK、退出0**，日志 `jim-08-final-isolated-graph-checks-3508c4557d4f4ce8baa6fb9f3946f2fe.log`。这是诊断graph与输入拒绝检查，不是新增生产功能、模型画质通过或生产全库。

最新用户指示“先检查为什么偏蓝，你自己找方案修复吧 做好记录”。继续当前模型内根因排查，暂缓第8节FramePack/原生时基建议；不以未获选择的新后端替代调查。下方21:42及“停止”是上一轮时点，JIM-08仍IN_PROGRESS。

证据根 `D:/VideoSi/cache/video-ai/logs/jim-08-color-trace-20261021/`。

- 实际数值边界：`probe_condition_equivalence.py` 调用真实原生VAE独立编码、安装节点与 `WAN21_Vace.extra_conds`，对照已存官方VACE三个条件函数。`conditions-002/report.json` 中 `[96,15,54,96]` 的reference、inactive/reactive、history/future及mask最大差全0。官方VAE以同一原生VAE+显式标准化适配，不是完整官方pipeline独立一致性证明；没有加载/采样DiT。第一版参考列表维度错误退出1，v1及日志保留；第二版退出0，日志 `jim-08-vace-condition-equivalence-v2-f3cd62e0ca7f466282a3d7f98de1f6da.log`。
- 文本路径：首次逐token前置断言未过，另用轻量 `probe_tokens.py` 确认仅中文逗号356→275（官方ftfy规范化），正/反分别5/27处，长度相同512，没有截断。第二版强制两种编码器使用相同native token，真实输出均有限；正提示139token、cosine0.998466/relative L2 0.05530，反提示126token、cosine0.997547/relative L2 0.06998。`text-002/report.json` 及BF16条件SHA完整保存；原BF16 UMT5使用已有SkyReels权重，无新增下载。实现/计算精度也不同，不仅是存储位数；embedding差异尚不证明蓝偏原因。
- 原BF16文本条件续片对照：保留原FP16 DiT、参考/9真实历史、53生成/41新增、shape/seed/sampler/提示token，只用安装原生 `ConditioningLoader` 加载已有BF16真实输出替代CLIPLoader/两个CLIPTextEncode；无自定义节点/Comfy修改。两项图检查先RED（1failure/1error）后GREEN（2tests、退出0）；原生CPU ConditioningLoader逐值相等预检退出0。准备器首轮导入路径错误退出1，v1/日志保留，显式加入helper路径后退出0。
- 原任务 `1f88f71e-8bdf-4d5c-ba07-17ab691b79fd` 完成，218.43秒、runner退出0；一个intent、一次POST。文本精度/实现路径是唯一实验因素，没有修改DiT/采样参数。53实际帧取[9,50)41新增、父93+新41=134帧/16fps/8.375秒，RGB及PTS相等；BF16比FP8文本的蓝色斑块减轻，接缝MAE11.09→8.50仅作诊断。后段仍有蓝羽、形态变化及环境变亮，`text-evaluation-001/visual-screening.json` 为appearance failed、motion unverified，没有完整播放或human接受。审阅副本 `D:/VideoSi/projects/video-ai/reviews/JIM-08-original-text-review.mp4`，SHA `4b3e50b1cdd004e93d7659505d64fb1bae18fd487d420229cb9776a5661daa6f`。原冻结case中的旧FP8基准不用于本次精度比较，另建只读评估case绑定确切FP16原任务结果，未改推理case/intent。首次评估误选无numpy的编排环境，import阶段退出1，无评估文件；随后用已有Comfy环境完成，未安装包/重发模型请求。
- 收敛假设：安装原生 `simple_scheduler` + flow shift8实测20步末个非零sigma0.296296、低于0.3仅1次；50步为0.140351、低于0.3有2次，详见 `schedule.json`。已存官方VACE推理函数默认50步/shift5/guide5，与旧20步不同；本次不同时改变shift/CFG或冒称安装UniPC等价于官方flow实现。此处大终止间隔只是可检验假设，不是已证实根因。
- 单步数对照从原FP16+FP8文本baseline graph出发，仅 `KSampler.steps:20→50`，保持其余节点/token/参考/9历史/shape/seed等相同，不把BF16文本改进叠加进去。两项图检查RED（1failure/1error）→GREEN（2tests、退出0），`convergence-case-001.json`、`convergence_trial.py`、`test_convergence_graph.py`。唯一原任务 `04eca9eb-3938-44d7-af86-b01f0b755da0` 已受理执行，当前尚无颜色/质量结果。实际生成结束后才跑原生视频保存路径色条/三原图/历史末帧检查；所有Python/媒体/模型任务串行。

## 2026-10-21 继续修复颜色与连续性：原生往返与原精度对照（当前）

**21:42本轮终态：修复未完成，停止当前VACE路线的追加生成；原run/生产字节保持。** 三次GPU分别是原精度、较长历史、无旧父片的初始生成，各一个intent，均技术成功但未通过全部外观要求；没有新增human_video接受或生产交付。完整最终审计`D:/VideoSi/cache/video-ai/logs/jim-08-color-diagnosis-20261021/final-audit.json`退出0：原run3011项大小/SHA/mtime及378项生产基准匹配，原VACE权重34,675,323,640字节完整SHA匹配，VAE SHA `2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b`保持；三个helper/case与intent身份匹配，全部真实运行确认为FP16，三个旧服务已结束。未改生产源码/workflow，不另跑裸全库。最初最终审计因helper只接受Path却收到str而退出1，日志`jim-08-color-repair-final-audit-95e2ad556e9644d0af42d372328eec49.log`保留；仅检查器统一Path后重核，修正日志`jim-08-color-repair-final-audit-corrected-089a1659b1d1487bacc42c122f7d5966.log`退出0，不把检查器错误当作模型失败或隐藏原失败。

初始生成原任务`c394a442-207c-401b-bf1d-3064f74747bc`成功，220.90秒。53帧/16fps=3.3125秒，只有参考图、没有任何旧父视频/历史；trim1后PTS及审阅字节一致。实际查看7格生成采样、参考及高分辨率末帧：白羽蓝偏明显减轻，但湖面/背景持续变亮、出现大片近白高光，稳定曝光要求未通过。`initial-evaluation-001/visual-screening.json`记录appearance failed、lighting failed、motion unverified；不是通用生成已通过，不声称同后端能消除所有漂移。未生成这个首片的任何续片，不要求用户再次接受已筛查失败样片。

审阅副本分别为`D:/VideoSi/projects/video-ai/reviews/JIM-08-precision-repair-review.mp4`（SHA `afdd0bed984a89a90e9b4f67a06f58cee3ee32eb13b90bdcd46aa7691e1c80f7`）、`JIM-08-history-repair-review.mp4`（SHA `066e38846fdb37a2abc1f002fc3161c925553d2819e8acb6aca20ed9c15c1687`）、`JIM-08-initial-repair-review.mp4`（SHA `045afcc1c89a4e554a1df25274f230effe34cb082707c300876f2293acfd44f9`）。前两份为原父+41新增8.375秒无混合对照，第三份是独立首片，不与旧父片拼接。

下一步建议与待选择点已写入主设计第8节：FramePack F1统一首片/跨窗参考历史，允许模型原生30fps并按真实PTS映射到最终16fps；这是对“源片必须原生16fps”的明确设计变化，不能静默实行。建议有限9窗与60GB下载上限、先完整身份/资源准入、失败即停；没有下载/安装/运行F1，精确权重清单仍未核实。用户尚未作出这个后端/时基选择，JIM-08保持IN_PROGRESS，未完成。下方“执行中/尚无完成”均是本轮历史时点。

**21:24较长历史结果：技术成功，接缝静态差异减小，但外观仍未通过。** 原任务`53dc5d76-08b6-4f25-9cb9-c3a3e3458725`成功、300.64秒、runner退出0。69实际帧取[25,66)为41新增，父片+新段仍134帧/16fps=8.375秒，RGB/PTS精确；对照将baseline的[9,50)与本例[25,66)分别取帧，未错位比较。实际采样可见相比短历史蓝偏减轻，但后段仍有蓝色羽毛与翼部/形态变化，不能接受；MAE6.73相对前11.09仅作诊断，不能替代颜色/动态结论。完整接缝动作仍unverified，未登记human_video接受。

此时停止旧Wan2.2父片→VACE2.1的输入组合试验，转为初始生成架构诊断：当前混合后端尚未证明风格/运动兼容，不能因PNG/SHA与帧率正确就默认可互接。一个独立首片探针用同一VACE原FP16、原选图、无历史，H0/N53/G53；提示仅去掉不存在的历史承接语句，当前动作与外观来自外部case。不是原片续作，不拼旧父片或继承旧首片接受；首片静态失败就停止，不执行新续片。

初始图检查先RED **2 failures**（`jim-08-initial-graph-red-e68079c5eaef4f69902e5eba7b388f58.log`）后GREEN **2 tests OK**（`jim-08-initial-graph-green-94ed6f73c44e48f3b06868bd14beef41.log`）；原生CPU覆盖H0无历史、独立reference和trim，最终收据`initial-native-cpu-final.json`、日志`jim-08-initial-native-cpu-final-bacedb88b9a4424293bc9f7ebdb20058.log`退出0。第一次CPU收据给H0沿用“历史已路由”标签不准确，只修报告字段并重跑保存独立final收据；原检查未失败，两份保留，不假装发生模型问题。

初始生成执行日志`jim-08-same-backend-initial-1aa3bf7b388849db9bee9ad3d6a8c082.log`、目录`initial-trial-001/`，当前尚无完成/质量结论。不加新模型下载、不改正式run/原声音字幕；通用后端兼容与跨题材验证仍未完成。下方历史“执行中”均是此前时点。

**21:12原精度结果：技术成功但外观仍失败；已按证据转查历史时域，而非继续调精度。** 原任务`553b2477-c49e-42a2-97b7-d3373523a1bc`，221.00秒；真实日志确认`model weight dtype torch.float16, manual cast: None`，原权重约33,068MB staged，使用原生动态显存，不能把staged数当作整卡常驻显存。runner退出0，53实际帧/41新增、134帧16fps审阅RGB与PTS精确核验。查看FP8/FP16与父片对照，FP16仍有明显蓝/青色羽毛及形态变化，`precision-evaluation-001/visual-screening.json`为appearance failed、motion unverified、human=false；不能把FP8转换视为该失败的充分解释。没有修改CFG/步数、采样器或提示词，也未换模型。

下一项唯一输入对照为历史首末跨度0.5秒→1.5秒，按fps推导25帧，本例取已接受父片真正保留原生索引[68,93)。每帧RGB经ffmpeg APNG往返及安装原生LoadImage全序列核验相等；不是复制/插帧构造运动。新增41帧不变，G53→69以容纳上下文，参考latent仍动态trim1后取[25,66)，丢3尾帧；noise形状随上下文改变，未声称逐元素同噪声。`history-case-001.json`将这些数值作为案例输入，1.5秒不是产品写死窗口或总时长上限。

历史图检查RED **3 failures**（`jim-08-history-graph-red-b239f2559ac2402894b674e1eeccd853.log`）后GREEN **3 tests OK、退出0**（`jim-08-history-graph-green-4c93843240164cb291545931accae3db.log`）。CPU三组H5/H9/H25与两分辨率的参考/历史/trim验证及实际25帧像素核对退出0，收据`history-native-cpu.json`，日志`jim-08-history-native-cpu-781cee097d0d4a3d82354a2a4a47b116.log`；native CPU证明在intent前绑定到case，不把其当成实际画质。

历史原任务`53dc5d76-08b6-4f25-9cb9-c3a3e3458725`已受理并在原FP16、同参考/提示/seed/采样配置下执行。唯一变化为真实历史长度与必要的G预算，证据`history-trial-001/`、日志`jim-08-duration-history-comparison-bc444023dd4444dc8f573ee7d48c5340.log`。当前还没有完成/颜色或动作改善结论；若仍失败，停止此VACE输入组合，不盲加其他参数。下方原精度“尚无完成”是早先时点。

用户明确“那你继续修复吧，颜色也不对”。继续同任务故障排查，更新关联设计Scope与Approach第7节；这句话确认颜色问题及继续修复意图，不推断用户已完整播放、动作合格或接受任何样片。仍以通用生成/续写为目标，不加白鹭/湖面调色分支，不自动下载其他模型。

独立证据根`D:/VideoSi/cache/video-ai/logs/jim-08-color-diagnosis-20261021/`。先执行原生真实VAE encode/decode：通用色条、三张已选原图及9帧真实历史，共五组；没有DiT/扩散或色彩修正。五组报告`roundtrip-002/report.json`，命令日志`jim-08-native-vae-color-roundtrip-corrected-61f1e2f5c1a74104990e2b6824a1f634.log`退出0。实际查看输入/解码对照，未见生成样片那种明显蓝偏；全图均值各通道漂移绝对值最大约0.506/255，不用均值掩盖局部缺陷，也不声称排除了所有编解码误差。

第一次探针退出1，日志`jim-08-native-vae-color-roundtrip-e4cb34f9bbde410c8e87ecdb27184271.log`：脚本直接调用VAE.decode，未处理其5维batch/time输出，形状断言失败，尚未颜色结论。保留`probe_vae_color-v1.py`及失败现场；修正探针为调用安装原生VAEDecode节点的batch/time展开后通过，未改生产VAE或降低颜色断言。CIM系统内存读取被环境拒绝，没有提升权限；改用只读GlobalMemoryStatusEx，记录空闲物理19,562,233,856字节、可用commit11,640,791,040字节；是否足够仍以真实按需加载为准。

据此把下一变量限定为此前FP8加载。精度图检查真实RED **3 failures**（`jim-08-precision-graph-red-6efcea406de64bf6a24ed09a4c8993f0.log`），GREEN **3 tests OK、退出0**（`jim-08-precision-graph-green-f56fab53326641ae933e1a6e01f5c0f1.log`）。真实graph前置diff只有UNETLoader的weight_dtype改变，reference/history/trim、提示、seed、sampler及latent形状/预算保持；源checkpoint header全部F16。Comfy原生加载支持meta/lazy、mmap和DynamicVRAM，未覆盖包或自造传输。

唯一原精度对照已启动，日志`jim-08-original-fp16-comparison-35aeecb42dfc4233b2dbd13a470c82b3.log`，输出目录`precision-trial-001/`。必须由原生运行日志确认FP16，不能凭default参数先计通过；当前还没有实际完成/颜色改善/动作结论，也不预设FP8是根因。若资源不足或仍失败就保留并停止该对照，不退回量化或同时改参数。

## 2026-10-21 通用连续性方案修订与独立参考对照（当前）

**最新结果：技术完成，独立原图参考仍未通过外观准入；本轮停止，不推广生产。** 唯一GPU原任务`6f395e46-c206-4730-9a79-024640a17ce6`成功，Comfy记录217.84秒，runner退出0；结束后只终止自有服务，Windows terminate返回1与模型任务成功/runner退出0分别保留。没有第二次GPU提交。

实际输出在`trial-001/output/scene3_vace_firstclip_trial_00001_.mp4`，SHA `48576e8edbe587446d5d915cbe598f972c935fb99337562f1f58da2321c48e97`。参考增加的1个latent由原生动态trim去除后，实际解码53帧；取[9,50)得到41新增帧、丢3尾帧。父93+新增41构成134帧/16fps=8.375秒对照，5.8125秒处进入新增内容；无混合/插帧/变速/防抖。lossless RGB逐帧和PTS与父片原解码像素+新段精确相同，technical-audit收据位于`evaluation-001/technical-audit.json`。

审阅副本`D:/VideoSi/projects/video-ai/reviews/JIM-08-reference-history-regression.mp4`，SHA `bd56becd134e4b368217f11d1819f25b27b8f1ffa0d000b56abc1a17e19693e7`。实际查看四行采样对照、原父末帧和新末帧：新段仍出现明显蓝/青色羽毛及头颈/翼部外观变化，相对已接受父片不合格。`evaluation-001/visual-screening.json`以agent_image记录appearance failed、motion unverified、human_video=false；未完整播放，不要求用户再次接受已筛查失败结果，不把MAE改变量当成质量结论。这只否定本次配置，不外推所有参考控制方法无效。

最终隔离检查**4 tests OK，退出0**（含已有输出目录在构造网络客户端前拒绝，未再运行真实helper），日志`jim-08-generic-reference-final-check-97c2b445b5f540d19fa8b0d81cb44ae3.log`。`final-audit.json`退出0：原run3011项大小/SHA/mtime、378生产基准全部匹配；原VACE采样/正反提示逐节点保留，仅有参考和必要trim接线；34,675,323,640字节权重完整重SHA匹配；唯一intent/POST与副本身份核验。生产源码/workflow未变，不另跑裸全库，也不把前置3651 pytest记成本轮新结果。

通用条件分工和CPU路由/预算验证成立，不代表通用画质已通过；当前固定参考+历史的这次真实组合仍失败，人物/产品/非人主体的跨镜头与长链质量均未验证。后续不能为这个例子写色彩特判、锁死所有背景或复用已接受首片结论；须继续以通用能力和真实对照评价其他架构。JIM-08保持IN_PROGRESS、未交付/发布。下列“采样中”等为本轮早先时点。

用户明确“把这些调整一下在方案中试试，还有切记你要做通用的视频生成方案，而不是针对某一个视频完成工作”。已更新JIM-08关联设计的Scope/Approach/Tests：固定外观参考与真实运动历史分开、镜头意图区分locked/tracking/authored、能力按模型准入，不照搬通用motion/CFG/帧数/IPAdapter参数；主体/场景/文案/色调/源路径来自案例，不能进入通用分支。正式跨题材、镜头和长链验证列为独立门槛，单个白鹭对照不能证明通用质量。

本轮隔离目录`D:/VideoSi/cache/video-ai/logs/jim-08-generic-continuity-20261021/`，没有生产源码/workflow改动。临时`reference_trial.py`从外部manifest和baseline graph增加原生参考与动态trim，保留原采样参数/提示/真实历史。图连接三项RED：**3 failures**，日志`jim-08-generic-reference-red-4e83a66146c84f648d6428e931f5649c.log`；GREEN **3 tests OK，退出0**，日志`jim-08-generic-reference-green-01fce94d24aa4ded99e898f48ee1cebb.log`。不计入生产3651 pytest。

原生CPU检查两个案例：320×192、H5/N7/G13，以及768×432、H9/N41/G53；正反条件均有独立参考/历史，参考增加1 latent且由TrimVideoLatent精确去掉，剩余分别4/14个latent，预算13/53帧。首次`torch.equal`要求减/加0.5的float32算术逐值相等而失败，原日志`jim-08-generic-native-reference-cpu-220010dccf4b4e29a2dde67bb75b93c9.log`保留；仅检查器使用1e-7绝对容差，输入文件SHA仍逐字节核验。修正后退出0，日志`jim-08-generic-native-reference-cpu-corrected-ecde0fec912e4102a6685b6a434b4219.log`，收据`native-cpu.json`。这是替身VAE的原生路由/shape验证，没有模型采样或视觉质量接受。

唯一GPU对照使用此前失败例的同模型原SHA、FP8加载、20步/CFG6/uni_pc/simple/shift8/seed及原正反提示；参考选图SHA `d29e1f201a58691c97eb221ff1c5bb5d675c7a0442c436d7fff8b3bb8fb5e94f`，9帧历史SHA及五项父片/选图记录独立核验。增加参考会按原生接口增加一个latent维度，所需噪声张量形状因此改变；相同seed不表示未知区逐元素噪声与旧例相同，不作这种额外等价声明。原任务`6f395e46-c206-4730-9a79-024640a17ce6`已受理并采样，日志`jim-08-generic-reference-gpu-f6c07ca840964d32a62cae51bb47c48b.log`。只有这一intent，不自动第二次POST。当前尚无实际输出/静态筛查/完整动态结论，不得重新执行已有trial目录。

此前FramePack待选择、未授权新增VACE等描述为历史时点；本次新增授权只覆盖上述条件组合探针，不覆盖FramePack/其他模型、云视频、反复换参数、生产模型迁移或正式发布。

## 2026-10-21 按同任务交接恢复，下一探针待选择（历史）

用户明确“按 JIM-08 交接继续。”。全文读取关联设计/交接后，在任务板记录`PAUSED -> IN_PROGRESS`并保留原交接路径。恢复不扩大原试验授权；本轮仅只读核对和下一次探针准备，没有新模型下载、安装、推理、媒体生成、CLI推进或pytest。

新审计`D:/VideoSi/cache/video-ai/logs/jim-08-resume-readonly-audit-cefff00c56f747e4a22314ea395647f5.json`退出0：原run3011项大小/SHA/mtime、378项生产基准和SkyReels审阅副本身份匹配；六个技术clip记录、三个首片动态接受、无SkyReels第二窗intent。再次实际查看SkyReels采样图，保留后段外观/光照漂移失败，动作仍unverified，不登记新的human_video结论或全库通过。

已在[JIM-08长场景调研](JIM-08-industry-continuity-research.md#2026-10-21-恢复审查与下一次验证建议)整理一次FramePack F1探针：从scene3已选图重做，最多9个真实前向窗口、预计约10.8333秒、研究原生30fps；持续固定首图/分层历史，逐窗筛查，保存未混合轨检查接缝，失败即停。它不继承旧首片接受，不改变正式16fps要求，也不证明任意长场景。需用户选择这项新增模型试验后才安装/推理。

只读HF模型元数据请求三仓库均超时，证据`D:/VideoSi/cache/video-ai/logs/jim-08-framepack-resume-research-20261021/metadata-receipt.json`；不可变权重清单/精确下载量和本机峰值仍待准入，不冒称下载准备完成。已核对F1现有源码快照，并通过GitHub读取尺寸桶/依赖清单。当前JIM-08为IN_PROGRESS、未完成；下面PAUSED及各阶段“当前”均为历史时点。

## 2026-10-21 暂停并交接下一会话（历史）

用户明确“现在还剩什么工作，交接给下一个任务吧”。已保存旧交接原字节快照并刷新`docs/task-handoffs/JIM-08-handoff.md`，随后将任务板JIM-08由IN_PROGRESS转为PAUSED。尚未满足COMPLETED，不新建后继任务。原三场景续片问题未解决，VACE与SkyReels首窗均未通过外观准入；后续仍需连续性方案/修复、真实三场景及多片动态验收、超分与完整旁白字幕合成、最终观察、显式发布及无重复副作用核验。

本次仅整理交接与状态，没有新增测试、下载或推理；引用既有3651 passed及18:41模型/原run/生产身份审计，不登记新全库或模型通过。现有自有下载/推理均已结束，未跑第二窗。下一会话先只读核对交接与最新证据、形成具体下一方案，不自动重跑失败试验或推进原链。下方IN_PROGRESS和运行中均为历史时点，当前状态以任务板PAUSED为准。

## 2026-10-21 SkyReels-V3首窗已实测，外观未通过（当前）

**本机可运行，但本轮外观一致性未通过，第二窗未执行。** 18:37:19第一窗正常完成，157生成帧减25历史帧，得到132帧/24fps=5.5秒新增；本窗含编码/核验632.52秒。8步CPU mmap指针全部恢复，CUDA分配峰值8.48GB、保留12.07GB，外部整卡约13.6GB。不能用显存适配通过代替连续性通过。

已实际查看12格采样、原父末帧和新增末帧：新首帧接近原片；后续暖金色树林/湖面光照逐渐减弱，新增末帧背景灰绿、羽毛阴影偏冷。以agent_image记录采样外观失败，未伪造整段播放或human_video接受，动作连续性仍未验证。按约定在第一窗停止，没有第二窗intent、换seed、参数重试或自动改用其他模型。该结果仅针对本次768×432/BF16/SDPA样片，不外推该模型全部配置。

可播放副本`D:/VideoSi/projects/video-ai/reviews/JIM-08-skyreels-v3-first-window.mp4`，205帧/24fps=8.541667秒，3.041667秒开始新生成；SHA256 `8a93779ffd1b1282c48853a4c2331da99041873376977f47ce6d6def98463c3f`。逐帧RGB/PTS与历史数组+真实新增数组一致；历史时基适配明确登记，不是原生16fps正式产物。最终审计18:41重算全部10模型文件SHA、17固定代码Git blob，原run3011文件字节/mtime及生产378基准身份不变，审阅副本字节一致，推理进程已退出。全部结果在`jim-08-skyreels-v3-validation-20261021/final-audit.json`及关联technical/visual-screening记录。没有生产源码/工作流修改或新裸全库，不把既有3651结果登记为本轮模型通过。JIM-08继续IN_PROGRESS；原动态续接问题尚未解决。以下运行中状态均为历史记录。

## 2026-10-21 SkyReels-V3启动与加载适配（历史）

18:26:38使用显式只读映射的第一窗已进入真实推理，首步54.82秒完成，所有CPU权重指针恢复，CUDA分配峰值约8.43GB/保留约12.07GB。此前两次停在生成intent之前的加载尝试没有运行去噪：补faulthandler后捕获`safetensors.get_tensor`经`torch/storage.py __getitem__`的Windows access violation，已保留栈并终止确切自有进程。改用Python显式ACCESS_READ文件映射和BF16 tensor视图，另做真实RED/GREEN及与按块传输组合的GPU对照，非零输出误差0、指针恢复、checkpoint字节不变；没有更改权重精度或采样参数。该改动只限隔离helper，不是生产修复。第一窗intent已存在，后续不能自动重跑本窗。

17:18:22所需10文件下载全部完成，40,468,106,151字节逐文件SHA256匹配，收据`model-download-receipt.json`。18:19原父片输入准备已通过，原run3011项及生产378项身份核对；按原mapping取`generated.mp4`的实际保留原生帧，尾帧逐像素等于已存PNG。最初探针从重编码`source.mp4`取RGB时与原生PNG不相同（MAE0.7557），因而在任何生成前拒绝；分别解码证实generated与PNG误差0，修正为原生成帧映射，源片及旧记录未改。历史24Hz取样最大PTS偏差1/48秒，lossless副本逐帧/PTS通过，所有适配均单独记账。

官方BF16 T5文本编码随后完成，完整prompt少于512token、context绑定与输出落盘；编码进程退出后启动第一窗推理。真实14B样片仍在执行，尚无连续性或动态通过；第一窗结果出来后先检查明显外观漂移，再决定是否执行授权范围内第二窗。

用户明确“那就先验证第一个方案吧”，继续[SkyReels-V3隔离验证](JIM-08-skyreels-v3-validation.md)。已固定官方源代码与V2V14B权重身份，HF/ModelScope LFS大小及SHA交叉匹配，所需约40.468GB文件正在下载；不下载多镜头权重或其他方案。独立依赖目录已准备，Comfy环境包未覆盖。

真实meta参数计数为14,288,491,584；官方默认FP32初始化约57.154GB，高于本机内存。隔离meta/mmap/按块传输方案保留官方BF16数值；小型真实Wan GPU探针先RED证实原offload返CPU会丢失原存储，GREEN全部指针恢复，非零输出与原生路径误差0，重复执行相同。该探针不证明14B实测、内存峰值或连续性通过。计划按真实PTS适配24fps研究历史，保持原768×432；最多两个5秒续写窗口，先一窗检查明显漂移，不自动追加试验。原正式16fps、多片续接验收及原run保留。

证据目录`D:/VideoSi/cache/video-ai/logs/jim-08-skyreels-v3-validation-20261021/`，源代码、模型元数据、RED/GREEN及隔离helper均在此。原直接源码网络抓取超时、初次import缺wcwidth已如实保留并分别改固定GitHub读取/补独立依赖。当前尚无新视频或动态接受，JIM-08为IN_PROGRESS；下方“未批准执行”为此前调研时点。

## 2026-10-21 长场景业界方案调研（历史）

用户授权调研业界长场景方案。已完成[JIM-08长场景连续生成方案调研](JIM-08-industry-continuity-research.md)，对照官方论文、README及实际推理实现，区分视频续写、历史上下文压缩、因果KV缓存与长期身份检索。建议先评估SkyReels-V3专用续写的资源与时基准入，FramePack作为从已选图重做长镜头的备选；LongLive/MemFlow作为长期架构参考，未宣称解决连续性。

实际代码确认SkyReels-V3每轮以25帧视频历史作干净条件，按最多5秒一轮续写，但没有长期KV或独立原选图输入；读取器不处理源PTS，输出24fps，不能直接接现有16fps父片作公平试验。FramePack官方路径从图片开始、输出30fps，F1还在CPU积累历史并对解码重叠做混合。两者24GB显存/32GB RAM本机峰值未实测，不自动下载或安装。Self Forcing官方测试组合为24GB显卡/Linux/64GB RAM，MemFlow为80GB卡，MemRoPE为单卡40GB或两卡24GB，不能把论文实时速度外推本机。

商业候选Seedance2.5已取到官方完整Markdown，确认独立extend任务、24–60fps及最小407,696像素输入门槛；旧父片16fps、331,776像素不符合，现有即梦图片凭证也不证明方舟视频API权限。Veo/Luma所查延长接口限制自身生成片；Veo3.1 Gemini预览另有2026-10-22关闭提示。资料快照、Git blob身份和官方Markdown SHA收据位于`D:/VideoSi/cache/video-ai/logs/jim-08-industry-continuity-research-20261021/`。

本轮仅研究与任务文档更新，没有新增模型权重、依赖或推理，没有改生产代码、工作流、原run或原验收；未重跑全库，不把既有3651通过说成本轮验证。原多片续接及原生16fps要求保留，JIM-08继续IN_PROGRESS。后续小样设计、停止条件及帧率边界见报告，未批准执行。

## 2026-10-21 长场景要求补入架构讨论（历史）

用户追问“一个场景很长怎么办？”，未批准整段生成或改变原验收目标。已修正`JIM-08-whole-scene-proposal.md`：整段方案仅保留为短场景候选，不能作为支持任意场景时长的通用修复。长镜头需要验证受控时间窗口、实际运动/模型状态、固定外观/环境参考及重叠区域约束；现有独立I2V及VACE试验未证明此能力，不能只改称“滑窗”就计通过。允许语义切镜是另一种产品选择，不等同于一镜到底。未执行新的模型调用、未改原多片续接验收或生产代码，JIM-08继续IN_PROGRESS。

## 2026-10-21 VACE试验被用户拒绝，整段方案讨论（历史）

用户明确“画面确实变了，有问题”，绑定唯一VACE对照及SHA的原话记录为`jim-08-vace-scene3-user-rejection-20261021.json`。VACE画面一致性判失败；未扩写其具体故障帧/完整观看范围或动作结论。该方向不推广生产，不增加VACE提交。以下等待观看为历史状态。

再核对实际graph/原生节点，新增区域的mask全白，主体和背景均是重新生成区域，过去9帧仅为条件；没有未来画面像素的硬保留，也未单独输入reference_image。已知上下文重建接近并不等于新增部分外观保留；FP8/20步/参考输入的独立影响尚未隔离，不承诺调一项就修好。

只读准备`JIM-08-whole-scene-proposal.md`及`D:/VideoSi/cache/video-ai/logs/jim-08-whole-scene-proposal-20261021/proposal.json`。按实际冻结scene-plan和现有_wan_frames推导3份待提交graph：221/113/137生成帧，保留219/110/134帧，合计463帧/28.9375秒。用原Wan2.2和已选图，先scene3整段验证；不继承旧首片的接受观察。准备脚本退出0，原3011文件字节/mtime不变，未调用模型，未改生产代码。明确要把原“独立多片续接”验收改为“整段长镜头一致性”，已向用户请求这个架构/验收选择，未擅自改原Acceptance或提交试验。

## 2026-10-21 VACE单段试验（历史）

**14:12试验技术完成，等待真实完整播放；未判定连续性修复通过。** 唯一prompt_id `fa61d214-ea3b-491a-b4ff-5008d70a07b5`，原生WAN21_Vace按记录的FP8存储/FP16转换运行，20步完成，Comfy记录200.59秒。runner及评估均退出0，原3011文件字节/mtime不变，自有服务已停止。

完整53帧生成，保留[9,50)的41新增帧，接原父93帧形成134帧/16fps/8.375秒对照，接缝5.8125秒；stream-copy后的每个decoded framemd5与父片+新源片一致。副本`jim-08-vace-scene3-evaluation-20261021/scene3-parent-and-vace-continuation.mp4`，SHA `589d66a0cb0a5e487836b64db8ee1260076ec8dc80633457eaffce992c2e645c`。观察请求`jim-08-vace-scene3-trial-review-request-20261021.json`，未伪造human_video或外推到其他场景。

实际采样仍有羽色偏蓝及翼尖颜色变化；新片较旧片留住主体，但动作连续性必须完整播放。接缝MAE10.45、旧9.17只是定位数据，不能据此认定通过或替代观看。已读上游wan/vace.py，mask的nearest-exact行为与安装节点一致，不虚构本机掩码bug。最终独立静态审计`jim-08-vace-scene3-trial-final-audit-20261021.json`核对378基准身份仍全部一致、原3011文件不变和完整对照帧序列。未改生产代码/测试/workflow，未再次全库、不冒充新的3651通过；以下启动及下载状态均为历史记录。

**14:07:15权重下载完成且完整SHA256通过；14:08:09原生CPU条件探针通过，现已启动唯一scene3 GPU试验。** 下载耗时约26分钟，目标34,675,323,640字节完整匹配`f202a5c59b8a91ada1862c46a038214f1f7f216c61ec8350d25f69b919da4307`，安装收据`jim-08-vace-model-download-receipt-20261021.json`，未改默认生产配置。原始进度保留为同日志目录`jim-08-vace-download-progress-*.txt`。

CPU实际LoadImage读取9帧；逐帧比较父generated原生帧[84,93)的全部RGB像素与输入APNG，9帧顺序/像素全部相同，同时绑定父clip/mapping/last-frame/原接受观察的SHA。实际执行原生WanVaceToVideo验证已知9帧及未来44帧mask补齐、VACE特征[1,32,14,54,96]及mask[1,64,14,54,96]。该53帧长度的原生nearest-exact压缩实际产生2个完全已知latent位置，不能套用旧I2V的3个位置假设。CPU替身VAE未加载模型或采样，不能作为视觉通过。证据`jim-08-vace-native-prefix-cpu-audit-20261021.json`。

首次CPU脚本退出1：安装ffmpeg已移除-vsync选项，发生在提取原生帧阶段，尚未GPU提交；保留脚本v1与失败输出，仅运行目录helper改为-fps_mode passthrough，校正后退出0。未改生产代码、测试、workflow或原媒体。

唯一GPU runner已启动：`jim-08-vace-scene3-approved-trial-acd3046ac6344e699a9fcba5aff5dbc7.log`，独立目录`jim-08-vace-scene3-trial-20261021/`。参数为官方示例20steps/CFG6/uni_pc/simple/shift8，源fp16权重由原生UNETLoader按FP8加载；768×432/53生成帧/16fps，保留[9,50)的41个新增帧，seed264244520399005。下载/CPU通过不证明模型推理、接缝或完整动态观看通过；以下下载中为历史记录。

用户已针对连续性修复方案明确“同意”，授权记录`jim-08-vace-trial-user-approval-20261021.json`。本次只下载/核验VACE14B并隔离验证scene3，尚未修改生产源码、测试、workflow或旧冻结run，也不把未来试验输出算作已接受。

已实际核对ComfyUI官方示例所指`wan2.1_vace_14B_fp16.safetensors`：34,675,323,640字节，SHA256 `f202a5c59b8a91ada1862c46a038214f1f7f216c61ec8350d25f69b919da4307`；HF镜像固定revision与ModelScope同仓库固定revision的LFS大小/SHA一致。ModelScope实际Range206成功，13:41启动单连接可恢复下载，完整SHA通过前仅保留自有partial，尚未加载/推理。原HF直连超时、镜像blobs查询403及PowerShell TLS错误均保留，换为可访问的固定版本传输不改变目标权重内容。

已通过GitHub只读连接取得官方ComfyUI VACE workflow文本，准备20steps/CFG6/uni_pc/simple/shift8及明确的原生FP8加载配置；不预设内存可行或视觉效果。CPU实际原生9帧/逐帧mask条件探针和单次GPU提交均待下载结束后串行执行。先前“待选择”是历史状态，此次授权不再重复询问。

## 2026-10-21 14B升级续作（当前）

**当前：用户拒绝三个续片的连续性，已停止推进，正在深度诊断及隔离对照。** 用户原话“场景1 2 3都有问题，不连续，深度分析一下问题再解决”，记录`jim-08-user-continuity-rejection-eb1b0232b4264af1b13f0a38886559b0.json`，不捏造其具体故障帧或新确认的完整观看范围。三个clip_0002原本未准入，继续保持未接受；不提交最后scene1 clip3、不合成/发布。三个已接受首片及全部原运行证据保留。

完整诊断见`docs/task-designs/JIM-08-continuity-diagnosis.md`。已执行：三组接缝采样图和低层像素差；逐帧MD5一致的原样连续播放副本；原run3011文件字节/mtime未变；本机native LoadImage真实读取9帧APNG及WanImageToVideo CPU编码/mask探针。事实是旧末帧传递正确，但每次只有单帧条件、重复完整动作起点提示、无速度/翼拍时序；scene3采样出现明显羽色/曝光改变。探针只证明接口能力，不证明视觉修复。

同原模型/seed/45生成帧执行scene3两次隔离对照，输出在`jim-08-continuity-experiment-4d0937faf06c43ca95fad6f0c7a72d39/`，不接入生产或伪称已接受。A原任务已成功；诊断helper误用canonical_digest比较Comfy将fps=16规范化为16.0的历史而退出1。单独审计确认唯一差异为该数值类型，既有生产_same_history_graph正常接受；修正仅运行目录helper，原失败/代码v1保留，A从本地原终态恢复、未重新POST。一次helper复用旧stdout文件准备错误也保留，发生在启动/提交前。A/B均已完成且服务已停止，仍未证明修复：接缝首个新增帧MAE旧9.17/A14.42/B10.77，A色调恶化、B仍有接缝明暗变化；两次各仅36个新增帧，不是生产替换。评估在jim-08-continuity-probe-evaluation-6800e8f7d08e401f89972141dee943b1。C1采样出现噪声，随后原生CPU Euler/flow复现定位到高低阶段交界残余噪声污染已知前缀；只校正该交界的C2已完成并消除历史噪声，但新增接缝MAE11.28及采样图仍未证明改善；所有服务已停，不推广生产，下一步应审视续写架构，不修改已安装ComfyUI或生产workflow。原生产源码/测试未变，3651全库仍仅说明当前旧逻辑技术契约通过，不能代表真实连续性合格。

**修复方向待选择：** 已准备`docs/task-designs/JIM-08-continuity-repair-proposal.md`，建议新增Wan2.1 VACE 14B，仅隔离验证scene3视频续写；官方UserGuide明确支持firstclip续写，ComfyUI官方示例给出具体权重，尚未下载。HuggingFace元数据请求超时，未核实确切大小/下载可用性；本机24GB VRAM/32GB RAM加载可行性待实测。已向用户呈现该具体步骤，因为原设计禁止自动换模型，等本次明确选择。即梦4.0、Qwen3 14B和原片保持。原生产378项身份仍与全库前置一致，最新只读核对日志jim-08-continuity-diagnostic-source-identity-20261021.json；原run3011文件不变，未有生产修复通过或新动态验收。

**第二轮真实续片已完成，当前6/7技术完成、3/7已动态接受。** 11:53:18–12:07:16 +08原CLI实际退出3 awaiting_continuity_review/error=null，三个scene各自clip_0002已出；模板明确要求完整观看本段和原父片。各子片input使用父片最后实际保留原生帧的PNG字节，独立审计逐一核对父末帧SHA=子input.source SHA=子start.png SHA，rule=identity_png_copy_v1；mapping均丢生成首帧、保留原生16fps。generated/source/子末帧/父末帧/子start全部大小与SHA通过，三个父observation-accepted存在，三个新模板仍unverified且review_method=null。证据`jim-08-real-wan-second-clips-b1776b2b1b674560a8045e443c552d76`及同前缀-gate-audit.json。最后scene1 clip3尚未生成，不外推首轮观看结论。等待用户按“父片→本次续片”完整播放、比较所选基准并确认衔接/外观/风格/动作/首尾后，才能继续剩余末段及合成。

用户针对三个确切首片source.mp4及完整播放/对照选图/外观背景风格/动作变形跳变/首尾检查的提问回复**“三段都看完，正常”**。11:50后保留原话和上下文，记录`jim-08-user-first-clips-confirmation-0025fed51099413e8d2ebd47005a48ac.json`，三份human_video观察从原模板复制、全部媒体/身份/playback范围原样，原模板不改；描述仅如实转录用户确认，未捏造具体动作细节。viewed_at取本轮收到确认并记录的时刻。

11:51:03–11:52:37三次原CLI消费分别确认scene1/2/3首片观察，实际退出2 blocked/error=null：每个首片均进入accepted_clip_ids，下一片pending，此为消费专用入口的正常等待，不是生成失败。日志分别`jim-08-real-review-scene1-first-837b163584f0450999718d039a954ce3`、`jim-08-real-review-scene2-first-dc2436bf1c6c42adac17d49548e1c79e`、`jim-08-real-review-scene3-first-7614674cc0de428f8e34a213469b238c`。三个observation-accepted.json已落盘，普通同run续作现进入第二轮续片；只从各父片最后实际保留的原生帧续接，不把本轮确认外推到尚未生成的续片或最终影片。任务IN_PROGRESS；以下“0动态接受”是历史快照。

**真实首批Wan已完成，当前awaiting_continuity_review。** 仅补本run服务目录后，同run普通CLI10:49:25–11:15:25 +08实际退出3/error=null，三个scene首片各完成1段，均93帧/16fps=5.8125秒；原已规划7片中目前3片完成、0片动态观察接受，续片未提交。原接受任务/graph/输出、裁片、原生保留末帧、mapping和观察模板均落盘。各source SHA：scene1 `8dade91d874cda83af1a8c9e126452d1c4f7746abe9e5ee8153d0db33716db6d`，scene2 `da461a123a94344fe51ce8549b9024d347b080507f19a3ed3553a17c9973fc08`，scene3 `fb0d55e89f22fcf96a99ef55ba7433f40d7d41092eac025183d0c1101cab7639`。原公共CLI日志`jim-08-real-wan-prepared-directories-44f65e85735445dea080d2b12af2865a`，独立静态字节门槛审计同前缀`-gate-audit.json`验证三段generated/source/原生末帧大小与SHA、模板仍unverified且review_method=null；不把技术成功或静帧当动态通过。

已向用户提供第一段完整播放问题，同时继续独立scene生成；当前三个完整source.mp4均可提供用户连续观看。现有工具无连续视频观看能力，因此只登记真实human_video回复，不伪造agent_video。三个观察模板位于对应`production/scene-clips/<scene>_clip_0001/observation-template.json`，尚未提交观察。运行目录另准备`jim-08-invoke-reviewed-resume.ps1`支持原CLI clip/final/publish选项，原wrapper保留不改，凭证仍只在进程内；无生产/测试源码变更，不需重跑既有全库。任务IN_PROGRESS；等待动态观察后继续其余4片和最终合成/观看/发布。

真实Wan首次续作10:46:42–10:47:50退出1，三个scene均ServiceStartError/服务退出2。三份实际Comfy stderr一致明确：`--user-directory`指定的本run `comfy/user`不存在，argparse退出，未到HTTP服务/生成提交。已核查三个clip目录均无intent/accepted/submission，不把启动失败写成模型失败或未知提交。按现有bootstrap的受控D盘路径创建本run `comfy/input/output/temp/user`目录，未改生产源码、配置、冻结模型/graph或旧证据；原CLI同run继续。此为运行目录准备，无生产/测试代码变更，现有3651项全库及378源身份仍适用；以下“正在执行首片”按当时记录保留。

10:44后用户回复“风格一致，收到了”，确认所选图风格及QQ选图邮件收信。原话与提问上下文保存`jim-08-user-image-confirmation-71f6023e6791411d9767c44a3a6cb860.json`，未扩写为每个附件字节或两次投递均已人工核对。随后实际查看三张所选原图，主体均为白羽/黄喙/深色长腿白鹭，湖面芦苇、晨雾与暖色写实风格一致，动作依次站立、展翅、平飞。以**agent_image/Codex**记录实际原图查看，保留用户原话，不假冒人类主体检查；`user-selection-with-whole-group-review.json`精确覆盖三张SHA。原CLI10:45:37–10:46:04退出0 image_batch_accepted/all_images_accepted=true，证据`jim-08-real-accept-image-group-6400df9356964471a835cc0c5b406362`，已产生complete-acceptance。普通同run续作现进入真实Wan首片生成；尚无动态观看通过或成片接受，以下等待整组/收信为历史状态。

10:41:25–10:41:41 +08，用户明确“场景2选第二张”，与已明确的场景3第2张一起写入原模板`user-selection-scene2-2-scene3-2.json`，intent=accept、observation=null。scene2 SHA `e6fd702191c50d58200c63dd5942c63f25aeca208b3df19c4bdea634a0b4492f`，scene3 SHA `d29e1f201a58691c97eb221ff1c5bb5d675c7a0442c436d7fff8b3bb8fb5e94f`；原CLI已写入第二批accepted.json，两个精确选择与原提交副本SHA均核验一致。CLI实际退出3 awaiting_image_selection/error=null，all_images_accepted=false，原因是整组观察尚未提供；无complete-acceptance。日志`jim-08-real-accept-scene2-2-scene3-2-aadf31d6ab174bbc8d92cf49e5f83388`。所有场景选图已明确；仅整组主体/风格观察和QQ实际收信仍待用户事实，未启动Wan。下方场景2待选为历史快照。

10:39:11–10:39:19 +08，用户先指定场景3，经明确两张位置后回复“选择2”，确认为scene_0003/request_02_image_01，原图SHA `d29e1f201a58691c97eb221ff1c5bb5d675c7a0442c436d7fff8b3bb8fb5e94f`。从原第二批模板保存`user-selection-scene3-candidate2-draft.json`，intent=draft、仅此scene、observation=null，经原公共CLI消费，实际退出3 awaiting_image_selection/error=null，原提交副本字节摘要核验一致。日志`jim-08-real-draft-scene3-candidate2-7cf89228b397403eaa741bd869cd20f8`。scene2仍缺选择，整组观察和实际QQ收信仍未确认；此次不是整批接受，不启动Wan、不补邮件。下方“两个选择均待答”为历史快照。

**最终当前版本裸全库已完成：3651 passed in20068.38s（5:34:28），pytest退出0，04:21:27–09:55:56 +08。** 前缀`jim-08-grounding-full-regression-a1596fa456d04178b7cbbed7197dd9cc`；完整逐例输出`-pytest.txt`，前后378项源码/测试/workflows/使用说明身份完全一致。09:56:51独立Python审计原输出SHA、3651个唯一节点、零非通过/零重复、前后清单以及当前378项实际字节，全部通过，原配置与v3全文SHA也一致；`jim-08-root-final-full-audit-3605d610b6474dfb8cbfb8cbab6c9730-audit.json`。此结论仅为替身与真实媒体验证，不代表真实Wan、实际观看或交付通过。

验证外壳有独立统计错误，原失败如实保留：PowerShell对OrderedDictionary使用`Group-Object node`把全部记录归成空名称组，导致pytest退出0、全部3651通过、source_changed=false之后外壳仍退出1。未改生产/测试源文件或原结果，独立解析日志确认3651唯一节点；仅将运行目录脚本改为显式`Group-Object { $_.node }`。原完整3651行重建OrderedDictionary复现误报，并确认修正后3651组/零重复，证据`a1596fa4...-runner-grouping-audit.json`。不把外壳退出1冒充0，也不因此重跑未变化的生产源码全库。

**当前仍为IN_PROGRESS，等待真实第二批选择/整组一致性/QQ实际收信事实。** 尚无真实Wan、动态连续观察、成片、最终观察或正式发布；本轮独立工作和测试已结束，不制造人类接受来跨过门槛。用户已要求每30分钟仅进度，活跃执行期间已按约汇报，未创建外部定时任务。下方所有“运行中/待启动”均为各次历史快照，以本段及验收矩阵为准。

04:21:27启动当前新裸全库，前缀**`jim-08-grounding-full-regression-a1596fa456d04178b7cbbed7197dd9cc`**。使用唯一D盘basetemp、bare pytest-v及前后源文件SHA清单，覆盖整个项目；源码/测试/workflows和快照内说明文件保持稳定，期间无并发Python/媒体。结果待实际完成，当前不声称全库通过；早先失败/中断记录不合并冒充本次全通过。

恢复修正最终三模块回归：**47 passed in333.38s，退出0**，`jim-08-reference-recovery-green-6e644e5b2421470fb7ca9f72a270b941.log`，包括原完整格式与紧凑格式的过期输入URL/缺result原任务恢复，以及缺请求/提交证据时零云操作。04:21:09在Python串行空闲后执行正常证书/主机名验证的OpenSSL匿名GET Range0-0，实际**HTTP403**，确认这个确切基准对象拒绝匿名读取；审计`jim-08-anonymous-reference-openssl-db94d1b31d394bd39866523034a67f43-audit.json`。无Authorization/query/proxy/redirect，未改ACL；只对该对象作此结论，不声称整个桶的所有对象/策略均已审核。新裸全库待立即串行启动，真实batch2选图和收信事实仍待答。

04:11:23已停止上一轮裸全库`cdbc8ea5...`：收集3651项、248passed/1failed，无终端pytest完成退出码；378项前后身份无变化，原日志及`-interrupted.json`保留，不能记为全库通过。失败是既有`test_original_task_query_recovery_does_not_require_live_input_urls`：新增安全检查误把result一律设为必需，阻断了无manifest时查询原受理任务的正常恢复。旧用例及新紧凑格式等价用例分别真实RED（`jim-08-legacy-query-red-498d7e6855154fa28826ea16bc8d485c.log`、`jim-08-compact-query-red-a42a9d60145f426f9df747be8cf8637f.log`）。已修正为仅有manifest时强制result齐全；原request/intent/submit-evidence/accepted仍全部必需，现存result仍严格核验。只读增量复审未发现剩余具体问题；三模块GREEN回归运行中，前缀`jim-08-reference-recovery-green-6e644e5b2421470fb7ca9f72a270b941`。通过后仍须从头执行新裸全库，以下“运行中”均为历史状态。

**当前实际门槛：image_batch_0002 awaiting_image_selection。** 同run正式参考续作03:52:51–03:55:24 +08，CLI退出3，四个参考任务均完成并下载原图，scene_0002/scene_0003各两张；原800字节cap、4.0模型及用户所选左图保持。TOS同一内容寻址对象已上传并HEAD/GET验证bytes/SHA，object收据绑定基准SHA `f94326fa819c7efdf6b1857d262d1fe0bd17b76f1d23803f30cd2b9b411e680e`；四个真实提交的参考URL摘要/时效及对象用途均在原request/intent/provenance。gate审计为 `jim-08-real-reference-compact-4871591f6c064de49cbb7fdf489d6ffa-gate-audit.json`；官方接受/结果/原图在 `production/jimeng/scene_0002/` 与 `scene_0003/`。技术完成不等于人类一致性通过。

第二批QQ邮件SMTP250接受，实际MIME及收据在 `production/image-selection/image_batch_0002/mail/part_0001/attempt_0001/`。已展示实际contact_sheet（含已选基准及四张新候选），询问两个场景选择、整组主体/环境是否可接受及实际邮件附件事实；均待真实用户回答。未生成Wan，无影片/最终观察/发布。

最终源码稳定后于03:57:12启动新裸全库，前缀 **`jim-08-grounding-full-regression-cdbc8ea5bfb749eba2f52b22af35e98f`**，实际收集**3651项**，前置文件身份清单保留；当前运行中，无最终通过或后置身份结论。只有本次最终结果能代表新增参考修复版本；此前两轮中断、所有RED和定向结果继续保留。

私有访问边界：额外PowerShell/.NET匿名GET小范围核查的v1/v2/v3均未取得可确认HTTP状态，v3为本机MethodInvocationException→WebException→Win32Exception（原公开文档下载已有Schannel凭据错误记录）。这些核查不证明私有或公开；没有禁用证书校验、改ACL或继续无效重试。原有Python/OpenSSL的签名TOS验证及官方参考任务成功不受此原生TLS问题影响。匿名访问状态仍未核实，待当前Python全库结束后用正常验证证书的OpenSSL串行只读确认。

最新参考修复验证：三模块 **28passed in228.64s，退出0**（`jim-08-reference-final-targeted-d0481dbab79e47b596c1250d6f06f450.log`），含两类型/字面转义、多主体完整字段、中文按字节、未知提交零补单、请求目录和提交证据缺失零云操作、紧凑中断恢复、旧完整prompt精确重放和Wan准入。最终只读复审确认重复付费分支在代码层面关闭，未发现新具体问题；没有代替实际测试。

对真实原run只读独立执行正式renderer及集中选择函数：scene2 **799字节/509字符**、scene3 **784字节/504字符**，均≤冻结800字节；原完整格式2548/2533字节。模型仍`jimeng_t2i_v40`，旧config、cap、已选原图与原Bible未改；完整提示词、SHA和限额在 `jim-08-actual-reference-budget-2c6dd001fcdf44ec8a0919ca165f9b93-audit.json`，日志同前缀.log。`git diff --check`退出0（仅命令级safecrlf=false，不改Git配置）。同run真实公共CLI续作已启动，前缀 `jim-08-real-reference-compact-4871591f6c064de49cbb7fdf489d6ffa`，当前尚待实际退出结果，不先记参考/TOS成功。

参考提示词修复续记：第二次裸全库在03:26:50主动中断以修复已真实发现的参考容量缺陷，**98passed/0failed**，375项前后身份一致，未完成而非全库通过；原`59e3d586...`日志及interrupted记录保留。新兼容设计见JIM-08 Scope新增两条，旧完整renderer保持，只有无请求证据且旧格式超限时采用完整视觉字段的紧凑表示；同一模型/API/冻结cap/所选基准保持，原引用证据仍完整落盘，不声称移出引用后的模型输入细节完全等价。

新测试首次准备错误：替身Bible无引用时旧prompt仅500字节，断言>800错误，**1failed/5passed**（`jim-08-reference-budget-red-175f0ed63a0843ff921b2d66642724dd.log`），不能算有效feature RED。补真实完整引用事实后 **6failed/1passed in9.78s**（`jim-08-reference-budget-real-red-96dc4f6953ac42daaa87fc56e25ae252.log`），原守卫正确拦下、紧凑renderer尚缺。实现后五模块 **63passed/1failed in427.49s**（`jim-08-reference-budget-green-53ebcce6610a4839989f973db05bb507.log`）；唯一失败是新测试过度要求中间images_ready阶段events.jsonl也零写。诊断确认只追加正常事件日志；改为核对全部production持久记录和外部调用/邮件计数，最终completed零写约定仍保留原全库，不修改生产日志行为。

只读审查发现两项Important并真实RED：缺少整个已完成request目录可能被误当新提交；紧凑事实/创作命名空间及字面分隔不明确。包含前述事件日志诊断的独立 **4failed in94.41s**（`jim-08-reference-review-red-b4a60d5db25b41bb991ac073d838ea56.log`）。已加完整request集合/原摘要核对、F/C/R命名空间、JSON条件引用及控制/Unicode行分隔转义。两新模块 **16passed in205.76s**（`jim-08-reference-review-green-df6262e46f814584a842d7ae8a277377.log`）。

复审进一步发现保留request.json但丢提交证据仍可能进入新付费分支。五种缺失证据真实RED **3failed/2passed in30.69s**（`jim-08-reference-proof-red-69154f408975445c8cf962e87a18d944.log`）。现有provenance要求每个原request及intent/submit-evidence/accepted/result完整，按原契约核验身份、摘要及task_id，整批首次云操作前拒绝缺失/冲突；没有provenance的正常部分请求仍走原恢复。最终只读复审未再发现具体问题；三模块最终定向回归运行中（`jim-08-reference-final-targeted-d0481dbab79e47b596c1250d6f06f450.log`），实际预算/真实参考续作/最终裸全库仍待串行执行。

最新续作：用户要求“每隔30分钟汇报一下进度只要进度，不要明细日志”；后续聊天进度仅简述当前比例/失败数/阶段，不贴明细日志。03:16的原裸全库快照368passed/3failed、3630collected，三项均为 `test_new_original_text_uses_automatic_prefix_and_exact_baseline_prompts[intent/tts_body/large_tts_body]`。03:17:27终止自有测试session准备修复，原测试没有终端pytest退出码/完整结论；375项源身份前后无变化。原日志、`-after-interrupted.json`、`-interrupted.json`均保留，不能记作全库通过。

单独RED复现第一项（`jim-08-full-suite-failure-red-b4e24520423c4289a6cdf7db3f5b8c81.log`，1failed in3.11s）：本地HTTP fixture用json.loads解析SCENE_INPUT_JSON之后整个文本，遇到合法SOURCE_CITATION_RULES尾注报Extra data并断开连接。仅将该fixture改为JSONDecoder.raw_decode读取第一个完整JSON，不改生产逻辑、不删尾注、不弱化原测试断言；三项 **3passed in40.47s**，日志 `jim-08-full-suite-failure-green-4a7ea69771fe4020a918124e95cf5f0f.log`。03:22:06已串行重启当前裸全库，前缀 `jim-08-grounding-full-regression-59e3d586f7964bb092797401ec59178d`，仍须实际完成并核对全部节点/前后身份。

用户“左边的”已通过原CLI消费当前批次user-selection-left.json，03:18:52–03:18:55退出0 `image_batch_accepted`，日志 `jim-08-real-accept-left-d5269aab832d45dc9383822dc5eca915`。未填整组观察，也未虚构实际QQ收信。

03:19:01–03:19:03普通续作退出3 `awaiting_image_model_configuration`：`reference prompt exceeds verified model capability`，日志 `jim-08-real-reference-batch-0e7b2fa74ca74a78b1f7de73fc11477b`。纯本地核对scene2完整参考prompt1720字符/2548字节、scene3为1715字符/2533字节（`jim-08-reference-prompt-size-54b0e5c6e92c46cf97a9dcd4ab05a042.log`）；冻结cap为800字节，故守卫正确拒绝且未发生TOS上传/参考出图/Wan。原官方资料建议不超过800字符，不能据此把已绑定800字节cap改大。当前仅安排只读修复设计审查：怎样保留全部视觉事实、将重复引用/追溯信息留在原Bible，同时精确恢复旧prompt；未改生产prompt/模型/cap或已选基准。此项仍未解决，不声明真实参考通过。

用户后续明确选择“左边的”，并询问“这个不是要发邮件确认吗”。已说明邮件已提交QQ服务器，现有范围是邮件看图+外部录入选择，不自动读取回信。按真实选择准备当前批次 `user-selection-left.json`：scene_0001/request_01_image_01及原图SHA，intent=accept、observation=null；仅基准选择，不伪造全组观察/实际收信。当前裸全库仍在串行执行，未并行运行消费CLI或新媒体/参考任务；准备文件尚未消费。用户尚未明确实际收到邮件。

**当前真实等待点：awaiting_image_selection。** 新wire实测 `20261021-014723-4ebdc1fecab2` 于01:47:22–01:49:28 +08完成首批出图，CLI实际退出**3**（父PowerShell工具将非零显示为1；以独立result记录的CLI3为准）。scene planner14B初次提案即通过，未用纠正；三个scene均绑定entity_0001/group_0001，首scene三片、其余各两片，规划共7片；463帧/16fps=**28.9375秒**、1,387,200个48k样本。这里只是已规划，尚无Wan视频或观看通过。

官方`jimeng_t2i_v40`两次任务均实际完成，2560×1440 PNG；task_id `15264366624190032065`（request_01_image_01，SHA `f94326fa819c7efdf6b1857d262d1fe0bd17b76f1d23803f30cd2b9b411e680e`）、`11525029665218781504`（request_02_image_01，SHA `788e167541cacc4e5cdd154af1f7557ebd0f6645b0da8b13d37e4559e7cba2cb`）。证据在该run `production/jimeng/scene_0001/`。首批仅基准图，无TOS参考任务，参考读取仍未执行。

QQ SMTP01:49:28返回250接受，Message-ID `<20261021-014723-4ebdc1fecab2.image_batch_0001.part_0001.attempt_0001@video-ai.local>`；收据及实际MIME在 `production/image-selection/image_batch_0001/mail/part_0001/attempt_0001/`。已向用户展示实际contact_sheet并询问左/右选择、基准接受及QQ收信附件一致事实；用户尚未回答，不将SMTP250写成已收信或人类接受。仅查看静态候选不代表全组一致性或影片验收。gate审计 `jim-08-real-14b-environment-54251c42e0fa477397605a52dcf45bda-gate-audit-v2.json`，保留v1中旧production-state快照；真实等待状态以公共CLI JSON为准。

源码稳定后已串行启动**当前裸全库3630项**：`jim-08-grounding-full-regression-25bcafeba7a14b6eacef7ed1014deb8f`，01:50:35 +08开始，独立basetemp，前置375项文件身份清单。当前运行中，尚无最终通过/退出/后置身份结论；不与其他Python或媒体并行。用户选图期间继续该验证，不声称JIM-08完成。

最新定向回归：九模块 **230 passed in57.35s，退出0**，日志 `jim-08-environment-final-targeted-3ee5bc7736714da3bc2f7de8bffefb3c.log`；包括容量边界重放、body=null提前拒绝、新wire六项HTTP集成及旧wire/generic反馈恢复。正常仓库配置`git diff --check`退出0（仅LF/CRLF提示）；首次未使用Git绝对路径导致命令未找到，随后使用`C:/Program Files/Git/cmd/git.exe`完成检查，没有改Git配置或元数据。

新独立公共CLI运行 `20261021-014723-4ebdc1fecab2`，日志前缀 `jim-08-real-14b-environment-54251c42e0fa477397605a52dcf45bda`。使用原14B配置/v3全文和scene-local transport，当前运行中，尚无云/邮件/影片通过结论；裸全库待此Python运行结束后串行启动。

当前补记（以下“运行中/尚待”均按各段当时状态保留）：group反馈实测 `20261021-013014-60de3e1d11da` 于01:31:58 +08退出2，473帧/29.5625秒、1,417,920样本；纠正仍引用未来环境来源。没有图像/TOS/SMTP，保留该run初次与唯一纠正，不追加第三次。

针对反复真实错误，在同一Ollama请求内增加可逆scene-local环境表示（`adapters/ollama_scenes.py`）：仅每非空段恰好一个speech且scene数量固定时，required场景槽冻结完整段/单元映射；来源用unit ID无损展开为完整原文/range；每场景环境只能用当前/过去来源新建，或向后引用先前场景，后续新环境须change_sources。decoder只恢复身份和模型明确选择，不自动合并或推定主体/场景语义；canonical schema与验证、最终记录、32768/8192、一次纠正及人工门槛保持。多单元段落沿旧格式；恢复完整精确重建五种历史/当前格式。

环境wire RED **2 failed/4 passed**（`jim-08-environment-wire-red-d80b36df5ac04775a4cfcf4280a4189e.log`），组合单元 **31 passed**（`jim-08-environment-wire-green-554771284cb74178b651a7650bb0ac97.log`）。集成初次重名导致collection错误（`jim-08-environment-wire-integration-e8b4d45b32fc432bab24d231e94846ae.log`）；重命名后 **261 passed/6 setup errors**（`jim-08-environment-wire-regression-5cc67e0e59db469b9270817070680fdd.log`），原因是新模块未导入被复用fixture依赖`production_config`。修正导入后六项实际通过，未把此前setup错误记作通过。

独立只读审查发现Important：新紧凑请求满足容量，但恢复时更早的旧全文引用候选可先超限并阻断恢复。153字符单单元+5000字节原始evidence真实边界复现，首次提交成功而重放失败；RED **1 failed/6 passed in5.54s**，日志 `jim-08-recovery-capacity-red-2d799f3a4062407bbef8d9d35a837f95.log`。现容量守卫仅将原异常细化为`SceneCapacityError(ValueError)`，恢复只跳过此种候选容量错误；源/结构等其他异常不被吞，实际新请求仍拒绝超限，仍须完整body及HTTP身份匹配。六模块 **150 passed in56.03s**，日志 `jim-08-environment-recovery-green-936b074b77be4721bb140c980ca38f3a.log`。复审确认Important修复；另建议显式拒绝无匹配哨兵与body=null相等，已RED **1 failed**（`jim-08-unmatched-intent-red-704d2a6758af4dad944ca73c128e8407.log`）后加`original_body is None`本层拒绝；下游本来也拒绝，无自动重发漏洞。最终更广回归正在执行，真实新wire和裸全库尚未开始。

后续keyed实测 `20261021-012247-0482266cdfba`，01:22:46–01:24:38 +08:00退出2；新标识符约束下不再出现中文编号。初次提案把相同`environment=env_group_001`拆为三组、无环境变化来源；旧通用纠错后模型把全部行动序列放入一共享组并引用未来段落，被拒绝。未发生云图像/TOS/SMTP。该运行的两次提案和所有输入/配音保留，未第三次提交。

继续针对该实际错误补精确环境组诊断：保持原拒绝条件及错误字符串，只跟踪环境组首次使用截止并在异常附`SCENE_GROUP_REPAIR_JSON`（前/新组及环境、当前单元、可复用来源单元/最早截止，说明动作变化不等于环境变化、共享环境不能引用未来动作、真实换环境须change_sources）。真实RED **1 failed**（`jim-08-group-feedback-red-9c56c295288845188bd5b6891c3e272b.log`）；四模块 **129 passed in49.06s**（`jim-08-group-feedback-green-172d3ed2774b4ee5889113187905eed4.log`），其中包含之前补的7项14B历史wire/generic链接恢复。对原已保存提案纯本地重建诊断，完整预算**32510≤32768**，未改原run、未发HTTP；日志 `jim-08-group-feedback-budget-c660996dec9740e48961a1773a4325b4.log`。独立只读审查无具体问题，未将预算/测试当作模型质量通过；此后另补一项历史generic环境组恢复尚未运行。

相同配置和v3文案的新独立公共CLI实测已启动，日志前缀 `jim-08-real-14b-context-1c5c441525a64e509cd9aad17c842496`，尚无退出结果。模型、正文、时长设置保持，未通过前不声称官方图像或影片成功。

14B首个实测结果补记：`20261021-011455-3ebcd27e0b64`，01:14:54–01:17:23 +08:00退出2，476帧/29.75秒、样本1,427,520。初次scene2引用`entity_00意图`，纠正后引用`entity_00意图: `，均未声明，原主体实际声明为`entity_0001`。这是生成的内部编号混入说明文字；更大模型未自动解决原流程。纠错原来仅通用“unknown key”而缺可用编号上下文。未提交云图像/TOS/SMTP。

据实际错误补RED **5 failed**：四类声明/引用位置不能拒绝混入解释的编号，unknown-key纠错无可用键上下文（`jim-08-scene-key-red-7a118c3636344867a35d1295659334e6.log`）。在新outgoing wire中为内部key/entity_key/scene_group_id/entity_ids/variant_ids增加ASCII标识符约束；正文/canonical schema/已有提案不变。unknown-key原拒绝与错误字符串保持，仅增加`SCENE_LINK_REPAIR_JSON`场景索引、被拒引用和实际声明键。四种发行wire精确重建，旧14B/8B和历史generic纠错保留。九模块 **246 passed in46.80s**，退出0（`jim-08-scene-key-green-43b8490f85a14430b0043aab289e17ad.log`）；此后补7个历史14B wire/generic链接恢复组合尚待运行，不冒充已通过。独立只读增量审查无具体问题，不等于安装的grammar转换器或实际质量已通过。

不对已失败run追加第三次请求，使用相同14B配置和v3文案新建独立试跑；日志前缀 `jim-08-real-14b-keyed-9a386b545a4440b49dbd4ddaf0db8cae`，尚无退出结果，不登记通过。代码仍待当前新裸全库。

用户明确“同意，升级吧”，已按BLOCKED→READY→IN_PROGRESS恢复同任务；随后明确“不用严格是30秒，实际多长就是多长”，允许完整实际时间轴，不再需要时长容差答复。下面2026-10-20的待选择/阻塞均为历史记录。即梦图片仍4.0，实际云权限、参考读取、邮件和影片尚未通过。

Qwen3 14B已用自有loopback11436服务器下载，pull退出0并停止该自有服务器，没有操作外部默认11434或生产11435服务。下载日志前缀 `jim-08-pull-qwen14-27ec6597073f40afa74ff88b70597115`。安装后独立逐字节SHA256核对config及全部层，模型层9,276,184,896字节、digest `sha256:a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e`；installed manifest与先前实际获取的官方完整JSON相同，SHA `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`。核对日志 `jim-08-verify-qwen14-install-eb4eb8ca0e3244169f2b07a3e98d4c60.log`。这证明安装身份，不代表模型效果。

实现可选顶层`scene_planner_model`，缺省8B，当前只允许8B/14B且仅即梦策略有效；units/旧storyboard保留8B。模型从冻结raw读取，传入请求构造、注入planner绑定和响应模型核对；旧resolved/schema/settings形状不变，三类旧wire仍完整精确重建，不信任已保存任意模型。普通请求不能14B，32768/8192和一次纠正保持。新单元回归RED **6 failed/8 passed**（`jim-08-model-selection-red-6b12470a0758488abecdeefdc61212cb.log`），修复后四模块 **97 passed in2.23s**（`jim-08-model-selection-green-ebdfa8142c164a66ac0239e5f927302d.log`）。协调器集成RED **8 failed/2 passed**（`jim-08-model-binding-red-0bcabb78c3b747dbbf7c8d58b0478914.log`），模型绑定实现后八模块 **202 passed in41.34s**（`jim-08-model-binding-green-60a376fdbe3848e6a508d87885a0506d.log`）。包含14B初次/一次纠正/原始配置改为8B后仍冻结14B、重放无HTTP、错误响应模型不授权纠正、注入模型不同本地拒绝、intent/frozen模型篡改拒绝及默认自有服务清理。独立只读审查无具体Critical/Important/Minor问题，未把静态审查视为真实效果或全库通过。

新任务配置 `D:/VideoSi/projects/video-ai/config/jimeng-acceptance-14b.json` SHA `3e5eb1896bcd1fab39be3361ba7ac456277870d52605a2f40efa8ed961767318`；原 `jimeng-acceptance-30s.json` SHA `e652ef5df342709cb315e791a5007cf6773638d2ab1cc792bfa471c09c51b9c4` 保留。新配置只改scene model14B及本次closing_seconds 6.7→3，其他字段保持；后者在用户随后放宽时长前已按先前33.6875s测量值准备并开始冻结运行，不修改当前冻结run。此实测不是完全相同时间轴的单变量比较；不能预设新时长或质量。原文案v3字节未变。

公共CLI真实实测已启动：`python -B -m video_ai make-video --config D:/VideoSi/projects/video-ai/config/jimeng-acceptance-14b.json --script D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance-v3.txt --json`；日志前缀 `jim-08-real-14b-14c1287d8c9d4c13904cd8339f335465`。尚无退出结果，不登记通过。当前完整裸全库尚未启动，待源码稳定及该Python运行结束后串行执行准备脚本；不再用旧213项或JIM-07全库代表当前版本通过。

## 最新进展：真实规划暴露的缺陷修复

最新结果：推理实测run `20261020-233458-996ce31b92b0` 于23:36:41 +08:00退出2，第二个完成提案的语音单元为`[speech_0001],[speech_0003],[speech_0003]`，完整性校验正确拒绝：`scene unit partition must cover all speech exactly once in source order`。首次提案仍有未来来源。两次实际thinking分别1750/6610字符，eval_count2503/3758，done_reason均stop；证明安装服务执行了thinking，未出现输出截断，但不能声称这已验证所有输出预算语义。实际539帧/33.6875秒。仍无云图像、TOS、SMTP或成片。

最终当前八模块 **213 passed in34.80s，退出0**，日志 `jim-08-scene-reasoning-final-targeted-bab5bf5d5be24e9e968b1eb9813723c1.log`。其中含历史/当前thinking及通用/详细纠错恢复、完成/响应中断，以及篡改think为旧合法值False或未支持值`high`均不能重绑原HTTP证据；所有恢复均无新POST。裸全库尚未执行，准备脚本为 `D:/VideoSi/cache/video-ai/logs/jim-08-grounding-full-regression.ps1`，不冒充已启动或通过；待代码稳定后串行执行，前后371项source/test/workflow/说明/配置等身份及逐节点覆盖一并核对。

下一步待用户选择：已询问是否下载更大的**本地分镜**Qwen3 14B并补显式模型选择/旧请求兼容；这不改变已确认的即梦4.0。只读获取官方公开manifest（HTTP200），总层字节9,276,198,077（约9.3GB），原件 `D:/VideoSi/cache/video-ai/logs/jim-08-qwen3-14b-public-manifest.json`，SHA256 `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`；模型层digest `sha256:a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e`。日志 `jim-08-planner-model-metadata-3947ea0972e74224bb59b8177be1c828.log`。只取元数据，没有下载权重；本机目前仅安装qwen3:8b。GPU为RTX5090 D v2、24455MiB，元数据/显存检查不保证14B能满足整上下文或规划质量。

可审阅的拟议变更：新任务专用配置显式选择`qwen3:14b`作为scene planner；旧配置缺省8B、units/旧storyboard仍按原模型。模型字段随冻结配置绑定；adapter请求和响应model须与该绑定精确一致，旧run继续重建原8B与原thinking，不能把新模型的结果注入旧run。保留32768/8192预算、完整原文、一次纠正和所有人工门槛。先RED后实现参数解析/模型身份、旧run恢复及篡改拒绝测试；本地装好并核对manifest后用同一完整文案/媒体配置独立实测，效果未知，失败仍保留现场。代码稳定后再执行新裸全库。用户也可选择保留8B继续诊断；尚无选择，不提前下载或实施此扩展。

后续单变量验证：v3运行 `20261020-232830-bbb9ab87afa3` 已于23:30:21 +08:00退出2，仍是第二次完成提案未来来源被拒绝；实际541帧/33.8125秒，未达到精确30秒。初次错误为共享环境变化缺来源，纠正后又引入未来引用；没有图片/TOS/SMTP。停止继续改文案猜测，先复核架构：纠正只收到首个错误，不包含被拒提案的完整上下文，模型实际重新规划可能引入另一处错误；不是校验器误报。独立审查未发现应放宽的来源条件。

仅对新的场景规划请求开启Qwen3:8b `think=True` 作为单变量实验，普通请求仍False；保持相同v3文案/配置、32768完整输入guard、8192输出预算及一次纠正。恢复精确重建三种已发行wire：无元组约束/False、紧凑元组约束/False、紧凑元组约束/True；匹配后仍核对完整intent/context与HTTP证据。真实RED分别为新场景think断言1 failed（`jim-08-scene-reasoning-red-788473011eef467fad1476972ca91320.log`），只改think尚未修复旧恢复时4 failed（`jim-08-scene-reasoning-legacy-red-047ba10fbb0e49098eecb68b27493c78.log`）。修复后八模块 **207 passed in30.16s**（`jim-08-scene-reasoning-targeted-350535b97346433d8ff139c3222385da.log`）；再补历史/详细纠错×False/True×完成/响应中断，两个模块 **47 passed in29.82s**（`jim-08-scene-reasoning-replay-final-55b1a1555780496d9935099e74a4d0d4.log`）。后续think篡改回归尚待执行。静态审查无新增具体问题，不代表模型质量已通过。

新独立实测日志前缀 `jim-08-real-scene-reasoning-f455e50deb0a48ebb2ea875f070d1865`，尚无退出结果；不会更改旧run的think、旧文案或请求，也不会把thinking拼入正文。模型可能用思考挤占JSON输出预算；遇length仍停止、不追加请求。已向用户询问本次30秒是否允许几秒波动，尚无答复，不预设接受33.8125秒。另记录既存边界：时间截止目前在variant/group使用时实施，entity仅核对精确原文来源，不能声称entity已有相同时间门槛。

本节覆盖下方早期快照中的“仅文档、未改源码”描述。多次实际规划未通过，已先刷新同任务pause交接，再记录IN_PROGRESS→BLOCKED；待用户明确下一步本地分镜方案后恢复。没有真实即梦图像、TOS对象、邮件收件或影片接受结论。生产代码/测试已改变，JIM-07全库基线不再证明当前版本；完成前必须取得当前版本新的裸全库结果和前后文件身份。

- 独立run `20261020-225656-80131ea756f2` 使用v2三段文案，真实PCM17.3秒、时间轴421帧/26.3125秒。初次规划引用偏移错误，一次纠正后仍引用未来段落；第二次完成提案被严格拒绝，退出2，未发生云图像或邮件请求。原初次/纠正请求响应保留，不再第三次提交。
- 独立run `20261020-230858-4b618d9ad6f0` 使用 `jimeng-acceptance-30s.json`（只调整本次结尾停顿为6.7秒）。实际配音波动为18.5秒，时间轴500帧/31.25秒，不能称为精确30秒。初版anyOf语法在HTTP前超容量；改为紧凑整对象enum后原run续作，没有重复配音。实际两次提案共50/50引用均匹配原语音单元，但仍含未来引用，第二次提案被拒绝，退出2；保留现场，不新增第三次请求。日志前缀 `jim-08-real-start-fixed-114c0f38f0554e46aff150ffe994c563`、`jim-08-real-resume-grounded-749cc040b58e47e789ef7b5e24a8bf2e`；只读诊断 `jim-08-grounding-runtime-check-8835cd228b60435a81b31a6cdaf5374f.log`。
- `adapters/ollama.py` 针对场景引用增加完整原单元元组enum和首次使用证据说明；原全文、后续单元、32768容量拒绝和8192输出预算保留。语义校验仍拒绝未来来源。实际50/50元组正确不等于已证实安装的转换器能拒绝所有对抗性错误元组；本地schema回归和实际模型行为分别记录。
- `planning/production_scenes.py` 在原拒绝异常中增加确切被拒绝来源、最晚允许位置和可用完整原单元；`runtime/production_scene_plan.py` 把该诊断加入唯一纠正请求。恢复时重建历史或当前请求体，历史通用纠错提示仍须完整identity/body和HTTP证据匹配，没有重发未知提交或放宽一次纠正限制。
- 初版未来引用测试误用 `fact`，在schema层先被拒绝；该失败不能证明修复。改为合法 `name/value/sources`，临时去除诊断后取得真正RED：**1 failed**，断言纠错prompt缺少 `SOURCE_REPAIR_JSON`；日志 `jim-08-future-repair-red-corrected-6067bb88206d44b4b291c5232e914afc.log`。恢复后定向 **40 passed in25.39s，退出0**；日志 `jim-08-future-repair-green-6946262a671443aca3c34c24757ad702.log`。覆盖历史/详细提示×已完成/响应中断四种恢复；原intent和已有文件字节不变，HTTP仍仅两次。
- 最后八模块 **204 passed in29.04s，退出0**；日志 `jim-08-grounding-final-targeted-8c6b9818caa94b54beeeb8041fd0adcc.log`。前一阶段为199通过，不能代替本次结果。独立只读审查确认fixture已修复，无新增具体生产代码问题；静态审查不证明真实模型质量或全库通过。
- 新独立试跑 `20261020-232431-f6ad170ae85d`，公共 `make-video --config .../jimeng-acceptance-30s.json --script .../jimeng-acceptance-v2.txt --json`，23:24:30–23:26:25 +08:00 **退出2**。日志前缀 `jim-08-real-start-source-repair-4153c1def6bf468fa06047fd7d824e97`。纠错提示确实收到被拒绝的第二语音单元及最晚31位置/第一单元可用证据；模型修正第一组后又把第三段飞行动作放入第二组共享设定，该组首次使用截止56而引用结束86，仍被严格拒绝。原记录保留，不做第三次请求。实际时间轴仍500帧/31.25秒；尚无云图像/邮件。
- 只读比较原始/纠正提案发现模型将“动作序列”当作稳定环境组，导致未来证据泄漏；问题并非凭证或即梦4.0。未新增第四次生产代码试修或改变协议。在用户文案委托范围内，将固定洁白羽毛/芦苇/浅水/远处树林/晨光在第一段交代清楚，再独立准备 `jimeng-acceptance-v3.txt`（SHA256 `7ec4a870bde1478a191d3647f0ff8dd15577236c0a0e6b800075fc5a66d57406`）；后两段仍为展翼和飞行。原文案/旧run未改。新run `20261020-232830-bbb9ab87afa3` 已执行本地配音/规划，日志前缀 `jim-08-real-start-stable-context-987ad059ac654d41af687fdafa030435`，尚无退出结果，不登记通过。凭证仅在启动进程临时加载。

## 范围与当前状态

2026-10-20 用户要求“完成JIM-08”，任务板记录 `READY -> IN_PROGRESS`。实施契约为 [JIM-08-design.md](JIM-08-design.md)，历史阻塞交接为 [JIM-08-handoff.md](../task-handoffs/JIM-08-handoff.md)。本轮使用说明、合法示例及本地定向验证已完成。后续模型、凭证、桶和委托文案输入齐备后，任务已由BLOCKED→READY→IN_PROGRESS恢复，真实CLI已启动；尚无真实图片/收信/观看/正式发布通过结论。

前置基线仅引用 [JIM-07-verification.md](JIM-07-verification.md)：3552 passed，退出0，364项文件身份一致。这是前序结果，不是JIM-08本轮运行结果，也不能证明真实服务或观看通过。

## 五项验收矩阵

| 验收项 | 替身证据 | 真实服务证据 | 观看/用户结论 | 确切run/文件 | 状态 | 问题与下一步 |
| --- | --- | --- | --- | --- | --- | --- |
| 1. 端到端、故障及相关历史回归 | 当前裸全库3651通过/pytest退出0，378项前后与独立重算身份一致；模型/环境230项、参考恢复47项定向通过，失败逐次保留 | 不适用 | 不适用 | a1596fa4前缀完整输出及root-final-full-audit-3605d610独立审计 | 当前版本全库通过；验证外壳统计误报另记并复核关闭 | 不将替身通过当真实观看/服务验收；原外壳退出1、失败与中断证据保留 |
| 2. 用户指定模型、官方出图及TOS参考读取 | 正式4.0、官方能力材料绑定及TOS/参考替身回归 | 同run基准2张、带真实TOS参考的关联4张均完成；TOS对象签名HEAD/GET核字节和SHA；该基准对象匿名GET实际403 | 实际图像效果待用户整组确认 | `20261021-014723-4ebdc1fecab2`的jimeng/reference-storage/provenance、两份gate audit和anonymous-reference-openssl-db94d1b3审计 | 技术调用完成；视觉未通过 | 不把模型任务成功当人类一致性通过；匿名403只对已核查的确切对象作结论 |
| 3. QQ实际收信、选择与整组图片观察 | 实际选择协议及邮件/完整准入回归有证据 | 两批SMTP250接受，MIME/Message-ID已落盘；两批选择及整组准入均经原CLI接受 | 基准左图、场景2/3各第2张；用户确认风格一致及QQ邮件收到；另实际agent_image查看三张原图 | 当前run两批accepted、complete-acceptance及6400df93日志；用户原话71f6023e记录 | 选择、静态准入及用户收信确认完成 | 不扩写用户结论为所有附件字节核对、两次投递均已核验或动态影片通过 |
| 4. 三画面主体、连续长链及完整成片验收 | 当前旧逻辑全库通过200帧血缘/映射/组合/准入替身测试，不能证明真实模型连续 | 时间轴463帧/28.9375秒、计划7片；6片技术生成，父末PNG字节正确，但三个续片用户拒绝 | 用户接受三个首片后明确三个续片不连续；没有把子片记通过 | 原run六段、两轮gate审计；continuity-diagnosis.md及隔离对照目录 | 真实效果不通过；停止推进，诊断/修复中 | 补时序条件及阶段提示，先实测再集成新冻结修订；不改原run、不补未知请求、不以像素分数替代动态观看 |
| 5. 正式收据、完成重放无副作用及使用说明 | 说明/示例及恢复契约已更新；本轮全库通过，含完整交付及两次只读重放替身测试 | 正式交付及完成重放未执行 | 未核实 | README/config说明及候选说明；无真实交付收据 | 文档及替身通过；真实验收未完成 | 最终观察通过再显式发布，随后两次普通续作和一次重复publish核对零副作用及用户邮件事实 |

## 配置输入检查

首次检查：

- `D:/VideoSi/projects/video-ai/config/jimeng-acceptance.json`：不存在。
- `D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance.txt`：不存在。
- 当前进程中的默认变量 `VIDEO_AI_VOLC_ACCESS_KEY`、`VIDEO_AI_VOLC_SECRET_KEY`、`VIDEO_AI_SMTP_AUTH_CODE`：均未设置。仅记录存在性；没有读取、输出或落盘秘密值。实际变量名以用户配置为准，默认变量缺失不代表其他名称不存在。
- 尚无用户指定的实际req_key/参数、经核验的参考能力档案或已有TOS桶设置；不使用示例值代替。
- 发件及收件既定为 `318575094@qq.com`，SSL 465；尚未验证账号可用或收件箱投递。

按设计“缺失时……停止真实请求”，目前未调用真实模型、TOS或SMTP。向用户索取任务配置/原文的本地路径及在执行环境配置凭证的方法，继续不依赖这些输入的文档与本地检查。

## 本轮命令与结果

继续实施输入（用户“同意，那就用4.0吧”）：已确认4.0模型，在此前助手代拟30秒白鹭方案的明确委托上下文中准备正式输入。`jimeng-acceptance.json` 的SHA256为 `ddad10d6e5c9a74482a88ed2885d6ba259e22e82d7aa3a06eaf4a1ad9bdf1fd9`，正式原文与草稿字节相同（`436fb9a25228e38037c6b21c07db699dea381ef1dd31ab7169a63f0914032212`），仍保留完整原文、原声音和媒体参数。

官方能力材料：Python/OpenSSL实际取得 `https://docs.volcengine.com/docs/JimengAI/JimengAI-ImageGeneration40-InterfaceDocumentation?lang=zh` 的HTTP 200完整HTML（884892字节），原字节保存在 `D:/VideoSi/cache/video-ai/logs/jim-08-official-jimeng40-27bc48853870403786caafce171fe8bd.html`，SHA256 `c683c91f401d3e2a78d2fe0a0fbd623ac81b33cb910f33c63162c4145b9d1011`。实际核对协议、req_key、参考图字段/数量/格式/尺寸/文件限额及提示词建议；不是仅对JS占位页或搜索摘要做能力断言。Windows Invoke-WebRequest/curl此前分别报连接及Schannel SEC_E_NO_CREDENTIALS，此错误属于公开资料下载的本地TLS组件；Python校验证书的HTTPS随后成功，没有禁用TLS校验或修改生产代码。

档案 `D:/VideoSi/projects/video-ai/config/jimeng-v40-capability.json` 由本次实际核对者Codex填写并绑定上述原材料SHA和带时区时间，档案SHA256为 `3180aa1d88caae5708227cb099a994ab78c6d4353c8bd48100e519c76e0e20bc`。本次采用**保守本地准入子集**：只接受本次生成的2560×1440 PNG/JPEG；最多10张；15,000,000字节；提示词最多800 UTF-8字节。因此保证不超过官方800字符建议，但可能保守拒绝本可接受的较长多字节提示词。本地最小/最大尺寸及字节限制不是冒充服务的精确最小尺寸/提示词字节上限，边界解释在同目录`jimeng-v40-capability-verification.json`。实际官方限额/权限与参考读取仍要经真实请求验证；遇到本地拒绝不放宽或伪造档案来绕过。

正式配置解析/模型选择/URL预算检查退出0，日志 `D:/VideoSi/cache/video-ai/logs/jim-08-real-config-prepare-024fd93e79b34ddfa273636ec473f350.log`。真实本地doctor命令 `python -B -m video_ai doctor --config D:/VideoSi/projects/video-ai/config/jimeng-acceptance.json --script D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance.txt --json` 退出0，日志 `D:/VideoSi/cache/video-ai/logs/jim-08-real-preflight-317416029d7e47029faadb4b49a69f15.log`；只证明本地预检，`inference_verified/full_run_space_checked/fast_profile_verified`仍为false。

按任务板已记录的解除和继续请求启动真实公共CLI：`python -B -m video_ai make-video --config D:/VideoSi/projects/video-ai/config/jimeng-acceptance.json --script D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance.txt --json`。三项凭证仅在该启动进程内从用户本地JSON加载；日志前缀 `D:/VideoSi/cache/video-ai/logs/jim-08-real-start-f46d39e96b074b4dba43fcf979b8072a`，stdout JSON及stderr分开保存。新run为 `D:/VideoSi/projects/video-ai/runs/20261020-225154-10d18e7c8a70`，目前仍在执行，尚无退出码/完成结果，不能计通过。首个等待点需实测时长及三画面/连续链，30秒尚未实现/验证。

首轮实际结果补记：22:51:54–22:53:39 +08:00，**退出2、blocked/scene_plan**，错误为`scene planning context exceeds full-input capacity; no truncation or automatic retry`。实际无损原文被分成13个语音单元并已完成本机真实GPT-SoVITS配音；PCM 1,051,200样本=21.9秒，时间轴含静音1,483,200样本、495帧=30.9375秒。没有`scene-planning/initial.intent.json`，只保存`inputs.json`；在规划模型请求前拒绝，未到即梦/TOS/SMTP阶段，不能登记为官方图像请求或收信失败。

只读根因重现：prompt 23,282 UTF-8字节、schema 8,800字节，完整输入/输出保守预算42,322 > 32,768；timeline占14,688字节、unit各字段无损保留。诊断日志 `D:/VideoSi/cache/video-ai/logs/jim-08-context-diagnosis-16e8e1034dbc42ee9a25c7d71e497aaf.log`。这是既定的完整输入容量拒绝，没有放宽guard、删字段、截全文、变更生产代码或改旧冻结运行。

在用户明确委托样片文案的范围内，将三个画面改写为更连贯的描述，另存 `D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance-v2.txt`；原文案与运行完整保留。相同配置新建独立run `D:/VideoSi/projects/video-ai/runs/20261020-225656-80131ea756f2`，命令只将上述`--script`改为v2路径；日志前缀 `D:/VideoSi/cache/video-ai/logs/jim-08-real-start-v2-c06984923cba4a20b704029bf5e399b9`。这是尚未提交任何官方图片/云任务前的本地样片输入修整，不是重发未知任务或自动新增收费返工；v2仍在执行，实际时长与规划尚待核对。未达到任何真实影片验收通过。

补充输入与准备（2026-10-20 22:46 +08:00）：用户授权助手准备文案，要求视频30秒，并表示不理解模型选择。已准备三段同一白鹭的完整文案草稿 `D:/VideoSi/projects/video-ai/inputs/jimeng-acceptance.proposed.txt`（81个非空白字符，SHA256 `436fb9a25228e38037c6b21c07db699dea381ef1dd31ab7169a63f0914032212`）；配置建议 `D:/VideoSi/projects/video-ai/config/jimeng-acceptance.proposed.json`（SHA256 `a0c74b64fe7433885a3985e4234a92786aad9be31eab5499e5cc19801ec52611`）。建议图片模型4.0、每段目标一画面、单片上限6秒，保留原production.json的实际voice、媒体、权重、工具和workflow路径，合入用户已提供的桶设置；不覆盖原配置。通过load_config/scene_planning/selection_email/reference_storage解析及原配置字节、voice/media一致性检查，退出0。日志 `D:/VideoSi/cache/video-ai/logs/jim-08-30second-proposal-d2ae8faca69a4f939fa139a67acafeb6.log`。这是可供用户确认的建议，不是已冻结的正式运行；没有配音或真实调用，实际时长未知，30秒尚未实现/验证，三个画面及连续链也须以真实规划核对。最终模型/文案确认、参考能力核验及后续真实验收仍待执行；任务保持BLOCKED。

补充输入（2026-10-20 22:41 +08:00）：用户表示SMTP授权码已保存。重新检查原凭证文件，JSON合法，AK/SK及 `VIDEO_AI_SMTP_AUTH_CODE` 三字段均为非空字符串，均可在一次检查进程内临时加载到环境；未输出、复制或记录实际值。脱敏报告 `D:/VideoSi/cache/video-ai/logs/jim-08-smtp-credential-check-fa69f351a461431580edd4b7138023a6.json`。尚未做远端鉴权或发送邮件，不能登记实际QQ收信。已有参考设置存在，完整任务配置及验收文案仍不存在。SMTP本地输入不再是缺项；仍待用户最终确认模型/参数、文案，并完成真实能力核验及运行配置，任务保持BLOCKED。

补充输入（2026-10-20 21:55 +08:00）：用户提供 `D:/VideoSi/projects/video-ai/config/jimeng.credentials.local.json`。只检查结构及存在性，JSON解析成功，`VIDEO_AI_VOLC_ACCESS_KEY`、`VIDEO_AI_VOLC_SECRET_KEY` 两字段为非空字符串；已在一次独立检查进程中验证可以临时注入同名环境变量，没有输出、复制或记录秘密值。此注入仅对该次进程有效，后续实际CLI必须在同一启动进程重新加载该本地文件；现有程序只从环境取值，不会自动读取此JSON。未进行远端鉴权或付费请求，不宣称密钥有效/权限通过。脱敏报告：`D:/VideoSi/cache/video-ai/logs/jim-08-credential-file-check-b1ca7bb370df43719e304182a9db26d6.json`。该文件没有SMTP授权码；任务配置和文案仍不存在，TOS/模型能力等缺项保持。最初“默认变量未设置”的检查是历史记录，不能继续解读为用户尚未提供AK/SK。

补充输入（2026-10-20 22:19 +08:00）：用户确认已创建桶 `testvitest`，地域华北2（北京）。已创建非秘密参考设置 `D:/VideoSi/projects/video-ai/config/jimeng-reference-settings.json`：`region=cn-beijing`、`endpoint=https://tos-cn-beijing.volces.com`，凭证只引用已提供AK/SK的环境变量名，参考模型/能力档案仍留空待真实核验。通过现有 `parse_reference_storage`、`parse_capability_paths` 及三个根字段检查，退出0；文件SHA256为 `932f7a3be847e1026317e4d05b37dbead28de2020f3b8c5d724264a6f42b6f6d`。日志 `D:/VideoSi/cache/video-ai/logs/jim-08-tos-settings-check-fcebc4a3dfa64f36ac48414f2d0ec8c6.log` 保存起止时间/退出码及非秘密配置身份。没有TOS请求，权限、私有策略和官方参考读取尚未实际验证；已有桶设置不再是缺项。SMTP授权码、验收文案、用户最终模型选择/已核验能力档案及完整任务配置仍需完成，任务保持BLOCKED。

所有以下日志和对应的`-result.json`均位于 `D:/VideoSi/cache/video-ai/logs/`，metadata保存完整参数、起止时间及实际退出码。Python调用先bootstrap与Initialize，均使用D盘`$VideoAiPython -B`并串行执行。

| 执行 | 结果 | 确切日志文件名 |
| --- | --- | --- |
| 初次配置/记录/CLI六模块回归 | **81 passed、75 errors in 10.34s，退出1**；75项均在tmp_path准备阶段被旧pytest用户目录权限拒绝 | `jim-08-config-regression-c9679b3a8611495c8a5743b40a0372e3.log` |
| 同六模块改用本轮独立basetemp重跑 | **156 passed in 2.77s，退出0**；未改源码或测试 | `jim-08-config-regression-retry-9af94dd0b920480d8399d4517759e669.log` |
| 文档/合法示例变更后最终九模块回归 | **264 passed in 5.13s，退出0**；2026-10-20 20:49:43–20:49:49 +08:00 | `jim-08-final-local-regression-1df1c44410884393a303e7b581e57309.log` |
| 初版本地文档检查脚本 | **退出1**；错误假设CLI help会向外抛SystemExit，实际main捕获后返回0 | `jim-08-docs-check-38a648de3b364444a27b6d9d883b4803.log` |
| 修正检查脚本后的最终文档/示例/身份检查 | **退出0**；示例可加载、旧默认保留、空参考配置要求等待、11个新入口选项均存在、相对链接及锚点有效、363项源码/测试/workflow身份全匹配 | `jim-08-docs-check-final-e413ac7b95d54d3984116baa93435c72.log` |

最终九模块命令（独立basetemp是本次环境适配，不修改旧临时目录、ACL或历史证据）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-08-final-local-regression'
& $VideoAiPython -B -m pytest tests/unit/test_jimeng_config.py tests/unit/test_reference_config.py tests/unit/test_scene_clip_records.py tests/unit/test_config.py tests/unit/test_scene_planning_config.py tests/unit/test_scene_pipeline.py tests/unit/test_scene_revision.py tests/unit/test_scene_revision_records.py tests/integration/test_scene_pipeline_cli.py -q --tb=short --basetemp D:/VideoSi/cache/video-ai/temp/jim-08-1df1c44410884393a303e7b581e57309 -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

只读本地文档检查：先bootstrap、`Initialize-VideoAiEnvironment 'jim-08-docs-check-final'`，再执行 `& $VideoAiPython -B D:/VideoSi/cache/video-ai/logs/jim-08-check-docs-20261020.py`。脚本SHA256为 `7afdc648711e10fc06bdd986484a07fd198a37397d09863340fa9f2352a94d65`；初版保留为同目录`jim-08-check-docs-20261020-v1.py`，两次日志均保留。检查通过不代表真实服务调用。

最初全364项文件核对差异0，结果为 `jim-08-config-regression-c9679b3a8611495c8a5743b40a0372e3-baseline.json`；输入检查为同前缀`-preflight.json`。本轮改变的前置清单成员只有使用说明`docs/jimeng-candidates.md`；源码/测试/workflow共363项的清单及字节SHA仍全部匹配。最终四个文档/示例的bytes/SHA详见最终docs-check日志。完整前置全库仍明确引用JIM-07，不计为本轮重跑。

## 文档交付与自审

- `README.md`：新增新策略入口、实际配置/文案落点、按返回run及模板选图/逐片/最终观察、显式发布、等待码及修订；历史默认策略保留。
- `config/README.md`：移除JIM-01-only过时描述，列明AK/SK及QQ授权码、参考能力精确schema与TOS设置、路径迁移规则、模型切换及故障恢复。
- `config/jimeng.example.json`：显式列出与请求尺寸一致的预期输出尺寸；参考设置继续留空，不包含凭证或伪造能力材料。
- `docs/jimeng-candidates.md`：CLI示例改用使用者实际配置路径，说明首次调用可能生成图片、最终观察门槛，修正已实现父末帧续接及CLI邮件retry说明。
- 对照现有CLI、reference_config、selection_config及JIM-08设计进行文档自审；未改生产逻辑、测试或workflow，未创建Git分支、提交或推送。
- 交接标题/章节顺序、任务板BLOCKED及配置/文案仍不存在的核对已通过，日志 `jim-08-handoff-check-0e44c1e620754b5fbfe23e25969d076d.log`。该次额外临时覆盖`core.autocrlf=false`的diff检查退出2，将既有CRLF行尾误作空白；没有据此改文件或仓库配置。恢复使用仓库正常配置的`git diff --check`退出0，确切日志为 `jim-08-final-diff-check-77f75ba5b49a407ba1b91a73efb15dc6.log`。

## 失败、恢复与未核实边界

首轮pytest失败原因是 `D:/VideoSi/cache/video-ai/temp/pytest-of-qzw19` 权限拒绝；改用从未使用过的本轮临时目录后同组通过。旧目录和ACL未变，所有失败日志保留。文档检查脚本首次失败是检查器对CLI返回方式的错误假设，按现有`cli.py`捕获SystemExit的行为修正检查器；未改CLI或弱化检查。

此前因输入缺失由IN_PROGRESS记录为BLOCKED，并保留同任务pause交接；随后用户输入和实际材料补齐，已按两次合法转换恢复IN_PROGRESS并启动上述真实run。不得覆盖默认配置或伪造能力/观察，不以替身标记真实验收passed；仍未达到COMPLETED条件。

解除条件：用户提供确切实际配置和完整UTF-8文案本地路径，配置中含已选择模型及参数、经核验参考能力和已有TOS桶，并在执行环境设置所声明的凭证变量。先按设计核验输入，只记录凭证存在性和非秘密身份；再记录BLOCKED→READY及明确续作的READY→IN_PROGRESS。真实收信、整组图像、动态视频和全片结论仍须之后实际取得。未执行设计中的真实步骤、完整媒体组独立重跑、两次真实完成重放或重复publish。
