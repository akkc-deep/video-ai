# LVA-07-03 投入决策与具体环境/GPU资源清单设计

## Goal

根据 LVA-07-01 的环境审查、LVA-07-02 的真实 CPU 结果及 LVA-01 的素材/计时边界，交付可审阅的继续、停止或证据不足决定。若建议继续，只说明值得尝试独立实验，不表示完整模型、GPU 或质量已通过。

## Scope

只创建投入决策文档及机器可读环境/资源清单。可以读取现有文件、包元数据、模型 header 与既有实验记录；需要更新远端信息时仅查固定来源的 metadata，不下载 payload。不安装依赖、不建立新 worker、不导入 GPU torch/完整节点、不启动服务、不提交视频、不恢复生产、不改原模型或工作流。

精确 290 项批准只适用于 LVA-07-02 的固定 CPU profile。未来实际模型必须重新核对身份和结构；不得把该批准当任意 img 过滤或实际 full-model admission。原关闭提案保留，当前策略另有固定身份。

## Approach

1. 按顺序读取本设计、`LVA-07-wrapper-backend-design.md`、`LVA-07-environment-review.json/.md`、`LVA-07-02-results.json`、`LVA-07-02-applicability-results.json/.md`、`LVA-07-02-fix-design.md`、`LVA-01-gpu-results.md`、`LVA-04-results.md` 及其明确引用的模型/workflow 身份记录。后者只读取直接需要的字段，不扫描旧视频或重复历史 benchmark。
2. 在决策文档建立条件矩阵：mixed delta/映射、merged/unmerged、FP8/scale、low_mem_load/offload、完整源码/节点依赖、双专家真实应用、硬件预算及质量基线。每项记录证据层次、来源、已验证行为、未验证边界与解除条件。CPU 成功和完整运行未知分别记录。
3. 保留事实：上游固定 `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`；本地修复 `15ad15c292831865886b4fa9a2316188b0820035` 是 21 文件部分副本；30 项测试通过；2959 原始适用输入经真实解析保留及 CPU fixture 应用；Low290 为精确不适用。小模型 pair 每侧 256 MiB，不能直接深复制 14B；merged 已数值复现遗漏，禁止作为可用替代方案。完整注册、完整 Wan forward、fast FP8 与 low_mem_load 未验证。
4. 决策使用 `stop`、`insufficient_evidence`、`worth_isolated_attempt` 三选一。已证实拟用路径不支持且无具体修复方案时 `stop`；环境、源码或预算缺少足以形成可执行清单的证据时 `insufficient_evidence` 并列具体解除条件；仅在 CPU 语义支持拟用路径、完整环境/资源计划可审阅且后续完整模型门槛明确时才可 `worth_isolated_attempt`。不使用 `compatible` 或 `production_ready` 作为结论。merged 不支持不等同于所有 Wrapper 配置不支持。
5. 写环境 manifest。顶层字段固定：`task_id`、`decision`、`rationale`、`evidence`、`wrapper`、`comfy`、`runtime`、`dependencies`、`models`、`profile`、`resources`、`full_model_gate`、`gpu_plan`、`actions`、`unresolved`、`authorization`。`task_id` 必须为 `LVA-07-03`；`evidence` 为 path/sha256/scope 记录数组；模型条目有 role/path/bytes/sha256/header_sha256/reuse/source，明确历史身份与新观察；runtime 记录 Python/ABI/torch/CUDA、路径、是否实测；Wrapper 记录上游 SHA、本地修复 SHA、完整 checkout 可用性与补丁指纹。
6. `profile` 必须明确 merge、weight/compute dtype、scale、attention、compile、offload、low_mem_load 及每个选项的证据/待验证状态。没有证据的配置不能继承 CPU 放行；未确定值写 JSON `null` 并在 `unresolved` 给 reason、resolution、blocks 字段。CPU runtime 不得当 CUDA runtime。优先评估复用现有两基模和两 LoRA；W3 或 BF16 替代需独立列身份/代价，不能因同一 290 缺失自动更换或下载。
7. `resources` 分开列已有模型复用字节、新下载、新副本、临时空间、磁盘预留、RAM/VRAM 预计峰值、估算方法和测量来源日期。使用当前历史 RTX5090D V2/24455 MiB 观察时标为历史，不伪造本轮空闲值或双模型驻留证明。预算无法可信确定时结论不得为 `worth_isolated_attempt`。依赖如需新增，只有精确版本/URL/wheel tag/SHA/字节和依赖影响齐全才能列为可审阅安装动作。
8. `actions` 数组每项含 id、purpose、exact_command 或 null、read_set、write_set、download_bytes、estimated_disk_bytes、requires_explicit_authorization、executable、blocked_by。仅列具体可执行命令；缺参数时 executable=false 并说明缺口，不生成可误执行的占位命令。所有安装、下载、服务和 GPU 动作均未获本项授权，清单形成不执行。不得把旧 LVA-04/06 或 CPU 授权外推。
9. `full_model_gate` 固定 enabled=true、before_fast_post=true、verified=false：未来在独立 worker 构造真实两专家后逐项核对身份、schema、解析保留、实际静态/动态安装与异常原子性；不适用项独立对账。内存方案不能调用现有小模型 deepcopy API 处理 14B。失败不返回可用单侧、不提交 fast。验证只在准入边界一次并保存结果，不在每步/每帧重复。
10. `gpu_plan` 固定为先 1 个低运动 40 步 control，技术与人工质量通过后才 1 个同输入 4 步候选；768×432、16fps、93 帧及原素材/prompt/seed 身份沿用证据。记录采样器、CFG、sigma/split、计时边界与最大样本数 2；Wrapper 不能等价时明确限制，不能伪造原生可比性。冷1热3/高运动/父子链属于后续获准扩展，不在本项执行。

