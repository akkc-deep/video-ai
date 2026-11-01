# VCO-06 观察页保存修复交付

2026-10-29。用户已填写选项，但保存按钮提示“请明确目标颜色、结构、动作和光照意图；不确定时选择未确认”。实际原因是保存动作被确认资格的条件提前阻断，而非缺少所有选择。

## 使用入口

[修复版开发集观察页](D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261028-acquire-62d31ee3276941ecb65e35e23e4db250/observe-12-save-fixed.html)

- 按钮改为“保存填写结果”。条件未齐/有冲突时仍可导出草稿，原选择逐项保留，不替用户改成“未确认”。
- 提示具体字段，例如是否确认原图为目标、主体/动作选为否或未确认、光照选择为存在合理变化等。
- 完整且一致的观察仍导出旧正式schema；未满足项导出独立 `natural_material_observation_draft_v1`，旧观察校验器明确拒绝它成为正式标签。草稿不能用于资格/候选/改善通过。
- 本地按collection/媒体身份暂存各段填写，切换素材时恢复。浏览器禁用存储也不妨碍当前导出。
- 始终展示完整可复制JSON；下载被阻止时可使用复制出口。页面仅声称发起下载，不假称已确认文件落盘。

**原来已打开的旧页没有草稿缓存，尚未导出的填写不能从磁盘自动取回或迁移到新版。保留旧页，不要刷新/关闭，必要时与新版对照。** 修复不能证明此前未保存的答案或播放事件已经恢复。

## 验证

Node执行真实模板JavaScript：初始4失败/1通过准确复现阻断保存、无备用出口和切换丢填写；修复后最终7个新增浏览器用例及22个原观察用例，**29 passed，0.64s，exit0**。

日志：

- RED：`D:/VideoSi/cache/video-ai/logs/vco06-observer-save-red-6f6be749efbd4a50b540256d5fe64f73.log`
- 最终：`D:/VideoSi/cache/video-ai/logs/vco06-observer-save-final-e0d4df1007c54356abe611482067744b.log`

检查命令经bootstrap及Invoke-VideoAiNative：

```text
-B -m pytest tests/unit/test_vco06_observer_saving.py tests/unit/test_natural_acquisition_observation.py -q --tb=short --basetemp D:/VideoSi/cache/video-ai/temp/vco06-observer-save-final-e0d4df1007c54356abe611482067744b -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

合成浏览器事件只证明软件行为，不代表实际完整观看或视觉标签。没有改冻结观察校验器、采集模块/CLI、collection或媒体，没有新模型/GPU请求、全库回归、发布或Git写入。

修复页复用旧页完全相同的嵌入DATA：12个development案例及原collection/原图/视频身份，无holdout曝光。旧页保持原字节；采集冻结的4份Python/CLI软件SHA全部未变。

旧页SHA：`739f50eb331ca5a606b34c47b1e953d4218092cfd2f8f9fb39d4441e3f2128f5`。

新页SHA：`fac11270be719c80dde353de48fad75689c11a3b120dee81a01ebb38a08319b4`。

同采集根 `observer-save-fix.receipt.json` 记录实际新旧页身份与不变核对。原观察入口快照未覆盖，VCO-06任务状态及资格门槛未改变。
