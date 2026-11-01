# VCO-07 Task 1 native live proof report

Status: DONE. Implementation and focused verification complete; independent
review and production timing belong to the controller. No production, GPU,
network, analysis, epoch, source gate, git, worktree or installation operation
was performed. All Python commands used bootstrap/Initialize/InvokeNative -B,
unique external basetemp and external pytest cache.

Files changed:

- `src/video_ai/runtime/_protected_continuity_inputs.py` (new).
- `src/video_ai/runtime/verification.py` (window initialization, writer
  lifecycle, final verification, and close hooks only).
- `tests/unit/test_protected_continuity_inputs.py` (new).
- This report. No plan ledger modification or commits.

Implemented behavior:

- `prepare_continuity_inputs(records, *, immutable_roots=())` registers only
  supplied actual records inside the existing invocation window. Source pins
  and directory handles are separate from ordinary protected entries. Caps are
  32768 extra pins, 65536 directories, 32768 qualified records; capacity misses
  retain existing leases and leave unqualified rows to strict verification.
- Newly pinned files are completely hashed under a deny-write/delete reader.
  Original size, mtime, SHA and both fstat/path ownership must match. The native
  file duplicate is installed only after the full fresh hash and path checks.
  Same-size/mtime changed bytes cannot become a new baseline.
- Every directory ancestor, including the volume root, is opened as the
  directory object itself with OPEN_REPARSE_POINT/BACKUP_SEMANTICS,
  GENERIC_READ, SHARE_READ|SHARE_WRITE, and no SHARE_DELETE. Canonical paths
  and directory/reparse attributes qualify the initial chain; anchored chains
  are checked again before installation.
- Every fast file verification checks live attributes on ALL held ancestors
  before and after the native file verification. Fresh path ownership and
  nlink, original identity fields, live file metadata and handle canonical
  path must all match. Directory child-list times and unrelated hidden
  attributes are permitted. Reparse/non-directory attributes are refused.
- Default fast verification returns False for unavailable/unqualified state,
  non-Windows, no/closed window, missing protection, and hardlink fallback.
  Mismatches against an active baseline raise ValueError/OSError.
- Controller-authorized interface extension:
  `verify_protected_continuity_file(record, *, prepare_existing=False)`.
  True only allows canonical ancestor qualification for an already live
  native entry. It cannot hash, create a new file pin, pin an ordinary owned
  mutable file, or establish semantic ready admission. Repeated hits do not
  repeat strict preparation; they still execute all live attribute checks.
- Ordinary writer promotion retains its previous eviction semantics. Fast
  qualification is revoked and unused directory handles are released. Only
  explicitly authorized immutable source pins survive nested writers. All
  release candidates are validated before any ownership is removed, so an
  error on a later candidate cannot strand an earlier pin.
- Existing window RLock serializes preparation, verification and shutdown.
  Final window verification checks extra pins and parent protection. Close
  clears all additional state and closes all handles even after another close
  fails. Late copied contexts cannot populate a closed window. No emitted
  ByteGuard/proof object retains handles or this state.

Native findings and fixes:

1. FILE_READ_ATTRIBUTES-only directory handles do not reliably participate in
   deny-delete sharing enforcement. A real preexisting DELETE-capable handle
   still allowed qualification with that access mode. The counterexample first
   failed (fast True), then passed after changing to GENERIC_READ. An empty
   directory lease separately proves rename/rmdir denial and later release.
2. GENERIC_READ does not freeze reparse attributes. The real isolated empty
   directory FSCTL_SET_REPARSE_POINT/FSCTL_DELETE_REPARSE_POINT test succeeds
   while our directory handle remains open. Live verification refuses the
   installed reparse point and accepts the clean directory after DELETE.
   Removing the live rejection in a controlled mutation made this test fail
   with DID NOT RAISE; the rejection was immediately restored.
3. This NTFS volume rejects FSCTL_SET_REPARSE_POINT on a nonempty directory
   with winerror 145. The test explicitly reports that optional native feature
   result, preserves the proof, and exercises refusal/final verification if a
   filesystem supports installing the nonempty reparse point. No Windows
   tests were skipped for path inconvenience.
