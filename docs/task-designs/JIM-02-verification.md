# JIM-02 Verification

## Outcome

已完成独立的完整文案 scene 规划、共享视觉设定、固定基准依赖图、PCM/frame 绑定、Wan clip 预算与持锁持久化恢复。新策略全流程保护保留。五项验收及修复后完整历史回归均有下述证据，任务板已记录 COMPLETED。

## Acceptance evidence

1. `tests/unit/test_production_scenes.py` 用真实 ProductionTimeline 验证同段前两句共用一个 scene，另一个提案把三句合为一个 scene；空行保留原始字符范围，不额外出图。
2. 原文、source spans、timeline 字幕不变；首尾和所有停顿覆盖 0..total_frames。非整帧样本相交允许邻 unit 的少量 PCM；逐 unit 验证每个真实样本恰好覆盖一次，缺失、重叠、改写或零帧切点拒绝。
3. entity/variant/group 按首次使用分配稳定 ID，source_facts 与 creative_choices 分开。外观和场景 source_facts/change_sources 在实际使用时拒绝未来依据；实体固定身份仍可读取全文。原文精确 quote、owner、未使用/未知引用和虚构人工选择均检查。
4. `test_visual_consistency.py` 校验最早实际画面作为基准，不加设定图；同来源多用途全部保留，直接引用固定基准。循环、自引用、错误来源、遗漏用途及伪造批次拒绝。稳定批次例 `[[scene_0001],[scene_0002,scene_0003]]`。
5. `test_scene_clip_budget.py` 验证 200 帧画面在 6 秒上限下保留 `[93,92,15]`、生成 `[93,93,17]`、丢首 `[0,1,1]`、裁尾 `[0,0,1]`；边界帧数和非法时长检查。历史槽位接口与校验未修改，原非法跨主单元有效语音仍拒绝。

## Runtime evidence

`tests/integration/test_scene_planning.py` 使用实际本机 HTTP server、OllamaPlanner、HttpClient、RunLock 和磁盘文件，正常一次请求携带全文、全部段落、完整 units 与 timeline。格式/分组错误最多一次完整修正。持久响应、提案或两个输出之间中断均零重复请求恢复；意图无原响应停止。输入、run、settings、prompt、原 HTTP body、bible 或 commit 冲突拒绝；外部调用方锁保留，失锁不发 POST，自有服务在成功/异常后释放，恢复不重启服务。

事务顺序为不可变 inputs/intent → HTTP evidence/response SHA256 → 有效 proposal → visual-bible → scene-plan → scene-plan-commit。所有已有输出在补齐缺失文件前先核对；commit 缺少任一输出拒绝。规划文件重入不改 mtime。原有效 defaults 被保存并恢复。

scene 请求显式 num_ctx=32768、num_predict=8192，UTF-8 prompt/schema 字节上界及 2048 模板余量超限在意图及 POST 前拒绝。输出 length 截断、错误模型或非完成响应不产生 commit。历史请求体不新增上下文选项。

## Commands and results

所有 Python 均先执行 `. ./scripts/bootstrap.ps1` 和 `Initialize-VideoAiEnvironment`，使用 `$VideoAiPython -B`。

- 首轮纯规划：50 passed，新增接口先观察 RED。
- 配置/clip 及相关历史回归：173 passed in 2.59s，缺失 API 先观察 RED。
- 初次运行时 18 个测试先因模块缺失失败；实现后 18 passed。扩展服务/异常测试后发现截断缺口，RED 后修正。
- 独立审查两项 Important：未来服装/场景首用事实泄漏、上下文隐式截断。4 个新测试全部观察 RED（两项 DID NOT RAISE、缺少 num_ctx、超限未拒绝）再修复。
- 修复后设计专项、相关历史回归及 Ollama：**267 passed in 31.29s**，退出码 0。
- 最终全套：**2757 passed in 3790.62s (1:03:10)**，退出码 **0**。输出 `D:/VideoSi/cache/video-ai/logs/jim-02-full-verified.txt`。此前因尚在集成/审查而主动中断的运行没有作为通过证据。

专项完整命令：

```powershell
& $VideoAiPython -B -m pytest tests/unit/test_production_scenes.py tests/unit/test_visual_consistency.py tests/unit/test_scene_clip_budget.py tests/unit/test_scene_planning_config.py tests/integration/test_scene_planning.py tests/unit/test_production_units.py tests/unit/test_production_timing.py tests/unit/test_production_visual_plan.py tests/unit/test_production_visual_records.py tests/unit/test_jimeng_inputs.py tests/integration/test_jimeng_candidates.py tests/unit/test_ollama.py -q --tb=short
& $VideoAiPython -B -m pytest -q --tb=short
```

## Independent review and boundaries

独立审查直接读取全部实现与测试，未修改源码。Critical=0、Important=2（均已用失败测试修复）、Minor=0。未来服装问题有实际纯 API 重现；输入截断缺口由请求体与运行时路径审查确认，没有调用真实 Ollama 测试其截断行为。

审查边界裁定：真实模型语义/视觉一致性留给后续实际看图/观看；真实 Ollama 启动/tokenizer/硬件容量未测试，当前只证明保守准入及自有服务清理协议；沿用现有 adapter 的 ownership callback 到 transport 的微小 TOCTOU 窗口，不增加无证据的新机制；收费生成、上传、选图、成片和下游 commit 消费在后续任务实施；示例与使用文档由本次交付补齐；全套通过结果独立记录，审查不替代测试。

## Limits

没有真实收费出图、上传或邮件。自动结构检查不表示图片、动态视频或最终成片一致性已经通过。保守上下文预算会拒绝部分实际 tokenizer 可能容纳的长材料；不会通过截断原文继续制作。
