# VCO-08 结项记录与接续历史

## Final Completion — 2026-11-04

**VCO-08 已按任务板从 IN_PROGRESS -> COMPLETED，当前无未完成工作、活动测试或GPU进程。** 主五项Acceptance逐项证据见`docs/task-designs/VCO-08-production-verification.md`；正常使用方式见`docs/jimeng-candidates.md`。没有更大Order后继任务，不新建任务、不发布。

- 既有C四窗768×432/16fps、320帧20秒完整真实human_video接受保持（review SHA4beaf4aca19f19e1a5d1a4c28deddb525fd118a8c5e32d20891b0ed35440421f）。真实父raw13/48层KV/RNG可追踪，生产显式opt-in接口/版本化事务/静态与整链门禁/媒体/修订和旧兼容完成。
- 当前8源真实资源根`D:/VideoSi/projects/video-ai/inputs/vco08-production-resource/c8da3bd7e9c2441cbb9594255a959a20`五阶段complete，worker23784/runner9324及session13689实际exit0，resource_trigger=null。执行总时限和人工内存/显存配额null；启动/运行实际余量保持，Terminal/AweSun未关闭，0新增采样/文本编码/视频输出。
- 普通exporter和正常加载完成独立生产准入：`C/production-native16-admission.json`，185810字节，SHA1e56f31d5bb2c885342d250daaf9209bc38ff21383c9f3226cfbb30eac5c8d47，assessment.ready=true。最终日志vco08-production-admission-final-49c1e3f00363453884d30eb4991be482，exporter/覆盖核对及session65845均实际exit0。
- 最终逐节点账`C/regression-final-coverage.json`，1853412字节，SHA4afb0b07350ff1e1b6961539237ab16e8016217134369b94291ece77fcd05a67：5326唯一节点全部有有效PASS来源，未知0/未解决失败0，最后repair库存与全部当前源码SHA一致。1768批14失败由108 GREEN解决；659批1失败由21 GREEN解决，所有原始失败/中断收据保留。六条原生修订长集成保留既有完整终态，不重跑。
- 唯一独立review为0 Critical/3 Important/0 Minor，三项均真实RED→GREEN；无未处理重要项或延后Minor。diff --check通过。遵循.git只读约束，改动和证据保留在既有工作区，未commit/merge/push或清理证据。
- 适用视觉范围仍是单白鹭四窗20秒；其他输入和更长新链须实际新完整观看。生产封装资源前向/CPU fixture未被当作新视频视觉接受；模型、文本缓存、已接受资格片与失败血缘均复用保留。

下文均为历史进行中快照，其“待完成/运行中”及PID不能再作为活动入口；无需恢复或重启任何旧批次。

## Final software green / current-source resource operation (2026-11-04 00:05+08)

00:10更新：当前c8da3bd7e9c2441cbb9594255a959a20五阶段GPU已全部complete，worker23784/runner9324及tool session13689均真实退出0；resource_trigger=null，native_diffusion_calls/new_text_encoding_calls均0，执行/占用上限null。normal exporter + verify_final_coverage.py已通过run_final_closeout_checks.ps1启动，等待本次真实终态，不再启动GPU或测试。当前生产准入目标C/production-native16-admission.json此前不存在，不会覆盖旧收据。全部核对成功后仍需更新验收记录、设计header/ledger、研究记录、任务板COMPLETED和主handoff最终状态。

最终GPU唯一实例已实际启动：tool session13689，worker23784，output=`D:/VideoSi/projects/video-ai/inputs/vco08-production-resource/c8da3bd7e9c2441cbb9594255a959a20`，唯一pointer为`C/production-resource-current-c8da3bd7e9c2441cbb9594255a959a20.json`，bootstrap日志vco08-production-resource-final-7684dcee79b64b05977560354125c84d.log。不要重启或改源；只读worker.stdout.log监控，核对该root/completion.json及production-resource.json和实际退出码。后续closeout wrapper必须传这个新output，不用旧88e4。

659新增/受影响批session48047已完整结束：658 PASS/1 FAIL，9327.22秒、exit1、source_identity_unchanged=true，C/regression-final-affected-0360546c33894fc1b445fa064630af77。失败堆栈确认仅scene_continuity_records._prefix新增native scope检测访问旧expected缺失的video_expected。现仅将该新分流改为可选键读取，旧输入继续原historical provenance拒绝，不放宽原验证；21个失败节点+原生/旧continuity定向全部GREEN/34.52秒，session71023实际exit0，C/regression-final-repair-6d1e7f5cbd9645dab00f2b718969c4fe/completion.json source_identity_unchanged=true。原1768批14失败已在108 GREEN全部解决。勿再跑1768/659或已有6条原生修订长集成。

当前已启动run_current_resource.ps1进行最终当前8源五阶段GPU资源；先从本次stdout登记新的唯一pointer/output/实际PID（旧88e4不能用）。期间不改src/tests/scripts、不运行CPU测试、不重下/重编码/模型采样。用户Terminal/AweSun授权持续有效，仍保留实际空闲余量，不关闭应用。下一步五阶段complete+worker真实exit0后，运行run_final_closeout_checks.ps1 -ResourceRoot <新output>普通exporter到C/production-native16-admission.json，再verify_final_coverage.py逐项核对5326节点及最终repair源码SHA。该核对工具必须实际成功后才能更新COMPLETED；主验收/研究实录/设计header/plan checkbox/任务板和handoff终态仍待最终证据，不得提前结项。

## Active final affected suite (2026-11-03 21:30+08)

