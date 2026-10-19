# JIM-04 reference candidates and read-only admission report

Implemented Task 3 and the Task 4 read-only Wan admission builder. This report covers only the candidate/reference-record slice; the root coordinator owns complete batch integration and final whole-suite verification.

## Files

- `src/video_ai/adapters/jimeng.py`: controlled `submit(..., image_urls=None)` and optional ownership guard propagation for submit/query/download.
- `src/video_ai/runtime/jimeng_reference_candidates.py`: durable reference requests, single-submit intents, accepted-task/query/download recovery, immutable provenance and existing candidate manifest shape.
- `src/video_ai/runtime/reference_image_records.py`: fixed baseline resolution, shared prompt, reference/capability/object/source validation, provenance and Wan start-image admission.
- `src/video_ai/runtime/image_selection_records.py`: narrow reference-request dispatch; existing pure-text request validation remains unchanged.
- `tests/reference_helpers.py`, `tests/unit/test_reference_image_records.py`, `tests/integration/test_reference_candidates.py`: offline authentic PNG and HTTP-level request fixtures.

## Interfaces for coordination

`resolve_reference_bindings(frozen, bible, plan, scene, accepted_batches)` returns an ordered list of `(full_candidate_dict, uses_list)`. The candidate retains its original path and includes `scene_id`. Order follows `bible.baselines`; `(scene_id,candidate_id,sha256)` duplicates merge into one image while preserving every use.

`build_reference_prompt(scene, bible)` returns the exact original prompt plus `\nVISUAL_BIBLE_JSON\n` and canonical JSON containing only the current scene's stable entity/variant/group rows in Bible order, together with global style.

`validate_reference_inputs(frozen, scene, bible, plan, references, settings)` returns `(parsed_model_settings, prompt)` after local frozen-marker, capability, accepted-source, decoded-original, upload-intent and object-receipt checks. It makes no cloud request. `references` has the design's exact URL-free schema, including its verified object record.

`generate_reference_candidates(frozen, scene, bible, references, *, settings, capability, client, paths, logger, lock, storage=None)` preserves all mandatory design arguments. The explicit optional `storage` collaborator supplies `presign_get`; it must expose the exact bound `.settings` mapping. `settings` is the complete immutable marker returned by `bind_reference_settings`, and `capability` must equal its capability. A missing storage collaborator only fails when a new submission actually needs URLs; accepted/result recovery does not presign again.

`verify_reference_provenance(frozen, scene, bible, plan)` returns the verified provenance after checking bound settings, fixed accepted sources/originals/object receipts and every logical request/intent. `reference_candidates(...)` additionally validates all accepted/result/output/download/candidate records and decodes outputs through the original strict candidate reader. The JIM-03 reader dispatches to it only when the first logical request has `reference_inputs`.

`build_reference_image_acceptance(frozen, units, timeline)` requires the real JIM-03 complete receipt and whole-set observation, rebuilds every selected start image and every associated scene's reference provenance, and returns the exact design Wan manifest. The caller saves it under its held store. `require_reference_image_acceptance(...)` rebuilds the manifest and compares `production/reference-images/wan-inputs.json`; it never writes or calls Wan.

`JimengClient(..., ownership_check=None)` forwards a set guard to the HTTPS boundary for submit/query/download. The reference generator binds real clients to its current held store. Submission temporarily composes ownership, remaining reference URL TTL and read-only byte identity snapshots; querying/downloading resets to ownership alone, so accepted tasks remain recoverable after input URLs expire. This guards the actual network send after DNS/TLS waits as well as the caller-side submission boundary.

## Recovery and admission rules

