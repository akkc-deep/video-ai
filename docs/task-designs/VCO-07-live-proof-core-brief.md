# Task1 native live proof brief

Own ONLY new src/video_ai/runtime/_protected_continuity_inputs.py, minimal
src/video_ai/runtime/verification.py lifecycle changes, and new
tests/unit/test_protected_continuity_inputs.py. Do not edit media, ByteGuard,
scene_media_records, production state, operators, source data or other tests.
Repository D:/code/py/video-ai; runtime D:/VideoSi. All Python via bootstrap.ps1,
Initialize-VideoAiEnvironment and Invoke-VideoAiNative -B. Unique external
basetemp and external pytest cache. No installs/git/worktree/GPU/network or
production operations. Existing default model/effort; do not override.

Expose:

```python
prepare_continuity_inputs(records, *, immutable_roots=()) -> None
verify_protected_continuity_file(record) -> bool
```

records are immutable duck-typed _File rows: path(str canonical absolute),
bytes(int),mtime_ns(int),sha256(str),ownership(tuple of dev,ino,nlink,uid,gid).
False means unavailable/unsupported optimization; caller does its unchanged
strict _safe/fullhash path. A mismatching active baseline raises ValueError or
OSError, never returns success. Imports remain lazy to avoid manifest cycles.

Use existing verification._whole_inputs active Window and its RLock. No active
window, non-Windows, closed window, missing native entry/parent protection,
hardlink nlink!=1: return False. Do not weaken ordinary writer exclusion or
evict existing protected entries. Keep extra source file pins separately with
cap32768, directory handle cache cap65536, total records bounded; capacity miss
falls back, never drops a ByteGuard dependency. Extra handles belong solely to
window and close on window.close even on exceptions, copied late contexts and
partial setup. Final window.verify also validates extra protection, ignoring
permitted directory child-list timestamps but rejecting redirects/reparse attrs.

For current owned-run paths, only exact actual records inside immutable_roots
can acquire a special pin. Main will pass scene-continuity, scene-clips,
scene-revision, scene-rendering and exact frozen options/script paths, excluding
mutable manifest/events/upscale/composition/delivery. Outside writer-owned roots,
already protected native entries may be reused; if a new extra pin is needed,
it must still be an actual supplied admitted record. Never follow manifests or
discover unrelated source files. Source pin opens deny-write/delete handle and
FULLY HASHES under it, comparing path/bytes/mtime/SHA AND fstat/path ownership
against original record before accepting the new NativeInput; no stamp-only
rehash shortcut. Reuse existing same live native entry only after comparison.

For a fast check, anchor every existing directory ancestor by canonical
deny-delete directory handles, created after strict path checks. Validate
canonical directory path and reject reparse/non-directory objects initially;
before and after EVERY file verification query LIVE attributes on ALL its
ancestor handles, rejecting reparse points. Handles prevent ancestry replacement;
attributes remain mutable and must never be cached as permanently clean. Then
native entry.verify checks current file ID/size/mtime, handle canonical path,
native metadata; compare expected identity SHA/size/mtime/path and fresh ownership/
nlink. Preserve before/after file ownership checks where needed. Fast success
requires all of these; else strict fallback. Keep deadline control with caller;
no old reader/deadline/JSON cache.

IMPORTANT empirical evidence: check-directory-read-protection.py isolated
experiment e26055a55c90492c8e1a98829dbee94d showed directory GENERIC_READ with
SHARE_READ still permits FILE_WRITE_ATTRIBUTES handle and FSCTL_SET_REPARSE_POINT;
ordinary GENERIC_WRITE denied32, child creation allowed. Thus a read-only dir
handle alone is not enough: query live parent attributes for every verification.
Ancestor handles deny deletion/renaming so path objects cannot be swapped. Root
canonical check and parent chain anchoring must be robust to setup races; fail
closed or fall back if any qualification cannot be proved.

TDD tests: no window/fallback; real external native entry fast verifies and
rejects forged SHA/mtime/bytes/ownership; owned source pin denies writes and
fresh-rehash mismatch cannot be sealed (same size/mtime mutated between capture
and pin); mutable unlisted owned paths stay writable; nlink!=1 strict fallback;
close releases handles and proof retains none; nested writer/late copied context
and thread behavior; caps/failure cleanup; parent rename/leaf replacement blocked
under protection; actual FSCTL_SET/DELETE_REPARSE_POINT on an empty directory
handle proves live attribute query (test helper safe isolated paths), and any
supported nonempty reparse case must be refused; unrelated parent hidden/mtime
changes should not be falsely rejected if original strict policy permits them.
Never assert on mock behavior. Prefer native fixture counterexamples. No skip
on Windows simply because paths are inconvenient; unsupported optional native
features may be explicitly reported with fallback tests.

Read exact plan VCO-07-live-proof-plan.md and relevant existing native code. Write
failed-first tests, record logs, implement, run focused new+verification_session
tests, self-review, and report DONE or issues. Save report at
docs/task-designs/VCO-07-live-proof-core-report.md. Do not edit plan ledger.
