# Pause Handoff

## Handoff Type

pause

## Task Link

- **Task board:** `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`
- **Task ID:** `LVA-07-02`
- **Transition:** `IN_PROGRESS -> BLOCKED`

## Current State

用户“按照这个方案修复吧”已授权并完成独立代码修复。支持的CPU静态delta/动态LoRA路径、私有pair原子失败、重复/移除、scalar scale顺序、碰撞和旧入口整组提前拒绝均有21/21测试证据。原生产与不可变审查快照未改，补丁可独立重放。

完整LVA任务仍BLOCKED：3249项原始header/真实标准化映射已完成，High1500无缺失，Low1749中290项找不到当前base header直接目标；运行时完整payload消费/应用未执行。不是“CPU遗漏尚未修复”或“等待旧授权”。原始pair不能按可用配置投入GPU；没有准备后继。

后续用户“继续吧”已完成只读官方基模/加载规则核对：官方BF16同样缺相同290项，当前a743 Wrapper的img过滤集合与之精确相等；参考图记录998旧Wrapper，其源码无显式img过滤，历史Comfy/runtime不能据此当已验证。提案 `docs/task-designs/LVA-07-02-img-exclusion-proposal.json` 为关闭状态，要求对全量应用验收做明确调整后，才可将精确290项登记为不适用；其余High1500/Low1459仍严格。没有新状态迁移或实现/策略激活。

## Changed Files

- `docs/task-designs/LVA-07-02-design.md`：追加用户明确修复扩展范围。
- `docs/task-designs/LVA-07-02-fix-design.md`：保留设计，补实现与新阻断说明。
- `docs/task-designs/LVA-07-02-fix-plan.md`：针对性TDD、来源重放、review及报告计划。
- `patches/wanvideo-wrapper/lva07_mixed_delta.py`：真实fork新增CPU私有pair/静态delta及前置拒绝模块。
- `patches/wanvideo-wrapper/mixed-delta.patch`：原custom_linear与nodes_model_loading的6468-byte LF补丁。
- `patches/wanvideo-wrapper/manifest.json`：18份上游审查快照与修复产物SHA。
- `scripts/prepare_lva07_wrapper_fix.py`：本地不可覆盖/来源漂移拒绝的重放构建器。
- `scripts/verify_lva07_wrapper_fix.py`：绑定source SHA的显式CPU验证及结构化报告。
- `tests/experiments/test_lva07_wrapper_fix.py`：21项实际CPU方法测试，常规收集未opt-in时跳过。
- `docs/task-designs/LVA-07-02-fix-results.json`：实际来源、测试、review、边界和阻断。
- `docs/task-designs/LVA-07-02-fix-results.md`：修复结果、重放命令和未验证边界。
- `docs/task-designs/LVA-07-02-tensor-inventory.json`：3249项逐tensor真实header/标准化映射，runtime consumed/applied仍null。
- `docs/task-designs/LVA-07-02-results.json` / `.md`：保留原始RED，关联最新修复及Low缺失目标。
- `docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md`：授权、恢复、部分交付与新阻断证据。
- `docs/task-handoffs/LVA-07-02-handoff.md`：当前交接；历史阻断保留在任务板/结果中。
- `docs/task-designs/LVA-07-02-base-review.json` / `.md`：官方模型身份、精确Range header、参考图及两版源码规则核对。
- `docs/task-designs/LVA-07-02-img-exclusion-proposal.json`：固定原始输入身份和290项精确清单，enabled=false。

## Verification

以下复述已执行结果，创建交接不重跑：

