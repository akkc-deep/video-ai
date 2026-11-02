# VCO-08 Native16 Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 真实验证768×432、16fps、四窗320帧资格样片。

**Architecture:** 从已接受native15案例的冻结源派生独立案例，新增纯协议模块与固定shape子类，保持官方采样路径。资源/一次采样/未知不重跑门禁沿用；新视频单独观看。

**Tech Stack:** Windows PowerShell bootstrap、stdlib Python3.12、既有嵌入式3.13/Torch2.13+cu130、原LongCat代码与模型/隔离依赖。

**Spec:** `docs/task-designs/VCO-08-native16-qualification-design.md`

## Global Constraints

- 用户已选“按建议直接推进，无需逐步确认”；本阶段直接执行。
- 不写.git、不新下载/文本编码/模型副本、不改旧案例；新目录`D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification`。
- CPU测试与GPU串行，监测现有回归session33919至退出，不修改其src/tests/scripts。
- 无执行时间/人工占用上限；原实际余量门槛不变；每窗最多一次，unknown不重采样。
- 固定93+80+80+67、320帧/16fps/20秒，13历史只输出一次，末窗裁尾13，不改官方数学。

## Review Focus

- 末窗13历史与13裁尾不能混淆；320输出映射每帧唯一。
- 实际模型条件须为父窗13帧，不能只改审计元数据。
- 480p/15fps旧资源或媒体证据不能满足新准入。
- 缺失文本缓存必须拒绝，不触发重编码。
- 旧intent/failed/unknown不能获得新采样机会；成功latent才可decode-only。

## Progress / Rulings

- 用户已明确连续推进；文档记录实施选择，不再加入设计批准等待。
- 既有dirty workspace授权与.git只读约束优先于skill默认worktree/commit流程；本计划仅文件变更、证据落盘，不创建worktree或commit。
- 当前native15整链已接受；native16所有真实技术/视觉结论初始unverified。

### Task 1: 新身份与纯协议

**Files:** 新目录`prepare_native16.py`、`native16_contract.py`、`native16_contract_probe.py`；复制27源所需小文件及原case/text binding/reference。

**Interfaces:** `window_mapping(stage)`返回raw93/context/append/chain/tail精确范围；`condition_shape(resolution, scale_factor_spatial)`返回(432,768)，仅允许432p-native16及可整除尺寸的正整数scale。

- [x] 写probe，缺模块运行RED；断言stage1..4分别[0,93)、[13,93)、[13,93)、[13,80)，累计320，非法stage/标识/scale拒绝。
- [x] 实现纯模块；原25源逐项SHA核对后复制，新case保存原文本来源；用原SHA证明文本/首图不变、权重复制/下载/编码0。
- [x] 运行probe GREEN，保存身份与命令结果。RED日志3ec7070、GREEN/准备34a4dce；新case SHA44bdb18c5eba8084a936b198d458d5b33f83bcd26f5fb11e010c4823fd5d0139。

### Task 2: 固定shape pipeline与执行源适配

**Files:** `native16_pipeline.py`、`native16_pipeline_probe.py`、新副本worker/media/resource/state/supervisor/freeze/admission/assemble。

**Interfaces:** `Native16Pipeline`只覆写官方`get_condition_shape`；worker/probe均使用该类。worker的prompt_context改为只读缓存；mapping统一消费Task1函数。media时钟固定16；新资源门禁核对实际VAE[1,16,4,54,96]、输出[93,432,768,3]、KV4076863488字节及部署clock16。

- [x] 原类对新分辨率入口RED；实现子类后官方i2v/vc入口形状路径GREEN，不进入采样。日志ff43f0b→6df5726。
- [x] 新目录替换硬编码480/832/60/104、stage上限、15fps及末窗mapping；不改官方working源或数值适配。9项修改及SHA保存在source-adaptation.json。
- [x] probe覆盖缺缓存/资源shape或clock漂移拒绝、最终mapping；真实tiny raw/viewing时钟与PTS通过。worker a9ccff9 RED→59882b5 GREEN，admission 9fe053f RED→a1f83f8 GREEN；media cd9b070通过。27源freeze与worker --check日志f042034退出0，software SHAe21f5a7ed34736e85acff28af8785a05a8b4a5837fd90dc69bcba898f65d96d8。真实多窗组装仍留Task3，不把fixture当资格视频。
- [x] 一次fresh-context只读审查新目录增量。native16_qualification_review无Critical/Important/Minor；9修改SHA及11官方源一致，review.json保留。Ruling：review在最终freeze前完成，review后未修改27项执行源；freeze/worker检查确认相同内容。

### Task 3: 资源准入与四窗实际运行

**Files:** 新目录资源/布局/准入收据、window001..004、chain004。

- [ ] 等当前CPU回归退出并处理实际失败，读取主机余量。
- [ ] 运行五阶段真实新shape探针，无scheduler/视频；完整成功后freeze/layout/final-admission一致。
- [ ] 仅清理已退出资源探针的自有KV scratch，保留元数据/收据；实际窗口KV保持。
- [ ] stage1一次，核验技术+实际静态；无明显失败签发下窗screening，再按相同规则顺序stage2/3/4。失败停止，不重采样。
- [ ] 组装320帧，核验实际SHA/13历史/48层真实KV/输出PTS与映射；提交完整20秒视频并等待新的完整动态反馈。
- [ ] 按事实更新实录/板、生产适用范围和后续接口设计；不把资格样片当VCO-08全部完成。

## Verification commands

每条Python经项目bootstrap；CPU合同probe：`Invoke-VideoAiNative $VideoAiPython @('-B','<new-root>/native16_contract_probe.py')`。pipeline/数值脚本使用既有嵌入式Python。真实命令按顺序为`full_dit_resource_probe.py`、`freeze_software.py`、`checkpoint_layout_probe.py`、`final_admission_check.py`、`supervise_window.py --stage N`及`assemble_chain.py --windows 4`。每项必须退出0并核对实际收据；研究完整动态接受另记。
