# 重复读取与重复校验问题交接

> 后续现场更新：见 [2026-11-11 审核加载耗时交接](2026-11-11-review-loading-performance-handoff.md)。该次提交第 1 条审核记录运行约 6 分钟仍未完成，用户要求暂停视频生成，交由下一任务修复。

更新时间：2026-11-09 14:44（北京时间）。工作目录：`E:\code\py\video-ai`。

## 交接目标

彻底解决生成视频时的重复文件读取、重复哈希和历史修订递归遍历问题。用户明确要求：**“生成视频的过程中不要过度校验”**。用户反馈图片阶段已耗时约 20 小时，要求由另一任务专门解决性能问题。

不要继续以“进程还活着”为依据长期等待。先确认实际耗时调用链，减少重复工作，再证明真实流程变快。不要通过关闭全部校验、伪造审核、缩短原片或改成幻灯片来规避问题。

视频目标已由用户暂停。本次交接没有恢复该目标。

## 接手时的稳定状态

- 原视频：`E:\VideoAI\work\0002-旅行者2号-即梦版`。
- 当前可用修订：`process\revisions\08`，已实际返回 `revision_ready`，`error=null`，来源是 07 版。
- 08 版就绪文件：`production\scene-revision\ready.json`。
- 137 镜的首轮图片全部生成、实际查看过；110 镜已经按前 3 批正式接受，最后一批有 23 镜已查看并记录选择。**133 镜可复用，不等于 133 镜均已正式接受。**
- 仅 4 镜需替换：`scene_0011`、`scene_0012`、`scene_0038`、`scene_0042`。
- 交接检查时，上述 4 镜在 08 版中均为：`intent.json=0`、`accepted.json=0`、原始输出图片数为 0。尚未提交这 4 镜的付费生成请求。
- 原文、完整配音和时间线已保留：137 个分镜、298 个语音单元、17824 帧 / 16 fps，约 18 分 34 秒。不要重新规划整片或重新合成配音。
- Wan 视频片段、放大和最终视频合成尚未开始。最终成片不存在，不能报完成。

### 后台进程已停止

暂停目标不会自动保证后台 Python 退出，因此交接前做了受限停止：

1. 确认 4 个替换镜头均无付费意图。
2. 确认进程命令行为本任务的 `finish_reference_images_and_start_video.py 4 08`。
3. 仅停止实际 Python PID `33060`，统一执行 session `42443` 已返回终止码 `-1`。

最新日志：

`E:\VideoAI\scratch\logs\voyager2-reference-video-admitted-structure-reuse-d23ce4c9cd704c388da4abd5675da8e6.log`

不要继续轮询旧 session `42443`、`41129`、`54464`、`96053`、`56806`，它们均已终止。PID 也可能复用，任何后续进程操作必须重新验证命令行。接手前可只读确认有没有其他新任务，不要按名称结束所有 Python。

## 已测到的证据

### 1. 继承记录高度重复

对 08 版 `production\scene-revision\imports\*.json` 做了不读取媒体内容的统计：

| 指标 | 结果 |
| --- | ---: |
| import 记录数 | 246 |
| `source_json_snapshot.files` 与 `raw_files` 中的文件引用条目合计 | 509820 |
| 这些条目中的唯一文件路径数 | 3167 |

**数字的准确含义是“记录中的引用次数”，不是已经实测的 hash 调用次数或磁盘读取次数。** 不要把 509820 次引用直接写成 509820 次实际读取，也不要据此编造全部 20 小时的时间分布。真实重复读取另有下述调用栈证据；仍需要补按阶段的调用计数和耗时。

复现统计（只读，不读密钥，不哈希媒体）：

```powershell
@'
import json
from pathlib import Path
root = next(Path('E:/VideoAI/work').glob('0002-*')) / 'process/revisions/08/production/scene-revision/imports'
records = list(root.glob('*.json'))
paths = []
for path in records:
    value = json.loads(path.read_text(encoding='utf-8'))
    paths.extend(x['path'] for x in value.get('source_json_snapshot', {}).get('files', []))
    paths.extend(x['path'] for x in value.get('raw_files', []))
print({'imports': len(records), 'references': len(paths), 'unique_paths': len(set(paths))})
'@ | .tools/python/python.exe -
```

