# 视频生成成熟方案调研与现有程序选型建议

调研日期：2026-10-14。范围：官方产品、API、模型流程和独立评价；未调用付费生成或实施接入。

建议将下一步重点转为商用服务及完整参考素材流程的比较：MiniMax H3、Seedance 2.5、Wan 3.0 API 优先进入国内使用场景的候选名单；Gemini Omni Flash 1.1 作为另一条可评估路线。现有本地 SDXL Base → Wan 2.2 fast → 逐帧超分链路保留为对照。是否采用哪条路线由真实成片可用率决定，不能从官方展示推断自己的文案也能一次成功。

## 现有问题对选型的影响

已观察到的起始图包含严重条纹、色块、错主体及不自然纹理，这些缺陷会进入后续视频。当前历史样本使用 768×432 的 SDXL 基础模型图，代码已有英文 1280×720 分支，其真实效果尚未验证。

这个结果证明当前流程的产物质量不足，不能据此认定 Wan 2.2 模型家族本身都不可用。先前方案主要围绕提示词、分辨率和 LoRA，尚未建立与成熟产品的画质对照。应先建立可接受成片的外部参照，再决定本地优化是否值得继续投入。

## 成熟方案比较

| 方案 | 已核实的能力与接入形式 | 对本项目的价值 |
| --- | --- | --- |
| MiniMax H3／海螺 | 官方提供产品与 API；支持文本、首尾帧和多模态参考；公开基础权重与完整流程说明 | 值得作为首批质量对照；可先测 API，再评估本地部署 |
| Seedance 2.5／字节体系 | 官方模型支持最长 30 秒片段、视频延长、参考与编辑；Runway 开发者 API 已列出 2.5 | 适合测试多镜头、参考素材与较长叙事；注意不同渠道的费用 |
| Gemini Omni Flash 1.1 | 官方 API 支持视频生成与编辑、主体参考、首尾帧和参考素材延长 | 适合评估带参考的可控生成与局部修改；接入前核对账号及地区 |
| Wan 3.0 API | 阿里云官方提供文生、首帧、首尾帧、参考生成及提示词扩展 | 提供与本地旧 Wan 链路明显不同的服务对照；API 可用不等于对应完整模型可本地下载 |
| 可灵 3.0／3.0 Omni | 官方说明多图/元素参考、首尾帧、多镜头及原生音频；另有 API 平台 | 成熟参考控制路线，适合放入后续产品/角色一致性对比 |
| Runway Gen-4.5 与开发者平台 | Gen-4.5 支持文生/图生；平台另外提供多镜头 Recipe 和多个厂商模型 | 对开发者接入有价值，可通过一个接口试多个模型；平台功能不能全算作 Gen-4.5 单模型能力 |
| LTX Studio | 提供脚本拆场景/镜头、角色/物体/场景 Elements、可编辑分镜和导出 | 是可直接试用的生产工作台，也是现有程序工作流的参考；不等于本地 LTX 权重 |

