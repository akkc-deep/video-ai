# JIM-02 段落关键画面、共享视觉设定与时间预算

## Goal

读取完整原文、已冻结旁白单元及实际 PCM 时间轴，归纳少量可跨多句的 scene，并产生共享视觉设定、基准依赖图及 clip 预算。完整配音、字幕、样本数和总帧数保持不变。

## Scope

实现独立 scene 规划/校验 API、Ollama 规划适配、持久化恢复和 scene/clip 纯数据预算。新增 `production/visual-bible.json`、`production/scene-plan.json`、`production/scene-plan-commit.json`。不提交即梦、Wan、TOS 或 SMTP，不实现选图/观察/交付，不改变历史 `StoryboardSlot` 校验，也不移除 JIM-01 对尚未完成的新策略全流程协调器的保护。

这是任务板 Order=2 的实施契约；JIM-01 已先记录 COMPLETED。最终实现和验收结果单独记入 JIM-02-verification.md 及任务板。

## Approach

### 接口与配置

新增 `planning/production_scenes.py`：

- `paragraphs_from_script(script: SegmentedScript) -> list[dict]`。
- `make_scene_schema(script, units, timeline, settings) -> dict`：固定键 JSON schema。
- `build_scene_plan(script, units, timeline: ProductionTimeline, proposal: dict, *, settings: ScenePlanningSettings) -> tuple[dict, dict]`：返回 `(visual_bible, scene_plan)`。
- `validate_scene_plan(script, units, timeline, visual_bible, scene_plan, *, settings) -> None`：重新推导所有数字和引用；不得只检查模型给出的 passed 标记。

新增 `planning/visual_consistency.py`：`validate_reference_graph(scenes, bible) -> list[list[str]]`，返回稳定拓扑批次；不做视觉验收。

在 `production_visual_plan.py` 增加 `plan_scene_clips(scene_plan, *, max_clip_seconds) -> list[dict]`，不修改现有 `build_production_budgets`、`plan_production_source_clips` 和旧 `production_frame_mapping` 的语义。

新增 `runtime/production_scene_plan.py`：`produce_scene_plan(frozen, units, timeline, *, paths, logger, lock=None, planner=None) -> tuple[dict, dict]`。入口自行获取 RunLock，或消费调用方提供的现有锁。`planner` 为可注入的 OllamaPlanner；默认使用既有本机服务管理和 `qwen3:8b`，不增加模型。持锁前不写盘，失去锁后不请求或提交记录。

新增 `ScenePlanningSettings(target_scenes_per_paragraph=3, max_clip_seconds=6)` 和 `parse_scene_planning(value)`。`target_scenes_per_paragraph` 是正整数，拒绝 bool；`max_clip_seconds` 是有限正数，转换后须容纳至少 5 个原生帧。配置只在新策略允许根字段 `scene_planning`，缺省使用不可变的 `scene_planning_v1` 上述默认。配置中的显式值已经随 JIM-01 的 raw 源配置冻结；规划记录还必须保存完整有效 settings 和算法版本。不要为该设置向 ProjectConfig 添加会改变旧序列化形状的 dataclass 字段；由纯解析函数读取冻结的 raw 字段。

JIM-01 schema=2 options 和候选记录保持可读。恢复已有规划时消费其有效 settings，不因后来代码默认值变化重做规划；显式配置或源输入变化拒绝。旧 schema=1 项目继续原来的字段集合与消费者。

### 原文、段落与提案

`units` 使用现有 `production/units.json` payload 的 `spans/semantic_specs`；`timeline` 使用 `ProductionTimeline`，先执行其完整样本校验。旁白/字幕原文继续取原始 source_spans，不能用摘要重新配音或替换字幕。

段落按原文每个 CRLF、单 CR 或 LF 分界；CRLF 视为一个分隔符。范围包含该行末的分隔符，最后一段结束于 len(text)，完整覆盖原始 Unicode 字符；空行保留为段落但没有 scene。ID 按原文顺序为 `paragraph_0001` 等。speech unit 必须完全属于一个段落；跨界拒绝。空白或标点 skip 不发起 scene，也不丢弃原文。

模型一次看到完整 `decoded_text`、所有段落范围、全部 finalized units/事实和完整旁白时间轴，只输出视觉提案，不输出配音文本、帧边界或任务身份。提案精确顶层字段：`global_style/entities/appearance_variants/scene_groups/scenes`。不得沿用旧的逐槽位视觉 schema。

每个有语音段落输出 1 至 `min(target_scenes_per_paragraph, speech_unit_count)` 个 scene；可为同主题多句输出一个画面。目标数限制下无法保留必要场景变化时返回明确规划错误，要求调整规划配置，不能静默增为逐句出图。至少一个测试提案必须把同段两句归入一个 scene。不得用标点计数替代模型语义分组。

