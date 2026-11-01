# VCO-06 implementation and verification

Implementation:2026-10-27; closeout:2026-10-28. Task board:`docs/task-handoffs/video-continuity-optimization-task-board.md`; contract:`VCO-06-design.md`; execution ledger:`VCO-06-plan.md`; operator entry:`VCO-06-operations.md`.

## Current outcome

The explicit, default-off `research_candidate_v1` implementation is present. It has pure bounded constant repair arithmetic, complete sealed-profile verification, immutable locked proposal/review/status transactions, independent ordinary reference/after reports, native master/viewing media checks, revision ancestry and explicit refusal at production origin boundaries. Original media and acceptance/rejection records are separate from research candidates. `production_ready` and the profile's production eligibility remain false.

**VCO-06 is not yet accepted as complete.** Real input selection and native/color/preservation checks were performed, but the selected actual original references have no supported sRGB declaration. The actual VCO-02 reference gate returned unknown/unverified with no usable RGB analysis pixels. The legacy original run also lacks a current explicitly frozen continuity epoch/assessment and repair Precheck. There is no valid natural repaired candidate or new complete playback observation. Details and exact media identities:`docs/task-handoffs/VCO-06-real-input-audit.md`.

The scoped software checks below include all 186 distinct focused cases (159 unit/calibration and 27 integration cases), collected across serial commands and corrected isolated reruns. This is not a claim that one combined command passed: the two fixture/assertion failures and their corrections are retained below. The six required legacy compatibility files completed with **178 passed,5755.44s,exit0,no skips**. In total,364 distinct scoped/compatibility cases have passing evidence. Expanded transaction checks precede the final archive target/temporary preflight fix; the current159 unit cases,4 real CPU/history cases and178 compatibility cases ran against the final frozen Python source.

## Implementation

- `media/color_repair.py`: frozen sRGB transfer/quantization, one constant parameter, qualified sealed sign/ceiling, stable noop, all-frame residual/clipping/no-regression/strict improvement rules; bounded arrays and restored numerical settings.
- `runtime/_scene_color_repair_profile.py`: exact profile/protocol/input/index/software/source/result/pack/seal/evaluation closure; bounded saved-control summary replay checks fitted declarations and holdout conclusions without refitting or new measurement; final byte rehash detects same-size/restored-mtime drift.
- `runtime/scene_color_repair_records.py` and `_scene_color_repair_validation.py`: exact schemas, actual playback precheck, retained original non-color/history refusal, epoch/current source closure, selected-reference byte-copy identity, candidate lineage, complete review coverage, sticky failed submissions and read-only status.
- `runtime/production_scene_color_repair.py`, `_scene_color_repair_engine.py` and `_scene_color_repair_media.py`: real RunLock, independent engine archive, exclusive immutable persistence, all reference frames including0, constant RGB streaming, fixed master/playback recipes, exact rational native mapping, complete decoded measured bodies, bounded full-frame/PNG processing and precommit validation of prospective success terminals.
- `scripts/scene_color_repair.py`: local propose/review/status only, explicit paths, no force/adopt/retry/model/publish branch. Four existing source guards reject research origins before production consumption.

All changes remain in the original local workspace; `.git` is read-only. No commit,push,publication,new backend installation or model/GPU request was performed. Existing unrelated uncommitted work is preserved.

## Executed verification

Every Python command begins `. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment '<label>'`. Pytest is invoked through `Invoke-VideoAiNative $VideoAiPython`, with `-B -m pytest`, an independent basetemp under `D:/VideoSi/cache/video-ai/temp/` and `-o cache_dir=D:/VideoSi/cache/video-ai/pytest`. Tests are serial. Full-repository regression remains deferred to VCO-08 by the recorded user instruction.

