# VCO-03 Verification

2026-10-26 isolated temporal replay supplement: completed90cases (72calibration/18new-check), sealed threshold0.7365891044951167 before one new-source check. TP9/FP0/TN6/FN0;3established-cycle negative abstentions,15/18 labeled coverage. Calibration denominator explicitly48labeled/72total;24label-unverified excluded.62targeted tests passed;6252displayed ROI frame hashes and90original case/receipt bindings verified read-only. One fresh review's3Important findings resolved by additive certificate guards and explicit denominators/cluster limitations, with no detector rerun. Original16software files and16prior core artifacts unchanged; no production/VCO-04. [Evidence and scope](../task-handoffs/VCO-03-temporal-replay-results.md). Original formal benchmark boundary below remains separate.

## Status and boundary

Current task status (2026-10-26 reconciliation): COMPLETED under the user-selected AI experimental route. Software, all six experimental evidence channels and the temporal replay supplement are delivered; the main design's current Acceptance and task board now use that route. The original two-human real-benchmark protocol remains unaccepted and experimental profiles remain ineligible for production; these limitations no longer leave the current AI task BLOCKED. Earlier blocked snapshots below are historical.

The user requested implementation on 2026-10-24. Design: `docs/task-designs/VCO-03-design.md`; plan: `docs/task-designs/VCO-03-plan.md`. Source production interfaces, original VCO-02 artifacts and the original JIM-08 acceptance are not changed. `.git` is read-only; all changes remain in the working tree.

Only targeted checks run. The user deferred full regression to VCO-08/project closeout. No GPU/service/model generation, media collection or production approval is part of these checks.

## Dependency installation

Bootstrap command: dot-source `scripts/bootstrap.ps1`, initialize `vco03-dependencies`, then invoke the configured D:/VideoSi Python with `-B -m pip install -e .[dev,continuity]`.

- Exit 0: NumPy 2.2.6 and opencv-python-headless 4.12.0.88 installed under `D:/VideoSi/envs/video-ai`.
- Log: `D:/VideoSi/cache/video-ai/logs/vco03-dependencies-eb252ac7115f47398399b02621f9d6b8.log`.
- Base project dependencies remain empty; numerical imports occur only in diagnostic calls.

## RED/GREEN evidence

All pytest commands use bootstrap, `-B -m pytest`, and independent cache/basetemp directories under D:/VideoSi/cache/video-ai/temp.

| Scope | Result | Log |
|---|---|---|
| Reader interface/read-only/forgery RED | 7 failed for missing reader | `vco03-reader-red-5e021828964c442eb5b36dc39ce6b066.log` |
| Colorimetry unit GREEN | 39 passed, exit 0 | `vco03-reader-green-cf4a3009ad1d4972a09ba0d76875800c.log` |
| Measurement RED | 8 failed for missing analyzer | `vco03-measure-red-ec513a6962684b6380be99fa1af38b2f.log` |
| Measurement GREEN | 8 passed, exit 0 | `vco03-measure-green-de5eee0915a647ee89b8a17f6f283568.log` |
| Audit interface/profile RED | 2 failed for missing functions | `vco03-audit-red-982bd4267e8d43a49bf80bbf6b3797b0.log` |
| Calibration RED | 5 failed for missing calibration | `vco03-calibration-red-f5f47de9300e41e29412c1f42790a910.log` |
| Analyzer + calibration GREEN | 15 passed, exit 0 | `vco03-math-green-675da2da0f1740f1b214bdfa3f93b3e7.log` |
| Real CPU integration first attempt | 2 failed; fixture encoder omitted primaries/transfer from actual stream | `vco03-integration-first-dd751a26e1d44e0c988544adb6b4a3f2.log` |
| Real CPU integration after explicit x264 VUI | 3 passed, exit 0 | `vco03-integration-green-29ff31cfef604df3a080f0e75807261e.log` |
| Formula/geometry/context and literal six-score checks | 13 passed, exit 0 | `vco03-scores-404f9dde443a4defbb5cb424fe3bc006.log` |
| Ten control variants, source/display times, truth JSON isolation | 1 passed, exit 0 | `vco03-controls-658c9bc965804574b3bb08913ca37cba.log` |
| Small end-to-end calibration | 1 passed, 20 fixture_only cases, profile unverified, exit 0 | `vco03-calibration-smoke-27f3e2de23e24000a8a6cc82081fd001.log` |
| Independent-review regressions | 4 failed: empty-metrics enabled profile, future anchor, fps mismatch, unknown global join | `vco03-review-red-71b8bb6986fd436d83d57066873799f1.log` |
| Oversized original probe regression | 1 failed: original JSON bypassed reader size bound | `vco03-resource-red-2ba30d513ee74c3887fb0ae0315b9e46.log` |

All log names above are relative to `D:/VideoSi/cache/video-ai/logs/`. Later passing evidence must supersede each review regression before software is reported complete.

## Independent review and fix pass

Read-only independent review: `D:/VideoSi/cache/video-ai/temp/vco03-review/review.md`; complete source snapshot: adjacent `source-package.txt`. The reviewer found eight Important issues and four Minor issues. The review did not rerun broad tests or change the checkout.

