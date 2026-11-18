# LVA-07-02：基于真实CPU遗漏的最小修复设计

最新实施与验收见 [原始 payload 结果](LVA-07-02-applicability-results.md)：批准的精确 290 项策略、2959 项适用原始输入 CPU 验证和 30/30 测试已完成；merged block/head 遗漏已真实复现，继续禁用。下文保留方案形成及前批修复时的历史说明，不以旧未实施/旧阻断描述覆盖新证据。完整模型、完整注册和 GPU 仍不在本次验证范围。

## 授权后的实现更新（2026-11-18）

用户“按照这个方案修复吧”已授权独立副本实现。当前支持的CPU路径已修复并通过21项重放测试，详见 `LVA-07-02-fix-results.md/.json`。实现新增 `lva07_mixed_delta.py`，保留原CustomLinear动态数学、修正其scale顺序，并在原nodes入口增加整组只读准入；未改生产或原快照。明确验证的scalar-scale float8_e4m3fn CPU分支可用，其他FP8/fast/merged/完整模型仍未认证。

原始3249项header核对新发现Low290项无当前base直接目标，完整pair仍保持拒绝。本文件下方“仅设计/未实施”等为首次设计形成时的历史状态；最新实施和限制以上述结果报告为准。

2026-11-18。**仅设计，未实现、未修复上游、未取得兼容通过。** 基线为 Wrapper `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`。本项按停止条件在首批CPU遗漏复现后停止扩展，不把未运行的merged/FP8/完整模型测试写成已成立。

## 已复现的问题及范围

真实 `custom_linear.py` 和 `gguf/gguf_utils.py` 完整模块在独立Python3.13.14 / torch2.14.1+cpu中执行。只用namespace定位相对包，不替换算法或依赖；未执行Wrapper注册或Comfy导入。固定小文本SHA及完整数值见 `LVA-07-02-results.json` 的 `cpu_execution`。

`set_lora_params` 仅在 `CustomLinear` 中查询 `.weight`；`forward` 原样使用bias。float64、strength0.5、无FP8、无compile首批结果：

| 用例 | 独立预期 | 实际 | 最大绝对误差 |
| --- | --- | --- | ---: |
| block modulation `[1,6,2]` | 全部1.125 | 全部1.0 | 0.125 |
| head modulation `[1,2,2]` | 全部1.125 | 全部1.0 | 0.125 |
| bias forward | `[1.625,1.125]` | `[1.5,1.5]` | 0.375 |
| linear weight diff对照 | `[1.875,1.875]` | `[1.875,1.875]` | 0 |

这里输入是由固定Comfy源码定义的parsed `('diff',(tensor,))` tuple，非完整LoRA loader输出。`.diff_m → .modulation.diff` 的语义依据固定Wrapper标准化函数及固定Comfy `lora.load_lora` / `calculate_weight` 的加性diff分支；没有从名字猜乘法或broadcast，也没有执行整个converter/loader链。这个范围足以复现unmerged应用层遗漏，不能证明完整权重消费。

## 方案选择

1. **先加严格拒绝（最小安全修复）**：在两专家准入阶段发现任意未覆盖目标即拒绝pair，不能把 `set_lora_params` 无异常当应用成功。这会维持候选不可用，但防止错误接受。
2. **补全unmerged的静态参数应用**：保留真实CustomLinear矩阵weight的动态路径，在独立副本上一次性应用bias/norm/modulation；需要完整消费与原子性证据，才可能支持当前pair。这是恢复支持的后续最小方向。
3. **直接切merged**不作为解决方案：merged非叶参数遗漏只有源码证据，且scaled FP8与重复应用尚未验证，不能绕过门槛。

当前建议先执行方案1；方案2是需要后续实现和验证的设计，不在本轮改动Wrapper。不能仅删掉41个high diff_m、忽略bias/norm或换LoRA来使测试变绿。

## 具体修改边界与接口

拟在**独立fork**的 `nodes_model_loading.py`、`custom_linear.py` 内修改，不碰生产checkout：

- `model_lora_keys_unet` / `load_lora_for_models_mod` 前后的输入台账必须保留source key到normalized key、target、patch类型、shape/dtype的映射。标准化前拒绝不同source key写同一normalized key；必须捕获原dict覆盖，不能在覆盖之后才数patches。
- 新增 `prepare_lora_pair(high, low, high_patches, low_patches, strengths)`：先只读完成两侧全量preflight，再创建两个私有副本，内部执行应用与验真，最后才返回pair；任一异常返回异常而不返回可用单侧对象。每项记录 `dynamic_weight` / `static_parameter` / `rejected`。
- `set_lora_params` 保持矩阵weight原有动态计算入口。增加与其同一准入事务内调用的 `apply_static_deltas(private_model, static_plan)`，只接受当前证明其数值语义的加性diff及精确目标。该函数不在每步、每帧或每次forward中重做全量扫描。
- 方案1在既有loader声明接受前调用只读分类；凡目标为bias、norm或modulation且本次配置没有已验证应用器，抛出具名异常。该拒绝必须早于任一原始模型/patch字典/缓冲区写入。