| Check | Actual result | Log under `D:/VideoSi/cache/video-ai/logs/` |
|---|---|---|
| Numerical/profile task initial and reviewed checks | Final111 passed:numeric57,profile31,existing calibration23 | `vco06-reviewed-core-final-a67983d8da154afc996e907c2ac3d015.log` |
| Formal r2 profile saved-control replay and complete closure | Passed:12004 Artifacts,12723957 parsed metadata bytes,105.11s; original4 qualified directions retained | `vco06-profile-reviewed-real-r2-6c5f78548174402cbd0eea55df0a0f6b.log` |
| Runtime media/review regressions | RED5 failures/8 passes→GREEN13; genuine foreign pair/after report substitution RED→GREEN, exact fixture terminal bytes restored | `vco06-runtime-review-red-e458d990c82846d497039d16d8e381d3.log`; `vco06-runtime-review-green-a1c5e475adf2486c9374ac4730c0985b.log` |
| Initial complete real CPU flow | 4 passed,271.74s; real FFmpeg,original ordinary assessment,independent selected reference,master/viewing media,after report,fixture-only review,noops and source guards | `vco06-flow-green-2b60751dd9d44c5d912a6610ab2c4fbb.log` |
| Initial recovery set | 10 passed,1042.00s; partial retention,no re-encode,new UUID/raw lineage,three-attempt cap,completed output recovery,sticky failure/current-epoch staleness | `vco06-recovery-first-f5838f92249f44c8a4caab2511cd3f18.log` |
| Final review regressions | RED15,including a genuinely invalid recovered fit which previously left an awaiting-review terminal; now fixed | `vco06-final-review-red-bd1b4eeabfb04c0aa784b42319e77972.log` |
| Larger reference/output metadata budget | RED2; both resource guards added before persistence/allocation | `vco06-resource-preflight-red-da80803e5210479086726a13b83a4f2b.log` |
| Current-source unit/calibration collection | **159 passed,22.97s**,exit0,no skips; includes numerical/profile/records/review/media/final guards/CLI/calibration, streaming PNG exact RGB+sRGB roundtrip, wrong-lock rejection and real Windows junction archive preflight | `vco06-closeout-unit-01dc75ce6ffb43c1b4f5281cd777e4ff.log` |
| Final real candidate and invalid-recovery positive checks | **2 passed,261.76s**; complete candidate review plus review-write interruptions; invalid recovery does not commit successful terminal | `vco06-final-positive-b22b327741da457c915d93395014648c.log` |
| Expanded transaction boundaries,explicit wrong lock,FFmpeg encoder failure/timeout | **23 passed,1 failed,2 deselected,1910.55s**,exit1. The intended-RGB assertion incorrectly required a master before encoding; corrected to require retained intended RGB and absent master. Its isolated rerun **passed**; the same rerun command initially failed both history fixtures because they overwrote the old frozen ROI | `vco06-final-flow-recovery-5329742d284b49ab9d8933e0a24ae46f.log`; `vco06-boundary-history-final-32ce3580146f49748eafba0331e3d95b.log` |
| Current-source genuine CPU candidate,invalid recovery,and historical original continuity responses | **4 passed,459.51s**,exit0. History fixtures now reuse the old frozen manifest/ROI; color-only risk permits research fitting and non-color risk remains blocked after a fresh precheck/new epoch. No identity validation weakened | `vco06-closeout-current-flows-b009e405ffc24289b2af8c8d46ffa167.log` |
| Archive alias regression | Controlled actual Windows junction RED proved a write through an alias before late refusal. Target and temporary canonical checks now occur before directory/file creation; GREEN included in the current159 | `vco06-archive-alias-red-0e675398ce6a4eb39eb8f61f46d81438.log`; current unit log above |
| Required legacy compatibility,exact six files | **178 passed,5755.44s**,exit0,no skips; includes the full public pipeline and continuity/revision recovery | `vco06-final-compat-7ffbc141c43842f99f13f5020f2e8822.log` |

Focused implementation reports retain additional exact RED/GREEN command arguments:`VCO-06-numeric-report.md`,`VCO-06-profile-report.md`,`VCO-06-media-final-fix.md`. The execution ledger records the corrected intended-RGB assertion; it does not conceal a product failure or mark the failed command passed.

The final command records below retain the exact pytest arguments used. Every referenced log also records executable,working directory,complete arguments and exit code. These were serial invocations through `Invoke-VideoAiNative $VideoAiPython`,after bootstrap and `Initialize-VideoAiEnvironment` with the matching label.

```text
vco06-closeout-unit:
-B -m pytest tests/unit/test_color_repair.py tests/unit/test_scene_color_repair_profile.py tests/unit/test_scene_color_repair_records.py tests/unit/test_scene_color_repair_review.py tests/unit/test_scene_color_repair_media.py tests/unit/test_scene_color_repair_final_guards.py tests/unit/test_scene_color_repair_cli.py tests/unit/test_scene_color_repair_archive.py tests/unit/test_vco06_repair_calibration.py -q --tb=short --basetemp D:/VideoSi/cache/video-ai/temp/vco06-closeout-unit-01dc75ce6ffb43c1b4f5281cd777e4ff -o cache_dir=D:/VideoSi/cache/video-ai/pytest

vco06-closeout-current-flows:
-B -m pytest tests/integration/test_scene_color_repair_flow.py::test_genuine_cpu_candidate_master_playback_reports_and_fixture_review tests/integration/test_scene_color_repair_recovery.py::test_bad_recovered_fit_never_commits_a_successful_terminal tests/integration/test_scene_color_repair_history.py -v --tb=short --basetemp D:/VideoSi/cache/video-ai/temp/vco06-closeout-current-flows-b009e405ffc24289b2af8c8d46ffa167 -o cache_dir=D:/VideoSi/cache/video-ai/pytest

vco06-final-compat:
-B -m pytest tests/unit/test_scene_clip_records.py tests/unit/test_scene_clip_observations.py tests/unit/test_scene_revision.py tests/integration/test_scene_revision_flow.py tests/integration/test_scene_pipeline_recovery.py tests/integration/test_scene_continuity_recovery.py -v --tb=short --basetemp D:/VideoSi/cache/video-ai/temp/vco06-final-compat-7ffbc141c43842f99f13f5020f2e8822 -o cache_dir=D:/VideoSi/cache/video-ai/pytest
```

