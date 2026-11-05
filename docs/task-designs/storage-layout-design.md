# 存储目录重规划方案

状态：用户已批准实施；新编号入口、制作包与独立交付、close/clean、测试及普通缓存隔离已接入。旧任务、现有模型/环境/历史缓存未自动迁移或删除。验证结果随实施计划记录。
盘点日期：2026-11-05。

## Goal

把一个视频的全部制作文件集中管理，正式交付独立保留。视频结束制作、确认不再返工后，将整个制作目录归入 `D:/VideoSi/disposable/video-ai/`，可以整体删除。公共缓存、测试、安装残留也统一归入该可清理根目录。

本版按用户确认补充“完成后整目录删除”：先前方案把主素材长期保存在 runs，只能删除工作副本；现已按视频组织制作包，并区分发布、结束制作、待删除三个阶段。

命名简化：用户只面对一个自动分配的视频编号及目录名，例如 `0001-旅行者一号`。制作、交付、待删除区均沿用同一名字；不再要求用户区分视频 ID、运行 ID、会话 ID。技术字段 video_id 使用同一个简单编号，旧协议必需的请求/运行标识保留在内部记录中，不作为新视频目录的长名称。

实施说明：以下细分类目录表示设计职责。实际版本在 `process/revisions/01/` 内沿用既有管线的 `production/`、`audio/`、`shots/`、`comfy/`、`logs/` 等分区，以保留冻结记录与恢复路径；未为了凑齐示意目录再复制一套 assets/work。视频的所有这些目录仍在同一个完整制作包内，结束后可一起清理。新任务的合成帧和超分输入/输出镜像在同卷优先采用不可变硬链接，能力不支持时回退普通副本。

“可删除”的含义：制作程序和相关测试、安装进程退出后，可以清理符合条件的子目录；不丢失正式成片、公共配置、仍需续作的素材、模型或运行环境。删除已结束视频的制作包，意味着放弃该视频原制作进度和素材返工能力。正在被进程使用的文件不属于当前可清理集合。

## Scope

包括：

- 新任务及测试、安装、诊断产生文件的目录约定。
- 模型与运行依赖从普通缓存中分离，日志按是否为运行依赖归类。
- 已有目录的分类清单、逐批迁移办法和清理入口设计。
- 优先减少逐帧复制，并将可重建工作文件与必须保留的制作资产分开。

不包括：本次实际移动或删除文件；更换视频模型、生成策略、画质或帧率；按年龄自动删除任务；删除云端 TOS 对象；对全部历史记录做路径字符串替换。

用户要求：生成视频过程中不要过度校验。空间统计不读取媒体内容、不重新计算模型摘要、不解码视频；清理检查在清理入口执行，不插入逐帧推理循环。

## Approach

### 1. 已确认的现状

| 位置/代码 | 已确认的问题及影响 |
| --- | --- |
| `D:/VideoSi/projects/video-ai/runs` | 单层枚举得到 131,528 个子目录，其中 131,386 个名称以八位日期开头。名称不能判定是否可删，不能据此批量删除。 |
| `tests/conftest.py::runtime_run` | 加载正式样例配置，直接通过 `create_run()` 在正式 runs 下创建目录，没有在该 fixture 内清理。测试产物会与真实任务混用目录。 |
| `D:/VideoSi/cache/video-ai` | 混有测试、诊断、pip/uv、HF/Torch、`uv-python`、日志与生产文本缓存。不能整体视为垃圾。 |
| `scripts/bootstrap.ps1` | `HF_HOME`、`TORCH_HOME`、`UV_PYTHON_INSTALL_DIR` 和普通临时缓存都指向 cache；其中可能含实际权重、基础解释器。 |
| `runtime/production_scene_upscale.py` | 原始帧、Comfy input 副本、Comfy output 与逐帧输出会同时存在。 |
| `runtime/_scene_composition_materialized.py` | 合成又为整个帧序列复制 PNG，重复占用随视频时长增长。 |
| `runtime/start_image_checks.py`、`_source_clip_inputs.py`、`_upscale_inputs.py` | 仍引用 `runs/20261004-040653-a0fcd961cc58/task4-acceptance.json`。这些历史材料是依赖，不能按普通旧任务清掉。 |
| `runtime/_whole_scene_admission.py` | 仍引用 `cache/video-ai/logs/vco05-20261027-native321`。这部分日志及其关联文件是依赖。 |
| `runtime/paths.py`、`config.py`、`manifest.py`、`production_state.py` | 路径校验、配置冻结、文件身份及父子任务引用绑定现有绝对路径，不能只改配置再搬文件。 |
| `projects/video-ai/productions` 等旁支目录 | 有正式项目集合、研究和预览资料，是否保留需按用途和引用归类，不能一概视为临时数据。 |

