# LVA-01 离线交付历史快照

2026-11-15，当前状态 **COMPLETED**。本文件记录离线交付时的证据和限制。随后用户明确回复“同意，按这个做吧”，真实新实验现已技术执行完毕，16次原生/1424帧超分/12份1080P，最终父子质量已获用户确认；当前实机数据见 [LVA-01-gpu-results.md](LVA-01-gpu-results.md)。**LVA-01 原质量本地基线与校验台账已完成**；没有付费调用或恢复暂停生产，未改动生成业务代码和用户已有的冷准入改动。

机器可读汇总：[LVA-01-results.json](LVA-01-results.json)。设计：[LVA-01-design.md](LVA-01-design.md)。调用点/独立拦截价值：[LVA-01-validation-ledger.md](LVA-01-validation-ledger.md)。已冻结并执行的实验协议：[LVA-01-gpu-experiments.json](LVA-01-gpu-experiments.json)。

## 历史离线交付内容与边界（真实实验前）

- `src/video_ai/runtime/local_video_metrics.py`：显式上下文，当前线程、原始事件上限、全调用点聚合、源码/调用者定位、嵌套耗时与实际文件身份哈希、完整/范围解码分类。无新增文件验证、参数修改或证据格式变更。
- `src/video_ai/runtime/local_comfy_metrics.py`、`scripts/observe_local_comfy.py`：独立实验进程的图像/文本/high/low/VAE/编码/超分节点、模型load/unload方法调用墙钟和设备级GPU采样。保持native启动顺序和方法描述符；完成节点即刷新聚合checkpoint，Windows强停明确保留部分状态。未实际启动Comfy或GPU，实机兼容性待验证。
- `summarize_samples`：normal/recovery、cold/warm 分开计算 P50/P95、每可用视频秒墙钟成本、失败/重做率，人工等待单列；质量不通过不计可用秒。汇总接口已测试，**真实数值尚未采集**。
- `scripts/benchmark_local_video.py`：新的 scratch 隔离 fixture，FFmpeg/FFprobe 白名单及禁网；每条件4次开关对照，输出 JSON/Markdown。样本是合成媒体，不是三类真实质量 fixture。
- 新增单元及真实媒体/隔离生成恢复测试；没有删除或合并生产校验。

提示词、HTTP body、密钥、异常消息、原始命令行和输入路径不写入观测报告。基准报告中的路径仅定位新建的合成 fixture。未跟踪 Comfy 子进程、已有 HTTP worker 或命名文件身份 helper 以外的像素缓冲哈希；缺失项显式列出。原始事件有上限，不宣称总内存的硬上限。

## 离线媒体开关对照

Windows 11，Python 3.12.10。样本为128×72、16fps、9帧 testsrc2 视频，保留全部帧。工具 SHA、每次样本、源/产物 SHA 见 `E:/VideoAI/scratch/logs/LVA-01-offline-reviewed.json`，同目录 `.md` 为对照表，`LVA-01-offline-reviewed-calls/` 为逐次观测。

| 条件 | 不开启追踪均值 | 开启追踪均值 | 观测/未观测比 | 每侧次数 |
| --- | ---: | ---: | ---: | ---: |
| inspect/trim/末帧正常媒体流程 | 0.313208s | 0.790512s | 2.524 | 4 |
| 已有媒体新作用域完整读取 | 0.083228s | 0.223697s | 2.688 | 4 |

开关两侧输出 SHA 完全一致，源文件未变化。磁盘缓存未清空，顺序交替；这不是 GPU 冷/热运行，也不是 durable intent 恢复的性能结论。**追踪扰动显著，性能墙钟必须使用未开启追踪的对照；追踪时间只供所选函数的诊断，不能外推真实耗时排名或加速倍数。**