The fix pass rejects future ordinary anchors and unproved cross-clip output adjacency, checks source timing against declared output fps, gates profile applicability on native source fps, validates profile evidence against frozen catalogs/labels/sealed thresholds/case results/evaluation, and claims evidenced media ancestry across both splits before fitting. It bounds original JSON regardless of extension, checks score deadlines, uses one bounded exact slope buffer, counts comparison metadata incrementally, keeps fractional flow centers until final original-pixel nearest sampling, and packs truth masks before measurement. A call-local grayscale LRU and lazy numerical import cache avoid repeated work without retaining full-resolution pixels.

Three reviewer Minor findings were treated as Important because their effects violate explicit evidence/reproducibility requirements: dependency RECORD redirection/empty inventories, audit-output-dependent numerical digests, and calibration predictions missing sealed thresholds. They are included in this fix pass. The remaining Minor finding is deferred: the same-frame identity shortcut is conservative for two distinct persisted records of an otherwise equivalent spatial source; it can abstain on a uniform region rather than exploit all permitted spatial identity proofs. It cannot turn an unknown spatial transform into comparable evidence.

Additional RED logs: `vco03-mask-red-c80d2743a36c4d00ae63917cb746d9a2.log`, `vco03-lineage-red-2afdec9bae8d49ef8130aff524e309c2.log`, `vco03-audit-integrity-red-9c9634eb56014212a219320395504e8e.log`, and corrected inventory RED `vco03-inventory-red-2d62eb75fe6043c39acd3105ac8b1b90.log`. The first inventory probe failed inside its test setup because the dependency mock preceded numerical initialization; the corrected probe reached the intended missing-inventory boundary.

First fix verification: 65 passed and 1 failed (`vco03-review-green-unit-fd89f1daf8644abfbf92c2f8aa7a68ae.log`); the remaining oversized-probe failure identified that FFmpeg stdout JSON uses a `.log` name. After routing original JSON reads through the bounded reader independently of extension, all 66 unit checks passed, exit 0 (`vco03-review-green-unit2-9e1e27785fdf4be294e89a2fd694f8bb.log`).

Reviewer boundary decisions: real benchmark acceptance remains incomplete; full regression remains deferred as instructed; production integration/correction/inference stays outside this task; the approved unsigned local evidence format provides consistency/drift checks rather than external authentication; undisclosed rights/ancestry cannot be inferred from pixels, while evidenced shared ancestry is rejected across scene groups.

The first complete five-file targeted run produced **96 passed, 1 failed**, exit 1, in 252.71s (`vco03-targeted-a2136efd452643a6b396d1b487e02dea.log`). The failing `test_fixture_calibration_seals_thresholds_before_holdout_and_stays_unverified` showed that profile revalidation accumulated the bytes of already released sequential case geometries in its live metadata budget. The fix releases those documents after extracting compact score rows and restores the caller's budget on exit. The calibration-only fitter spy is restored before the independent evidence verifier rechecks the frozen calibration scores; this verifier does not compute holdout measurements or tune thresholds.

Shared geometry deadline/preallocation regressions RED: `vco03-geometry-budget-red-e12e1e22b37e435fa656af7ef34dd298.log`. Geometry + complete fixture calibration/evidence verification GREEN: **3 passed**, exit 0, 50.48s (`vco03-fix-green-focused-044d19f3d85a4b9f8dbd95ac4904e842.log`). Actual native source-fps/PNG reference provenance RED: `vco03-native-fps-red-1e980c970f244bec9615e27e712b2018.log`.

The next complete five-file run produced **100 passed**, exit 0, 253.27s (`vco03-final-targeted-12f3da30dd00441ba7339266cba2111b.log`). A final resource-accounting check then added a conservative preallocation guard for packed truth masks plus simultaneously live RGB/float warp intermediates; its RED is `vco03-control-peak-red-2ff9071bf4b74785b902f98ea0bde56b.log`. The last five-file run includes that guard and has 101 collected cases; its final result is recorded below after completion.