## Review disposition

Fresh scoped reports:`VCO-06-numeric-profile-review.md`,`VCO-06-runtime-review.md`; fresh final report:`VCO-06-final-review.md`. All reported Important findings received fixes and regression coverage. No Critical or minor finding was reported. There was no second review presented as proof: RED/GREEN and actual CPU/closure checks establish the fixes.

The final fixes enforce retained original non-color failures even when a newer precheck is supplied; validate complete saved numerical/full-frame bodies instead of a passed flag; use chunked channel differences,explicit buffer lifetimes and streaming PNG; and verify a prospective success terminal before its immutable write. Additional preflight includes a larger independent reference and output JSON in the shared metadata budget. Failure terminals bind only their verified local producer bytes and do not claim a complete measured closure.

## Final identity and preservation

After all tests finished,the following commands ran serially through bootstrap and `Invoke-VideoAiNative $VideoAiPython`:

```text
Initialize-VideoAiEnvironment 'vco06-final-source-identity'
-B D:/VideoSi/cache/video-ai/temp/vco06_scope_identity.py verify D:/VideoSi/cache/video-ai/logs/vco06-final-scope-2d065b5de93840d7b91f71254e78d2cb.json

Initialize-VideoAiEnvironment 'vco06-final-original-preservation'
-B D:/VideoSi/cache/video-ai/temp/vco06_original_inventory_closeout.py

git diff --check
```

- **433/433 Python source/test/script files unchanged**,exit0. Result:`D:/VideoSi/cache/video-ai/logs/vco06-final-scope-2d065b5de93840d7b91f71254e78d2cb-verification.json`; log:`vco06-final-source-identity-482e3299eeff4de5aebd235baee79319.log`.
- **3011/3011 original run files unchanged**,including exact file set,bytes,SHA256 and mtime_ns; zero missing,extra or changed,exit0. Result:`D:/VideoSi/cache/video-ai/logs/vco06-original-closeout-61627cd9e494438fa9ff309d890f5232.json`; log:`vco06-final-original-preservation-2e6ca654d3c848079cf7243c7af221ff.log`.
- `git diff --check`:exit0; only existing LF/CRLF conversion notices. No Git mutation was performed.
- Original entry handoff archived byte-for-byte at `D:/VideoSi/cache/video-ai/logs/vco06-entry-handoff-62b39579eff143e0840650ada64dc3fb.md`,6737 bytes,SHA256 `357d35941e49b7d5cb4fc36ca20d1a908d3af78045538bc0e21a1c7b371a7f3e`.

## Acceptance mapping

1. **Software verified in focused checks:** request-only/default-off behavior,stable noop,unsupported/unqualified/context/identity refusal; research origin rejection and preserved original source lineage.
2. **Conditional numerical and tiny actual CPU media evidence exists:** exact native timing,all retained frames,one parameter,full-frame clipping/roundtrip checks and independently bound reports. These are controlled fixture-only samples,not natural-video success.
3. **Unverified:** actual natural light color improvement,material/motion/flicker preservation and complete actual original/candidate playback. No replacement of this requirement by static images,synthetic review text or software scores.
4. **Software verified:** independent immutable candidates and revisions,original raw/rejection preservation,local dependency invalidation,explicit production refusal,completed output reuse and raw restart; all required legacy compatibility cases passed.
5. **Partial:** all outcome limits,AI/oracle conditional scope,old non-blind holdout and `production_eligible=false` are preserved. Complete VCO-06 only after both software checks and the actual natural candidate/playback acceptance exist.

## Task disposition

**BLOCKED,not COMPLETED.** The design's Acceptance3 and5 require a genuine applicable natural candidate and complete actual playback. The selected egret and both alternative accepted first clips cannot supply the required proved-sRGB independent selected reference; the original run also lacks a current frozen assessment and actual repair Precheck. The real gate and original preservation evidence are in `docs/task-handoffs/VCO-06-real-input-audit.md`.

The pause/blocker handoff is `docs/task-handoffs/VCO-06-handoff.md`. Resume only after a qualifying natural source/reference and current diagnostic/precheck evidence are available,then complete the genuine candidate and actual playback acceptance. No successor preparation,full-suite run,new model/GPU request or actual production publication was performed. Full regression remains deferred to VCO-08.
