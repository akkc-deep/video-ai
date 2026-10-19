# JIM-04 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. Track verified progress here.

**Goal:** Implement the approved [JIM-04 design](JIM-04-design.md), preserving selected baselines and one-submission recovery.

**Architecture:** Separate pure configuration, TOS storage, reference generation transactions, and read-only acceptance. Reuse JIM-03 notification and selection unchanged except reference request verification dispatch.

**Tech Stack:** Python 3.12 standard library, pytest, existing Windows bootstrap and media tools.

## Global constraints

- The full JIM-04 design is authoritative for exact schemas, signatures and failure rules.
- No real cloud upload, paid generation, SMTP, Wan or model service startup.
- Bootstrap before Python; runtime/cache/logs stay under D:/VideoSi.
- Work in the supplied checkout: Git executable unavailable and .git is read-only under the session policy. No commits/worktree mutations; retain reviewable local changes.
- User explicitly requested implementation of the prepared task; do not restart design approval.
- File-isolated storage and candidate implementations may run alongside root configuration/coordinator work; shared interfaces are agreed explicitly. Independent review is read-only.

### Task 1: TOS storage and finite HTTPS

Files: adapters/reference_storage.py, adapters/external_https.py, tests/unit/test_reference_storage.py, existing HTTPS tests as needed.

Interfaces: Produce ReferenceStorage(settings, *, http=None, clock=None, ownership_check=None), ensure_original(original, *, run_id, before_put), presign_get(object_record, *, expires_seconds). Consume settings mapping or dataclass; document representation for Task 2. ExternalResponse needs headers and a controlled 404 path without weakening errors for existing consumers.

- [x] Write independent fixed TOS4 GET/header vector using design's exact UTC/credentials/key/TTL; run and observe missing adapter.
- [x] Implement signing, content-addressed HEAD/GET/PUT, real byte/metadata verification, before_put handshake, finite deadlines and ownership checks.
- [x] Test reuse, conflict, unknown PUT recovery, redirection refusal, non-disclosure and caller-thread callback.
- [x] Run storage and existing HTTPS/Jimeng adapter regression. Expected: all pass.

### Task 2: Reference configuration and immutable settings

Files: reference_config.py, config.py, runtime/production_inputs.py, new runtime/reference_settings.py if useful, tests/unit/test_reference_config.py.

Interfaces: Produce strict capability/storage parsers, explicit model selection and frozen capability identity; load/bind settings for legacy prepared runs without modifying their frozen inputs. Exact settings.json contract is in design. Consume Task 1 storage representation.

- [x] Test invalid/bool/evidence/endpoint/TTL settings and model selection before implementation.
- [x] Implement raw preservation/freeze/load, capability byte hashes and explicit supplementation with immutable first binding.
- [x] Test missing config writes no marker; credential rotation remains possible; source/model/capability/storage changes refuse.
- [x] Run configuration and historical frozen-input tests. Expected: all pass.

### Task 3: Reference generation and provenance verification

Files: adapters/jimeng.py, runtime/jimeng_reference_candidates.py, runtime/reference_image_records.py, runtime/image_selection_records.py, tests/unit/test_reference_image_records.py, reference candidate integration tests.

Interfaces: Produce generate_reference_candidates and reference provenance validation per design; consume settings/model/capability and ReferenceStorage. Extend submit via explicit controlled image_urls. Preserve legacy request readers.

- [x] Write real PNG/baseline fixtures and actual HTTP body assertions; observe missing reference behavior.
- [x] Implement ordered multi-use reference binding, exact shared prompt, one-submission intent and original-task recovery, immutable provenance and source/object verification.
- [x] Test unsupported inputs zero submit, unknown intent, accepted/query/download recovery, changed source, lock loss and secret-free records.
- [x] Run reference records/candidates plus JIM-01/JIM-03 regressions. Expected: all pass.

### Task 4: Batch coordination, Wan image acceptance and documentation

Files: runtime/production_reference_images.py, runtime/reference_image_records.py, tests/integration/test_jimeng_reference_flow.py, config/jimeng.example.json, docs/jimeng-candidates.md.

Interfaces: Produce ReferencePreparationResult, produce_reference_batch and require_reference_image_acceptance with design's exact result/status/Wan schemas; consume Tasks 1–3 and existing prepare_image_batch/require_complete_image_acceptance.

