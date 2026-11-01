# VCO-07 byte proof core — independent Task 1 review

Verdict: CHANGES_REQUESTED. No Critical findings; two Important findings below. The core is otherwise coherent and substantially matches its brief. This verdict covers only the two new files in the supplied exact diff package, not the pending parent integration.

Reviewed inputs: `VCO-07-byte-proof-core-brief.md`, `VCO-07-byte-proof-core-report.md`, and `VCO-07-byte-proof-core-review-package-867196570f04432c9484bcb830ac14b0.txt`. Package base: `2292bc92eaabfc88ddd229a0c738ea6b0394ea45`; core SHA256: `A15DE5944412889F601D7FA7A3065787903D8B069BEA8702AD3B2ECBB11364BD`; test SHA256: `21026ECF416C0FBAFAAB06D9220B3160D73432672251AF328865CA4020A323E6`. Line references below are new-file line numbers reconstructed from that package.

This was a static review. No implementation edits, test reruns, production commands, network/GPU operations, subagents, or .git writes were performed. The implementer's reported final result is 54 passed, no skips, exit 0, in `vco07-byte-proof-core-green-final-c13ec58f37364f00991e6cdf4130f557.log`; this review did not independently rerun or inspect that log. The full suite remains deferred to VCO-08.

## Specification compliance

The exported capture/observation interface, lazy runtime imports, declared mtime and byte/hash comparisons, ownership/nlink snapshot, immutable tuple-backed proof, fresh verification deadline, observation suppression, normal-closure-only finish, exception restoration, nested propagation, copied-context handling, and bounded observation consumption match the brief on inspection. Failed observations poison all live builders, including when callers catch the exception. The extra bounds on empty inventory specifications and absences are reasonable fail-closed extensions.

The primitive retains only explicitly observed identity/inventory/absence data. It does not recursively parse historical manifests or retain decoded reports, readers, handles, or admission deadlines. All seven scanner kinds are present. However, the whole-file prepass does not fully preserve the required exclusion semantics (Important 1), and the verification deadline is not checked at some important IO boundaries (Important 2).

The two new files cannot establish the global installation requirements: actual-validator observation coverage, consumed-history scope, initial complete admission, pending/failed/legacy-none non-installation, `store.for_root` compatibility, original per-write/POST locks, or historical base-context behavior. These remain required parent integration checks, not missing implementation in this explicitly independent primitive task. Nothing reviewed authorizes changing saved reports, source POSTs, or playback records.

## Code quality findings

### Important 1 — whole-file prepass applies checks inside excluded subtrees

Location: `src/video_ai/runtime/_continuity_byte_guard.py:84` through line 89, invoked at line 98 before the original inventory at line 101.

`_reject_redirected_descendants()` walks every descendant with `root.rglob('*')` and rejects every link/reparse point. It contains no `.git` or `__pycache__` exclusion. Therefore, a root whose admitted inventory is just `keep.json` will fail verification if an unrelated redirect exists inside `root/.git/` or `root/__pycache__/`, even though the brief explicitly requires the existing whole-file scanner's exclusions to be preserved. The later call to `EvidenceReader.inventory()` cannot restore exclusions after the prepass has already raised. This expands the proof's effective dependencies to excluded metadata and can reject an otherwise unchanged accepted inventory.

Apply the same excluded-subtree rules to the metadata traversal while retaining rejection of empty redirected directories in the included tree. Prune excluded subtrees before descending rather than merely filtering the final returned filenames. Keep the original inventory scanner and its same-scan ancestor optimization.

Missing necessary coverage: `tests/unit/test_continuity_byte_guard.py:120` only puts ordinary files in excluded directories. Add cases where a redirect is below each excluded directory and the included inventory remains unchanged; verification should preserve the original scanner's exclusion behavior. Keep the included empty-redirect regression at line 316 rejecting redirects.

### Important 2 — expired metadata/prepass work can start another expensive IO operation

Locations: `src/video_ai/runtime/_continuity_byte_guard.py:162` through line 170, and lines 98–101; helper lines 84–89.

The file loop checks time before `_safe()` and `stat()`, then proceeds directly to `hash_file()`. If path validation or metadata IO consumes the remaining interval, the full hash still starts after the deadline. Similarly, the final `lstat()` in `_reject_redirected_descendants()` can cross the deadline, return after iterator exhaustion, and immediately start `EvidenceReader.inventory()` without another time check. A scan that enumerates no yielded entries can also return without the helper performing a deadline check. Rejection after the subsequent call prevents accepting an expired proof, but it does not satisfy the brief's requirement to check between IO and after scans and can unnecessarily extend a blocked ownership check by another full operation.

