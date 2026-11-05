# Reference generation speed

后续两轮代码修复及离线对比已完成，详见 [修复实施记录](reference-generation-speed-fix.md)：相同第 19 场景只读恢复平均从 19.594 秒降至 5.427 秒，再降至 4.203 秒（累计减少 78.55%）。生成未恢复，未发出云端请求；下方“尚未解决”状态及实测数据是修复前诊断记录，保留用于对照。真实新图生成速度尚未验证。

## 待后续任务修复：场景图生成被重复全量校验拖慢

记录日期：2026-11-04。用户要求：“把这个问题记录一下，我会让下一个任务修复”。

**状态：诊断完成，性能问题尚未解决；本次只记录，不开始后续修复。视频生成仍按用户要求暂停。** 下方原实施记录属于历史，局部优化和测试通过不代表这个问题已经解决。

### 问题与影响

场景图生成的“确认仍持有任务”“保存小记录”“发送/查询 HTTP 请求”等高频动作，都可能触发整条历史依赖的文件、路径、身份和目录核对。冻结配置也曾在多个读取入口反复完整加载。成本随历史依赖数量和回调次数放大；已有图的恢复也执行大量本地验证，长时间没有新图。

本次完整素材检查涉及 2,749 个文件（其中 1,733 个 JSON、736 个 WAV，其余为历史响应、脚本、字体和配置等），捕获文件大小合计 300,618,199 字节。该大小是依赖集合总量，**不代表每次检查都会重新读取全部文件内容**；已有哈希缓存后，路径/文件身份/目录遍历仍反复执行。

### 已确认的实测证据

| 项目 | 实测结果与边界 |
| --- | --- |
| 缓存预热后的完整素材检查 | 0.953507、0.936174、0.937774 秒/次 |
| 缓存预热后的完整配置加载 | 1.643695、1.628767、1.621557 秒/次 |
| 首次只读配置加载 / 修订来源校验 | 6.836430 秒 / 17.941435 秒，包含首次读取开销 |
| 仅校验已有参考候选图 | 5.906163 秒，不生成新图 |
| 旧场景恢复 | 场景 0002–0019 每个约 19 秒；最新恢复日志从 22:48:25 到 22:54:57，期间复用旧结果 |
| 离线 HTTP 回调放大 | 一个返回 2 字节的模拟 POST 响应，触发 4 次 ownership 回调、8 次完整修订检查调用；只是计数，未执行这 8 次全量检查。实际网络请求为 0，也未覆盖真实 DNS/TLS/send 钩子的额外调用 |
| 第 20 场景的两个请求结果落盘 | 22:55:16 进入生成，到 22:57:50.605 两个请求结果均写完，约 155 秒；场景收尾尚未完成，因此不能当作完整场景耗时 |
| 提交接口服务端报告耗时 | 两个请求分别为 832.398963ms、1.351139861s；这不是模型推理耗时，不能据此断言云端整次生成只要一秒 |

### 已定位的调用链

- `runtime/jimeng_candidates.py::_Records.owned()` 与 `runtime/production_image_selection.py::_Records.owned()`：检查运行锁之外，还调用 `RevisionGuard.verify_captured_bytes()`。
- `_Records.save()` / `.image()`：新记录或图片写入前后均调用 `.owned()`；一个很小的记录也可能付出约两轮全量检查的成本。
- `runtime/jimeng_reference_candidates.py::_submission_guard()`：每次网络回调调用两次 `store.owned()`，还检查当前请求相关快照。
- `adapters/external_https.py`：请求开始、DNS/TLS 完成、发送、响应读取循环和返回前都有 guard；把完整历史素材校验放进这个回调会放大成本。暂停后的离线计数已重现放大现象。
- `runtime/scene_revision_records.py::RevisionGuard.verify_captured_bytes()`：遍历捕获文件，执行 `verify_artifact()`、文件身份核对、目录清单和缺失路径检查；`safe_path()` 还反复检查祖先路径。
- `runtime/image_selection_records.py::_run()` 与 `runtime/reference_settings.py::_run()`：通过 `load_frozen_inputs()` 核对冻结输入；局部读取事务外仍会完整加载。
- `runtime/production_reference_images.py` 的场景循环与 `runtime/jimeng_reference_candidates.py` 的请求循环都是串行；每个场景两张候选图的等待也串行。
- 每个尚需提交的新场景，还通过 `_storage_object(..., verify_remote=True)` 对同一基准参考图重复做 TOS HEAD/GET 核对；额外网络耗时尚未单独精确测量，不得随意归因或给出节省秒数。