## Exact final targeted invocation

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco03-release-targeted'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest','-v',
 'tests/unit/test_continuity_analysis.py','tests/unit/test_continuity_calibration.py',
 'tests/integration/test_continuity_analysis_flow.py','tests/unit/test_colorimetry.py',
 'tests/integration/test_colorimetry_flow.py',
 '-o',"cache_dir=D:/VideoSi/cache/video-ai/temp/vco03-cache-$VideoAiCommandId",
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco03-release-$VideoAiCommandId")
exit $VideoAiExitCode
```

Final source/test/script/pyproject snapshot before that invocation: `D:/VideoSi/cache/video-ai/temp/vco03-release-source-identities.json`. Full regression was not run. Source/audit invariance checks are in the real flow tests; numerical dependencies and algorithm file identities are also frozen in each independent continuity audit.

**Final result: 101 passed in 252.66s, exit 0.** Log: `D:/VideoSi/cache/video-ai/logs/vco03-release-targeted-8dbed14b3f6c4c00a03a67c3b554f404.log`. After completion all **16/16** frozen files matched bytes, last-write timestamp and SHA256; `git diff --check` passed. No source/test/script change followed this run.

**Task state:** `IN_PROGRESS -> BLOCKED`, after writing the pause handoff at `docs/task-handoffs/VCO-03-handoff.md`. Software checks are delivered; real corpus/annotations/evaluation remain missing. This is not COMPLETED and does not prepare VCO-04.

## Public-source preparation follow-up

User authorization: “你来寻找吧”, after delegating material preparation. Network discovery/download of explicitly licensed public videos is now authorized; human viewing, accurate labels and outcome acceptance are unchanged.

- Candidate inventory: `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/public-source-candidates.json` and `.csv`, 24 candidates / 6 genres / 4 each; proposed 12/12 split is not frozen. Twenty ISO Republic pages each explicitly state CC0; animation projects retain their separate CC-BY/CC-BY-SA attribution and modification terms. Primary-page and license evidence are preserved under the adjacent provenance directory. Distinct source pages are not yet a proof of independent media lineage.
- Three complete public-mirror ZIP downloads with CRC-checked MP4 extraction and SHA receipts: Big Buck Bunny (276134947-byte MP4, SHA `ae51005850b0ff757fe60c3dd7a12d754d3cd2397d87d939b55235e457f97658`); Elephants Dream teaser (30639218-byte MP4, SHA `5fe4e42a4c6893f40c90d841ac3e638d7b68d31b04d4a91f22b2bb5071d8c2d6`); Caminandes (125974946-byte MP4, SHA `468e6743c674689a728726bbe4bb4b2a65bd8702a89f021af26a8bb4d450eebd`). Logs: `vco03-download-open-movie-89f9e901bbf7436d8a97050ae88e2d6c.log` and `vco03-download-animation-sources-3940a03c920341f2b9ca85c1da48788e.log` under the established cache logs directory.
- Header/preview audit: `D:/VideoSi/projects/video-ai/runs/20261024-124328-6c958ad48e17`; ordinary JPEG previews at explicitly recorded decode indices 0/300/600/900 are marked preview-only, not common-space analysis or full-video watching. Big Buck Bunny has no stream color declarations; Elephants Dream lacks primaries and uses an unsupported transfer/matrix combination; neither is admitted by assuming Rec.709. Caminandes declares bt709/bt709/bt709/tv at native 24fps.
- Real color preparation audit: `D:/VideoSi/projects/video-ai/runs/20261024-124505-baf05a594401`; `colorimetry/public_caminandes/sidecar.json` is resolved. Actual decoded frame 300 is ready in srgb_rgb24_v1, 6220800 bytes, native PTS 300000 and time_base 1/24000. The actual `load_color_analysis_set` context read/exit check passed and source size/mtime/SHA stayed unchanged. Log: `vco03-public-real-frame-6a972daa4beb4853b5308da63b225871.log`. Exact frame identity and limits are in `caminandes-one-frame-preparation.json` in the candidate directory.
- A first preview attempt failed because its new output directory did not yet exist; the helper was corrected and rerun in a fresh independent audit. Log: `vco03-source-inspection-fixed-01154c7944854fddba380af0d30e7ef6.log`. Source data and repository implementation were not modified.
- Network limitations: native ISO Republic HTTPS and redirected HTTP access timed out; successful foreground downloads used the public Blender mirror. An optional background timeout-helper launch was automatically rejected with “blocked by policy”; it was not used, and ordinary foreground native commands provided the successful download alternative. Pexels was not selected for automated collection; its current service terms restrict that use.

These are discovery and partial preparation results: **24 candidates, 3 downloaded sources, 1 verified analysis frame, 0 complete four-second sources with reviewed ROI/truth, 0 constructed corpus control cases, 0 human reviews, 0 real calibration profiles**. No production code changed, no pytest rerun was needed for this data-only follow-up, and the task remains BLOCKED rather than COMPLETED.

Final curation verification: `D:/VideoSi/cache/video-ai/logs/vco03-curation-verification-c512b66f26ad4cb088fb0f9911b78208.log`, with structured result `curation-verification.json` in the candidate directory. JSON/CSV both have 24 unique slots, each of six genres has four candidates; all three downloaded MP4 SHAs and the ready frame record/raw SHA match their receipts; 16/16 frozen implementation files remain unchanged; git diff --check passed. The draft intake has been filled with candidate source pages and the three actual local paths; its source selection and split remain unfrozen and it is not passed to the calibration API as a real catalog.

## Acceptance evidence and outstanding inputs

- CPU fixtures use explicitly tagged 64x36 2fps eight-frame H.264, one sRGB PNG, exact original PTS and output mapping, independent new audits, and source-run/audit bytes/mtime/SHA comparison.
- These are software fixtures. Synthetic observer IDs and labels used in fixture_only tests are not human playback evidence.
- Real catalog, 24 independent sources across six genres, 240 human-reviewed controls, two independent complete-playback labels plus adjudication, and six ready real-benchmark detector evaluations have not been supplied or run. The user has been asked for explicit catalog/labels paths.
- No numerical threshold, accuracy, real cross-genre validity, complete dynamic viewing or video-quality pass is claimed.
- VCO-03 cannot transition to COMPLETED until both software checks and the design's real calibration acceptance are established. VCO-04 is not prepared from incomplete outputs.

## Remaining-checklist data execution (2026-10-24)

The explicitly requested data continuation reuses the delivered implementation and old assets. No production code, tests, dependencies or production configuration changed, and pytest was not rerun. This does not replace the historical 101-test software evidence or real acceptance.

- Inventory: 11 downloaded versions from 10 project sources pending lineage confirmation; the second BBB is the same project. Three additional MP4 remuxes retain the WebM originals and have matching compressed video packet hashes, decoded native PTS/time_base, nominal FPS, dimensions and color fields. Different container-derived average-rate headers are recorded, with no FPS/color override. Five unknown, one unsupported and one conflicting project sources remain unadmitted; only Caminandes, the frog source and the CC0 speaker source have resolved supported color.
- Selected complete native intervals: Caminandes frames [240,336), PTS [240000,336000) at 1/24000; frog frames [240,360), PTS [8008,12012) at 1/1000; CC0 speaker frames [120,216), PTS [240240,432432) at 1/48000. All 312 frames were actually converted through existing VCO-02 APIs. Rejected exploratory intervals and their evidence remain separate: Caminandes cut 346->347, frog title card [0,120), and frog cut 363->364 in the earlier [270,390) proposal.
- Review material: 10 full original-interval playback copies, 1,105 native-index review frames, 2,210 unsigned ROI rows, separate unsigned truth/initial anchors, lineage/unfrozen split/attribution records, 240 reused pending case IDs, and two blank 2,880-row reviewer sheets. Actual constructed controls, genuine human reviews, calibration profiles and holdout evaluations are all zero. Playback rasters are review-only, not color analysis evidence.
- Final bootstrap invocation: `D:/VideoSi/envs/video-ai/Scripts/python.exe -B D:/VideoSi/cache/video-ai/temp/vco03_verify_remaining.py`; **exit 0**. Log: `D:/VideoSi/cache/video-ai/logs/vco03-remaining-complete-inventory-verification-9b0351c5031d4981b8156386abf1e4c7.log`. Verified 523 ready analysis records / 522 distinct native source frames (including rejected/exploratory frames and the duplicate old frame-300 evidence), all actual RGB lengths/SHA and reader exit closure; 16/16 frozen software files and three old media remain unchanged. Selected review frames/PTS, MP4 frame counts, unsigned drafts, blank labels, 240 original case IDs and local HTML links were checked. Observed completed preparation commands remained below 300 seconds (maximum approximately 230.5 seconds); calibration was not invoked.
- Structured evidence: `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/remaining-verification.json`, adjacent `commands-index.json` and `review-package/package-identities.json`. Progress is the candidate directory's `remaining-progress.json`; complete delivery and human instructions are linked from `docs/task-handoffs/VCO-03-remaining-delivery.md`.

The 24-source requirement remains unmet: 21 further/replacement color-ready intervals are needed, in addition to genuine content/lineage/ROI confirmation and subsequent dual control viewing. No formal catalog or labels, split freeze, threshold fitting, holdout evaluation or VCO-04 start is claimed. Task status remains BLOCKED without a state transition.


## Manual-download follow-up verification (2026-10-24)

2026-10-24 手动下载续办：21/21 请求文件完整解码；18 个新来源颜色 resolved，已完成 2,172 个连续原生 ready 帧。复用旧三段 312 帧后，共 21 段 / 2,484 个完整 ready 原生帧。31 个待确认项目来源共 3,593 帧播放/逐帧材料、7,186 行未签署 ROI；240 个原有 case 位置保留，实际 ROI 确认/控制/真人审阅/评估均为 0。

拟用 24 个位置已有 20 个颜色/原生帧就绪：people 4、animals 4、transport 4、outdoor 3、indoor 4、animation 1；另有一段人物备用。至少还缺 outdoor 1、animation 3，内容/独立血缘未确认还可能增加替换需求。Spring 和狗缺必要颜色声明，黄花现有解释不受支持；不得补猜 Rec.709。

All 21 supplied final downloads passed complete video decoding. Native VCO-02 interpretation admitted 18, rejected dog/Spring as unknown and flowers as unsupported. User-confirmed office alias is explicitly not human playback or ROI evidence. Original Spring and packet-copy MP4 retain matching compressed video packet hashes, decoded PTS/timebase, nominal FPS, dimensions and stream/frame color; absent declarations remain absent.

Fresh verification reads all 2,172 new selected RGB frames and the 312 reused old selected frames through load_color_analysis_set, verifies byte lengths/SHA and exit identities, as explicit bounded per-source command batches. Old sealed package 2,769 file identities and all 16 released implementation identities are unchanged. The 31-source review version contains 3,593 frame rows, 7,186 unsigned ROI rows, separate truth/clip anchors, original 240 case IDs and two blank 2,880-row label forms, with offline links checked. Construction/human reviews/profiles/holdout remain zero. No production source/tests/dependencies/config mutation, pytest rerun or VCO-04 start.

Artifacts: `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/followup-verification.json`, per-source `verification/`, `commands-index.json`, and `review-package/package-identities.json`. Exact bootstrap commands and exit codes are indexed in commands-index; verifier script is `D:/VideoSi/cache/video-ai/temp/vco03_verify_manual_followup.py`, operations `manual START END`, `baseline`, `package`. Current data snapshot is `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/followup-progress.json`; old baseline proof remains separate. Four new licensed alternative-source transfers failed within bounded attempts and are not counted as downloads. This is preparation evidence, not real benchmark acceptance; task remains BLOCKED.


用户内容反馈更新：用户表示“我认为里面的视频都没有问题”。按上一轮明确要求的20段拟用ready视频范围，已登记内容接受意见；原话、范围解释、片段身份在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/user-content-feedback.json`。没有据此补签完整播放区间、逐帧ROI、独立血缘或双人控制标签。下一步集中核对入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/roi-review.html`（20段、2,388帧/4,776行框草稿）。原封存审阅包不变，ROI确认/控制/评估计数仍为0，VCO-03保持BLOCKED。


2026-10-24 用户最新版ROI确认后的更新：用户表示“全部看完了 现在没问题了”，已按此前明确的20段最新版逐帧材料登记接受，实际作者标识conversation_user，reviewed_at使用该确认接收时间并在凭据解释；不虚构姓名、第二审阅者或控制观看。对应2,388帧/4,776行ROI已生成独立精确schema的regions/truth，使用两项最新修订覆盖路径。

已通过既有build_control_case/ControlProvider和真实VCO-02 reader构造这20源的200个控制（总240位置仍缺40），共23,880个实验显示帧，保留原生/实验两套时间、recipe、原帧身份、每帧控制RGB摘要、原尺寸padding mask及完整播放/逐帧材料。全部播放N与每帧PTS逐一核对；另对每case首/中/末帧实际重构RGB及padding，共600帧，核对PNG与原生控制缩图。未使用普通manifest冒充重播；原片/原分析记录不改。

新双人待审入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/review-package/index.html`；独立A/B空表、裁定表、240位置与200真实播放路径在该目录。两份表各2,880行，其中2,400行为已构造待观看、480行未构造不得填。尚无任何真人控制标签；variant名称不签出anomaly/normal。