### 2. 补 4 镜仍先进行整套来源读取

交接前实际进程 `33060` 的调用栈为：

```text
finish_reference_images_and_start_video.py:43 main
  load_frozen_inputs
    validate_revision_structure
      verify_artifact
        artifact
          safe_path / hash_file / 文件读取
```

此前同一工作流还多次观察到：

```text
load_prepared_inputs
  require_scene_revision
    validate_revision_structure
    capture_origin / RevisionGuard.capture / verify_captured_bytes
      hash_file / protected_hash / hashlib.file_digest
```

以及：

```text
generate_reference_candidates
  reference_candidates
    resolve_reference_prompt
      effective_image_prompt
        load_frozen_inputs(来源版本)
          validate_revision_structure
```

后一个提示词继承路径已局部修改，见“已做修改”。首次加载和来源捕获仍然很重，不能把问题说成全部解决。

### 3. 局部修订的多个阶段重复付出读取成本

07 → 08 修订进程实际依次经过：

```text
source_reference_context
_snapshot
_capture_origins
copy_media / copy_identity
for capture in captures.values(): guard.verify_captured_bytes()
freeze_inputs / load_frozen_inputs
_admit_created_revision
再次 for capture in captures.values(): guard.verify_captured_bytes()
ready.json
```

08 已真实创建成功，但过程中大量时间耗在本地来源校验，不是云端一直在出图。

## 重点代码与未解决热点

行号可能因修改偏移，请用函数名搜索。

| 文件 / 入口 | 需要检查的问题 |
| --- | --- |
| `src/video_ai/runtime/scene_revision_records.py`：`validate_revision_structure`（约 280 行） | 遍历全部 import，逐项验证快照、原始文件、复制文件、目录清单，重复路径多。最新修复只覆盖本进程已经完成 admission 后的复用；首次加载仍完整遍历。 |
| 同文件：`require_scene_revision`（约 432 行） | 构造整个继承证明，递归祖先版本，对每个 import 再捕获来源。检查结构、证明与捕获闭包之间是否有大量重叠。 |
| 同文件：`revision_read_transaction`、`revision_read_matches`、`revision_read_checkpoint` | 事务出口会重新调用登记的输入加载器和 guard；checkpoint 会暂时关闭读取事务复用。需要检查出口/checkpoint 是否又放大为全链重读。 |
| 同文件：`RevisionGuard.capture`、`verify_captured_bytes` | 不同 guard 的文件集合高度重叠。现有缓存按 guard 去重，并不等于按唯一文件去重。还会递归祖先 guard。 |
| `src/video_ai/runtime/_scene_revision_origins.py`：`capture_origin`（约 348 行） | 约 387 行无条件捕获时间线所有 PCM；处理一个图片节点也带入整段配音。评估是否能由共享 common 证明承担，而不是每个镜头重复。 |
| 同文件：`capture_origin` 尾部（约 479–497 行） | 修订来源会把 `production/scene-revision` 加入待遍历目录，再递归捕获 JSON 和非 JSON 文件。历史复制媒体、原始证据可能被每个节点再次纳入。需要梳理真正依赖闭包，不能直接删路径绕过不变量。 |
| `src/video_ai/runtime/production_scene_revision.py` | `_snapshot`、`_capture_origins`、`copy_media`、冻结、admission 及两次 captures 循环之间重复读取；约 468、496 行两次全 capture 检查仍存在。 |
| `src/video_ai/runtime/_scene_revision_copy.py`：`copy_media`、`copy_identity` | 现有批次作用域并非跨所有 import 的全局唯一文件复用；复制仍需检查单文件身份与字节，但不应每复制一张图重复读取全部共同来源。 |
| `src/video_ai/runtime/_scene_revision_reference.py`：`source_reference_context` | 已加读取事务，但递归来源仍可能重新 `load_frozen_inputs`。检查能否使用已 admitted 的 `source_frozen`。 |
| `src/video_ai/runtime/image_selection_records.py`：`_run`（约 61 行） | 通过 `revision_read_matches` 登记完整 `load_frozen_inputs` 回调；事务出口/checkpoint 会再次调用。 |
| `src/video_ai/runtime/production_reference_images.py`：`_operate` | 每镜一个 checkpoint transaction；复用已有候选仍会先做来源检查和存储对象处理。完成图片不应因遍历批次再次请求模型。 |
| `src/video_ai/runtime/manifest.py`、`verification.py`、`_continuity_byte_guard.py` | 真正哈希和读取发生处。`_captures` 激活时会故意禁用部分复用，避免漏捕获依赖；任何新优化必须保留依赖观察语义。 |