### 已有局部改动，避免下一任务重做或误判

历史进程 PID34612 的 10 秒采样（498 个样本）显示约 69.3% inclusive 时间处在 `_WholeInputWindow._immutable()` 目录归属扫描。**这是旧版本采样，不代表当前仍有同样占比。** 当前 `verification.py::get()` 已利用同锁下的准入/驱逐不变量取消命中时的重复扫描，仍保留 native handle / 路径身份检查。

已有 `whole_input_protection(immutable_roots=...)`、HTTPS/TOS worker 的 `copy_context()`、`revision_read_transaction()` 和 `revision_read_matches()`；参考图的局部纯读取可合并重复检查，两个配置入口共享同一读取事务的加载结果。它们只缓解了一部分问题，网络/落盘热路径仍会完整检查。

既有验证结果供下一任务参考，不代表已经满足性能目标：核心保护/传输回归 113 passed；最新修订/参考图单元测试 51 passed；最新提交/来源变更/原任务恢复集成测试 4 passed。较早的 111 passed 回归开始于后续配置复用改动之前，不得称其覆盖了最终全部改动。**本次用户要求记录问题期间没有重新运行测试或启动修复。**

### 后续修复方向与验证依据

先针对已定位的全量校验热路径设计修复：区分轻量运行锁检查、当前请求依赖核对、整批来源一致性检查；复用已经验证且持续受保护的输入/配置，避免每次回调或写小文件都扫描整个项目。全量检查的准确边界由后续任务确定，本文不是已经批准的完整实施设计。

后续验证应证明：

- 小记录写入和 HTTP 读写循环不再反复遍历整批历史依赖。
- 未变化的冻结配置可复用；相关输入真实变化时仍能检测，不能仅凭 mtime 复用哈希，也不能直接删除所有来源检查。
- 已完成候选图和已接受的云端 task ID 可复用，`submit_unknown` 不得自动再次付费提交。
- 保留剧本、配音、分镜、基准图、模型、分辨率及每场景两张候选图的现有语义，不能靠减少工作量或降低画质宣称提速。
- 分别报告恢复、本地检查、网络/云端等待、下载与落盘耗时；实际结果推进才是性能证据，不能只以单元测试通过宣称已恢复出图。

独立场景的并发属于进一步优化，先解决重复全量校验；本文没有确定并发数或新增性能阈值。用户授权下一任务修复前，不在本任务继续实施。

### 下一任务的入口及暂停状态

先读取本文、下面的证据文件和相关调用链，再开展针对性的离线诊断/修复。保持生成暂停；不要因为读取此记录而自动开始或恢复视频制作。

- 当前 run：`D:/VideoSi/projects/video-ai/runs/20261104-053708-1a5f92e2ac83`。
- 暂停记录：`D:/VideoSi/cache/video-ai/video-task-paused.json`。生成进程以 `NtSuspendProcess` 挂起，不是已退出；PID33528，创建时间 `134382772141510029`。`.make-video.lock` 保留。任何后续进程操作都必须重新验证锁的 owner、创建时间和 token，不得只凭 PID 操作，不得直接删锁再启动第二个 producer。
- 暂停时 19 个场景有 `candidates.json`；第 20 场景两张原图及两次 `result.json` 已落盘，但场景汇总尚未写完。暂停记录无缺少 result 的付费 intent。应保留并恢复这些结果，不应重新生成付费请求。
- 诊断时确认该 producer 全部 5 个线程为 `Wait / Suspended`；诊断未恢复进程，未发出真实网络或付费生成请求。
- 保留仓库其他既有未提交改动，特别是 VCO 相关内容；不要整仓回滚来处理此问题。

