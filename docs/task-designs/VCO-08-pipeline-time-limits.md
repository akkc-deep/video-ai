# Legacy production execution policy

User instruction: formal video production has no execution time budget. This
scope covers the public legacy pipeline, source generation and upscale entry
points. It does not change model, graph, frame-count, resource or byte limits.

The production entry points apply the shared call-local production scope.
Wan attempts and upscale clips/frames use no monotonic or wall execution end.
Individual HTTP requests retain the finite configured request timeout; unknown
submission intents remain once-only and never authorize another POST.

New durable policies explicitly record `time_limits: unlimited_v1` and null
execution timeout values. Native attempt/frame and clip receipts retain that
policy so partial recovery can identify their semantics before a draft exists.
Readers choose semantics from saved receipts, never from the current call-local
scope. Exact historical finite policies remain readable without rewriting
options, graph bytes, manifests or receipt identities.

Implementation and verification sequence:

1. Add failing focused tests for late bounded HTTP, historical pipeline scope,
   explicit policies and receipt replay beyond an obsolete frame timeout.
2. Apply production scope to public generation/resume endpoints and replace
   operation deadlines with the shared unlimited execution helpers.
3. Record and validate explicit new policies while retaining legacy readers;
   retain durable start/completion ordering and request-level bounds.
4. Run the focused RED/GREEN tests and affected source/upscale/pipeline checks
   serially with other CPU/GPU work. No service, model download or GPU run.

Ruling: legacy finite receipt validation keeps its original historical time
bounds. Resuming old runs uses current unlimited execution for new work, while
the frozen old receipts continue to describe and authenticate the old work.

The existing finite-deadline characterization cases deliberately invoke the
undecorated internal body (`__wrapped__`) to build/read historical finite
receipts. This is restricted to those historical cases; separate public-entry
tests prove the new unlimited default, bounded late HTTP, and completed receipt
consumption with no active production scope.

Verification recorded on 2026-11-01:

- RED: `./scripts/test_windows.ps1 tests/unit/test_legacy_pipeline_no_time_limits.py -q --tb=short`
  exited 1; 5 intended missing-behavior failures in 1.17s. Log:
  `D:/VideoSi/cache/video-ai/logs/test-e6ae08d9beb548f7a5d1686812d7912b.log`.
- GREEN: the same command exited 0; 8 passed in 18.07s. Log:
  `D:/VideoSi/cache/video-ai/logs/test-d05b9dd23b2447cdb2e8984aa084e3ae.log`.
  The added cases cover both source/upscale completed consumers outside the
  execution scope, plus both current and frozen legacy pipeline option bytes.
- Scoped `git diff --check` exited 0. Existing affected compatibility checks and
  independent review remain pending; these results do not claim a full suite or
  a real model generation run.

Owned implementation files:

- `src/video_ai/pipeline.py`
- `src/video_ai/runtime/_legacy_execution_policy.py`
- `src/video_ai/runtime/_source_clip_generation.py`
- `src/video_ai/runtime/_source_clip_evidence.py`
- `src/video_ai/runtime/source_clip_checks.py`
- `src/video_ai/runtime/start_image_checks.py`
- `src/video_ai/runtime/_upscale_generation.py`
- `src/video_ai/runtime/_upscale_evidence.py`
- `src/video_ai/runtime/_upscale_resume.py`
- `src/video_ai/runtime/upscale_checks.py`
- `src/video_ai/runtime/pipeline_import.py`
- `src/video_ai/runtime/_pipeline_saved_import.py`

Owned verification files:

- `tests/unit/test_legacy_pipeline_no_time_limits.py`
- `tests/source_clip_helpers.py`
- `tests/upscale_helpers.py`
- `tests/unit/test_upscale_generation.py`
- `tests/unit/test_upscale_checks.py`
- `tests/unit/test_upscale_resume.py`
- This scoped design and verification note.

Independent review follow-up:

