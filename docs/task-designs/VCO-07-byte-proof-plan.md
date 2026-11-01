# VCO-07 media admission byte proof plan

Binding spec: VCO-07-design.md. Existing 05a epoch and current three assessments,
source videos and author playback feedback remain valid. This runtime-only fix
must not change Engine, create another epoch, invoke source models or replay CV.

## Global Constraints

- Preserve initial complete semantic continuity admission and all per-write/POST
  lock, original bytes, declared mtime, alias, absence and exact inventory guards.
- Capture actual validator reads, actual archive paths and consumed history only;
  never recursively bless historical manifest.original paths or unused reports.
- Bound proof state, retain no decoded caches/old deadline, and make verification
  immutable/thread-safe and compatible with store.for_root/read-only paths.
- Never install a ready proof for a pending/failed/legacy-none admission. Base
  context retains its historical/read-only behavior until full admission passes.
- .git read-only, no worktree/commits, no network/GPU during checks; user deferred
  full suite to VCO-08. Existing checkout is explicitly authorized. Preserve all
  saved reports and original three source POSTs and playback records.

## Task 1 — Independent primitive

Use VCO-07-byte-proof-core-brief.md only. Owned new core module and focused tests.
Fixed interface feeds Task 2; immutable ByteGuard verifies actual observations.

## Task 2 — Observation wiring and media installation

Observe every manifest.hash_file successful return, including protected hits.
Observe the exact original inventories/absences in continuity records, revision
guards and whole EvidenceReader without changing inactive behavior. Capture the
continuity-source glob before/after initial full continuity admission. Install
proof only after semantic success and existing media snapshot recheck; retain
original full callbacks on proof overflow. Bind full frozen/unit/timeline typed
state to guard. for_root shares immutable guard. Add meaningful protocol/guard
tests and benchmark actual current-run admission/proof without GPU or writes.

## Task 3 — Resume concrete work

Freeze new runtime-only software, verify Engine remains current 05a, retain
all current three reports. Resume only saved authored reviews e557c7fff7664b6f...
with matching production logger; never rerun analyses. Once source gates ready,
run existing authorized upscale/composition path, final actual playback and
independent publish/replay. Do not claim VCO-07 complete until those outcomes.

## Pre-flight conflict table and ledger

Task 2 current: runtime observation and media installation implemented. Initial
wiring RED 11 failed/4 passed (74547048d3ac444c8ab0bf1967b15b8e). Added current
job-intent scanner RED1 (d6e7c19d2d7e49a197521d9af30c2138); GREEN core+wiring76
(4e5ecd48bf1740e9b8dde28b4aaccbbb). Original five runtime regression files115
passed/39.86s (2cec7c2ba40141708cacc7c42ce45530).

Fresh independent review found two Important absence gaps. Prefix fallback RED1
(941d22d397f54aa1aff477d830ce81f9) then GREEN77 (59799603cb5444859289020ff236dedf).
Historical promotion RED4 (7e2d14b8fa3b4cb28d87151586041c91), then seven-file
GREEN196/41.50s (8d1ab7937a5f4aaaafbcee39b17f1c94). Final combined-absence bound
and promotion+wiring40 passed/2.64s (5e17b4b02dae4f3b8533d97a6c685f03). Existing
integration protocol recovery22 passed/0.39s (db761cffb7154df2bedd4bdfce937db7).
No full suite, source POST, new epoch, analysis, acceptance, GPU or publish.

Ruling: preserve 05a by supplementing only canonical promotion receipts in the
actual observed file closure, rather than editing media/PromotionResolver.
Every consumed resolver receipt is frozen; an original stage without an observed
identity must still be absent during supplementation. Existing stage identities
are never replaced; combined absences are bounded, and the complete proof is
verified before installation. Cost if wrong: an unrecognized receipt fails closed;
CaptureLimit retains the original complete callback, with its original cost.

Final Task2 fix pass: inherited metadata fallback RED1 d1cdb8ae580b479f9225bfa7b7dfe0d7,
GREEN all eight relevant files220/41.65s ce15659bbfc4416898ae0102c79b4829. Both
reviewed Important findings plus this related origin absence are covered; no
remaining known Critical/Important. Full suite remains deferred to VCO-08.