证据与复现入口（均为本机路径）：

1. `D:/VideoSi/cache/video-ai/logs/scene-image-speed-diagnosis.json`：最新只读实测、文件数量、逐请求时间线和离线 HTTP 回调计数。
2. `D:/VideoSi/cache/video-ai/logs/reference-resume-acd31bf4e1ac4177bf2c2673f53c0135.log`：逐场景恢复与第 20 场景开始时间。
3. `D:/VideoSi/cache/video-ai/logs/reference-stall-34612.speedscope.json`：旧版本 CPU 热点采样，仅用于说明历史热点。
4. `D:/VideoSi/cache/video-ai/diagnose_scene_image_speed.py`：只读本地测量脚本，主动禁止 socket 连接，不调用生产 CLI。
5. `D:/VideoSi/cache/video-ai/count_scene_https_guards.py`：模拟 HTTP 响应的回调计数脚本，主动禁止真实网络；使用已有 URL 生命周期证据，过期后可能拒绝执行，不得为复现而提交新云端请求。

---

## 以下为历史实施记录

User asks to generate candidates faster. Existing source job owns run 20261104-053708-1a5f92e2ac83 and has completed 15 scenes; preserve all accepted task IDs and completed images. No inference/model/prompt changes or duplicate submissions.

The main waste is rehashing the revision's sealed imported audio/inputs under the writable-run root and losing verification contexts in TOS/HTTPS workers. Extend the existing Windows protection window with explicit immutable_roots. Only those declared, fully hashed inputs can retain native deny-write/delete handles within the current writable run. Ordinary writable outputs and manifest.json remain fully rehashed and movable. Context copying lets worker guards use the same live protection; existing cancellation/deadline and full source checks remain.

- [x] RED→GREEN for sealed owned inputs, writable siblings, nested writers, released/closed contexts and network worker digest reuse.
- [x] Implement scoped immutable roots + copy_context for external HTTPS and TOS worker threads; run verification/transport regressions and independent review.
- [x] Update operational resume helper to pin only already-sealed inputs and completed scene directories.
- [x] Suspend ONLY the known owned producer atomically; inspect all persisted paid intents. If any lack accepted/result evidence, resume and wait. Only stop at a no-inflight-model checkpoint, archive the dead-owner lock, then resume existing IDs with the optimized helper.
- [ ] Verify actual progress and retained candidate identities after restart; report measured behavior.

No Git metadata writes; user already opted out of design approval. Do not weaken source identity checks, overwrite immutable artifacts, change service limits or manufacture receipts. Process control is scoped to PID33500 with its exact stored start time and current run lock ownership; do not touch unrelated processes.

Validation: initial four new tests failed for the missing API, then all four passed. Verification/session/continuity/TOS/HTTPS regressions: 110 passed. Three additional edge cases (manifest exclusion despite explicit declaration, nested scope expansion rejection, earlier copied context seeing writable siblings) plus targeted coverage: 10 passed. Independent static review found no substantive issue in the core changes. Before restart, scene manifests advanced to 18; recent scenes each took about 6m20s. First atomic checkpoint declined to stop because scene_0019/request_02 was pending, and resumed the producer.

