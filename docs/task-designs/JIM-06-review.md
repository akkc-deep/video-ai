# JIM-06 independent review

Reviewed 2026-10-19 against the complete `JIM-06-design.md`, `JIM-06-plan.md`, and the 22-file SHA256 source snapshot in `D:/VideoSi/cache/video-ai/logs/jim-06-review-package.md`. All 13 implementation modules and all nine test/helper modules in that package were read, including the complete delivery recovery test module. Relevant inherited store, admission, logger and service helpers were inspected read-only. Predecessor checkout changes are outside this review.

This is a static review, not a test result. I ran no Python, media commands, or test suites and modified no implementation/tests. Worker reports describe limited historical/diagnostic results, including 52 Task 1 unit passes and 60 quick observation/delivery passes; those are not a final combined regression gate. The final authentic, historical and whole-suite results remain pending. Test-authored viewing observations establish protocol behavior only.

**Specification verdict: changes required.** No Critical issue identified. The snapshot has four Important findings below. The coordinator is arranging corrections, so this is not approval of either the snapshot or later working-tree bytes.

**Maintainability/test-quality verdict: useful separation and substantial recovery tests, but not yet sufficient for approval.** The pure planner, independent schema domains, immutable command receipts, genuine PCM comparisons and owned delivery transactions are strong. Missing tests are concentrated at the boundaries between separately validated components. Dense control flow and test doubles make those omissions harder to see.

Line references below refer to the packaged source snapshot, not lines shifted by concurrent corrections.

## Important findings

### I1 — Partial frame submission evidence is not adjudicated during whole-batch preflight

Locations: `src/video_ai/runtime/scene_upscale_transactions.py:297`, `:127`; callers in `src/video_ai/runtime/_scene_upscale_records.py:180` and `src/video_ai/runtime/production_scene_upscale.py:73`.

`validate_scene_frame_submission` returns `None` immediately if `submission.json` is missing. `_load` checks record shape and accepted evidence, but the retained POST rejection and full queue/history conflict/failure adjudication occur later in `recover_or_submit_scene_frame`. A later frame with a durable rejected response, mismatched original history graph, differing successful outputs, or retained execution failure can therefore pass preflight if the crash occurred before terminal/submission persistence. When an earlier frame is missing, its paid submission can happen before the loop reaches the later conflict. This violates the explicit all-frame local-conflict gate. Read-only progress can also describe that terminal raw evidence merely as running.

A related hole is the no-intent branch: it checks `http/*.json`, but a request/graph with only an orphan `http/<UUID>.body` has no matching JSON and is not rejected there. Once request.json exists, the higher-level request-absent orphan check no longer protects this path.

Required correction: independently validate and adjudicate all existing raw evidence before treating a partial frame as a legal resumable prefix; distinguish incomplete unknown state from definite conflict/failure without new network work. Detect orphan body files even without intent. Preserve ordinary accepted-response/history recovery and the normal queue/history completion race.

Missing coverage: a later frame interrupted immediately before writing its rejection/conflict/failure terminal, an earlier frame still missing, and assertions of zero new POST/service starts; separately, request+graph plus orphan body with no intent. Existing tests cover same-frame recovery and a later orphan graph, which do not exercise this combination. Reported to coordinator before the report was written.

### I2 — Downstream guards omit raw bytes referenced by admitted upscale records

Location: `src/video_ai/runtime/scene_media_records.py:247`.

`require_scene_upscale_acceptance_record` validates the upscale evidence, captures every `*.json` file and its inventory, and captures each frame's input/input_copy/model_output/output. It does not capture the nested raw Artifacts in the admitted upscale JSON. In particular, upscale `http/<UUID>.body`, extraction evidence and still-existing prepared staging files are absent from downstream `guard_paths`/empty-file guards.