Benchmark73042 stopped after verified PID40924/start/path identity because the
diagnostic script omitted the normal verified_scene_execution_write memo scope.
Native exit-1 is not success; old phase5414404c.../agent-stop.json preserves why.
No production/GPU/source model work occurred. Ruling: correct only the diagnostic
entry boundary, which is part of the existing production API, without relaxing
any validation or redoing analyses. Current benchmark native50915, start08:29:34,
log56e34f5f2e2646818885386171671ff2, phase33eae4770e054e3e87dfe54e3dbb1806.
It is nonready progress capture only; awaits measured result, never admission.

Freeze preparation d2cc8c386b8f44d48d1443c84ab9df42 exited0: 315 files/7 changed,
Engine05a unchanged. Saved df939d4a8f9147fca9452b6ab31f97a5, then diagnostic
benchmark script corrected, so a new exact inventory is required before author
submission. Do not reuse315 as if byte-identical. No source reviews submitted.

08:42 continuation: normal-boundary benchmark50915 also stopped after 10m47s
without capture completion, with exact worker42604/creation/path checked and
phase33eae477.../agent-stop.json preserved. Native-1 is not a benchmark pass.
Isolated observer profile8e6792a2 found 1000 protected hits .028s baseline/.322s
captured; ten identical 1000-entry inventories1.417s. This is extra capture IO,
not a production source/quality failure. Ruling: deduplicate canonical file
resolution only for identical already-captured names, retaining fresh leaf stat/
ownership and all final verify IO; check inventory distinct parents before/after
plus each leaf reparse checks, matching the original EvidenceReader strategy.

Complexity/ownership RED2failed1passed c7f2f0ae35df486ca83fef774b964204, final eight
files223 passed/40.47s e244e32a83444abba600117eec405e5d. Isolated revised profile
50f4b37d: captured1000 hits .173s; inventory.345s. Scoped core safety review
requested from existing reviewer; no production/GPU work. Actual benchmark now
native96616, log92ec2a74b94b463d92768115ab891fc8, phasee9d429d062da44708d7ac2bad4d8dfd5,
start08:42:09; normal production scope plus phase timings only. Await real result.
Both315 inventories (df939... and4f6a0...) predate this observer/script change;
must freeze a fresh exact software inventory before authored source submission.

08:48 superseding ruling: independent observer review found three Important
capture-time alias gaps in the proposed fast recording (observer-review.md).
Do not waive them based on final verify: parent junctions can appear transiently.
Stopped only own diagnostic39456 after exact creation/path check; native96616
exit-1 is not success (phasee9d429.../agent-stop.json). No production mutations.
Restored strict `_safe` on every file observation and every inventory entry;
kept fresh lstat ownership. Complexity assertions requesting unsafe skip were
replaced by strict-canonical assertions, plus actual parent-redirect and
generator-transient-junction fixtures. Valid RED4 ef4c977c1ca343b6a6e7682aca82a0eb;
first attempted RED b461... had a test indentation error and is NOT valid RED.
Final same eight files225 passed/41.24s cd69008c02c742ff9afec2303e560fb4.

Current only actual diagnostic native60465, logc5b3d39f3caa4c89bc8f025f318ece6f,
phase1cef5e70e5824d85b2c2602091a5d7d2, start08:47:19. Strict observation, normal
production boundary and stage timings; allow initial capture to finish instead
of changing code during it. This initial capture can be slow; detector/report
deadline remains original300s and installed proof verify remains unchanged.
Not a current production ready proof, no reviews submitted, no GPU. Actual
performance still awaits result. No full-suite reruns; all original reports and
three source POSTs/author playback observations retained.