验证：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/control-delivery-verification.json`，逐源verification/与sealed-case-identities/保存闭包。原两版封存审阅包合计8785文件与16/16冻结软件身份未变；未重跑pytest。审阅编码试运行曾因-r与passthrough冲突、concat微秒逐段取整漂移而拒绝，已保留失败audit；使用累计边界微秒差和原生tick末帧duration，严格复核所有PTS后才登记构造成功。校验脚本曾误比较FileIdentity的verified_at观测时间，改为既有稳定身份比较；大小/mtime/SHA仍严格核对。

总体仍BLOCKED：至少还缺1户外/3动画可用来源，独立血缘与12/12 split尚未确认/冻结；两位真人需独立完整观看原区间及真实变体并逐region/detector填标签，分歧由第三位真人裁定。另外已实际发现青蛙原片的1/1000时基有33/34步长，当前校准入口仅接收恒定步长；此兼容问题单列，不能靠改原PTS或跳过检查解决。本轮没有拟合/留出/真实profile，也不启动VCO-04。


控制审阅本轮反馈更新：用户表示“其他的没问题了”。已保留people_03的手部遮挡/钢笔色偏两项位置问题，以及20项allowed_lighting和熔岩灯两项drift的“不明显”观察；其余项目登记为未提出额外构造问题，不按variant或“没问题”自动写出normal/anomaly。汇总原话和范围解释：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/review-feedback/round-001-summary.json`。people_03两种操作的新选区已做100帧草稿，当前待用户确认：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/correction-drafts/people_03-targets-v3/index.html`；旧控制和正式truth尚未替换，须确认新区域后再重建受影响的控制。没有第二位审阅者、完整case/region/detector标签或裁定记录；当前仍不校准，BLOCKED不变。


2026-10-25 people_03修订更新：用户回复“这次可以了”，已将最新版v5选区接受意见与版本身份独立登记（接受范围按对话解释，不补造额外原片观看、case标签或第二人）。正式手部/钢笔/背景三类区域与100帧真值已分别保存；钢笔使用已接受的原尺寸mask。

新版本 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002` 复用190个旧控制，重建people_03的10个；其中两项按用户明确目标分别选择hand遮挡、pen局部色偏。仍使用既有verified reader、build_control_case和ControlProvider，在像素生成前显式记录recipe.local_region_ids选择；未改生产源码/算法幅度。全部100帧检查色偏在钢笔mask之外像素不变、遮挡严格符合手框上半部规则；其余8类800帧原生控制RGB与旧版逐一完全相同。10类又独立重算30帧RGB/PNG/padding，播放帧数与所有原生实验PTS通过。

