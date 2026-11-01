# VCO-06 资格研究续作结果

2026-10-28。用户要求读取正式交付、复用已有输入并继续资格校准、真实候选与改善验收。本轮复用了原包，没有重复导入、重出视频或改写原结果。

**本轮已完成全49帧像素特征重放、资格统计实现和资格准备审计；正式自然阈值校准仍缺输入/标签，未生成自然profile、真实修复候选或改善接受记录。VCO-06保持BLOCKED。**

## 唯一续作入口

- 原交付：[正式研究输入交付](VCO-06-research-input-delivery.md)。原输入包及其 delivery.json 保持原字节。
- 本轮根：`D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261028-resume-245dea6b135b4cc19a7b8cb9077a206f/`。
- 最终审计：该目录 `qualification-audit.final.json`，452655 bytes，SHA256 `cc02371430e35e6313b06acd8b874becdb37ebee232c22eb3cfb0b57f30adca6`。
- 资格定义：[独立自然校色资格协议](../task-designs/VCO-06-natural-qualification-protocol.md)。它明确完整研究输入尚未冻结，不是已经封存的资格实验。
- 实施账本：[continuation plan](../superpowers/plans/2026-10-28-vco06-qualification-continuation.md)。

## 实际完成

正式context再次核验真实Wan事务、原图/原片、current commit/epoch/assessment、完整全帧普通报告与全部分片。随后从原图/原生视频的真实RGB及既定配对坐标重新执行9×9特征测量；结果按原producer的紧凑序列化逐字节匹配保存的baseline，不能只改baseline并更新交付SHA蒙混。

全部49帧重放成立，每帧角色和配对点完整保留；原baseline SHA仍为 `aaf6803584388df0ce4633c0aecd5bc86f9200fe893c0dbfb36197dc66fbf2b5`。正式输入状态仍是research_input_ready，资格状态仍是awaiting_qualification，ready_for_propose=false。

新增的纯统计实现准确计算逐帧/角色b与正交p90残差、等权全片B、固定支持的前后改善/逐帧退化/时间增加；保留负的regression/increase，不删帧、不换坐标，也不根据采样点数量改变帧/角色权重。没有估计自然修复参数a或选择最佳算子。

下面是原片开发诊断，**不是阈值、自然标签、修复参数或改善结论**。三种operation仅为明确分别记账的投影，wb_g的同一统计对应两个可能修复符号：

| operation | 完整帧 | 每帧角色 | B=平均绝对bias | 最大绝对bias | 最大逐行正交p90 |
|---|---:|---:|---:|---:|---:|
| exposure | 49 | 1 | 0.011201061029305348 | 0.018630244830896057 | 0.06177666657599916 |
| wb_r | 49 | 1 | 0.007310906775752355 | 0.012538897333647322 | 0.08146649889048241 |
| wb_g | 49 | 1 | 0.009049122250294056 | 0.014073102668577068 | 0.0887230305857005 |

没有资格阈值时，不能把这些数值叫作“正常”“需要修”“已改善”或noop。用户“没有看到有明显问题，我分辨不出来”仍为原始描述性反馈，未升级为完整观看或已知色偏方向。

## 为什么没有进入真实候选

审计只拥有1个已见开发来源、0个有效实际观察确认的自然偏色正例、0个新holdout案例。完整自然研究inputs、控制recipe及标签清单没有冻结；五个阈值仍全部null，qualified_directions=[]，natural_profile=null。

已批准设计要求development和新的holdout各至少12个完整视频、每split至少4个不重叠scene_group；每个希望取得资格的方向还须每split有跨4组的4个真实自然案例。49帧是一段视频，不能当49个独立案例；同视频复制、人工注入、旧24来源/旧holdout不能变成新的自然盲测。

目前也没有有效的实际完整播放、已知operation/轴和颜色目标Precheck。可用工具没有提供实际完整视频播放能力；静帧、逐帧CPU测量或用户继续执行授权不能代替这些记录。因此没有合法依据拟合/渲染自然候选，也没有候选可供改善验收。本轮保留原片；没有为制造视觉差异而强行修色或追加无法完成视觉标签的推理。

## 软件验证与修复

当前源码最终11文件 **132 passed，123.94s，exit0，无skip**，其中44个新用例加88个相关既有用例；这些都是软件检查，不计为自然研究案例。日志根为 `D:/VideoSi/cache/video-ai/logs/`：

- 最终：`vco06-qualification-final-suite-3655b2fcfb6b463b82a47c5752f61e33.log`。
- 之前131项通过：`vco06-qualification-current-suite-f516a522b33f4a109d27b5a098d5d11c.log`；之后补充输入包写入隔离回归并全部重跑，未拿旧结果冒充最终132项。
- 数值RED24→GREEN28：`vco06-natural-statistics-red-57aa0594528c415b95b8aeea36004173.log`、`vco06-natural-statistics-green-136498de7670499297e5dc31a93f252c.log`。
- 审计RED17及GREEN45：`vco06-qualification-audit-red-tests-8c0fdcd71ce84147bba5667937483551.log`、`vco06-qualification-audit-green-lf-9e503801d51e40b7a048044003a00895.log`。更早fixture setup errors及3失败/42通过保留；根因分别是测试在fixture导入缺失模块，以及Windows文本CRLF不同于真实producer的二进制LF，修正测试，没有放宽字节核验。
- 报告窗口RED1→GREEN47：`vco06-qualification-window-red-0e23d24ddd5e4a8fae2edd34924af59c.log`、`vco06-qualification-window-green-542fd0f3d4e5484186f19ec83bf25eab.log`。完整root/全部shards现加入本审计最终重哈希窗口，覆盖重放后被修改的情况；JSON去重预算同步计入。
- 输入包隔离RED1：`vco06-qualification-bundle-red-b5d7508f86544447ac4429ab12ebf069.log`；已增加“即使输入包放在独立audit根下，也不能在该包内写输出”的前置检查，最终132项包含GREEN。