22:24更新：同一CPU session48047/runner10080/pytest8992仍运行，109 PASS/1 FAIL，当前test_prepared_public_pipeline_waits_for_parent_and_never_posts_child_or_duplicate长用例；只读py-spy证实已越过实际合成进入test_scene_pipeline_recovery.py:261的完成事务损坏只读拒绝及后续继承检查，CPU持续工作，非等待人工/模型。不要因慢而重启；不改src/tests/scripts、不启动GPU。91→92→109各节点已真实输出PASS，唯一FAIL仍旧_prefix缺video_expected兼容。

staging工具现已进一步准备好：run_final_repair.ps1从regression-final-repair-selection.json读取nodeids/nodeids_sha256/node_count，严格前后源码SHA、真实终态并写C/regression-repair-current.json。待659完整结束、查看所有完整失败堆栈后，修复已RED问题，生成失败节点+必要native continuity覆盖的精确repair清单/selection，再运行该runner，不重复659。verify_final_coverage.py现已支持659中的失败由显式repair完成收据逐项解决，并核对最终repair源码库存；不再硬要求659原批全绿，不会用旧PASS掩盖新FAIL。

run_final_closeout_checks.ps1 -ResourceRoot <新资源output>已准备：先核对新completion真实exit0/无resource_trigger，用正常scripts/export_temporal_evidence.py+该root/runtime.json、production-resource.json导出C/production-native16-admission.json，再执行verify_final_coverage.py生成C/regression-final-coverage.json。所有脚本用powershell.exe -NoProfile -ExecutionPolicy Bypass -File启动（默认execution policy禁止直接dot-source）。资源入口仍run_current_resource.ps1，务必在CPU/repair都结束后运行并登记新stdout的唯一pointer/root/PID，别误用旧88e4。

21:36更新：659批次已30 PASS/1 FAIL，仍运行。失败为test_scene_continuity_recovery.py::test_prefix_playback_rejects_fabricated_historical_assessment_stub；静态根因是scene_continuity_records._prefix新增native scope检测直接expected['video_expected']，旧helper输入不含该字段，提前KeyError而非既有历史provenance拒绝。先等完整终态，不在CPU中改源码；之后以当前已RED节点修复仅native检测的可选键读取，使旧输入继续原历史验证并ProductionRefused，补native continuity定向。不重新跑整659，保留完整已PASS节点；verify_final_coverage.py目前草稿要求659全绿，若有此失败必须扩展为显式最终修复收据/逐节点合并及最终源码SHA后才可生成完成账，不能忽略失败或直接改数量。

**唯一活动CPU：tool session48047 / runner10080**，入口`C/regression-affected-current.json`，输出`C/regression-final-affected-0360546c33894fc1b445fa064630af77`。实际collect5326节点，原5127全部保留、新增199；补跑清单659节点SHA31534b0c857beeac7e065ffafd50d8580a8b9ae1d400face1fb002f220e1368b。包含193个新增节点及466个受影响旧节点，六个原生修订集成按已完成c0e3/d79d/56f2各2项证据保留。其余1768批1754 PASS/14 FAIL中的全部14已在108 GREEN63b6b9d2cbda4ddda126e1b3444d9f53解决，勿重复整个1768或长原生修订。

659运行期间不改src/tests/scripts、不启动GPU；当前只输出前几条旧continuity集成PASS，批次未终态，不预记绿色。runner自带前后全部源码SHA/列表SHA和真实退出码，执行时限null。最终collect bootstrap ccc3b2b051c6481d89dfd21e4b66f047实际exit0/5326；外层PowerShell因stderr信息返回1，不是collection失败，完整log确认。PowerShell重定向文件UTF16 BOM；新增staging工具按BOM读取。

下一步终态后核验实际结果；GREEN后按run_current_resource.ps1取得当前8源五阶段资源（无采样/编码），正常scripts/export_temporal_evidence.py以新root/runtime.json、production-resource.json导出C/production-native16-admission.json。随后运行staging/verify_final_coverage.py（需bootstrap wrapper），会严格核对5326逐节点来源、14旧失败已解决、六原生集成保留、659实际PASS集合与全部当前源码SHA，产出C/regression-final-coverage.json；未完整时会拒绝。不重跑download、模型完整hash、已有文本编码或资格采样。最后逐项验收证据/任务板及主handoff结项；VCO-08仍IN_PROGRESS，不能提前完成。

## Regression fixes green / final collection (2026-11-03 21:21+08)

session51431已完整退出1：1768精确余项=1754 PASS/14 FAIL，1300.17秒、source_identity_unchanged=true。原目录C/regression-remaining-final-ac534ed13ab54c3e89b020f46ca962ab保留。14项已按真实堆栈修复：七项legacy最小media对象config可选；四项whole祖先fixture明确whole；execution=None所有新native分流按空mode处理；公共verify_whole_scene_frozen补全mandatory读保护；旧finite continuity测试仅显式测试注入，新增生产长preflight无上限断言，不恢复生产上限。shared cache首/续窗workflow差异有新RED7b62c44c后修复按实际创建者匹配，成功video无unknown也通过。

**最新GREEN**：七文件108 PASS/14.54秒、实际exit0，test-63b6b9d2cbda4ddda126e1b3444d9f53；session33500已退出。当前正在final --collect-only，stdout为C/production-staging/final-collection.stdout.log。完成后运行make_final_coverage.py该日志生成最终新增/受影响节点（排除已跑1768及独立已通过的6条native revision节点），再用有源码前后/列表SHA守卫的runner串行执行。14失败在108中均已复验，不再跑整个1768。最终当前源码资源五阶段、exporter至C/production-native16-admission.json、覆盖账和逐项Acceptance仍待。不要把下文旧11失败/活动PID当当前状态；不重下/重编/重采样已接受资格。

