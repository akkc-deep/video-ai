# JIM-06 composition implementation evidence

Task 2 owns the schema-2 composition runtime and its two integration test modules. The implementation derives every contribution from admitted scene/clip and upscale evidence, copies unique frame sequences, verifies the original PCM sample bytes and zero silence/padding, derives subtitles with the existing private-font layout, and preserves unique original encode/probe outputs and immutable candidate preparation evidence. Candidate completion remains `awaiting_final_review` until an independently authored final observation is accepted.

## Commands and observed outcomes

All Python commands follow `. ./scripts/bootstrap.ps1`, `Initialize-VideoAiEnvironment`, and use `$VideoAiPython -B`. Team test leases serialize Python/media generation. Runtime, temporary files and logs remain under `D:/VideoSi`.

1. `Initialize-VideoAiEnvironment 'jim-06-composition-red'`; `& $VideoAiPython -B -m pytest tests/integration/test_scene_media_flow.py tests/integration/test_scene_composition_recovery.py -q --tb=short`
   - Observed exit 1, **2 collection errors in 0.08s**, both expected `ModuleNotFoundError: video_ai.runtime.production_scene_composition` before implementation.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-composition-red-3445e160090141a29fe17264fa6ece99.log`.
2. `Initialize-VideoAiEnvironment 'jim-06-composition-flow'`; `& $VideoAiPython -B -m pytest tests/integration/test_scene_media_flow.py -k test_candidate_preserves_original_pcm_subtitles_and_awaits_actual_review -q -x --tb=short`
   - Observed exit 0, **1 passed, 1 deselected in 325.86s**.
   - Authentic original scene budget was 6 frames (3+2+1), committed before admission. Original PCM was authored with distinct nonzero samples before the real timeline/image/clip admission, then checked byte-for-byte with every silence/padding interval zero.
   - Real 1920x1080 H.264/AAC candidate, full native media decode/CFR/PTS/AAC checks, exact SRT/ASS/private-font layout, unverified observation template and absent formal output paths all passed.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-composition-flow-b489a4f452784364a64ac844aa82e21e.log`.
   - Diagnostic tree only; common owner subsequently strengthened caller-thread/path/tool guards. Final-tree batch remains required.
3. Review I2 analogue, before the scoped fix: `Initialize-VideoAiEnvironment 'jim-06-composition-guard-red'`; `& $VideoAiPython -B -m pytest tests/integration/test_scene_composition_recovery.py -k test_candidate_ready_handoff_preserves_real_file_staging_guards -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest`
   - Observed exit 1, **2 failed, 1 deselected in 0.36s**. Both expected failures were `DID NOT RAISE ProductionRefused`: mutation of extant candidate staging and reappearance of legitimately promoted staging escaped the downstream base guard.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-composition-guard-red-7f600df1717d4585ac6bf0dbe27bccad.log`.
4. After the scoped fix, the same pytest selection with `Initialize-VideoAiEnvironment 'jim-06-composition-guard-green'`:
   - Observed exit 0, **2 passed, 1 deselected in 0.35s**.
   - `_capture_composition_guard` now checks both prior stage/base guards before recapture, receipt-captures candidate-ready with `capture_admitted`, and propagates positive files, JSON inventories, empty files, absent promoted staging and invocation-local tool stamps.
   - These are direct real-file/real-RunLock handoff tests, not media-generation or complete-admission substitutes.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-composition-guard-green-e4f9c70a01cd49e897193f1094d408cc.log`.
5. Original command-completion proof guard, before its scoped fix: `Initialize-VideoAiEnvironment 'jim-06-completion-proof-red'`; `& $VideoAiPython -B -m pytest tests/integration/test_scene_composition_recovery.py -k test_original_command_completion_proof_is_preserved_in_downstream_guard -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest`
   - Observed exit 1, **2 failed, 3 deselected in 0.38s**, expected `DID NOT RAISE ProductionRefused` for removing/changing the original encode completion row after initial capture.
   - The narrow fixture verifies a real authored `command_finished` row through `_completion`, then exercises the real-file/real-lock handoff. It makes no upstream media-completion claim.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-completion-proof-red-9b085cb1309a4d09a1eab2cb680c6487.log`.
6. The same event-proof selection after the fix, with `Initialize-VideoAiEnvironment 'jim-06-completion-proof-green'`:
   - Observed exit 0, **2 passed, 3 deselected in 0.36s**.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-completion-proof-green-7500e069e6fa43feb67d2aa721faefe1.log`.
