# JIM-06 integration review notes

These are coordinator inspection findings during implementation, not an independent approval or completed verification. Workers own the fixes and covering tests; final execution and independent review remain required.

| Area | Finding and required outcome | Current evidence |
| --- | --- | --- |
| Observation time bound | Exact serialized template has no candidate timestamp. Pass validator expected as `{template, created_at}` from admitted candidate; keep observation fields unchanged. | Design clarified; worker pure tests initially 24 passed, expanded cases pending. |
| Visual/PCM identity | Scene narration `bindings` must not become visual baseline bindings. Use selected_image.baseline_bindings; original ArtifactStamp has no SHA member, hash actual PCM. | Worker implementation and authentic-shape pure regressions added; expanded execution pending. |
| PNG terminal replay | Copied identity-conflict terminal path used undefined `template`; fixed node=5 image output must validate retained conflict evidence. | Upscale worker notified; expanded transaction suite pending. |
| Whole-batch preflight | A later orphan graph/HTTP/output or corrupted prepared copy must prevent all new frame POSTs. | Worker added full extant-component preflight; behavioral regression pending. |
| Temporary local failures | Generic ffprobe/decode/copy failure must retain original submission without terminal invalid_media or repeat POST. | Worker narrowed exception class; regression pending. |
| Extraction identity | Hash source before the entire inspect/extract/decode operation and after; verify every retained RGB24 pixel. | Worker accepted correction; real native media tests pending. |
| Accepted candidate recovery | Missing success/outer marker may only recover exact original successful evidence. Existing candidate/preparation must never trigger fresh encode or materialization. | Composition worker added retry restrictions and regressions; execution pending. |
| Publication guards | for_root copies guard dictionaries. Candidate/media/PCM/encoding captures must propagate back to common context before observation acceptance or output publication. | Composition/delivery workers added propagation and late-mutation tests; execution pending. |
| Empty logs | Positive Artifact entries omit legitimate empty command logs; capture their expected emptiness separately for late-send/accept/publish guards. | Shared guard_empty_paths added by owners; late append regression pending. |
| Read-only partial progress | Validate existing partial composition/transactions/raw failed observation, derive running/failed from evidence and reject corruption. Do not trust mere marker existence or mutable status. | Shared stage helpers integrated; final tests pending. |
| Early run validation | All public writers must validate the full prepared frozen run before lock acquisition or run/log identity assignment. | Delivery worker asked to use existing _run precheck; final tests pending. |
| Redirected paths | Base run_path resolves aliases within the same run. New store must reject lexical symlinks/junctions/reparse components before resolving even when target stays inside run. | Shared store owner notified; refusal tests pending. |
| Atomic JSON leftovers | Recognizable unaccepted store temporary files from fsync-before-rename interruption must remain preserved without permanently blocking valid recovery or counting as accepted records. | Shared store owner notified; interrupted-before-rename recovery pending. |

## Runtime test discipline

The team uses one serial Python/test lease. Every invocation bootstraps the project, uses Python -B and D:/VideoSi runtime/log/temp paths. No real inference/cloud/mail calls occur. The first authentic upscale diagnostic began with the original 66-frame fixture; subsequent short fixtures reduce initial synthetic PCM samples before writing real PCM and committing plans, while long_scene retains the upstream 200-frame chain. No accepted budgets or original text are changed.

Final serial verification runner: `D:/VideoSi/cache/video-ai/logs/jim-06-serial-validation.ps1`. It runs the targeted suite, exact historical list and fresh whole suite and compares source/test/workflow/usage SHA256 identities. It has been syntax-parsed only; no final test run is claimed yet.

## Additional admission and command-proof review

- Pre-admission JSON inventory/byte snapshots now prevent a semantic gate from admitting one version and later capturing a different version. Task 1 reported six observed RED cases and a 69-pass unit batch; these are incremental evidence, not the final combined gate. Original JSON bytes must drive recursive capture.
- Non-JSON bytes without an independently recorded SHA (original PCM and command stdout/stderr) also need capture before the semantic gate and recheck afterward. Coordinator inspection identified the remaining late-first-capture window; owner is checking and adding narrow regressions.
- Composition's unique successful `command_finished` proof resides in `logs/production/events.jsonl`. Retain its identity after both encode and probe complete, revalidate both original proofs against those bytes, and propagate it through final acceptance/delivery. Binding before probe would wrongly reject legitimate command appends. Owner confirmed the omission; narrow mutation/removal regressions and authentic receipt-ready mutation coverage are being prepared.
- Unknown/unprepared-run normalization for both final-observation consumption and delivery is being checked before run/log identity assignment and lock acquisition, using six narrow public-entry tests.

None of these entries records final acceptance or a test that has not actually run. Final authentic delivery, 200-frame, historical and whole-suite verification remain required.

Scoped independent rereview confirmed the initial raw-protocol adjudication, decisive receipt snapshot checks and promoted-staging corrections, but found two remaining Important boundaries. A known successful later-frame PNG must be decoded before treating either raw-success/no-submission or submission/no-output-ready as a resumable batch prefix. Reusing an existing final accepted/rejected observation must recheck the original store and observation snapshot after reading/validating the repeated external input. Owners are adding regressions and minimal corrections before source freeze. The newly repaired rejection receipt must be reflected in that replay snapshot.
