# VCO-06 实际观看记录接收与资格准备结果

2026-10-29。用户报告“我都看完了，你继续吧”，并澄清10段中的“原本希望发生光照变化=是”实际意思为“只是在视频里看到了变化”。已保存两条原话作为补充证据，未代选修正轴、未将未知标签改为通过，也未要求再次观看。

## 当前结果

实际导出文件保存在 `D:/code/py/video-ai/docs/task-handoffs/g0*.json`，共13份、覆盖12段development；折纸s03有两份不同保存时间的提交，均保留。通过只读查询项目对应的下载目标找到原位置；默认Downloads目录没有这些文件，并不表示用户没有保存。

原观察校验器接收10份正式v1记录，覆盖9段；它们的原始标签均为 `unverified`，入库后仍为未确认。3份陶瓷球草稿原样归档，不强行送进正式标签。12段本地草稿也已按collection/视频/原图身份定向恢复，保留原始值字节及来源序列号、数据块校验；只保存本项目当前12段的条目，不保存其他网页数据，不改浏览器配置或存储。

实际浏览器记录证实12/12段均具有完整 `[0,3.0625]` played范围、原生ended、约3.06秒实际经过时间、原速可见且无中断；实际RVFC为47帧或48帧，不补写缺帧。结合用户本轮“都看完”报告，观看动作已有真实材料支持，不能继续把“不肯看/尚未看”当作阻塞原因。浏览器时间范围、人类完整观看报告、自然颜色判断和修正资格仍分别留存。

用户关于光照的澄清仅作用于10个原为true的字段：新增解释视图记录其意图为无预期变光；所有原JSON和复选框保留不动。原为false的陶瓷s02不变，原为null的陶瓷s03仍保留未知。此澄清不替作者确认颜色中性、单轴/方向、运动安全或候选改善。

## 逐段处理

下表“处理依据”是带来源的审查解释，不替换用户原始自然标签。

| 开发段 | 用户实际文字 | 原标签 | 处理依据 |
|---|---|---|---|
| 陶瓷s01 | 没有问题 | neutral草稿 | 目标/结构/动作已确认；光照误解已澄清，当前中性报告一致，可保留原片，不算偏色正例 |
| 陶瓷s02 | 视频棕色偏淡，蓝色偏深 | mild_color_bias草稿 | 修正轴/方向未确定，只有1个场景组，尚不满足恒定单轴校色Precheck及四组资格覆盖 |
| 陶瓷s03 | 球的形状有问题，是扁的 | neutral草稿 | 结构选为false、照明未知；显式形状缺陷永久保留，不能按neutral忽略 |
| 几何块s01 | 没看出问题 | unverified | 保留未确认，不自动升级为中性 |
| 几何块s02 | 倒下后颜色不正确，变浅了 | unverified | 结构选为false，并描述动作中的颜色变化；不能确认为全片恒定偏色 |
| 几何块s03 | 没看出存在问题 | unverified | 保留未确认 |
| 折纸s01 | 移动过程中最右边图形发生了不合理形变，多了一个折痕 | unverified | 明确的非颜色缺陷，恒定校色不能修复 |
| 折纸s02 | 无法确认有移动 | unverified | 不替作者确定运动质量或颜色中性 |
| 折纸s03 | 结尾多了一个先前不存在的图形 | unverified | 新增物体的原始负面描述保留，不被其他选项覆盖 |
| 木材s01 | 没看出有问题 | unverified | 保留未确认 |
| 木材s02 | 左侧棕色图形颜色变化存在问题 | unverified | 尚不证明恒定、全局、单轴颜色问题 |
| 木材s03 | 没看出有问题 | unverified | 保留未确认 |

**当前确认合格的已知轴自然偏色正例为0，qualified_directions=[]，五阈值仍为null。** 原始标签为2个neutral草稿、1个mild草稿、9段unverified；不能把这些直接写成已通过校准。即使后来澄清陶瓷s02的方向，单一场景组仍不满足每方向跨4组的既定研究覆盖要求。

未封存阈值、未读取holdout自然指标、未生成自然profile或校色候选。研究阶段的freeze/measure/seal/evaluate/finalize及新自然策略消费者仍待实现，旧audit命令不能冒充完整校准。观看和接收记录的进展不能代替资格或实际改善验收，VCO-06继续BLOCKED。

## 证据入口与本轮验证

本轮根：`D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261029-observation-intake-a20e37ad9c984900882aa743738a4fc4/`。

- `observation-intake-audit.json`：12段及13份导出、10份正式未确认入库收据、3草稿及浏览器实际时间记录的完整索引。
- `resolved-observation-readiness.json`：追加光照澄清后的解释视图及四个方向均无已确认正例的准备结论；24012 bytes，SHA256 `a5eedd928a2e9e97354d3823fdd6c6d48dfc65a0f2b2c843f47ee2cfd9479984`。
- `author-lighting-clarification.json`、`user-current-portal-viewing-report.json`：本轮用户原话及其适用范围，不假造人类审阅时间。
- `raw-exports/`、`raw-caches/`、`intake-receipts/`：原始导出字节、仅本项目的实际缓存及实际正式导入收据。
- `preservation.json`：13份用户原文件、4份冻结Python/CLI及collection/receipt/新旧页共21项bytes、SHA、mtime全部不变。
- `docs-before-update/`：本次更新前默认交接、任务板及采集交付记录原字节。

本轮没有修改产品源码或测试，不重跑已通过的软件检查。上述记录由实际原校验器与来源验证器执行产生，并核验12个开发case的真实生成事务、原图/原片、生成时间及媒体身份；不是合成测试观察。

所有Python经bootstrap、Initialize-VideoAiEnvironment、Invoke-VideoAiNative串行执行。日志根 `D:/VideoSi/cache/video-ai/logs/`：

- 定向恢复：`vco06-actual-observation-recovery-bd7f2d0e3ea54065ae27230fc58dd839.log`，exit0。
- 原缓存字节保全：`vco06-observation-cache-preservation-b0c106246a9542ee9c1a5b82c921382e.log`，exit0。
- 实际入库与来源复核：`vco06-real-observation-intake-final-d72ab36bb37f4fb6a89eaaa24d71abff.log`，exit0。
- 用户澄清与21项原件复核：`vco06-author-lighting-clarification-3b69a46781e445c08370075bfef3b5f2.log`，exit0。

初次一次性intake辅助脚本误用仅限runtime路径的read_json读取源码目录导出，在首个导出读取处退出1，尚未入库；原日志 `vco06-real-observation-intake-60912a5e50ea4b14ba28f450e06ec7d0.log` 和未完成输出根保留。辅助脚本改为strict_json读取显式原文件后，在新根完成实际入库；未放宽产品路径或schema校验。

无新增生成/模型请求、重试补单、依赖安装、全库回归、Git写入或后继任务准备。固定24次采集预算已用完，不自动为取得正例再换seed或补单。后续入口应从本结果读已知标签/缺陷和覆盖不足，不能要求用户重复完成本轮观看。