Trigger: after initial composition/final-acceptance admission, change a raw upscale HTTP body while leaving its response JSON and four repeated frame Artifacts unchanged; for example, mutate it at the movie `prepared` publication boundary. Subsequent publication guards check the same JSON bytes/inventory and frame media and can publish the final receipt without noticing that an indispensable upstream proof no longer validates. A fresh public require would reject it, but the in-flight acceptance/publication must reject it too.

Required correction: capture the full already-admitted upscale record inventory, including positive and empty raw bodies, while respecting legitimately absent promoted staging paths. Propagate all resulting guard categories across stage roots.

Missing coverage: late positive/empty **upscale** HTTP-body mutation before encoding, final acceptance or output rename/receipt. The current raw-body unit test covers capturing a synthetic upstream scene-clip record directly, not the upscale-to-composition handoff. Reported to coordinator.

Follow-up inspection confirmed the same omission for candidate preparation: `production_scene_composition.py:_candidate_ready` validates an existing candidate staging copy, but `_capture_composition_guard` captures only candidate/materialized Artifacts and preparation JSON bytes. It does not capture that staging copy or its legitimate absence after rename. Use the receipt-aware capture for candidate-ready too. The new `guard_absent_paths` category must propagate through both `_capture_composition_guard` and `_observation_context`; their explicit propagation lists in the snapshot only carry paths, directories and empty paths.

### I3 — Final acceptance has no upstream recheck after the final observation scan

Location: `src/video_ai/runtime/production_scene_delivery.py:141` and `:147`.

After saving raw observation bytes, `_consume` calls `verify_global`, then runs `final_observation_state`, then persists the acceptance/rejection receipt. The state scan can read and validate many authored originals and rebuild template inputs; it receives the already-admitted candidate and does not revalidate candidate media. `store.write` checks the caller thread and lock, but not the captured upstream byte guards.

Trigger: mutate the candidate, PCM or another captured dependency during the second `final_observation_state` scan, after its preceding `verify_global`. The new acceptance receipt is still written and the call returns `final_review_ready`. A later require rejects the changed bytes, but the current invocation has accepted a stale version, contrary to the immediate acceptance guard contract.

Required correction: recheck the complete store guard after the fresh scan and immediately before persisting a decisive receipt; also recheck before reporting ready on reuse paths if those paths perform intervening reads. Preserve failed-raw recovery and accepted immutability.

Missing coverage: mutation during the final rescan, rather than at the earlier `observation-original` boundary or later output-publication boundaries. A deterministic hook around that second scan suffices. Reported to coordinator.

Related guard rebinding: `_observation_context` with a supplied cached candidate recaptures current candidate-commit/materialized/candidate-ready/command hashes into `context['store']` without first comparing existing captures. A JSON-only mutation can therefore replace the context's previous authority during a rescan. In `_consume`, the original local store is an earlier independent guard snapshot; the final check should use that store, not solely the freshly rebound context. More generally, check prior captures before recapture (when holding the lock), or preserve and compare existing identities rather than overwriting them. Add a JSON-only mutation regression as well as a candidate-MP4 mutation case.

### I4 — Snapshot capture assumes promoted upstream staging files still exist

Location: `src/video_ai/runtime/scene_media_records.py:120` and `:138`.

The snapshot recursively validates every nested Artifact in admitted upstream JSON. A valid media-ready receipt retains its staging Artifact after the staging file has been renamed to the target; a valid extraction-ready receipt likewise retains its staging directory/frame list. Complete upstream admission permits this normal promoted state. Recursive capture nevertheless tries to hash the absent historical staging path and raises `FileNotFoundError`, preventing ordinary admitted runs from entering JIM-06.

The coordinator separately reported this failure from a preserved authentic run. The snapshot code independently confirms the failure path. During this review the working tree acquired receipt-aware staging/target capture and absent-path guard logic; those changed bytes are outside the original package and require their new regression results and an updated snapshot/final hashes. This finding must not be counted as independently verified fixed by this report.