来源：[MiniMax 官方仓库](https://github.com/MiniMax-AI/MiniMax-H3)、[Seedance 2.5 官方介绍](https://seed.bytedance.com/zh/seedance2_5)、[Runway 模型目录](https://docs.dev.runwayml.com/guides/models/)、[Google Omni 文档](https://ai.google.dev/gemini-api/docs/omni)、[Wan 3.0 官方 API](https://help.aliyun.com/en/model-studio/wan3-video-generation-api-reference)、[可灵官方指南](https://kling.ai/quickstart/klingai-video-3-omni-model-user-guide)、[LTX 分镜工作台](https://ltx.io/studio/platform/ai-storyboard-generator)。

字节国内直连渠道需要继续核对账号可开通版本和控制台价格。官方已有 [Seedance 2.5 API 文档入口](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)，但本次网页正文受动态加载限制；不以搜索摘要确认全部接入参数。上表的托管 API 能力来自实际读取的 Runway 官方开发文档。

## 独立评价支持哪些选择

本次读取的 Artificial Analysis 有音频图生视频榜单中，MiniMax H3（768p）、Gemini Omni Flash 1.1、Seedance 2.5 和 Wan 3.0 位于前列。Vidu Q4 仍标记 Preview，因此不把最新预览排名直接当成生产成熟度。该榜单基于盲测人类偏好；有声与无声、不同任务的榜单分开比较，不能将一个排名解释成所有题材上的绝对优势。

来源：[图生视频榜单](https://artificialanalysis.ai/video/leaderboard/image-to-video/)、[评价方法](https://artificialanalysis.ai/methodology/video)。

本项目使用独立原文旁白，有声榜单只能作为选型线索；自己的比较须重点观察画面，避免把声音效果误算成视觉收益。

## 产品效果来自哪些完整流程

### 参考资产替代反复猜测主体

LTX Studio 把角色、物体和场景作为可复用 Elements；可灵 Omni 也提供多图和元素参考。对本项目的启示是：同一主体应复用图像资产及参考描述，跨镜头改变姿态和镜位，而不是每镜头仅靠重新写一遍主体名称来获得一致性。

来源：[LTX 分镜中的 Elements](https://ltx.io/studio/platform/ai-storyboard-generator)、[可灵 Omni 的参考功能](https://kling.ai/quickstart/klingai-video-3-omni-model-user-guide)。

起始资产可以评估 Seedream 5.0 Pro 或当前 Nano Banana 系列；这里提出的是候选，不是已验证的画质排名。参考图可承担不同角色：严格首帧、主体外观、环境、风格或动作参考；它们不能全部被当作同一种“起始图”。Google 官方文档明确区分首帧和主体参考。来源：[Seedream 官方模型](https://seed.bytedance.com/zh/seedream5_0_pro)、[Omni 参考输入](https://ai.google.dev/gemini-api/docs/omni)。

### 面向目标模型的上下文处理

MiniMax 官方将完整 H3 分为 Context-IR、H3-Base 和 Regenerate-2K：上下文处理后生成基础视频，再结合原上下文生成高分辨率版本。Context-IR 没有包含在开放权重发布中；官方提供 API 和专门的提示词指南。因此本地基础权重不自动等于完整产品效果，普通逐帧超分也不等于上下文引导的再生成。

来源：[H3 完整系统说明](https://github.com/MiniMax-AI/MiniMax-H3)。

Wan 3.0 API 的 `prompt_extend` 可启用服务端提示词扩展；其官方说明短提示可受益，同时增加延迟。对本项目的启示是按目标模型适配输入，不给所有图像和视频模型套一份固定字符数的提示词。该功能仍不能保证原文含义无误。来源：[Wan 3.0 参数说明](https://help.aliyun.com/en/model-studio/wan3-video-generation-api-reference)。

### 可编辑分镜与选择性返修

Runway 的多镜头 Recipe 提供自动拆镜和自定义 3～5 镜头模式，支持明确的镜头描述与时长；LTX Studio 提供可编辑分镜。借鉴这些流程时，应先组织场景、主体、镜位和动作，再安排镜头覆盖旁白，避免把所有短句都机械地变成独立场景。

来源：[Runway 多镜头工作流](https://docs.dev.runwayml.com/recipes/multi-shot-video/)、[LTX 分镜工作台](https://ltx.io/studio/platform/ai-storyboard-generator)。

这是一项未来设计建议，不意味着本轮改动现有旁白时间轴。原文配音和字幕应继续由程序控制；模型自带语音可以关闭、静音或仅保留需要的环境音，避免改写原旁白。

## API 费用的可比口径

下列是本次读取页面的标价，统一为美元；它们不是网页会员包或厂商直连价格。

| 模型与渠道 | 输出档位 | 基础视频费用／输出秒 |
| --- | --- | ---: |
| H3，经 Runway | 768p / 2K | $0.10 / $0.15 |
| Seedance 2.5，经 Runway | 720p / 1080p | $0.30 / $0.68 |
| Gen-4.5，Runway | 对应 API 输出档位 | $0.12 |
| 可灵 3.0 Pro，经 Runway | 1080p，关闭原生音频 | $0.12 |
| Wan 3.0，经 Runway | 1080p | $0.20 |
| Gemini Omni Flash 1.1，经 Runway | 1080p | $0.15 |
| Veo 3.1 Standard / Fast，Google Gemini API | 1080p，带音频 | $0.40 / $0.12 |

来源：[Runway API 定价](https://docs.dev.runwayml.com/guides/pricing/)、[Google API 定价](https://ai.google.dev/gemini-api/docs/pricing)。Runway 页面标明每 credit 为 $0.01，上表已换算。

参考输入可能额外收费：例如 H3、Omni 的参考图片和参考视频，Seedance 2.5 的输入/参考视频；Seedance 也有单次最低收费。图片生成、税费、下载存储、专业输出和镜头返修需要另计。Google 与 Runway 对同一 Google 模型可能使用不同渠道价格，不能混用。

成本应按“合格素材”计算。例如计划得到 60 秒成片，但实际生成 180 秒候选素材：每秒 $0.12 的方案仅基础视频费用就是 $21.60；每秒 $0.68 就是 $122.40。这是按假设总输出秒数计算的估算，不是报价，实际镜头时长限制及最小计费会改变结果。高价模型若减少返修，也可能比低价但低可用率的模型便宜。

Veo 3.1 仍可纳入比较，但按本次 Google 文档，1080p/参考图等模式存在 8 秒时长约束，应按实际可选时长规划和计费。来源：[Veo 官方生成文档](https://ai.google.dev/gemini-api/docs/veo)。

## 本地部署路线

可研究 H3-Base 或 LTX-2.5 的官方部署方案，并以产品/API 输出作参照。H3 的完整官方上下文流程涉及托管模块，不能把基础权重部署称为完整复现。LTX 官方仓库当前 quick start 使用 LTX-2.5，所列 BF16 下载约 66 GiB；这是下载体积，不是显存需求。硬件适配、量化与速度需单独测量。

来源：[H3 官方仓库](https://github.com/MiniMax-AI/MiniMax-H3)、[LTX 官方仓库](https://github.com/Lightricks/LTX-2)。

LoRA 在这条路线里是按需控制风格或主体的工具；当前更优先的问题是基础画质、参考资产和完整生成流程。先比较未加 LoRA 的可用率，再决定是否投入训练或挑选 LoRA。

## 不宜作为新路线的 Sora API

OpenAI 官方 deprecations 页面列明 Videos API、Sora 2 和 Sora 2 Pro 于 2026-09-24 停用。因此这次新 API 接入不选择 Sora；旧模型介绍和价格页面的存在不能替代生命周期公告。这里的结论仅针对上述 API，不扩展为其他产品的状态判断。

来源：[OpenAI 官方停用公告](https://developers.openai.com/api/docs/deprecations)。

## 对这个程序的建议

第一优先：对照成熟 API 的实际画质。国内场景先选择 H3、Seedance 2.5 和 Wan 3.0；账号或网络条件合适时加入 Gemini Omni Flash 1.1。通过官方产品先试效果，能够满足需求后再设计程序接入。Runway 可作为多模型实验入口，但最终接入渠道还应比较厂商直连费用和能力。

第二优先：保留原文配音、字幕和交付功能，未来将画面阶段改为可替换的生成后端。不同后端需要独立提示词和参考素材角色，保存实际模型、参数、费用和输出，不强行共用 SDXL 的提示词规则。

第三优先：图片资产以实际参考图与现代生成/编辑模型准备，支持主体外观和场景复用。先比较“原始画面生成质量”与“上游参考资产质量”，再决定是否保留本地 SDXL 或采用 LoRA。

建议的最小实测：五类题材各一个 5 秒镜头，每路线生成两次，共三路线、30 条候选片。以相同视觉要求、相同参考素材分别测试，保持每家推荐的模型输入方式；记录原始图/片、改写提示词、可用率及成本。基础模型能力和各家推荐完整流程分别比较，避免误把输入适配差异当成模型能力差异。

还应选择一份短脚本测试整片：跨镜头外观、景别变化、动作连贯和剪辑节奏都不是单镜头测试能证明的。验收以原始输出和最终成片观看为准，不以分辨率、超分结果或自动格式校验作画质结论。

这次调研没有取得自己的付费样片，也没有确认用户账号权限及预算；候选名单用于下一阶段对照，不宣称其中任何一家保证通用高质量成片。
