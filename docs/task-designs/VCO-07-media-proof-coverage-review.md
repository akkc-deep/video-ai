# VCO-07 exact media-proof coverage review

Date: 2026-10-31. One fresh review of the new coverage optimization. Two Important findings; no implementation edits and no second reviewer.

## Scope and evidence

Read `VCO-07-design.md` and `VCO-07-media-proof-coverage-plan.md`. Reviewed the new `_scene_media_check_coverage.py`, the ready-callback tagging delta in `scene_continuity_records.py`, the coverage/whole-execution/ownership/fallback/clone delta in `scene_media_records.py`, and `test_scene_media_check_coverage.py`. Read adjoining execution, revision, reader, base-store, and writer/transport call sites solely to establish the changed code's contracts and consumers.

Compared both changed runtime files with `D:/VideoSi/projects/video-ai/vco07-diagnostics/pre-media-proof-coverage-31db8ce93d21430f9d1076fe290caf20/*.bin`, reading the archives as data only. The continuity delta is exactly the three-line tag registration after creation of the existing callback. Its original closure, full `ByteGuard.verify()`, and before/after argument checks remain intact.

Reviewed source SHA256 values:

| File | SHA256 |
| --- | --- |
| `src/video_ai/runtime/_scene_media_check_coverage.py` | `5cb227b789318470c85d752a0ca6b86f23a4d66bb1fa1d2254d7c8636c41696f` |
| `src/video_ai/runtime/scene_continuity_records.py` | `237186d46378a15aca75ac3838dd0668b98249f89fb30f401ba60797804cdbd3` |
| `src/video_ai/runtime/scene_media_records.py` | `107fc83dd58dffcedfdb186cad39ffe8c29cae6ef1a8deefa20f1f084edec69a` |
| `tests/unit/test_scene_media_check_coverage.py` | `1e478fe1d140a8b675e6cbc9f352d4c94ab05bfdeb6bccabc4f49da216e48c0d` |

Diff/hash log: `D:/VideoSi/cache/video-ai/logs/vco07-coverage-review-diff-c46c4e9faae944e39a5a360832ae8e70.log`, exit 0.

Confirmed the supplied relevant-batch log ends with `151 passed in 43.20s`, exit 0: `D:/VideoSi/cache/video-ai/logs/vco07-media-coverage-final-runtime-1e3531362b6046488273f7486aa3dd97.log`. This is existing verification evidence, not a rerun by this reviewer.

## Important 1: restore execution validation when a source callback invalidates coverage on the global/send path

Location: `src/video_ai/runtime/scene_media_records.py:135-140`, reached through `verify_global()` at lines 127-133 and `capture_guard()` at lines 373-377. The newly thin ownership branch is at lines 91-98.

`verify_global()` first calls `assert_owned()`. With a valid certificate, that deliberately skips execution validation. It then invokes the full source callback through `verify_captured_bytes()`. If that callback changes an execution binding, coverage becomes false, but the subsequent fallback runs only `revision_context['guard'].verify_captured_bytes()`. The execution check skipped at entry is never restored. This differs from the explicit execution fallback added to `assert_write()` at lines 324-334.

Concrete consequence: a send guard can succeed with an execution-budget binding that the original execution validator would reject. The request/graph byte comparisons after `verify_global()` do not validate this changed binding. Production upscale supplies `store.capture_guard(request, graph)` as the client's ownership check; the frame protocol also obtains that guard. This is a guard acceptance defect with potential to admit a downstream operation, not a demonstrated real POST.

Reproduced RED cases:

1. Build the existing `coverage_case`, acquire its real `RunLock`, and install a successful coverage certificate.
2. Write fixture `inputs.json`, frame `request.json`, and `graph.json`; capture the real send guard.
3. Instrument `ByteGuard.verify` exactly as the existing callback-time revision test does: run its original implementation first, then, only for the source proof and once, set `c['check'].budget_artifact['sha256'] = 'f' * 64`.
4. Require `store.verify_global()` to raise. It returns successfully: **RED**.
5. In a fresh fixture, require the captured send guard to raise. It also returns successfully: **RED**.

The source files remain unchanged during this trigger. The expected budget identity changes in memory, which the stated changed-contract requirement explicitly covers. `WholeExecutionCheck.__call__` would reject it at its Artifact equality check, lines 75-76.