本次目录数量来自单层枚举；另做了一次只读取目录和文件大小的盘点，没有读取媒体内容：

| 目录 | 可访问文件逻辑大小（GiB） | 文件数 |
| --- | ---: | ---: |
| `projects/video-ai/runs` | 545.67 | 5,765,139 |
| `models` | 199.49 | 125,186 |
| `tools` | 60.87 | 204,492 |
| `projects/video-ai/vco08-preflight` | 36.06 | 5,624 |
| `projects/video-ai/inputs` | 7.64 | 438 |
| `cache/video-ai` | 5.11 | 854,559 |
| `projects/video-ai/continuity-benchmark` | 3.72 | 14,983 |

这些数据是逻辑大小，硬链接可能重复累计；扫描跳过 123 个链接/目录联接及部分拒绝访问路径，因此不代表精确物理占用或可回收量。主要整理对象应是 runs 中的任务资产、测试残留和实验资料，只清理普通 cache 收益有限。大量小文件还会产生文件系统额外占用。

### 2. 方案比较

| 方案 | 优点 | 局限 |
| --- | --- | --- |
| 只整理原 cache | 改动最少 | 正式 runs 仍被测试污染，媒体副本继续增长；模型与解释器仍可能误删。 |
| 新视频采用整包制作目录，完成后转入统一 disposable（推荐） | 一个视频一个制作包；交付独立；旧任务原位兼容 | 需要调整新任务的路径、工作文件和结束制作入口。 |
| 所有任务重建为全新目录体系 | 目录最整齐 | 历史绝对路径、冻结配置与继承引用迁移复杂，首期收益不抵风险。 |

推荐第二种。此选择是本方案的建议，尚不代表用户已批准实施。

### 3. 推荐目录结构

```text
D:/code/py/video-ai/                   源码、测试代码、方案文档

D:/VideoSi/
├─ models/                           所有视频共用的模型及必要资源，保留
│  ├─ comfyui/                       Wan、VAE、文本编码器、超分等
│  ├─ ollama/                        本地语言模型
│  ├─ tts/                           语音模型及 BERT/Hubert 等配套资源
│  ├─ huggingface/                   HF 模型库，保留内部目录结构
│  └─ torch/                         实际推理权重；可重建编译缓存不放这里
├─ tools/                            ComfyUI、FFmpeg、GPT-SoVITS 等，保留
├─ envs/                             Python 环境及基础解释器，保留
│  ├─ video-ai/                      调度程序环境
│  └─ python/                        承接 uv-python；先处理 venv 引用
├─ projects/video-ai/
│  ├─ config/                        公共配置、模型能力档案、本地凭证配置
│  ├─ inputs/                        多视频共用的声音、字体等素材
│  ├─ productions/0001-旅行者一号/    新视频的完整制作目录，详细见下文
│  ├─ runs/<run_id>/                 旧版运行兼容区，首期保留原路径
│  ├─ dependencies/                  公共验收依据及必要研究资料
│  └─ storage/                       视频索引、归类、迁移/清理报告
├─ output/video-ai/0001-旅行者一号/    同一个视频名字，独立交付区
│  ├─ v001/                          第一次正式发布；后续 v002、v003
│  └─ latest.json                    最新正式版本指向，只引用交付区内路径
└─ disposable/video-ai/               唯一可清理根目录
   ├─ completed/0001-旅行者一号/       同一个视频名字，已结束制作、可整包删
   ├─ abandoned/                     按同一视频名字收纳明确放弃的制作包
   ├─ cache/                         pip、uv、pycache、CUDA/Triton 等可重建缓存
   ├─ downloads/                     安装包、wheel 下载副本
   ├─ tests/                         程序自动管理测试隔离目录
   ├─ diagnostics/                   程序自动管理诊断、性能实验目录
   ├─ logs/                          不参与恢复、验收的普通启动日志
   ├─ tmp/                           程序自动管理进程/工具临时文件
   └─ trash/                         已分类旧版残留，附原始路径清单
```

现有 `cache/video-ai` 是过渡目录，迁移前不允许整目录清理。新目录不通过 junction 或符号链接伪装旧路径。进行中的制作包、公共依赖和正式成片不能落入 disposable；已明确结束制作的包才能进入 completed。

### 3.1 一个视频的制作目录

例如制作“旅行者一号”，自动分配编号 `0001`，视频目录名为 `0001-旅行者一号`。后续视频使用 `0002-名称`、`0003-名称`，编号不复用，超过四位时自然增长。程序统一分配编号以避免冲突；用户可以按编号或视频名称操作。标题修改记在 project.json，默认不重命名已有目录，避免影响引用。下文 `<video_id>` 等技术占位符均指这同一个视频编号/登记的目录，用户无需记额外标识。以下目录按需创建，不为空目录预先铺满磁盘。