Check the deadline after the pre-hash path/metadata validation and before starting `hash_file()`. Check it after the metadata traversal and before starting the existing whole-file inventory operation, including the empty/exhausted traversal path. Other multi-operation scanner boundaries should follow the same rule where practical.

Missing necessary coverage: deadline tests at `tests/unit/test_continuity_byte_guard.py:296` and line 340 only advance time inside the hash or original inventory call and verify eventual rejection. Add regressions advancing the clock during real pre-hash metadata/path work and during the last prepass metadata read, then assert the next expensive hash/inventory call is not started. These address avoidable work after expiry; they do not require asynchronous cancellation of an in-flight filesystem call.

### Minor — accepted-tree cost is still unmeasured

Location: `src/video_ai/runtime/_continuity_byte_guard.py:98` and line 101; report's remaining-concerns section.

The extra metadata traversal is linear additional work on every whole-file verification. The reported 0.33-second unit run on small temporary fixtures does not establish the intended reduction from the approximately 157-second full preflight. This is an explicitly disclosed integration measurement gap, not evidence that the implementation is too slow. Measure it on the actual accepted tree during the parent's already planned bounded preflight checks, after fixing exclusion handling. No benchmark or full-suite rerun is requested as part of this review.

## Adjudication and remaining coverage

Synchronous hash/reader calls being non-preemptible is not itself a defect under this brief: it expressly asks for checks between IO and after scans. The implementation allocates a fresh deadline and rejects after an overlong hash/inventory call; it does not reuse an old admission deadline. Important 2 concerns starting additional IO after an earlier operation has already exhausted that interval.

No demonstrated Critical security bypass was found in the supplied core. Existing tests materially cover content/mtime drift, replacement/hardlinks, inventories, absence, nested/error/late contexts, overflow poisoning, snapshot isolation, and copied-thread verification. Additional useful core coverage would exercise closure racing a copied-context observation, and overflow of the new empty-inventory/absence caps; their absence alone is not a blocker on the inspected locking and bound logic.

Critical integration coverage remains outside this package: prove no ready proof is installed for pending, failed, or legacy-none admissions; prove real observation hooks capture every actual dependency without unused historical originals; exercise `store.for_root` and read-only/historical base contexts; and retain original lock, POST/write, byte, mtime, alias, absence, and exact-inventory checks. The parent should verify those against its integration changes before claiming end-to-end acceptance.

## Scoped fix round 1 review

Verdict: APPROVED for the scoped Task 1 fixes. This supersedes the initial CHANGES_REQUESTED verdict for Important 1 and Important 2 only. No new Critical, Important, or Minor breakage was identified in this fix diff.

Reviewed `VCO-07-byte-proof-core-fix1-package-24c919fd93784feca41dc7ba3c24c0b5.txt` against the previously reviewed 54-test snapshots, plus the appended round 1 implementation report. This review was static: no tests were rerun, no implementation files were edited, and no agents were spawned.

- Important 1: ADDRESSED. The updated `_reject_redirected_descendants()` uses top-down `Path.walk()`, prunes `.git` and `__pycache__` from directory names before descent, ignores their excluded file names, and skips the descendant prepass when the root itself is within an excluded path component. Included descendants retain lstat/link/reparse rejection before descent. The original `EvidenceReader.inventory()` call remains intact. Both excluded-subtree redirect cases were added; the existing included-empty-redirect regression remains in the test file.
- Important 2: ADDRESSED. `ByteGuard.verify()` now checks the deadline after path validation and after metadata/ownership validation before hashing. The whole-file prepass checks after lstat and after traversal completion, including empty traversal, and `_scan()` checks before invoking the original inventory. Additional checks cover adjacent assessment/nonempty-file and path-validation IO boundaries. New regressions assert that expired pre-hash work and expired last-metadata/empty-scan work do not start the next hash/inventory operation.

Reported round 1 evidence: RED `vco07-byte-proof-core-round1-red-75e635d9b16d4079adf5f3fd8688ed81.log`, exit 1, 6 failed and 54 passed; GREEN `vco07-byte-proof-core-round1-green-85656d1c1817438483a06c6e710c4472.log`, exit 0, 60 passed with no skips. The implementer reports no source/test changes after GREEN. This review did not independently inspect or rerun those logs.

The previously recorded Minor accepted-tree traversal measurement remains assigned to Task 2 and deferred. Parent integration requirements and the VCO-08 full-suite deferral remain unchanged. This scoped approval does not claim production acceptance or playback validation.
