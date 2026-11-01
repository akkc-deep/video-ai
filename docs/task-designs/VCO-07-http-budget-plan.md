# VCO-07 real HTTP frame-budget Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline with TDD, one fresh review of this new delta after tests. No implementer delegation.

**Goal:** Fit actual guarded whole-scene HTTP exchanges into the original180s tracking interval while preserving every actual-write/send input proof.

**Architecture:** Opt in only the default concrete SceneComfyClient used by explicit whole upscale to full ownership checks at every socket write; waiting/read phases retain deadline/cancel checks, and caller media writers retain their complete proofs. Prepare only the first fresh whole frame's owned service under its existing startup phase before calling the unchanged frame tracker. Defaults, segmented, custom factories, old intent handling, raw evidence and all protocol code remain.

**Tech Stack:** Existing Python HTTPConnection/Thread/ContextVar, SceneMediaStore, owned service and pytest/local HTTPServer. No dependencies.

**Spec:** docs/task-designs/VCO-07-design.md

## Global Constraints

Original180s frame protocol byte-for-byte unchanged; existing300s service startup not enlarged. No reset of existing intent, source/epoch/viewing regeneration, git writes/worktree/installs/full suite/VCO-08 or production until new review/control/freeze. Keep current225 state and exact signed AweSun run approval38b31692.

## Review Focus

1. Source/lock loss during connect or before POST body must prevent that actual wire write, including a slow complete guard using the last deadline.
2. A cancelled/blocked DNS or response reader must never resume a late send or write caller-owned evidence.
3. Raw memory responses are not acceptance: input drift after a POST must stop the caller's protected raw/acceptance write.
4. Fresh whole bootstrap must not start services on completed replay, alter segmented behavior or reset an existing intent's tracking boundary.
5. Unknown custom transports must retain original full-phase behavior; opt-in is rejected for delegated transports and factories receive no new required argument.

## Exact implementation interfaces

- Modify src/video_ai/adapters/scene_comfy.py: optional keyword send_checks_only=False, strictly bool; True requires http=None. Full callback remains before every concrete HTTPConnection.send, bracketed by deadline/cancel checks. A phase_guard uses the old full callback by default and only deadline checks for explicit opt-in waiting/reads. copy_context, raw body/length/JSON_LIMIT and caller cancellation/connection closure remain.
- Modify src/video_ai/runtime/production_scene_upscale.py::_produce: for explicit whole, service is None and current frame intent absent, call existing ensure before the unchanged frame transaction. Pass send_checks_only=True only to the default concrete client in whole mode. Service start/cleanup and all original source checks remain.
- Create tests/unit/test_scene_comfy_send_checks.py and test_scene_upscale_service_preparation.py; use real loopback transport for writes/read chunks/drift/cancellation and explicit producer-order controls for fresh/segmented/pending/replay.
- Diagnostic check-real-http-frame-budget.py uses real concrete client, real guarded logger, measured unchanged store costs,270 globals/two319178-byte PNG fixtures and2MiB remote schema. Socket destinations restricted to its ephemeral fixture server. cold0 explicitly charges78s preparation before tracking, without changing180s; no production service or model POST.

Use executing-plans inline, systematic-debugging, TDD and one fresh review of any new production delta. No git writes/worktrees/installs/full suite or VCO-08. Main spec: VCO-07-design.md. Existing repaired native/coverage/send-artifact scopes and their69/201/154 results remain accepted; do not re-review them.

## Observed failure and boundaries

Production27558/worker38868 ended18:27:51 exit2; phase06319e054a6f476ab6a7c2c765f8e3cc resultSceneSubmitUnknown: remote object_info unavailable before intent: original frame tracking deadline exceeded. GPU admission succeeded, owned Comfy12428 started18:25:11 and healthy18:26:06, then stopped normally with lease released.0intent/0upscalePOST/0completed,225 preserved files, source3POST/bytes and Engine05a retained. No active production remains. No user desktop action is required.

The old179.212-second fixture modeled Client rather than real SceneComfyClient and logger=None rather than _GuardedLogger. It counted one full callback per API, omitted real connection/send/read-chunk checks and guarded log writes, and assumed30s startup. Actual cold import alone54.1s, GPU-acquired-to-healthy77.2s, not a complete ensure timing. The old model is insufficient; do not repeat it or the unchanged1111s context profile.

