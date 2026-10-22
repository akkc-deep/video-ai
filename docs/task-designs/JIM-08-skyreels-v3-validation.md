# JIM-08 SkyReels-V3隔离验证

状态：**第一窗技术完成，采样外观检查未通过，按约定停止，第二窗未执行。** 2026-10-21用户明确“那就先验证第一个方案吧”，授权执行已讨论的SkyReels-V3可行性与短续写验证。属于一次隔离技术试验，不是生产策略迁移；不追加FramePack、LongLive或商业API试验。原多片续接、原生16fps和完整正式时间轴的验收继续有效。

## 本次结果

本机已真实运行官方BF16单镜头续写：18:37:19完成8步，生成157帧，去除25帧重建历史后得到132帧/24fps，即5.5秒新增视频。包含编码与逐帧核验的本窗耗时632.52秒，CUDA分配峰值8,477,737,984字节、保留峰值12,071,206,912字节；外部显存读数约13.6GB，不能把分配峰值当作整卡占用。

实际查看12格采样图、原父末帧及新增末帧。起始新帧与父末姿态/画面接近，但后续采样逐渐丢失暖金色树林和湖面光照，末帧背景转灰绿、羽毛阴影更冷；按本试验保持外观/光照的要求，静态外观筛查判失败并停止第二窗。没有声称完整播放或动作连续性通过，也没有把这一窗外推为任意长镜头能力失败或该模型所有配置都无效。

审阅副本：`D:/VideoSi/projects/video-ai/reviews/JIM-08-skyreels-v3-first-window.mp4`，205帧/24fps=8.541667秒，前73帧为显式时基适配的原生历史，3.041667秒开始132帧真实新增。SHA256 `8a93779ffd1b1282c48853a4c2331da99041873376977f47ce6d6def98463c3f`。副本与试验输出字节一致，lossless RGB逐帧/PTS已核对。采样图为同目录`JIM-08-skyreels-v3-samples.png`。

18:41最终审计对全部10个模型文件重新完整计算SHA256，17个固定源文件Git blob SHA一致，原run3011项字节/mtime及生产378项基准身份均不变。没有第二窗intent或新的生产观察接受。证据为`final-audit.json`、`window_01.technical.json`、`window_01.visual-screening.json`；推理进程已正常退出。以下为执行范围与过程记录。

## 试验目标与范围

检验专用视频续写模型能否在原scene3白鹭父片之后持续飞行，并保持羽色、体形、背景、曝光和取景。最多两个真实生成窗口，每窗请求新增5秒，实际时长以原生输出帧数/24记账。第一窗出现明显外观漂移时停止；不自动换seed、模型、采样参数或追加更长压力测试。

固定源为原run `20261021-014723-4ebdc1fecab2` 的 `scene_0003_clip_0001/source.mp4`，93帧/16fps，SHA256 `fb0d55e89f22fcf96a99ef55ba7433f40d7d41092eac025183d0c1101cab7639`。旧首片接受仅说明原父片正常，不能外推新续片；新样片没有human_video接受记录。

条件像素按其`mapping.json`回到`generated.mp4`的保留帧[0,93)，SHA256 `e4aef0d3edc0787f3c89ff0038a25d6658ef515093e4ff75c8672d74c746c736`，尾帧须与已存原生PNG逐像素相同。`source.mp4`是重编码副本，不能假定其解码RGB等同原生PNG；初次不匹配已在生成前拒绝并定位，未以近似RGB替代原生输入。

研究输出使用24fps，保持768×432。为适配模型，按真实PTS从父片末3秒以24Hz最近邻取73个原生画面，末25帧作为模型条件。该取样会在历史上下文重复部分原帧，保持首末帧的真实时间间隔，不创造历史像素、不通过重复画面填充新增时长；末显示间隔从1/16变为1/24秒须单独登记。这是显式的研究时基适配，不称为原生16fps，也不改变原片。第二窗条件只取第一窗真实输出末25帧。

## 已核验的模型与环境