## Active exact remaining regression (2026-11-03 21:05+08)

Important1公开修订复验56f22a27a1ea4ad3a475090840b9b54c已真实退出0：one-window/prepare-cache两条2 PASS/186.78秒。独立审查三项Important均已有RED→GREEN，不重派review。

**唯一活动CPU是tool session51431 / runner6796**；`C/regression-remaining-current.json`指向`C/regression-remaining-final-ac534ed13ab54c3e89b020f46ca962ab`，精确1768节点，源码前后哈希由runner核验，不设置时限。当前约38%，尚无completion。已明确11项FAILED：test_scene_media_coverage_review.py的different_whole_ancestor四参数；test_scene_media_records.py的captured_upstream三参数、json_fsync、capture_promoted、capture_admitted_extraction两参数。不要只看尾部PASSED就声称没有失败。

先等当前完整终态，运行期间不修改src/tests/scripts或启动GPU。静态调查待堆栈确认：SceneMediaStore.assert_owned中新native分支直接self.frozen.config.raw，使旧最小对象七用例AttributeError；different_whole_ancestor测试从coverage_case复制了segmented config_snapshot，祖先并未标whole，需明确fixture祖先为whole后测试其独立reader，不能恢复用户已移除的whole重复检查。当前尚未应用这两项修复，需等完整堆栈并RED→GREEN，已通过的无影响节点保留。

`C/production-staging/make_final_coverage.py`已准备，待最终源码collect后从collection日志选新增/受影响文件并排除本批1768。修复后须单独复验失败/受影响旧媒体文件；再运行选出的定向/计划兼容覆盖、当前源码五阶段资源和正常exporter。新增`docs/task-designs/VCO-08-production-verification.md`为真实证据/待办表，未写完成。git diff --check退出0，仅行尾CRLF提示。旧61 GREEN、跨run2 GREEN和实际资格视频保持，不重下模型/重编码/重采样。

## Current final-review fix pass (2026-11-03 20:51+08)

CPU d79dfdc3193f4759afa3f9c36be52c05已完整退出0：两条原生跨run修订集成2 PASS/3508.22秒，不重跑。用户Windows Terminal/AweSun放行继续有效。独立最终review已完成，不再派复审。

审查Important 2（fresh native只检查upscale）已真实RED→GREEN，29 PASS/1e39309fefa548668d047aef2c66ea05；Important 3（通用complete_value原生分流schema4）RED2a05fbb00d0e4d44a21ecd035f11cfed→38 PASS/1c5e1ff425d344649af243287cee5f2a。源码已存在，不重复实现。

Important 1公开修订入口真实RED6aed65a40107414891948e9d9e962dfe：launch-intent早于worker intent时误revision_ready。现新增native_revision_effects核验视频/独立cache的request/launch/owner/terminal关系，未知阻止修订，latent待解码仍阻止，已匹配失败终态可归档，已提交cache只读复用。修正测试中中断mock未恢复而遮蔽真实cache resolver的问题，使用真实resolver验证缓存字节不变。61项定向GREEN7db928e038804bbdb15ec7ef7ba46a14/4.80秒。

**唯一当前CPU**：tool session10652，test-56f22a27a1ea4ad3a475090840b9b54c，运行test_temporal_revision_flow.py -k revision_blocks_native_launch的one-window/prepare-cache两条公开入口集成；尚无终态。先核对结果，运行期间不改src/tests/scripts、不启动GPU。之后补最终受影响覆盖/精确1768剩余节点、当前源码五阶段资源、正常exporter至C/production-native16-admission.json及逐项Acceptance，尚不能结项。

## Current CPU After Event Projection Fix (2026-11-03 19:22+08)

**唯一活动CPU是 session36241 / test-d79dfdc3193f4759afa3f9c36be52c05**。按partial先行、`-vv -x`运行test_native_revision_keeps_raw_parent_but_requires_new_mixed_chain_review及test_native_revision_inherits_unchanged_scene_with_original_observation。先核实终态，期间不改src/tests/scripts、不启动GPU。

最新：该批次已完整输出partial节点 **PASSED [50%]**，第一条局部父窗继承/raw13/一次采样/新混合链观看门禁/原事件及源run不变均通过；第二条整场景继承仍运行，批次未有终态。唯一独立最终review已按技能要求派 /root/vco08_final_review（只读，禁止测试/GPU/写文件/再派代理），包C/production-staging/final-review-package.json含59 overlay/28 untracked；后续取其Critical/Important在本agent按RED→GREEN处理，不另派复审。

独立review现已完成：**3 Important / 0 Critical / 0 Minor / Declined空**，完整发现保留C/production-staging/final-review-findings.md。必须在当前CPU批次终态后按一次RED→GREEN fix pass处理：（1）_admitted_snapshot遗漏native video/cache launch-intent早期unknown；（2）fresh native production_preflight/model-path checker仍要求inactive Wan；（3）coordinator缺失complete.json时通用complete_value重建schema3而非native schema4，须0新增provider恢复。不要重派review，不因这些已知待修项提前finalize或标记完成。

19:48更新：实际pytest18668、launcher8912，均19:22:27启动；只读stack C/production-staging/native-partial-live-stack.txt确认处于partial用例220行目标produce_scene_clips的继承来源核验。源run20261103-112308-8142537d9012四窗/complete已生成，目标20261103-112738-9901f043de86已revision_ready，尚无目标新后继结果时不计PASS。待CPU结束且最终软件验证后，GPU启动用C/production-staging/run_current_resource.ps1（已备但未运行）。runner改为每次输出独立production-resource-current-<output_uuid>.json，避免覆盖旧current.json immutable收据；从新stdout登记确切pointer/PID，旧88e4保留历史。