提案 scene 精确字段：`paragraph_id/unit_ids/summary/image_prompt/motion_prompt/entity_ids/variant_ids/scene_group_id/change_sources`。`unit_ids` 必须是该段中连续 speech 单元，每个语音单元全局恰好出现一次，顺序与原文一致；不跨段合并。summary 是视觉摘要，两个 prompt 是非空可见画面/动作描述，不能冒充原文或人工结论。

稳定 ID 由程序按首次出现顺序分配 `scene_0001/entity_0001/variant_0001/group_0001`。模型用提案内局部 `key` 关联，程序验证唯一性后替换；未知/重复 key 拒绝。提案实体/变体/场景组字段分别为：

- entity：`key/label/fixed_attributes/source_facts/creative_choices`。
- appearance_variant：`key/entity_key/attributes/source_facts/creative_choices/change_sources`，描述服装等可随剧情变动的属性。
- scene_group：`key/label/environment/time/lighting/spatial_relations/source_facts/creative_choices/change_sources`。
- global_style：`description/source_facts/creative_choices`。

提案 scene 的 `entity_ids/variant_ids` 在替换前为对应列表的局部 key 数组，`scene_group_id` 为场景组局部 key；最终记录才使用程序分配的 ID。每个 scene 必须关联一个场景组，实体与变体数组可为空；关联变体所属实体必须同时列于该 scene 的 entity_ids。数组内重复引用拒绝；首次出现按 scene 顺序及其引用数组顺序确定，场景组按 scene 顺序确定。

以上 attributes 为非空字符串数组（允许空数组表示原文未定）；source_facts 行为 `name/value/sources`，sources 行为 `unit_id/text_start/text_end/quote`，必须落在指定 finalized unit 原文范围且 quote 与原文切片完全相等。creative_choices 行为 `name/value/reason`，必须明确为创作建议，不能假标来源。change_sources 为同样的原文 source 行数组；同实体变体变化、场景组变化必须给出当前或先前已发生的原文依据，不能引用未来剧情提前换装/换景。

相同指代通过完整原文、既有 semantic_specs 和模型返回的共享 key 归一到同一个 entity；不增加题材专用名词表，不靠固定种子宣称一致。属性未定时保持未定或提出 creative_choices，等后续真实选图确定，不能编造“用户已选”。

外观变体与场景组的 source_facts 也受实际使用 scene 的原文截止位置约束，首次基准不能引用未来服装或地点事实。global_style 与实体固定身份事实可以读取全文；不能把随剧情发生的变化混入不受时间约束的属性。

### 视觉设定、基准与依赖

`visual-bible.json` 精确字段：`schema_version/production_strategy/run_id/algorithm/source_sha256/units_sha256/timeline_sha256/settings/global_style/entities/appearance_variants/scene_groups/baselines`；schema=2、strategy=`paragraph_jimeng_v1`、algorithm=`scene_planning_v1`。所有 identity SHA256 使用规范 UTF-8 JSON（sort_keys、紧凑分隔符、allow_nan=false）或原始脚本字节，不能混用对象 repr。source_sha256 使用冻结 script FileIdentity。

分配 ID 后，entity/variant/group 的最终行移除 `key`，分别改为 `entity_id`、`variant_id/entity_id`、`group_id`，保留上面的所有属性和来源字段。每组的基准是它首次出现在实际 scene 中的图片，不增设额外角色设定画面。

`baselines` 行精确字段为 `kind/id/scene_id`，kind 为 `entity/appearance_variant/scene_group`；顺序按 kind 的上述顺序及各列表 ID 顺序。entity 基准保持物理身份，variant 基准保持特定外观，group 基准保持环境。每个使用过的实体/变体/组恰好有一个基准，未使用条目拒绝。

每个 scene 派生 `reference_bindings`，行字段为 `source_scene_id/uses`；uses 行字段为 `kind/id`。直接引用各项固定基准，基准等于本 scene 时不产生自引用。同一来源图合并成一个 reference_bindings 行但保留全部用途，不以合并为由丢弃主体。source_scene 必须较早出现，且真实含有所声明的 entity/variant/group；禁止只通过相邻画面替代固定基准。

`dependencies` 是去重后的 source_scene_id，按 scene 顺序排列。Kahn 稳定拓扑排序产生 `batches`，每一批按 scene 编号排序；全部零入度实际 scene 同批，移除该批后才计算下一批。循环、未知 ID、自引用、错误来源、遗漏用途或伪造批次都拒绝。仅记录依赖，不在本任务触发候选/选择；模型参考能力及数量限制由 JIM-04 准入。

### 完整时间覆盖与 clip 预算

