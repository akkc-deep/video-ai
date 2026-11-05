# Video storage layout implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement these tasks inline. User approved the design and implementation; do not ask for a second design or execution-method approval.

**Goal:** One visible video number, one complete production bundle, independent deliverables, and explicit close/clean commands.

**Architecture:** A storage manager owns video allocation, current-revision lookup, lifecycle locking and deletion boundaries. Existing generation engines run under an allocation scope into short internal revision directories; legacy absolute paths remain supported. The production CLI is the managed entrypoint, while low-level APIs and historical CLI commands preserve compatibility.

**Tech Stack:** Python 3.12 standard library, Windows/NTFS, PowerShell, pytest.

**Spec:** `docs/task-designs/storage-layout-design.md`

## Global Constraints

- One visible automatically allocated number and name, e.g. `0001-旅行者一号`; resume/close/clean by `--video 0001`.
- No historical file deletion or moving installed weights/environments during this implementation.
- Preserve original submitted requests, frozen inputs and unknown-effect recovery; no additional inference, video decoding or model hashing for storage operations.
- Public resources stay outside disposable. Reparse points cannot redirect cleanup outside managed roots.
- Existing workspace changes are preserved. Git metadata is read-only in this environment: implement in the supplied workspace, no commits/worktree creation.

## Review Focus

- Closing concurrently with creation/revision/reference registration must never move a live bundle.
- An interrupted close or clean resumes without creating an empty replacement video.
- A legacy run cannot become eligible for deletion through a forged video selector/index.
- Public/paid results needed by another retained task cannot be removed through close.
- Cleaning a completed bundle leaves real, independent delivered files accessible.

## Tasks

### Task 1: Managed roots, video allocation and lifecycle

Files: create `src/video_ai/runtime/storage.py`, `storage_lock.py`; extend `runtime/paths.py`, `manifest.py`; add `tests/unit/test_storage.py`.

Interfaces: `VideoStorage(runtime_root=RUNTIME_ROOT)`, `create(title)`, `find(selector)`, `allocate_revision(video)`, `activity(video)`, `report(video=None)`, `close(video, dry_run=False)`, `clean(video=None, dry_run=False)`, `allocation_scope(storage, video)`.

- [x] Write failing tests for sequential numbers/Chinese titles, stable lookup, occupied/unknown/legacy/reparse rejection, close interruption, targeted clean and independent outputs.
- [x] Run the new test module and observe failures.
- [x] Implement atomic indices and metadata-only inventory, process-aware Windows locks, whole-video lifecycle/cleanup and scoped run allocation.
- [x] Run the new module; all tests pass without touching real productions/runs/models/output.

### Task 2: Generation entrypoint, revisions and independent delivery

Files: create `src/video_ai/managed_production.py`; extend `runtime/production_inputs.py`, `production_scene_revision.py`, `runtime/production_delivery.py`, `cli.py`; add `tests/integration/test_storage_lifecycle.py`.

Interfaces: `make_managed_video(..., video=None, title=None)`, managed allocation in `create_run`, current-revision index and completed delivery manifest.

- [x] Write failing synthetic lifecycle tests for new/resume/revision/publish/close/clean with no real models, including blocked/unknown requests and a second video dependency.
- [x] Observe failures, implement CLI `--video`, title, and `storage report/close/clean` with dry-run and per-video selection.
- [x] Preserve generation records within short `process/revisions/01` folders and references to sibling revisions; never rewrite an existing frozen record.
- [x] Deliver to `output/<video-name>/v001/video.mp4`, copy script, retain existing publication receipts, add independent `delivery.json`/latest index.
- [x] Run lifecycle and relevant existing production/revision/delivery regressions.

### Task 3: Test and cache isolation, launcher and documentation

Files: modify `tests/conftest.py`, `scripts/bootstrap.ps1`, migration/online-install scripts as needed, README/config documentation; add focused isolation tests.

- [x] Write failing tests proving runtime fixtures and ordinary caches stay in disposable and model/Python dependencies remain protected.
- [x] Implement isolated test allocation, ordinary-cache routing and preserve legacy HF/Torch/base-interpreter locations while dependencies exist.
- [x] Make launch/resume instructions use one video number; document exact close/clean commands and that generation completion does not auto-delete.
- [x] Run focused storage/path/config/CLI/bootstrap/launcher/migration tests; no full video generation or full historical scan.

### Task 4: Review and completion

- [x] Review changed files against all lifecycle requirements; request one independent final code review.
- [x] Fix material findings with targeted regression tests; run the affected suite once more.
- [x] Record exact tests/results and remaining limitations in this plan's ledger; summarize usage to the user.

## Execution ledger

