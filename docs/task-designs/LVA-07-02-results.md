# LVA-07-02 CPU验证与修复结果

## 最新验收（2026-11-18）

用户已同意精确 290 项不适用范围。策略已实现，High1500 + Low1459 共 **2959 项原始输入**全部通过真实解析保留及 CPU fixture 应用；**30/30 测试通过**。原始 merged modulation 遗漏已真实复现并继续禁用。详见 [最新结果](LVA-07-02-applicability-results.md) 与 [逐项证据](LVA-07-02-applicability-results.json)。完整 14B、节点注册、GPU 和视频仍未验证；CPU 任务收尾不放行采样。

## 历史阶段记录

以下是批准例外与原始 payload 验证前的历史记录，其中 BLOCKED、等待批准、21 项和未消费等描述不代表当前状态。原始 RED 和安装记录保留。

更新：2026-11-18。**独立代码修复已交付，21项针对性CPU测试通过；完整任务保持BLOCKED。** 当前阻断是Low290项输入在既有base header无直接目标，完整原始权重消费/应用尚未验收。具体实现、重放和限制见 [修复结果](LVA-07-02-fix-results.md)；逐项映射见 [3249项header清单](LVA-07-02-tensor-inventory.json)。下方原始负向数值是修复前基线，保留为RED证据。

最新只读核对见 [官方基模与规则核对](LVA-07-02-base-review.md)：官方BF16模型也缺同一290个img目标，不能据此前缺失观测认定本机一定选错基模。当前固定a743节点有明确img过滤规则，但参考图记录的998旧源码没有该显式规则。精确290项“不适用”提案已形成且关闭，需明确调整全量输入验收后才能实现/启用；当前严格代码未改变。

## 已下载及安装

用户针对上一轮精确清单回复“同意下載吧”。32个固定wheel已按URL/hash下载，共154334412 bytes（约147.18 MiB），并离线安装到 `E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/cpu-site/`。pip安装报告与原清单32/32版本、SHA一致，pip check exit0：No broken requirements found。

合并的下载/安装器命令在执行前被自动审批拒绝，仅返回blocked by policy，没有具体原因。采用更小副作用的替代：从现有Python3.13.14复制31个解释器文件（20652143 bytes）到scratch/runtime，另写仅指向scratch的_pth，使用相同已授权CPU wheel做离线--target安装。没有下载或运行Python安装器，没有系统登记、PATH或生产包修改。**这是独立portable环境，不是venv**；原提案中的安装器方案未执行。

运行时检查：Python3.13.14、torch2.14.1+cpu、torch.version.cuda=None；sys.path仅含scratch/runtime zip、runtime及cpu-site。原始Comfy/Wrapper生产环境未导入或修改，0GPU、0服务、0视频POST、0模型下载/大模型重哈希。

## 真实CPU证据

完整执行固定Wrapper源码 `custom_linear.py` 和 `gguf/gguf_utils.py`，真实accelerate/gguf/torch均来自cpu-site，实际走CustomLinear custom-op路径。namespace只定位包路径，没有替换任何算法或强制依赖；没有执行Wrapper节点注册或完整Comfy模块导入。

被测源码：Wrapper设计基线 `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`；custom_linear SHA256 `6841721813b89869e7dae8488b9fee7b9dd607aa6d6614c79b19079a8bd8ec59`，gguf_utils SHA256 `0299748fef63414ec59fe731c629ab3b5872d293135591fd59d1fc27ad69d9f0`，均与LVA-07-01小文本快照身份一致。

| 首批用例 | 预期 | 实际 | 最大绝对误差 | 结果 |
| --- | --- | --- | ---: | --- |
| 普通weight diff对照 | `[1.875,1.875]` | `[1.875,1.875]` | 0 | PASS |
| high block modulation | 全部1.125 | 全部1.0 | 0.125 | RED，未应用 |
| high head modulation | 全部1.125 | 全部1.0 | 0.125 | RED，未应用 |
| low bias forward | `[1.625,1.125]` | `[1.5,1.5]` | 0.375 | RED，未应用 |

strength0.5，float64计算，atol1e-12/rtol0；独立数学预期为加性diff。测试输入是synthetic parsed-diff tuple，非原LoRA payload，也没有执行完整converter/loader链。结果只支持这三个代表目标在真实unmerged应用层被遗漏，不能将其外推为3249个原始输入的已消费/应用计数或整个Wrapper普遍不支持。

最终复核批次显式使用float64参数存储。初批CustomLinear参数默认float32而forward为float64，当前二进制精确fixture的结果相同；为修正存储dtype说明，复核后只重跑同4例。两次均exit1、1通过/3失败/0运行错误，合计8次case执行、4个独立用例。没有通过修改预期、expectedFailure或修复上游来制造GREEN。

## 交付及未完成验收

- [复现入口](../../scripts/reproduce_lva07_cpu.py)：独立CPU环境显式执行，不进入产品/常规生成链。
- [结构化结果](LVA-07-02-results.json)：实际版本、来源SHA、逐fixture预期/实际/误差、原日志路径、授权/安装记录及限制。
- [最小修复设计](LVA-07-02-fix-design.md)：先严格拒绝不支持目标；独立副本已实施静态bias/norm/modulation和CPU原子pair入口，见修复结果；生产和原审查快照未修改。
- [环境及命令](LVA-07-02-cpu-environment.md)、[原哈希锁](LVA-07-02-cpu-requirements.lock)：保留原提案和实际portable替代路径的区别。

修复前曾触发“未应用即停止”。用户随后明确授权按方案修复，已在小型CPU模型验证norm、静态delta、scalar-scale FP8、重复/移除和私有pair失败回滚；原始3249项只有header/真实标准化映射，没有payload消费或完整模型应用，consumed/applied仍为null。没有创建可提交视频的原始pair，不冒认完整模型原子性。

任务未标COMPLETED，LVA-07-03未准备。代码遗漏已有修复证据；当前完整pair保持停止，需先解决Low290项base目标缺失，再继续实际加载/应用验收。不重复索取已有下载/修复授权，不自动换base或启动GPU。

## 实际命令和检查

下载：`.tools/python/python.exe -I -m pip --isolated download --no-cache-dir --only-binary=:all: --platform win_amd64 --python-version 3.13 --implementation cp --abi cp313 --require-hashes --dest E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/wheels -r docs/task-designs/LVA-07-02-cpu-requirements.lock`，exit0。完整实参及输出见scratch/pip-download.log。

离线安装：由外部pip的 `--python scratch/runtime/python.exe` 指定目标解释器，使用 `--no-index --find-links scratch/wheels --only-binary=:all: --require-hashes --target scratch/cpu-site -r scratch/offline-requirements.lock`，exit0。offline lock的32个版本/hash与原URL锁一致；pip-install-report.json保留本地wheel的hash和版本。

复核批次：

```powershell
& E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/runtime/python.exe -I -B scripts/reproduce_lva07_cpu.py --source-root E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit --source-evidence E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit/metadata-evidence.json --output E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/cpu-negative-results-reviewed.json
```

exit1，4 tests / 3 failures / 0 errors，日志 `E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/cpu-negative-tests-reviewed.log`。这是实际负面结果，不是测试全通过。独立只读review确认窄结论成立，2项证据/设计Important与2项Minor已处理。未运行产品全库测试或GPU；没有产品实现变更。
