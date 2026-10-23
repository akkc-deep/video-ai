# VCO-01：版本化片段视觉提示契约

## Goal

实施 JIM-08-color-repair-design.md 的 A 阶段，将模型视觉指令与审计证据分离，按 clip 冻结、审查和恢复提示文本。

## Scope

包含 visual_v2 精确配置、schema_version=1 契约、冻结文件、SHA/原文校验、纯渲染、源片请求及视频修订失效。不包含真实推理、整段模式、自动生成/接受提示草稿或颜色验收。用户 2026-10-23“完成任务 VCO-01”授权本任务实现与软件验证。

## Approach

沿用既有 A 阶段字段，不增改其内容语义。`parse_scene_rendering(value)` 接受精确的 prompt_policy/prompt_contract，路径相对配置文件解析；仅 paragraph_jimeng_v1 可用。配置仅存在于 raw，不新增 ProjectConfig 字段，保持无配置的 resolved/options 完全一致。

使用路径：先从已完成语义规划与选图准入的源 run 读取 bible、plan 和 wan-inputs，编写独立契约并完成文本审查，再通过现有 reconfigure 修订入口冻结 visual_v2。绑定已实际准入的输入，不预造未来选图身份。后续改提示继续建立修订；可继承已验证的原文、PCM、计划和图片。

`validate_scene_video_prompt_contract(contract, *, bible=None, plan=None, wan_inputs=None, script=None)` 总是验证精确结构及文本审查；提供上下文时验证三项 canonical SHA、clip 顺序完整覆盖和 changes 的原文 speech unit 范围/逐字 quote。部分上下文拒绝。返回独立副本，不修改输入。

`render_scene_video_prompt(contract, bible, scene, clip_id)` 只提取当前 scene 所引实体 label/fixed_attributes、变体 attributes、环境 environment/time/lighting/spatial_relations，加 style 和本 clip motion/camera/lighting；每个字段单独使用 JSON 字符串编码，含数组的字段使用 JSON 数组。缺正式视觉字段拒绝。changes 只留在审计契约，不输出来源和坐标。文本审核负责原图姿态、阶段及变化的合理性，校验器不按题材关键词自动改写文本。

`runtime/scene_video_prompt_records.py` 解析、冻结及读回契约。freeze_inputs 复制原始字节到 production/scene-video-prompts.json，以 execution_policy.input_identities.scene_video_prompts 绑定；结构/文本审查在冻结时验证，上下文绑定在 scene_context 构造所有请求前验证。无配置时不增加身份或输入字段。scene_context 将 policy 和契约 Artifact 独立写入新 inputs，并加入 guard_paths，发送前重哈希。

build_scene_wan_plan 增加可选关键字 prompt_contract；无新配置时原 renderer 原样运行；配置存在但缺契约时拒绝。comparison_images 保持原审计身份与单 start_image graph。

修订身份旧字段维持原重建函数。新身份显式 schema_version=2，增加 rendering（prompt_policy、prompt_contract_sha256）；planning_sha256 排除 scene_rendering。新身份精确校验，legacy→visual_v2、反向和契约 SHA 变化仅使 clips 及其内容后代失效，保留 common/plan/images/choices/image_group。目标配置身份读实际契约字节；后续冻结必须匹配已提交身份。非 reconfigure 修订继承源 run 冻结契约路径，避免重读已变化的外部文件。

修订绑定细节：继承视图会修改 run_id、PCM/选图路径，不能自动重签 review。`prompt_binding_context` 先验证当前精确绑定；不匹配时，仅当 common、plan、image_group 和全部 choice 都有有效 import 证明，才沿只读源链验证契约原来绑定的已准入数据。任一选图/规划变化都不能用该路径绕过 SHA；保留原契约字节与审查 SHA，目标仍使用被证明语义相同的视觉字段渲染。

连续两次修订、尚未推进中间 run 的 pipeline 时，中间 run 可能未写出派生 wan-inputs.json。仅在中间 run 自身同样具备完整 imports 时，以 build_reference_image_acceptance 只读重建该视图并守卫文件仍然缺席；已有文件必须走 require_reference_image_acceptance 严格验证，不覆盖坏文件，也不重写原 run。非修订源缺少原始准入记录时拒绝。

## Files

- 新增 planning/scene_video_prompts.py、runtime/scene_video_prompt_records.py。
- 修改 config.py、runtime/production_inputs.py、planning/scene_clip_continuation.py、runtime/scene_clip_records.py。
- 修改 planning/scene_revision.py、runtime/production_scene_revision.py、runtime/scene_revision_records.py：版本身份重建、失效及恢复核验；runtime/_scene_revision_origins.py 为继承 clip/upscale 的证据闭包绑定源提示契约。
- 新增 tests/unit/test_scene_video_prompts.py、tests/integration/test_scene_video_prompt_flow.py，扩展修订单元/集成用例。

以上源码路径以 src/video_ai/ 为前缀。

## Tests

所有 Python 命令先 `. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment 'vco01-<stage>'`，用 `$VideoAiPython -B -m pytest`，独立 `--basetemp D:/VideoSi/cache/video-ai/temp/vco01-<stage>-$VideoAiCommandId`；缓存也重定向到该 temp 根，避免仓库 .pytest_cache 权限告警。

先运行新增单元测试看到缺失接口/功能失败，再实现。定向覆盖 test_scene_video_prompts、test_scene_clip_continuation、test_scene_revision、test_scene_clip_generation、test_scene_revision_flow、test_scene_pipeline_recovery；最后裸全库 pytest。期望全部退出 0。检查精确 schema、异常类型/空值、quote/审查 SHA、跨题材/跨 scene 隔离、续片动作、输入不可变、旧请求逐字段、字节漂移零提交和修订不重出图；保留真实命令及日志路径。

## Acceptance

满足任务板 VCO-01 的五项验收，定向及全库实测通过；冻结旧输入和源 run 不被改写；不得把软件验证登记为颜色或动态视频通过。

## Risks

人工或 agent_text 的声明审查不等于视频观看；代码能验证审查内容 SHA 与来源，不能仅靠字符串证明动作、光照语义合理。新契约绑定实际已准入图和计划；实际规划或选图变化后须重新提供匹配的契约和文本审查，只有被 import 证明的 run/path 映射可沿用原绑定。当前环境 .git 只读，在当前工作区保留原有两份未跟踪项目文档，不执行提交或 worktree 元数据写入。