请从 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/people03-corrected.html` 直接查看修订的两项；完整200控制新入口是 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/index.html`。其他来源和旧版均保留，不重计成210个case。手/笔独立region后，正式ROI为4,876行，双人空表各2,940行（2,460行已构造待审，480行未构造）。没有将“其他没问题”写成normal/anomaly，实际双人标签与校准均0。

新校准兼容限制必须保留：当前校准循环默认选择所有subject区域，还不会重放这两项用户指定的目标子集。对应选择、输入和构造器适配器已存 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/calibration-target-replay-requirements.json`，正式校准前须支持并验证精确重放，不能用默认的双subject构造替代本次已审阅的两项。此前青蛙33/34毫秒步长、4个来源缺口、血缘/split、独立双人标签与裁定依赖仍在，任务保持BLOCKED，无留出或VCO-04启动。数据辅助脚本改变不影响16/16冻结实现身份，未重跑pytest。

验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/correction-delivery-verification.json`；日志/退出码见同级commands-index.json。最新进度已写回S/remaining-progress.json。


2026-10-25 修订材料接受：用户对刚交付的people_03手部遮挡/钢笔局部色偏两项新版回复“没问题”。已按实际控制文件及播放文件身份登记为作用位置/画面可接受，关闭本轮位置问题；原话在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-feedback/people03-corrected-material-acceptance.json`。此前22项弱可见性反馈与已解释的people_01现象继续保留。该意见没有扩写为case/region/detector的normal/anomaly标签，也未补造观看范围/时间、第二位真人或裁定。下一位真人独立审阅入口为 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/reviewer-b.html`，B表仍为空。本轮画面与位置反馈已汇总；正式标签、其余素材/血缘/split、时间兼容及目标选择重放仍未齐，VCO-03保持BLOCKED，无校准。