Ruling: Work in the supplied dirty workspace because Git metadata is read-only and it contains the current production implementation; no reset, staging, branch creation or commits.

Ruling: Implement inline because delegation is disabled by the session unless specifically required by a skill. One final independent reviewer is required by executing-plans.

Ruling: Retain existing stage-relative filenames underneath each short internal revision rather than mechanically rewrite hundreds of media/recovery path contracts. This preserves existing frozen-request correctness while concentrating every video's files in one removable bundle. User-facing directories and IDs follow the approved simplified design; input/config snapshots and assets/work categories can be resolved from recorded stage paths without duplicating media. Document the concrete on-disk implementation rather than claim every illustrative design subdirectory is already populated.

Task 1: core lifecycle implemented. Initial storage tests observed missing module, then 10 passed. Managed roots, short revision allocation, atomic index, close/clean and crash recovery covered in `tests/unit/test_storage.py`.

Task 2: CLI/managed production implemented; initial missing wrapper observed, then 16 storage/lifecycle tests passed. Added a real synthetic scene-revision integration: exposed Unicode FreeType font loading, fixed by using run-relative ASCII snapshot paths for managed contact-sheet filters. Exposed short-ID SMTP collisions and validator mismatch; centralized message identity and kept legacy IDs unchanged. Real revision test plus mail identity test now 2 passed (18.55 s).

Task 3: test runtime and resource fixtures isolated, bootstrap ordinary caches routed to disposable while legacy model/base-Python locations remain protected. Initial isolation tests 3 failed before implementation. First broader regression 142 passed/9 failed: thread ContextVar isolation and structured invalid-text errors; fixed with registered test roots for fixture worker threads and legacy error-result passthrough. Second targeted regression 35 passed/2 failed (158.36 s): old CLI tests inject a legacy allocator; fixed managed wrapper to preserve injected legacy result. Retest still required. Do not repeat the four already passing full-media interruption variants without a new failure.

Remaining: shared-cache cleanup; owner/unknown-effect close cases; installer locks and launcher instructions; independent delivery crash semantics; final targeted tests and one final independent review. No real historical data moved/deleted, no real model inference invoked.

Task 3: implemented shared disposable cleanup, live pytest owner protection, real unknown TTS/mail checks, launcher continuation by simple number, installer lifecycle leases and docs. New immutable frame linking observed failing, then 14 storage tests passed. First complete focused pass: 228 passed in 37.80 s.

Final review: one fresh independent read-only reviewer reported seven Important issues: actual Jimeng intent schema, escaped Unicode dependency paths, legacy generation lease, direct revision API lease, premature current-revision commit, active launcher log deletion, and old standard-test-launcher paths. All addressed in one consolidated pass. Reproducing tests observed failing for real Jimeng intents, escaped dependencies, revision reservation/current pointer, legacy-cache lease, active log and test paths. Added direct API activity assertion and OS mutex contention coverage. Post-fix focused suite: 236 passed in 38.25 s, log `D:/VideoSi/disposable/video-ai/tests/storage-reviewed-final.log`.

Final review minor: contradictory implementation-status wording in design document corrected; no deferred minor findings.

Final: Ruling: real-service outcomes, real-video semantics and adversarial external filesystem races were outside this static review. Validate lifecycle/independent file retention using synthetic providers and real codec files, with no real inference, no extra full-video qualification and no claims about historical freed space. Existing boundary checks and OS mutex remain; unrelated malicious OS-level file replacement is not newly modeled.

Ruling: managed output paths are derived lexically after invocation admission, rather than scanning every video index during repeated frozen-input checks. This preserves the no-overvalidation constraint.

Final engine smoke: reused the existing real-engine/local-model-double test under a managed Chinese video directory. Generation/publication succeeded; initial close correctly refused the foreign-lock corruption deliberately left by the reused legacy test. The test restores only that exact synthetic corruption before close/clean. Final result: 1 passed in 41.13 s, log `D:/VideoSi/disposable/video-ai/tests/storage-engine-final.log`. Real engine, Chinese paths, real encoded media and independent delivery survive process-data removal; model services are local synthetic doubles, not real inference.

Final fixture isolation audit: removed five remaining hardcoded model/tool test roots from helpers and routed the occupied-output fixture to the sandbox. Relevant migration/storyboard/path/real-managed-revision subset: 103 passed in 49.59 s, log `D:/VideoSi/disposable/video-ai/tests/storage-isolation-final.log`. Added direct cleanup-junction boundary check: 1 passed in 0.34 s; public sentinel preserved.

All four tasks complete. Changes remain in the supplied working tree; Git metadata was not changed. No real historical video/model/environment data moved or deleted. No deferred minor review findings. No full repository test run or real-model video qualification claimed; focused tests above are the verification for this storage change.
