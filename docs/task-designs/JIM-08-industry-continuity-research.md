# JIM-08 长场景连续生成方案调研

调研日期：2026-10-21。适用硬件：RTX 5090 D v2，约24GB显存、32GB系统内存，Windows。目标是同一白鹭在长镜头中持续运动，并保持羽色、身体形态、背景、曝光和镜头轨迹。

最新范围修订：用户强调目标为**通用视频生成方案**。本报告白鹭仅为已有失败案例；通用条件、镜头意图、能力分派与跨题材/长链门槛以[JIM-08主设计](JIM-08-design.md)新增约定为准。用户已授权一次VACE固定原图+真实历史对照，20:09技术完成但外观仍失败，详见[诊断最新结果](JIM-08-continuity-diagnosis.md#2026-10-21-通用方案修订后的参考历史单变量对照)和verification；没有自动启动FramePack。下方“下一次验证建议/未授权VACE”仅为此前历史时点。

后续进展：用户已选择验证第一个方案，范围与实际进度另记于[SkyReels-V3隔离验证](JIM-08-skyreels-v3-validation.md)及verification当前段。下文“仅调研、尚未执行”均为本报告完成时点，不覆盖后续授权，也不表示后续视频已通过。

**优先评估专门训练的视频续写模型 SkyReels-V3；从选图重新生成分钟级长镜头时，评估 FramePack。长期架构参考 LongLive 的流式缓存与 MemFlow 的历史检索。** 这三个方向分别解决已有视频续写、低显存长片生成、长程记忆，不能互相冒充。当前没有核实到能在本机现有环境直接接入、同时满足原生16fps和任意长镜头稳定性的现成方案。

本次为资料与实现调研，没有新增权重下载、依赖安装或生成任务。原多片续接验收、463帧时间轴及既有拒绝结论保留；JIM-08仍为IN_PROGRESS。

## 长镜头需要保留什么

业界有三类相关机制。视频续写模型以一段真实历史视频作为条件，学习接下来如何运动；FramePack把历史帧按不同精度压缩，在有限的模型上下文中继续生成；LongLive等因果模型保留跨块注意力缓存，并通过长序列训练减少生成越久越偏的问题。它们都比单独一张末帧提供更多时间信息，但缓存和历史latent仍是模型特征，不能理解成显式保存了白鹭的翼拍速度或物理状态。

要同时避免动作断裂和外观漂移，需要近期运动历史与长期主体依据。只保留最近一段，会逐渐忘记最初的白鹭；只反复给同一张图，又可能把动作拉回原姿态。MemFlow通过检索更早的相关历史补足长期依据，说明“连续生成”和“始终是同一主体”是两个需要分别检验的问题。[LongLive论文](https://arxiv.org/abs/2509.22622)、[MemFlow官方实现](https://github.com/KlingAIResearch/MemFlow)

“无限长度”通常指推理窗口或缓存不随视频总长度无限增长，不表示画质、身份或动作可以无限期保持，也不表示整套程序的CPU内存和输出存储恒定。固定窗口仍会积累预测误差。

## 候选方案比较

| 方案 | 真实机制与现有输入 | 本机部署依据及限制 | 对JIM-08的判断 |
| --- | --- | --- | --- |
| [SkyReels-V3 Video Extension](https://github.com/SkyworkAI/SkyReels-V3) | 专门的单镜头续写模型，读取已有视频；官方支持5–30秒新增内容，内部多轮生成 | 官方有FP8与block offload；未给本机24GB/32GB峰值实测。24fps，依赖需隔离 | **已有视频续写的首个本地候选**；不能据30秒支持外推任意长链 |
| [FramePack](https://github.com/lllyasviel/FramePack) | 历史上下文压缩；原版双向抗漂移，F1按时间向前生成并持续保留首图依据 | 官方支持Windows、RTX50系列，称6GB可生成60秒；30fps，首次模型下载超过30GB。32GB RAM加载峰值未证实 | **从已选图重做长镜头的候选**；官方GUI不是直接接旧Wan视频的接口 |
| [SkyReels-V2 DF](https://github.com/SkyworkAI/SkyReels-V2) | 训练支持逐帧噪声级别的Diffusion Forcing，重叠视频历史，提供extension接口 | 官方540p的1.3B约14.7GB显存，14B约51.2GB；24fps | 1.3B可作低资源机制对照；不预设其细节质量等同现有14B |
| [LongLive 1.0 / 2.0](https://github.com/NVlabs/LongLive) | 因果注意力、跨块KV缓存、长期训练、保留早期依据；2.0增加量化等基础设施 | 1.0公布H100结果；2.0速度表基于GB200，FP8验证基于H100。I2V训练支持不能等同已核验的适用I2V权重 | **长期架构参考**；不能把现有Wan2.2 I2V权重直接换成因果模型 |
| [Self Forcing](https://github.com/guandeh17/Self-Forcing) | 训练时模拟生成历史，缩小训练和实际连续推理的差异 | 官方测试24GB GPU，但要求Linux和64GB RAM；基础模型为Wan2.1 T2V 1.3B | 本机内存和系统未达到官方测试组合，不列为最先部署项 |
| [MemFlow](https://github.com/KlingAIResearch/MemFlow) / [MemRoPE](https://github.com/YoungRaeKimm/MemRoPE) | 分别采用历史检索、持续压缩记忆，补充长期身份信息 | MemFlow官方测试80GB卡/Linux；MemRoPE要求单卡40GB以上或两张24GB卡 | 适合借鉴记忆设计，不是现有单卡24GB的已验证直接方案 |
| [IAMFlow](https://github.com/Eddie0521/IAMFlow) | 在流式生成中加入身份感知记忆 | 官方部署把DiT/文本编码器/LLM放一张卡，VAE/VLM放另一张卡 | 研究线索；额外模型和多卡要求使其不适合本次首试 |
| [FreeNoise](https://github.com/AILab-CVC/FreeNoise) / [FIFO-Diffusion](https://github.com/jjihwan/FIFO-Diffusion_public) | 调整噪声、时间窗口或滚动去噪，延长基础模型的生成范围 | 官方实现基于各自支持的旧模型；不是现有Wan2.2双阶段工作流的通用开关 | 不建议作为本次“再改一个采样参数”的修复 |

表中的显存和速度均为对应作者公布的配置依据，没有换算成本机性能。尤其是H100/GB200上的实时速度，不能用于估算本机分钟级视频的等待时间。

## SkyReels-V3为何值得先评估

它与本次需求最接近之处，是有独立的`single_shot_extension`任务，而不是把普通I2V的第一张图替换成视频文件。代码每轮读取25个历史像素帧，经VAE编码后作为干净前缀，与新增噪声一起进入模型；前缀时间步设为0，只更新新增部分。较长请求按最多5秒一轮执行，后续轮次用上一轮尾25帧继续。这个流程可以核查历史究竟怎样参与推理。[实际续写代码](https://github.com/SkyworkAI/SkyReels-V3/blob/main/skyreels_v3/pipelines/single_shot_extension_pipeline.py)

同时要看到它的边界：25帧在24fps下只约1.04秒；该路径没有跨轮保留长期KV，也没有同时把独立的原选图送入单镜头续写模型。模型学过视频续写，增加了成功的依据，但仍可能随着多轮续写改变羽色或背景。它不是已经验证成功的长程身份解决方案，不能用“多了16张历史帧”推断必然胜过已失败的VACE。

实现还有三个接入问题需要先处理：

1. **输入时基。** 官方读取器按解码帧索引取尾25帧，没有读取PTS或按源帧率重采样；输出固定24fps。把现有16fps父片直接交给它，会把1.5625秒历史当作约1.04秒的时间节奏，无法作为公平的运动连续性试验。[输入读取器](https://github.com/SkyworkAI/SkyReels-V3/blob/main/skyreels_v3/utils/util.py)、[输出入口](https://github.com/SkyworkAI/SkyReels-V3/blob/main/generate_video.py)
2. **内存与环境。** `--low_vram`有官方支持，但先建立BF16模型、载入权重，再量化；CPU加载峰值需要单独核算。依赖固定PyTorch2.8、TorchAO0.10、FlashAttention等，与现有Comfy环境不同；不应在现有环境直接安装覆盖。[加载实现](https://github.com/SkyworkAI/SkyReels-V3/blob/main/skyreels_v3/modules/__init__.py)、[依赖清单](https://github.com/SkyworkAI/SkyReels-V3/blob/main/requirements.txt)
3. **输出契约。** 官方函数返回新增视频，而不是原父片加新增片的完整成片。需要独立核验实际新增帧数、上下文裁除及拼接边界，不能只相信整数秒参数。README权重链接与CLI默认模型名也不同，实施前应明确采用的官方仓库及其文件身份。

因此，优先级是“先完成资源与时基准入，再做一次小样”，不是立即换模型恢复原生产run。

## FramePack适合怎样的长场景

它对近期历史保留更多信息、对较远历史使用更高压缩率，使模型每次处理的上下文规模可控。原版通过双向采样抑制漂移；F1是另一套向前生成的权重与调度，不能把原版双向抗漂移的效果直接归给F1。[官方方法说明](https://lllyasviel.github.io/frame_pack_gitpage/)

核对F1代码可见，它把首图latent与最近历史一起提供给下一段，另保留压缩的历史latent及首图视觉特征。这里的首图是持续的条件依据，不是未来画面的硬性像素锁定。官方程序从图片开始，没有接旧Wan父片的原生入口；要沿用它，应重新生成当前镜头，再重新观察。[F1实现](https://github.com/lllyasviel/FramePack/blob/main/demo_gradio_f1.py)

原程序还在CPU积累完整历史latent和已解码像素，并在解码重叠处调用`soft_append_bcthw`做线性混合。因此，固定模型上下文不等于整个应用内存恒定；混合后的接缝好看，也不能证明未混合的动作接顺。若用于正式续接，应保存混合前的段落和来源，分别观察，不能用混合作为接受证据。[重叠处理代码](https://github.com/lllyasviel/FramePack/blob/main/diffusers_helper/utils.py)

它适合验证“从同一张选图长时间生成”的能力，但需要新增Hunyuan系权重和编码器，不能复用现有Wan双阶段模型。官方6GB显存演示没有解决本机32GB系统内存的加载峰值问题；官方30fps输出也尚未满足现有原生16fps契约。

## 流式记忆方案的实际成熟度

LongLive把近期动作保存在跨块注意力缓存中，并保留早期特征；切换提示词时刷新相关缓存，避免简单重复完整动作脚本。MemFlow进一步按当前提示检索过去相关帧，而不是永远只记最初几帧。这为长镜头架构提供了可实现的参考，但任意鸟类身份与翼拍相位仍需实测。

LongLive2.0已发布5B权重、NVFP4及FP8实现，不过官方性能数字有明确的服务器硬件和计时范围；其I2V训练功能不能代替对实际适用checkpoint的核验。[2.0部署说明](https://github.com/NVlabs/LongLive/blob/main/LongLive2.0/README.md)

也存在面向消费卡的工程封装。Daydream Scope给LongLive的配置标注预计20GB显存，支持视频输入、量化与缓存管理；这是封装作者的估计，并未证明本机能以768×432保住原白鹭。Scope当前代码许可为CC BY-NC-SA 4.0，与LongLive仓库Apache2.0不同，不能把上游许可直接覆盖整个封装。[Scope配置](https://github.com/daydreamlive/scope/blob/main/src/scope/core/pipelines/longlive/schema.py)、[Scope许可说明](https://github.com/daydreamlive/scope#license)

FramePack仓库代码采用Apache2.0；SkyReels-V2/V3采用Skywork社区许可，其声明允许商业用途但受协议条款约束。代码许可与各基础模型、权重及依赖许可需分别记录，本报告没有据此作全部组件均可任意商用的结论。[FramePack许可](https://github.com/lllyasviel/FramePack/blob/main/LICENSE)、[SkyReels-V3许可](https://github.com/SkyworkAI/SkyReels-V3/blob/main/LICENSE.txt)

## 商业服务能否解决

**Seedance 2.5是值得保留的云端候选。** 官方已把`extend`列为独立任务，支持视频与额外参考素材，推荐显式设置`omni_reference_task_type=extend`、`reference_video`及`ratio=adaptive`。当前API提供4–30秒生成范围；官方示例将新增片与原片拼接，不能据此认为API一定返回完整父子成片或支持无界长链。[官方模型说明](https://ark.volcengine.com/region:cn-beijing/docs/seedance-2-5.md)、[续写示例](https://ark.volcengine.com/region:cn-beijing/docs/seedance-2-5-prompt-guide.md)

这条路径不能直接接本次旧片：官方视频输入要求24–60fps，像素总量至少407,696；本次父片16fps、768×432=331,776像素，两个条件均不符。现有即梦图片AK/SK与TOS配置也不等于已开通方舟视频API Key、模型权限及预算。若采用云端，需另建符合规范的研究链，不能偷偷改帧率、放大旧片后当作原生续接通过。[官方API输入及鉴权](https://ark.volcengine.com/region:cn-beijing/docs/create-video-generation-task-api.md)

Veo与Luma也提供延长功能，但查到的对应接口都限制为自身生成的视频，无法直接承接现有Wan片。Gemini API的Veo3.1预览文档还明确写明将在2026-10-22关闭，当前不应围绕该预览接口新建实现；后续若选Google云，应重新核对其正式服务。[Veo接口与生命周期](https://ai.google.dev/gemini-api/docs/veo?hl=en)、[Luma延长接口](https://docs.lumalabs.ai/docs/video-generation)

## 建议的验证顺序

先推进SkyReels-V3的准入分析，FramePack保留为从选图重做长镜头的备选。需要完全本地、严格沿用现有16fps父片时，当前不能声称其中任一方案已经可以直接上线；若把原生24/30fps链纳入研究，必须与正式16fps验收分开。保持真实时长的帧率转换与只改FPS元数据有本质差别，但任何转换都不能冒充原生16fps。

后续小样应有明确上限和停止条件，以下为待选择的验证设计，尚未执行：

1. 核对一个候选的确切权重清单、磁盘占用、加载峰值及Windows内核支持，明确原生帧率与输入时间戳策略。不能因资源不足自动改分辨率、权重精度或时长。
2. 在独立研究目录生成约10–15秒、至少跨两个真实生成窗口的单镜头。从原选图保持同一白鹭、同一飞行动作，窗口之间只描述当前持续动作；保存全部上下文、新增帧与来源。新生成的第一段需要重新观察，不能继承旧首片的接受。
3. 第一条边界出现羽色、翼尖、背景或动作重置即判失败，停止该方案的本轮试验。通过后才考虑30秒、60秒压力测试；不以单个边界成功宣称长链成功，也不自动换种子反复生成。
4. 完整播放检查主体、背景、曝光、镜头轨迹和翼拍节奏；并检查0–10、10–30、30–60秒的变化趋势，防止只在开头稳定、后面退化。技术指标仅辅助定位，不能替代真实动态观察。
5. 选定且确有改善后，再设计生产策略、时基和恢复记录。保留原run、已选图、旁白/字幕及拒绝记录；原生16fps、完整时长、真实多片续接的验收若需调整，必须显式讨论，不能靠重切同一成片满足。

如果剧情允许景别变化，可以在同一语义场景内规划多个有意切换的镜头，借助角色与环境参考保持一致；这是一项产品选择，不能作为当前连续长镜头失败的通过理由。

## 资料留存

官方GitHub README与关键实现的快照、Git blob SHA清单，以及火山官方Markdown原文和SHA256收据，保存在 `D:/VideoSi/cache/video-ai/logs/jim-08-industry-continuity-research-20261021/`。入口为`github-sources-manifest.json`及`official-markdown-receipt.json`。先前获取到的火山HTML只有页面壳，保留在同目录，不将其计为正文证据；最终结论使用成功取得的官方Markdown。

本报告依据官方文档、论文与实际公开推理代码评估机制；没有把网页演示当作本机白鹭视频实测，也没有登记新的human_video观察或连续性通过。

## 2026-10-21 恢复审查与下一次验证建议

用户“按 JIM-08 交接继续。”后已恢复同一任务。以下是下一次隔离可行性探针的建议，**未获新增模型下载、安装或推理授权**；不是生产迁移设计，也不改变原生16fps、完整旁白/时间轴和真实多片动态验收。

重新核对SkyReels首窗的visual-screening和final-audit，并再次实际查看采样图：后段暖金色树林/湖面逐渐转灰绿，羽毛阴影偏冷，保留外观失败结论；未完整播放，动作仍未验证。新只读审计`D:/VideoSi/cache/video-ai/logs/jim-08-resume-readonly-audit-cefff00c56f747e4a22314ea395647f5.json`逐文件重算原run3011项的大小/SHA/mtime、生产基准378项及审阅副本SHA，全部匹配；仍为6个clip记录和3个首片observation-accepted，没有第二窗intent。它不是新pytest或视频质量通过。

### 选择依据

| 下一方向 | 解决问题的依据 | 当前代价与边界 | 建议 |
| --- | --- | --- | --- |
| FramePack F1单镜头探针 | 每窗持续输入固定首图latent/视觉特征、近期历史和分层压缩历史；与SkyReels仅最近25帧条件存在明确机制差别 | 从选图重做，不能直接继承旧Wan父片；新增Hunyuan系权重，官方30fps，本机32GB RAM加载峰值未证明 | 优先做一次有上限的研究验证 |
| 继续调SkyReels/VACE | 可复用已有权重，但本轮各自失败因素尚未独立隔离 | 已有停止约定；没有足够依据把增加步数、改精度或参考输入当成下一次必胜条件 | 本轮不建议追加参数试验 |
| LongLive/MemFlow或商业续写 | 长期缓存/记忆或专用云续写有不同机制 | 现有硬件/系统、实际I2V checkpoint或视频API权限仍有前置缺口 | 保留后续备选，不同时启动 |

F1的首图条件不是未来像素锁，不能承诺解决漂移。原版FramePack的双向抗漂移机制不直接归给F1；选择F1是为了检验按时间向前的真实跨窗历史与固定首图条件。

### 建议批准的一个探针

- **问题：** 从scene3已选原图重新开始，F1能否在约11秒内跨多个真实生成窗口，保持同一白鹭、暖金色湖面/树林及连续飞行动作？仅回答可行性，不接回正式run。
- **输入：** 原scene3选图，SHA256 `d29e1f201a58691c97eb221ff1c5bb5d675c7a0442c436d7fff8b3bb8fb5e94f`；不使用已拒绝续片或旧首片代替首图。正向提示固定为`The same white egret keeps flying steadily to the right above the same lake, with continuous natural wingbeats. Its white plumage, long neck, yellow beak and dark trailing legs remain consistent. Warm golden light, the same distant tree line, lake reflections and exposure stay steady. The camera tracks the egret smoothly at the same distance.`；不重复起飞或展翼动作起点。文案/旁白/正式时轴不受此研究提示影响。
- **唯一配置：** 官方`lllyasviel/FramePack_F1_I2V_HY_20250503`，DiT BF16，官方编码器/VAE FP16；seed=264244520399005，25步，latent_window_size=9，CFG=1、distilled guidance=10、rescale=0，TeaCache关闭，官方低显存路径保留6GB。每个已创建intent最多执行一次，失败不换seed/步数/精度或模型重跑。
- **尺寸与时基：** 官方640桶函数对2560×1440输入选择832×480，按其resize/center-crop记录实际输入像素与裁剪；研究原生30fps。不得直接把旧16fps父片输入F1，也不把30fps转码计作原生16fps生产接受。输入裁剪/模型首帧如已明显改变主体，立即停止。
- **上限：** 最多9个前向窗口，逐窗保留状态并先筛查后推进。按上游默认窗口推导，期望累计82个latent帧、325个像素帧，约10.8333秒；这是代码推导，实际以tensor形状、PTS和映射核验，不预记为实测。不补帧、变速或循环凑时长，不自动追加30/60秒压力测试。
- **状态与来源：** 保存固定首图latent/视觉特征身份、每窗clean_latents及1x/2x/4x历史索引、当前历史及RNG状态、生成latent和解码前后数组。不是每窗重新初始化独立I2V；如无法精确保留/核对状态，停止探针，不降级为仅末帧。
- **接缝：** 上游`soft_append_bcthw`混合33帧重叠。保留上游原输出供对照，同时另存无混合轨：首窗保留全部像素，后窗只附加解码数组中33帧重叠之后的真实新增像素；逐窗核验映射和像素帧数。未混合的边界出现动作/曝光跳变即失败，不以混合输出掩盖接缝。两份副本都记录实际帧数/时长及逐帧像素身份。
- **停止与观察：** 每窗先看首/中/尾及与前窗边界的采样，发现主体变形、羽色/背景/曝光明显漂移立即停止下一窗；无明显静态问题才继续，最多9窗。采样筛查通过后交付完整无混合副本供用户连续播放，检查翼拍节奏、速度、镜头和外观；未取得真实动态结论时保持unverified。通过只说明这个短探针有效，不能宣布任意长场景或三个正式scene已通过。

### 下载与资源准入

只读核对已有F1、README和utils快照Git blob身份，均匹配原manifest。另通过GitHub连接读取`bucket_tools.py`（blob `dc13fdeb11f9ac87c64dda049a06b968360e7c3f`）及`requirements.txt`（blob `9ee90ca442fde2abbe2806fc63307f748290d1c6`），核实上述尺寸选择及依赖版本。官方要求diffusers0.33.1、transformers4.46.2等，与SkyReels隔离目录不同，不能直接共用或覆盖生产Comfy包。

2026-10-21 19:48只读尝试三个官方HF仓库的模型元数据均超时；报告`D:/VideoSi/cache/video-ai/logs/jim-08-framepack-resume-research-20261021/metadata-receipt.json`。没有取得本轮不可变revision/LFS清单或精确下载量，不能把README的超过30GB估计当成已核实完整预算。D盘剩余449,634,799,616字节；磁盘有余量不等于内存准入。

批准探针后，第一步仍是取得并保存三个实际消费仓库的固定revision、逐文件大小/SHA：F1 transformer，`hunyuanvideo-community/HunyuanVideo`的text_encoder/text_encoder_2/tokenizer/tokenizer_2/vae，`lllyasviel/flux_redux_bfl`的feature_extractor/image_encoder；不下载未消费的原Hunyuan transformer或原版FramePack。完整清单未核实就不下载权重。之后才在独立研究目录准备依赖/模型；先核验本机Windows/Python/CUDA兼容、CPU提交余量和GPU加载峰值。不得照搬同时把全部编码器与DiT常驻CPU的GUI加载路径；按阶段加载/释放，必要只读映射/卸载改动先作小型数值等价验证。资源不足或需更改权重数值/尺寸/时长则停止并报告具体缺口，本次不自动降精度或扩充探针范围。

无论探针成败，原run、已选图、音频/字幕、观察及生产基准保持；若后续选择生产迁移，还须另行解决正式原生16fps兼容、显式revision、受影响观察失效、安全恢复和回归。当前没有候选已经证明同时满足原16fps与不限时长场景的要求。
