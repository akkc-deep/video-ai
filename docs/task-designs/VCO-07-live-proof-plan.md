# VCO-07 live protected proof performance repair

Binding scope remains VCO-07-design.md and the completed byte-proof plan. Runtime
only; current Engine05a and three source approvals/reports stay. No new source
POST/CV/epoch, no changed budgets, no .git/worktree/install/full suite. Current
source gate result3d0d63a2 is real ready. Media20544 was agent-stopped before any
frame intent/HTTP/GPU after it created only immutable inputs.json; native-1 is
not success. Preserve that file, audit and recover its dead RunLock normally.

Evidence: strict ByteGuard31209 files verify15.968s. Existing frame transaction
budget is frozen180s and at least12 full proofs occur even before first intent/
POST (existing request+graph writes, capture guards, ensure's before/after global
guards). Minimum measured191.616s excludes service startup. Do not extend or
restart deadlines. Fix protected verification and redundant checks instead.

## Task 1: active native lease verifier (independent implementation)

Owned files and exact interfaces: VCO-07-live-proof-core-brief.md. Implement
runtime/_protected_continuity_inputs.py and small verification.py lifecycle hook;
focused unit tests only. Protect actual admitted source reads in the current
whole input window. Retain no handles in ByteGuard. Source pin under a new held
deny-write/delete handle must freshly hash and match original SHA/mtime/ownership.
Keep every public observe_* strict; do not repeat the rejected capture shortcuts.

Native file identity/canonical alone does NOT cover ancestor reparse attributes.
Hold canonical directory handles with deny-delete for EVERY ancestor and query
their live reparse attributes before AND after each native file verification.
Directory objects cannot be replaced while those handles are held; attributes
are not treated as immutable. A separate experiment proved FILE_WRITE_ATTRIBUTES
can FSCTL_SET_REPARSE_POINT even with a read-only directory handle, so caching
directory attributes once is forbidden. Non-qualified cases always use strict
fallback. Per-file/parent/pin state and shutdown remain bounded and thread safe.

## Task 2: wiring and redundant-check removal (inline)

ByteGuard.verify may use Task1's boolean fast verifier, otherwise retain exact
old strict path/hash logic. Capture helper calls prepare only after successful
full semantics, complete capture and initial strict verify; only actual proof
dependencies and explicit immutable upstream target roots. Then reverify before
installation. Pending/failed/none/overflow never acquire a ready fast proof.

Media verify_global executes an identical continuity callback once at its last
existing position in verify_captured_bytes, while distinct callbacks both run.
Media.write keeps caller/lock checks, serializes a new JSON before the final
write_bytes guard (the same last guard as before), and does not pay the same
full proof twice. Existing-file writes still verify. Cover mutation during JSON
serialization, frame POST drift, distinct callbacks and clone/read-only behavior.
Do not remove protocol guards or modify scene_upscale_transactions budgets.

## Task 3: verify, review, resume

Run focused old/new guard and transaction tests, independent fresh review, actual
current-run read-only ready admission and proof timing. No analysis replay. Freeze
new software after checks; preserve original be59 bytes as data. Audit existing
only inputs.json SHA7bd5d19e... and source gate receipts, recover dead29100 lock
using original RunLock. Use a saved-state-aware resume operator, not the original
first-start helper that asserts no upscale root. Resume original same run with
no frame intents/POSTs, then463 RealESRGAN frames/composition/final human review/
independent publish/replay. Do not declare VCO-07 complete before those outcomes.

## Preflight interface table and ledger

| Tasks | Interface/file relationship | Decision |
|---|---|---|
| 1 vs 1 | Native file/dir leases, bounds, tests | Keep canonical directory objects pinned; query live attributes for each check; new source SHA rehash mandatory. |
| 2 vs 2 | ByteGuard fast hook, admission preparation, media writes | Final per-write/POST guard preserved, no captured-reader/deadline retained. |
| 3 vs 3 | Current source approvals vs runtime software | Engine stays05a; existing inputs and paid-source records are immutable. |
| 1 vs 2 | prepare_continuity_inputs / verify_protected_continuity_file | Fixed duck-typed file identity records; implementation owns native window only, integration owns proof/store. |
| 2 vs 3 | Exact frozen implementation and reviewed timing | Resume only after concrete evidence and new inventory. |

Ruling: native handles live only in existing invocation-local whole input window,
never immutable emitted proof. Parent path handles deny deletion/renaming but
do not prevent in-place reparse writes, so live parent attribute checks before/
after each verification are mandatory. No deadline or policy relaxation.

Ruling: keep established Windows checkout and docs-based ledger under explicit
.git read-only constraint; no worktree/commits or shell workspace scripts.

Task1: pending. Task2: pending. Task3: pending. No production process currently
running. Stop evidence media-phase24ba68.../agent-stop-before-frame-deadline-fix.json
records inputs.json1379 bytes/SHA7bd5d19e8b2a9c75301b41f4882aeb369e20ed0f7fc3fd7373f64997868416be,
old owner29100/start134378849632172871. Old lock not manually removed.

Task1: complete. Fresh independent review APPROVE, no findings; core30+existing
verification19 =49 passed/1.07s independently. Implementation final1aa0764782dc...
49 passed; reports core-report/core-review. Native GENERIC_READ required because
attributes-only directory handles do not enforce deny-delete (real RED→GREEN).
FSCTL attributes remain live mutable and are checked every file before/after.
Extra prepare_existing flag only qualifies an existing held physical read, never
new file pin/hash or semantic readiness; main uses it only for identical already
captured rows. Public unprotected observations keep exact strict path checking.

Task2 integration RED ea2d7f9c3failed5passed proves duplicate new JSON/global/clone
checks; GREEN61/3.93s 2afb6dba. Native wiring RED3 cd250346; initial integration
318passed1failed20b5e7de: test expected only one _safe but legitimate native
qualification checks strict twice more. Ruling: bounded initial qualification
is required and not a regression; test now caps setup <=4 for25 repeated reads.
No source policy weakened. Final current 11 files323 passed/45.79s 2bd7ce485635...
includes actual pin lifetime/nonready/overflow, public alias, source epoch/review,
media writer/POST, verification and frame transaction protocol tests.

Task2 whole-integration fresh review and real ready benchmark pending. Benchmark
uses new benchmark-ready-continuity-proof.py (old nonready script must NOT run).
No source regeneration/analysis/review replay or GPU. Existing inputs.json stays.

Task2: complete. Integration fresh review APPROVE/no findings, independent149
passed/38.91s; controller323 passed/45.79s. Task3 verification complete:36 budget/
transaction controls passed/4.37s; actual ready benchmark65655 exit0,31224 files/
38390804827 bytes,full callbacks4.360/4.375s,initial admission818.781s. No rerun.
Accurate321 inventory df51ee197ccb448f936ee71ba7bd8f7e prepared8a422db3 exit0;
Engine05a/frame180s unchanged. Task3 production recovery,463frames/composition,
new final human audio/subtitle review,publish/replay pending. Original29100 dead
lock must be recovered only through RunLock; saved inputs remain sole upscale file.
