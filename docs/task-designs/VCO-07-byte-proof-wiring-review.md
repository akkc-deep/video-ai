# VCO-07 byte proof wiring — independent Task 2 review

Initial verdict: CHANGES_REQUESTED. No Critical findings; two Important observation gaps identified below. This review covers the runtime wiring and its focused tests, not production acceptance or Task 3.

Inputs: `VCO-07-byte-proof-plan.md`, `VCO-07-byte-proof-core-report.md`, `VCO-07-byte-proof-core-review.md`, the current core/wiring source and focused tests, and data-only diffs against `D:/VideoSi/projects/video-ai/vco07-diagnostics/pre-byte-proof-<filename>.bin`. The snapshots were never executed. The reviewer made no implementation/test changes, ran no production/GPU/network commands or full suite, and made no .git writes. Only this requested report was written. The coordinator reported 76 focused tests and 115 original runtime regressions passing; these results were not independently rerun by this reviewer.

## Strengths and requirements checked

- `manifest.hash_file` observes both fresh hashes and successful protected hits. The observation callback returns without work outside an active capture.
- Successful full continuity admission precedes proof installation. Pending/failed exceptions propagate; `None` retains the original callback. Capture overflow performs a fresh full admission outside the failed capture and retains the original full callback.
- The media installation rechecks the existing media snapshot before changing either callback. Base historical/read-only context construction was not changed.
- The callback retains an immutable ByteGuard plus frozen argument state checks, without an old Reader, decoder cache or admission deadline. `for_root` shares that callback; original caller-thread, ownership, per-write and POST guards remain in place.
- Original epoch, attempt, job-intent, review, audit-output, revision and whole-evidence scans retain their scanners and now expose their actual inventories. Current continuity source glob is observed before and after admission.
- Historical archive code validates original identities as data and hashes actual saved archive paths. No added hook recursively opens historical original paths. Empty command logs and empty package files still pass through the real hash hooks in `_ReadWindow.freeze`/`verify`.
- The already reviewed core continues to check mtime, ownership/link metadata, aliases, byte identities, exact inventories, absence and a fresh verification deadline.

## Critical

None identified in this review.

## Important 1 — missing original-prefix absence on archive fallback

Location at initial review: `src/video_ai/runtime/scene_continuity_records.py:331`, `_read_prefix_original`.

When the author's original prefix observation is absent, the validator reads the deterministic SHA-named retained backup. The initial wiring captured the backup's bytes but did not observe the original path's absence. After admission, recreating that original path with changed bytes makes the full validator select it and reject its identity; the installed byte proof would continue to validate only the backup. This is a change in a consumed branch condition and violates the required absence closure.

Record `observe_absence(path)` immediately before taking the backup branch. Add a regression that captures the real `_read_prefix_original` fallback, recreates the original, and proves both the unchanged full validator and byte guard refuse. The coordinator was notified during review and added the observation at current line 332; scoped test evidence/final re-review remains to be recorded below.

## Important 2 — historical promotion staging absence is not observed

Locations: `src/video_ai/media/_continuity_promotions.py:142` (`_source`), `:152` (`resolve`), and `:163` (`verify`); proof integration at `src/video_ai/runtime/scene_continuity_records.py:695` and media installation at `src/video_ai/runtime/scene_media_records.py:434`.

PromotionResolver accepts an absent historical staging file through its proven final target. Its `exists()` branches do not expose absence to runtime capture. Recreating a historical stage with wrong bytes then makes the full report validator inspect and reject it, while a proof containing only the target continues to pass. The new current `scene_clip_records.validate_media_receipt` observation does not by itself cover historical/external promotion receipts consumed by the report reader.

The fix must remain runtime-only to preserve the current 05a Engine. A bounded supplement can inspect only canonical fixed promotion receipts already present in the actual captured file set, bind their already-validated bytes, and add missing-stage observations. Do not scan historical manifests or unrelated reports. If a stage is absent from the first proof's files, require its absence rather than conditionally observing it only when it is still absent at supplement time; otherwise a new file appearing between semantic admission and supplementation could escape. Preserve prior identities, refuse conflicts, apply capture limits to the combined state, and verify the completed proof before installation. Falling back to the original validator is preferable to emitting an incomplete proof.

## Minor

The accepted-tree benchmark remains pending at the time of this initial review. The focused temporary-fixture results establish behavior but do not establish the performance of real current-run traversal. This is already required by Task 2; record its measured result before claiming Task 2 complete. No additional full-suite or production run is requested.

## Declined to judge

- Task 3 production upscale/composition, final playback, publish/replay: outside this Task 2 implementation review and expressly not run.
- Full repository suite: explicitly deferred by the user to VCO-08.
- Re-reviewing the unchanged independent primitive from scratch: Task 1 already has scoped approval; this pass checked its new `job_intents` scanner integration and use by Task 2.

## Assessment

Ready to proceed: with fixes. The wiring preserves the intended installation and ownership structure, but both consumed absence branches must be closed before replacing the full semantic callback. The initial 76/115 passing results do not cover these two cases.

## Coordinator fix pass (2026-10-31 08:30+08)

The initial independent verdict above is retained. Both Important findings were
fixed in one pass with failed-first regressions: prefix RED941d22d3 then GREEN77;
promotion RED7e2d14b8 then GREEN196. `_capture_promotion_absences` supplements only
canonical actually captured receipts, refuses newly appearing uncaptured staging,
preserves existing identity baselines, limits the combined absence count, and
verifies the completed immutable proof before installation. All changes remain
runtime-only. A related three-generation metadata fallback absence was also
reproduced REDd1cdb8ae and fixed. Final eight-file run ce15659b exited0 with
220 passed/41.65s, including core, wiring, real resolver promotions, original media/
continuity/revision guards and the public recovery protocol. This is the author's
test-backed disposition, not a second independent review. No known unresolved
Critical/Important; actual-tree performance evidence remains pending separately.
