# VCO-07 byte proof core — Task 1 brief

Read this first. Implement only the two owned files below. Do not spawn agents,
change other files, run production, contact services/network, install packages,
create worktrees, commit, or touch .git. This existing workspace and .git read-only
restriction are authorized by VCO-07-design.md. Main task continues from saved
reports; do not restart VCO-07 or read its large handoff history.

## Purpose and owned files

The downstream media store currently calls full continuity admission for every
JSON write/HTTP ownership check. Its complete scene preflight costs ~157 seconds.
Replace repeated semantics with a read-only immutable proof of the actual files,
inventories and absences used by one successful initial admission. This task
implements the independent primitive; the parent will wire actual hash and
inventory observation sites and media store installation separately.

Create only:

- `src/video_ai/runtime/_continuity_byte_guard.py`
- `tests/unit/test_continuity_byte_guard.py`

## Frozen interface

Export:

```python
class CaptureLimit(ValueError): ...

@contextmanager
def capture_reads(*, maximum_files=32768, maximum_inventory_entries=65536):
    # yields a Capture; its finish() is available only after normal scope exit
    ...

def observe_file(identity): ...
def observe_inventory(path, kind, expected, *, pattern=None): ...
def observe_absence(path): ...
```

`identity` is a real runtime.manifest.FileIdentity or its five-field dict
`path/bytes/mtime_ns/sha256/verified_at`. All data fields are complete. Observe
the actual original baseline; duplicate observations must agree on path, bytes,
mtime and SHA (verified_at is descriptive). Capture stat ownership/nlink as
well so an added hardlink or file replacement cannot silently retain the same
content identity. Check that stat size/mtime agree with the observed identity.
Canonical absolute paths only; reject redirection and parent aliases.

The three observe functions are cheap no-ops with no active capture, including
no consuming an expected generator. Use ContextVar isolation. Nested scopes
must propagate actual read observations to both active captures, with bounded
and synchronized builders. A copied context used after its capture closes
must not populate a closed capture or mutate an emitted proof. Errors and
exceptions must always restore the previous capture state.

After normal context exit, `capture.finish()` returns an immutable `ByteGuard`.
Reject finish before successful closure or after exceptional closure. The guard
stores only immutable file identities/ownership, directory specifications and
absences: no decoded JSON, Reader, original 300-second deadline, window handles,
mutable collector dictionaries or bound verifier objects. Expose immutable
tuple data or read-only count properties as useful; the parent only requires
`guard.verify()` and may inspect counts for diagnostics.

`ByteGuard.verify()` performs fresh full hash_file checks (existing validated
operation/native-handle memoization remains in force), declared mtime and
ownership/nlink checks, exact current inventories and absence checks. Suppress
capture observations while it verifies, restoring any surrounding capture
afterward. It must be safe when invoked by copied HTTP thread contexts and must
not mutate the baseline. Use a fresh bounded verification interval of at most
300 seconds rather than retaining an expired admission deadline; check time
between IO and after scans. Never write or acquire a production RunLock.

On overflow raise CaptureLimit; never omit a dependency. Parent will fall back
to original full admission if a proof cannot be captured. Bound total unique
files and total inventory names; consume input iterables with an upper bound
rather than tuple-converting an unbounded generator first. Booleans are not
valid numeric limits. Repeated identical inventory keys do not charge again.

## Inventory kinds and exact semantics

`expected` contains strings/Paths already enumerated by the real validator.
Normalize/order them for exact set/sequence comparison; do not hold callers'
mutable containers. Guards use these scanners without any parsing:

- `children`: sorted all immediate `path.iterdir()` entries, files and folders.
- `json_direct`: sorted `path.glob('*.json')`, including matching invalid nodes.
- `assessment_paths`: sorted `path.glob('*/assessment.json')`.
- `nonempty_files`: sorted paths from recursive `rglob('*')` that are files and
  have size >0, exactly matching continuity terminal.outputs inventory.
- `revision_json`: sorted recursive `*.json` paths with the existing
  `scene_revision_records.safe_path(p, path)` path checks.
- `whole_files`: use the existing `_whole_scene_admission.EvidenceReader`'s
  `inventory(path, pattern or '*')` scan, preserving .git/__pycache__ exclusions,
  matching, file/path rejection, and the same-scan ancestor optimization.
  A new temporary EvidenceReader is fine, not an existing reader retained in
  the proof; suppress observation recursion during guard scans.
- `continuity_sources`: sorted `path.glob('*continuity*.py')` paths.

For glob scanners a nonexistent root naturally yields no paths; explicit
`observe_absence` covers cases where the original validator checks absence.
Reject redirected roots/parents and do not silently follow links while checking
inventories. New empty epoch/attempt folders must be detectable with `children`;
new non-JSON audit output must be detectable with `nonempty_files`.

All imports of manifest, revision helpers or admission readers must be lazy
enough to avoid circular imports once manifest.hash_file calls observe_file.
Do not change media modules: they are Engine identity inputs and existing
verified reports must remain reusable.

## TDD and validation

Read test-driven-development SKILL.md and writing-good-tests.md. Write tests,
run RED, implement the minimum, run GREEN. Use real runtime_run/tmp runtime files;
do not assert on fake guards or source strings. Cover successful repeated proof
checks, content drift, mtime drift with unchanged bytes, replacement/hardlink,
new JSON/raw/receipt, empty epoch/attempt directory, non-JSON audit output,
absence, snapshot immutability, nested/isolation/exception/late copied context,
bounded overflow, and thread-safe verification. Avoid model/service calls.

Run Python only through this existing PowerShell bootstrap:

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco07-byte-proof-core-red-or-green'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_continuity_byte_guard.py','-q','--tb=short',
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco07-byte-proof-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $VideoAiExitCode
```

No full suite: the user explicitly deferred it to VCO-08. Do not independently
review/spawn a reviewer; the parent will dispatch that review after your report.

## Report contract

Write `docs/task-designs/VCO-07-byte-proof-core-report.md`: status DONE /
DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED; owned files; exact interface;
RED/GREEN commands, log paths, exit codes/counts; important safety decisions,
remaining concerns. Do not claim production acceptance or actual playback.
Return only status, one-line test summary, report path and concerns. No commit
because .git is read-only.
