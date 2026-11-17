# LVA-07-02：Wrapper Mixed Delta CPU 负向复现与最小修复设计

## Goal

在固定版本 Wrapper 的真实转换、加载和 patch 函数上，用小型 CPU 模型确认 LVA-04 两组 LightX2V LoRA 中 mixed delta 的实际映射、遗漏和数值语义；区分源码静态风险与 CPU 实际行为，为是否维护独立 Wrapper fork 提供证据。

本任务先做最小负向复现和修复设计，不实现完整后端、不启动 Comfy、不做 GPU/视频生成。LVA-07-01 的结论是停止当前候选安装/推理准备；因此若真实函数因缺依赖无法导入，先提交精确隔离 CPU 环境清单，等待用户明确授权，不用 mocks 冒充 CPU 验证。

## Frozen inputs

- Wrapper commit：`a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`（1.4.8），禁止浮动 main。
- Comfy source commit：`2c75dc1b379a59e0880619d029607af5169a62ef`；本机文件 SHA 以 LVA-07-01 JSON 为准。
- 审查依据：`docs/task-designs/LVA-07-environment-review.md/.json`。
- LoRA 身份只使用 LVA-04 已冻结记录，不重下或重哈希大文件：High 634645944 bytes，SHA256 `887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19`；Low 739472104 bytes，SHA256 `8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1`。
- Base header 审查有界，不证明完整模型加载，也不证明 High/Low payload 相同。

## Scope and method

1. 确认固定版本真实函数的最小 import graph；优先只读、CPU-only。不得导入或启动 Comfy 服务/GPU。
2. 使用小型确定性模块，其命名和参数结构匹配 Wrapper Wan block/head，覆盖普通 LoRA、`.diff`（linear 与 norm）、`.diff_b`、`.diff_m`（block modulation `[1,6,dim]`、head modulation `[1,2,dim]`），分别测 High、Low 和原子 pair。
3. 尽可能直接调用真实 Wrapper 的 key standardization、key mapping、converter、loader、merged/unmerged 应用函数。手写重实现不能作为 Wrapper 支持证据；thin shim 必须记录并保持被测函数源码身份。
4. 对每个输入 tensor 记录 source key、normalized key、target、shape/dtype、patch kind、consumed/applied/rejection reason；比较参数/缓冲区实际数值与独立推导的预期值。
5. 验证 key normalization 冲突、layer filter/img filter、low_mem_load、merge_loras、FP8 scale、strength/alpha/rank、重复应用/移除和异常原子性。
6. 只有复现后才提出最小 patch 设计；本任务不修改 Wrapper checkout、生产代码或 LoRA 原文件。

## Questions that must be answered

- `standardize_lora_key_format` 是否可能让不同 source key 归一化后冲突并覆盖？
- 两组权重每个 tensor 的目标是否存在，shape/dtype 是否兼容，是否被消费且真正应用？
- Unmerged `CustomLinear` 是否只应用矩阵 weight delta，遗漏 bias、norm、modulation？
- Merged `utils.apply_lora` 是否跳过既有子模块同时持有参数的 block/head？实际哪些 modulation 目标受影响？
- `load_lora_for_models_mod` 对未加载目标是否仅 warning 并继续，调用方是否会误判成功？
- FP8 matmul、merge/unmerge 和 scale tensor 是否改变应用语义？
- High/Low 是否能原子应用，避免其中一组失败后另一组已修改模型副本？

## CPU numerical tests (RED first)

普通 rank-r LoRA 的参考值：`W_out = W_base + strength * alpha/r * (up @ down)`。

`.diff`、`.diff_b`、`.diff_m` 的语义必须由固定来源格式和实际转换代码推导；不能因名字相似就套用普通 LoRA 公式。特别是 `.diff_m`，先确定它对 modulation tensor 的精确运算和 broadcast 规则；无法确认就标记 `semantics_unknown` 并停止，不猜公式。

先为 high 的 diff_m 和 low 的 diff_b 建立 RED 复现，再扩展全部类别。每个测试必须调用真实 Wrapper 函数；用 float32/float64 小张量计算 expected/actual 和误差容限。测试包括：

- key 转换、映射和碰撞检测；
- 每类 tensor consumed/applied 对账；
- merged 参数更新与 unmerged forward 数值；
- bias、norm、block modulation、head modulation；
- FP8 scale 行为和合并/不合并路径；
- High-only、Low-only、High+Low 原子准入；
- 未知 key、shape/dtype 错配、NaN/Inf、重复归一化 key、缺依赖和注入异常；
- 任一专家失败时两个原始模型副本均不发生部分修改。

保留上游源码未修改副本及 SHA。修复后只允许对应 RED 用例转 GREEN，不得把整个算法重写成与上游脱节的模拟版本。

## Dependency gate

LVA-07-01 发现多个声明依赖缺失，包括 accelerate、diffusers、peft、ftfy、gguf、pyloudnorm、protobuf、opencv-python；其中存在强制导入路径，不能仅凭某功能暂时不用就删除。

在安装前：
1. 列出导入真实函数的最小模块依赖闭包；
2. 确定 Windows AMD64 / Python 3.13.14 的精确版本、wheel 标签与 SHA；
3. 建立生产 Comfy embedded Python 之外的隔离 CPU venv；
4. 给出精确安装命令、wheel 来源、磁盘需求和 torch 依赖影响；
5. 仅做不落盘的 resolver/dry-run；任何下载或安装均需单独授权。

若真实函数必须依赖无法在隔离 CPU 环境导入的 CUDA custom op，需报告阻塞，不以 mocks 替代实际函数。

## Deliverables

- `docs/task-designs/LVA-07-02-results.json`：逐 tensor 的映射/消费/应用/拒绝、CPU 数值和证据等级。
- `docs/task-designs/LVA-07-02-results.md`：兼容结论、未验证边界和阻断项。
- `docs/task-designs/LVA-07-02-fix-design.md`：只有实际复现支持修复时才创建，说明最小改动函数、数学不变量、测试、fork/rebase策略。
- 获准后才创建隔离 CPU harness/tests；不创建 GPU workflow/backend。

## Acceptance and stop conditions

1. 两组权重全部输入 tensor 有逐项映射/消费/应用/拒绝轨迹。
2. 固定版本真实 Wrapper 函数在 CPU 执行；静态分析/mock-only 必须标记未验证。
3. 每种支持的 delta 数值与独立推导结果一致；未知语义 fail closed。
4. High/Low 原子性成立，部分失败不返回 pair、不污染任一原始模型副本。
5. merged/unmerged、FP8 scale 和重复应用语义有证据。
6. 不修改生产 Comfy、custom_nodes、生产代码、原 LoRA、工作流、旧任务和媒体；0 GPU、0 服务、0视频 POST、0模型下载。
7. 缺依赖时交付精确隔离环境清单并标记 BLOCKED，不假报通过。

遇到 diff_m 语义未知、任何 tensor 未消费/未应用、key collision、FP8 scale 不一致或 partial mutation，立即停止并记录；没有 CPU 数值证明，不得进入 LVA-07-03 的“兼容可继续”分支，更不得授权 Wrapper GPU 视频生成。