## 已做修改：不是全部问题已解决

这些修改均在当前工作区，未提交；仓库还有大量其他改动。**不要 reset、clean 或回退不相关文件。** `.tools` 内脚本可能被忽略，不一定随 Git 提交走，接手任务应使用当前工作区。

1. `_scene_revision_reference.py`：`source_reference_context` 包在本地读取事务中，减少同一读取阶段重复验证 guard。
2. `production_scene_revision.py`：`_snapshot`、`_capture_origins`、`_admit_created_revision` 已使用读取事务。最终 captures 循环等仍需检查。
3. `_scene_revision_copy.py`：`copy_media` 已使用 `revision_checkpoint_transaction`；不要仅依据旧交接假定仍是只读 transaction，应看当前代码。
4. `scene_revision_records.py`：`require_scene_revision` 在已完成的证明中保留 `source_frozen`；`scene_image_prompts.py` 使用它继承提示词，避免为提示词再次完整加载来源。
5. 最新修改：`validate_revision_structure` 在同一 revision scope 已存在完整 admitted proof 时，比较精确的 options digest，调用原 guard，然后复用已解析结构。普通 rendering 路径启用，特殊 rendering mode 保留旧 admission 路径。

最新修改**没有**消除首次 admission 的全部重复工作。交接时新进程仍停在首次 `load_frozen_inputs`，还没有真实端到端加速的证据。不要将单元测试通过等同于生产性能已修复。

### 已跑测试与限制

最近命令：

```powershell
$env:PYTHONPATH='E:/code/py/video-ai/src'
.tools/python/python.exe -m pytest tests/unit/test_revision_copy_transaction.py tests/unit/test_scene_revision_records.py tests/unit/test_reference_settings_empty.py tests/unit/test_focused_image_prompts.py -q
```

结果：**66 passed**。

新增结构复用回归用例先失败、修复后通过，覆盖多次加载复用、文件被改写后恢复时间戳仍能被拒绝、`1` 与 `true` 等类型改变仍被拒绝。

尝试的两组集成测试：

```powershell
.tools/python/python.exe -m pytest tests/integration/test_scene_revision_flow.py tests/integration/test_scene_image_prompt_revision.py -q
```

结果：**41 个 setup error，不能算通过。** 测试隔离 runtime 与示例配置中的 `E:/VideoAI/shared/tools/ffmpeg/bin/ffmpeg.exe` 路径不匹配，触发 `PathPolicy.validate_write(..., 'tool-env')`。未跑到本次修改，不应把它说成本次功能失败或功能通过。接手时用隔离测试资源修复/适配测试环境，不要为了跑测试修改真实生产配置或真实模型文件。

## 建议执行顺序

1. 阅读本文件、相关 diff 和项目 `AGENTS.md`。视频目标保持暂停，当前任务优先处理重复读取。
2. 在不调用付费 API、不生成视频的本地诊断入口中，对真实 08 版的首次加载、重复加载、checkpoint、继承来源捕获分别计时。统计实际 hash 调用次数、每路径次数、读取字节数、目录遍历次数和阶段耗时。不要打印密钥或完整环境变量。
3. 先解决首次加载与祖先闭包放大，不要只修提示词这样的下游热点。区分共同依赖、镜头独有依赖、动态写入记录，避免所有节点递归继承整个历史工作目录。
4. 把重复检查收敛到清晰的阶段边界。缓存必须有明确生命周期、原始基线、失效条件和线程/上下文规则；不能仅靠 mtime 或跨网络/写入盲目复用。
5. 补针对真实热点的计数测试和必要集成测试，测修复前后相同路径的实际耗时。不要反复跑全套测试或重新审图来证明性能修复。
6. 给用户具体结果：哪里不再重复读、实际计数与耗时如何变化、仍有什么限制。性能专项结束后，再由用户决定何时恢复视频目标。

