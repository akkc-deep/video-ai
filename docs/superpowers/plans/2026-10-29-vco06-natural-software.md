# VCO-06 Natural Software Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the remaining natural qualification/profile/candidate workflow without new model requests or fabricated natural labels.
**Architecture:** Add versioned consumers around existing frozen source, feature, statistics, conditional-profile and media primitives. Separate bounded per-case computation, immutable stage receipts and read-only verification; existing waiting/legacy paths stay unchanged.
**Tech Stack:** Existing Python3.12/NumPy/OpenCV/FFmpeg, no installs.
**Spec:** docs/task-designs/VCO-06-natural-software-design.md plus approved natural-input and qualification protocols.

## Global Constraints

- No GPU/model requests, additional sampling, Git writes, installs or production eligibility. Full suite remains VCO-08.
- Preserve all old frozen acquisition/pilot/feature/baseline/legacy modules and SHA; new CLI/module names carry the implementation.
- Single known axis/constant parameter, oldr2 direction/actual amplitude caps, full native16/F frames, all-frame geometry/support, no clipping and encoding roundtrip≤2.
- Actual16 observed cases remain developmental/unknown/negative/no-issue; never reclassify as qualified positives.
- Python always bootstrap→Initialize-VideoAiEnvironment→Invoke-VideoAiNative; tests and real operations serial; progress only every30minutes.

## Review Focus

1. Composite evidence forgery with refreshed JSON hashes: loaders must replay stage reductions and bind original independent freeze/producer/source identities.
2. Holdout leakage through input/status/loader before seal: opaque identity checks only until one sealed evaluation.
3. Unknown labels or late non-color failure overridden by a passing scalar: prechecks/history fail closed.
4. Encoded candidate diverging from intended fit: measure actual full decoded RGB, fixed coordinates, native mapping/last frame and no-clipping budget.
5. Interrupted stage/candidate changing UUID/input to hide failed results: keep original attempt, enforce stage order and three-attempt lineage.

### Task1 — Pure arithmetic and strict separation

Create media/natural_repair_engine.py and tests/unit/test_natural_repair_engine.py. Interfaces `fit_natural_parameter(frames,*,operation,conditional_profile)->dict`, `assess_natural_change(before,after,*,operation,thresholds)->dict`, `derive_natural_thresholds(cases,*,operation,direction)->dict` (last reduction may live in study records). No media/qualification authority from caller dictionaries.

- [x] RED: one known median-projection parameter; all-frame minimum81; unchanged support; original bounds/sign; neutral/no improvement/any-frame/off-axis/time regression; strict interval midpoint/missing4groups/unknown handling.
- [x] GREEN minimal functions; existing feature/statistics/oldengine unchanged; focused tests/logs.

### Task2 — Closed study records and actual per-case measurements

Create runtime/natural_study_records.py, natural_study_measure.py; tests/unit/test_natural_study_records.py and test_natural_study_measure.py. Interfaces freeze input validation, source/observation/manifest binding, software capture, immutable writes/locks, `measure_case(case,*,config,conditional_profile,out)->dict` with all-frame ordinary report, actual quantized control transforms and before/after features.

- [x] RED strict schemas, bool/NaN/time/path rejection, group/reference/video overlap, absent real files, no holdout label read, source/observation replay and historical failure preservation.
- [x] GREEN case-local budgets and original helpers; controls fixed before measurement, all failures retained.

### Task3 — Stage machine and profile validation

Create runtime/natural_study.py, natural_repair_profile.py, scripts/experiments/vco06_natural_study.py and unit/integration tests. Interfaces freeze/measure/seal/evaluate/finalize/status/check-inputs; profile loader matches approved signature.

- [x] RED phase order, same-input resume, no partial remeasure, strict midpoint replay, seal drift, holdout once and no-direction skip, missing/failed case denominator, handwritten profile rejection, software drift.
- [x] GREEN real stage execution and closure replay; qualified software fixture path and unqualified real path distinguished.

### Task4 — Natural candidates, actual media and observation/recovery

Create runtime/natural_candidate_records.py, natural_candidate_media.py, production_natural_repair.py, scripts/natural_color_repair.py; unit/integration tests.

