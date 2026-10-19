# JIM-05 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce exact scene source clips with observed parent-native-frame continuation and independently verifiable recovery.

**Architecture:** Independent schema=2 records consume committed scene planning and accepted reference images. Separate pure planning, bounded Comfy transport/transactions, media conversion, observation validation and orchestration preserve all schema=1 consumers.

**Tech Stack:** Python 3.12 standard library, pytest, existing ffmpeg/ffprobe and frozen Wan workflow.

**Spec:** `docs/task-designs/JIM-05-design.md` (binding, including exact fields).

## Global Constraints

- paragraph_jimeng_v1; native16/cut; fast 768x432 or quality 1280x720.
- Original scene budgets unchanged; 200-frame chain generates 93/93/17 and retains 93/92/15.
- All images accepted before service startup; every parent and leaf needs actual process observation.
- Intent precedes POST; no POST replay; raw HTTP evidence and exact original IDs survive interruptions.
- No real inference/cloud/email, CLI changes, upscaling, composition or delivery.
- Git is available through `C:/Program Files/Git/cmd/git.exe`; .git is read-only and prior JIM-03/JIM-04 work is present in the supplied checkout. Work in place, retain evidence; no commits/worktree claims.

## Review Focus

- Input mutation after intent or connection: actual send guard refuses request.
- Unknown accepted POST: recover only original task; never repeat submission.
- Parent PNG must come from generated retained native index, including discarded tail.
- Missing outer records: recover exact media receipts without re-encoding valid bytes.
- Waiting or failure in one scene must not prevent independent scene progress.

## Tasks

### Task 1: Pure continuation and native media helpers

Files: `planning/scene_clip_continuation.py`, `media/frames.py`, `media/video.py`, corresponding tests.
Interfaces: build_scene_wan_plan, scene_clip_frame_mapping, validate_scene_clip_frame_mappings, extract_native_frame, trim_scene_video, exactly as spec.
- [x] Write and run test_200_frame_retained_native_mapping (missing module RED).
- [x] Implement fixed parameters, shared Bible prompt, narration intersections and exact mapping; test malformed/boundary inputs.
- [x] Add real-media frame extraction and nonzero interval trim tests, observe RED, implement and verify.

### Task 2: Bounded Comfy transport and recoverable transactions

Files: `adapters/scene_comfy.py`, `runtime/scene_comfy_transactions.py`, `tests/unit/test_scene_comfy.py`.
Interfaces: SceneComfyClient and recover_or_submit_scene_clip per spec. Store protocol is shared with runtime implementer before edits.
- [x] Establish failing bounded transport / once-only transaction tests.
- [x] Implement loopback deadlines, actual send ownership checks, raw HTTP records and original graph/UUID recovery.
- [x] Verify rejected/conflicting/unknown task evidence, cancellation and recovery without duplicate POST.

### Task 3: Immutable records, observation and orchestration

Files: `runtime/scene_clip_records.py`, `runtime/scene_clip_observations.py`, `runtime/production_scene_clips.py`, new unit/integration tests.
Interfaces: two production APIs, two read-only admission APIs, observation APIs and SceneClipResult per spec.
- [x] Build authentic accepted-image fixtures; establish failing preflight/observation/generation tests.
- [x] Implement strict identities, atomic store/media receipts, locked orchestration and complete reconstruction.
- [x] Verify independent scene waits, parent observation gate, exact native PNG inputs, interruption and tamper cases.

### Task 4: Review, validation and handoff

Files: `docs/jimeng-candidates.md`, task verification document and task board; successor design/handoff after completion.
- [x] Document prepared-run APIs and honest actual-observation requirements.
- [x] Obtain fresh review against full spec; reproduce and fix material findings.
- [x] Run new targeted, specified historical and full serial suites; record actual logs/exit codes and file SHA256.
- [x] Record completed outcome only after evidence meets acceptance; prepare JIM-06 design and handoff without implementing it.

## Execution ledger