```text
projects/video-ai/productions/0001-旅行者一号/
├─ project.json                      视频编号、标题、状态、输出位置
├─ input/                            本视频原始输入，不能依赖用户临时目录
│  ├─ script.txt                     制作原文
│  ├─ references/                    本视频专用参考图片、音频等
│  └─ requests/                      用户选图、修改要求等原始输入
├─ config/                           本视频配置与声音/工作流快照
│  └─ workflows/                     制作使用的工作流文件；不复制模型权重
├─ assets/                           多个修订版本之间共用的本视频素材
│  ├─ images/                        已生成的原始候选图和选定图
│  ├─ audio/                         原始语音、规范 PCM、解说音轨
│  ├─ clips/                         模型生成片段及保留的原生视频
│  └─ upscaled/                      超分主帧或无损中间结果，避免重复主副本
├─ process/                          进度、分镜、请求、选图和运行日志
│  ├─ current.json                   当前进度入口，程序自动定位制作记录
│  └─ revisions/                     内部修订记录，按 01、02 顺序组织
│     └─ 01/                        本视频内的修订序号，无全局长运行 ID
│        ├─ manifest.json            运行状态、阶段进度、素材引用
│        ├─ frozen/                  该次制作冻结的输入、配置、工作流
│        ├─ planning/                分段、时间线、分镜、提示词
│        ├─ requests/                模型请求与原始恢复记录
│        ├─ reviews/                 选图、观察和接受记录
│        └─ logs/                    本次制作的日志、诊断
├─ work/                             程序管理的可重建工作文件
│  ├─ comfy/input/                   Comfy 所需输入镜像
│  ├─ comfy/output/                  尚未登记进 assets 的服务输出
│  ├─ comfy/temp/                    Comfy 临时结果
│  ├─ comfy/user/                    本视频独占的服务数据库等
│  ├─ extracted-frames/              从保留视频可重建的解码帧
│  ├─ composition/                   合成帧序列、临时字幕、编码中间文件
│  └─ tmp/                           本视频其他临时文件
└─ previews/                         选图联系表、单镜头预览、候选成片
```

区别：`assets` 保存有价值且恢复仍需的生成结果；`work` 只保存能够从 input/assets/记录本地重建的副本。尚未登记到 assets 的 Comfy 输出不能当成可重建文件清理；请求状态未知时连同恢复事实保留。此目录结构是新版本目标，不能只把旧目录改名就直接获得这些清理保证。

同一视频的续作、失败重试和返工均使用同一个视频编号及制作包。修订记录在 process/revisions 内自动保留，当前记录通过 current.json 定位，用户不需要选择运行 ID；保持每次冻结输入、请求与接受事实独立，不覆盖旧事实。修订仅使用本视频内自动递增的短序号，相关工作文件由程序隔离，避免覆盖尚需恢复的工作输出；同一视频的写入串行化。不同修订引用同一份不可变主素材，不复制一套完整 PNG。Comfy 如必须使用本地模型目录，仅建立受控的只读模型视图，不复制模型权重进视频包。

所有与该视频有关的生成物都必须能归入这个制作包。全局 TEMP 属于进程级工具临时区，视频专属阶段尽量显式指定到 work；不能把必须用于恢复的唯一结果留在全局 tmp。

### 3.2 一个视频的正式交付目录

```text
output/video-ai/0001-旅行者一号/
├─ latest.json                       最新发布版本，例如 v001
└─ v001/
   ├─ video.mp4                      最终视频
   ├─ video.srt                      对应字幕，延用发布协议的同名约定
   ├─ script.txt                     本版完整文案
   ├─ delivery.json                  视频 ID、版本、规格、交付文件清单
   └─ 发布收据及完成标记              延用现有协议的实际名称
```

交付区只接收正式发布结果，未通过的候选片仍在制作包 previews。已发布版本不覆盖，返工发布进入 v002。交付目录包含真实文件，不能用指向制作包的符号链接、快捷方式或路径引用代替文件；对外复制时整个 v001 即可。公共凭证和完整私有配置不复制进交付目录，制作概要可记模型标识等非敏感信息。

删除制作包后仍能播放、查看字幕和读取交付记录；交付查询不得因原 run 已移走而遍历或校验原素材。历史收据中的原始路径可以作为历史事实保留，不能成为读取正式成片的必需依赖。

### 3.3 完成后的目录如何删除

```text
制作、选图、观察、返工
  projects/video-ai/productions/<video_id>/
                   ↓ 正式发布
  output/video-ai/<video_id>/v001/       成片已独立保存
  productions/<video_id>/               此时仍保留，可继续返工
                   ↓ 明确结束制作、不再保留素材返工能力
  disposable/video-ai/completed/<video_id>/
                   ↓ 清理
  仅删除 completed 中该视频整包；output 保留
```