At 20:30:58 local the checkpoint found 38 completed paid tasks and 19 completed scenes, stopped only PID33500 after matching its start time and token, confirmed death, and archived the old lock. Audit: D:/VideoSi/cache/video-ai/logs/reference-speed-checkpoint-20261104T123058852383Z.json. Optimized producer PID34612 started 20:30:59, active session39183, log reference-resume-9d6309e724814f649930cc1d208adcb6.log. Read-only probe confirmed all prior scene manifest contents, all 38 task IDs, and the selected baseline PNG digest unchanged. No speed claim yet: producer still recovering existing records as of 20:34.

Operational review identified an older helper issue: SystemExit inside the protection context skipped normal-exit verification. Helper now stores main's result and exits after normal context closure for future invocations. The already-running invocation loaded the preceding helper; do not incur another restart solely for this (all transaction-boundary checks and native deny-write/delete handles remain active).

## Follow-up: measured CPU stall

At 22:28 the job was still at 19 scenes and had no pending/new paid task. The earlier optimization was not shown to improve production and must not be represented as successful. PID34612 had consumed about 7,003 CPU seconds since 20:30:59.

Read-only py-spy stack sampling (498 samples, 10 seconds) identified 69.3% inclusive time in the repeated immutable-root ownership scan before every protected digest hit. File: D:/VideoSi/cache/video-ai/logs/reference-stall-34612.speedscope.json. Retained entries are already admitted/evicted under the window lock; get now looks them up directly and retains native metadata/path verification. Existing writer/closed-context regressions: 113 passed.

The profile also showed nested reference validation repeatedly replaying complete revision source closure and frozen-input loading. Explicit strictly local read transactions now fully check guard bytes/inventories on first access and exit; frozen state remains checked on every lookup. Only reference binding, reference input validation, reference candidate reading and the local batch preflight use these scopes. Network and persistence are outside. Closed/foreign contexts and continuity dependency capture cannot reuse skipped checks. Input loader reuse keeps only a canonical digest and runs the complete loader again on scope exit. Ten targeted boundary/mutation/context tests passed after separate RED observations. Independent static review found no substantive issue in each change.

PID34612 was stopped at a checked checkpoint (all 38 tasks complete, same 19 scenes) at 22:37:51. PID35860 then failed with native exit code -1073741819 while a diagnostic faulthandler timer was dumping a traceback; the truncated dump is preserved, the exact crash cause is unconfirmed. Removed timer instrumentation. The OS process object was confirmed signaled/terminated with matching original creation time before archiving its lock; all 38 tasks still had accepted/result proof. No paid submissions were in flight. Archive audit: reference-crash-recovery-20261104T144345022166Z.json.

The producer at 22:43:45 was PID24588, creation time 134382770252425806, lock token 0898ad670d274d9d9c5ddca2a56ba6f9, exec session3529, log reference-resume-a391a8c356e446c28d1b81eeca016a0a.log. A subsequent read-only stack showed reference_settings._run also calling the same full loader, bypassing image_selection_records._run's transaction memo. Both callers now share the exact run/loader key; outside transactions they still load fresh. Independent review found no substantive issue. Current revision/reference unit suite: 51 passed in 4.00s. Earlier broad reference/revision regressions: 111 passed in 575.88s (started before the loader memo change; do not claim these exercised the latest memo).

All 38 completed paid tasks were again confirmed before stopping PID24588 at 22:46:53. Current producer PID33528, creation time 134382772141510029, lock token 26e0a996b6514e369485b71d92a5cb3c, exec session13748, log reference-resume-acd31bf4e1ac4177bf2c2673f53c0135.log. At 22:48:25 it logged scene_0002 recovery starting and completed it in 19.2 seconds, then started scene_0003. This confirms actual recovery movement, but not yet newly generated scene20. Helper logs each scene start/completion; diagnostic timer remains removed.

Latest-loader integration coverage: actual submit payload, changed source after intent blocks paid submit, and original task query/download recovery without resubmission: 4 passed in 15.14s. Current unit suite 51 passed. By 22:52:23, recovery had completed through scene_0012, consistently ~19 seconds per scene.
