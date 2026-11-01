# VCO-07 HTTP budget delta: fresh code review

Date: 2026-10-31. One independent review using the requesting-code-review code-reviewer template. Product and tests were read-only; this report is the sole repository write. Archived baseline files were compared as data with `git diff --no-index --text`, never imported or executed. No delegation, git mutation, installation, full suite, production service, GPU job, or model POST was performed.

## Scope and identities

Requirements: `docs/task-designs/VCO-07-design.md`, especially input proof at writers/submissions and the independent service startup budget; the exact interfaces, Review Focus and binding rulings in `docs/task-designs/VCO-07-http-budget-plan.md`.

Baseline directory: `D:/VideoSi/projects/video-ai/vco07-diagnostics/pre-real-http-budget-94b3a4da830148248f507343c91d9bb2/`.

| File | Baseline SHA256 | Reviewed SHA256 |
| --- | --- | --- |
| `src/video_ai/adapters/scene_comfy.py` | `f30d397b7acece45b4dcf78a7b47bf6d6cf54dd7ae570b34eb6ddee63409eeb0` | `3982bd8d75ad8ff93554a34e2dc6576d520542b258d30e8ae7cea0d138d576c7` |
| `src/video_ai/runtime/production_scene_upscale.py` | `a82562c6eb5799b84f951b6837b955732fcba75bf8c757016148d93c8a67e23b` | `18e264343a80f8481cae6db8c0f5ad549354e2c2cdeeb93c8abc547bedb20a5e` |

New test identities:

- `tests/unit/test_scene_comfy_send_checks.py`: `d68a755e7c6278e648de5c0f4ea7086870d04474c3c5e395e4b0d39f21f6e3d2`.
- `tests/unit/test_scene_upscale_service_preparation.py`: `e71df2f04b31dcc9bd9e9743b37ac2d237ccaa6191461a70588676bf1731e145`.

## Strengths

- The adapter change is explicit and defaults to the original behavior. Strict boolean validation and rejection of `http` with `send_checks_only=True` prevent a delegated transport from accidentally receiving the reduced phase checks (`scene_comfy.py:30`).
- Full input/ownership checking remains immediately before every concrete `HTTPConnection.send`, after connection establishment, bracketed by deadline/cancellation checks (`scene_comfy.py:55`, `scene_comfy.py:76`). Headers and POST body have separate checks. The changed read path retains the original byte limit, declared-length check, bounded caller wait, connection shutdown and context propagation.
- Preparation is narrowly gated and stays within the existing `try/finally` service lifecycle. The unchanged protocol still establishes its own deadline, and the producer passes the original configured frame timeout (`production_scene_upscale.py:122`).

## Review Focus results

1. **Source/lock loss during connect or before POST body:** the final full guard follows `connect()` and precedes `super().send(data)`. A callback that consumes the remaining budget fails its post-callback deadline check. Real loopback tests cover connect-time loss, body-time loss and a guard exhausting the deadline (`test_scene_comfy_send_checks.py:63`, `:74`, `:86`).
2. **Blocked DNS/read after cancellation:** the caller sets cancellation and closes connections on exit; a late connection checks cancellation before reaching the send guard. Response workers only build and enqueue in-memory results and have no logger/store writer. The focused DNS and blocked-response tests confirm no resumed request (`test_scene_comfy_send_checks.py:95`, `:140`). The frame protocol's cancelled guard remains installed on exit (`scene_upscale_transactions.py:519`).
3. **Raw response is not acceptance:** `_record_http` writes through `SceneMediaStore.write_bytes` and `write`; `_remote_validate` writes through the producer's `_GuardedLogger`. Their caller-thread guards retain full source proof (`scene_upscale_transactions.py:363`, `:392`; `scene_media_records.py:314`, `:326`, `:330`; `production_scene_clips.py:101`). The real POST drift test changes a protected dependency in the fixture server after receiving the request and confirms no raw response body, acceptance or submission is persisted (`test_scene_comfy_send_checks.py:167`). Later protocol guards and actual sends still recheck request/graph bindings.
4. **Fresh bootstrap/replay/recovery:** batch validation and aggregate replay return precede service creation; completed frame validation precedes the new preparation branch. The branch requires explicit whole mode, `service is None`, and absent original intent. Pending intents still enter the unchanged transaction first. The four producer controls cover fresh whole, segmented, pending and completed-frame replay, the unchanged 180-second argument, and service cleanup (`test_scene_upscale_service_preparation.py:13`). Existing aggregate replay control flow and unchanged service-start configuration were also inspected.
5. **Custom transports/factories:** default phase checks are still full guards; delegated opt-in is rejected. Only the default client with explicit whole mode receives the additional keyword. Custom factories receive their original call signature (`production_scene_upscale.py:127`). The existing delegated context contract was read; no change to it was found.

## Verification

Fresh reviewer run, through the required bootstrap:

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco07-http-budget-review-focused'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_scene_comfy_send_checks.py',
 'tests/unit/test_scene_upscale_service_preparation.py',
 '-q','--basetemp',"D:/VideoSi/cache/video-ai/temp/vco07-http-budget-review-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $script:VideoAiExitCode
```

Result: **16 passed in 1.24s; exit 0**. Log: `D:/VideoSi/cache/video-ai/logs/vco07-http-budget-review-focused-9f38cb014b6445959bb9e0918a4ffbad.log`.

Read, not rerun: the supplied affected-suite log `vco07-http-budget-safety-final-3b127cf297a14104aac8033ee043d0f8.log` records 98 passed in 10.52s, exit 0. Also read `profiled-frame-budget-control-c014cdc5eaf34e928c0058d1dca0c641.json`: it records 167.559 seconds within the unchanged 180-second fixture frame budget, 35 source checks, one loopback fixture POST, zero production POSTs and 87.938 seconds of modeled guarded preparation before tracking. This timing result is supporting fixture evidence, not an independently repeated benchmark or live acceptance.

## Issues

### Critical (Must Fix)

None found in the reviewed delta.

### Important (Should Fix)

None found in the reviewed delta.

### Minor (Nice to Have)

None identified that warrants a corrective change in this bounded review.

## Recommendations

Retain the fixture/live distinction in the continuation record. The review supports proceeding to the already planned final control and controlled continuation; it does not establish successful production upscale or VCO-07 completion.

## Declined to judge

- Prior native-batch, ByteGuard, media-coverage and send-artifact repair correctness: already reviewed, explicitly excluded from this review; unchanged writer/guard code was inspected only to verify the new transport's integration boundary.
- Whether the profiled costs accurately predict the next live production run: the supplied result uses historical costs and a loopback fixture; no production benchmark or source-profile regeneration was authorized for this review.
- Real frame quality, all 463 output frames, composition, final viewing/audio/subtitles, publication and zero-new-work production replay: future live acceptance obligations, not established by this HTTP delta or its tests.
- The pre-existing frame protocol's recovery timing design: protocol code and intent format are unchanged; this review checked that the new preparation condition does not move an existing intent outside its previous tracking entry point.

## Assessment

**Ready to merge? Yes, for this HTTP budget delta.**

The implementation follows the explicit transport and service-preparation rulings while retaining actual-send proofs, guarded durable evidence and default/custom compatibility. No Critical, Important or Minor defect was found; the independent 16-test run passed. This verdict does not claim live production success or authorize broader scope.