- 旧session1743/648334da已完整退出1：2 FAIL/1541.62秒。首条实际revision_ready及源片complete、仅指定scene一次新采样已通过，但最终断言发现原观看事件被remap_media重写paths；第二条长PCM只因helper原13帧断言而提前失败。不能把两条算PASS。
- 已加native_event_projection_draft.py至repo（勿再追加），修独立空target fixture后真实REDf696366e定位原request/static/chain observation被改写。新增remap_temporal_window/chain在两个消费者中只重定位技术媒体，原始request/作者事件和origin_template原文保留；120 GREENe765efccc4e746e4be8f0e7944098440/7.10秒。
- prepared_pipeline默认13帧/5+4+4断言保持，仅可选long speech_samples不套用该常量；OfflineNative的KV seam依然明确fixture_only，真实raw13仍送provider。跨run低层读查询native_progress使用一次完整mandatory读窗口，实际bytes/inventory均核对。
- 独立py-spy0.4.1只读采样工具仅解压于D:/VideoSi/tools/video-ai-diagnostics，未安装/升级生产环境；旧1743栈与profile保存在C/production-staging/native-origin-live-*，只作诊断不是验收。旧staging所有draft均已追加repo。
- 软件通过后仍需当前源码五阶段资源（旧88e4已过期）、正常exporter到C/production-native16-admission.json、精确1768剩余节点及新增/旧兼容覆盖、一次独立最终review（须含untracked）、主Acceptance逐项结项；VCO-08仍IN_PROGRESS。生产操作说明已追加docs/jimeng-candidates.md；未发布/未造后继任务。

## Latest CPU / Admission Fix (2026-11-03 18:54+08)

唯一活动CPU为 **session1743 / test-648334da137d4fbb9abc6b388500d73e**，运行test_temporal_revision_flow.py的inherits_unchanged及keeps_raw_parent两个节点。先核对终态，运行时不修改src/tests/scripts、不启动GPU。

- 旧83503/877c7e6f为定位到每个RevisionGuard.verify_frozen都重建完整资格闭包后受控中断，实际pytest11528退出-1/tool1，节点unknown，0 PASS。C/production-staging/native-origin-admission-duplication-interruption.json留证。不能恢复旧进程或把它算通过。
- native verify_temporal_frozen已加严格operation-local语义复用：同操作4次重建的真实count RED62a0ed45→24 GREENcaf83018；每次仍检查原byte/inventory、value/raw/typed EvidenceReader完整契约，跨操作重新准入、源码字节漂移仍拒绝。
- create_scene_revision仅native通过ExitStack持有mandatory input window+validation_session，target writable_validation_session使真实媒体pending可晋升。REDa694966d→新旧相关151 GREENca468aa5/5.30秒。只是为上下文新增一层缩进，不能误还原原有函数主体。
- 已把native_partial_integration_draft.py追加repo：长PCM生成首scene两窗，保留旧父窗/13真实raw帧，只重生成后继，新混合链必须新完整观看。测试helper prepared_pipeline增加speech_samples可选参数（默认原值）；OfflineNative增加明确fixture_only KV seam，实际raw13条件仍传provider。所有draft均已追加，勿重复追加。
- 新admission/records helper已改变，旧88e4资源收据不能finalize；软件最终后重跑五阶段（0采样/0新编码）。C/production-staging/run_remaining_regression.ps1已备好**但未运行**，严格1768列表及前后所有源SHA/终态；仍需旧兼容/新增覆盖、正常exporter最终准入、一次独立最终审查、Acceptance逐项核实。VCO-08仍IN_PROGRESS。

## Current Continuation (2026-11-03 18:29+08)

18:33更新：旧CPU58816/e26d11cf已退出1/348.02秒，失败为native source只冻结upscale，_target_configuration把effective子集当完整raw导致workflows.wan缺失。已真实小用例RED5e825cb5→仅native保留inactive raw绝对路径并叠加frozen active角色，155 GREEN7fbe2fd4；没有读/复制/启用Wan。native_risk_draft.py已追加repo并通过，不要重复追加。**唯一当前CPU为session83503/test-877c7e6fb7d74654b914b86d177db3ba**，相同跨run集成复验，先核实终态；不在运行中修改源码或启动GPU。其余剩余项继续，不重跑已通过媒体来掩盖本节点未通过。

- GPU session73545已退出0，worker8100/runner20072均结束，不重启。88e4a41c0c1745268d4bb686ae28930a五阶段resource complete=true、0采样/0新编码、无人工时间/占用上限；C/production-staging/resource-result-verification.json核实8源码。但之后为修订丢弃媒体边界修改temporal_scene_records，因此该收据只是历史通过，最终准入须重新运行当前源码五阶段资源。
- 原先未通过的完整媒体用例已GREEN：test-c0e3a23aeee84fd4a6f52d73d0a5979d实际退出0，2 PASS/1264.61秒；真实CPU超分、完整PCM/字幕、合成及同run0新增采样。数值/观察/continuity seam仍明确fixture_only。
- 来源修复：upscale capture_origin纳入native chains目录；_scene_revision_origin_clips仅在明确discarded集合内读取native binary声明，JSON/事务/观察仍核验，required媒体缺失仍拒绝。真实RED fa7e9603/7a6f3e54 → 6 GREEN7a591df182e24153abcbf37be0e74a91。
- **唯一CPU集成仍运行**：tool session58816，实际pytest19528（launcher3060），日志test-e26d11cf70974af3bb746262b57fee6d；目标test_native_revision_inherits_unchanged_scene_with_original_observation。先核实终态，运行中不修改src/tests/scripts、不启动GPU。不把当前source fixture三个窗口已生成当通过。
- 该集成结束后，把C/production-staging/native_risk_draft.py追加到tests/unit/test_temporal_continuity.py后运行unit，继续处理集成实际失败。native_origin_unit_draft.py/native_origin_integration_draft.py已追加到repo，勿重复追加。还需部分继承加新窗/旧兼容、1768精确剩余节点+受影响测试、正常exporter最终准入、一次独立最终审查与Acceptance。VCO-08仍IN_PROGRESS，不发布、不造后继任务。