独立只读审查：[review](../task-designs/VCO-06-qualification-continuation-review.md)，报告无Critical/Important/Minor发现。上述最后一个包隔离问题由随后自查发现并RED/GREEN修复；不声称该两行后续修复是审查者已经看过的内容。

准确最终pytest参数：

```text
-B -u -m pytest tests/unit/test_natural_repair_statistics.py tests/unit/test_natural_qualification_audit.py tests/unit/test_research_material_records.py tests/unit/test_research_pair_report.py tests/unit/test_natural_color_repair.py tests/unit/test_research_production_boundary.py tests/unit/test_research_material_cli.py tests/integration/test_research_material_flow.py tests/unit/test_scene_continuity_policy.py tests/unit/test_production_inputs.py tests/unit/test_continuity_report.py -q --tb=short --basetemp D:/VideoSi/cache/video-ai/temp/vco06-qualification-final-suite-3655b2fcfb6b463b82a47c5752f61e33 -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

所有Python命令先bootstrap、Initialize-VideoAiEnvironment，再通过Invoke-VideoAiNative执行；命令串行。此次只增加独立统计/审计和CLI，未改生产/旧校色入口；没有重跑旧178项完整生产恢复组，旧364/88等记录保留为历史。全库仍留VCO-08。

## 实际重放命令与保存核对

以下是已执行的最终命令；重复执行时须选择新的独立输出路径，不能覆盖此证据：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-qualification-final-real-replay'
Invoke-VideoAiNative $VideoAiPython @('-B',
 'scripts/experiments/vco06_natural_qualification.py','audit',
 '--delivery','D:/VideoSi/projects/video-ai/vco06-usable-input/20261028-141129-0710d61477d0/delivery.json',
 '--output','D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261028-resume-245dea6b135b4cc19a7b8cb9077a206f/qualification-audit.final.json')
```

实际退出3，返回awaiting_qualification、native_frames=49、ready_for_propose=false。日志 `vco06-qualification-final-real-replay-b877874f2acb4572bff4b694c775148f.log`。首次真实重放的pre-fix结果保留为同目录qualification-audit.json，不作为最终代码结果。

同目录保存：

- `protected-before.json`、`preservation-final.json`：输入run、普通报告run及原输入包的 **568/568 文件集合、bytes、SHA256、mtime ticks均未变**。
- `software-final.json`：最终命令前冻结451个Python源码/测试/脚本；执行后 **451/451 字节身份与文件集合一致**。
- 旧r2 profile SHA256仍为 `d0423aa2012f80fe590798242014a46c1af210fbfcfb3a7163f776bbf46b158f`；未覆盖旧profile、source、baseline、观察或旧失败。
- 初次PowerShell核对将451行JSON数组误当单个数组对象，产生假源码漂移；原报告保存在 `preservation-initial-checker-error.json`。修正数组展开后核对通过，未更新任何基线掩盖变化。
- `archives/`：本轮文档更新前的默认handoff、任务板及正式交付记录原字节快照，复制后SHA核对一致。

## 剩余工作与解除条件

1. 补齐并冻结可独立复核的完整来源/分组/split/控制recipe/实际观察清单；开发数据与全新holdout满足批准设计，已见纸质段只按其真实用途计账。
2. 具备实际完整播放能力的观察来源，提供真实自然标签和已知轴/目标意图；不要求用户勉强确认细微色偏，不用静帧代替。
3. 按development→严格间隔中点→seal→一次独立holdout完成资格。若没有方向通过，保留unqualified；不能为了完成任务手写新profile。
4. 有合格新profile和目标真实Precheck后才接入/执行新策略候选，再完成技术保护和真实完整原片/候选改善观察。

本轮没有新增模型/GPU请求、生产发布或Git写入。任务板仍BLOCKED，不产生状态迁移或VCO-07准备。

## 再次续作的前提复核（2026-10-28）

用户再次要求完成本文件剩余内容后，已读取任务板、主设计、自然输入修订设计和独立资格协议，并检查本地交付及研究目录。当前没有找到 `natural-repair-profile.json`；检索到的其他封存/profile文件属于旧实验或fixture，不能作为本研究的新自然资格。

实际执行 `scene_research_material.py status --run-dir D:/VideoSi/projects/video-ai/runs/20261028-145342-f5100beeb167`，退出0；当前仍为 `research_input_ready`、49帧、`full_video_observation=unverified`、`ready_for_propose=false`。日志：`D:/VideoSi/cache/video-ai/logs/vco06-continuation-prerequisite-status-424ba8bf616b406088ff28832b5494c1.log`。

再次核对原最终审计SHA及交付、baseline、原片、原图、commit、epoch、assessment、frame_map共8项的bytes/SHA，全部与已有绑定一致。复核记录：`D:/VideoSi/projects/video-ai/vco06-natural-qualification/prerequisite-check-f980bf302fa845838a7cd73b7b4c3cfd/prerequisite-check.json`，SHA256 `6dfd5b4d9c127de3dc5aa25b2152b1df54954edb7d17c57d0ade343f51a00693`。本次为当前状态和文件身份核对，没有重新执行像素重放或pytest；上文132项仍是此前实测结果。

已询问新增独立视频及实际完整播放标签的本地目录或服务位置；当前工具没有完整视频播放接口。在取得这些实证输入前，剩余第1–4项仍未完成，不拟造标签、阈值、profile或候选改善结论。未修改产品代码、输入包、旧实验或任务板状态；VCO-06继续BLOCKED。
