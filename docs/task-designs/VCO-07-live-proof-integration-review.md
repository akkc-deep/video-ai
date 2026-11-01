# VCO-07 live proof integration review

Verdict: **APPROVE Task 2 integration**. No Critical, Important or Minor finding
was identified. This is a code/interface verdict, not approval of production
timing, recovery, resume, final delivery or completion of VCO-07.

Reviewed the live-proof plan, core brief/report/independent review, original
byte-proof plan, current native core/window interfaces, complete affected
ByteGuard/capture/store paths and focused tests. Task 1's independent 49-pass
approval is accepted for its native implementation; its use by Task 2 was
independently inspected. The native core and verification hashes still match
that approved review.

The four pre-live-proof `.bin` snapshots under
`D:/VideoSi/projects/video-ai/vco07-diagnostics/pre-live-proof-1d13fb4dfcfd480ea9c9e4fcec09fc8a/`
were read solely as text data for a complete unified diff. They were never
imported or executed. The diff contains exactly the planned ByteGuard native
hook/repeated-observation qualification, post-admission preparation, media
callback/write changes, and the four Task 1 window lifecycle hooks. Diff log:
`D:/VideoSi/cache/video-ai/logs/vco07-integration-review-diff-17045e1e7f8f454b8a94f24d4e55b956.log`.

## Findings

- **Critical:** none identified.
- **Important:** none identified.
- **Minor:** none identified.

## Interface and boundary assessment

- `src/video_ai/runtime/_continuity_byte_guard.py:180`: fast success requires
  the live native verifier. False continues into the unchanged strict canonical
  path, metadata/ownership, hash and final path checks; exceptions propagate.
  Deadline checks bracket the new call. Inventories and absences retain their
  original scanners and checks. Capture suppression is restored in `finally`.
- `_continuity_byte_guard.py:292` and `:314`: observations still validate the
  complete identity shape and numeric/SHA fields. Native reuse is considered
  only when **every active builder already holds the exact path**, all four
  identity fields match, and prior ownership agrees across builders. The
  native verifier checks live ownership and parent attributes. A new nested
  builder, unqualified/owned file, closed window or unavailable protection
  follows strict capture. Conflicts still poison all active builders; capacity,
  close and copied-context handling remain unchanged. `prepare_existing=True`
  cannot create a new file pin or confer semantic readiness.
- `src/video_ai/runtime/scene_continuity_records.py:704`: full semantic
  admission, before/after source inventory, argument-state comparison,
  successful capture closure, promotion-absence supplementation and an initial
  proof verification all precede source preparation. Only `guard.files` are
  passed, without discovery or expansion of declared historical references.
  The explicit roots at `:737` cover the specified immutable upstream source
  areas and exact options/script files; they exclude mutable manifest, events,
  upscale, composition and delivery areas. New source pins freshly hash under
  native protection through the approved core. Another verification follows
  preparation. Pending/failed admissions propagate; legacy None and overflow
  retain the complete original validator, with a fresh semantic admission on
  overflow. No partial capture is installed.
- `scene_continuity_records.py:747` and
  `src/video_ai/runtime/scene_media_records.py:435`: the returned callback
  checks frozen/unit/timeline state before and after proof verification.
  Installation follows the existing media snapshot recheck and another call
  to that callback. Argument drift during preparation cannot install a usable
  ready callback. The closure retains immutable proof data and typed state,
  not an old reader, deadline or native handle.
- `scene_media_records.py:116`: deduplication uses object identity, not callback
  equality. An identical callback executes once at its existing later position
  inside `verify_captured_bytes`; distinct callbacks execute in their original
  order. Revision, artifact, inventory, absence, empty-file, model and tool
  checks remain. `for_root` at `:316` carries the same callbacks and original
  caller thread; read-only verification does not require a write lock.
- `scene_media_records.py:295`: new JSON retains caller/lock/path checks,
  serializes with the same UTF-8/NaN/indent/newline policy, then reaches the
  existing final `write_bytes` continuity guard. Source or argument mutation
  during serialization is refused before output bytes are created. Existing
  records still run `assert_write` and semantic equality validation; direct
  bytes writes retain their guard. Base `SceneClipStore.write_bytes:65`
  preserves lock checks around its immutable commit. A target appearing after
  serialization is handled by that existing immutable-byte comparison.
- `src/video_ai/runtime/scene_upscale_transactions.py:420`: the original
  deadline is created once, checked before/after the send guard, and retained
  by `remaining`; cancellation remains installed for late transport callbacks.
  The request/graph/intent and service/POST guards remain. This file has no
  working-tree diff. Task 2 introduces no transaction timeout adjustment.

## Fresh independent verification

Ran through `scripts/bootstrap.ps1`, `Initialize-VideoAiEnvironment`, and
`Invoke-VideoAiNative $VideoAiPython -B`, with separate unique external basetemp
and pytest cache:

- `tests/unit/test_continuity_byte_guard.py`
- `tests/unit/test_continuity_byte_guard_wiring.py`
- `tests/unit/test_scene_continuity_records.py`
- `tests/unit/test_scene_media_records.py`

Result: **149 passed in 38.91s**, exit code 0, no skips or warnings. Log:
`D:/VideoSi/cache/video-ai/logs/vco07-live-integration-independent-review-6557404a57344aea9b910d4922d8bd4b.log`.

These tests exercise strict alias/ownership handling, transient inventory
redirection, capture limits and copied contexts, actual native protected reuse
and post-close fallback, ready owned-source pin lifetime, no ready pins for
pending/failed/legacy/overflow, source/mtime/argument drift at write and frame
dispatch guards, callback identity/distinct callbacks, clone/read-only paths,
serialization-time mutation, and caller-thread enforcement. Task 1's approved
native tests additionally cover bounds, fresh hash rejection, writer revocation,
late windows and live directory reparse behavior. The controller's reported
323-test run is supplementary evidence, not claimed as this reviewer's run.

## Reviewed identity and remaining acceptance

| File | SHA256 |
|---|---|
| `src/video_ai/runtime/_continuity_byte_guard.py` | `0CAFE3D2D8F51D6146E9337DB13A666F7B499A0EE85609B213167D5B272197AC` |
| `src/video_ai/runtime/scene_continuity_records.py` | `689FA0769DFBBB700EB8A03832B4C812F23D0F3E9EECCCA1B85F41DF9633B93E` |
| `src/video_ai/runtime/scene_media_records.py` | `D657812D23D65EFAAB2A31E3E07613EE02076C0AB052A2FDAC3C889AF100D28E` |
| `src/video_ai/runtime/_protected_continuity_inputs.py` | `FC7348233487C90B0F70A7A1630BB1F3F58C16C0989B5D8CB51B851242534299` |
| `src/video_ai/runtime/verification.py` | `B1DBE2E98896BAB3A5CFFCFEA6EE7770E96EF0187941DA18364F2AAE48025EA0` |
| `tests/unit/test_continuity_byte_guard_wiring.py` | `319728F8AFB23084629F545F746C13C9C3370D3BD813B82C5B83BEC1401A4C35` |

Actual current-run ready admission and proof timing remain separate Task 3
acceptance evidence. This review did not control the running benchmark, write
implementation/test files, run the full suite, touch production or its dead
RunLock, replay source analysis/reviews, invoke GPU/network work, or modify git.
Existing source readiness and Engine05a are preserved task inputs, not reapproved
or recreated here. Software freeze, saved-input audit, original RunLock recovery,
concrete media processing and final publish/replay still require their own
recorded outcomes.