复现（指定新的输出名，已有报告拒绝覆盖）：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_local_video.py --output E:/VideoAI/scratch/logs/LVA-01-offline-repeat.json
```

## 隔离生成与原任务恢复调用数据

使用真实本地 FFmpeg、极小模型身份 fixture 和内存 Comfy transport，走现有 `produce_scene_clips`，3个场景生成到 `awaiting_continuity_review`；没有伪造人工质量接受。重入恢复仍等待同一审核，POST 数、GET 数及服务 ensure 数保持原值，原 clip 证据字节保持一致。真实 GPU、网络吞吐和完整影片均未测量。

| 所选当前线程指标 | 正常生成 | 已有产物恢复 |
| --- | ---: | ---: |
| manifest.hash_file 入口 | 13,545 | 1,383 |
| 实际文件身份 SHA 计算 | 6,704 | 1,771 |
| 实际哈希字节 | 52,311,601 | 39,821,990 |
| FFprobe 命令尝试 | 38 | 17 |
| 无范围限制的完整验证解码尝试 | 64 | 28 |
| 有范围限制的解码尝试 | 6 | 6 |
| 媒体进程尝试总数 | 79 | 34 |
| 模型/tool stamp metadata 检查 | 952 | 28 |
| 独立哈希文件路径数 | 240 | 228 |
| 保留原始事件 / 超限细节 | 20,000 / 35,982 | 8,021 / 0 |
| 观测异常 / 调用点聚合完整 | 0 / 是 | 0 / 是 |

报告保存在 `E:/VideoAI/scratch/logs/LVA-01-production-reviewed/normal.json`、`recovery.json` 及同名 Markdown。正常路径超限的原始事件细节没有被假装完整；全调用聚合未丢失。入口数不能直接相减求缓存命中率：实际 SHA 还包含直接 `protected_bytes` 读取，而入口数仅计 manifest.hash_file。

候选放大路径很明确：正常路径从 `scene_clip_records.py:178` 的 guard 调用 `validate_artifact` 6,270次，从 `:126` 的全局依赖循环调用6,030次。它们包含路径/来源/内容等不同层次，不能把整个调用删除；LVA-02 应先界定被强保护的相同依赖闭包，再保留持久化和晋升边界。模型 stamp 是 metadata 检查，不是重复读取数十GB模型。`_technical` 已有 `@inspection_reuse()`，完整探测复用不是本次新收益。

## 验证与审查

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -u -X utf8 -m pytest tests/unit/test_local_video_metrics.py tests/integration/test_local_video_metrics_flow.py tests/unit/test_scene_comfy_send_checks.py -q -s -p no:cacheprovider
```

**27 passed / 120.07s**。日志 `E:/VideoAI/scratch/logs/LVA-01-tests-final.txt`。覆盖缓存实际计算、无额外读取、敏感文本不泄漏、异常清理、不覆盖已有 profiler/报告、事件上限与聚合、样本分组/人工等待/质量失败、完整/范围解码，以及原请求恢复无重发。

既有媒体性能测试排除一项已知 fixture 错误后 **22 passed、1 deselected / 4.75s**。该项 `tests/unit/test_scene_media_performance.py::test_owned_service_cache_identity_rejects_pid_reuse` 单独运行仍失败：它用 `object.__new__(_OwnedService)` 构造对象但没有设置 `process_identity`，现有业务方法在 `production_scene_clips.py:202` 抛 AttributeError。单独复现没有导入新观测器；未为本任务改写无关业务代码或测试。日志 `LVA-01-existing-failure.txt`。未运行全库测试。

独立审查发现一个 Important：rawvideo 单帧输出被误算为完整解码。已用7个先失败后通过的分类用例修正，并重跑上述整合验证；复查无剩余 Critical/Important。没有以离线软件通过替代 GPU 或人工质量验收。

Comfy观测入口另有 **6项stub单元测试通过**，日志 `E:/VideoAI/scratch/logs/LVA-01-comfy-harness-tests.txt`；与既有13项观测单元和1项小型媒体整合共同验证为20项通过（0.53s）。审查发现的native allocator/torch启动顺序、Windows强停丢失最终summary两项Important，分别用启动顺序和退出前checkpoint的先失败后通过测试修正，复查无剩余重要问题。节点墙钟不执行CUDA同步；load/unload计方法调用而非物理权重全读；GPU峰值是设备级采样值，不保证本进程独占。强停的在途节点不算完成。

授权后新服务的具体启动入口如下；此命令尚未执行，也不自动提交任何图谱：

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/observe_local_comfy.py --experiment-root E:/VideoAI/scratch/benchmarks/LVA-01-gpu-session-01 --port 8189 --max-seconds 7200
```

该入口要求目录全新，将日志/节点checkpoint写入其中，并只停止它持有的新子进程。固定输入的请求/图谱应在用户确认后冻结，并以原durable intent恢复规则接入实验；启动器本身不执行提交、验收、超分或合成。原服务和生产生命周期不变，不能把此常驻诊断进程的热实验当作原生产端到端收益。

## 尚需完成及用户介入

1. 确认低运动、高运动、父子续接三组已选图与原质量请求，冻结图像/prompt摘要、seed、尺寸、完整帧预算和工具/模型身份。目前协议中的身份为 null，不能视作实际 fixture 或直接执行。
2. 用已提供的独立观测入口验证本机Comfy兼容性，并在上述已冻结输入上连接试验编排、确认原质量图和环境。生产侧生命周期保持不变；若新进程只有磁盘缓存热，不能登记为模型热运行。
3. 用户明确允许**新实验 run** 的真实 GPU 推理后，各组冷启动1次、热运行至少3次；不恢复旧生产、不重发 unknown、不调用付费 API。父子链人工确认父片后才能提交子片，等待单列。
4. 用户人工确认运动、角色/纹理、闪烁、颜色及续接质量；结合完整帧/PTS、超分1080P和交付数据，填写真实 P50/P95、有效秒成本、失败/重做与等待分离的端到端基线。

任务验收①的调用台账及④的离线行为保全已有证据；②的实机整体指标、③的三类真实 fixture/冷热实验仍缺少。任务保持 IN_PROGRESS，LVA-02 不提前置 READY，也不写未成立的后继交接。
