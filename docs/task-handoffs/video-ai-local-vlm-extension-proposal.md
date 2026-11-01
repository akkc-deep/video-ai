# video-ai 本地视觉大模型审查模块追加方案

> **性质**：增量技术设计，供后续 Codex 拆任务和实施。不是已实现功能或已通过的验收。
>
> **日期**：2026-10-24
>
> **仓库**：`akkc-deep/video-ai`，本次只读核查 `main` 提交 `2292bc92eaabfc88ddd229a0c738ea6b0394ea45`。
>
> **建议仓库路径**：`docs/task-designs/video-continuity-local-vlm-addon.md`
>
> **与原方案关系**：依附正在执行的“NumPy + OpenCV / 视频连续性通用优化”方案；仅增加视觉语义审查。不得中断、重写或假定现有方案已经完成。JIM-08 原任务、历史失败与人类验收记录保持原样。

## 1. 决策摘要

**新增独立的 Local VLM Reviewer（本地多模态视觉审查器）**：CPU 连续性分析提供量化异常，视觉模型结合已接受原图、同场景文本、真实抽样帧与时间顺序，解释“是自然光照/运镜，还是主体/材质/环境/动作发生无依据变化”，输出可复核的**风险报告**，而不是改视频或宣布合格。

首选部署 `qwen3.5:9b`（Ollama 本地多模态版本）；备选 `qwen3-vl:8b-instruct-q4_K_M` 作交叉验证。量化模型下载文件约数 GB，**文件大小不等于显存占用**；实际 VRAM 还包含视觉编码器、KV cache、图像输入与运行时开销。先在 24GB RTX 5090D V2 上串行、限量试验，不与 Wan/RealESRGAN 并发。

**新增能力**：主体身份和材质稳定性、光照变化的语义合理性、镜头构图与明显运动异常提示、对 CPU 数值告警的解释、问题帧定位。**不新增能力**：精准像素色差测量、连续动作的完整视频动态观察、生成纠错、自动重试或自动发布；这些仍由现有工具/人工观察/未来专门后端承担。

## 2. 与当前仓库的边界

已核查仓库的现有机制：

- `src/video_ai/runtime/services.py` 与 `src/video_ai/runtime/service_specs.py`：已管理本地 Ollama 的启动/健康/服务所有权，默认地址 `http://127.0.0.1:11434`。**复用这个地址，不重新搭建另一套服务**。
- `src/video_ai/adapters/ollama.py`：目前主要是文本规划的结构化 transport，对规划模型和输入有严格限制。**不要把视觉接口强行塞进现有 `ollama_body()`**，新增单独 Adapter。
- `src/video_ai/planning/scene_video_prompts.py` 与 `src/video_ai/runtime/scene_video_prompt_records.py`：已出现版本化视频提示契约实现（最新仓库版本）；本追加方案只读取已审查的视觉事实，不改其 schema 或冻结逻辑。
- `src/video_ai/runtime/scene_clip_observations.py`：已有 `human_video` / `agent_video` 真实播放验收及 `color_clothing`、`time_lighting`、`motion_process`、`parent_join` 等检查。**抽样图片的 VLM 结果只作为诊断 sidecar**，不能伪装成完整视频播放，不修改已接受观察。
- 现有 NumPy/OpenCV 方案仍负责逐帧指标、运动与媒体色彩空间；本模块不复制相同计算或擅自增加新的硬性修复动作。

开发期间，优先使用独立文件、独立测试、独立试验结果目录；直到原方案接口稳定且增量测试通过，才以一个显式启用的步骤衔接生产流。

## 3. 推荐模块与最小架构

```text
Wan2.2 / 已生成 native 视频
           │
           ├───────────────┐
           ▼               ▼
CPU Continuity Report   已接受原图 / 视觉设定 / 片段文案
           │               │
           └──────┬────────┘
                  ▼
        采样规划与帧绑定（只读）
         图片、fps、源帧索引、SHA
                  │
                  ▼
         Local VLM Reviewer
           Ollama /api/chat
                  │
                  ▼
      严格 JSON schema + 检查证据
                  │
                  ▼
      独立 Vision Review Report
                  │
                  ▼
      既有观察/返工决策（不自动放行）
```

### 3.1 建议新增文件（待与进行中的任务合并去重）