Fix: re-evaluate applicability after the complete source callback on every path that relied on thin ownership. If applicability was lost, execute the current original execution and revision validators before returning, or refuse the operation. Apply the rule consistently to global/send and writer paths; do not let an already-invalid certificate followed by another callback-time change avoid the post-callback checks. Preserve lock-free semantics of read-only byte audits when selecting where this check belongs. Add permanent global and send variants of the existing callback-mutation test; include an unknown/replaced execution callback as well as changed budget data.

## Important 2: revision contracts omit the whole-admission reader graphs reached through revision frozen inputs

Location: `src/video_ai/runtime/_scene_media_check_coverage.py:94-113`, especially the returned contract at lines 110-113; qualification executes the omitted dependency at line 182 and later trusts this incomplete contract at lines 155-159.

`RevisionGuard.verify_captured_bytes()` calls `verify_frozen(self.frozen)` and recursively verifies its ancestors. For a whole-scene frozen input, `verify_frozen()` calls `verify_whole_scene_frozen(frozen)`, whose cached path verifies that frozen input's `EvidenceReader` graph. `_revision_contract()` includes each revision's frozen options/raw, files, directories, absences, views, and revision ancestors, but does not bind these reached whole-admission reader graphs. Only `WholeExecutionCheck.admission_guard` receives `_reader_contract()` validation.

Actual read capture correctly includes the ancestor reader's current reads during qualification. That is insufficient to prove the same set remains complete later: a different ancestor admission reader can gain a dependency without changing any field in `_revision_contract()` or the execution reader contract. Unknown/custom validators inside that omitted graph are likewise outside the advertised typed graph checks.

Concrete consequence: an inherited whole-scene dependency can change after qualification while the certificate still applies, so both revision validation and the newly added dependency's byte check are skipped. The old fixed source proof cannot check a dependency added later.

Reproduced RED case:

1. Build `coverage_case`. Add an ordinary `RevisionGuard` ancestor with a copied frozen object.
2. Give that ancestor its own ordinary `EvidenceReader`, initially capturing the existing covered evidence file. Use the fixture's whole-admission stub to dispatch to that reader for the ancestor frozen object and to the original fixture reader otherwise. Both dispatch branches call the real reader `verify()`.
3. Acquire a real `RunLock` and qualify. Qualification succeeds, since all actual reads are covered by the existing source proof.
4. Create `new-ancestor-dependency.json` outside the captured revision inventory, call `ancestor_reader.capture(path)`, then change the file's bytes.
5. `certificate.applies(store)` is still true. Require `store.verify_global()` to raise for the changed dependency. It returns successfully: **RED**.

This fixture models distinct cached admission readers without loading production evidence; it uses real `RevisionGuard`, `EvidenceReader`, capture, proof, and store implementations. It does not establish that the current production run has already encountered this mutation.

Fix: include the actual live whole-admission reader graph reached from every revision frozen input and ancestor in qualification and subsequent applicability checks, including binding replacement and unknown-method refusal. Do not silently recapture a new graph as the old baseline. A smaller safe fallback is to refuse deduplication whenever a revision's whole-admission graph cannot be proven to be the already-bound known execution graph. Keep strict revision traversal for those cases. Add permanent tests for a distinct ancestor reader gaining a file/inventory/child guard, a reader override in that graph, and replacement of the live cached reader.

## Review test execution

Ran only three cheap focused tests, constructed in memory with `pytest.Function.from_parent` against the existing coverage test module and fixtures. No source or test file was edited. The Python command was invoked through `scripts/bootstrap.ps1`, `Initialize-VideoAiEnvironment`, and `Invoke-VideoAiNative $VideoAiPython -B`; pytest used an explicit `D:/VideoSi/cache/video-ai/temp/vco07-coverage-review-<CommandId>` basetemp and `D:/VideoSi/cache/video-ai/pytest` cache.

Result: **3 failed in 0.41s**, exit 1; each failure was the intended `DID NOT RAISE`, after successful certificate creation. Test names:

- `review_global_execution_change_inside_callback`
- `review_send_execution_change_inside_callback`
- `review_ancestor_reader_extension`