### 专项验收条件

- 同一只读阶段重复加载同一已验证版本，哈希/目录扫描次数不随调用次数线性重复。
- 首次加载的重复路径处理接近“唯一依赖文件集合”，不能因为 246 个 import 将 3167 个路径反复解析几十万次。
- 来源修订链加深时不出现递归指数放大；至少比较多层继承的计数趋势。
- 单镜头操作不无理由读取全片配音和所有历史复制媒体；共享依赖由共享证明承担。
- 文件字节变化（包括恢复 mtime）、目录新增/删除、原本缺失的文件出现、路径重定向、文件替换、typed options 变化仍能被捕获。
- 网络付费提交、复制写入、选择接受等边界仍有必要的身份和输入检查；不重复提交已经 accepted 或状态未知的云任务。
- 给出真实阶段基准，不只给测试通过数。不必为了基准完成整部付费视频。

## 素材与恢复视频所需入口

这里只交接恢复入口，不代表现在获准恢复已暂停目标。

- 23 镜已查看的选择：`.tools/voyager2-07-batch4-reviewed-choices.json`，包含 scene/candidate/SHA256。
- 4 镜问题和具体替换提示词：`.tools/voyager2-07-batch4-image-corrections.json`。
- 已完成的修订请求：`.tools/voyager2-07-batch4-image-correction-revision.json`。**08 已就绪，不要重建第 09 版或再次提交这个请求。**
- 视频历史执行记录：`docs/superpowers/plans/2026-11-08-source-bound-scenes.md`。尾部包含最新状态，较早日志和句子可能已过时，应以本文件快照和实际文件为准。
- 连续执行脚本：`.tools/finish_reference_images_and_start_video.py 4 08`。
  - 复用已有图片，只生成需要的 4 镜；
  - 准备本地选图记录后，持有同一 RunLock 等待 `.tools/voyager2-08-batch4-selection.json`；
  - 使用原 `consume_image_selection` 接受真实选择；
  - 仅 `all_images_accepted` 后调用原 `produce_scene_pipeline`，进入 Wan / upscale / composition。
- 4 张替换图实际查看后，把选择写到 `.tools/voyager2-08-batch4-corrected-choices.json`，然后运行：

```powershell
.tools/python/python.exe .tools/assemble_batch4_selection.py 08 .tools/voyager2-08-batch4-corrected-choices.json
```

该脚本把 23 个保留选择与 4 个实际替换选择绑定到正常批次模板；写出 selection 后，会唤醒上述连续脚本。**不要提前伪造 4 张图的已查看记录，不要在同一 RunLock 上再启动第二个视频进程。**

运行生产 helper 的环境入口（用户恢复视频后再使用）：

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
. E:/code/py/video-ai/scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'repeated-read-fixed-resume'
Invoke-VideoAiNative $VideoAiPython @('-B','E:/code/py/video-ai/.tools/finish_reference_images_and_start_video.py','4','08')
exit $script:VideoAiExitCode
```

保持即梦图片 **4.0**：`jimeng_t2i_v40`。不切 4.6，不重做全部图片，不发送邮件。凭据在项目本地配置与环境中读取，不要输出内容。模型服务权限先前已恢复，不要把本地读取慢误诊为额度或权限不足。

## 交接给新任务的简短指令

> 请阅读 `docs/handoffs/2026-11-09-repeated-read-handoff.md`，在当前工作区彻底解决修订继承导致的重复文件读取、重复哈希和历史目录递归遍历。先用真实 08 版做无付费请求的阶段计数与基准，保留必要的完整性检查，修复首次 admission 与跨节点共同依赖放大，并给出前后证据。视频目标已暂停、后台进程已在无付费意图边界停止，不要擅自恢复视频或重做 133 镜已有素材。
