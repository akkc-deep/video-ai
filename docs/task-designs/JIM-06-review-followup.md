# JIM-06 independent scoped follow-up review

Reviewed 2026-10-19. This follows `JIM-06-review.md` and the subsequent scoped reviews of admission/capture ordering, known PNG preflight, duplicate observation reuse, and composition guard propagation. The complete design and original 22-file package were read during the original review. This follow-up inspected the corrective implementation and narrow regression tests; it does not repeat or replace the original full review.

## Frozen review identity

- Package: `D:/VideoSi/cache/video-ai/logs/jim-06-fix-review-package.md`
- Package SHA256: `79CB7291FB28E5A3DC9DFAA9D9D15105BE9554B16A74981150D894DBEE197174`
- Package contains 22 source/test files. A read-only PowerShell hash comparison independently confirmed **22/22 current files match their packaged SHA256**, with no mismatch.
- The original package remains available as `D:/VideoSi/cache/video-ai/logs/jim-06-review-package.md`; findings in the first report describe those older bytes.

Key corrected implementation identities:

| File under `src/video_ai/runtime/` | SHA256 |
| --- | --- |
| `scene_media_records.py` | `5B1F962008259133F3B4388569C9A7B38BCA2B3640841F5C6384511CB466902F` |
| `_scene_upscale_records.py` | `29A8DDC134DE2213AF8E6C87598F2BCCBBCAAB01C51E42B5C76381F4256B31B9` |
| `scene_upscale_transactions.py` | `5B9C9AD1DE8A25E0EE93C868DD685CD66E16556E4262A64E9231500983F568C3` |
| `_scene_composition_commands.py` | `E7F1BFD6609C319E2C53006B0ED37E0DEB7D93E34CC865BA72A84A5EBA64A487` |
| `production_scene_composition.py` | `55A4435DBC155606B93A5B7914038CBCF4FB4FF5C77984E5FFCEC89229DF4AD3` |
| `production_scene_delivery.py` | `E57F28CABBCCC72993A6CA333349025E3FDE83748A3DA25D802900F1A02A37B1` |

## Closure of Important findings

### I1 — Whole-batch partial transaction and known-output preflight: closed statically

`validate_scene_frame_submission` now adjudicates retained evidence even without `submission.json`. Rejected POSTs, graph/output identity conflicts and retained execution failures raise a proved `SceneFrameTerminal` without writing a repair or making a request. The no-intent branch also refuses orphan body files. `validate_upscale_frames` can derive progress from raw terminal evidence, while production preflight stops before new paid work. The writer retains its original-task recovery path and can persist the original terminal when executing recovery.

The final delta closes the additional known-media window: `_pending_scene_frame_output` exposes the owned output proved by retained successful history. `_scene_upscale_records.py:160` validates that PNG when submission is missing, and the submitted-output branch validates PNG before looking for output-copy preparation. Both prefixes therefore stop on known incorrect format/dimensions before earlier missing frames can be submitted. Temporary local inspection errors remain resumable and do not manufacture a terminal or trigger another POST.

Reviewed regression coverage includes pending raw rejection/conflict/execution failure/orphan body cases and the two known-output prefixes crossed with incorrect format, dimensions and temporary tool failure. The latter explicitly asserts zero earlier paid submissions and service starts, with original evidence preserved. Existing original-UUID recovery and queue/history-race coverage remains present.

### I2 — Complete downstream byte guards and composition handoff: closed statically

The upscale acceptance facade now snapshots existing JSON before semantic admission, verifies that exact snapshot afterward, and adopts its original bytes while recursively capturing referenced raw evidence. Positive/empty HTTP bodies and command evidence therefore reach downstream guards. Captures use `bind_artifact` so a newer hash cannot replace an already captured identity.

Composition now carries candidate preparation staging state, absence guards, empty-log guards and tool stamps across stage roots. `_capture_composition_guard` compares existing identities/inventories, merges without overwriting authority, and runs a final byte/inventory audit even for lock-free readers.

The final delta closes the initial candidate-commit and new-command windows. `require_scene_composition_record` snapshots the six required composition records and commands/probes/media-ready inventories before `_commit`, then verifies/adopts the same snapshot and verifies again after handoff. An existing candidate commit is hashed before its semantic read and bound afterward. A newly written commit is bound to the exact expected serialized bytes. The immutable store serialization matches the `json_bytes` used for this new-commit proof. Complete candidate replay uses the read-only path; incomplete outer evidence retains the existing exact-recovery path.

Reviewed narrow regressions cover extant candidate staging mutation, promoted staging reappearance, changed candidate-commit/command JSON during handoff with old guard preservation, and a new command record appearing after semantic admission. These specifically address the timing gaps identified in review rather than merely testing mutation after capture.

### I3 — Final observation persistence, immutable capture and duplicate reuse: closed statically

Observation scans bind the actual raw bytes used for validation and retain an exact source inventory plus present/absent receipt identities. Their post-scan check prevents a new failed original, changed raw file or changed receipt from being adopted as fresh authority. Composition identities are merged using compare-before-bind helpers.

Decisive receipt writes now recheck the original store, exact scan snapshot and submitted raw identity after the final scan. Failed-raw receipt recovery also rechecks the original proof. The final delta adds the same checks before duplicate accepted/rejected results return. After legitimately creating a missing rejection receipt, `_consume` rescans to obtain its new exact receipt proof rather than retaining the obsolete absence snapshot.

Reviewed coverage includes post-scan upstream/raw/inventory/receipt changes, JSON-only composition rebinding, failed-raw repair races, and twelve duplicate-reuse mutations across accepted/rejected/raw-failed states. Three unchanged duplicate/repaired-rejection cases exercise the legal reuse path.