| 文件 | 责任 | 先期能否独立实现 |
| --- | --- | --- |
| `src/video_ai/adapters/ollama_vision.py` | 多图本地推理、服务检查、结构化响应、超时及错误 | 是 |
| `src/video_ai/media/vision_review_sampling.py` | 从原生映射和 CPU 异常中确定抽样帧及顺序；不修改图片 | 是 |
| `src/video_ai/planning/vision_review_contract.py` | 纯 JSON schema、字段验证、提示词模板和证据引用约束 | 是 |
| `src/video_ai/runtime/vision_review_records.py` | 只读源证据绑定、模型 digest、sidecar、恢复/版本失效 | 是 |
| `scripts/review_scene_vision.py` | 独立命令行试验入口，不修改主 CLI/正式 run | 是 |
| `src/video_ai/runtime/production_scene_clips.py` | 生产集成时增加可选诊断阶段 | **后期才改** |
| `src/video_ai/config.py`、生产配置冻结及 revision 逻辑 | 生产启用时增加独立版本化策略 | **后期才改** |

注：文件名是建议，不是仓库已存在的接口。若正在执行的通用方案已经建设相同采样/诊断能力，应直接消费它的稳定公共输出，避免复制。

## 4. 模型与 Windows 本地部署

### 4.1 选择

- **优先**：`qwen3.5:9b`，为图片/文字多模态审查提供较新的基础模型；先验证多图输入及严格 JSON 实测表现。
- **回退对照**：`qwen3-vl:8b-instruct-q4_K_M`，作为视觉领域对照；不要仅凭参数规模声称哪个在当前题材上一定更好。
- 不用旧场景规划的 Qwen3 14B 纯文本接口冒充视觉输入，也不必为这项功能替换原文规划模型。

Ollama 官方提供 `images` 多图输入、`format` JSON schema 和 `keep_alive` 请求控制。量化模型文件尺寸、支持功能及所需 Ollama 版本以实际安装环境、官方模型页和实际 `/api/tags`、`/api/show` 为准。

### 4.2 环境验证（Windows PowerShell）

```powershell
# 若 ollama 已在 PATH，可直接执行
ollama --version
ollama pull qwen3.5:9b
ollama list
ollama ps

# 只有实际需要做模型对照时，再下载备选
# ollama pull qwen3-vl:8b-instruct-q4_K_M
```

服务使用当前生产配置绑定的 Ollama 地址。**不得为了审查而终止现有 ComfyUI、Ollama 或其他用户进程**。严格采用 GPU 资源锁/排队：Wan 生成完成、模型资源释放后才装入视觉审查模型；审查请求使用 `keep_alive: 0` 使该模型请求结束后尽量卸载，并检查实际显存状态。不能认为 `keep_alive: 0` 能保证其他同时请求一定立刻释放；需做所有权与资源实测。

建议首轮每次请求最多 **8 张 768×432 抽样图**、每 clip 最多 **2 次视觉调用**、非流式、`temperature:0`、明确有限的超时（例如 180 秒，仅作为初始预算），先实测显存和延迟再冻结参数。上下文长度与输出 token 上限通过真实请求校准，不为了凑长视频一次塞入全部 320 帧。提示词和模型采用版本号/摘要，不跟随可变的 `latest` 标签悄悄升级。

### 4.3 API 交互示意（独立 Adapter，不是生产提交代码）

```python
from ollama import Client

client = Client(host="http://127.0.0.1:11434", timeout=180)
response = client.chat(
    model="qwen3.5:9b",
    messages=[{
        "role": "user",
        "content": "请根据这组按顺序标注的抽样帧及场景约束，返回严格JSON形式的连续性风险诊断。只能引用已提供的帧编号。",
        "images": ["reference.png", "parent_092.png", "child_000.png", "child_016.png"],
    }],
    format=REVIEW_JSON_SCHEMA,   # 待新增的严格 schema
    options={"temperature": 0},
    stream=False,
    keep_alive=0,
)
# adapter 内必须 parse + validate；schema 拒绝时报告 unverified
```

Ollama 的 Python SDK 接受本地图像路径；如果直接使用 REST，则应把每张图片转为 base64 发送。**不把本地绝对路径当作 REST images 内容**。请求前校验模型具备图像能力；收到无法解析、字段缺失、引用不存在帧或模型异常时，输出 `unverified` 并保留原始证据，不自动升级为通过。

## 5. 关键输入与抽帧策略

### 5.1 输入（均有来源及 SHA）

- `run_id / scene_id / clip_id / parent_clip_id`。
- 已接受场景参考原图、主体/环境固定属性、必要的动作阶段、明确允许的光照/外观变化（不向 VLM 传完整审计 JSON、密钥或无关历史文本）。
- 父片和子片的 **原生 generated/retained 帧映射**：保留帧索引及时间戳，不用裁片再次编码后近似 RGB 冒充原始帧。
- CPU 诊断输出的异常时间、异常类别、可比/不可比与统计指标；指标属于数值证据，而不是 VLM 能重新测量的量。
- 精确模型 tag + digest、Ollama 版本、审查 prompt 版本、实际发送图片的 SHA 和参数。

### 5.2 两类审查

