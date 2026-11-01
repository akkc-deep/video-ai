# VCO-04 配置与策略冻结实施记录

范围仅为设计第 3 节对应的配置解析和冻结输入；本记录不代表整个 VCO-04 已完成。

## 实现

- `src/video_ai/config.py` 新增 `parse_scene_continuity()`，精确接受 `{"schema_version":1,"policy":"advisory_v1"}`，拒绝未知键、部分/null 配置、bool/浮点版本及其他 policy。只有 `paragraph_jimeng_v1` 可声明该配置。
- 不扩展 `ProjectConfig` 字段，不给缺省配置补键；因此既有 resolved 配置身份没有新增默认字段。
- `freeze_inputs()` 仅在原配置明确声明策略时写入 `production/scene-continuity/policy.json`，以原五字段 `FileIdentity` 放入既有 `execution_policy.input_identities.scene_continuity_policy`。没有新增 options 顶层字段，保持 schema 2。
- `load_frozen_inputs()` 由原冻结 config 决定是否要求该身份角色，校验准确路径、原五字段身份、实时 SHA 和严格解析后的策略含义。配置缺角色、角色缺配置、重复/未知角色、错路径、缺文件、SHA 漂移、重算 SHA 后的非法策略及三字段 Artifact 替代均被拒绝。
- 未配置的旧 run 不读取诊断目录，不会因后来出现的 `policy.json` 自动启用，也不重写原 options。输入冻结代码直接使用配置解析器，没有为解析导入连续性 runtime records 或数值依赖。

## 定向 TDD 证据

新增 `tests/unit/test_scene_continuity_policy.py`，共 27 个展开测试用例；复用既有本地资源 fixture，不启动服务、模型或网络。

1. ROOT 协调串行 RED，生产代码尚未修改：该文件 10 项失败、17 项通过。失败为尚未支持的 `scene_continuity` 配置；17 项为原有严格拒绝和缺省兼容行为。合并运行中另有两个 records 缺失导入失败，属于 ROOT 的独立实施范围。
   日志：`D:/VideoSi/cache/video-ai/logs/vco04-policy-records-red-e97942dfa6874bb49b4163a87ea3c865.log`。
2. 增加最小实现后，按 ROOT 分配的串行测试时段执行以下命令，退出 0，`27 passed in 2.70s`，无 skip。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco04-policy-green'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest','-q',
 'tests/unit/test_scene_continuity_policy.py',
 '-o',"cache_dir=D:/VideoSi/cache/video-ai/temp/vco04-policy-cache-$VideoAiCommandId",
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco04-policy-$VideoAiCommandId")
exit $VideoAiExitCode
```

GREEN 日志：`D:/VideoSi/cache/video-ai/logs/vco04-policy-green-753fccc9c2154755865e5371c10993b6.log`。

覆盖包括同 size/mtime 的内容漂移、原配置源后来不可读时继续使用冻结副本、原 options 字节只读恢复、legacy/schema 2 两条无策略分支，以及未配置但出现诊断目录时仍保持未启用。既有生产输入和 Jimeng 配置兼容测试待 ROOT 统一串行安排，其结果由总验证记录汇总。

未运行全库测试、GPU、真实服务、付费调用或实际完整视频观看；没有修改示例/真实配置、运行时 records 模块、旧冻结产物或 `.git`。
