# VCO-04 independent implementation review

Reviewed 2026-10-26 against the complete `VCO-04-design.md` and implementation ledger in `VCO-04-plan.md`. This is a read-only implementation review except for this report. No tests, services, network, model requests, GPU work, Git writes, or implementation edits were performed by this reviewer. The controller was still executing targeted verification; this report does not establish completion or real video playback.

Scope: the five new continuity modules/script and the tracked configuration, CLI, production, source-clip, media, completed-prefix, delivery, and revision-origin changes. Existing VCO-03 artifacts and unrelated workspace changes were not attributed to VCO-04. Source locations below refer to the implementation inspected during review; concurrent controller fixes may move lines. Findings were communicated before this report was written and require verification against the final implementation.

## Assessment

No Critical issue identified. Five Important findings were identified. The intended separation between immutable media history and current admission is present, but the findings below prevent an unconditional acceptance recommendation for the inspected version.

## Important findings

### I1. Interruption after assessment leaves analyze permanently unable to recreate its review material

**Location:** `src/video_ai/runtime/production_scene_continuity.py:209`, `:277`.

The existing-assessment shortcut validates the assessment and immediately calls `artifact(.../review-template.json)`. The write path calls `boundary('assessment')` after persisting assessment and before `_review_template`. A KeyboardInterrupt at that required boundary leaves a valid immutable assessment without a template; the next identical analyze request takes the shortcut and fails because the template is absent. It never reaches template creation. The same issue applies if only the Markdown material is absent.

**Required fix:** use the validated existing assessment to idempotently restore both review files without invoking the analyzer or replacing assessment bytes. The existing `test_explicit_recovery_keeps_single_analysis_and_same_author_bytes` already expresses the required recovery and single-analysis assertion; its final result was pending at review time.

### I2. Production manifest accepts a fixed reference with no authored ROI

**Location:** `src/video_ai/runtime/scene_continuity_records.py:190`; supporting source `src/video_ai/media/continuity_analysis.py:224` and `:96`.

`validate_manifest_binding` verifies retained-frame coverage, the independent reference source/index, and the required comparison tuples, but does not require a reference anchor in the regions record. The ordinary `_resolve_manifest` enforces clip-start anchors only. Removing the independent reference anchor while retaining all clip-start anchors therefore passes both structural checks. `_measure` sees no left-hand reference box and emits `identity_unverified` for reference comparisons. A complete video response can then resolve those concerns even though an explicit required production input was omitted.

This conflicts with design section 6, which requires an ROI for the independent reference and says missing semantic input must wait rather than silently become an otherwise admissible diagnostic.

**Required fix:** verify each relevant region has the exact independent-reference anchor as well as the exact clip-start anchors before allocating an analysis job. Add a missing-reference-anchor regression using otherwise valid ordinary input.

### I3. Full-prefix author evidence is never archived in the production run

**Location:** `src/video_ai/runtime/production_scene_continuity.py:303`, especially `:320`–`:337`; `src/video_ai/runtime/scene_continuity_records.py:256`.

Review consumption preserves Review raw bytes and delegates schema-2 video observation preservation to `_consume`, but never creates the specified `prefix-observations/<sha256>.json`. For three or more clips, the only PrefixObservation remains at the caller-supplied runtime path, which `_prefix` and `_review_state` reopen on every query. Editing or removing that input file destroys the ability to validate a previously accepted or confirmed-failure review, including historical and revision-origin evidence. This fails closed, but loses the durable original author evidence explicitly required by sections 4 and 8.

**Required fix:** preserve the exact PrefixObservation raw bytes before the review-original boundary and make subsequent reads prove and consume the retained bytes without changing the author's Review submission. Include removal/change of the submission input and interruption/replay checks. Merely copying the file while continuing to require the mutable input path would not solve the recovery problem.

### I4. Transaction timestamps are not completely validated

**Location:** `src/video_ai/runtime/scene_continuity_records.py:114`, `:364`–`:415`, `:458`.

Epoch commit time is checked against intent time but not against now. An otherwise valid commit changed to `2999-01-01T00:00:00+00:00` passes this branch; the repository's newly added `test_future_epoch_commit_and_extra_epoch_without_intent_rejected` directly targets that missing check. `_assessment` does not parse job/attempt `created_at` or terminal `finished_at`, and only parses assessment `created_at` without checking chronology. Receipt creation time similarly lacks a future upper bound. Exact keys alone do not enforce the required timezone-aware timestamp contract.

**Required fix:** validate the timestamps of every consumed transaction record, reject future persisted completion/receipt times, and enforce appropriate intent → attempt → terminal → assessment → review → receipt ordering. Recovery must retain legitimate original times rather than manufacture new earlier evidence.

### I5. The cumulative 64 MiB metadata limit is refunded by profile validation

**Location:** `src/video_ai/media/continuity_report.py:138`–`:167`, `:455`; supporting source `src/video_ai/media/continuity_calibration.py:331`–`:335`.

The new report reader intentionally makes `release_json` a no-op so sequential profile inputs still count toward the total. However, `_verify_profile_evidence` unconditionally restores `window.json_bytes` to its entry baseline in `finally`. The report verifier calls that helper directly. Profile JSON paths remain in `window.json_paths`, so later evidence expansion does not charge them again. A profile that is below the limit in isolation, followed by report/pair/metrics metadata, can therefore pass with more than 64 MiB of distinct parsed metadata in the same verification.

There is a second aggregation issue at the runtime boundary: each `_assessment` constructs a new report window, independent of the shared runtime `Reader`, so a multi-assessment progress read has no single combined metadata budget.