- “编码完成”不等于正式发布；“正式发布”也不自动等于同意丢弃制作素材。
- 结束制作须已完成交付、没有仍运行/状态未知的模型请求，且没有其他保留任务依赖这个制作包。
- 视频之间默认不建立跨视频的隐藏依赖。需要复用到另一个视频的素材，先登记到公共 inputs 或完整落入目标视频包；未完成此处理时源视频不能进入 completed。
- 同一视频下的所有 run 一起结束、一起移动，因此同视频修订之间的引用不会遗漏。
- 移动前在 storage 写明原路径和结束状态，阻止恢复入口自动重建同 ID 空任务。移动在同盘完成，通常不复制大文件；移动失败时按记录恢复，不能提前显示“可删除”。
- 整包清理后，不再支持从其旧运行进度恢复；重新制作是新任务，可能重新调用付费模型。清理不会改变已有成片。
- 停止但以后还要继续的视频，继续放在 productions。明确放弃且没有未决请求/依赖的视频，才可以进入 abandoned；不会仅因为状态 failed 就自动归类。

### 3.4 公共资源的目录职责

| 目录 | 放什么 | 保留规则 |
| --- | --- | --- |
| `models/comfyui` | Wan、SDXL、VAE、编码器、RealESRGAN 等 | 多视频共享；不随单个视频清理。 |
| `models/ollama` | Qwen 等本地语言模型的 blobs/索引 | 保留内部结构；停用模型另做管理。 |
| `models/tts` | GPT-SoVITS 权重、Hubert、BERT、其他语音配套 | 保留。 |
| `models/huggingface`、`models/torch` | 名为缓存但实际用于推理的权重 | 与可删除下载缓存分离；默认保留。 |
| `models/<其他路线>` | 当前 LongCat、SkyReels、FramePack、SVI 等 | 是否使用另列清单，不能因是实验路线便直接删。 |
| `tools` | 第三方程序和其必需运行库 | 禁止继续混入普通视频生成物。内置权重逐步统一引用 models。 |
| `envs` | 调度 venv、基础 Python；必要工具环境 | 保留；包下载缓存进 disposable。 |
| `projects/video-ai/config` | 默认制作配置、声音配置、模型能力、私有连接配置 | 保留；方案不变更凭证保管方式。 |
| `projects/video-ai/inputs` | 共享声音、字体、长期复用参考素材 | 仅放公共资源；单个视频文案进入自己的 input。 |
| `projects/video-ai/dependencies` | 程序确实依赖的验收材料及其配套文件 | 保留引用完整性；不能只是搬一个 JSON。 |
| `projects/video-ai/storage` | 活动/已结束视频索引、旧目录分类、清理报告 | 体积小，长期保留，不放大媒体。 |
| `D:/code/py/video-ai` | 源码、测试代码、文档、配置样例 | 不放成片、模型和制作媒体。 |

### 3.5 统一可清理目录的职责

| disposable 内目录 | 放什么 | 何时可删 |
| --- | --- | --- |
| `completed/<video_id>` | 已结束制作的视频完整制作包 | 整包状态完成迁移且无占用后；删除将失去原素材返工能力。 |
| `abandoned/<video_id>` | 明确放弃的未完成视频制作包 | 未决请求及外部依赖已处理且无占用后。 |
| `cache/pip`、`cache/uv` | 包缓存 | 安装进程退出后；删除可能导致重新下载。 |
| `cache/pycache`、`cache/cuda`、`cache/triton` 等 | 可重建的解释/编译缓存 | 使用它的进程退出后；下次启动可能变慢。 |
| `cache/temporal-text` | 可重建的模型文本计算缓存 | 恢复已支持缺失重建后；不能把未验证的旧缓存直接归入。 |
| `downloads` | zip、exe、wheel 及下载临时文件 | 下载/安装结束且确认不是安装后的实际程序后。 |
| `tests/<session_id>` | 整套测试 runtime、假模型、假输入、假成片 | 对应测试会话退出后。 |
| `diagnostics/<session_id>` | 无正式任务依赖的性能实验、诊断媒体 | 会话退出且不再作为正式能力依赖后。 |
| `logs` | 普通启动/安装日志 | 不被恢复、验收引用且进程退出后。 |
| `tmp/<session_id>` | 无恢复价值的进程临时文件 | 对应进程退出后。 |
| `trash/<batch_id>` | 已分类旧数据及其原位置清单 | 移动完成、无占用和依赖后。 |

这一个根目录统一管理可清理数据，但不表示运行过程中可以随意手工清空整个根目录。正式清理入口跳过正在使用的子树。

### 3.6 现有目录如何归位