- [x] Test three scenes/two batches with selected fixed baseline and actual reference body; full selection plus observation required for Wan manifest.
- [x] Implement owned/external lock coordination, settings preflight, immutable object intent/receipt, reference candidates, notification recovery and independent error result.
- [x] Test boundary interruptions, missing/invalid config, expiry, model/config changes, changed provenance/original, lock cleanup, no Wan submissions.
- [x] Update example and usage docs with supplementation, verified capability and existing bucket setup.
- [x] Run new targeted tests, design's historical regressions, then full suite serially. Record actual commands/results.
- [x] Independent final review, fix material findings with regression tests, record verification and COMPLETED, then prepare JIM-05 using task handoff skill.

## Progress and decisions

- 2026-10-19: Read full task design and handoff. User start request: “JIM-04完成这个任务”. READY -> IN_PROGRESS.
- Preflight: Task 1/2 share storage settings; use plain mapping at adapter boundary. Tasks 2/3 share immutable settings/model capability. Tasks 3/4 share provenance and candidate manifests; JIM-03 dispatch must remain read-only. Each task agrees with the approved exact schemas; no design changes identified.
- Session adaptation: preserve changes in supplied checkout and plan ledger because Git is unavailable/read-only; do not run shell helper scripts requiring Git. Review files directly. No real-service authorization is needed for the designed substitute-only tests.
- Task 1 implementation: storage delegate observed fixed-vector missing-module RED, implemented finite caller-thread handshake and actual-send ownership/cancellation guard. Report `JIM-04-storage-report.md`; adapter regression 86 passed in 8.98s. Independent storage review established no remaining material finding.
- Task 2 implementation: root observed 36 configuration tests RED, then 63 new/config/input tests GREEN. Independent review found unused fallback fields could bypass validation and capability validation used a different read than the copy. Both reproduced RED; fixed upfront validation and exact stable byte-buffer validation before copy. Latest config/input run 44 passed in 1.98s; independent focused recheck 7 passed. Report `JIM-04-storage-config-review.md`.
- Task 3 implementation: fixed references/shared prompt, exact independent request/provenance records, real reference payload and original-task/download recovery implemented. Delegate reported 29 targeted tests and 96 relevant historical tests passing before final audit fixes; final combined verification is recorded below.
- Task 4 initial integration: root 4 missing-module tests RED -> 40 coordinator/config GREEN; real HTTP body + full selection/observation/Wan list + fault recovery run 11 passed in 204.37s. Real JPEG RED -> GREEN 1 passed in 17.89s; shared-SHA baselines RED -> GREEN 1 passed in 16.77s. Additional limit/release tests are in the final combined run.
- Whole-change review `JIM-04-final-review.md` found shared-SHA source alias conflict, actual-send URL TTL gap and unanchored actual-submit intent evidence. All are being corrected with focused regression tests before final verification.
- Decision: preserve an object's initial upload source path when another accepted baseline has identical bytes; verify each accepted source separately and retain separate reference positions by scene/candidate/SHA. This implements content addressing without changing the public schemas.
- Decision: add a small immutable `submit-evidence.json` canonical intent-digest sidecar before network transmission. This lets readers reject changed body/URL/time evidence while preserving all exact request/intent/accepted/provenance/Wan schemas and keeping URLs ephemeral.
- Final combined new verification: **118 passed in 360.71s (0:06:00), exit 0**; `D:/VideoSi/cache/video-ai/logs/jim-04-targeted-final.txt`. Related historical and full tests run serially next. Code implementation is stable; task completion remains gated on final verification.
- Final related historical regression: **186 passed in 200.44s (0:03:20), exit 0**; `D:/VideoSi/cache/video-ai/logs/jim-04-historical-final.txt`. The full suite then ran serially, `D:/VideoSi/cache/video-ai/logs/jim-04-full-final.txt`.
- Final whole suite: **3012 passed in 3840.59s (1:04:00), exit 0**, `D:/VideoSi/cache/video-ai/logs/jim-04-full-final.txt`. All 20 recorded implementation/test/example/doc SHA256 values matched after testing. Current task outcomes and independent review are complete; JIM-04 COMPLETED was recorded before successor design/preparation.
- Successor selection: after recording completion, selected Order 5 JIM-05; observed NOT_STARTED and Design=None. Its detailed design is now being prepared; status/Handoff remain unchanged until the completed design is linked and handoff written.
- Successor preparation complete: finished and fully read `JIM-05-design.md`, linked that exact design while preserving NOT_STARTED/Handoff=None, wrote and linked `../task-handoffs/JIM-05-handoff.md`, then recorded JIM-05 NOT_STARTED -> READY with concrete first implementation action. Both direct dependency inputs (JIM-02/JIM-04) are reconciled. No JIM-05 code, tests, service startup or real observation was performed. Only handoff/board/plan documentation changed after final verification.