The exact executable reproduction code and output are retained in `D:/VideoSi/cache/video-ai/logs/vco07-coverage-review-red-546ce1725bc6409887e5442e4d46fd48.log`. No GREEN is claimed: this review makes no implementation changes. The only repository write was this report; the authorized test/bootstrap invocation generated its disposable fixture runs, cache, and diagnostic logs under `D:/VideoSi`.

## Other assessed behavior

- `_proof_covers()` compares complete `File.key()` values, rejects duplicate paths, and requires exact inventory specifications and absence membership. It does not downgrade content identity to path, size, or mtime. Coverage is all-or-nothing.
- Qualification performs real reads after full admission, checks the actual callback before and after capture, and handles capture overflow with fresh strict validation. Unknown execution and direct revision types/overrides fall back. The execution reader graph has bounded cycle/type/method checks; finding 2 concerns graphs not reached by that contract.
- The tag is installed only after the existing successful ready source capture in the product integration. It preserves the callback's function closure and argument checks. Callback/tag identity and both store callback slots are checked for applicability.
- A changed contract before a call disables certified ownership; the base ownership method then runs the execution validator. Direct revision changes are restored on global/read checks, and writer callback-time revision changes have explicit fallback. Finding 1 concerns the missing corresponding execution fallback on global/send.
- The new ownership branch checks the real `RunLock` type, run directory, and current owner JSON. Persistent store writes still enter `assert_write()`; production guarded logging uses that method; transport guards enter `verify_global()`. Thin ownership is sound only while the complete coverage and fallback assumptions hold, which the two findings currently break.
- Clone applicability checks the receiving store's frozen identity, run directory, execution/revision identity, and callback slots. Media Artifact, JSON inventory, absence, empty-file, model, tool, and request/graph guard loops were not removed by this delta. Clone-added media Artifacts still flow through those loops.
- Caller-thread write enforcement remains in place, and the certificate does not retain native handles or deadlines. Default/segmented execution remains on the original closure and unqualified ownership path. `None` execution uses the strict fallback. No separate defect was found in these inspected changes; this is not an exhaustive concurrency or legacy-compatibility certification.

## Declined to judge

- The frozen native lease/ByteGuard implementation, file-sharing/alias rules, protected-input core, native batch repair, and prior late-hardlink fix. Prior 69-test evidence is accepted as supplied; no re-review or rerun of that work.
- The unchanged frame transaction protocol, its 180-second timeout, 30-second cold allowance, once-only submission/recovery semantics, or broad old 200-frame/delivery suites. Call sites were read only to trace the changed guards.
- An installed covered-store performance result: the new actual profile is pending. The old installed profile's source 4.406s, execution 1.812s, writer 6.110s, and global 8.438s are supplied historical measurements, not new measurements by this review.
- Real 180-second feasibility, service cold start, GPU memory, throughput, and completion under the installed runtime. The 212.592s refused and 166.586s qualified fixture clock controls demonstrate their modeled protocol behavior only; they do not authorize or prove production recovery.
- The complete VCO-07 implementation, unrelated runtime/planning source, all-suite compatibility, or VCO-08 acceptance. No full suite, install, network, GPU, worktree, or git write was performed.
- Current production state verification or mutation. Source3ready/Engine05a, original source POST3/upscale POST0, and preserved orphan 219 PNGs are supplied context, not freshly certified production facts here. No production writer, source regeneration, observation/epoch regeneration, extraction recovery, media-ready transition, or POST was run.
- Real 463-frame upscale/composition, audio/subtitle fidelity, final viewing, human response, publish/SMTP, or zero-new-work replay. All remain separate production acceptance work.
- Visual quality, research generalization, VCO-05/VCO-06 historical evidence validity, or JIM-08 completion.
- Arbitrary malicious Python introspection or forged internal tags/code objects. This review tests the stated supported graph/callback mutation boundary, not an adversarial same-process security sandbox.
- Repair correctness or post-repair GREEN results. The requested deliverable is one review; implementation and targeted RED/GREEN fixes belong to the implementer, with no second reviewer implied.

## Verdict

**Changes required: fix both Important findings before relying on this optimization for production advancement.** The equality/subset mechanism and source tagging preserve their intended checks, but the incomplete revision graph contract and missing post-callback execution fallback permit certification to outlive the obligations it was meant to replace. Existing passing tests and synthetic timing controls do not close these gaps. Production profile, feasibility, recovery, final observation, and publication remain pending.