以下是用途映射，尚不是已批准的移动/删除清单。

| 当前目录/类别 | 目标与处理办法 |
| --- | --- |
| `projects/video-ai/runs` | 旧版兼容区；识别真实任务、测试和固定依赖后逐批处理。活动旧任务不强行迁移。 |
| `projects/video-ai/productions/voyager1-20261104` | 当前只有项目包装文件；先保留，登记其关联 run。以后扩展为按视频集中管理的结构。 |
| `projects/video-ai/config` | 保留公共配置；历史候选配置、某视频专属配置按归属收入对应视频 config，活动引用先保持。 |
| `projects/video-ai/inputs` | 字体和共用声音保留；单视频文案/修订归对应 input；测试内容归 tests。 |
| `continuity-benchmark`、`vco07-diagnostics`、`vco07-implementation`、`vco08-preflight` | 分成“程序依赖的能力依据”和“可放弃的实验”；前者进 dependencies，后者进 diagnostics/trash。 |
| `vco06-input-preparation`、`vco06-natural-qualification`、`vco06-plan-revisions`、`vco06-usable-input`、`vco07-preparation` | 依据用途分入公共依赖、某视频制作包或已放弃实验；不按前缀批量清理。 |
| `natural-repair-candidates`、`reviews`、`research-material-imports` | 某视频专用的回对应包；公共有效依据进 dependencies；无依赖且确认放弃的进 trash。 |
| `cache/video-ai/huggingface`、`torch` | 实际权重进 models；可重建编译/下载副本才进 disposable/cache。 |
| `cache/video-ai/uv-python` | 基础解释器进 envs/python；有环境引用时先保留原位。 |
| `cache/video-ai/temp`、`tmp`、`pytest*`、`tests-*` | 归临时/测试类别，排除活动进程、生产恢复资料和特殊依赖后移入 disposable。 |
| `cache/video-ai/logs`、`review`、`semantic-review-*`、`visual-diagnosis-*` | 被代码/任务引用的资料先保护；其余分别归运行日志、诊断和可清理日志。 |
| `cache/video-ai/locks` | 按实际所有者处理；锁不是按年龄自动删除的垃圾文件。 |
| `models/tests`、`tools/tests`、`output` 中测试目录 | 迁入独立 tests sandbox；只凭已确认的测试归属操作。 |
| `tools/*/output`、`GPT-SoVITS/TEMP` | 按视频归属收回制作包；公共运行依赖原位保留，旧残留分类。 |
| `D:/VideoSi/tmp`、`git-downloads`、`codex-http` | 根目录杂项；确认下载用途和进程归属后归 downloads/tmp/diagnostics；本项目无法确认归属的继续保留。 |
| `D:/VideoSi/docs` | 先保留外部文档；本仓库文档以源码 docs 为主。若兼有运行依据，依据先登记到 dependencies。 |
| 源码目录 `tmp`、`.pytest_cache`、测试 `__pycache__` | 后续生成到 disposable/tests 或 cache；现有副本无占用后可分类清理。 |
| `models`、`tools`、`envs` 的非测试内容 | 公共资源原位保留；重复权重先判定是否硬链接，停用模型另做决定。 |

### 4. 文件分类规则

| 类别 | 放置位置 | 删除影响/规则 |
| --- | --- | --- |
| 成片、字幕、发布收据 | output | 长期保留；正常清理不触碰。 |
| 公共配置、共用声音和字体 | config/inputs | 保留，不随视频清理。 |
| 本视频原文、专用参考素材、冻结配置 | productions/<video_id>/input、config、runs | 制作时保留；正式发布的文案另存交付区；明确结束制作后可随整包清理。 |
| 已选及未选候选图、原始模型输出、音频、原生片段、超分主帧 | productions/<video_id>/assets | 制作与返工时保留，不能仅因“已有成片”删除；结束制作后随整包清理。付费模型结果不视为可免费下载的缓存。 |
| intent/request/result、未知请求标识、观察/选择记录、必要日志 | productions/<video_id>/runs 或公共 dependencies | 未决请求和仍有保留依赖时不能结束制作；公共依赖不随视频清理。 |
| Comfy 输入镜像、合成帧序列、可重建编码文件 | productions/<video_id>/work | 只有对应阶段已支持“缺失后从保留主资产重建”，且未包含尚未登记的唯一服务输出，才能单独清理；结束制作后随整包清理。 |
| HF/Torch 下的实际权重和模型资源 | models | 保留，不按缓存清理。暂不能拆分的 HF 库整体保留。 |
| uv-python、venv 基础解释器 | envs | 保留，不能当安装缓存删除。解释器迁移要同步修复环境引用。 |
| pip/uv 包下载缓存、完成安装后的安装包、编译缓存 | disposable/cache、downloads | 工具退出后可删；后续可能重建或下载。 |
| temporal-text 等阶段计算缓存 | disposable/cache | 先确认恢复允许缺失并能从保留输入本地重建；否则暂留原处。 |
| 测试运行和合成媒体 | disposable/tests | 测试进程退出后可删，与生产根隔离。 |
| 历史研究、失败任务、预览 | 原位保留，待分类 | 只有确定放弃、没有仍保留的引用且无未决提交，才退役到 trash。名称、时间、退出失败均不足以判断可删。 |