## Files

- 创建 `docs/task-designs/LVA-07-environment-manifest.json`：上述固定结构、证据/计划/未知值及授权范围。
- 创建 `docs/task-designs/LVA-07-investment-decision.md`：决定、条件矩阵、资源表、逐项动作和实际完整模型门槛。与 JSON 的 decision/预算/样本数一致。
- 更新任务板 LVA-07-03 的实际结果/状态；不修改前驱结果来消除未知，也不提前制作 GPU backend。后继只能在本项结果支持且依照任务交接规则时准备。

## Tests

无需产品测试或新 CPU/payload 重跑。本项只产出文档：

```powershell
& .tools/python/python.exe -I -m json.tool docs/task-designs/LVA-07-environment-manifest.json > $null
& .tools/python/python.exe -I -c "import json,pathlib; p=pathlib.Path('docs/task-designs/LVA-07-environment-manifest.json'); m=json.loads(p.read_text(encoding='utf-8')); required='task_id decision rationale evidence wrapper comfy runtime dependencies models profile resources full_model_gate gpu_plan actions unresolved authorization'.split(); assert set(required)<=set(m); assert m['task_id']=='LVA-07-03'; assert m['decision'] in ['stop','insufficient_evidence','worth_isolated_attempt']; assert m['full_model_gate']['enabled'] and m['full_model_gate']['before_fast_post'] and not m['full_model_gate']['verified']; assert m['gpu_plan']['max_samples']==2; assert not m['authorization']['gpu'] and not m['authorization']['installation']; assert all(not a['executable'] or a['exact_command'] for a in m['actions']); print('manifest contract passed')"
git diff --check
```

预期各 exit0。另人工对照 MD/JSON 决定与预算一致、证据文件存在且摘要匹配、估算/历史值/实测有区别、没有 GPU 通过或完整模型已应用的表述。未知值必须可定位到解除条件；命令不可执行时明确标记，不为了清单完整而猜版本或资源数。

## Acceptance

交付两个一致的文件；决定有直接证据和条件矩阵支持；继续建议具备精确可审阅动作和预算，否则明确停止或证据不足。固定源码/模型身份、290 项批准范围和所有 CPU 限制保留。完整模型门槛、最小两样本先后关系、人工质量停止条件和需另行授权的动作均具体；没有任何安装、下载、服务、GPU 或媒体生成副作用。

## Risks

完整 checkout/节点依赖、14B 原子准入内存方案、实际 FP8/offload 路径仍缺运行证明，是本项必须评估的输入事实，不是待用户补写的设计要求。历史硬件和资源不能认证新环境；不同基模/精度/调度器的收益不能归因纯后端。原始 merged 已知有缺陷，不能绕开 unmerged 的完整运行未知。判断证据不足是有效交付，不得为推进顺序虚构环境就绪。
