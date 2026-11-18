# LVA-07-02 独立 Wrapper 修复结果

最新补充：[原始 payload 结果](LVA-07-02-applicability-results.md) 已完成批准例外和 2959 项适用输入 CPU 验证，30/30 测试通过。下文是前批 21 项修复交付的历史记录；旧 290 项阻断已由用户批准的精确策略解决。完整模型仍未就绪，merged 真实负向诊断已补齐并继续禁用。

2026-11-18。**代码层修复已交付，独立重放的21项CPU测试全部通过。原始完整LoRA pair仍未准入：Low有290项输入在当前base header中没有对应目标。** 不将CPU修复完成登记为完整LVA-07-02验收通过。

后续只读核对已确认：官方BF16 header也缺完全相同290项，不能以此直接推导“必须换基模”。当前a743 Wrapper有按无img结构过滤规则；官方图记录的998旧版本无该显式规则，历史runtime仍未验证。详见 [基模与规则核对](LVA-07-02-base-review.md)。精确290项排除提案尚未启用，本文件记录的代码和21项测试没有因此改变。

## 改动及验证

- 在独立源码副本中增加 `prepare_lora_pair`：先检查两专家全部parsed patch，再创建并验证私有副本；bias、norm、block/head modulation只应用一次，普通矩阵LoRA保留真实CustomLinear计算路径。
- 失败不返回单侧可用对象；注入Low实际静态应用后的异常，两侧原始参数/缓冲区保持不变。非独立deepcopy和共享storage拒绝；重复应用拒绝，移除从独立原始副本恢复。
- 修复真实CustomLinear的scale顺序：有LoRA时先对weight应用scale，再加delta，避免小输入分支把delta额外缩放。通过scalar scale和float8_e4m3fn CPU用例；不是fast FP8/GPU运行证明。
- 标准化键名冲突在覆盖前拒绝。旧节点入口在整个LoRA列表的任何clone、调度标记或特殊模型修改之前完成只读检查；mixed静态目标拒绝，使用私有pair API。缓存输入避免重复文件读取，不在采样步/视频帧中增加全量检查。

首轮15项测试先观察失败；补充边界测试发现并修复动态更新溢出、非独立复制及meta模型旧入口限制。独立review发现旧入口检查晚于调度标记修改，新增两项回归先失败再通过。最终新副本重放后 **21 tests / 0 failures / 0 errors，exit0**，同时覆盖float32/float64、rank1/2与alpha、非法输入、schedule、碰撞、scale和失败回滚。

三个原失败的数值预期未削弱：block/head modulation更新到1.125，bias-only forward为`[1.625,1.125]`；weight-only对照仍为`[1.875,1.875]`。原始上游RED证据保留，修复测试调用真实组合入口。

## 可审查与重放的交付

- [新增模块](../../patches/wanvideo-wrapper/lva07_mixed_delta.py)、[上游修改patch](../../patches/wanvideo-wrapper/mixed-delta.patch)、[来源和hash清单](../../patches/wanvideo-wrapper/manifest.json)。patch仅6468 bytes，保留LF，未整份改写原文件。
- [构建独立副本](../../scripts/prepare_lva07_wrapper_fix.py)、[运行验证并输出身份报告](../../scripts/verify_lva07_wrapper_fix.py)、[CPU回归测试](../../tests/experiments/test_lva07_wrapper_fix.py)。构建器核对18份原始源码SHA和修复产物SHA，拒绝覆盖已有目标和来源漂移。
- [结构化修复结果](LVA-07-02-fix-results.json)，包含实际环境、source SHA、测试日志、review及限制。

独立源码位置：`E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/wrapper`，本地分支 `lva07/mixed-delta-fix`，最终commit `801be04a9b4863502b50dd8a353bda45a824e0d1`。源修复提交为 `dca06d1a288929628c75a0393e67f1e2afdccac9`；随后本地元数据提交修正该副本自己的baseline引用和LF换行，未改已测试代码。来源是18份已审查快照，**不是完整上游checkout**；没有远程fork/push。

独立重放位置为 `E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/final-replay`，修复commit `59ac0e39e9a111d0f5242535b64d7a3fd9c15585`。21项测试先通过，再核对19个被测源码文件SHA与最终副本相同后提交；没有在通过后修改代码。重放副本最终元数据commit为 `fc08567927de471be7c8ce90cde5b3f270172a5b`，未改变19份已测试代码。两处本地工作区均干净。

重放命令（使用新的、不存在的目标）：

```powershell
& .tools/python/python.exe -I scripts/prepare_lva07_wrapper_fix.py --source-root E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit --destination E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/new-copy
& E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/runtime/python.exe -I -B scripts/verify_lva07_wrapper_fix.py --source-root E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/new-copy --output E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/new-copy-results.json
```

实际最终日志：`E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/final-green.log`，原始JSON为同目录`final-results.json`。构建器拒绝已有目标/漂移来源的检查通过，且拒绝发生在创建新目标前。常规pytest收集该模块时没有opt-in环境变量会跳过21项；该检查exit0、出现已有pytest缓存目录WinError5警告，不把跳过算通过。产品全库未运行，没有产品runtime变更。

## 原始权重的另一个阻断

本轮对两组LoRA和两个base仅各读一次有界header，执行修复后的真实完整标准化函数；没有读取tensor payload或重哈希大文件。逐项证据见 [3249项清单](LVA-07-02-tensor-inventory.json)。

| 专家 | 原始输入tensor | header目标缺失 | 已找到目标的shape不匹配 |
| --- | ---: | ---: | ---: |
| High | 1500 | 0 | 0 |
| Low | 1749 | 290 | 0 |

Low缺失包括82个down、82个up、84个bias、42个diff，集中在各block的`cross_attn.k_img/v_img/norm_k_img`及`img_emb.proj`。当前目录只有既有high/low两个base，未发现另一份可直接验证的本地候选。

这里结论限定为真实header的直接目标匹配：没有完整加载模型，不能从header推断两文件payload相同，也不证明完整Wrapper运行后模型属性。所有原始tensor的`runtime_consumed/runtime_applied`仍为null；没有把3249项header映射或小fixture通过当实际完整应用。

当前完整pair必须保持拒绝；应先核实Low LoRA与base结构/路径是否匹配，或准备有明确身份和资源清单的兼容模型方案。不能过滤掉这290项、补随机参数或静默替换base。没有为解除此阻断自动下载新模型。

## 未验证边界

CPU pair API接受parsed patch和裸transformer模块，限定每侧256MiB参数/缓冲区的小模型验证预算；不承诺14B深复制可行。完整converter/loader、原始payload消费、完整Wan forward、merged、真实GPU/fast FP8、视频质量和速度都未验证。节点入口回归为完整真实函数的AST执行，并对不可用Comfy I/O/parser使用明确的边界fixture；不是完整节点注册证明。

本轮0新依赖安装/下载、0模型下载、0GPU/服务/视频POST、0生产或原快照改写；现有模型、工作流、旧run和媒体保持原样。LVA-07-02保留BLOCKED，后继不自动准备；本次用户要求的独立代码修复已经交付。