7. `Initialize-VideoAiEnvironment 'jim-06-composition-guard-regression'`; `& $VideoAiPython -B -m pytest tests/integration/test_scene_composition_recovery.py -k 'not test_exact_evidence_recovers_missing_outer_record_without_reencoding' -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest`
   - Observed exit 0, **4 passed, 1 deselected in 0.53s**: both staging guard cases plus both original completion-proof guard cases.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-composition-guard-regression-7dc84c9ec6ce42fb982fdca4bf4a6fb5.log`.
8. Capture-rebind review regressions, before correction: `Initialize-VideoAiEnvironment 'jim-06-composition-rebind-red'`; `& $VideoAiPython -B -m pytest tests/integration/test_scene_composition_recovery.py -k 'capture_cannot_replace or admission_rejects_command_added' -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest`
   - Observed exit 1, **3 failed, 5 deselected in 0.45s**, all expected `DID NOT RAISE ProductionRefused`: candidate-commit mutation during handoff, command-intent mutation during handoff, and a new command JSON added after the semantic read scan.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-composition-rebind-red-e9ddca68e31d47098fd6f2a74daa0fd1.log`.
9. The same three-case selection after correction, with `Initialize-VideoAiEnvironment 'jim-06-composition-rebind-green'`:
   - Observed exit 0, **3 passed, 5 deselected in 0.41s**.
   - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-composition-rebind-green-9c6da195c0894c58984187cb9793c925.log`.
10. `Initialize-VideoAiEnvironment 'jim-06-composition-rebind-regression'`; `& $VideoAiPython -B -m pytest tests/integration/test_scene_composition_recovery.py -k 'not test_exact_evidence_recovers_missing_outer_record_without_reencoding' -q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest`
    - Observed exit 0, **7 passed, 1 deselected in 0.94s**. This is the complete narrow recovery-file batch; the authentic combined recovery case remains excluded.
    - Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-06-composition-rebind-regression-75a2a5080bab49228779054b132f043c.log`.

## Clarification

Successful ffmpeg commands at `-v error` can produce empty stdout/stderr. The global Artifact contract requires positive bytes. Following the existing scene-clip evidence helper, empty logs retain their exact `COMMAND_FIELDS` paths and must exist; only nonempty raw logs become strict Artifact entries. Receipt validation recomputes that evidence list from the original bound log paths, so changing a formerly empty log invalidates the receipt. No placeholder bytes or alternate record fields are written.

Command intent `inputs_sha256` is `canonical_digest({'materialized': materialized})` for encode and `canonical_digest({'materialized': materialized, 'encoded': original_encode_artifact})` for probe. The complete materialized record binds the composition inputs and contributions. This formula additionally binds every exact materialized file and the original encode inspected by probe.

The old frozen-input schema records configured tool paths, command evidence and model stamps, but does not record historical ffmpeg/ffprobe binary stamps. Invocation-local `ArtifactStamp` guards now verify those binaries before/after command execution and read-only media inspections. No historical tool identity is invented and no existing frozen schema changes.

Original command completion evidence is now bound after both encode and probe have finished. `bind_command_completion_proof` hashes `events.jsonl`, rechecks both original intent digests, success receipts and matching successful `command_finished` rows, and checks the same log hash afterward. The bound Artifact enters the composition guard and downstream base guard. Legitimate encode/probe event appends occur before this point; later composition/final-observation/delivery paths do not append media-command events. No persisted fields were added. Authentic integration of the binding helper and late delivery event-log mutation is left to the coordinator's pending full batch; the narrow tests establish the real-file guard handoff.

The final handoff uses `bind_artifact` instead of replacing prior byte authority, compares prior JSON inventories before extending them, and ends with lock-free `verify_captured_bytes` audits of both stage and base stores. Read-only composition admission snapshots all fixed composition JSON plus command/probe/candidate-ready inventories before semantic validation, then verifies and adopts exactly those original bytes afterward. Existing candidate-commit bytes are captured before its read/equality check; a newly written commit binds its original serialized `json_bytes` SHA. A complete writer replay takes the read-only snapshot path; missing-record recovery retains the writer path so legitimate new records and command attempts are not prematurely frozen.

## Remaining verification

Final-tree execution is pending for the full two-file composition batch (eleven pytest cases, including seven narrow staging/event-proof/capture-race guard cases). Recovery scenarios are consolidated into one authentic run to avoid repeating expensive admission setup: materialized-before-encode interruption, encode command-finished interruption, exact original encode recovery, probe command-finished interruption, exact original probe recovery, candidate-ready-before-promotion interruption, promoted-candidate-before-commit interruption, post-commit interruption, four missing outer marker/receipt repairs, two missing-original-evidence refusals with zero new commands, and narration byte tampering. Every case retains its fresh full public admission and explicit stage-labelled assertions. Ready bytes/timestamps, the single materialization attempt and the original command intents are asserted unchanged.

Offline fixture observations validate protocol and recovery behavior; they do not claim actual model or final-film visual acceptance.
