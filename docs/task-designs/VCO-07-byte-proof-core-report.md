# VCO-07 byte proof core report

Status: DONE_WITH_CONCERNS

Implemented the independent primitive only. Integration, production acceptance,
actual playback, and the full suite were not performed. No services, network,
GPU, package installation, worktrees, commits, or .git writes were used.

## Owned files

- `src/video_ai/runtime/_continuity_byte_guard.py` (new)
- `tests/unit/test_continuity_byte_guard.py` (new)
- This required report; no other existing file was changed by this task.

## Exact interface

```python
class CaptureLimit(ValueError): ...

@contextmanager
def capture_reads(*, maximum_files=32768, maximum_inventory_entries=65536): ...

def observe_file(identity): ...
def observe_inventory(path, kind, expected, *, pattern=None): ...
def observe_absence(path): ...
```

The scope yields `Capture`; `capture.finish()` returns `ByteGuard` only after
successful normal closure. Failed observations poison every active builder even
if their exception is caught. `ByteGuard.verify()` returns `None` on success and
raises on changed dependencies or expiry. File/scanner failures can propagate
`ValueError` (including `ProductionRefused`) or `OSError`.

The frozen guard exposes immutable `files`, `inventories`, and `absences` tuples
and read-only `file_count`, `inventory_count`, `inventory_entry_count`, and
`absence_count` properties. Individual file and directory rows are frozen,
slotted dataclasses. No caller containers, builders, reader objects, original
deadlines, decoded JSON, bound verifiers, or native handles are retained.

All seven specified scanner kinds are implemented: `children`, `json_direct`,
`assessment_paths`, `nonempty_files`, `revision_json`, `whole_files`, and
`continuity_sources`. Whole-file scans call a new temporary
`EvidenceReader.inventory(root, pattern or '*')` and retain its matching,
exclusions, rejection checks, and same-scan ancestor optimization.

## TDD and verification evidence