### 2026-10-25 继续任务：校准兼容修复与集中材料

用户要求“继续任务啊”。本轮复用已确认素材/ROI/200个控制，修复青蛙33/34ms原生PTS被等间隔门槛误拒、已接受的挡手/钢笔变色不能由正式校准重放的问题。catalog source可选control_targets绑定真实授权及subject ID并参与corpus SHA；profile复核也直接核对原区域身份和原生时序，拒绝修改后重新计算身份的控制时间/角色。参数、变换幅度、原媒体与已审材料保持原样。

最终五文件检查106 passed，退出0，日志 `D:/VideoSi/cache/video-ai/logs/vco03-compatibility-final-targeted-458c8400d9774061a402c853099cf89c.log`；初始5项RED及profile篡改链RED均有记录，修复后GREEN。实际20源/2,388帧原生区间核验通过；people03全部10变体/1,000帧正式构造器RGB及padding与既有材料一致。封存审阅材料/控制共39,207个唯一文件身份未变；历史16软件身份中5个按本修复改变，其余11个保持一致，新快照在本轮目录，旧快照保留。独立审查的一项Important已按RED/GREEN修复；一项Minor保留：普通profile适用域保守检查整片时步，区间外时步可能导致弃权。未运行全库、真实拟合或留出。

新增候选下载3项中途/握手超时、1项403，均留有限尝试证据；未把partial计为下载。仍缺1户外/3动画。集中入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/index.html`；补缺下载入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/manual-downloads-20261025-remaining/download-links.html`；兼容20源清单 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/final-code-verification/prepared-sources.compatible.partial.json`；验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/continuation-verification.json`；命令/退出码 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/commands-index.json`。已审位置意见不需重复确认；正式A/B逐case-region-detector独立标签仍为0，独立血缘及12/12分组未冻结，真实profile为0。VCO-03仍BLOCKED，VCO-04不启动。


### 2026-10-25 已交两表与后续AI审核

用户先后报告akkc/qzw已填完，并明确“后面的视频我也都让ai审核”。已保留两份提交副本并核对2460行/200控制：结构错误均0，标签相同940、不同1520，双方viewed_at各缺2460。akkc原证据标为AI代填建议，qzw为整体未发现异常反馈转录，故不把表格差异自动记作已验证真人分歧，也不伪造观看时间、裁定或正式标签。接收/差异证据 `D:\VideoSi\projects\video-ai\continuity-benchmark\public-sourcing-725743bd99ca43f79aa47a85010ce0e7\remaining-work\manual-intake-20261024\replacement-manual-intake-20261025\received-reviews-7db6c87e6fe5\submission-verification.json`。

新增4文件全部完整解码且颜色resolved，各120原生帧共480帧，经原VCO-02 reader与_source_timing复核，完整播放N及每帧PTS全核对；新增960条AI选区草稿保持author=null/confirmed=false。AI检查首尾联系表及概览；星空/光斑未建立可靠同体/背景身份，工具黑背景缺纹理，不能据技术就绪保证正式校准适用性。24位置均有原生帧草案，但正式ROI仍20源、控制仍200/240，来源独立血缘/split仍未冻结。AI入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review.html`；验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review-verification.json`。16项软件身份未变，未重跑既有106项测试；未拟合、未跑留出、未启动VCO-04，任务仍BLOCKED。


### 2026-10-25 原始诊断样例交付

用户同意继续完成带分数、定位和不可比原因的诊断报告。本轮只使用原计划校准侧people_02的10种已有控制，另补people_01的原样/运动重播/相机跳变3种，未改样本归组、未读取留出侧结果、未读取判断表参与计算。现有build_control_case/ColorAnalysisReader/measure_continuity实际计算13个控制、1,560显示帧（各另含1固定参考）、3,107完整比较，输出11,704条分数记录。每次命令<=300秒，校准/阈值拟合入口已在数据脚本中禁止。

为保留16MiB单文件上限，原始比较逐pair分块落盘，未删比较/降采样/修改参数。3,107块身份复核、39块指标摘要独立重算通过；16个软件文件身份保持。原样人物02背景仅覆盖全图3格，119时间比较均无相机支持；人物01原样40/119时间比较具备相机支持，保留其它弃权，不把无分数当正常。六类分数已有可核对的对照，但无异常阈值、无准确率/真人验收通过。

HTML含并排原样/变体、区域与比较类型选择、同来源同项目一致纵轴、曲线点/峰值显示时间定位及算法轨迹框；Markdown、CSV、SVG可独立查看。浏览器两次无头交互检查受本机图形/权限及超时限制未完成，未宣称通过；JS语法和本地资源另验。入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/index.html`；摘要 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/README.md`；证据 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/evidence-verification.json`；来源和命令 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/diagnostic-provenance.json`、`D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/commands-and-browser-status.json`。本轮为数据/报告，未改生产源码或重跑已有106项定向测试，未拟合、未跑留出、未启动VCO-04。VCO-03正式验收仍未完成，状态保持BLOCKED。

最终发布校验：13案例全部3,107块身份再核对、39块摘要重算通过；发布页面45个本地资源（去重计数以实际证据为准）、JS语法和SVG结构通过。最终凭据 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/delivery-final-check.json`。浏览器交互未自动验证的限制继续保留。