- New requests validate sources, object receipts, capability, prompt byte size and URL TTL before intent. A second complete local check immediately before submission catches source changes after the durable intent boundary.
- Intents persist the logical request digest, exact submit-body byte digest, ordered URL byte digests and issued/expiry evidence. Signed URLs remain in memory.
- An adjunct `submit-evidence.json` is saved after the intent and before the actual send. Its exact fields are `schema_version/run_id/scene_id/request_id/logical_request_sha256/intent_sha256`; the latter is the canonical digest of the complete intent. Read-only provenance and accepted/result recovery require this independent anchor, so changing only valid-looking body/URL hashes in an intent is detected. The design's exact request/intent/provenance/accepted/result/Wan schemas remain unchanged. Intent without an accepted task remains `submit_unknown` even if the adjunct marker was interrupted before creation.
- Intent without accepted task ID refuses with `submit_unknown`. Existing task IDs are queried; completed result/download records are recovered without presigning or submitting the original request again.
- Submission, accepted, downloaded and provenance boundaries support local fault injection. Missing provenance after completed requests is rebuilt without another cloud request.
- Object receipts bind their upload intent digest and an earlier accepted original path/byte digest; ETag is checked as an entity marker and never used as the content digest. Distinct selected originals with identical bytes share the one content-addressed object while retaining distinct scene/candidate reference slots. The preserved upload source must still be an earlier accepted, run-bound original with matching actual bytes/SHA; the actual-send guard independently checks every currently selected original as well.
- Legacy pure-text related scenes remain readable through JIM-03, but cannot satisfy JIM-04 Wan reference admission.

## Verification

All Python commands used `scripts/bootstrap.ps1`, `Initialize-VideoAiEnvironment`, and `& $VideoAiPython -B`.

Red runs observed before production implementation: four initial unit failures (missing reference record module and unsupported explicit `image_urls`); twelve initial integration failures (missing reference generator). Additional red runs exposed source replacement after intent, missing DNS ownership propagation, and commit source/schema/extra-field acceptance. The corresponding fixes passed their regression tests.

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-04-candidates-tests'
& $VideoAiPython -B -m pytest tests/unit/test_reference_image_records.py tests/integration/test_reference_candidates.py -q --tb=short
```

Result: **29 passed in 71.87s**. Coverage includes actual submitted reference URLs/shared prompt, one-original multi-use resolution, replay with zero HTTP/presign, unknown submit, original-task query/download recovery, capability prompt/byte/dimension/format limits, source/object/use/count/byte/prompt/TTL failures before submission, expired unsent URL re-signing, provenance tampering, accepted/downloaded/provenance interruption recovery, source changes after intent, and zero transmitted bytes after DNS ownership loss.

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-04-candidates-regression'
& $VideoAiPython -B -m pytest tests/unit/test_reference_image_records.py tests/unit/test_image_selection_records.py tests/integration/test_jimeng_candidates.py tests/integration/test_image_selection_flow.py -q --tb=short
```

Result: **96 passed in 168.36s**. This preserves historical pure-text candidates, exact original verification and the existing JIM-03 selection flow.

Final review then added the actual-send TTL/identity guard, shared-SHA source alias support and independent submit-evidence marker. Focused RED/GREEN commands after those changes:

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-04-candidates-ttl'
& $VideoAiPython -B -m pytest tests/integration/test_reference_candidates.py -q -k 'submit_ttl_guard or query_recovery_does_not_require' --tb=short
```

Result: **2 passed, 22 deselected in 9.20s**. The TTL test first failed with actual POST bytes transmitted after DNS advanced the clock by 3500 seconds, then passed with zero transmitted bytes. Original-task query recovery succeeds with the input clock advanced by 4000 seconds.

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'jim-04-candidates-evidence'
& $VideoAiPython -B -m pytest tests/integration/test_reference_candidates.py -q -k 'single_intent_hash_tampering or submit_unknown or submit_ttl_guard' --tb=short
```

Result: **4 passed, 22 deselected in 17.13s**. Both single-intent hash mutations first reproduced acceptance in a RED run, then were rejected with the independent evidence marker. Root independently verified its shared-SHA multi-baseline and JPEG integration regressions after the alias/MIME corrections. No further broad test process is running in this slice. The root coordinator will run final serial combined integration, historical and full-suite verification; the earlier 29/96-test results are intentionally distinguished from these final focused results.

No unresolved requirement or design conflict remains in this slice. The small evidence sidecar is an explicit coordination decision recorded above, not a change to any design-defined record schema.

## Limits

No real cloud, upload, SMTP, paid image generation, Wan request, model-service startup or Git mutation was performed. Capability fixtures are test inputs, not asserted service limits. Actual account permissions, private-bucket accessibility and visual image consistency remain JIM-08 observations. Source verification intentionally decodes originals repeatedly at admission and submission boundaries; this adds local test/runtime cost to keep mutable file changes detectable.