1. **接缝续接**：参考原图 1 张、父末最多3张、子片前段最多4张；例如父[-16,-8,-1]、子[0,16,32,64]，按实际存在帧裁剪，总数不超过8。时间标签标明父/子及16fps索引。
2. **整段20秒**：参考原图 1 张、全片稀疏采样若干张，优先覆盖开头、中间、末尾；CPU 报告某时刻变色或主体出框时，优先加入异常前/中/后帧。超出一次调用的图像预算时拆成有限的两次审查，不能断言未抽样区间没有问题。

抽帧采用确定性算法、固定顺序和有界图像数量，生成 sidecar manifest，保留每张图片的准确 `frame_id`、PTS、所在原片、SHA。若使用带标签的拼图，标签和未标注原生图必须有清楚的证据区分，不能让拼图操作改变原有像素测量。

### 5.3 触发策略

先做 **影子审查（shadow mode）**：现有 CPU 方案决定是否出现数值异常，VLM 对疑似异常做语义解释；同时对部分 CPU 未报警样片做抽样核查，以验证是否漏检“脸变了、衣服变了、运动阶段突然重置”等语义问题。任何 VLM 审查都不改变旧的下游行为，不额外触发模型重生成。

## 6. 提示词合同与严格输出

**系统提示必须说明**：你只看到带帧标签的一组静态抽样图和可信的场景约束；不能声称看过完整视频；必须指出具体证据帧；判断原文是否允许日落、阴影、灯光变化或新景物；不推测没有提供的时间点；无法确定写 `insufficient_evidence`。不得生成没有来源的主体身份/颜色事实。

建议 JSON 概念结构：

```json
{
  "schema_version": 1,
  "review_scope": "sampled_frames",
  "assessment": "no_obvious_issue|suspected_issue|insufficient_evidence",
  "findings": [
    {
      "category": "material_color|lighting|identity|environment|motion|camera|composition",
      "severity": "low|medium|high",
      "evidence_frame_ids": ["parent:092", "child:032"],
      "expected_change": "yes|no|unknown",
      "explanation": "必须以图片与已审查场景内容作具体解释"
    }
  ],
  "limitations": "仅抽样帧观察，不能代表完整动作审查"
}
```

备注：上面用 `|` 表示候选枚举，**并非字面值**；拆任务时要做真正的 `enum`/字段长度/最大 findings 数量/`additionalProperties:false` 严格 schema。`evidence_frame_ids` 必须存在于本次输入 manifest；不得让模型自己创建或改写未提供的帧 ID。来源 SHA、真实模型响应及审查版本由程序外层写入而不是要求模型凭空返回。

`no_obvious_issue` 仅代表**这些抽样图未见明显异常**，**不是**原系统的 `passed`，不能自动建立 `agent_video` 或 `human_video` 观察回执；`suspected_issue` 进入人工/已有审查，`insufficient_evidence` 也不得放行。

## 7. 与当前 CPU 方案的联合判定

| CPU 结果 | VLM 结果 | 处理建议 |
| --- | --- | --- |
| 未见异常 | 抽样未见明显异常 | 继续沿用原有动态验收，不自动放行 |
| 报告色差 | 判断是剧情支持的入影/日落 | 标记“可能合理”，保留原始 CPU 数值并等待审查 |
| 报告色差 | 判断主体材质/背景不合理漂移 | 标记“需要复核/返工”，提供问题帧 |
| CPU 无报警 | VLM 发现主体换脸/衣服/构图变化 | 标记语义异常，避免 CPU 漏报 |
| CPU 无法比较 | VLM 证据不足或前后场景差异很大 | `unverified`，由实际观看确认 |
| 数据/服务故障 | VLM 超时、模型未安装或 JSON 错误 | 不修改任何原视频，记录故障，走既有人工验收路径 |

建议由独立 `DecisionPolicy` 做确定性整合。不得让视觉模型直接调用 Wan、RealESRGAN、修复器或 Git 操作；如果原方案已加修复模块，只有后续显式批准的步骤才能生成**独立修复候选**，不能据 VLM 回答修改原生颜色或下一段的起始参考。

## 8. 持久化、版本与故障恢复