- User start evidence: 2026-10-19 “完成任务JIM-05”; complete design/handoff consumed; READY -> IN_PROGRESS.
- Authorization: existing implementation-ready design and explicit completion request authorize implementation; no repeat design approval needed.
- Pre-flight: Task 1 planning/media and Task 2 transport have separate files; both feed Task 3. Exact spec fields bind all interfaces.
- Ruling: use supplied checkout without Git mutations — executable initially absent from PATH, then found at its absolute path; .git remains read-only and prior task changes are present. Preserve plans/test evidence and use read-only Git status/diff.
- Task 1 initial verification: missing-module RED; exact200 mapping GREEN; planning/native media/old budget **162 passed in 17.74s**. Independent review found >6-second committed budgets accepted; failure reproduced, reject without replanning. Final combined run still pending.
- Task 2 initial verification: missing-module RED; transport/transactions **32 passed in 6.81s**, old Comfy recovery/tracking **27 passed in 15.96s**. Independent review fixes reproduce queue/history completion race, retained failed/conflicting output history, orphan HTTP evidence, lost POST response plus failed original task; all fixed before whole-change review.
- Observation module initial verification: missing-module RED; **47 passed in 0.93s**; templates remain unauthored/unverified and both parent/leaf media are bound.
- Runtime initial verification: record-store RED->GREEN; missing coordinator RED->GREEN; first authentic three-scene full admission/replay **1 passed in 207.89s**. Review-driven hardening includes required receipts/recipes, native PNG pixel comparison, all pending transaction preflight, accepted observation immutability, fresh global sources, deterministic outer recovery and primary/cleanup preservation. Broader integration/whole suite pending.
- Ruling: raw HTTP response bodies may be zero bytes and use an adapter-local bytes=0 identity; every media Artifact remains strictly positive. This preserves exact empty network evidence without fabricating bytes; downstream code must use the HTTP-specific validator for those bodies.
- Ruling: reuse complete decode results only within one API invocation, keyed by SHA-bound Artifacts/expected dimensions/frames, rehashing bytes on every reuse; no cross-call or mtime cache. This reduces repeated replay cost while preserving changed-media rejection.
- Ruling: technical clip.created_at is the final native extraction preparation receipt.created_at. This makes a missing outer clip marker recoverable byte-for-byte without inventing a new identity or rerunning inference/media work.
- Independent final review: stable narrow **129 passed in 8.50s**, no newly confirmed material finding except explicitly tracked invalid-media work. Scoped follow-up caught local encoder RuntimeError being incorrectly permanent; authentic RED **1 failed in 96.33s**, narrowed to confirmed InvalidGeneratedMedia metadata/count only. First invalid-count GREEN **1 passed in 105.32s**. Full report `JIM-05-review.md`.
- Ruling: after initial complete source admission, exact byte hashes and JSON directory inventories of all consumed Jimeng/reference-storage/reference-image/selection evidence are rechecked within the same invocation before POST, observation receipt and complete. This replaces repeating the same full admission decoders during one observation call; public reentry still always performs fresh full admission, and modified evidence is refused.
- Final serial validation started: targeted 269 cases, then specified historical set, then full suite. Pipeline script/logs under `D:/VideoSi/cache/video-ai/logs/jim-05-*`; no success or completion recorded until actual exit codes and summaries are available.
- While the targeted process (already imported modules) was running, explicit unknown-run audit found unprepared directories reported failed with run/log paths. New rejection regression observed RED; entry now refuses missing frozen options before assigning run identity/acquiring a lock. Fresh runtime/store verification **15 passed**; the subsequent full suite includes this additional case and the updated entry. Targeted count remains its original 269 collection; final full-suite hash evidence is authoritative for final implementation bytes.
- Late recovery audit reproduced failed original + missing rejected receipt being overridden (**1 failed in 123.83s**). Added full original-observation replay, raw-failed blocking cursor, exact rejected receipt repair and parent actual-send inventory guard; units **64 passed in 1.90s**, scoped independent rereview no new Critical/Important. Authentic GREEN process and final serial full suite include these added tests. No public record schema changes; the raw-only cursor exists only in memory. Original 269-case targeted process remains running its already imported modules.
- Original-import targeted run completed: **269 passed in 3343.84s (0:55:43)**, exit 0, `D:/VideoSi/cache/video-ai/logs/jim-05-targeted-final.txt`. This includes the authentic transient-trim recovery GREEN. Late failed-raw recovery focused GREEN: **64 passed, 1 deselected in 137.86s**, exit 0, `jim-05-failed-raw-green.txt`. The serial pipeline captured 21 final file SHA256 values and started historical regression; fresh full-suite and post-run hash gates remain pending.
- Final-byte design-listed historical regression: **212 passed in 838.51s (0:13:58)**, exit 0, `D:/VideoSi/cache/video-ai/logs/jim-05-historical-final.txt`. Fresh full suite started serially after this result; no implementation/test/usage edits since the 21-file snapshot.
- Final fresh whole suite: **3206 passed in 7302.90s (2:01:42)**, exit 0, `D:/VideoSi/cache/video-ai/logs/jim-05-full-final.txt`. All late recovery additions are included. The serial pipeline exited 0; **21 checked, matched=true, changed=[]** in `jim-05-verified-files-check.json`. Outcome mapping and exact commands/logs are in `JIM-05-verification.md`. Earlier pending statements above are chronological ledger entries, superseded by this final result.
- JIM-05 completion recorded before successor work. Selected board Order=6 JIM-06; completed/read/link design `JIM-06-design.md`, wrote/linked exact next-task `docs/task-handoffs/JIM-06-handoff.md`, then NOT_STARTED -> READY. Successor implementation/tests were not started. Local checkout preserved on main with read-only Git metadata; no branch, commit, merge or PR operation requested/performed.
