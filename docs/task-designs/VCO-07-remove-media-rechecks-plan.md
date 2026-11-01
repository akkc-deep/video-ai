# VCO-07 remove repeated media checks

> **For agentic workers:** Use superpowers:executing-plans inline. The user's explicit request supplies the scope; no additional design approval is required.

**Goal:** Remove the repeated dependency, ancestor and remote-capability checks responsible for 222 seconds per whole-scene upscale frame, then resume the retained run.

**Architecture:** Whole-scene media stores use lock ownership and the existing original-intent transaction protocol. Source admission happens at context construction; no continuity ByteGuard, repeated captured-artifact inventory audit or per-frame object_info is installed. Local PNG decoding, original-task identity and immutable commits remain part of producing valid media. Historical branches keep their existing behavior.

**Tech Stack:** Existing Python 3.12, Windows, PowerShell bootstrap, Comfy/RealESRGAN and FFmpeg. No dependency installation or git writes.

**Spec:** VCO-07-design.md plus the overriding user instruction “把这些检验都去掉，没有用”. This explicitly supersedes the old requirement to recheck all original bytes and parent directories before each media write/send.

## Global constraints

- Preserve the same run, all three admitted sources, 463 frames, original PCM/subtitles, and existing 129 successful frame transactions.
- No source regeneration, new epoch, repeated source viewing or VCO-08/full-suite run.
- Stop the old frozen worker at a no-pending-intent boundary before editing; use normal RunLock recovery afterward.
- Keep original-intent recovery, frame/media validation and the final human viewing/publication stages.
- User explicitly chose removal; the former late upstream mutation rejection between media writes is no longer a requirement for whole-scene media.

## Review focus

- A stopped partial frame before intent must resume without losing completed frames.
- Existing durable intents must never cause a second POST.
- A lost run lock still prevents commits and sends.
- Historical stores retain their current checks.
- Missing/invalid PNG and incomplete final human review remain distinguishable from successful production.

## Task 1: remove repeated checks and resume

**Files:** scene_media_records.py, scene_upscale_transactions.py, tests/unit/test_scene_media_without_rechecks.py; existing handoff/design/operations records.

- [x] Diagnose 20 completed real frames: 222.071s total, 0.827s execution; record evidence d8ae05bb428c44139333e25bb1e00afe.
- [x] Suspend and stop owned worker43872 and Comfy38648 with 129 complete frames, 129 intents/submissions, no pending queue; preserve inventory in stop82eaa9fb9dab439f8dafab50f13e1619.
- [x] Write failing regressions: 8 failed/2 passed, RED318b290538b042f295ee93944c37873e.
- [x] Implement the smallest whole-scene branch removal; keep ordinary transaction ownership and output validation.
- [x] Related128 passed/10.23s/exit0, GREEN4abdfee5d07b472e9169a5ff979e7c39; single fresh review no Critical/Important/Minor. First94passed/1old-policy test failure corrected by placing the old strict fixture on the historical segmented branch.
- [x] State-aware operator audited the129-frame stop inventory and353software once, then invoked normal make_video once: session38367/logc55f4a9a06f44cfb8ac67bd5f5ae7add/phaseab4340d0a85c4e33a70ba4201ba09b64. Actual post-change throughput remains pending.
- [x] Actual463frames/composition complete;2.75616843s/frame versus222.071419s (80.57x). New final human feedback accepted, explicitpublish delivered, ordinary replay delivered; no new model POST/mail and delivery bytes/mtime/file identities unchanged. Closeout23458 exit0, phaseaaf18f158320412da5246c30e90908e5/result.json complete=true at06:14:12; VCO-07 task board COMPLETED.

Actual media05:10: 463/463 frames finished04:43:56.547; last20 intervals average about2.76s versus222.071s, about80x. Full candidate created04:55:01.913759, all technical checks passed; session40798 ended04:55:10/expectedexit3 awaiting_final_review. Original sourcePOSTs3; totalupscalePOSTs463 and thisinvocation334; no forbidden calls/publish. Record phase214d/completed-throughput.json and result.json. Final new human viewing/audio/subtitle feedback, publication and replay remain unchecked; VCO-07 remains IN_PROGRESS.

Ruling: The user instruction overrides the old pre-write full-proof contract and the old freeze. This is an intentional policy change, not an attempt to preserve that expensive contract through another optimization.

Ruling: Retain the existing checkout and inline execution; .git is read-only and previous task authorization excludes worktrees and full-library reruns.

Recovery ledger03:47: first38367/phaseab4340 exited2 before any POST because exited Windows PID objects retained their creation identity. Added only exit-FILETIME handling in production_state.process_started_at; actual retained-child RED1failed/1passed58f6f41d, GREEN42passed1.51s8ef2c3da (ownership/state/new media). Same reviewer checked the tiny delta, no findings. Original129-frame inventory unchanged. New operator resume-without-media-rechecks-after-ended-owner.py validates that exact0POST refusal and audits354software; invoked once as session40798/log748f9c79754349e0aed2db8cd5d61ae2/phase214d9d35e305419d8398ef4b05b9a0d5. Do not monitor or restart38367 or20441. New throughput remains pending.

Live04:06: worker12596 owns the recovered run lock, session40798 active,129frames retained; still one-time entry restoration, no post-change frame and no actual throughput claim. Original ended GPU leasee4dcae/43872 archived intact under exact proof of both old processes ended and current12596 lock ownership; phase214d/ended-gpu-lease-recovery.json. Current3productSHA match354freeze. Entry frozen/source admission remains; removed audits are the recurring whole-media write/send/tool/ancestor/object_info hot path. Continue this invocation rather than restart it or repeat green tests.