Every invocation used the existing native PowerShell bootstrap, with this exact
command shape and the command name below substituted for `<name>`:

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment '<name>'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_continuity_byte_guard.py','-q','--tb=short',
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco07-byte-proof-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $VideoAiExitCode
```

Logs are under `D:/VideoSi/cache/video-ai/logs/`:

| Stage / command name | Log filename | Exit / result |
| --- | --- | --- |
| Initial harness run: `vco07-byte-proof-core-red` | `vco07-byte-proof-core-red-3bed79c858954d16b344cc1183a42d48.log` | 1; 40 setup errors because the module did not exist. Import was moved into test bodies before treating RED as valid. |
| Valid initial RED: `vco07-byte-proof-core-red` | `vco07-byte-proof-core-red-12bb57585af8496587cea54f89ca7062.log` | 1; 40 failures, all for the missing module, before implementation. |
| Initial GREEN: `vco07-byte-proof-core-green` | `vco07-byte-proof-core-green-637f4f0e4a43473abd43cb2020ec5d59.log` | 0; 39 passed, 1 skipped (Windows symlink privilege). |
| Scanner regression RED: `vco07-byte-proof-core-red-scanners` | `vco07-byte-proof-core-red-scanners-b334e06c490344009cdae0ed92256b45.log` | 1; 2 failed, 52 passed. Empty redirected descendants escaped assessment/whole scanners. |
| Scanner GREEN: `vco07-byte-proof-core-green` | `vco07-byte-proof-core-green-19dcf885248747ba9dfe787953ee6c6d.log` | 0; 54 passed, no skips. |
| Final GREEN: `vco07-byte-proof-core-green-final` | `vco07-byte-proof-core-green-final-c13ec58f37364f00991e6cdf4130f557.log` | 0; 54 passed in 0.33 seconds, no skips. |

The final run followed the refactor that avoids repeated full ancestor walks
over whole-file results already checked by EvidenceReader. No subsequent code
changes were made.

Tests use actual files beneath the bootstrap runtime temporary directory.
Coverage includes repeated verification; mutable-input snapshot isolation;
content drift with restored mtime; mtime-only drift; replacement and added
hardlinks; all inventory kinds; new JSON/raw/receipts; empty epoch/attempt
directories; non-JSON audit output; whole-file patterns/exclusions; nonexistent
glob roots; empty-file filtering; explicit absences; nested scopes; isolated
contexts; exceptions; late copied contexts; normal-closure-only finish;
boolean/invalid limits; bounded generator overflow; poisoned partial captures;
duplicate disagreement; declared-stat disagreement; parent aliases; root and
descendant redirection; suppression/restoration during successful and failed
verification; synchronized thread observations; copied-thread verification;
fresh verification intervals and deadline checks after hash/scanner IO.

The redirect tests use symlinks where available and Windows junctions otherwise;
the final run had no privilege-related skips. Deadline tests alter only the
clock and elapsed time around real hash/inventory operations; they do not
substitute fake guards or file contents.

## Safety decisions

- `ContextVar` holds active builders in parent-first order. Observations acquire
  their reentrant locks in that same order, then validate and update every live
  builder. Closing is synchronized with observation. Closed copied contexts
  ignore observations, including expected iterables, without changing a proof.
- Observation functions return immediately outside capture. Inventories copy
  and sort their input, consuming at most the remaining capacity plus one
  element. Repeated identical keys reuse their existing allowance. Overflow
  raises `CaptureLimit`, never silently truncates dependencies.
- In addition to the configured unique-file and inventory-name limits, absence
  count and directory-specification count are each independently bounded by
  `maximum_files`. This prevents unbounded growth through empty inventories or
  absences; the parent can use its specified original-admission fallback.
- Files retain original SHA, declared bytes/mtime, descriptive verified_at, and
  stat device/inode/link-count/uid/gid ownership. Current metadata must agree
  with the observed identity, and duplicate observations cannot replace the
  original baseline. Verification checks ownership and metadata around the
  existing full `manifest.hash_file` operation. Existing validated operation
  and native-handle memoization remain untouched.
- Paths must be absolute, canonical, and free of redirected ancestors or parent
  aliases. Revision path checks and all runtime-dependent imports are lazy.
- Assessment scanning checks each immediate directory before entering it.
  Whole-file scanning first performs a metadata-only descendant redirection
  check, including empty directories, before calling the existing reader. Its
  lstat checks do not repeat a full ancestor walk for every sibling.
- Every verification call suppresses observations with a token restored in
  `finally`, allocates a fresh deadline of `monotonic() + 300.0`, checks time
  around file IO and after scans, and never changes the baseline. It does not
  acquire RunLock or perform writes.

## Remaining concerns / integration notes

- The extra whole-tree lstat pass conservatively rejects redirected descendants
  even when they have no matching files. Its cost against the full accepted
  evidence tree has not been measured; parent integration should include that
  in its bounded preflight measurements. No accepted-tree performance or
  production acceptance claim is made here.
- The existing synchronous hash/reader calls cannot be interrupted mid-call by
  this primitive. An overlong operation is rejected at the next time check;
  no expired admission deadline is retained.
- Real observation hooks and media-store installation remain the parent's
  separate work. The full suite remains deferred to VCO-08 as instructed.

## Review fix round 1

Status: DONE_WITH_CONCERNS. Both Important findings in
`VCO-07-byte-proof-core-review.md` were reproduced and fixed in the two owned
core/test files. The remaining concern is the already assigned Task 2 accepted-
tree traversal benchmark; this round did not expand into integration work.

Changes:

- The whole-file metadata pass now uses a top-down `Path.walk()` and removes
  `.git` and `__pycache__` from directory names before descent. It also omits
  excluded file names and skips descendant checking when the supplied root is
  itself inside an excluded subtree, matching the original reader's path-parts
  exclusions. Included entries still receive lstat/reparse checks before
  descent, including empty redirected directories. The existing temporary
  `EvidenceReader.inventory()` call and its ancestor optimization are unchanged.
  This supersedes the original report's description of conservatively checking
  every descendant, including excluded metadata.
- Verification checks the fresh deadline after pre-hash path validation, after
  stat/ownership validation immediately before hashing, after the whole-file
  metadata pass, and immediately before starting the original inventory scan.
  The pass checks after each lstat and after completion, including empty scans.
  Adjacent scanner metadata boundaries also check time before further IO:
  assessment directory classification, nonempty-file classification/stat,
  post-hash path/stat, final root validation, and absence path validation.
- Six new regression cases use actual runtime files and real path/stat/scan
  operations. Two prove redirects below `.git` and `__pycache__` do not affect
  an unchanged included inventory. Two advance the clock after real pre-hash
  path/stat work and prove hashing is not started. Two advance it during the
  last metadata read or empty-directory scan and prove the original inventory
  operation is not started. Existing included-empty-redirect tests still pass.

Round 1 RED command (before implementation changes):

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco07-byte-proof-core-round1-red'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_continuity_byte_guard.py','-q','--tb=short',
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco07-byte-proof-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $VideoAiExitCode
```

RED log:
`D:/VideoSi/cache/video-ai/logs/vco07-byte-proof-core-round1-red-75e635d9b16d4079adf5f3fd8688ed81.log`.
Exit 1: **6 failed, 54 passed in 0.43 seconds**, no skips. Both exclusion cases
raised on excluded redirects; all four deadline cases demonstrated that the
next hash/inventory operation started after the earlier metadata work expired.

Round 1 GREEN command (after implementation changes):

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco07-byte-proof-core-round1-green'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_continuity_byte_guard.py','-q','--tb=short',
 '--basetemp',"D:/VideoSi/cache/video-ai/temp/vco07-byte-proof-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $VideoAiExitCode
```

GREEN log:
`D:/VideoSi/cache/video-ai/logs/vco07-byte-proof-core-round1-green-85656d1c1817438483a06c6e710c4472.log`.
Exit 0: **60 passed in 0.38 seconds**, no skips. No source/test changes followed
this GREEN run. No full suite, production, GPU, network, subagents, commits,
integration changes, or other file edits were performed during this round,
apart from this required report append. Synchronous IO remains non-preemptible;
the fixed boundaries prevent starting the next operation after prior work has
already expired the interval.
