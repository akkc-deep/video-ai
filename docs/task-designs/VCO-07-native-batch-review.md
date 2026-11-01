# VCO-07 native batch review

Date: 2026-10-31. One fresh independent, read-only review under `requesting-code-review` / `executing-plans`. No product, test, git or runtime files were changed; no archived code was executed; no tests, GPU work, network calls or production writers were run by this reviewer. This report is the sole write.

## Scope and evidence

Read `VCO-07-design.md` and `VCO-07-native-batch-plan.md`. Reviewed the new `media/scene_native_batch.py`, the optional remaining-time extension to `media/scene_upscale.py:verify_png`, the whole-mode/recovery delta in `runtime/production_scene_upscale.py:_extract`, and both new unit-test files. Read existing path, identity, logger, extraction promotion and evidence-capture code only to understand those interfaces.

Compared both modified producers as text against `pre-native-batch-8f6ee6fa71c04c2c90dafb74b2bbe340/*.py.bin`. Their archived SHA256 values match the corresponding entries in `implementation-live-proof-df51ee197ccb448f936ee71ba7bd8f7e.json`:

- `production_scene_upscale.py`: `9b1fe230be0e0f549991956ceb1792987457eefae73fd7487ab7e0c209928475`.
- `scene_upscale.py`: `9a300a1960a8bf4903bb4cd798ecc7b3ce8102cd7945bdb734130443f510cb82`.

Reviewed current SHA256 values:

| File | SHA256 |
|---|---|
| `src/video_ai/media/scene_native_batch.py` | `b11321f7c0a5a45a5ca3040fa214e6f71c22cdfa4d67d584a76528c71bf28554` |
| `src/video_ai/media/scene_upscale.py` | `2d9b23c60b2a6b5a68e7b1027bc94b80d7d5fbe503726668452f25adab94fa91` |
| `src/video_ai/runtime/production_scene_upscale.py` | `a82562c6eb5799b84f951b6837b955732fcba75bf8c757016148d93c8a67e23b` |
| `tests/unit/test_scene_native_batch.py` | `20d758710354c2af1aec3087653be9d750cbfd7519f0e4b7796412c81d637e6e` |
| `tests/unit/test_scene_native_batch_deadline.py` | `dfeb92864b159cdff59d72b95baffbbd4f99d1e3bdffd990f93516c82ffc9608` |

Read the original `media-resume-phase-d0dde8ef7c5a4e56a358b8c5ad0988e5/result.json`: failed with `TimeoutError / media budget expired`; original source bytes unchanged, source POST count 3, new source POST 0, upscale POST 0, no forbidden calls, not published. The supplied 21st-PNG/219-extracted diagnosis is consistent with the old per-image logging path; this review did not independently reconstruct every original event.

Read `D:/VideoSi/cache/video-ai/logs/vco07-native-batch-focused-green-6c657b5e469e45c49b54e880120b59ac.log`: its explicit command covers the two new unit files, `test_frames.py`, and `test_whole_scene_media.py`; result is **66 passed in 16.31s, exit 0**. This is inspected prior execution evidence, not a reviewer rerun. RED/GREEN chronology is reported in the plan and dispatch, not independently replayed. The stopped overbroad `ed71236f` run is **not** a passing run and contributes no passing-suite claim.

## Strengths and checked behavior

- Whole-only dispatch is explicit. The archived diff leaves the legacy helper and original segmented path intact; `verify_png` without the new callback retains its previous timeout behavior. Recovery checks absolute parent ownership, exact lowercase `extraction-` plus 32 hex characters and `store._lexical` before proceeding. The reuse branch does not invoke extraction.
- Every retained image still receives the existing signature/chunk/CRC, probe and complete RGB24 decode checks. Every decoded byte is compared to the corresponding source frame. Count, dimensions, numeric inventory, last-frame defects and reordered images are checked without sampling.
- Source and PNG `FileIdentity` checks include bytes, SHA256 and mtime. `_sequence` repeats inventory and canonical-path checks; persistent reparse redirection is rejected through `_local` / path resolution, with production recovery also using `_lexical`. Byte mutation with a restored mtime still changes the digest. The hardlink exception is the finding below.
- The helper creates one deadline and does not renew it per image. Both PNG subprocesses get a freshly evaluated remaining budget, capped by the existing 300-second call limit; the callback also checks after decode. Final rechecks reject expiry or byte/inventory drift before a successful return. This establishes cooperative refusal logic, not a measured wall-clock completion guarantee for synchronous guards or filesystem operations.
- Full-source inspection remains logged. Per-PNG subprocesses are read-only; their complete results are summarized in one aggregate record rather than fabricated command logs. Actual logger calls still pass through the existing guarded logger. No continuity cache/protection or frame-transaction timeout is modified.
- The aggregate JSON lives in the logger tree, outside the directory renamed to `input-frames`. `_extract` preserves it as an Artifact in extraction-ready/final evidence. `SceneMediaStore.capture_command_evidence` treats nested image/source identities in these logs as historical observations, so their old staging paths do not become mandatory live files after promotion. The original extraction reader still independently verifies the target sequence and native source correspondence. The aggregate alone is not an extraction-ready marker; a failure after its save leaves diagnostic evidence without granting extraction acceptance.