4. Writer-promotion self-review found that validating/removing rows in one
   loop could leak a previous pin if a later row failed. A two-source native
   metadata counterexample first failed because first.bin remained locked;
   two-phase validation/removal fixed it. The same check also ensures ordinary
   extra pins are validated before writer release, matching ordinary entries.

TDD and verification evidence (all logs under
`D:/VideoSi/cache/video-ai/logs/`):

- Initial RED: `vco07-core-red-323b4fea8a3d4961b63d393a13d848be.log`:
  11 failed, each asserting native continuity protection is missing. This was
  an assertion failure, not a collection failure.
- Directory sharing RED:
  `vco07-core-boundaries-1b6ce3f7b3c54792bd0e7605d5a1ca67.log`:
  `test_unqualified_parent_open_falls_back_and_releases_partial_ancestors`
  failed because metadata-only protection wrongly returned True; 40 passed.
  GREEN `vco07-core-directory-share-green-1a53916985ba4a1cb6c69e7329e80932.log`:
  41 passed.
- Optional existing-only interface RED:
  `vco07-core-existing-red-bd9fc91ffb794750b3d06955591cf321.log`:
  three direct tests failed because the keyword was unsupported.
  GREEN `vco07-core-existing-green-65c3506df36e460791a5970483f281e3.log`:
  45 passed.
- Live reparse mutation RED:
  `vco07-core-live-attrs-red-b761116964eb477f89364a490de825e7.log`:
  `test_live_directory_query_refuses_fsctl_reparse_then_recovers_after_delete`
  failed with DID NOT RAISE when live refusal was removed. Restored thereafter.
- Writer validation RED:
  `vco07-core-promotion-red-995fc58065624114ac5b7e739f99162f.log`:
  `test_writer_promotion_validates_extra_ordinary_pin_before_release` failed
  with DID NOT RAISE; fixed by checking live state before release.
- Partial writer cleanup RED:
  `vco07-core-promotion-cleanup-red-2872542d217940ee993f6056899f65ce.log`:
  `test_failed_writer_promotion_does_not_lose_previously_validated_pin` failed
  because first.bin remained locked; fixed with two-phase release.
- A final metadata fixture initially attempted CREATE_ALWAYS on a hidden file
  after close, which Windows rejects independently of leases. The fixture now
  restores the hidden attribute before checking writeability. No production
  change was made for that fixture issue.
- Final GREEN:
  `vco07-core-task1-final-1aa0764782dc4c958cee4dbb51e9cdee.log`:
  **49 passed in 1.05s**, comprising 30 new tests and 19 existing
  `test_verification_session.py` tests. No warnings or skips. The optional
  nonempty-reparse case is explicitly reported as winerror 145.

The final command was:

```powershell
. .\scripts\bootstrap.ps1
Initialize-VideoAiEnvironment 'vco07-core-task1-final'
$taskTemp = New-VideoAiDirectory ('D:\VideoSi\cache\video-ai\temp\vco07-core-task1-final-' + [guid]::NewGuid().ToString('N'))
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest','tests/unit/test_protected_continuity_inputs.py','tests/unit/test_verification_session.py','-q','-s','--basetemp',($taskTemp + '\pytest'),'-o',('cache_dir=' + $taskTemp + '\cache'))
exit $script:VideoAiExitCode
```

Other runs used this same bootstrap pattern with a unique command/log name,
external temp directory, and the indicated focused file/-k selection.

Self-review checked bounds, lazy imports, canonical root-to-parent setup,
live before/after attributes, fresh source hash/ownership, ordinary writer
revocation, authorized immutable pin survival, file and directory native
identity, failure cleanup, final verification, no-handle proof ownership,
copied/late contexts and thread behavior. No remaining implementation issue
was identified. Full-suite and production timing were deliberately not run,
as the task authorizes only focused tests and prohibits production operations.
