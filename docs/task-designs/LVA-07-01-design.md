# LVA-07-01：环境与 Wrapper 加载路径只读审查

## Goal

在安装和真实 GPU 投入之前，判断固定版本 WanVideoWrapper 与当前环境是否有明确冲突，以及它是否存在完整处理既有 high/low 1022 混合 delta 的路径。交付可追溯的审查结论，不预先承诺兼容、安装或提速。

## Scope

- 只读审查 Wrapper 源码、依赖声明、节点注册、模型结构要求和既有 LVA-04 权重证据；不执行节点导入、pip install、模型下载、服务启动或采样。
- 历史环境为 Windows、RTX 5090 D v2、driver 610.88、Python 3.13.14、torch 2.14.1+cu130、CUDA 13.0、Comfy 0.44.0。它是 LVA-04 的记录，审查时区分历史值与本轮只读查询值。
- high/low 身份、字节数及 SHA 取自 `docs/task-designs/LVA-04-source-research.json`；header 分类取自 `docs/task-designs/LVA-04-native-rejection-evidence.json`。不重新下载1.37GB权重或重复哈希全模型来做源码审查。

## Approach

1. 全文阅读总体专项设计、任务板本项、LVA-04 结果和两份 JSON。确认 high 的41个 diff_m 是重点，low 并未完成原生运行时准入。
2. 只读查询 Wrapper HEAD 作为候选，记录完整 commit SHA，之后所有源码引用绑定该 SHA；审阅近期提交与声明，不将浮动 main 作为安装锁定结果。网络或源码缺失记为未验证，不猜测版本。
3. 阅读 README、requirements.txt、pyproject.toml（若存在）、`__init__.py`、`nodes_model_loading.py`、`nodes_sampler.py` 及它们实际调用的转换/patch代码。分别追踪普通 LoRA、diff、diff_b、diff_m，记录函数、目标参数映射、merge/unmerge、FP8限制及未识别 key 的处理。缺失文件如实记录，不能据文件名臆测实现。
4. 核对 Python ABI、torch/CUDA、Windows wheel 与必需/可选依赖；对 Triton、SageAttention、xformers 等区分必需导入与可绕开的可选路径。只读包元数据/索引，不运行依赖安装或节点 import。审查当前 base 能否直接使用，若要求 Kijai 重打包 base，列出独立变量及待确认内容。
5. 生成审查 JSON/Markdown，给出“可以进入 CPU 验证 / 明确不支持 / 证据不足”，逐项附固定源码依据。此处不能得出“完整模型已加载”或“GPU可用”。存在不支持的 delta、必须改生产环境、依赖证据不足时，停止后续安装/推理准备，并写清解除条件。

只读取证示例（由执行者运行，本轮未运行；`$wrapperCommit` 必须取真实返回值）：

```powershell
$wrapperCommit = ((git ls-remote https://github.com/kijai/ComfyUI-WanVideoWrapper.git HEAD) -split '\s+')[0]
Invoke-RestMethod "https://api.github.com/repos/kijai/ComfyUI-WanVideoWrapper/commits/$wrapperCommit"
Invoke-RestMethod "https://raw.githubusercontent.com/kijai/ComfyUI-WanVideoWrapper/$wrapperCommit/README.md"
Invoke-RestMethod "https://raw.githubusercontent.com/kijai/ComfyUI-WanVideoWrapper/$wrapperCommit/requirements.txt"
Invoke-RestMethod "https://raw.githubusercontent.com/kijai/ComfyUI-WanVideoWrapper/$wrapperCommit/__init__.py"
Invoke-RestMethod "https://raw.githubusercontent.com/kijai/ComfyUI-WanVideoWrapper/$wrapperCommit/nodes_model_loading.py"
Invoke-RestMethod "https://raw.githubusercontent.com/kijai/ComfyUI-WanVideoWrapper/$wrapperCommit/nodes_sampler.py"
```

只读获取源码文本用于审查不等于安装；不运行远程代码。候选提交查询后立即固定，后续不重新解析 HEAD。查询失败或未得到40位完整SHA时停止，不使用空值或浮动分支继续取证。

## Files

- 读取：`docs/task-designs/LVA-07-wrapper-backend-design.md`、`LVA-04-results.md`、`LVA-04-source-research.json`、`LVA-04-native-rejection-evidence.json`。
- 拟创建：`docs/task-designs/LVA-07-environment-review.json`、`docs/task-designs/LVA-07-environment-review.md`：环境/依赖兼容矩阵，四类 patch 的固定源码依据，两个专家的适用结论、阻断项及 CPU 验证建议。这是将来交付路径，当前没有结果文件。
- 更新：唯一任务板本项详情记录实际命令、结果、证据局限；只有实际完成审查后才能登记完成。
- 不在本项创建 runtime、backend、workflow 或生产节点；最终可运行 environment manifest 留给后续具体资源清单。

## Tests

本项无产品代码，不跑 GPU 或应用测试套件；用定向文档/证据检查验收：

```powershell
Get-Content -Raw -Encoding UTF8 docs/task-designs/LVA-07-environment-review.json | ConvertFrom-Json | Out-Null
rg -n 'diff_m|diff_b|unmerged|FP8|Windows|Python|commit|未验证|unsupported' docs/task-designs/LVA-07-environment-review.md
git diff --name-only
```

预期：JSON可解析；报告覆盖上述实际适用的条目并引用完整 commit；diff仅为本任务文档及板状态，生产代码、模型和现有工作流无变更。不把关键字命中当成兼容性证明，逐条对照实际源码。报告命令仅在文件产生后运行。

## Acceptance

- 完整候选 SHA 与审阅文件有记录；所有兼容声明可定位到该版本源码或明确依赖元数据。
- 两个专家分别覆盖，high 的41个 diff_m、全部 diff_b/diff及普通 LoRA 有映射/处理路径或明确拒绝依据；不得把 header tensor 数当 applied patch 数。
- 环境矩阵说明当前组合可兼容、需独立 runtime 或尚无证据；不把历史环境记录伪称本轮新查询。
- 给出进入 CPU 验证、停止或证据不足的结论；不承诺真实加载、质量或提速。
- 0安装、0模型下载、0节点导入、0服务启动、0生成 POST、0 GPU采样；既有环境与暂停生产保持。

## Risks

- Wrapper WIP 可能改变 LoRA转换、modulation目标及依赖；候选 SHA 尚未审查是本任务输入待获取项，不是已知兼容版本。
- 源码支持只能决定是否值得 CPU 验证，无法替代实际应用和人工观看。
- 若高/低之外另有第二套历史 pair，当前指定文档没有该来源；不得自行替换本次锁定对象。