### 5. 控制持续增长

1. **先隔离测试。** 测试构建独立 `RuntimePaths/PathPolicy`，只在 `disposable/tests/<session_id>/runtime` 内写入；生产入口仍使用固定根策略。不能为了测试放宽正式命令的任意写目录限制。当前散落在 models/tests、tools/tests、output 和 runs 的测试写入也要纳入隔离。
2. **单一主资产。** 每份模型结果、超分主帧在本视频 assets 中保留一个主位置。新任务的 Comfy 输入与合成工作序列只保留引用/工作副本，不永久保存多份相同字节。
3. **优先减少复制。** 同卷、已关闭写入且约定不可修改的 PNG 工作副本优先硬链接；消费者只读。可能被工具覆盖的文件使用普通副本，禁止链接到可写模型输出。硬链接不是备份，任何后续修改都须写新文件。
4. **保留恢复事实。** 新视频索引记录 `storage_layout_version=2`、简单编号、当前修订和交付版本；修订记录位于 `process/revisions`，既有冻结/请求协议保持原格式。当前清理入口只删除明确结束的完整制作包，不在活动视频内单独删工作帧，因此不额外引入逐帧重建和重验协议。旧任务继续按原路径恢复，不能直接套用新包清理规则。
5. **不在生成过程中反复扫盘。** 阶段结束可释放已不需要且已支持恢复重建的工作文件；完整统计和历史清理在独立命令中执行。不新增逐帧 hash、全量视频解码或模型文件核验。

模型也单独列出保留清单：例如当前 `models/vco08-longcat` 约 72.25 GiB、`models/skyreels-v3` 约 37.69 GiB。它们是否仍供现有任务或能力验证使用尚未确认，不默认标为垃圾。若后续明确停用某条路线，可以在排除依赖后单独退役相应模型。工具目录与 runs 中还出现与 models 同名同大小的权重，先按文件 ID/链接关系确认是否共享磁盘块，避免把已有硬链接误判成可释放的重复副本。

发布后默认保留整个视频制作包，以支持返工；明确结束制作后，整包进入 completed。清理其可重建 work 内容不会丢失主素材；清理 completed 整包会丢弃全部制作素材与原进度，交付区不受影响。

### 6. 已接入的管理入口与边界

沿用 `python -m video_ai` 增加 `storage` 子命令：

```powershell
$python = 'D:/VideoSi/envs/video-ai/Scripts/python.exe'
& $python -B -m video_ai storage report --json
& $python -B -m video_ai storage clean --dry-run --json
& $python -B -m video_ai storage clean --json
& $python -B -m video_ai storage close --video 0001 --dry-run --json
& $python -B -m video_ai storage close --video 0001 --json
```

以上命令已接入。另支持 `storage report/clean --video 0001`，其中 clean 不带 --video 时才处理共享可清理目录。测试/安装等进程占用的内容以及未分类历史目录不自动清理。

- `report`：按保留项、可清理项、待确认项统计路径、文件/目录数和逻辑字节，显示跳过项；不默认承诺实际可回收物理空间。硬链接或稀疏文件存在时注明逻辑统计口径。
- `clean --dry-run`：只列出 disposable 内可清理子树与预计逻辑字节，同时列出占用项及原因。
- `clean`：仅清理 disposable 内允许的子树。生成、测试、安装、close 与清理入口使用同一套互斥机制，避免“检查后又开始写入”的竞争；外来进程或未明占用则跳过相关子树，不强制终止进程。
- `close`：用户明确结束一个视频的制作，将其完整制作包归入 completed；dry-run 列出交付位置、制作包大小和阻塞项。检查归属/占用/依赖、登记结束状态、整包移动和索引提交全程持有同一互斥；新 run、修订、发布和引用登记入口拒绝对正在结束或已结束的视频新增写入或依赖。入口不重新解码整片、不重新 hash 模型；复用已有发布事实，并检查交付文件存在。归档状态与移动记录要能在中断后恢复。
- 删除前确认规范绝对路径在 disposable 内，拒绝对子目录 junction/reparse point 的递归跟随；保留报告写到 `projects/video-ai/storage`。这些是清理边界检查，不进入视频逐帧循环。
- 正在运行、等待选图/观察、暂停但要继续的任务，其主资产始终保留。未知模型提交及其恢复材料也保留。
- 不提供“按旧目录名一键全删”选项；历史迁移、退役与清理分开，首期清理不自动判断哪些真实任务已被放弃。