所有接口以上为拟议，尚未创建。实际完整loader导入闭包仍须先补齐；现有32-wheel最小环境不等于完整节点环境。

## 数学与应用不变量

- 对已确认加性diff：`P_new = cast(P_base + strength * delta, original_dtype)`；先在明确的float32/float64计算域执行，输入delta必须与目标shape完全相等且有限，禁止隐式broadcast。bias/norm/modulation都按其真实目标shape处理；block/head维度分别保持 `[1,6,dim]` / `[1,2,dim]`。
- `diff_m`只作名称到modulation参数的转换，转换后是加性diff；不套普通rank-r LoRA的alpha/rank。普通LoRA仍使用 `strength * alpha/rank * (up @ down)`，有无alpha的约定以固定真实adapter为准，需另行执行测试，当前没有该测试结果。
- 静态参数暂只支持标量常量strength。遇到schedule、未知patch类型、未知dtype/FP8量化、缺失目标、shape不等、非有限值或alias冲突，在preflight拒绝整个pair；不能把它们降格成warning后继续。
- 深复制必须覆盖参数、缓冲区、patch字典和运行状态，禁止仅依赖Comfy浅clone以为参数独立。CPU小模型可用 `copy.deepcopy` 并注入low侧异常验证原始high/low完全不变；完整14B的复制/内存方案不在本设计认领可行，不据此授权加载两模型。
- 静态应用只发生一次。应用身份绑定base、LoRA、目标清单、strength及dtype策略；同一身份重复调用应明确返回已有结果或拒绝，不能再加一次。移除/重配从私有原始副本恢复，禁止在量化结果上相减来假设可逆。
- bias更新后由原 `CustomLinear.forward` 使用新bias；modulation更新应由真实Wan block/head消费。当前小型fixture没有证明完整Wan forward，后者仍是后续门槛。

## merged与FP8的限制

`utils.apply_lora` 的遍历对自有参数+子模块可能跳过，仍是源码级风险。本轮没有运行该函数，不据unmerged测试宣布merged已复现或修好。若后续处理merged，应按实际目标参数逐项遍历、检测alias并对账，禁止以“叶模块全部遍历”替代完整参数覆盖。

FP8目前一律不因CPU float64通过而放行。必须独立推导base量化/scale语义，验证scale只应用一次、delta在正确反量化域相加、dtype回写和移除/重用一致；在此之前静态delta遇FP8/scaled配置应拒绝。不能默认将当前float64加法照搬后重标定成功。

## 验证与接受条件

保留现有 `scripts/reproduce_lva07_cpu.py` 作为上游基线的3个RED断言和weight对照，不能修改预期或改为expectedFailure来宣称GREEN。现有复现命令见结果报告。输出中的 `baseline_wrapper_commit` 仅标明设计基线，实际被测文件以 `imported_sources` 的路径和SHA为准；4项局部用例通过也只能称 `fixture_tests_passed`，不能称完整兼容。

方案1应新增 `reject_unsupported_pair_without_mutation`：调用真实fork的 `prepare_lora_pair`，对high modulation或low bias断言具名 `UnsupportedPatch` 异常；同时核对两个原始模型参数/缓冲区/patch字典不变，且没有返回pair。它不会使上游基线的3个数值断言变GREEN，不把“拒绝成功”记为“支持修复成功”。

方案2应另建fork组合入口测试，调用真实 `prepare_lora_pair → apply_static_deltas + set_lora_params`，而非只调用原 `set_lora_params`。沿用现有独立数值预期（modulation1.125、bias forward `[1.625,1.125]`、weight对照 `[1.875,1.875]`），在实际返回的私有模型上断言；4项应全通过且无运行错误，才称这些用例已修复。修复版本以新source-evidence及fork完整commit固定身份；unmerged与merged须分别执行并报告。当前组合入口尚不存在，未调用、未测试、未修复。

另需新建独立CPU准入测试：完整两专家输入台账；普通LoRA/diff/norm/bias/block与head；strength/alpha/rank；重复/移除；未知key、shape/dtype、NaN/Inf、标准化碰撞；high-only/low-only/pair；注入low阶段异常后两侧原始参数/缓冲区/patch身份不变且不返回pair。以上测试尚未编写或执行，不作完成证据。

完整模型的消费/应用和GPU/质量仍分别有后续门槛；本设计不将CPU小张量接受升级为完整模型接受。本项仍有未完成验收，保持停止/阻断，不准备GPU。

## fork和rebase策略

不修改现有快照或生产custom_nodes。在另行决定投入后，从固定SHA建立单独fork分支；将严格拒绝与实际支持修复分成可审查提交，每个提交记录完整SHA和对应RED/GREEN命令。保存原基线SHA和源码副本。

每次rebase先固定目标上游SHA并审阅converter/loader/custom_linear/utils差异；若上游已改变modulation/bias或FP8语义，重新做该路径的源码及CPU验证。禁止浮动main自动更新、保留旧证据却替换被测源码，或为解决冲突静默删除patch类别。只有实际输出、目标台账和原子性证据齐备才能重新考虑继续；维护fork的决定仍属于LVA-07-03，不在本项自动创建远程fork或推送。
