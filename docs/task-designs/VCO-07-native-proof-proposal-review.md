# VCO-07 Native proof fast path — proposal review

Status: CONDITIONAL DESIGN ASSESSMENT; NOT IMPLEMENTED OR ACCEPTED. No product/test edits, tests, experiments, network/GPU operations, or production commands were performed by this reviewer. This report evaluates the proposed change; it does not approve a live production replacement or claim a passing benchmark.

The review applied `designing-task-contracts` to separate supported premises from unresolved requirements. Inspected: the current `_continuity_byte_guard.py` verification path; `verification.py` NativeInput/window/session code; relevant inventory and transaction call sites; and the supplied parent-rename experiment result. Reported live PIDs, source-gate results, POST/intent counts, 31,209-file/33-inventory proof, and 15.968-second verification cost were provided by the parent and were not independently rechecked here.

## Assessment

Keeping every public `observe_*` check strict avoids the earlier capture regressions. Reusing a SHA from a continuously held Windows deny-write/delete handle is materially stronger than reusing a pathname or an earlier stat: the existing `_locked_reader()` uses `GENERIC_READ` with `FILE_SHARE_READ` only (`verification.py:261`), and `_NativeInput` duplicates that handle. A successful initial full hash under this protection, followed by uninterrupted handle ownership and live identity/metadata checks, can justify digest reuse. This is already the basis of the existing native window.

The proposal must compare the cached identity against the guard's original path, byte count, declared mtime and SHA, and independently compare current regular-file type, full guard ownership tuple, and link count. `_NativeInput.verify()` at `verification.py:98` currently checks path stat device/inode/size/mtime, native BasicInfo, and normalized handle path. It does **not** itself check nlink, uid/gid, or every ancestor's reparse flag. The proposed wrapper must provide those missing checks; calling `entry.verify(path)` alone is insufficient.

No concrete counterexample was established in this read-only review in which an initially strict canonical local-NTFS path, a continuously protected single-link file, matching live path FileID, and matching normalized handle path all survive a parent junction retarget to a different file. A retarget to a different object fails FileID; another hardlink is excluded by nlink=1; moving the original directory is blocked in the supplied experiment. Nevertheless, identity equality and a single rename experiment are not a complete proof that every forbidden ancestor reparse mutation is prevented. The remaining alias question below must stay explicit.

## Critical

No demonstrated Critical bypass was found in the unimplemented proposal. This is not a safety certification of code that does not yet exist.

## Important 1 — ancestor reparse protection is not established by the supplied experiment

`D:/VideoSi/cache/video-ai/temp/native-parent-protection-e1834a9d54564a63b385561d8a8727c9/result.json` records `parent_rename_blocked: true`, `PermissionError`, and WinError 5. This confirms that particular rename attempt. It contains no evidence about setting or deleting a reparse point in place, changing more distant ancestors, or other filesystem types.

Deny-write/delete sharing belongs to the **file handle**. A junction update operates on an **ancestor directory**. It must not be assumed to have identical sharing behavior without establishing the applicable NTFS operation constraints. Existing `entry.verify()` does not inspect those directory attributes, and `GetFinalPathNameByHandleW` describes the held file's normalized name rather than returning an attestation that each lexical ancestor is an ordinary directory.

Necessary constraint: restrict the optimization to the supported local Windows filesystem/handle semantics, an initially strict alias-free baseline, a continuously held valid deny-write/delete handle, and baseline **and current** nlink=1. Preserve strict fallback for preexisting multiple links. Either demonstrate that an originally ordinary ancestor cannot be converted/replaced into a redirect while preserving all fast-path predicates, covering `FSCTL_SET_REPARSE_POINT`/`FSCTL_DELETE_REPARSE_POINT` and ancestor replacement, or continue fresh strict ancestor checks. A blocked rename alone does not close this question. Do not manufacture a successful attack claim: this review has not run or proved one.

Any behavioral test should use disposable runtime trees, attempt the actual directory operation, and require either the OS to prevent the mutation or verification to reject it before a guard succeeds. Include the immediate parent, a higher ancestor, leaf redirection/replacement, and a short-name alias. No such experiments are authorized or executed by this report itself.

## Important 2 — a newly acquired source pin needs a new authenticated digest

Actual `guard.files` membership proves what admission read, not that current bytes still equal that baseline when a later pin is acquired. A concrete failure sequence if this requirement is omitted: admission hashes bytes A; before pinning, the file changes to same-length bytes B with restored mtime and unchanged inode; the code opens a new protected handle, captures its current native stamp, but attaches the old guard SHA for A. Subsequent NativeInput checks all describe protected bytes B while reporting SHA(A). The immutable proof's current ownership/size/mtime checks cannot repair that false association.