现有索引：`storage/videos/0001.json`（视频及修订归属、状态、交付版本）、`storage/sequence.json`（不复用的简单编号）、`storage/reports/clean-0001.json`（清理结果）。旧目录分类清单及旧版运行退役表待真实归类时建立，不自动将现有 13 万多个目录判定为垃圾。索引不能单独证明文件可删；归属、引用及占用在管理入口核对。

### 7. 已有数据落地顺序

1. 先改测试和普通缓存写入，阻止继续污染正式目录；保留当前生产任务原位运行。
2. 独立生成目录级分类清单，区分真实任务、可证实的测试、待确认资料和固定依赖。日期命名的 13 万多个目录不能直接按测试目录处理，空目录也须确认非活动任务。
3. 把确认为测试残留、无引用实验、已完成安装的下载副本逐批移入 disposable/trash 或对应分类目录；报告记录来源、目标与失败项。移动本身不释放空间，清理后才可能释放。
4. 固定验收依赖先登记保护，再连同其引用闭包迁到 dependencies，修改对应读取入口和迁移脚本。只移动一个 JSON 而不处理其关联路径不算完成；首期可继续原位保护。
5. HF/Torch/uv-python 分别确认实际运行依赖后迁入 models/envs，更新 bootstrap、安装脚本和相关配置。整体保留 HF 内部链接结构；任何仍引用旧路径的环境保持原位，直到轻量启动通过。
6. 新视频采用完整制作包、独立版本化交付与 close 协议；已有 voyager 等项目包装文件先用于登记关联旧 run，旧 run 延续原协议，不重写冻结文件。对明确结束或放弃的旧视频，按索引收齐其所有旧 run/工作文件并处理外部依赖后才能退役；不宣称只移动原 productions 包装目录就清掉其全部制作文件。旧路径退役状态须能被恢复入口识别，避免被当成新任务重建。
7. 验证新视频交付与制作包已独立，才启用 close；首批清理报告剩余占用与实际磁盘空闲变化。不自动删除 models/tools/envs，也不按时间自动结束视频制作。

未分类目录继续原位保留。这允许先回收已确认可清理的空间，而不要求一次解决所有历史资料。

## Files

以下列出方案涉及的模块职责；实际改动以实施计划与当前工作区为准，未使用的候选模块不为凑齐清单而改动：

| 文件 | 职责 |
| --- | --- |
| `src/video_ai/runtime/paths.py` | 视频级根目录、嵌套 run、assets/work、disposable、dependencies、storage 的路径策略；生产/测试隔离。 |
| `src/video_ai/config.py`、`config/*.example.json` | 新布局的配置表示及旧版本兼容，避免把全部历史 cache 直接改成可删除类别。 |
| `src/video_ai/runtime/manifest.py`、`production_state.py`、`production_inputs.py` | 版本化存储布局、工作目录准入和缺失重建；旧 run 继续原位读取。 |
| `src/video_ai/runtime/storage.py`（新增）、`src/video_ai/cli.py` | 视频归属索引、结束制作、分类盘点、dry-run、清理与互斥入口。 |
| `src/video_ai/runtime/production_delivery.py`、`production_delivery_records.py`、`src/video_ai/production.py` | 独立交付包、版本化发布与关闭后交付查询；原制作目录不再是读取成片的前提。 |
| `src/video_ai/runtime/production_scene_revision.py`、`scene_revision_records.py` 及相关源素材读取模块 | 同视频多 run 的主资产复用与引用；跨视频复用须解除对可删除制作包的依赖。 |
| `src/video_ai/runtime/production_scene_upscale.py`、`_scene_upscale_records.py`、`scene_media_records.py` | 区分超分主结果与 Comfy 工作副本，支持工作文件重建。 |
| `src/video_ai/runtime/_scene_composition_materialized.py`、`production_scene_composition.py` | 合成工作帧、硬链接/副本策略、清理后本地重建。 |
| `src/video_ai/runtime/service_specs.py` | 新任务 Comfy input/temp/output/user 的具体位置及资源占用管理。 |
| `src/video_ai/runtime/start_image_checks.py`、`_source_clip_inputs.py`、`_upscale_inputs.py`、`_whole_scene_admission.py` | 历史依赖保护和后续 dependencies 入口。 |
| `scripts/bootstrap.ps1`、`install_windows.ps1`、`install_online.ps1`、`migrate_windows.ps1` | 缓存/解释器/模型环境变量归位；安装与迁移采用相同分类，参与清理互斥。 |
| `tests/conftest.py` 及其他直接写正式根的 fixture | 测试 sandbox 及退出后的清理，禁止污染生产。 |
| `tests/unit/test_storage.py`、`tests/integration/test_storage_lifecycle.py`（新增） | 清理范围、引用保护、并发占用与重建恢复的有限回归。 |
| `README.md`、`config/README.md`、`docs/windows-migration.md` | 目录说明、清理命令及删除影响。 |

