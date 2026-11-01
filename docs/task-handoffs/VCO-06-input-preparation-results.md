# VCO-06 真实输入准备执行结果

2026-10-28，执行者 Codex。按 [输入准备要求](../task-designs/VCO-06-input-preparation-requirements.md) 执行了现有素材查找、真实参考图门槛、来源闭包、当前诊断、封存 profile 和原件保存核验。**交付状态为 `blocked`，没有满足 `ready_for_propose` 的素材组。** 本次完成的是要求文档明确允许的“找不到合格素材，交付缺项和证据”分支；没有完成 VCO-06 的真实校色验收。

## 交付入口

- [交付说明](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-004831-15b456a44302/README.md)
- [权威文件索引](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-004831-15b456a44302/delivery.json)
- [逐项资格与阻塞原因](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-004831-15b456a44302/qualification.json)
- [交付包文件身份清单](D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-004831-15b456a44302/package-files.json)

交付目录包含 README、delivery、qualification、准备前后原件清单、evidence、logs 和一次性 tools。生产权威文件保留在原路径，索引用真实 path/bytes/SHA256 引用；VCO-02 记录继续使用自己的五字段身份。

## 实际核验

| 项目 | 本次结果 |
|---|---|
| 现有素材发现 | 扫描既有 runs 根下 2,013 份 clip request；得到 1,324 个选图路径/SHA 组合、8 个不同选图 SHA。470 份缺少 path 或 selected_image 的 request 保留为拒绝记录。扫描发现不代表生产来源已通过。 |
| 带 sRGB 声明的替代图 | 84 组的冻结 script.txt 均明确标记 fixture_only，不能作为真实生成素材。每组判定及身份在 selection-audit.json。 |
| 真实优先样本 | 原 run `20261021-014723-4ebdc1fecab2`、无父片的白鹭 `scene_0003_clip_0001`，另核对 scene_0001/0002 的首段。 |
| 三张真实原选图 | 逐一实际执行 inspect_color_asset、decode_analysis_frame、load_color_analysis_set。三组均为 interpretation=unknown、analysis=unverified、pixels=null；缺少 sRGB/gAMA/cHRM/iCCP 声明。读者闭包有效，没有 unverified_mapping。 |
| 原图身份与静态映射 | 原图身份与实际 request.selected_image 相同；提供字节完全相同的 .png 副本，没有改元数据。独立静态参考 mapping 的 generated/retained/output 索引为 null，真实 proof 已绑定原图副本身份。 |
| 冻结输入与生产来源 | load_frozen_inputs 成功；真实 common→scene_context→collect_progress 核验成功，原 run 中六个已有技术片段被核验，包含目标首段。保留各片段真实等待状态，没有把它们改成新验收通过。 |
| 当前诊断 | scene_continuity_audit status 退出3，policy=null、current_epoch=null、clips=[]、ready=null。旧 run 无冻结策略、当前 assessment 或报告闭包，没有补写 options。 |
| 封存 r2 profile | 现有 verified_profile 校验成功，完整闭包 12,004 项；production_eligible=false。未重拟合或扩大方向/阈值。 |
| 完整播放与 Precheck | 没有取得新的实际完整播放观察；历史 human_video 接受单独引用，不等于本次校色问题/轴/目标意图预检。未填写 Precheck。 |
| 全帧与配对 | 依要求在原图 gate 失败后停止该组后续准备。没有新全帧源像素分析、ROI、pair manifest 或请求；自然配对尚未测量，未宣称原生/轨道/修复资源门槛本次全项通过。 |
| 原件与软件 | 原 run 3,011 个文件的集合、bytes/SHA256/mtime_ns 准备前后及历史保存基线一致；436 个既有源码/测试/脚本、pyproject、任务板和输入要求文件身份未变。合法新增只在交付目录、独立 audit run 和 bootstrap 日志。 |

参考图实际诊断位于独立 run `D:/VideoSi/projects/video-ai/runs/20261028-005107-869f43a10271`，对应交付包 `evidence/reference-gates.json` 中的 `audit_run_dir`；所有 sidecar/analysis/proof 均有精确身份索引。

## 实际命令与验证

各阶段均先加载 `scripts/bootstrap.ps1`，调用 `Initialize-VideoAiEnvironment`，再以 `Invoke-VideoAiNative $VideoAiPython @('-B', 实际脚本绝对路径)` 执行。一次性脚本原字节、完整日志和每个退出码已保留。

- `tools/discover.py`：目录扫描结果已保存，但末尾汇总没有解包 PNG 解析器的 `(metadata, conflicts)` 返回值，退出1；失败脚本和日志保留。
- `tools/summarize_discovery.py`：只规范化已保存扫描数据，退出0；没有重新解释或修改原图。
- `tools/prepare_evidence.py`：三组实际参考 gate、读者复核、冻结输入、profile 闭包及原件前后核对，退出0。
- `tools/check_context.py`：串行执行真实 status 和生产来源核验，分别退出3、0；wrapper 退出0。每条子命令的完整 args、stdout、stderr、工具身份和300秒期限在包内 logs 的 receipt 中。
- `tools/finalize.py`：生成 blocked 交付索引并核对历史保存基线，退出0。
- `tools/verify_delivery.py`：只读验证，退出0，结果为 `verified_blocked_delivery`；核对37个包内文件、3,011个原件、436个既有软件/约定文件及三组参考 gate，共哈希3,772个唯一文件，`ready_for_propose=false`。12,004项 profile 闭包的严格核验由前面的实际 API 执行，末次包核对没有再次运行同一完整 profile 审计。

最终复核日志：[vco06-input-preparation-verify-170caa0f93c84f4989e2cb409cf0750b.log](D:/VideoSi/cache/video-ai/logs/vco06-input-preparation-verify-170caa0f93c84f4989e2cb409cf0750b.log)。实际复核命令可直接执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-input-preparation-verify'
Invoke-VideoAiNative $VideoAiPython @('-B','D:/VideoSi/projects/video-ai/vco06-input-preparation/20261028-004831-15b456a44302/tools/verify_delivery.py')
$verifyExit = $VideoAiExitCode
```

## 未满足项与下一步

旧视频已绑定的原选图不能事后加标签、转换或替换。此次没有找到另一组可消费的真实来源；若继续取得新素材，需要在新 run 创建前冻结 advisory_v1、实际使用色彩解释有依据且符合当前 PNG 分支的选图，并取得真实完整播放者提供的轻微偏色/已知轴/目标意图预检，再按原要求建立完整诊断和独立配对。

当前任务未建立新增真实推理的独立授权，因此没有追加模型/GPU请求。当前也没有合法 propose 请求；下一条可执行命令是上面的只读交付复核。未安装依赖、运行全库回归、改产品源码、重校准、生成候选、发布或写入 .git。任务板及原 VCO-06 阻塞交接保持原状，不自动推进 VCO-07。
