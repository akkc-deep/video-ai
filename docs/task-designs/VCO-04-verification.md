# VCO-04 实施与验证

状态：COMPLETED（2026-10-27，软件实施与定向验收）。以任务板和设计 `docs/task-designs/VCO-04-design.md` 为准。411项不同的定向用例已逐项取得通过结果；生产播放/视觉准确率/正式Benchmark不在这些软件通过结论内。

## 实施内容

显式 opt-in `advisory_v1` 策略及 FileIdentity 冻结；ordinary 报告只读闭包与安装身份核验；不可变诊断 epoch、安装归档、本地 job/attempt/assessment、逐风险 Review；完整播放与三段以上同作者前缀记录；生成、超分、合成、完成前缀及发布的当前资格守卫。旧 schema2 视频观察、请求和媒体聚合继续按原契约保存。

显式本地入口：`scripts/scene_continuity_audit.py analyze/reassess/status`；`make-video --run-dir ABS --continuity-review ABS` 仅收取证据，不推进生成。没有自动测量、自动签署观察、模型服务启动或发布。

操作顺序、请求字段和恢复语义见 [VCO-04-operations.md](VCO-04-operations.md)。

## 已执行检查

全部 Python 经 bootstrap、Initialize-VideoAiEnvironment、Invoke-VideoAiNative；缓存与原始日志在 `D:/VideoSi/cache/video-ai`。测试串行执行。

| 检查 | 实际结果 | 原始日志 basename |
|---|---|---|
| 初始策略/记录 RED | 12 failed、17 passed，缺配置和模块 | vco04-policy-records-red-e97942dfa6874bb49b4163a87ea3c865.log |
| 策略冻结 GREEN | 27 passed，exit0 | vco04-policy-green-753fccc9c2154755865e5371c10993b6.log |
| 本地事务 RED | 5 failed，缺事务入口 | vco04-transactions-red-c484369240464a96a9e54389ca283c0d.log |
| 普通报告最终 GREEN（含算法升级历史读取） | 8 passed，exit0 | vco04-report-upgrade-final-ae08b73a221343948eb0477bbb47b04c.log |
| 首轮入口/CLI/旧运行恢复 GREEN | 26 passed，exit0 | vco04-guards-green2-bf875df7057544c894fdcd9aa85c80bc.log |
| epoch/状态分支 RED | 7 passed、1 failed，确认缺陷被错误分为等待 | vco04-root-records-pending-red-ad23fe642f82487982e794d1c27b4318.log |
| 来源/前缀 RED | 4 failed、1 passed，父前缀、原始字节、历史assessment、继承metadata | vco04-provenance-red-fe5902057ea646e69c08253ed61d9dc6.log |
| 来源/前缀 GREEN | 21 passed，exit0 | vco04-provenance-green-9a02fe21356a4152ae1fb8b74bcbcbf3.log |
| 审查元数据预算修复 GREEN | 10 passed，exit0；共享预算/截止时间、profile 不能退款 | vco04-report-budget-final-45e3f400b026482ea2809ca3e93256ec.log |
| 最终基础核心组 | 71 passed，exit0，83.68s；policy/records/report/recovery 四文件 | vco04-final-core-9ba6594917a34e12a672a023b96b00f9.log |
| 真实小样本五项 | 5 passed，exit0，287.96s；完整三前缀准入、静态查询、ROI/身份拒绝、同作者回应、逐边界恢复 | vco04-tiny-flow-final-0a049daf822048f1b67c88080a6c6122.log |
| 完整旧兼容组13文件 | 304 passed、25 failed，7611.88s；失败均为精简旧发布上下文被新守卫要求script_path | vco04-final-compat-ad53e3f03199407399205a1e50242175.log |
| 旧发布兼容及两个边界修复 | 27 passed，exit0，6.83s；包含上述全部25失败项，以及可选依赖缺失、完整归档写完但commit未写时的恢复 | vco04-final-edge-green-d12b7f2ef1594c6a97ebb83e821de941.log |
| 追加真实恢复组合 RED | 2 passed、1 failed，173.84s；既有assessment未拒绝第二成功attempt | vco04-extra-flow-red-b3542d6a00bd4becaefa516aca7a5b9d.log |
| 记录/恢复收尾 GREEN | 36 passed，exit0，34.08s；含14 records及22恢复拒绝用例 | vco04-final-records-green2-aa2b7f49833b42e6b852ac5f47f98903.log |
| 公开报告接口 RED | 1 failed，14.65s；缺设计约定的expected_engine/位置manifest调用 | vco04-public-report-red-e09751632dc943529d07cd9301ec5639.log |
| 最终契约核心组 GREEN | 74 passed，exit0，88.25s；policy27、records14、report11、recovery22 | vco04-final-core-contract-e799af24739d4128b87894f25697de73.log |
| 最终契约真实链路 GREEN | 8 passed，exit0，453.81s；含全部原五项与跨代次缺陷、部分恢复/多成功拒绝、三次attempt上限 | vco04-eight-flow-contract-final-4e78d3311bed4a0597640fdfb491c058.log |