scene 顺序由语义分组确定后，数字由程序推导：首 scene.start_frame=0；每个后继 scene 的起点为其首个 unit 在 timeline 中 `start_sample` 经既有 `sample_to_frame(...,16)` 四舍五入的帧；前 scene.end_frame 等于后 scene.start_frame；末 scene.end_frame=timeline.total_frames。非正长度或不可严格递增的切点拒绝提案，并在一次修正请求中要求合并过短组，不静默删帧。首尾、段落/句停顿都包含在覆盖范围。

scene 的样本窗口为 `[start_frame*3000, min(end_frame*3000,total_samples))`。bindings 由该窗口与每个旁白 clip 的 `[start_sample,end_sample)` 交集生成，保存 `unit_id/text_start/text_end/text/semantic_member/start_sample/end_sample`；这些 start/end_sample 是绝对交集，原文范围和 text 仍为完整 unit。semantic_member 表示是否在该 scene 的 unit_ids 中；量化边界可带相邻 unit 的小范围交集。逐 unit 汇总 bindings 必须恰好覆盖其全部 PCM 样本且无重叠；新 schema 允许多个 semantic_member 各自含完整有效语音，不调用旧“非主单元最多一帧”校验。

`scene-plan.json` 精确字段：`schema_version/production_strategy/run_id/algorithm/source_sha256/units_sha256/timeline_sha256/settings/visual_bible_sha256/total_samples/total_frames/paragraphs/scenes/batches/clips`。scene 最终精确字段：`scene_id/paragraph_id/unit_ids/text_start/text_end/summary/image_prompt/motion_prompt/entity_ids/variant_ids/scene_group_id/change_sources/start_frame/end_frame/bindings/reference_bindings/dependencies`。text_start/end 是首末语义 unit 的原始字符包络。paragraph 行为 `paragraph_id/text_start/text_end/unit_ids`。

Wan length 必须满足 4n+1。令 `L=floor(max_clip_seconds*16)`、`M=1+4*floor((L-1)/4)`，必须 M>=5。首 clip 最多贡献 M 帧；续 clip 最多贡献 M-1 帧，以便多申请并丢弃一个首部衔接帧。每次贪心取容量以内的剩余帧，`generated_frames=_wan_frames(retained_frames+discard_head_frames)`；首片 discard_head_frames=0，续片=1。末尾多余帧为 trim_tail_frames，不参加成片，不作下一片尾帧来源。

默认 6 秒：L=96、M=93。200 帧 scene 精确拆为贡献 `[93,92,15]`，生成 `[93,93,17]`，丢首 `[0,1,1]`、裁尾 `[0,0,1]`。不因为多出 clip 而新增 scene 或图片。

clip 精确字段：`clip_id/scene_id/ordinal/parent_clip_id/input_kind/start_frame/end_frame/retained_frames/generated_frames/discard_head_frames/trim_tail_frames/retained_source_start/retained_source_end`。clip ID 为 `<scene_id>_clip_0001`；ordinal 从 1 开始；首片 parent=null、input_kind=`selected_scene_image`；续片指向同 scene 直接前片、input_kind=`parent_retained_last_frame`。retained_source_start=discard_head_frames，end=start+retained_frames。该数据只规划未来输入来源，不假造图片哈希、父片生成或观察通过。

### 持久化、失败和恢复

复用既有 OllamaPlanner/on_intent、HttpClient 的本机限制、服务 ownership 及 stop_owned_preserving_exception。全部请求提示词始终带完整原文；允许一次格式/规划修正请求，修正失败停止，不能无限循环。未知原请求优先消费原 HTTP 证据；缺少完整证据时明确停止，不能普通续作自动重新请求。规划不涉及收费即梦提交。

仅 scene 请求显式固定 num_ctx=32768、num_predict=8192，保留 2048 token 模板/系统余量。以完整 prompt 和 JSON schema 的 UTF-8 字节数作为保守 token 上界，在意图持久化和 POST 之前准入；上界加输出及余量超出容量则明确停止，不裁全文或静默缩短输出预算。done_reason=length 同样停止，不提交有效计划；历史请求体保持原有选项。

在 `production/scene-planning/` 保存不可变 planning-intent、原 response 身份和有效提案；记录绑定 run、script/units/timeline/settings 和 schema/prompt 摘要。所有恢复先重算输入 SHA256；输入变化、手改提示词或输出冲突一律拒绝。规划结果若已经存在且身份一致，零模型请求返回，不重写文件。