## Live Production Resource Preflight (2026-11-03 17:58+08)

用户已明确放行Windows Terminal/AweSun，本次授权保留于C/production-desktop-authorization.json；不用再问。**唯一活动GPU资源预检**由实际stdlib runner20072持有embedded worker8100，tool session73545；当前入口C/production-resource-current.json。输出`D:/VideoSi/projects/video-ai/inputs/vco08-production-resource/88e4a41c0c1745268d4bb686ae28930a`，bootstrap日志`vco08-production-resource-0e68bfc906c6419fadacc5ad00b13888.log`。不重启当前进程；没有CPU测试同时运行。必须核对completion.json及production-resource.json/真实退出码；5阶段complete前不finalize，不把进程启动当通过。源码8项在预检期间不修改。

- 此前75a2da4c477a416a9161b24b85d72d40 CPU复验因具体重复全闭包核验缺陷受控中断，实际-1；其集成节点unknown，未计PASS。已通过真实RED76447a2752014b539e333b8d0e749459修复逐文件重核全闭包及CLI main顺序；新旧相关59/60项通过。原生已准入文件只核验本文件/实际持续句柄，完整依赖仍由严格原生byte proof/coverage守卫。
- 新提示编码独立owned prepare-cache阶段已在视频intent前接入；原缓存直接复用，unknown cache作业不再编码，原提示绝不重编码。worker CLI允许精确input或prepared-run目录，parent仍不导入Torch。完成source/header/selected-image、cache与独立proof定向94 PASS后，补充native source snapshot与bound origin metadata。
- 新`runtime/temporal_scene_origins.py`及单测已加入，原生snapshot走自己的事务视图，已接入native metadata起源的精确Artifact、raw93/Generator/整链viewer复制角色及完整scene来源闭包；共享旧分支规则保持。最新8个native文件110 PASS/13.61秒，test67f504e212a94f7cb562a33d1e1ae4c9。原生同mode继承的整链、部分新链跨run观察与完整媒体端到端尚须集成复验，当前不宣称Task6完成。
- GPU真实预检结束后，先检查结果/修复实际失败，再继续`test_temporal_revision_flow.py`媒体/PCM/字幕与native origin用例。当前`test_native_mode_to_real_upscale_mapping_full_pcm_and_subtitles`最新完整RED为cc3598cd330f4b8e9344f300595d39aa；上述中断批次不能算GREEN。之后仍需旧兼容、1768剩余节点+影响范围、新源码identity、独立最终审查与主Acceptance逐项结项；VCO-08仍IN_PROGRESS。

## Latest Active Work (2026-11-03 16:54+08)

本节和production plan最新ledger优先于下方14:39历史快照。VCO-08仍IN_PROGRESS，继续当前实现，不重做资格或下载/文本编码。

- Task3已完成；Task4原生process/worker和真实数值provider已实现，五阶段真实GPU资源尚未运行。Task5流式组装/公开入口/静态与chain观察接入已实现，320四窗与334五窗fixture_only生产事务、真实编码/解码及同run0新增采样测试2 PASS/134.37秒（67565c6c208a49b083bc16869492b61f）。FakeProvider和数值KV seam均明确，不冒充真实模型视频。
- 当前唯一CPU测试：`tests/integration/test_temporal_revision_flow.py -k native_mode_to_real`，bootstrap日志`test-cc3598cd330f4b8e9344f300595d39aa.log`，tool session45766；Python实际17220/launcher19576，16:49:37启动。先核对终态，运行期间不改src/tests/scripts。上一次该测试真实RED7ab6cd14b76b43eea7ca492086619174在原生生产创建manifest前因resolved workflows缺Wan被拒；已按显式native仅允许完整upscale快照修复，不放宽其他mode。
- Task6纯schema4映射、rendering identity4/source execution2和旧版本保留已完成。独立TemporalExecutionCheck已实现并拒绝未知/被替换proof；native源context已使用，媒体context尚未接入。VCO-04原生binding/一份完整chain观看作自身prefix与旧continuity定向通过，仍需完整消费者/风险回应/旧兼容。
- 原生请求新增冻结selected_image/comparison_images/narration_bindings/visual_bible_sha256，防下游失去VCO-01共享上下文；真实RED0d179e49eeb14a3b95a09d9d736a360e→worker/records/proof55 GREEN abfedace6c8d455f9ab48c67738db589。现有资格C不使用该新生产请求，不修改它。
- 常规native修订已能冻结独立准入并合法保留PCM/选图，真实测试aab86232344242d58759187ad08e3872实际revision_ready，只剩测试误写预期[13,3]而真实原scene预算为[13,2,3]；已修正预期，尚待完整复验。runtime的native source snapshot/origin与媒体proof接入仍待做，未宣称完成。
- GPU两次检查都在worker启动前拒绝，零模型调用。已用现有desktop_policy逐项核实，仅Windows Terminal `C:/Program Files/WindowsApps/Microsoft.WindowsTerminal_1.24.12741.0_x64__8wekyb3d8bbwe/WindowsTerminal.exe`和`D:/Program Files/Oray/AweSun/flutter/AweSun.exe`（均C+G）未获放行，空闲23708MiB。按现有gpu_desktop.desktop_approval_scope明确路径授权要求，异步问题待用户答复。不得把用户未答复当批准，也不关应用/降资源余量/改全局allowlist。收到允许后在run作用域用这两个确切路径与真实回复文本授权，运行C/production-staging/run_production_resource.py（需给runner加desktop_approval_scope），不要重装bundle或重读资格全部bank。
- 已发现尚待修复的CLI顺序：`temporal_native_worker.py`中`if __name__=='__main__':main()`位于`execute_native_operation`定义之前，import测试不暴露。当前CPU退出后写真实runpy CLI+注入provider的RED测试，再把main调用移到文件末尾；不能直接启动GPU前漏掉该修复。
- 之后完成Task6媒体external-artifact proof（当前generic SceneMediaStore会拒绝native workflow的外部bundle/python/cache路径；必须仅以独立严格native闭包覆盖，不放宽run_path）、修订origin、端到端PCM/字幕及VCO-04，再执行1768精确剩余节点+新增/受影响测试/最终独立review。旧751与2607 PASS来源账保持，不重跑原4375或其无影响前缀。全程没有时间或模型内存占用配额，真实空闲余量守卫保持。