- 先在 `D:/VideoSi/cache/video-ai/` 下隔离试验目录写原生帧抽样 manifest、`request.json`（不保存图片 base64）、`response.json`、`review.json`、错误和必要样图；权限符合仓库现有路径所有权规则。原正式 run 只读，所有先前通过/拒绝的观察不可改写。
- 报告包括 `source_video_sha256`、帧映射版本、image SHA 列表、`cpu_report_sha256`、视觉设定/提示契约 SHA、model name+digest、Ollama 版本、`prompt_version`、结构化输出 JSON 及状态。
- 重复执行同一输入与策略时复用经过校验的原报告，不再次推理；身份发生变化时使诊断报告失效，而不是重生成未改变的源视频。推理结果不明时避免偷偷重试或重复触发收费/昂贵任务；本地视觉审查也应有最大次数和时限。
- 生产集成时添加显式 `enabled=false`（默认关闭）与独立 `vision_review_policy` 版本；新字段只影响新策略，旧冻结运行不改原请求或媒体重建。生产方案正式采用前，先与正在执行的连续性优化设计合并并冻结输入/输出契约。
- 本地图片/文案原则上不出站；不要启用 cloud 模型或远程 Ollama 地址，除非后续显式新增授权。最小化日志中的原文、私人信息和凭证。

## 9. 可独立拆分的五个增量任务

| 任务 | 交付 | 前置依赖 | 独立验收 |
| --- | --- | --- | --- |
| VLM-01 本地模型环境与 Adapter | Ollama 的视觉能力探测、多图请求、JSON schema、超时、digest | 无；不碰旧生成流水线 | 真正多图模型返回可解析 JSON；模型缺失/超时能安全结束；无外部服务被终止 |
| VLM-02 确定性取帧/证据包 | 原始帧映射、CPU 异常时间、参考图片、SHA | 可消费旧媒体记录，CPU 接口后期接入 | 首尾帧正确、索引不混淆、最多8图、无重编码伪装 |
| VLM-03 语义风险合同 | 片段级视觉提示、枚举 findings、证据校验 | VLM-01、02 | 合理光照变化不无条件拒绝、故障/幻觉帧 ID 拒绝、静帧永不冒充动态验收 |
| VLM-04 独立影子审查 | `scripts/review_scene_vision.py`、只读报告、对照基准 | VLM-01~03、实际视频样本 | 已知坏例被标记/不能自动通过；正常例不无依据硬拒绝；保存真实模型、延迟、显存和原件 SHA |
| VLM-05 条件式生产集成 | 启用开关、CPU/VLM 联合状态、恢复/版本失效 | CPU 方案接口稳定且 VLM-04 实测通过 | 旧配置请求/graph/接受记录不变；模型不可用时不阻断旧流程；没有自动重生成或发布 |

**任务执行顺序建议：VLM-01/02/03 独立开发 → VLM-04 用 JIM-08 历史真实片段影子测试 → CPU 原方案稳定后再做 VLM-05。** 不要求暂停当前正在执行的 NumPy + OpenCV 方案。

## 10. 最低验收矩阵

- **模型行为**：多图输入确实生效；JSON schema 有严格可解析字段；所有证据帧 ID 都能从原采样清单定位；不能编造缺失帧或主体事实。
- **颜色**：已知偏红、偏冷、曝光变化的旧失败片段能给出位置与风险；自然阴影、日落等允许变化不被“一律锁色”误判。
- **运动**：对于帧中可见的姿态变化能提示“疑似异常”，但不可宣称通过连续运动验收；需要真实视频完整播放。
- **完整性**：冻结源文件、原生16fps/时间轴、PCM、字幕、超分、合成、原 JIM-08 验收与发布过程不被改变。
- **资源**：24GB 显存下的真实模型加载、单张与多图测试、峰值显存、耗时、Ollama 卸载与 ComfyUI 串行资源验证有记录。OOM/超时不自动降规格重试。
- **兼容和安全**：旧 run 原字节不变；参数/版本/输入漂移能检测；服务异常不误杀其他进程；证据失效不自动改已接受记录。
- **样本泛化**：至少覆盖主体材质、光照变化、场景切换、运镜与异常遮挡的正负对照，不用单一白鸟/湖景案例宣布通用性。

成功标准是：**新增可重复的语义风险诊断，帮助定位/排除连续性问题，但始终保持现有正式动态验收。** 不承诺视觉模型可以直接修复生成模型导致的几何变形或跨窗口长期漂移。

## 11. 参考资料

- Ollama 本地图像输入：<https://docs.ollama.com/capabilities/vision>
- Ollama JSON Schema 输出：<https://docs.ollama.com/capabilities/structured-outputs>
- Ollama Chat API、`keep_alive`：<https://docs.ollama.com/api/chat>
- Qwen3.5 Ollama 模型页：<https://ollama.com/library/qwen3.5>
- Qwen3-VL Ollama 模型页：<https://ollama.com/library/qwen3-vl>
- 本仓库 `src/video_ai/adapters/ollama.py`、`src/video_ai/runtime/services.py`、`src/video_ai/runtime/scene_clip_observations.py`、`src/video_ai/planning/scene_video_prompts.py`

**实施边界重申**：本文件只提供追加模块设计，未提交 GitHub、未运行本地模型、未修改源码，也没有替代正在实施的 CPU 连续性方案或未完成的 JIM-08 验收。
