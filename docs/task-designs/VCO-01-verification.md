# VCO-01 软件验证记录

日期：2026-10-23。以下为本任务软件验证；没有提交 GPU/付费推理，没有新增颜色或动态视频通过证据。离线 Wan 输出为 FFmpeg 合成测试媒体，观察记录为明确标记的测试替身。

## 环境与输入保护

仓库 D:/code/py/video-ai；Python 3.12.10，bootstrap.ps1 初始化，所有测试运行缓存、日志和独立 basetemp 位于 D:/VideoSi/cache/video-ai。原先未跟踪的 proposal 与 task-board 是本任务输入，保留其内容并仅对任务板进行必要状态更新。.git 只读，未创建分支、提交或推送。

集成测试逐文件比较源测试 run 的 mtime_ns、size 和 SHA256，提示修订保留原文、PCM、语义计划和所有已准入图片，所有图片/规划/邮件请求工厂均禁止调用。外部契约源文件改变或删除后按冻结副本恢复；冻结契约的同长度、恢复 mtime 字节漂移应在构造网络客户端前拒绝。

## RED/GREEN

日志均在 D:/VideoSi/cache/video-ai/logs/：

- 基线 continuation/revision：94 passed，退出 0；vco01-baseline-713b99a1581a4fe2a6633aaa4a1b8bad.log。原仓库 pytest cache 不可写告警，此后显式使用独立运行缓存。
- 契约 RED：缺少 scene_video_prompts 模块，退出 1；vco01-contract-red-1d31e5d1e17e436a802589c56c60e7b0.log。
- 契约/旧续片 GREEN：83 passed，退出 0；vco01-contract-green-ad30bb3ae0f448a79ad5e40835d6bdc8.log。
- 渲染身份 RED：缺少新 schema_version，退出 1；vco01-revision-red-29245bcf81b54aee9efb26469abc1205.log。
- 契约/续片/修订 GREEN：145 passed，退出 0；vco01-revision-green-2fbbc22ac3f54b43bd68c4b334a3238d.log。
- 运行层 RED：提示配置被归入 planning_sha256，导致原图失效；vco01-runtime-red-8e3f5dcecb1347b6aa648b5665366f48.log。
- 集成初版调用失败：跳过 pipeline 图片准入汇总，缺少新 run 的 wan-inputs.json；1 failed、2 passed，退出 1，vco01-runtime-scoped-98a627c202224389a807d55dff9634ab.log。后续用正式 pipeline 推进，拒绝图片/邮件/规划工厂，验证无重出图。
- 两次中断的调试运行（runtime-green、runtime-diagnose）没有登记通过；无 revision_scope 的测试直接调用会反复深度重建来源证明，已按正式入口的作用域修正测试组织。
- 祖先契约守卫 RED：正式离线 pipeline、漂移零提交和父子片恢复 3 passed；修改祖先契约后 guard 未拒绝（DID NOT RAISE），1 failed，退出 1；vco01-runtime-flow-8ddbefc7148d41deb697072e7c870266.log。修复为仅对启用 visual_v2 的 clip/upscale 捕获冻结契约路径。
- 首次合并定向收集发现 unit/integration 同名 test_scene_video_prompts.py 导致 pytest import mismatch，退出 2；vco01-targeted-0b88c6db194a49fcb89864e68b555581.log。集成文件改为 test_scene_video_prompt_flow.py，保留单元文件名。
- 中间修订尚未落地 Wan 汇总的 RED：FileNotFoundError，退出 1，vco01-binding-red-643c64fea8cf4c6a84a091cfeeafa52f.log；限定完整 imports 才只读重建后，契约/续片/修订单元 151 passed、退出 0，vco01-binding-green-deacaa406fab430693c3567996f2b09d.log。源文件已存在时不走重建分支。

最终源码/测试的 path、bytes、SHA256 快照：D:/VideoSi/cache/video-ai/logs/vco01-source-snapshot.json；全库验证后复验，防止用旧代码结果代替最终源码验证。

## 独立审查

只读 reviewer 检查精确 schema、review SHA、纯视觉输出、旧路径兼容及版本化恢复，发现一项 Important：clip/upscale 来源闭包遗漏祖先 scene-video-prompts.json。以修改祖先契约字节、复验 guard 的实际回归用例处理；不将首次 load_frozen_inputs 的核验视作整个调用期间的持续守卫。

## 最终验证

验收映射：

| 任务板验收 | 对应验证 |
|---|---|
| 精确 schema、审查/绑定 SHA、原文引用与完整 clip 覆盖 | test_scene_video_prompts.py 的 schema、changes、覆盖与三项绑定用例；合法策略下配置拒绝与冻结无效 JSON 用例 |
| 当前 scene 纯视觉与逐 clip 阶段 | 人物/机械臂/树叶渲染、审计字段隔离、换行引用、缺正式字段拒绝、源片/续片不同 motion 的真实请求记录 |
| 旧 options/inputs/parameters/graph 与重建兼容 | 保留原 test_production_inputs、test_scene_clip_continuation、test_scene_clip_generation、test_scene_revision_flow 和 test_scene_pipeline_recovery；无配置分支不新增身份字段 |
| 视频后代失效并合法继承通用前缀/选图 | 版本化 rendering 身份单元用例；离线正式 pipeline 禁止新规划、图片与邮件工厂，源树身份保持一致；修订恢复/观察/超分/合成原回归 |
| 漂移零提交、恢复与修订 | 冻结后同 stat 字节漂移、预检后发送守卫、祖先 clip 来源守卫、重复恢复不二次提交、外部契约源变化后使用冻结副本、中间继承视图重建 |

以上五项软件验收映射均已由最终全库验证通过；没有将软件结果登记为真实视频颜色或动态观看通过。

最终源码的裸全库命令如下（没有路径、-k、-m 或跳过选择）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco01-full'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest','-v','-o',"cache_dir=D:/VideoSi/cache/video-ai/temp/vco01-cache-$VideoAiCommandId",'--basetemp',"D:/VideoSi/cache/video-ai/temp/vco01-full-$VideoAiCommandId")
exit $VideoAiExitCode
```

运行日志：D:/VideoSi/cache/video-ai/logs/vco01-full-85499112ee604420b26fd6fb13e22ba4.log。最终结果：**3715 passed in 19118.06s (5:18:38)，退出码 0**；无失败、跳过或告警摘要。完整测试包含新增发送前 SHA 守卫、祖先契约字节闭包及非 reconfigure 继承测试，以及原 200 帧长链的 93/92/15 分配和精确映射回归。

运行后复验 vco01-source-snapshot.json 中全部 13 个源码/测试文件，bytes 和 SHA256 均相同；git diff --check 退出 0。最终代码没有使用旧版本的通过结果。先前定向运行 ef287468262c42738d00036c2bf34628 已中断并由该最终全库覆盖，不登记为全部通过。后续仅补齐任务文档和交接，不再修改已验证源码。