逐组件补充：`VCO-04-policy-implementation.md`、`VCO-04-report-implementation.md`、`VCO-04-guards-implementation.md`。持续执行账本：`VCO-04-plan.md`。

## 真实 CPU 小样本与限制

使用真实 FFmpeg 64×36、16fps、明确 SDR 的三段媒体和 VCO-02 分析帧，独立固定首帧参考与 ordinary VCO-03。原三段各4帧样例的 metrics 16,185,691 bytes，最终 report 超16MiB被拒绝，保留失败日志 `vco04-tiny-flow-green-6259176ec10b49bf8b631d47d605e828.log`。后续采用每段2帧（总6帧），满足设计每段最多8帧/总最多24帧，保持原资源上限。

技术场景上下文明确为 fixture_only（现有真实 Wan 生产 profile 尺寸固定），媒体/色彩证明/分析与旁路记录实际执行；播放声明为明确合成 fixture，测试软件状态与拒绝分支，不表示环境具备实际 agent_video 播放能力或视频外观已经通过。原AI研究profile未改写为普通生产profile，正式双人Benchmark限制保留。

## 实施中的工程澄清

NumPy 的实际 RECORD 包含合法0字节 marker/source文件。为完整归档和保留原 fingerprint，允许已验证 RECORD 成员及其逐字节归档副本为0；其他报告/作者JSON仍必须非空。此例外仅限准确安装库存，不根据后缀或任意空文件放宽。

保留原只读技术媒体核验。原 `scene_context/collect_progress` 会进行ffprobe、原生完整解码和尾帧像素核验；本任务没有添加绕过它们的公开参数。因此status禁止新的诊断帧提取、测分和写入，但仍可能发生CPU技术解码，完整历史链查询可能很慢。相关设计措辞与操作说明已明确这一点；真实小样本的只读测试拒绝 `analyze_continuity`/`decode_analysis_frame` 调用并核对查询前后字节不变，没有声称原技术校验无解码。

## 逐项验收

1. **策略与旧run兼容：通过。** 严格两字段配置、唯一条件身份角色和原字节冻结由27项policy验证；旧兼容329项逐项通过（首次304通过；另外25个精简旧发布上下文在早退修复后全部重跑通过）。这些失败没有隐瞒或算作首次全绿，也没有为无策略run添加默认键/目录检查。
2. **绑定与报告闭包：通过。** 真实6帧三clip和独立参考记录、帧/PTS/ROI/前缀约束、普通报告/raw/metrics/pairs/证据/构建/包来源及损坏拒绝由11项report和真实链路验证。公开report API兼容设计的两个位置身份参数并精确核验expected_engine；runtime显式绑定epoch Engine。无profile保持unverified。
3. **动态观察与当前资格：通过软件规则验收。** 原schema2观察保留，当前逐风险回应/完整同作者前缀分别验证。无诊断、漏回应、不同作者、不完整参考、确认缺陷均不ready；原ready之后有效确认缺陷仍阻断，原receipt不覆盖。没有生成实际播放或视频质量已通过的结论。
4. **版本与恢复：通过。** 初始epoch/commit、job/attempt/report/terminal/assessment/review各边界中断、完整报告一次测量、部分audit保留并新建有限attempt、两份成功冲突拒绝、三次上限第四次不测量，以及已完成归档但commit未写的幂等恢复均有实际用例。实际相同媒体重评后确认缺陷仍阻断，原请求/媒体和原观察字节保持。归档只读取证，不执行旧代码。
5. **定向检查与外部边界：通过。** 最终核心74＋真实链路8＋旧兼容329＝411个不同用例逐项有通过结果，无缺依赖skip。模型/外部HTTP/service/SMTP在新真实小样本中设为调用即失败，原明确local fake-server兼容场景保留；没有真实模型、付费试验或生产发布。公开发布底层入口直接检查当前资格。
6. **证据与范围：通过。** 实际RED/GREEN和独立审查均保留；五项Important已修复并逐项验证。AI研究profile、正式双人Benchmark及实际播放能力限制未被改写。本轮只完成VCO-04，后续任务没有启动。

收尾核对：最终封存的407份Python/PowerShell源码/测试/脚本身份与运行后集合全部相同，无增删或bytes/SHA漂移。快照与核验分别为 `D:/VideoSi/cache/video-ai/temp/vco04-final-verified-source.json`、`D:/VideoSi/cache/video-ai/temp/vco04-final-source-verification.json`。`git diff --check`退出0；换行提示为仓库既有autocrlf提示。`.git`只读，改动保留工作区，未提交、推送或清理其他任务产物。

本任务软件验收无剩余项。全库回归仍按既有用户约定留在VCO-08/项目最终收尾；真实生产run的准确输入、完整播放观察与实际外观结果须各自按证据建立，不从这些fixture自动继承。