### 2026-10-25 背景覆盖改进试验

用户询问下一步后，继续对已定位的背景支持不足做独立AI输入试验：保留people_02原主体/背景，增补右侧沙发候选，仅提供clip起点/参考锚点；原样、重播、跳变各120帧重算。360控制RGB与旧材料一致，717比较中原两个区域1,434项色彩测量/可比性完全相同，16项软件身份未改。新支持数量和运动/相机分数见 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/README.md`，验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/experiment-verification.json`。

v1数据脚本因共享region_ids列表的重复追加触发资源保护，失败状态保留；v2按比较独立复制列表并验证无重复后成功，未放宽资源或算法阈值。新增框仍为AI候选，不替代正式ROI/真值，不改变原200控制或13个独特诊断case计数（共16次输入版本测量），不拟合/读留出/读标签。入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/index.html`；正式VCO-03仍未完成。


### 2026-10-25 背景试验边界核查与统计更正

新增背景后仅改善可测量性，尚未证明检测更准确。原样people02第60帧clip起点框与前段传播框中心相差约[-0.000543,-0.000293]，该重置位移进入速度；仅从保存的该帧速度扣除此分量，第60/61帧分数由75.9977/77.7987降为1.1613/1.7490。此为单变量敏感性复算，未修改生产算法，也不当作正式修复验收。

camera_jump真正发生的第60帧，原背景与AI背景均registration_failed，故相机/运动分数为空；第80帧峰值不能算定位成功。已更正试验表原camera_jump相机支持数为59/119（可用分数56条），不再误写0/119。下一自动工作先隔离跨clip锚点重置对运动测量的影响，再研究跳变处配准失败；只用原定校准侧，不读取留出或拟合阈值。用户暂不需重复观看/补表。

最新说明：[背景试验](D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/README.md)；逐帧核查 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/boundary-investigation.json`；最终身份核查 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/delivery-final-check.json`。原200控制、13独特诊断case、16项软件身份保持，正式VCO-03仍BLOCKED，未启动VCO-04。


### 2026-10-25 运动边界修复与背景支持复测（最新）

用户要求“继续处理吧”。`continuity_analysis.py` 当前帧对速度改由已通过匹配的左→右仿射作用于左框中心计算，clip起点anchor仍用于选区及后续跟踪，避免anchor重置进入运动速度。两项真实纹理回归先RED（静止误测0.64、平移误测-0.1102），修复后26项分析器单元检查GREEN。独立AI代码审查无Critical/Important问题，未冒充真人视频审阅。

同一people02校准侧、相同右侧AI背景输入复测：原样第60/61帧75.9977/77.7987降至1.1613/1.7490；重播48.6539/50.8001，实际图像变化仍保留。代码前后717比较/三区域2,151项匹配与颜色结果完全相同。原窗口背景跳变时仅10个点通过筛选、原右沙发仅2个，不降低12点门槛。

独立AI背景输入试验改用宽窗户与顶部植物/遮篷；从clip起点传播并使用相同匹配器，两区域跳变对最终13向量覆盖全图4格，C中119/119时间比较可估计相机。新增两个背景区域第60帧camera_jump均5852.9661，峰值第60帧；原样同帧3.5604。原背景本身该帧仍跟踪失败、分数为空，不能写成原区域已恢复。新区域是基于静态概览及有限支持探查调整的AI草稿，并非正式ROI或独立验证集；顶部植物独立运动及跨片背景身份仍待正式核验。原两区域1,434项颜色测量/可比性保持一致。

五个指定测试文件合计108 passed。首次合跑325.54秒超出300秒单命令预算，记录保留且不登记预算合规；随后按文件分成五次270秒硬超时的检查，各批结果/实际时长见commands-and-checks.json。未执行全库；未改匹配参数/阈值、源片、原200控制、正式ROI或判断表。16项软件身份中仅分析器和本单元测试改变，旧快照/旧依赖指纹保留；新测量在独立audit，旧profile不得复用。本轮新增6次测量，原始诊断累计22次、独特case仍13。

入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/motion-registration-fix-20261025/index.html`；说明 `.../README.md`；数值 `.../before-after.csv`；完整测量证据 `.../experiment-verification.json`；命令 `.../commands-and-checks.json`；新软件身份 `.../software-identities.json`；最终交付核查 `.../delivery-final-check.json`。这些省略号均指前述同一目录。