- 初始真实source CPU15项RED；补充边界19项观察2失败/1错误后修复；review新增21项观察2失败后修复。最终独立重放21/21通过、0失败/错误、exit0，原始预期未削弱。
- 实际最终命令：`E:/VideoAI/scratch/benchmarks/LVA-07-02-cpu/runtime/python.exe -I -B scripts/verify_lva07_wrapper_fix.py --source-root E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/final-replay --output E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/final-results.json`。日志同目录final-green.log。
- 构建命令：`.tools/python/python.exe -I scripts/prepare_lva07_wrapper_fix.py --source-root E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit --destination E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/final-replay`，exit0。已有目标和漂移来源各拒绝exit2，目标未覆盖/未创建，工具检查通过。
- 本地source HEAD `801be04a9b4863502b50dd8a353bda45a824e0d1`；replay HEAD `fc08567927de471be7c8ce90cde5b3f270172a5b`。18份来源、19份已测试源码与patch/artifact hash通过；两个源码工作区干净。代码通过后只有来源JSON元数据baseline/LF修正，无被测代码变化。
- Header collector `.tools/python/python.exe -I E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/audit_headers.py` exit0：High1500/Low1749，缺失0/290，已找到shape不匹配0；约0.72MiB header，无payload/全文件重哈希。
- 独立只读review一项Important（旧入口修改状态先于拒绝）和一项Minor（CRLF使patch放大）已处理。新增真实完整入口函数AST回归的I/O/parser使用明确边界fixture；不冒认完整Comfy模块加载。
- 定向结果审计通过21-test结果、19修复/18原始SHA、3249记录/null runtime与0禁止操作。项目`git diff --check` exit0，source分支diff --check在来源元数据LF修正后exit0。
- 常规pytest收集exit0，21项因未opt-in跳过；已有pytest缓存WinError5警告披露，不计为21项通过。产品全库/真实GPU/完整模型/merged：Not run。
- 本轮只读collector `read_remote_headers.py` exit0，4个精确206 Range，两个官方header各113504+8 bytes，共227024 bytes，无tensor payload。官方固定workflow37227 bytes/SHA匹配，SetLoRAs79/80均启用且连接sampler。集合比较High0/Low290，官方/本机缺失及a743 img排除source key集合完全相等。998旧源码只读取证，无显式img过滤；不重跑未改动的21项实现测试。

## Remaining Work

1. 取得对精确290项“不适用”提案的明确验收范围调整，或保留原始全量拒绝要求。官方基模同样没有这些目标，不为此直接下载57GB基模。
2. 验证实际完整converter/loader消费、原始两专家完整应用；保持header证据与runtime证据分层。
3. 完成merged/fullFP8/full-model等尚未验收内容时遵循具体环境/资源与授权边界。

## Resume Task

继续 `LVA-07-02` 的未完成兼容性验收。已交付代码修复和CPU小模型证据应复用，不再从原始3个RED重复开始，不重复下载依赖，不恢复旧生产或运行视频。

## Start Here

依次读取：

1. 任务板本项权威状态及最新repair/input blocker/provenance证据。
2. `docs/task-designs/LVA-07-02-design.md`全文，含用户授权扩展。
3. `docs/task-designs/LVA-07-02-fix-results.md/.json`及原results。
4. `docs/task-designs/LVA-07-02-tensor-inventory.json`的Low缺失项。
5. patch目录manifest及两脚本；需要数学/维护规则时读fix-design。
6. `docs/task-designs/LVA-07-02-base-review.md/.json`及未启用的img-exclusion-proposal，注意998/a743版本区别。

第一步：核对用户是否明确接受精确290项“不适用”的范围提案。没有该确认就保持严格拒绝。若接受，先记录范围变更再独立解除/开始，实施只允许固定身份/精确集合的显式规则；不是泛化过滤，也不表示其余2959项已消费/应用。

## Blocker

- **Reason:** Low原始1749输入中290项在本机及官方base header均无精确目标（82 down、82 up、84 bias、42 diff）。当前a743有精确对应过滤规则，但原全量输入应用验收尚未明确调整；提案未启用，实际原始pair消费/应用仍未验证。CPU代码修复和官方工作流不能自行解除该门槛。
- **Resolution condition:** 有固定身份的Low LoRA/base/实际转换路径证据能为这些输入提供正确目标，并完成相应消费/应用验收，或用户明确修订此项全量消费验收边界后有对应接受证据。记录具体解除事实后才 `BLOCKED -> READY`，再单独开始。不能因代码修复完成或已有下载/修复授权自动解除。

## Risks

只验证CPU小模型、parsed patch协议和scalar-scale float8_e4m3fn算术；每侧256MiB预算不证明14B复制可行。完整节点注册、原始LoRA payload、完整Wan forward、merged、fastFP8/GPU、视频质量和速度仍未验证。header匹配不等于实际应用；相同base header hash不证明payload相同。源副本为18份审查文件的局部snapshot，不是完整checkout；没有生产激活、远程fork/push、新依赖/模型下载或GPU/服务。