## Current Production Implementation Snapshot (2026-11-03 14:39+08)

**当前无CPU回归或GPU进程运行；旧14148/8068均已结束，不能重启旧4375批次。直接继续生产计划Task3，不再请求资格接受或逐步确认。**

- 用户新反馈“视频没问题，继续吧”已绑定C完整320帧/20秒链；review SHA4beaf4aca19f19e1a5d1a4c28deddb525fd118a8c5e32d20891b0ed35440421f。C资格收据`native16-qualification-assessment.json` SHAafeee7f892bb36329a6d7afd4ffa297931ae3683c3149847b4d6602dbb40c947。资格通过，不重采样/下载/编码。
- 正在执行`docs/task-designs/VCO-08-production-native16-plan.md`及关联design。Task1纯预算/协议/配置/prompt版本入口完成；Task2准入/27源bundle/冻结/exporter软件实现及定向验证已完成，真实生产封装五阶段资源和最终ready明确等Task4。Tasks3..7尚未开始；VCO-08仍IN_PROGRESS，生产未启用。
- 新文件：`planning/scene_temporal.py`、`runtime/temporal_scene_admission.py`、`scripts/export_temporal_evidence.py`、两个对应unit测试。已修改config、jimeng_config的native active模型/图分支、scene_execution、scene_clip_continuation、scene_video_prompts、production_inputs、scene_execution_records。具体TDD日志见production plan账本。
- 最新合跑241 PASS（test-36c41d2ec3c344bf9b41b04acc62a329）；旧production_inputs/recovery/execution_records兼容70 PASS/142.60秒（test-5eba65cb78ce4adfb62c883424c5d7bf，session7384已退出0）。先前Task1主要200+旧映射198通过，不能简单相加当唯一测试总数。
- 真实C资格读取/三份bank完整闭包及27小源码安装通过：bundle `D:/VideoSi/tools/video-ai-temporal-native/ae99bb7ed0ee399adb8dd4b23ef754900f844ce516348859664d0925e1c523f3`，bundle.json SHA03603bbf0e2e755811aec79ebc9a809ee6744dadfd0e8326f20f88eacc19a057，`C/production-core-installation.json`保留。安装0权重复制/下载/文本编码，parent未导入Torch；不要为继续Task3重复此安装/完整bank读取。
- 原4375批次在新接受后为先实施最终源码作受控调度中断（非时间上限）：退出15，520源前后一致，**2607完整PASS/0FAIL**，stdout已打印下一未完成节点，边界精确；原751 PASS保留。`C/regression-implementation-checkpoint.json`与`regression-post-implementation-remaining-nodeids.txt`为继续依据：**1768未完成**，列表SHA1d461611f9cad13986a71fe242dd7bdb1018b7ab1445ef44ed3c1887773910b2。最终源码完成后只续此列表+新增/受影响测试，不重启旧4375或机械重跑原前缀。
- Task3下一步：先写`test_temporal_scene_observations.py`及records测试并实际RED，再实现独立static-window/dynamic-chain模板、父raw13/Generator/静态绑定与schema4 index；尚未创建这些文件。Task4原生process/worker/resource-preflight都未创建，不能伪记生产资源通过。Task6仍须升级runtime prompt mode/schema、rendering identity4、修订snapshot/origin和媒体guard消费者；当前配置可解析不代表这些已完成。
- 遵循既有dirty工作区/.git只读授权，不建worktree/commit，不升级Comfy，不重下模型或重编码既有缓存；研究/正式生产时间和人工占用上限null，实际余量守卫不变。最终审查须包含untracked新文件，不能仅看git diff --stat。

## Task Link

- Board: `docs/task-handoffs/video-continuity-optimization-task-board.md`
- Task: **VCO-08 / IN_PROGRESS**。这是活动快照，不是暂停、阻塞或完成。
- Primary design: `docs/task-designs/VCO-08-design.md`
- Current spec/ledger: `docs/task-designs/VCO-08-native16-qualification-design.md` / `VCO-08-native16-qualification-plan.md`
- Evidence: `docs/task-designs/VCO-08-research-results.md`最新段落；生产接口调查为`VCO-08-native16-interface-audit.md`。
- 旧handoff原字节归档于Q/handoff-before-active-4cccc8b0e7d9f86324bf22b27592882448cecf9908595201b6fa9140d475b149.md。旧BLOCKED是历史，不按旧入口重做。