官方源代码固定commit `28c771e8456341be6a213e3d1133ed1fd19bf75d`；权重为README链接的 `Skywork/SkyReels-V3-V2V-14B`，HF revision `68def6119d5731ab5f11faeda18a4a6bf65ff52e`。ModelScope固定版本的LFS大小/SHA与HF交叉一致。只下载单镜头续写、T5、VAE及其配置/分词器，约40.468GB，不下载shot_transformer或其他任务权重。每个文件完成SHA256后才准入。

DiT共14,288,491,584参数，原生BF16权重28,576,983,168字节。官方默认先建立FP32模型，单模型初始化约57.154GB；本机32GB物理内存、当时仅约11.6GB剩余commit，不能照搬此加载路径。`--low_vram`也先建模再量化，不能解决初始化峰值。

采用隔离的meta初始化、mmap绑定和按块传输，保留官方BF16权重值，不量化。官方原有`.to(cpu)`会重新分配CPU权重，因此另在试验目录绑定返回原mmap存储的传输适配器，保留官方forward与block offload顺序。真实小型Wan GPU探针先RED确认原CPU存储指针丢失，再GREEN验证所有指针恢复，非零输出与原生参考逐值相同，重复推理也相同；它仅验证传输正确，不是14B视频或连续性通过。

实际14B加载还暴露当前safetensors/PyTorch Windows映射路径的access violation，发生在`get_tensor`访问`UntypedStorage.__getitem__`，两次均未到生成intent。隔离helper改为显式ACCESS_READ映射、校验完整BF16 header/offset/shape后建立只读视图，避开该存储切片路径。新映射及其与按块传输的组合均经RED/GREEN，保持checkpoint字节与小型GPU输出精确一致；实际第一步14B推理已完成后才登记可运行，未将加载失败描述为视觉试验失败。

768×432用于与原片同尺寸对照，低于官方主推720P，不将本次效果直接当作该模型720P质量评价。

使用现有portable Python/PyTorch2.13 CUDA13底座，diffusers0.34、accelerate1.8.1、ftfy6.3.1、wcwidth0.2.14仅安装到本试验独立`python-deps`目录，没有覆盖Comfy的site-packages。使用上游已有Torch SDPA回退，不安装FlashAttention。真实import与14B meta参数计数、小型GPU forward已通过。初次import缺wcwidth后仅补独立依赖；第一次直接网络抓源码超时后改用固定版本GitHub读取，原失败记录保留。

## 固定推理与观察

沿官方单镜头续写流程：历史25像素帧/7latent，干净前缀时间步为0；CFG蒸馏8步、CFG1、shift8，seed `264244520399005`，无negative prompt。提示词只描述同一白鹭持续水平飞行与固定环境，不重复起飞/展翼完整动作脚本。保留上游每窗帧对齐算法，输出有补齐时不伪称精确5秒。

T5使用官方BF16权重与forward，先单独编码后释放整个进程；DiT推理使用已绑定的同一context。每窗单独intent，不重复启动已有intent；失败保存错误及已完成步数，不自动重跑生成。记录完整重建数组、新增数组、条件latent、每步GPU峰值与CPU权重指针恢复。

审阅副本包含历史与真实新增帧；历史和新帧分开记账，不混合接缝，不插帧或变速补长。lossless RGB编码后逐帧核验像素与PTS。静态采样只能提前发现明显问题；完整动态判断仍需真实播放，不能用MAE或小型数值探针替代。

原run3011文件在生成前后核对大小、SHA及mtime；生产378基准文件与已有全库前置身份比较。源代码、生产workflow及正式run均不修改，因此不触发新的生产修复全库；原3651通过不作为新模型质量证据。

## 证据位置

独立目录：`D:/VideoSi/cache/video-ai/logs/jim-08-skyreels-v3-validation-20261021/`。权重目录：`D:/VideoSi/models/skyreels-v3/SkyReels-V3-V2V-14B/`。

`validation-model-identity.json`记录模型、大小、SHA与授权范围；`source-identity.json`记录固定源代码；`disk-backing-red.json`及`disk-backing-green.json`记录真实传输探针。下载、准备、T5编码、每窗推理与静态采样分别记账。当前下载与准备不代表视频已经生成或连续性已通过；最终结果以本项verification当前记录为准。