- [x] RED no qualified profile/precheck/non-color failures→no fit/encode; current epoch/whole-frame mapping; one parameter; actual master/playback full decode/no clip/roundtrip≤2/fixed-support metrics; incomplete review/failure override/three attempts/partial outputs/read-only status.
- [x] GREEN end-to-end qualified software fixture using real CPU FFmpeg, review and interruption/recovery; no fake production mapping or real natural success claim.

### Task5 — Actual16 refusal/preservation, compatibility and delivery

- [x] Run actual existing16 records/contexts through new assess; report missing formal check-inputs prerequisites without placeholders; retain original bytes and all reported failures/unknowns; zero model requests.
- [x] Run focused new/related tests and six specified compatibility files serial; one final independent scoped reviewer, fix material issues RED/GREEN.
- [x] Verify original identities; deliver software capabilities separately from unavailable natural qualification/improvement; update same task evidence, no completion/state transition without outcome.

## Ledger

- User explicitly “你继续完成” after agreeing next work is remaining software, existing16 refusal/preservation and no more sampling. Continue inline without another approval loop.
- Ruling: new consumers preserve every old frozen module; old estimate_natural_repair waiting branch remains historical. New CLI vco06_natural_study.py carries real stages; old audit CLI remains byte-stable.
- Ruling: offline frozen-study dry transform is permitted only for qualification computation on copies with author-known axis/semantics and oldr2 cap. It is never runtime candidate authority or human improvement; otherwise the specified before/after threshold derivation cannot execute. No real case is newly granted this permission without valid labels.
- Start2026-10-29 20:24+08. No new inference, labels or successful qualification have been produced.
- Task1 complete: engine RED31 missing implementation, GREEN59 including28 old feature/statistics checks. Task2 records partial: RED17, GREEN48 including engine31. Logs engine-green-b9223ec5da5c48dfa61149044e588e5b and study-records-green-f64c0e97d8c542079a16e0c2f293f269 under runtime cache/logs.
- Guard follow-up: RED2 (orthogonal residual masked by noop; empty holdout observation identity). Implemented residual guard and nonempty inputs; legal null context retained. No frozen historical module edited.
- Ruling: ledger stays in this plan's Ledger section, as established at setup; Git remains read-only and no worktree/commit command is authorized. Tests remain focused and serial; full suite belongs to VCO-08 per task constraints.
- Guard GREEN50: vco06-natural-guard-green-4b33030e23564b208caa294436a1f09e.log. Records/measure/core GREEN54: vco06-natural-measure-green2-3277d8407e704a91bd3e5e8e4cf10365.log. Blind-context regression RED1: source metadata now verifies without calling the old pixel-reading context loader before seal.
- Stages/profile: RED5 missing modules, GREEN60 then7 expanded stage cases (vco06-natural-stages-green-5eda00f631cd42bfb67f3a07a63b5dd5.log, vco06-natural-profile-path-0e9bb9e1d5854f54ad96e6409519d505.log). Synthetic source/measurement providers are isolated test utilities; they are not actual natural qualification.
- Visual contract RED9→GREEN9 (vco06-natural-review-green-d2016ca26e6f4d68aada7be5c46b6397.log). Candidate transaction RED5 missing module→GREEN5 plus2 real CPU native16 media tests (vco06-natural-runtime-green-7018fea92c8c4d3896fd3c105a2a63c5.log):7 passed57.68s. Two-code full-frame master roundtrip, full playback decode, last frame, actual fixed-support metrics and immutable partial output tested.
- Replay label guard RED1→GREEN10 including transaction checks (vco06-natural-replay-green-f7a6cad2924e4039b8cc13ce767a575b.log); changing unknown author labels into exempt refused negatives now fails independently of refreshed metric SHA.
- Ruling: qualification requires real original/preview improvement observation, as required by the approved protocol. Add offline qualification preview encoding only after author-safe dry fit; it is separate from runtime candidate ledger. A bound review index may be submitted to finalize after one-shot evaluation; no thresholds or measurements can change. Missing/failed observation produces unqualified. Cost: additional CPU preview, never a new model request or fabricated human label.
- Ruling: ordinary geometry requires a source clip ID. Generic composition records carry only the actual research manifest clip ID and native local PTS; generated/retained/output indices stay null. No production mapping is fabricated.
- CPU fixture diagnosis: FileIdentity5 is required at VCO-02 boundaries; Artifact3 stays at new record boundaries. The source fixture needed explicit x264 color tags. Frozen OpenCV overlap reports0 for near-coincident polygons under tiny affine error; fixture uses a declared interior reference ROI. Frozen geometry is unchanged and actual cases retain their real failures. Low gray RGB at-.01 often quantizes to no median change; bright textured CPU fixture at-.018 proves nonzero actual improvement without counting as natural evidence.
- Actual16 audit completed at software-audits/20261029-existing16-c6f36d83165a49c28e21046277f499f0/delivery.json, SHA7c9a7be5ae7b9c4af7e8705bdf57350107c5c0279971192866ba749226a560df:16×49 native frames revalidated,4 abstained/12 awaiting calibration-suitable observation,6824 original files bytes/SHA/mtime unchanged, zero fitting/encoding/model requests. Actual watching remains completed; waiting status concerns unknown axis/semantics, not a new viewing demand. Existing16 have no current ordinary assessment/pair manifest, so no ROI or future-SHA request was fabricated.
- Pre-review focused suite:169 passed402.41s, exit0 (vco06-natural-focused-b4d6a907807e494ea57e13aa44fd3f5b.log). Candidate/source identity GREEN28 passed229.28s (vco06-natural-identity-green-689f52aedd9f4e32a4971983868fd68c.log), history GREEN36 passed51.63s (vco06-natural-history-green-db12096cd40847aca870052968c6013d.log). Earlier full-flow run was interrupted after4minutes spent replaying the multi-GB legacy closure; subsequent media transaction fixtures isolate that already separately tested authority. No interrupted run is counted as passing.
- One fresh read-only reviewer natural_software_final_review found8 Important,0 Critical. Findings: failed=True replay bypass; editable geometry support; unbound master/partial playback inventories; fabricated terminal states; sibling/non-color-response failure bypass; receipt redirect away from original bytes; omitted registered observation history; per-variant deadline resets. No second review or implementer agents.
- Fix pass RED:11 unit regressions (vco06-natural-review-fixes-red-d73bc78894624f1ca371cc8fad11f607.log);3 media failures plus1 initially inadequate swap test (vco06-natural-media-replay-red-ec3f9aa44eb04695b9c5b787fc6faab9.log); corrected distinct-source swap RED1 (vco06-natural-master-binding-red-cfe69b38ec3c4d719eb17153bc6ff140.log). Implemented canonical disjoint failures, strict terminal gates, shared original-byte review loader/family failure checks, opaque history completeness, full ordinary RGB geometry reconstruction, exact master/playback inventories and one deadline per case/render/replay.
- Fix verification GREEN63 unit63.50s (vco06-natural-review-unit-green-dbe23fcdf261449fb2a8f157a4ed7f6d.log), then GREEN21 stage/real-CPU-media/transactions479.26s (vco06-natural-review-media-green-fd427d05fe4e4eeaa43e7f40ff96a16a.log). Authentic blank-message errors and multi-case metadata budget tests RED2; success-schema and independent profile/candidate budget tests RED3; their final integration is included in the current189-test focused run, not preclaimed as passed.
- Ruling: one case shares a300second deadline through all128 controls, preview encoding, inspections and replay; exhaustion stops launching more work. A whole multi-case study/profile consists of independent bounded cases. Its small metadata anchors are recaptured after case batches; resetting those metadata reads does not extend an individual case. Completed profile verification precedes the runtime candidate case budget, with original request identities checked again before work.
- Current final targeted run: vco06-natural-final-targeted-0f9eb4fc235a43fca206519f1d3ca0d1.log, active session96750 at22:18+08. Do not edit product files during its frozen software tests. One additional deterministic risk-response duplicate-by-key-order regression has been added but not yet run; close it in the same review completeness fix pass before final compatibility. Next: finish current run, RED that test, shared indexed risk deduplication, rerun final focused suite, six required compatibility files serial, fresh actual16/history audit and original preservation, documentation closeout. No more model requests, sampling or new viewing tasks.
- The189-test run completed successfully597.04s, exit0; it precedes the last risk-completeness refinement. Visual-review and Precheck duplicate-risk regressions both failed while the valid distinct-risk Precheck passed (vco06-natural-risk-coverage-red-ac30d7015b29433193003597cafee159.log). Shared expected-item indices now enforce one response per actual risk independent of JSON key order. No further product changes are planned.
- Latest final scoped run is192 tests: vco06-natural-final-green-fd0edd232f7047f6a7881293dbf51adc.log, active session60065. Once complete, run the exact six compatibility files serial, then rerun the actual16 audit with complete registered observation identities (updated helper preserves its own immutable producer copy in each new audit root), original preservation, CLI help and documentation closeout. Do not count earlier169/189 or overlapping63/21 as additional cases.
- That192-test run passed599.73s, exit0. One numerical boundary regression then showed unchanged stable sources were incorrectly abstained when legitimate nonzero-repair frame/time midpoint ceilings were negative. RED1 with the strict nonzero-repair companion already passing; noop now admits zero regression/increase while retaining off-axis protection and the exact negative ceilings for nonzero repairs. This grants no fit/encode authority and introduces no threshold defaults.
- Final product source validation:194 passed597.45s, exit0, no skip (vco06-natural-closeout-targeted-c232204151954eba8e2836274fa1912c.log). This supersedes the overlapping169/189/192 runs for final counts. All8 Important findings and the distinct-risk/neutral-boundary refinements have RED/GREEN evidence in the single fix pass; no deferred minor or repeat reviewer.
- Exact six-file compatibility run started22:53+08, session64542, log vco06-natural-six-compat-b662f8816515421d9367c2975ea2f3d0.log. Historical same scope took5755seconds; wait for actual completion, do not run tests/real audit in parallel and do not edit product/test files. Last user progress update22:53+08:194 targeted checks passed, six compatibility files still running; next update around23:23 and then every30minutes, progress only. After compatibility: fresh actual16/history audit, verify originals, CLI help, archive/update same handoff and board evidence without state transition. No new sampling/model/viewing tasks.
- Compatibility checkpoint23:23:48+08:144 dots passed /80% reported, process still active64542, no failure output observed. User received only this progress and unchanged natural acceptance state; next progress around23:53. Background exec cells310/311 have finished polling; native pytest64542 is still running. Keep waiting, do not start a duplicate run.
- Compatibility completed2026-10-30 00:28+08:178 passed5690.52s, exit0, no skip; exact six-file scope unchanged. Sessions64542 and all polling cells finished. No product/test code was edited during this run.
- Final actual16 run after all fixes:16×49 frames,4 abstained/12 awaiting suitability,6838 original files preserved bytes/SHA/mtime (14 registered observation copies added to protection); zero fit/encode/model requests. delivery SHA8b90348efb6029be13402dac165b5c81937fe0f28caf87b11da8926f4f309721 under software-audits/20261029-existing16-7c3b470462224447a52a0aca62f69d44. Actual log vco06-natural-final-actual16-001e1ea8691a45a8be82cb80349e5644.log exit0.
- Final closeout log vco06-natural-final-closeout-87ae899ffa2e42e3b2fe7a5c5c58443d.log exit0:6838 current originals and original54 pilot-baseline identities unchanged;10 product/CLI SHA match independent software.FROZEN from the194-test run;10 test/helper files unchanged since that run began;2 actual CLI help checks passed. closeout.json SHA66d44584be30782257322de423d75fdd5153b503d2574f37be4266578bba1ca9. Entry handoff/board/design archived before documentation update. git --no-optional-locks diff --check exit0 with existing newline notices only; no Git writes.
- Task1–5 software plan complete. Natural qualification/improvement remains unaccepted with0 confirmed suitable known-axis positives, so VCO-06 stays BLOCKED; no successor preparation. Final evidence and limitations: docs/task-handoffs/VCO-06-natural-software-results.md. No remaining tests, background workers, new sampling or watching request from this round.