## Historical Snapshot: Qualification / Old Regression Before Production Implementation

**四窗GPU已退出，完整20秒新动态已被用户接受，不再采样。先监测下列原CPU回归，退出后直接实施生产Tasks1..7。**

- Q=`D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification`
- **C=`Q/allocator-async-candidate-v1`**，当前唯一活动案例。
- 当前入口 **C/live-run.json**；2026-11-03 12:57+08四窗均各一次成功、完整性/实际静态通过。首窗4263.735秒/result849ff142563d9882c323f77aceae4277ee6c92672303a97419c925d7b172f3c3；第二窗4515.047秒/result8864c391d778155902120742591a43c5feecc9720e21c1ab241a56b19ac40b08；第三窗4161.422秒/resultb763f56a29e7832d88b3ae48f2d4184c2ef41ed8301161305fab7ccd78534463；第四窗4157.734秒/result6da17c6c99f388566c49979115a88dd1b304973fa25ef0ad07629a1c7a37dc42，12:51:42真实退出0。三个续窗各实际KV48层/4,076,863,488字节完整SHA通过。不要等待或重启已退出第四窗14808/9000/8536或前三窗。
- **C/trial-001/chain-004/viewing.mp4**完整新动态已被用户回复“视频没问题，继续吧”接受；`chain-004/dynamic-review.json` SHA `4beaf4aca19f19e1a5d1a4c28deddb525fd118a8c5e32d20891b0ed35440421f`，human_video/[0,320)。真实320帧/16fps/20秒，93+80+80+67，边界93/173/253；raw逐像素相同，保留区逐帧对齐、全链artifact SHA通过。曝光明暗变化、主体左移/翼腿出框已披露。资格接受仅单白鹭四窗，生产尚未实现/启用；无需再请求同一新视频反馈或逐步实施确认。
- chain result SHA `454ca48cd8febea79243dc6609dbb16d3913f8c3aba2f528df5c6dc4499bb7c4`；viewing SHA `1a45636bd0fed6cabfbefa9afbc05402371a6f4fbf8faad4d0338fae583adeba`；chain integrity SHA `0f6708185220c1c9e77344dba098aac2376a9573b486563800a1ab226b070274`。C/native16-technical-assessment.json与chain/dynamic-review-request.json保持。
- **当前CPU回归**：2026-11-03 12:56:15+08启动一次，runner PowerShell **14148** / test wrapper **9612** / Python launcher **21652** / 实际pytest **8068**，外层tool **70072**只作启动、不要求存活。`C/regression-final.stdout.log`逐节点`-vv -rA`，已实际collect4375；`regression-final.stderr.log`，实际pytest bootstrap日志`D:/VideoSi/cache/video-ai/logs/test-5f24febc8ece4f9aa24af2f5ffb5babc.log`。
- C/regression-final-launch.json、regression-final-run-intent.json绑定起点与精确列表；终态须有`regression-final-completion.json`/实际退出码/完整pytest结果。会话丢失先核对原进程与日志，不能重复启动或推造PASS。源码520项再次核验仅旧timeout测试修复，source proof6db413796bf028262f52eb83d7c3e5394ef4ddb49c7e3d49bd5410738f67aa68。回归执行中不改src/tests/scripts，不启动GPU。CIM进程查询拒绝访问，可用Get-Process/既有psutil，不请求提权。
- case SHA `66ab2b4eaf48fc1adde81e8319c0384a33c93b7022baf5fd438bf832317077d0`
- 27源software SHA `637d88ff64441e241d922585a4ca16cd279b7c0fe70575dea328083ed1302e93`，冻结源不能改。
- tool会话丢失时先核对原PID/起点/日志/产物，不能据此重启。每窗最多一次；failed/unknown且无sample-complete不能重采样。成功latent后才允许同身份decode-only。

## Authorization and Protocol

- 用户已接受M的完整253帧native15三窗，明确指出chain-003/viewing.mp4“这个视频没有问题”。M=`D:/VideoSi/projects/video-ai/vco08-preflight/20261102-0102-progress-io`。
- 用户对原生worker、768×432/16fps/320帧路线明确选择**“按建议直接推进，无需逐步确认”**，并反复要求完成任务；不再逐窗确认。
- Q资源失败后，按该持续授权作已记录裁决：具体修复/实测后独立C续验，原Q不重启，不更换seed/题材/规格、不降低余量守卫，不无修复随机重抽。范围/错误代价在qualification plan和C/proposal.json；不伪写用户对C的新逐字批准。
- 研究与正式生产无执行总时限；原8GiB CUDA池/20GiB allocation配额已移除。保留启动空闲物理8GiB/commit10GiB/GPU18GiB；运行物理2GiB/commit4GiB/GPU1GiB/磁盘32GiB。不关闭用户应用、不改pagefile。
- 模型revision03b55529b1d1d4045f5fbe14d65c8c6e8116b278，代码6b3f4b8582a8bc3f20f795735f5383716c4ba794；23文件77,577,230,776字节下载已完成，不重下/重复全量hash/复制权重。
- 模型目录D:/VideoSi/models/vco08-longcat/03b55529b1d1d4045f5fbe14d65c8c6e8116b278，依赖共享原R/python-deps，不升级Comfy。
- 文本缓存SHA `53c254856bcb45c0fd1cb8081bb5391538a9c0b672687e1605c1ef13404e77c5`；原飞行白鹭/提示、seed42、50步、CFG4保持。新下载/编码/权重复制0。
- 官方没有fps条件输入；16fps是采样前部署输出时钟。尺寸子类432×768，采样数学继承官方。
- 四窗原生各93帧；续窗13像素历史→4 latent，80新增。保留**93+80+80+67=320帧/20秒**；末窗[13,80)，裁尾13。边界93/173/253、PTS i/16；不混合/循环/插帧/补帧/变速。
- latent[1,16,24,54,96]；真实clean KV48层96个BF16文件，每层[1,32,5184,128]，共4,076,863,488字节。
- 无LoRA/quantization/compile/FFN切块/math attention回退；原映射驻留/VAE71卷积空闲缓存释放保持。

