# JIM-04 Tasks 1–2 independent review

Reviewed 2026-10-19. Scope: `reference_storage.py`, `external_https.py`, `reference_config.py`, `runtime/reference_settings.py`, the optional reference fields in `config.py`, and capability freeze/load in `production_inputs.py`, against `JIM-04-design.md` and the storage implementation report. No implementation edits, Git operations, cloud calls, real uploads, or email were performed.

**Final disposition:** Both reported findings below are resolved. The root agent fixed the unused fallback bypass by parsing every non-null fallback before choosing a model, rejecting unknown live model/storage fields, and excluding invalid unused supplemental capability files. The subsequent capability validation/copy race is fixed by validating the exact stable byte buffer before saving it. Scoped inspection and the seven targeted checks below confirm these reported routes are closed. No remaining Critical or Important finding was established within this review scope.

## Important: unused reference model configuration bypasses validation and persists credentials

**Locations:** `src/video_ai/reference_config.py:102–113`; `src/video_ai/runtime/reference_settings.py:29–36,119–126`.

`choose_reference_model()` returns immediately when `image_generation` has a valid capability. Consequently, a non-null `reference_generation` is never passed through `parse_image_generation()` in this case. `_options()` only checks the supplement's root fields, and binding then copies the entire unchecked source into `production/reference-images/config-source.json`.

This violates the design's requirements that `reference_generation` follow the image model parser and that the supplemental file contain no credential values. An otherwise valid reference model object with an additional `secret_key` field is rejected by the image parser when used, but is silently accepted and saved as plaintext when the chosen primary model has a valid archive. The immutable settings loader subsequently accepts the same source. The marker itself contains safe selected settings; the leak is in its persisted raw source copy.

**Reproduced with the real freeze/bind/load path:**

1. Use `runtime_run`, `configured`, `image_settings`, `capability`, and `storage_settings` from the existing tests to freeze a new paragraph run with no reference fields.
2. Write the ordinary valid capability for `jimeng_t2i_v40`.
3. Write a supplement with exactly the three permitted roots, valid capability paths and storage, and `reference_generation = image_settings()` plus `secret_key = "SYNTHETIC_REVIEW_SECRET"`.
4. Under a real `RunLock`, call `bind_reference_settings(frozen, store=_Records(run, lock), reference_settings_path=source)`.
5. Binding succeeds, chooses `jimeng_t2i_v40`, the copied `config-source.json` contains `SYNTHETIC_REVIEW_SECRET`, and `load_reference_settings(frozen) == marker` is true.

The reproduction used only a synthetic value and local files. Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-04-review-repro-3fb8aa860a8649dabd80ca14b566baa3.log`. Local evidence copy: `D:/VideoSi/projects/video-ai/runs/20261019-002227-a41356bcf7b8/production/reference-images/config-source.json`.

Validate every non-null `reference_generation` before selecting the preferred model and before copying raw settings; keep model preference unchanged. Add a regression for invalid or credential-bearing unused fallback settings. Initial raw project configuration has the same delayed-validation concern because `config.py` admits the optional raw fields without parsing their contents before freeze persists them.

## Verification and remaining scope

Bootstrapped targeted tests passed: `tests/unit/test_reference_config.py tests/unit/test_reference_storage.py tests/unit/test_external_https.py -q --tb=short` — **66 passed in 1.80s**, exit 0. Log: `D:/VideoSi/cache/video-ai/logs/jim-04-storage-config-review-352a666f3c7d4e2291364ef39a21e689.log`.

No additional Critical or Important issue was established in the reviewed storage/HTTPS code. The fixed canonical signing vectors, safe path restrictions, post-DNS/pre-send guards, callback authorization/cancellation, no implicit PUT replay, raw byte capability freezing, and copied-source recovery were inspected. Real service interoperability and private bucket access remain outside this local review. The unfinished runtime coordinator and candidate modules were excluded as requested.

## Follow-up Important: capability validation and freezing reread different source bytes

**Location:** `src/video_ai/runtime/production_inputs.py:129–130` in the follow-up revision.

The added `parse_capability(read_json(Path(source)), req_key=req_key)` validates one read, then `_copy_small(source, ...)` opens and reads the source again. A replacement between these operations passes `_copy_small`'s own stability checks because the replacement can remain stable throughout the second read. The copied bytes are not parsed, and `load_frozen_inputs()` verifies their recorded digest without validating the capability schema. This leaves a reproducible route for rejected credential-bearing capability bytes to be frozen despite the added check.

**Deterministic local schedule:** Start from a valid archive, then wrap `_copy_small` so that, only for the capability source path, it writes the same profile plus `secret_key = "SYNTHETIC_RACE_SECRET"` immediately before calling the original `_copy_small`. This models a source replacement after the preceding validation read. `freeze_inputs()` returns successfully; `production/reference-capabilities/jimeng_t2i_v40.json` contains the synthetic secret; `load_frozen_inputs()` accepts the run.

Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-04-review-freeze-race-65a466e3905846db9845a11845fa143b.log`. Evidence copy: `D:/VideoSi/projects/video-ai/runs/20261019-002408-d5f0b3bcf590/production/reference-capabilities/jimeng_t2i_v40.json`.

Validate the exact stable raw byte buffer before `_save_bytes()` writes it, retaining that same buffer for the stored SHA256. An optional validator in `_copy_small`, called after stability checks and before saving, would preserve the existing raw byte identity contract and avoid persisting rejected bytes.

### Final fix verification

`_copy_small(..., validate=None)` now runs `validate(raw)` after its `fstat`/current-file stability check and before `_save_bytes(destination, raw)`. Capability freezing passes a callback that runs `parse_capability(strict_json(raw), req_key=key)` on this same buffer. The parsed, stored, and hashed capability bytes therefore agree, and invalid replacement bytes are rejected before a capability copy is written.

Bootstrapped focused checks passed: unused fallback credential rejection; both live credential-field cases; source replacement between validation/copy; selected-model preference; original capability byte preservation; and supplement recovery after original files are deleted — **7 passed in 0.82s**, exit 0. Log: `D:/VideoSi/cache/video-ai/logs/jim-04-review-fixes-b3d31fdafb1844af8342eb6bd10a6bdb.log`. No broad suite was run during the root agent's ongoing verification.