- Imported-child upscale generation must register the durable unlimited policy
  before extraction/inference, allowing interrupted partial inventory to replay
  source commands longer than the historical 300-second limit.
- The public child derivation APIs also perform formal preflight/trim/decode and
  therefore need their own execution scope for direct callers.
- A subsequent audit found the legacy SDXL start-image HTTP wrapper still has a
  shared per-image execution deadline. Start-image prepare/resume/finalize are
  included in formal production scope; each HTTP request stays finite. Its
  existing command evidence reader has no elapsed 300-second restriction.

All three follow-ups are repaired. The imported child registers its durable
policy before generation; public child derivation and start-image entry points
apply the production scope; the image HTTP wrapper keeps its finite individual
request cap with no per-image deadline in production.

- Expanded RED, same focused command: 8 failed and the original 8 passed in
  31.18s, exit 1. Log `D:/VideoSi/cache/video-ai/logs/test-255eaf8d611c42e08a5301ace5dbd95a.log`.
- Expanded GREEN: 16 passed in 30.66s, exit 0. Log
  `D:/VideoSi/cache/video-ai/logs/test-c13d4ea949414915b9da0c7d7ff85746.log`.
- The imported-child regression uses authentic inherited/native frame prefixes,
  interrupts before the next POST and before clip completion, simulates a
  completed 301-second extraction, then reconstructs outside production scope
  with no new POST and no manifest rewrite.
- The 13-file affected legacy compatibility batch exited 0: 476 passed in
  1248.81s (20:48), using
  `./scripts/test_windows.ps1 <affected files> -x -vv --tb=short`. Log:
  `D:/VideoSi/cache/video-ai/logs/test-68c135fbf31b4684933477ed643148e6.log`.
- A separate real historical-policy fixture passed its first current public
  resume: 1 passed in 8.52s, exit 0, log
  `D:/VideoSi/cache/video-ai/logs/test-6542e155daaf41db9734b29aad5558d8.log`.
  It creates actual old finite frame/media evidence and a finite workflow policy,
  resumes only the unsubmitted tail, simulates a new 301-second encoding-copy
  inspection, then finalizes and consumes the completed report outside the
  production scope. The old policy pointer/file, old checkpoint bytes and old
  frame record stay unchanged; only one new POST occurs. No product fix was
  necessary for this first-resume path.

Existing recovery limit retained: a run with a registered `upscale_resume`
receipt cannot be reopened a second time or admitted as another partial import.
That once-only admission rule is unchanged by removal of execution time limits;
this change does not add repeated in-place recovery or a new receipt-chain rule.

The completed 476-case command was:

```powershell
./scripts/test_windows.ps1 tests/unit/test_source_clip_generation.py tests/unit/test_source_clip_checks.py tests/unit/test_source_clip_user_acceptance.py tests/unit/test_upscale_generation.py tests/unit/test_upscale_checks.py tests/unit/test_upscale_resume.py tests/unit/test_pipeline.py tests/unit/test_pipeline_import.py tests/unit/test_pipeline_reconcile.py tests/unit/test_pipeline_saved_import.py tests/integration/test_source_clips_cli.py tests/integration/test_upscale_cli.py tests/integration/test_pipeline_cli.py -x -vv --tb=short
```

The separate historical-policy command was:

```powershell
./scripts/test_windows.ps1 tests/unit/test_legacy_pipeline_no_time_limits.py::test_first_public_resume_of_real_finite_policy_preserves_old_receipts -q --tb=short
```

At handoff, product code is stable and the two Important independent review
findings have focused RED/GREEN evidence. The testing slot has returned to the
main production agent. The following extra affected files remain pending its
serial batch: `tests/unit/test_start_image_generation.py`,
`tests/unit/test_start_image_checks.py`, and
`tests/unit/test_pipeline_revision_resume.py`. No full-suite, service, model
download or GPU execution result is claimed here.