**Required fix:** share a non-refundable metadata budget across the production operation and its nested report/profile/color readers. Preserve any existing VCO-03 streaming semantics separately. Add a boundary case where each phase is individually below the cap but their distinct combined bytes exceed it; it must reject before accepting the operation.

## Minor observations

- `_ReadWindow` and `Reader` count JSON differently: the former charges distinct paths, while the latter charges repeated reads of the same path. Clarify one operation-level definition when fixing I5; redundant validation should not exhaust the limit unpredictably.
- `SceneContinuityResult` advertises `reviewed`, but the standalone script only exposes analyze/reassess/status and review consumption returns the existing `SceneClipResult`, as the public runtime signature specifies. Document the actual result contract rather than suggesting the local script can produce `reviewed` today.

## Areas checked without an additional concrete defect

- Optional policy parsing rejects unknown keys, bool schema versions, unsupported policy and legacy strategy; loading requires the exact frozen role/path and preserves the absent-policy branch.
- Current source/media admission wraps historical base validation. Completed-prefix and missing-aggregate paths perform historical reconstruction before checking current admission; media writers retain current guards.
- Child submission admission covers its scene prefix, while durable model intents preserve the old recovery path. No diagnostic implementation imports model clients or service managers.
- Current engine capture and archived historical engine verification are distinct. Historical archives are hashed as data, and no archived Python/native code is executed.
- Raw current reviews are scanned even when a prior ready receipt exists; `confirmed_issue` and failed playback have priority. Historical candidate matching uses source SHA and ordered local ranges, with explicit revision-origin recursion.
- One/two-clip evidence is bound to the exact schema-2 observation. Three-clip playback checks exact ordered media/ranges, author identity, actual video method, checks/verdict/issues, and a verified current or historical assessment. The previously discussed fabricated historical stub is rejected by the current loader.
- Report validation checks ordinary manifest identity, source/analysis provenance, report/metrics/pair agreement, detector derivation, original audit paths, deep nested references, and fresh closure bytes. Frame/comparison maxima are inherited from the ordinary manifest validator.

These are source-review conclusions, not proof that every dynamic branch has executed successfully.

## Verification limits and acceptance handoff

The controller reported policy 27 passed, report 8 passed, and guard/recovery 21 passed at dispatch. This reviewer did not rerun or independently claim those results. Tiny real-media flow and boundary recovery were still active. The plan ledger itself only recorded earlier partial tiny-flow failures and fixture reduction at the time inspected.

The final acceptance record must include the final serial results for both design test groups and show regression evidence for the findings above. Particularly consequential requirements still need explicit final evidence: confirmed defects across changed engines and inherited revisions; raw failed prefix after ready; partial-audit retry limits; conflict between multiple successful attempts; original media/request/PCM/subtitle preservation after reassess; and completed/delivered-prefix/direct-writer guards after reassess. Mocked orchestration tests are useful but should not be described as end-to-end proof of these combinations.

The synthetic tiny-media observations remain explicitly fixtures. Neither this review nor a passing fixture test establishes actual human/agent complete playback, visual accuracy, production thresholds, or completion of the separate formal benchmark.

## Controller resolution, 2026-10-27

The independent findings above are retained unchanged as review evidence. The controller fixed all five in the first fix wave and observed their regressions pass:

| Finding | Final behavior and evidence |
|---|---|
| Assessment/template recovery | Existing validated assessment restores the idempotent review template. `test_explicit_recovery_keeps_single_analysis_and_same_author_bytes` passed with all job/attempt/report/assessment/review boundaries; the analyzer runs once. |
| Fixed-reference ROI | Every region requires exact clip-start anchors plus the independent reference anchor. The missing-reference-ROI case was RED, then passed in `test_manifest_binding_rejects_incomplete_frames_wrong_join_and_reference`. |
| Prefix original retention | Valid three-plus-clip PrefixObservation bytes are retained under their SHA and can be read from that retained copy if the caller removes the original path. The actual-byte assertion passed in `test_real_tiny_frames_to_report_and_explicit_fixture_review`. |
| Timestamps | Future epoch commits reject; job/attempt/report/terminal/assessment ordering and current time are checked. Core `test_future_epoch_commit_and_extra_epoch_without_intent_rejected` passed. |
| Aggregate metadata budget | The report window cannot refund unique bytes; explicit shared Budget/deadline spans runtime/history/report/source metadata. `test_profile_validation_cannot_refund_unique_json_budget` and `test_distinct_report_validations_share_one_metadata_budget` were RED, then passed. |

Actual logs: `vco04-final-core-9ba6594917a34e12a672a023b96b00f9.log` (71 passed), `vco04-tiny-flow-final-0a049daf822048f1b67c88080a6c6122.log` (5 passed), and `vco04-report-budget-final-45e3f400b026482ea2809ca3e93256ec.log` (10 passed). This is controller verification, not a second independent review. The full required compatibility group and the three additional acceptance combinations were still pending at this resolution note; their final results belong in `VCO-04-verification.md`.

Final controller closeout: core74 passed, complete real-media flow8 passed, and all329 legacy compatibility cases obtained passing results (304 on the first run;25 minimal-context failures fixed and rerun). Additional actual RED/GREEN closed duplicate-success history, missing dependency classification, archive-before-commit resume, and the public expected-engine/positional-manifest contract. Final407source identities match, diff check exits0, and board records VCO-04 COMPLETED. Full exact logs and outcome mapping are in VCO-04-verification.md. No open Important/Critical or deferred minor remains from this review; actual production playback and benchmark limitations remain unchanged.