先通过完整纯校验，再使用同目录临时文件+fsync+原子改名依次提交 visual-bible 和 scene-plan，最后写 scene-plan-commit。commit 精确字段：`schema_version/run_id/source_sha256/units_sha256/timeline_sha256/settings/visual_bible_sha256/scene_plan_sha256`。下游只消费有有效 commit 且哈希均匹配的计划。提交中断可从已保存提案补齐缺失文件；已有文件不一致时停止，不能覆盖历史。规划状态是 proposed，不得写 passed 的一致性或人工验收结论。此独立计划不塞进旧 storyboard payload/Comfy UUID 字段。

## Files

- 新增 `src/video_ai/planning/production_scenes.py`：段落/提案/schema、scene 时间与 bindings 纯校验。
- 新增 `src/video_ai/planning/visual_consistency.py`：共享来源、基准/依赖图纯规则。
- 新增 `src/video_ai/runtime/production_scene_plan.py`：持锁规划与事务恢复。
- 修改 `src/video_ai/config.py`：允许/校验新策略 scene_planning；保持旧 dataclass 序列化和冻结快照。
- 修改 `src/video_ai/planning/production_visual_plan.py`：新增独立 plan_scene_clips，不改旧接口。
- 修改 `config/jimeng.example.json`、`docs/jimeng-candidates.md`：记录已实现的规划 API 与配置；不可声称全流程已接通。
- 新增测试 `tests/unit/test_production_scenes.py`、`tests/unit/test_visual_consistency.py`、`tests/unit/test_scene_clip_budget.py`、`tests/integration/test_scene_planning.py`。

## Tests

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-02-tests'
& $VideoAiPython -B -m pytest tests/unit/test_production_scenes.py tests/unit/test_visual_consistency.py tests/unit/test_scene_clip_budget.py tests/integration/test_scene_planning.py -q
& $VideoAiPython -B -m pytest tests/unit/test_production_units.py tests/unit/test_production_timing.py tests/unit/test_production_visual_plan.py tests/unit/test_production_visual_records.py tests/unit/test_jimeng_inputs.py tests/integration/test_jimeng_candidates.py -q
```

下列场景已按实施契约建立测试；实际命令、结果和审查修复见 `JIM-02-verification.md`：

1. 同段三句“湖面很静。白鸟停在石上。它望向远处。”的固定替身提案前两句共用 scene；完整原文和字幕不变。另一提案可把三句合成一个 scene，证明数量不由句号决定；短段一个 scene，空行不出图。
2. 以真实 ProductionTimeline 构造首尾/句停顿/段停顿及非整帧样本；scene 从 0 连续覆盖至 total_frames，bindings 对每条 PCM 全量且恰好覆盖。缺失 unit、跨段合并、重复/乱序、零帧 scene、样本空洞和 text 篡改均拒绝。
3. 同主体跨三 scene、跨段“它”的来源正确；fixed_attributes/source_facts/creative_choices 不混用。原文换装产生有依据的 variant，未知引用、错误 quote、未来换装依据、伪造用户选择拒绝。
4. 基准选最早实际 scene，不增加设定图；稳定批次如 `[[scene_0001],[scene_0002,scene_0003]]`。循环、自引用、错误来源、遗漏实体/背景用途拒绝；同图多用途合并但用途完整。
5. 200 帧、6 秒上限按上述 `[93,92,15]` 数值例逐项断言。测试 1/93/94/185 帧边界、短上限与浮点取整；每个 generated_frames<=floor(seconds*16)、4n+1，贡献总和等于 scene 长度且图数不变。
6. 本地 HTTP 替身收到完整原文和全部段落，正常成功请求一次，格式错误最多一次修正；持久提案或双文件提交中断后零重复请求恢复。改变原文/单位/时间轴/setting/run/commit 哈希拒绝；自有服务和锁在异常后释放；不产生即梦/Wan/SMTP 请求。
7. 历史单主单元/槽位限制仍严格拒绝原来非法的跨主单元有效语音；新规则只用于 scene schema=2。JIM-01 schema=2 options/候选仍可读，旧 schema=1 resolved 字段不增加。

## Acceptance

任务板 JIM-02 五项验收逐项由 Tests 1、2、3、4、5/7 证明；运行时实际写出可校验的 visual-bible/scene-plan/commit，并能从中断恢复。只有在规划输出及历史回归都通过后记录完成；规划自动通过不代表图片、动态视频或最终成片一致性通过。

## Risks

LLM 规划只能保证结构、来源和时间覆盖可核验，语义解释仍可能有误，后续实际选图与连续观看不可省略。默认 6 秒是请求时长上限，因 Wan 4n+1 约束实际首片最大 93 帧而非 96 帧；不得为凑整多生成并保留超上限时长。模型上下文超限或材料不足必须明确停止，不能裁掉原文后继续。JIM-01 只有候选 API，新策略全流程协调仍需后续任务，不因规划完成而开放未经选图的 Wan 路径。