For each new pin, open the mandatory deny-write/delete reader, perform a complete digest under that very handle, compare path/bytes/mtime/SHA and ownership/nlink with the original guard, then retain its duplicate without a protection gap. Native stamp/metadata and current path identity must remain consistent through acquisition. Alternatively reuse an existing continuously protected entry whose authenticated full identity already matches that guard. Never construct a new `_NativeInput` from old SHA plus a newly sampled stamp without the full digest.

Require a regression where bytes change after admission but before pin acquisition with size and mtime preserved. Pin installation must fail, leaving no accepted stale-SHA entry. Pinning must not change or refresh the original proof baseline.

## Important 3 — explicit writable-root exceptions need an exact lifetime and eligibility contract

Current `_WholeInputWindow.enter_writer()` (`verification.py:153`) evicts entries below the writer root, and `_whole_cached_identity()` (`:212`) excludes owned roots. Retaining explicit source pins under an active writer is a deliberate new exception to both behaviors. A directory-name whitelist such as `scene-clips` or `scene-continuity` is not alone evidence that every contained file is immutable: mutable aggregate state, intent/event files, or an unfinished epoch may share an upstream namespace.

Necessary constraints:

- Install pins only after a complete successful semantic admission, from the exact immutable proof and semantically closed upstream epoch/archive/source files. Check exact canonical path components and file roles, not string prefixes or recursive manifest originals. A nested mutable manifest/event file remains excluded even under an allowed directory. New upscale/composition artifacts remain excluded.
- Keep the ordinary writer exclusion/eviction unchanged. Only explicitly installed immutable pins may survive nested writer entry; do not make all owned files eligible merely because a pin table exists.
- Store and synchronize pins in the existing window, not in ByteGuard. Under the same RLock, check window-open state, entry membership, handle liveness, writer eligibility, complete expected identity, ownership/nlink and the native verification result. Prevent close/eviction from invalidating a handle during use; late copied contexts cannot repopulate a closed window.
- Give added pins a separate unique-entry cap of 32,768 without evicting the existing 32,768 primary entries. Avoid double-owning/closing a shared entry. Capacity/open failures may leave files on the strict path; they must never remove dependencies from the proof or turn them into unchecked successes. Close all new handles on installation failure and all remaining handles on window exit.
- Distinguish **ineligible/cache miss** from **validation failure**. Non-Windows, missing/closed window, unprotected/owned non-pin file, or multiple links can take the original strict path. An eligible entry with changed identity, native metadata, canonical path, link count, or guard SHA must reject; do not suppress that evidence as a harmless cache miss.

Test nested writer entry/exit, cross-thread close/verification, failed admission and pending/legacy-none non-installation, pin overflow, partial acquisition failure, and rejection of every excluded mutable role. No such new behavior has been implemented or tested for this proposal in this review.

## Deadline and smaller alternative

Preserve a new per-verification deadline, observation suppression, exact inventories and absences on every invocation. Check time after waiting for the window lock and after native IO, and before starting the next operation. The RLock serializes window state; it does not itself freeze the filesystem. Native calls remain synchronous, so the same post-call expiry limitation applies. Keep the frame's existing 180-second deadline and every ownership/POST/write guard; do not solve repeated verification cost by removing guard sites or extending that transaction deadline here.

A smaller first change is to use only already-protected **external** entries, with no new owned-file pins, and retain fresh `safe_path(path, path.anchor)` ancestor/leaf checks around each eligible native check. The strict immutable baseline supplies spelling validity, and the live native canonical name can replace redundant path-resolution work only while identity/ownership/link predicates remain valid. All ineligible files keep the current full path. This narrows the new trust boundary, retains explicit ancestor rejection, and avoids changing nested-writer semantics. Measure its actual benefit before deciding whether the additional pin mechanism is necessary; no speedup is guaranteed here.

Another possible design is to hold explicit bounded protection on the distinct ancestor directories for the reuse interval, but its exact access/share modes, reparse handling, and interference with legitimate child creation/writes would themselves need design and validation. A once-per-scan parent cache without such protection would reintroduce the earlier transient-alias gap.

## Acceptance boundary

The proposal is not implementation-ready for removal of all ancestor checks until Important 1 is resolved. SHA reuse is defensible subject to continuous native protection and the full comparisons above; source pins additionally require Important 2 and Important 3. No Minor issue is raised merely because the 15.968-second measurement shows pressure on the frame budget. That measurement motivates optimization but cannot establish security equivalence. Final acceptance requires implementation review and focused native evidence, followed by the already authorized runtime validation workflow; this report does not run or authorize those steps and does not claim production or playback success.
