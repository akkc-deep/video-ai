# VCO-06 final scoped review

Reviewed the VCO-06 design and implementation plan, numerical module, repair records/profile/engine/media/validation/transaction modules, CLI, the four production-origin guards, and the scoped unit/integration tests. This was a static, read-only product review. No tests, media commands, subagents, Git mutations, or product edits were performed; this report is the only new file. Reproducers below describe code paths, not executed test results. Previously reported numeric/profile and runtime fixes were considered rather than assumed complete.

The parent session is running recovery and compatibility verification separately. Synthetic `fixture_only` viewing declarations are not natural-video acceptance. Missing real playback/precheck evidence remains an acceptance limitation and is not waived by this review.

## Important findings

### 1. A new precheck can bypass a retained original motion/structure failure

Locations: `src/video_ai/runtime/_scene_color_repair_validation.py:37-46`; `src/video_ai/runtime/scene_color_repair_records.py:97-103`.

`collect_progress` returns the target clip even when it has a retained failed observation, with `source[clip_id]['rejected']` populated (`scene_clip_records.py:464-487,506-510`). `capture_binding` ignores that failure history and validates only the observation selected by the new precheck. Its parent checks inspect accepted observations, but there is no corresponding target-history check. The current assessment validator validates technical reports; it does not enforce retained playback failures.

Reproducer: start with a technically complete target and current assessment, then retain a valid original observation with `motion_process='failed'` (and its issue). Supply a separate new original observation with non-color checks passed, and an otherwise valid color-only precheck referencing that new observation. The new observation is not submitted to the original acceptance writer, so the existing accepted-versus-failed conflict guard does not run. `validate_precheck` sees only passed non-color checks, and proposal can proceed to fitting despite the retained confirmed motion defect. This also affects a candidate's later `current_binding` recheck if the disqualifying original observation arrives after proposal.

The design permits repairing an original color failure, but explicitly excludes confirmed motion/structure defects and forbids clearing the original block with another passed observation. Retaining the old bytes without enforcing their meaning is insufficient.

Fix direction: inspect all valid retained original observations and relevant current/historical continuity responses for the bound source. Reject any confirmed non-color defect; preserve the explicit color-only exception. Add a regression where the selected precheck is valid but a different retained original observation confirms a motion/structure failure, including a failure arriving after candidate generation.

### 2. Saved/recovered numerical evidence can contradict its `passed` flag and still authorize review

Locations: `src/video_ai/runtime/_scene_color_repair_media.py:292-295`; `src/video_ai/runtime/_scene_color_repair_validation.py:317`.

The saved-media validator checks the outer decoded-score schema, frame count and roundtrip maxima, then trusts only `scores.get('passed') is True`. It does not validate the score object's exact schema, per-frame residual thresholds, aggregate improvement, regression, reasons, or frame order. It never reads the body of `full-frame-checks.json`. Saved fit validation similarly checks only the lengths of `before`/`after`, not their row contents or numerical conditions. Hashing these documents proves which bytes were supplied, not that their measured contents passed.

Reproducer: on a completed candidate before review, replace `decoded-scores.json.scores` with `{'passed': true}` while keeping valid `roundtrip_max`; alternatively retain detailed scores but set a frame's `p99_error` above 2 or `max_error` above 4 and retain `passed=true`. Set a `full-frame-checks.json` row's `new_clip` to 1. Refresh the changed Artifacts in media/terminal closure. All source/master/playback, report, recipe and sidecar identities remain unchanged. The present saved validator accepts these omitted or contradictory measurements, and a valid candidate review can receive `research_candidate_reviewed`. The same gap applies to recovery before the first terminal exists.

This is a remaining part of early runtime finding 3, not a repeat of the now-fixed raw-master alias check. The saved admission still fails to establish the required all-frame numerical and full-frame clipping gates.

Fix direction: require canonical evidence paths and presence; validate complete exact schemas, candidate/frame identity, finite numbers, thresholds, no new clipping, zero parameter change, aggregate strict improvement and consistency of `passed`/`reasons`. Apply the same checks to fit and decoded measurements before admitting or recovering a candidate. Regressions should cover missing score fields and contradictory failure values with otherwise valid media identities.

### 3. The pixel preflight undercounts full-frame NumPy temporaries

Locations: `src/video_ai/runtime/_scene_color_repair_media.py:24-30,127` (the analogous decoded difference at line 163 also allocates full-frame temporaries).

`dimensions` budgets `3*raw + count*2048*25 + 16MiB`. During `np.abs(changed.astype(np.int16)-image)`, the source RGB and changed RGB already occupy `2*raw`; the int16 cast/subtraction or subtraction/absolute-result pair occupies another `4*raw` at peak. The actual expression therefore needs at least `6*raw`, before sample arrays and retained prior-frame buffers. This is not bounded by the numerical operator's chunked implementation.

Concrete size: two native 3840x2160 frames have `raw=24,883,200` bytes. They pass the repair preflight at `91,529,216` bytes (assuming sufficient disk), while this full-frame expression alone reaches at least `149,299,200` bytes, exceeding the declared 128MiB (`134,217,728`) pixel-work limit. The ordinary source RGB limit permits this size.

Fix direction: calculate clipping, changed-channel counts and maxima in bounded chunks, releasing prior full-frame buffers, or conservatively account for every simultaneously live array before allocation. Add a regression that observes allocation ordering/working-set bounds without allocating oversized test images.

### 4. Recovery persists an awaiting-review terminal before checking the recovered fit and producer closure

Location: `src/video_ai/runtime/production_scene_color_repair.py:196-213`.

`_finish_recovered` performs partial report/media checks and writes immutable `terminal.json` with `status='awaiting_review'` at lines 211-212. Only afterward does `validate_saved_candidate` enforce the recovered fit schema/status/bound and the exact candidate-owned report producer/epoch/manifest checks. If those checks reject, the exception handler preserves the already-present terminal and cannot record a failed terminal. Thus a failed recovery leaves a durable successful-status terminal and an immutable, unusable candidate.

Reproducer: interrupt a valid colored proposal at `after-report`, leaving complete measured outputs and no terminal. Change `fit.json.operation` to another operation (or make a producer's `engine_epoch` differ) before retrying the same request. There is no prior terminal Artifact binding this output yet. Recovery hashes the changed file into a new `awaiting_review` terminal, then rejects it in `validate_saved_candidate`. The public call returns blocked and subsequent status reports stale, but `terminal.json` permanently claims awaiting-review. No invalid candidate needs to become production-ready for this to violate the recovery contract.

Fix direction: assemble and fully validate the prospective terminal and all recovered producer/fit/media evidence before committing the terminal. Preserve partial outputs and record the truthful failure/interruption result when validation fails. Add a recovery regression asserting that invalid complete-looking outputs never create an awaiting-review terminal.

## Other scoped observations

No Critical finding is reported. The explicit four production-origin guards reject the inspected research paths/records, and no concrete import bypass was established. Failed candidate review submissions take precedence over an existing passed receipt on reread. The status path has no direct extraction, encoding, or persistence call. Those observations are static-review conclusions, not substitutes for the parent's serial verification or real-video acceptance.