## Tests

实施采用针对性存储、目录、配置、CLI、发布、安装迁移和合成协议回归，不运行真实模型推理。具体命令与测试结果记录在 `docs/superpowers/plans/2026-11-05-storage-layout.md`。

```powershell
$python = 'D:/VideoSi/envs/video-ai/Scripts/python.exe'
& $python -B -m pytest tests/unit/test_paths.py tests/unit/test_storage.py tests/integration/test_storage_lifecycle.py -q -p no:cacheprovider --basetemp D:/VideoSi/disposable/video-ai/tests/storage-check
& $python -B -m video_ai storage report --json
& $python -B -m video_ai storage clean --dry-run --json
```

预期：测试通过；测试阶段没有新增正式 productions/runs/output/models/tools 产物；报告无媒体内容读取和模型调用；dry-run 不改文件。

生命周期用例在专用测试 runtime 内覆盖：

- 清空工作文件后，用保留资产重建超分输入和合成帧序列；生成结果不重复请求，正式交付文件保持可读。
- 清理与生成/测试/安装互斥；活动项跳过；junction 越界目标不删除。
- 父子任务继承、固定历史验收、未知提交材料不会被归到可清理项；旧 run 仍从旧路径恢复。
- 硬链接工作副本删除不影响主资产；需要改写的工具采用独立副本。
- 模拟批次迁移中断可根据报告恢复，不出现覆盖源数据或误认迁移成功。
- 同视频多个修订 run 全部在一个制作包内；close 后整包进入 completed，清理后各发布版本仍可读取，无须存在旧 run。
- 存在跨视频引用、未决提交、未正式发布或写入占用时，close 不能将其显示为可删除。
- 结束状态记录和移动之间任一步中断，都能恢复到明确位置，不丢包、不生成同 ID 的新空任务。
- close 与并发新 run/修订/引用登记互斥；不存在检查通过后又写入待删除制作包的窗口。

涉及 bootstrap/安装/迁移改动时，另运行现有 `tests/integration/test_migration_windows.py` 与 `tests/integration/test_online_install.py` 的相关用例。仅做轻量 Python 启动、配置读取和工具版本检查，不为了目录调整重新跑一次完整视频。

## Acceptance

- 新测试、独立诊断和普通缓存只产生在 `disposable/video-ai`；视频专属资产、工作文件和日志集中在该视频制作包，不再向正式 runs 累积测试目录。
- 一个新视频对应一个完整制作包；结束制作后可整包归入 completed 并删除，无需到多个公共目录找残留。
- 清理只需认准一个根目录，正常清理入口不会接收任意用户路径，也不会触碰 models/tools/envs、活动制作包、公共素材和成片。
- 删除非活动 disposable 内容后，程序能正常启动；保留任务能继续制作，缺失工作文件在本地重建，无额外付费生成。
- 旧任务冻结输入和请求事实未改写，历史依赖仍可读取；未分类的旧数据不会自动迁移或删除。
- 已结束视频的制作包删除后，成片、字幕、文案、各正式版本和发布记录仍可独立读取；原运行恢复明确显示已结束/已清理，不自动重新付费生成。
- 存储报告能解释主要占用分别属于哪些类别；首批清理有实际释放结果，无虚构回收量。
- 不新增生成过程中的反复全量扫描、模型摘要计算或视频解码检查。

## Risks

- 保留完整返工能力意味着主素材仍会占空间；发布默认保留制作包，明确结束制作后才允许清理。用户已授权实现，但本次未结束或清理任何真实视频。
- 13 万多个日期目录的真实任务/测试比例未确认；现有大小统计为可访问文件的逻辑字节，可回收物理空间仍待分类，不能把目录数当作删除依据。
- 历史记录包含绝对路径和内容身份；强行迁移可能使恢复失效，因此默认原位兼容。
- 现有 cache 含权重、基础解释器和运行证据。新目录规则只有在迁移与恢复改造完成后成立，不能回套到全部旧 cache。
- 硬链接文件逻辑大小会重复累计，删掉一份链接未必释放磁盘块；实际释放以卷空闲空间变化辅助衡量。
- 某些第三方工具临时目录可能不服从环境变量，需在其启动参数中显式指定；尚未接入互斥机制的外部进程在清理时保守跳过。
- 具体可回收空间、用户希望保留哪些旧项目、是否需要离线重装包，均未确认；这些影响首批清单，不妨碍先隔离新增产物。