Preserve every actual send's full source/request/graph check, RunLock, caller-thread evidence writes, cancel/deadline-before-and-after guards, strict chunk/JSON limits, no late sends, no retries and original intent recovery. Frame protocol180s and existing service startup300s remain. No timeout enlargement or reset of an existing request. Whole-only preparatory service startup before a fresh frame is a candidate subject to RED and the binding main design's separate service budget; it is not yet implemented or proven.

## Task 1: reproduce the actual boundary

- [ ] A local ephemeral HTTP server plus real SceneComfyClient, real qualified SceneMediaStore, actual guarded logger and measured unchanged source/global costs. Fixture-only POST must be confined to this local server; block all other socket destinations. Use a conservative2MiB node-info response and actual small POST/queue/history bodies. Record physical send/read/callback counts, size and every modeled cost. First observe the installed180s failure with0production network.
- [ ] Separately prove which full callbacks are at actual sends and final acceptance versus deadline-only transport housekeeping. Read existing adapter deadline/ownership tests before choosing the smallest change. Do not assume old facade counts.

## Task 2: implement only the demonstrated minimum

- [ ] Decide and ledger a bounded fix from Task1, keeping source verification at actual sends and returned-response acceptance, original180 protocol, original defaults/segmented semantics and all failure evidence. No generic admission cache or weakened unknown ownership.
- [ ] Write behavioral REDs for any adapter phase change: drift before actual socket write, loss while connecting, callback consuming final budget, expired worker, cancel while reading, POST body guard, response/input drift, full byte-length/JSON refusal, custom transport contract and no late writes.
- [ ] If startup is moved to its separate preparation phase, RED proves only fresh explicit whole startup moves before the original frame call, no service on completed replay, existing intent unchanged and original service limits/cleanup retained.

## Task 3: verify and review

- [ ] Run only affected adapter/frame/media/writer checks, plus the new actual-client budget control. Preserve prior unchanged evidence; do not run all-library tests. One fresh review of new delta, fix Important/Critical once with RED/GREEN, ledger minors. Do not treat a timing fixture as live success.

## Task 4: exact continuation

- [ ] Audit unchanged225 state/3sourcePOST/Engine05a, freeze only actual reviewed changes and new diagnostics/tests against345 dc2e5bae. Preserve exact same signed AweSun agent run-scoped approval38b31692; no extra user action or new ordinary permission.
- [ ] New state-aware operator once, normal make_video admission, no source/epoch/viewing/profile regeneration. Monitor the same process; actual first frame and463-frame composition still required, followed by new final viewing/audio/subtitles, explicit publish and zero-new-work replay before completion.

## Ledger

LIVE2026-11-01 01:52+08: same20441/43872+24204 and owned38648 all confirmed active.100completed/101intents/101upscalePOSTs; original source POSTs exactly3. Latest authoritative frame.json01:49:59.707. No producer restart/software change;350b918/ef96ff01/phase2140941b frozen. Continue the existing attempt; entire463/composition/new final human video-audio-subtitle acceptance/publish/replay still pending. No new source/epoch/viewing or VCO-08.

LIVE22:47+08: same native session20441/43872 (launcher24204), owned Comfy38648 confirmed active.50authoritative frame.json/51intents, latest complete22:45:20.967. No producer restart or product/software changes.350 b918/ef96ff01/phase2140941b unchanged. Consecutive completions about222s/frame; user informed coarse28h batch duration (strict full proofs dominate GPU1s inference). Keep running this attempt; do not broaden this now-passing HTTP repair for throughput. Source/epoch/viewing are not repeated. Complete463/composition/final human video+audio+subtitle review/publish/replay still pending.

LIVE milestone19:45+08: same session20441/worker43872, owned Comfy38648, no restart/code changes. Service prepared19:40:16, healthy19:41:12. First actual ESRGAN POST executed1.30s; original intent19:42:33, accepted19:43:12, submission19:44:05 and authoritative frame.json19:44:30 persisted. Output.png2392431bytes, verified1920x1080 by original writer. At19:45:31 completed1/submission1/intent1;243 upscale-root files, next frame local request being prepared. This proves the new HTTP boundary passed a real frame;463-frame completion/composition/final viewing/publish/replay remain pending. Continue SAME frozen350 invocation only.

