# LVA-07-02 原始 payload CPU 验证结果

2026-11-18。用户批准的精确 290 项例外已实现。**2959 个适用原始输入全部通过真实解析保留及 CPU 目标 fixture 应用，30/30 测试通过。** 完整 14B 模型、节点注册与视频兼容性仍未验证。

| 专家 | 原始输入 | 不适用 | 解析读取且最终保留 | CPU fixture 应用 |
| --- | ---: | ---: | ---: | ---: |
| High | 1500 | 0 | 1500 | 1500 |
| Low | 1749 | 290 | 1459 | 1459 |
| 合计 | 3249 | 290 | 2959 | 2959 |

逐项源 key、标准化 key、目标、shape/dtype、分类及数值探针见 [结构化结果](LVA-07-02-applicability-results.json)。trace 共 3249 条，覆盖 1255 组解析、High1095/Low1054 个目标参数；tensor 数不是 patch 数。290 项均为 `declared_not_applicable`，没有记为消费或应用。

## 实际来源与执行

上游固定 `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00` 的 18 文件快照经补丁形成 21 文件独立部分副本，位置 `E:/VideoAI/scratch/benchmarks/LVA-07-02-applicability/replay-wrapper`，本地 commit `15ad15c292831865886b4fa9a2316188b0820035`。payload 执行时工作区干净；不是完整 checkout，没有生产激活。

本机基模只读有界 header，核对大小、固定 header SHA、无 img 目标及目标 shape/存储 dtype。meta 模型使用实际 header。原始 LoRA payload 经真实 normalizer、key mapper、Comfy loader/ordinary LoRAAdapter，再执行真实修复模块静态数学和 CustomLinear 动态数学。AST 提取保持原函数/类主体，注册表限定普通 LoRA，不是完整节点注册。

每个输入必须是最终 parsed payload 对应槽位保留的同一张量对象。每个适用目标在 FP32 零基底 fixture 上计算全部元素，矩阵按 512 行分块；每块独立 double 数值探针，所有输出元素检查有限。**这证明原始增量的 CPU 数学，不证明实际 14B 基底已应用或完整 Wan forward 正确。**

最终 exit0，44.81 秒；Windows `peak_wset` 为 1,899,302,912 bytes，约 1.77 GiB。执行前后核对完整 prepared 源码清单和执行脚本，结果记录策略、normalizer/mapper、Comfy 组件和 trace 指纹。trace SHA256 为 `b2922754863c13a1e7737ea0cdfe2277e098e186115ffa6e1e54d8cff26c71f0`。完整大文件 SHA 沿用历史准入，本次仅检查 header/stat，没有重哈希大模型。

## 修复和限制

- 静态 bias、norm、block/head modulation 已修复；strength、alpha/rank、scalar-scale FP8 顺序通过 CPU fixture 验证。
- 小模型私有 High/Low pair 验证预检、异常不发布/不污染原模型、重复拒绝及移除恢复。每侧 256 MiB 预算，不能直接用于双 14B。
- 新增回归覆盖目标 dtype、读取后被覆盖、源码漂移、header 身份/长度拒绝；原 21 项与新增 9 项共 30 项通过。
- 原始 merged `utils.apply_lora` 已真实 CPU 执行：block/head modulation 预期 1.125，实际均为 1.0；bias 实际 `[0.625,-0.875]`，norm 实际 `[1.125,1.125]`。**merged 遗漏已复现，继续不支持，未修复。**
- `low_mem_load` 完整链、fast FP8、完整节点注册、完整模型 pair 应用、GPU、视频质量与速度均未验证。实际拟用配置仍须通过后续门槛。

## 历史与重放

原 [关闭提案](LVA-07-02-img-exclusion-proposal.json) 保留；批准后生效的 CPU [固定策略](../../patches/wanvideo-wrapper/lva07_img_policy.json) 单独保存，不是通用 img 过滤。原 unmerged RED、安装记录及 21 项修复见 [主结果](LVA-07-02-results.json)、[前批结果](LVA-07-02-fix-results.md) 和 [CPU 环境](LVA-07-02-cpu-environment.md)。没有修改原 RED 预期。

使用 [构建器](../../scripts/prepare_lva07_wrapper_fix.py)、[测试验证器](../../scripts/verify_lva07_wrapper_fix.py)、[payload 验证器](../../scripts/validate_lva07_applicable_payloads.py) 和 [merged 诊断](../../scripts/diagnose_lva07_merged_cpu.py)。精确命令、结果、指纹和 trace 在结构化结果及 `E:/VideoAI/scratch/benchmarks/LVA-07-02-applicability/`。新输出目录必须不存在；不必重复成功运行。

本次 0 新依赖下载/安装、0 模型下载、0 GPU、0 服务、0 视频 POST、0 生产修改。未跑产品全库测试：没有产品 runtime 改动。CPU 任务收尾不代表 Wrapper 可以直接生成视频；LVA-07-03 仅准备投入决策与资源清单。