## Findings

### Critical

None found in the reviewed delta.

### Important — repeat the non-alias check at both final rechecks

**Location:** `src/video_ai/media/scene_native_batch.py:66-69`, following the one-time `st_nlink` check at lines 49-51.

**Trigger:** After that initial check, another process (or a test hook in `verify_png` or the final logger guard) creates a hardlink outside the extraction directory to a verified PNG. No PNG bytes, pathname, size or mtime need change. The directory's own inventory remains identical.

**Effect:** Both final `recheck()` calls accept the newly aliased PNG. `_sequence` rejects symlinks and path redirection but does not inspect hardlink count; `_again` compares serialized `FileIdentity` fields, which contain neither link count nor a previous change-time value. Owned staging files use short-lived hash handles, so the production write session does not keep a deny-write/delete handle over the entire validation interval. Later artifact checks and pixel validation also accept unchanged bytes. Thus an allegedly non-aliased owned extraction can be returned and promoted while an external pathname still refers to the same mutable file. This weakens the explicit ownership guarantee and can permit later external writes to affect the accepted native input, or force an avoidable downstream refusal.

**Fix:** Factor the exact-sequence plus `st_nlink == 1` validation into one local routine and invoke it initially and in every `recheck()`, including after `logger.save_json`. Preserve the existing canonical-path, inventory, digest, mtime and deadline checks.

**Regression:** Use a real hardlink to an earlier PNG, outside the batch directory but inside the owned test run. Parameterize creation (a) after an image verification and (b) inside the aggregate evidence logger guard. Assert the helper refuses rather than returns; an integration-level assertion may additionally verify no `extraction-ready.json` or accepted extraction is created. Keep a pre-existing-hardlink rejection control. These cases are absent from the current new tests despite the plan's alias-rejection requirement. Reproduce RED before the fix, then GREEN.

### Minor

None recorded. The unmeasured acceptance items below are intentionally not downgraded into cosmetic findings.

## Declined to judge

- Actual 219-frame completion within 1200 seconds under the installed `SceneMediaStore` guard: the virtual-budget test replaces source inspection/decode and PNG validation, accounts for one aggregate write plus synthetic per-image time, and does not measure the full installed operation. Real profiling/acceptance is separately pending.
- Actual 180-second frame-transaction feasibility under measured installed guard cost: outside this delta; the frame transaction is frozen, and no new timing result was available to this reviewer.
- Strict preemptive wall-clock interruption of synchronous guards, hashing and JSON writes: these existing APIs are cooperative; callback and final refusal checks do not interrupt a running filesystem operation. No claim of a hard realtime bound is made.
- Live recovery of the saved 219-PNG production orphan through promotion and subsequent remaining batches: static API/promotion interfaces were checked, but no production writer was run and the inspected 66-test command does not establish this operator acceptance.
- RealESRGAN/GPU execution, remaining 463-frame production, composition, audio/subtitles, new human playback, publication and zero-new-work replay: expressly outside the review execution scope and still separate VCO-07 acceptance gates.
- Whole-repository software inventory reconciliation and the actual Engine05a identity comparison: verified the two archived producer identities and exact reviewed delta, but did not certify unrelated files or recompute the continuity engine closure. That reconciliation belongs to the executor before recovery.
- Unrelated repository diffs, prior continuity/native-lease implementation, legacy long-chain/full-suite/delivery behavior and the stopped overbroad run: frozen or explicitly excluded. Existing supporting code was read only to assess integration; no broad approval or passing result is inferred.
- Pre-existing checker behavior for inputs outside the bounded native media envelope, broader parser/resource hardening and arbitrary simultaneous hostile filesystem rewrites: those implementations are unchanged. The concrete late-hardlink gap introduced into the new helper's stated non-alias guarantee is judged above, not set aside.

## Verdict

**With fixes — not ready to approve this delta yet.** Fix the Important late-hardlink acceptance gap and demonstrate its RED/GREEN regression. The rest of the reviewed implementation preserves the intended strict validation and bounded evidence design on static inspection and the inspected focused run. This verdict does not approve unmeasured installed-guard timing, production recovery, GPU execution or overall VCO-07 completion.