Task 2: complete at09:03+08. Strict actual-tree benchmark native60465 exited0,
phase1cef5e70e5824d85b2c2602091a5d7d2/result.json:31,209 actual files totaling
38,387,230,007 bytes;33 inventories/23,202 entries/20 absences. Initial capture
841.875s (scene_context676.219s;epochs21.375s;three assessments43.422/30.282/
16.907s); new proof.verify15.968s. Initial context precedes the unchanged report
Reader300s interval. All three states remain awaiting_review, ready=false;
this benchmark installed no production admission and wrote no production state.
No source regeneration/analysis/GPU. Exact current315 softwarebe59c6c3456a4e5c...
frozen82833976c7e04252a8a0fe8163126def exited0, Engine05a unchanged. The slower
initial strict capture is recorded, not hidden or treated as a reason to relax
aliases. Extra capture-recording optimization is deferred; primitive safety
checks restored and all known review Important findings addressed by RED→GREEN.

Task 3: started only saved authored review submission with submit-current helper,
be59 software, e557 review plan and original continuing authorization. No repeat
analysis/recovery/epoch. Source gates, upscale, composition, final actual review,
publish/replay still require real results; do not mark VCO-07 completed yet.

Task3 source review submission completed: native5572/worker34432 exited0, log
fe2eee3260d043eab1af2af065e8630d. Phase3d0d63a2a93c492ca8716887db14823b/result.json
all_source_gates_ready=true, original_source_posts3,new_model_posts0,forbidden[].
Real three source observations/reviews retained, original reports and Engine05a
unchanged; 219/110/134 native retained frames. Third source returnedready09:44:26;
first/second returnedawaiting for remaining clips, not failure. At09:49:23 started
one authorized advance-reviewed-sources invocation, native20544/worker29100,
log3d688edb25424105aef7d62e93b4e33a. Exact software remains315be59, no new runtime
edits. Await actual phase/GPU/upscale/composition; no production outcome preclaimed.

Task 1: complete (existing HEAD2292bc9, no commits under read-only policy).
Round1/5: both Important addressed; RED6 failed54passed75e635d9 then GREEN60
passed/no skips85656d1c1817438483a06c6e710c4472. Scoped independent re-review
APPROVED in core-review.md, no new breakage. Actual traversal benchmark is
carried to Task2, not treated as a production pass. Task2 integration proceeds
inline under executing-plans; Task1 independent primitive used SDD as narrated.

Task 1 initial implementation: 54 passed/no skips (c13ec58f37364f00991e6cdf4130f557),
DONE_WITH_CONCERNS. Extra traversal cost and non-preemptible synchronous IO are
observations, not an assertion of actual performance. Task review requested two
Important fixes: preserve excluded subtree semantics, and check deadlines before
starting new IO after metadata/prepass work. Round 1/5 dispatched to same owner;
no integration source changes before this task clears review. Minor deferred:
extra traversal cost remains unmeasured and is explicitly included in Task 2's
actual guard benchmark. No Git commits under existing read-only constraint.

| Tasks | Shared interface / files | Finding and ruling |
|---|---|---|
| 1 vs 1 | Files and tests vs immutable observer API | Consistent; no product hooks in Task 1. |
| 2 vs 2 | All observation hooks vs byte proof installation | Must preserve original scanners and inactive behavior; tests and actual proof benchmark required. |
| 3 vs 3 | Saved source gate artifacts vs unchanged Engine | Source/analysis replay is explicitly excluded. |
| 1 vs 2 | capture_reads/observe_file/inventory/absence/finish/verify | Interfaces frozen in brief; Task 2 starts only after core review. |
| 2 vs 3 | Frozen runtime identity and guard benchmark | No running software changes; freeze only after checks/review. |

Ruling: Adapt SDD workspace/commit mechanics to existing authorized Windows
checkout and .git read-only policy; reports/ledger stay in established docs,
tests use native bootstrap and external runtime cache. No new worktree or commits.
Cost if wrong: evidence is file/hash based rather than a commit range; review
packages must include precise owned file contents and original snapshots.

Current production checkpoint: own worker14600/native72006 stopped before any
source author original/accepted receipt; three current reports and draft reviews
are durable. Stop evidence is diagnostics/agent-stop-before-media-byte-proof-
3d22f415c5df4a179aa0251f5de6bd68.json. Native -1 is not success. Stale lock must be
handled only by existing RunLock dead-owner recovery, never manual deletion.
