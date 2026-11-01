# VCO-07 Task 1 independent native core review

Review date: 2026-10-31. Verdict: **APPROVE Task 1**. No Critical,
Important or Minor implementation finding was identified within this review.
This verdict does not approve Task 2 integration, production timing or resume.

Reviewed the live-proof brief, plan and implementation report, the complete new
native core and its tests, and the existing native window/read protection.
Applied the requesting-code-review reviewer criteria and fresh verification.
The saved `verification.py.bin` was read only as text data; it was not imported
or executed. Its complete textual comparison with current `verification.py`
shows only the four stated initialization/writer/verify/close hook additions.
No product/test source was edited by this reviewer. No production, network,
GPU, installation, commit, checkout or full-suite operation was performed.

## Strengths and inspected boundaries

- `_protected_continuity_inputs.py:54`: directory opens use GENERIC_READ,
  SHARE_READ|SHARE_WRITE without SHARE_DELETE, and BACKUP_SEMANTICS plus
  OPEN_REPARSE_POINT. Canonical directory qualification at lines 64–72 and
  root-to-parent setup/revalidation at lines 162–212 cover every ancestor,
  including the volume root. Directory timestamps and unrelated attributes
  are correctly excluded from the protection baseline.
- `_protected_continuity_inputs.py:129`: every fast verification queries all
  held parents before and after the file checks. The native file's original
  identity, live handle metadata/canonical path and fresh path ownership are
  checked; directory attributes are never cached as permanently clean.
- `_protected_continuity_inputs.py:189`: new pins hash the entire file under
  `_locked_reader` deny-write/delete protection. SHA, size, mtime, fstat/path
  ownership and file stamp checks precede installation. Restored size/mtime
  cannot seal changed content as the old SHA.
- `_protected_continuity_inputs.py:102`: ordinary writer promotion validates
  the complete release set before removing ownership. Only separately acquired,
  explicitly immutable pins survive. Ordinary native entries retain their old
  eviction behavior in `verification.py:154`; qualification cannot bypass it.
- `_protected_continuity_inputs.py:153`, `:220`, `:227`, `:249`: capacity misses
  preserve existing dependencies; failed preparation closes pending handles;
  absent protection returns False; active baseline mismatches raise. Extra
  state remains bounded and owned solely by the invocation window.
- `_protected_continuity_inputs.py:258` and `:276`: preparation and fast checks
  take the window RLock and reject closed contexts. `verification.py:174` checks
  extra protection at successful window exit; `:181` closes remaining native
  resources even if another close raises. Late copied contexts cannot add pins.
- `_protected_continuity_inputs.py:158`, `:276`: `prepare_existing=True` can
  qualify only an already live entry, cannot enter the fresh-file/hash branch,
  and does not authorize an ordinary writer-owned file. Repeated hits retain
  the before/after parent checks.

## Issues

- **Critical:** none identified.
- **Important:** none identified.
- **Minor:** none identified.

## Fresh independent verification

Executed through `scripts/bootstrap.ps1`, `Initialize-VideoAiEnvironment` and
`Invoke-VideoAiNative $VideoAiPython -B`, with unique external basetemp and
pytest cache. Only these focused test files ran:

- `tests/unit/test_protected_continuity_inputs.py`
- `tests/unit/test_verification_session.py`

Result: **49 passed in 1.07s**, exit code 0, no skips or warnings. Log:
`D:/VideoSi/cache/video-ai/logs/vco07-core-independent-review-93ed5096e9564921967e493930b065d3.log`.
Native tests include writer revocation, explicit immutable pins, live directory
reparse installation/removal, deny-delete protection, fresh-hash rejection,
capacity/partial setup, invalid native close, late contexts and copied threads.

On this NTFS volume the nonempty-directory reparse operation reports winerror
145. The empty-directory test demonstrates live FSCTL attribute changes under
the actual lease. Per-file/final refusal on a filesystem permitting nonempty
reparse installation remains a conditional test branch, not claimed as executed
here; its call path was inspected statically.

Reviewed file SHA256 values:

| File | SHA256 |
|---|---|
| `src/video_ai/runtime/_protected_continuity_inputs.py` | `FC7348233487C90B0F70A7A1630BB1F3F58C16C0989B5D8CB51B851242534299` |
| `src/video_ai/runtime/verification.py` | `B1DBE2E98896BAB3A5CFFCFEA6EE7770E96EF0187941DA18364F2AAE48025EA0` |
| `tests/unit/test_protected_continuity_inputs.py` | `74914E819547007F3874172D2C5F4C7FD500579542A889DA95CC1D35BE1C8EA0` |

## Declined to judge and required interface constraints

1. **Task 2 ready-proof installation:** implementation belongs to the controller.
   Preparation must receive only actual immutable captured records after full
   successful semantic admission and initial strict verification, followed by
   reverification before installation. Pending/failed/overflow captures must
   never acquire ready status merely because a native file check succeeds.
2. **Immutable root selection:** this core trusts the caller's explicit roots;
   it does not independently know workflow mutability. Pass canonical intended
   immutable upstream roots/exact frozen files only. Mutable manifests, events,
   upscale, composition and delivery must remain outside that authorization.
3. **ByteGuard/observation consumers:** every False must retain the original
   strict path and hash fallback; active mismatch exceptions must propagate.
   `prepare_existing` proves physical protection only and must not replace
   semantics or relax public observe_* checks. Proof objects remain data only.
4. **Inventories, absences and timing:** file leases do not prove directory
   inventories or absent paths. Existing inventory/absence checks and caller
   deadline checks must remain. Actual 31,209-file performance and unchanged
   transaction budgets require separate measured acceptance; these tiny tests
   do not establish production latency.
5. **Media callback/write changes:** only identical callbacks may be combined;
   distinct callbacks still run. Preserve the final write/POST guard, caller and
   RunLock checks, and test serialization-time mutation and frame POST drift.
   These concurrently edited interfaces were not adjudicated in this core review.
6. **Production recovery/resume and final delivery:** outside this read-only
   task. Audit saved inputs and source receipts, recover the dead RunLock using
   the established mechanism, freeze/review final integration, and obtain real
   processing/publish/replay evidence under Task 3 before declaring VCO-07 done.

The core is ready for integration review: its safety decisions follow the
specified native protection contract, and focused real Windows verification
passed independently. No required Task 1 fix remains from this review.