### I4 — Legitimately promoted staging artifacts: closed statically

Receipt-aware capture distinguishes historical staging identities from live target bytes. When a validated preparation receipt proves staging was promoted, it binds the target and records the staging path/directory as absent rather than hashing a nonexistent historical file. A surviving staging copy remains byte-bound. Reappearance of a captured absent staging path is refused, and absent guards propagate through store cloning and composition/observation handoff.

The narrow promoted-receipt test covers valid absent staging and later conflicting reappearance. The coordinator also reports a preserved authentic six-frame source context now admits successfully, with 284 positive Artifact guards, 93 empty-path guards and 12 promoted-path guards; that is coordinator execution evidence, not a command run by this reviewer.

## Additional guard findings from scoped review

The source admission-to-capture race is closed by capturing immutable JSON inventories/bytes before the semantic require calls and comparing afterward. Adoption parses the saved snapshot bytes and checks the snapshot again after recursive capture. This prevents a newly appended failed observation or changed JSON from becoming a trusted post-validation baseline.

Original PCM, whose older stamp lacks SHA, is hashed before those gates. `capture_unhashed_inputs` follows referenced log JSON to original command stdout/stderr and captures positive or empty bytes before semantic admission. `verify_admission_snapshot` compares these dependencies without requiring a write lock, preserving read-only public admission. Same-stat PCM replacement and previously empty command-log mutation are represented in the new gate-race regressions.

The original composition `command_finished` proof now remains guarded downstream. `bind_command_completion_proof` waits until encode and probe may finish appending their command events, hashes `events.jsonl`, revalidates both original intents/receipts and their unique successful command completions, verifies unchanged event bytes, and binds that identity for final acceptance/publication. It compares prior captures rather than rebinding a changed event log. Removal/change of original completion evidence is covered by narrow downstream-guard tests. No historical tool binary identity is invented; invocation-local tool stamps retain the clarified contract.

## Static verdict and verification boundary

**No remaining Critical or Important finding was identified in the reviewed frozen correction scope.** The original four Important classes and the additional scoped guard findings are closed by the implementation and reviewed regression coverage. The original Minor readability/test-double observations remain nonblocking; no unrelated refactor is required for this task.

**Static specification verdict: pass for the frozen reviewed changes.** Maintainability/test quality is adequate for this scope with the noted Minor observations. This is not a claim that the task has completed its required execution gates.

The coordinator reports the following narrow execution outcomes: Task 1 three unit files **80 passed in 7.58s**; observation/delivery quick batch **92 passed, 2 authentic deselected in 8.24s**; non-authentic composition recovery cases **7 passed in 0.94s**. I inspected the relevant tests but did not run those commands. Earlier intermediate counts are not substituted for the final required suites.

At this review's completion, the root agent's final authentic/long-chain/recovery, historical and full-suite verification is still in progress or pending. Its actual counts, exit codes and matching final hashes must be recorded separately before JIM-06 is marked complete. I ran no Python, media commands, model requests or test suites and changed no source/test files; only this follow-up report was written. No actual paid inference, genuine audiovisual viewing or real model-quality acceptance is claimed.

## Final snapshot addendum — test fixture tracking budget

The later frozen package is `D:/VideoSi/cache/video-ai/logs/jim-06-final-review-package.md`, SHA256 `DC293E4FBBF90F2C603FCF1BECE5DEB515A4C9E15E5F6A2E1167C6271847B9E5`. A fresh read-only PowerShell comparison independently confirmed **22/22 current source/test files match this package**. The earlier fix package is preserved.

Package comparison found exactly one changed source/test file: `tests/integration/test_scene_upscale_flow.py`, now SHA256 `D8B8AEFD2724D800402E7F9B8ED7B98660244EF3ADFA32C0147EE71DD4349066` (previously `E44DB100F09060EF8034448350FDF84AEF9D2ED09E75A17048886A1E58BFB16E`). Its only code change replaces the literal `timeout=10` in the deliberate terminal-write interruption setup with `timeout=setup['frozen'].config.timeouts['upscale_frame']`; two comment lines explain the production-budget alignment. All 13 production files are byte-identical to the reviewed fix package, as are the other eight test/helper files.

I inspected the retained log `D:/VideoSi/cache/video-ai/logs/jim-06-targeted-initial-timeout.txt`. The first targeted run reports **189 passed, 1 failed in 8718.12s**. The failing authentic conflict test reached the genuine tracking deadline guard and raised `SceneSubmitUnknown` while preparing its retained conflict, before the intended terminal-write `KeyboardInterrupt`. It was using its test-local ten-second tracking budget.

**Scoped verdict: this test-only correction is appropriate and does not weaken the business assertions or production timeout semantics.** The production entrypoint already passes the same frozen `upscale_frame` budget (configured default 180 seconds). The test still requires the deliberate `KeyboardInterrupt`, exactly one prior POST, absence of terminal/submission commits at that boundary, zero subsequent POST/service starts, unchanged conflict evidence, and blocked read-only progress with evidence and zero completed frames. It does not accept a deadline exception as success, disable a guard, shorten the evidence scan, alter deadline arithmetic, or modify any production code.

At this addendum, the root agent is separately rerunning that single corrected case. No result from that rerun is claimed here. The execution record must retain the original **189 passed + 1 failed**, followed by the actual separate repair-verification result; it must not describe the original targeted invocation as wholly green. The exact historical regression and fresh full suite, which includes all 190 new cases, remain for the root's serial verification. The test-only delta does not invalidate the static production closure above, and no new Critical or Important issue was identified. This reviewer ran no Python, tests or media commands.