Current18:52+08: new review complete with no Critical/Important/Minor (VCO-07-http-budget-review.md); independent16 tests9f38cb01 passed/1.24s. Final affected suite3b127cf2:98 passed/10.52s exit0; extra original source-transaction compatabed9bc5:23 passed/3.65s exit0. Earlier safety9ead5e80 was97pass/1fixture failure (missing Content-Type in fixture prevented POST); corrected fixture and retained real post-response drift coverage. No production fix was needed for that test error.

Final identity-bound actual-HTTP controlfb004710 exit0, result8ab7392aa3c9430d89a1ca5a5879adf0:167.565982/180s,35complete source checks, real adapter+guarded logger,2MiB schema, all4actual fixture routes,1fixturePOST/0production. Unchanged measured media proof source7259 bound, reviewed adapter3982/prod18e2 bound plus operatorb0d7 identity. Original protocol unchanged; modeled preparation87.938s charged before frame. No re-review/old full profile needed.

Freeze fbc71681 exit0: exact350softwareb918c65eacfe4d38bf4caabe5baa1d2e, only2allowed current changes/5added against345dc2e, archives match and producer AST outside_produce exact; original225 state/external input/evidence/Engine05a unchanged. New resume-reviewed-http-media.py+350 inventory invoked ONCE under ongoing authorization, session20441/logef96ff01e7da47d2ba2f3ecf37dfe8bd, phasenative-batch-resume-phase-2140941bb0284d4fafbc6032719a9bab. Current code frozen; monitor this invocation only. Actual first frame/463frames/composition/new final viewing/publish/replay remain pending.

Task1 pending. Task2-4 pending. No production modification or new production start yet. The cold77.2s value is an observed lower bound, not a measured complete ensure charge; the real HTTP control must identify actual missing obligations before selecting a fix.

Task1 complete: d16d0a01 first diagnostic only failed on old promoted PNG path, not valid RED. Corrected to exact036c audit plus actual image identity.8ee99eb6 valid cold RED:190.533s/23source checks/0POST, same before-intent error.07ed6281 valid already-warm RED:192.470s/39source checks/0POST,2MiB object_info alone exhausts budget. No new source/profile/production run.

Task2 initial RED36f8cead:10failed/2passed for missing explicit interface/producer preparation. After adding only optional constructor plumbing, a007936e is effective behavioral RED: real2MiB response hits180s deadline. Original two product files archived as data under diagnostics/pre-real-http-budget-94b3a4da830148248f507343c91d9bb2, SHA matched345 inventory before edits; never executed.

Ruling: the main design requires full proof at actual writes and sends, not repeated scans during memory-only reads. Explicit new mode checks full source/request/graph at every actual socket write; raw returned bytes are not accepted media or permission to persist. Every caller evidence writer still invokes the full proof, and later sends recheck request/graph. Cost if wrong: source drift could be detected later than an intermediate read; the new genuine post-response drift test must show it cannot become raw/accepted durable evidence. Original default transport behavior remains unchanged.

Ruling: prepare an owned service before a fresh explicit whole frame's tracking call because service startup already has its own300s phase. Existing frame function and180s are untouched, no original intent exists at that boundary, and completed replay/segmented/pending paths retain their previous startup behavior. Cost if wrong: preparation could start a service unnecessarily or change recovery timing; dedicated producer controls and review cover those cases.

Initial GREEN3c4e82ea exit0:56 passed/8.01s across new12 controls plus original concrete transport/context/frame transactions. Real-wire prepared control39751874 exit0:167.559s inside unchanged180,35complete source checks,actual2MiB object_info/POST/queue/history,1 fixture POST/0production network.87.938s modeled guarded preparation charged before tracking;78s is only an observed bootstrap lower bound, not live acceptance. Additional response-read/size/drift safety controls pending; one fresh review of this new two-file delta still required. No new production start.