Missing coverage in the snapshot: constructing the common context from a genuinely promoted upstream media-ready receipt with no staging file, followed by a successful real short flow. Also verify that reappearance of a conflicting absent staging file is caught and that all absent-path guards propagate through composition/delivery store clones.

## Minor findings

### M1 — Dense transaction control flow increases review and maintenance cost

Representative locations: `src/video_ai/runtime/scene_delivery_files.py:278`, `src/video_ai/runtime/scene_upscale_transactions.py:119`, and `src/video_ai/runtime/production_scene_delivery.py:122`.

Many state transitions combine several guards, mutations and writes on a single line, with untyped context dictionaries carrying mutable guard sets across stage roots. The I2 omission and the already-fixed caller-thread clone defect are examples of invariants that are easy to miss at these handoffs. Expand state transitions into separate statements and centralize propagation of every guard category instead of repeating selected dictionary/set updates in composition and observation code. Keep the public schemas unchanged.

### M2 — Protocol doubles need explicit integration checks for guard propagation

Locations: `tests/unit/test_scene_upscale_transactions.py:12` and `tests/integration/test_scene_media_recovery.py:48`.

The lightweight transaction Store intentionally has no real lock/path guard and returns arbitrary byte outputs. Low-level publication tests use `SceneClipStore` and authored non-media candidate bytes. These are appropriate protocol fixtures, but passing them does not verify the `SceneMediaStore` admission/capture boundary. Keep their scope explicit and add narrow real-store integration regressions for I1–I4. Current authentic tests are valuable but still pending final execution; do not infer their results from quick protocol tests.

## Reviewed outcomes and remaining evidence

| Contract area | Static assessment |
| --- | --- |
| Native retained mapping | Correct source-based 93/92/15 mapping, no second child-head removal; ordered technical-frame contributions. Pure and authentic 200-frame tests are authored. |
| Native pixel proof | Full sequential RGB24 source decode and every PNG comparison; original source/image hashes checked. Fast/quality dimensions are tested with real media. |
| Once-only submissions | Intent precedes POST; unknown original task is GET-only; response/accepted/history recovery preserves UUID/graph. Normal race and retained conflict handling are present; whole-batch partial adjudication needs I1. |
| Global identities and thread guards | Exact Artifact schemas, lexical reparse checks, actual run lock and preserved caller-thread clone are present. Invocation-local tool ArtifactStamp semantics correctly avoid inventing historical binary stamps. I2/I4 block complete guard assurance. |
| Narration/subtitles | Genuine original speech PCM comparison plus all-zero gaps/padding; exact SRT/ASS regeneration and font bytes; unique materialization directories and complete sequence hash checks. |
| Candidate commands/media | Unique encode/probe intents, exact successful command-log matching, retained original encode, probe stdout recovery, full decode/CFR/PTS/AAC validation and no accepted-media reencode on documented recovery paths. |
| Final observation | Exact candidate/composition/selected-image/baseline/dynamic-chain bindings; scene/join/unit text, full playback, verdict and time checks; failed raw blocks without a receipt; accepted observations reject later replacement. I3 affects final persistence timing. |
| Formal output | File-ID plus SHA ownership, unique immutable temp attempts, unknown-temp preservation, no-overwrite Windows rename, receipt-last and completed readback. Existing same-byte unrelated targets are refused. |
| Read-only replay | Separate progress/require facade and completed prefix; no repair from read APIs; original command and actual media are reconstructed. Partial raw-terminal progress is part of I1. |
| Legacy isolation | All reviewed production changes are new scene/schema=2 modules. Legacy shot validators/workflows are reused without relaxation in this package; historical regression still must run. |
| Validation gate | Final current-tree targeted, authentic long-chain/recovery, exact historical list and full-suite outcomes with matching file SHA256 are required before completion. |

No actual paid model call, cloud action, email, or genuine final-film viewing was performed by this review. Corrections should be reviewed against refreshed bytes; final approval must separately record which findings were fixed and which fresh tests passed.