下一步仍以正式准入、独立血缘/12+12分组、可追溯标签和真实校准依赖为准；本轮只证实该校准侧样例的代码修复和测量支持，不宣称整体准确率通过。用户当前无需重复下载、观看或填表。VCO-03保持BLOCKED，VCO-04保持NOT_STARTED。


### 2026-10-25 校准输入依赖审计与40个待构造计划（最新）

用户要求继续任务。本轮只读复用24候选/2,868原生帧，四批各6源经既有ColorAnalysisReader、_source_timing和原始血缘提取核验，最长36.52秒，退出0；20源正式regions/truth通过schema及全帧覆盖检查，4源保持unsigned AI草稿。来源/作者/许可均已补入新24源CSV，包括原空表漏填的Caminandes/青蛙。已选24源未发现已验证媒体原始血缘跨源/跨split冲突，未据此宣称独立性已证实；原12+12位置分配与每题材2+2保持，未冻结。

全部200已有控制recipe及display_map长度与兼容20源输入一致。新副本显式复用兼容清单中的people03 control_targets（hand遮挡、pen改色）；原jobs仍指向无此字段的旧source.json，故新的重放绑定直接指向本批sources-20，避免再走默认全主体。旧源、控制和视频不覆盖。

新增4源的40个待构造计划已绑定实际120原生帧身份、官方_recipe、显示/原生双时间和clip边界；未调用构造器/测量器、未生成RGB或新ControlCase，实际控制仍200。20源部分catalog经过纯结构校验，但缺24源/独立血缘/冻结/正式标签，不能直接运行真实校准。软件16项身份保持，沿用108项定向通过记录，未重复pytest。

统一当前说明 `docs/task-handoffs/VCO-03-calibration-input-status.md`；入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/index.html`；全部证据、40计划、200重放绑定和来源CSV均在同目录，最终核验delivery-final-check.json。三类真实缺口集中为新增区域/真值、独立血缘与分组、正式审阅记录；保留AI来源，不伪造标签/时间/独立性，不要求重复下载或重填整套旧表。无拟合/留出/VCO-04，VCO-03状态保持BLOCKED。


### 2026-10-25 用户选择AI实验校准并完成（当前交付路线）

用户明确“ai校准的就可以，我不想填表格”，授权独立AI实验路线；设计 `docs/task-designs/VCO-03-AI-experiment.md`。已冻结24来源/12+12分组及2,940条AI弱标签，原表、真人ROI和正式benchmark协议分别保留；AI-only annotation没有冒充真人。当前不需要用户填写表格，旧人工依赖不阻塞本AI路线。

240控制位置均有结果：230完整测量、10固定metadata资源弃权；54,730完整比较、27,710含参考实验帧请求。120校准case结果齐备后只拟合一次，封存阈值身份后才算120检查case。4项有实验阈值：seam4.85805、local8.41253、drift8.41262、camera8.97361；累计/动作缺有效正常类，保持null。相机检查端到端召回28.6%，不隐去弱项。标签940 normal/133 anomaly/120 not_comparable/1747 unverified，新增4源480项全部unverified；不按recipe补造正负，不使用qzw整体normal转录作独立标签。

临时数据脚本初期一次reader超时和JSON格式膨胀拒绝均保留；紧凑分块不放宽16MiB/64MiB资源门槛。两帧缓存32次原生像素/掩码一致性通过；按码值LUT加速构造与原provider的5源/6变体/120帧原生像素/掩码逐字节相同，已有20源的后续快路径逐帧对照原控制RGB摘要。生产算法16项身份保持，不重跑已有108项软件检查。

独立AI代码审查提出“失败producer不能借新receipt获认证”和“检查侧须绑定封存阈值身份”两项Important；4项预期RED→5项GREEN（含有效receipt正例），原source失败产物隔离，合法续算保持原producer/输入摘要/依赖/闭包绑定。10资源失败仅从其原已闭合失败receipt派生空分数与弃权，不补造完整比较。

统一交付 `docs/task-handoffs/VCO-03-AI-calibration-results.md`；报告/实验profile/评估/CSV/冻结输入/最终核验均在 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025`。experimental-profile始终production_eligible=false，普通profile校验实际拒绝，没有启动VCO-04。原正式benchmark状态单独保留；本AI实验路线已完成，后续不再索要人工表。