## Evidence Already Complete

- **M native15**：三窗各一次成功，253帧/15fps/253/15秒、raw逐像素一致、历史一次输出。两续窗KV各48层/4,907,335,680字节及所有artifact完整SHA核验。M/three-window-integrity.json、native15-research-assessment.json、chain-003/dynamic-review.json保持；整链review SHA d31def417863db56f4f9e1487820f364ba66ecd6994c8ae2f9de80033a7dda43。接受不外推16fps/任意长度。
- **Q失败**：首窗14/50被commit_reserve停止，worker8684退出1、1225.063秒，无latent/sample-complete/媒体。原27源/intent保持；Q/trial-001/window-001/failure-observation.json。原监督器没保存触发瞬间具体commit，不能把最后一秒15.5GB当停止值。事后系统commit限额约35.49GB、当前Job无内存配额；不能归因特定应用。
- **C修复**：相对Q仅4执行源改变allocator选择/准入绑定与原停止资源快照；其余23源含11官方源未改。随机官方FFN两allocator输出逐字节SHA相同，仅机制证据。backend/错backend拒绝/原stop样本留证均RED→GREEN。
- C完整五阶段probe session3407退出0、约211.2秒；最低commit6,267,060,224/物理13,692,510,208字节；peak reserved8,187,281,408（Q13,281,263,616）。layout和final-admission退出0。
- 独立review唯一Important：layout先import torch。真实RED3989d682→Python启动前设两allocator环境后GREEN1d103b20，冻结27源未改。所有C先导入Torch入口用wrapper显式-AllocatorBackend cudaMallocAsync。
- C/proposal.json、candidate.patch、实际资源/布局/准入/缓存/失败血缘保持。仅退出后的预检KV scratch逐SHA释放，各4,076,863,488字节；实际窗口KV/模型/媒体不删。

## Historical Continuation Instructions (superseded by current snapshot)

1. 四窗verify/static/assemble和verify_chain_integrity均完成，不重做、不重采样。真实用户答复已消费并绑定当前result/viewing SHA，完整新动态接受已记录，不再询问。
2. 监测当前CPU回归14148及其真实子进程/日志/终态，保留751已验证前缀。原4375列表不包含已完成前缀；当前仅collect4375，尚无通过结论。中断时只从完整`-vv`节点结果取证，不从tmp/current-test推造PASS。
3. 当前CPU退出后，按`VCO-08-production-native16-design.md`与`VCO-08-production-native16-plan.md`实施Tasks1..7；资格所有前置已通过，计划已补齐，尚未开始生产源码。用户已授权直接推进，无需再逐步确认。
4. 完成生产mode/协议/准入/事务/修订/媒体消费者及真实验证；未来产品变更依影响补充最终回归，不能借当前旧源码结果宣布新功能通过。**尚未实现temporal_extension_v1，任务未完成。**

## Software Regression: Preserve the Exact Prefix

- 原collection两次5127节点、520源一致。原完整批次调度中断后精确752项：751 PASS、1 FAIL；4375未完成。M/regression-resume-manifest.json、regression-checkpoint-boundary-proof.json保持。
- 唯一timeout故障真实RED95.31秒：production无时限覆盖旧测试注入。仅修目标测试临时patch processes.command_timeout，真实编码器/timeout、日志/终态/原片不变/UUID不重试保持；5项GREEN139.56秒，日志test-70fb977d06c14ee491ec4839fba34ce2。
- M/regression-resume-source-proof.json证明519源码字节未变，唯一测试块还原后SHA匹配原快照。不机械重跑751前缀。
- 4375批次session33919/worker41072/launcher28172在会话中断后消失，无完成标记/终态。M/regression-remaining-interruption.json保留；不能从tmp或current-test诊断marker推造PASS。不等待旧33919、不在GPU时重启测试。
- 未解决4375节点仍在M/regression-remaining-nodeids.txt，SHA6d2a340b343b5110faeafa6507a37529e6b71c10e766255691ef2a954b9ef8a4。收尾用受控wrapper及精确列表，优先逐节点完整行输出以便中断取证。未来产品变更按影响补充最终验证。

## Execution

- 只写repo与D:/VideoSi；.git只读，不reset/stage/commit/worktree，不关用户应用/改pagefile。
- 当前PowerShell脚本受默认策略限制，使用进程级powershell.exe -NoProfile -ExecutionPolicy Bypass -File C/run_research_script.ps1；不改系统执行策略。wrapper内仍走项目bootstrap/Initialize/Invoke-VideoAiNative。
- stdlib用$VideoAiPython3.12；Torch/numpy/av/psutil用既有嵌入式3.13。嵌入式helper必须显式加脚本根sys.path。
- C Torch入口用-Embedded -AllocatorBackend cudaMallocAsync；-Stage N/-Windows N转发参数。supervisor是stdlib父进程，worker为冻结嵌入式入口。
- CPU测试/GPU串行；每≤60秒简报；读worker日志，避免无必要竞争progress.json。
- R/N/M/Q/C失败和实际banks/媒体/模型保留；M/closed-test-font-archive是既有可逆归档，不重做维护。
