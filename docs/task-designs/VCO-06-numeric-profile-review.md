# VCO-06 numeric and sealed-profile review

Scope: `media/color_repair.py`, `runtime/_scene_color_repair_profile.py`, their two unit-test files, and `tests/repair_profile_helpers.py`, against design sections 2, 4, 5 and Tests. This is a static, read-only product review. No tests, media commands, experiment execution, network, commits, or product edits were performed. Existing reported evidence (56 numeric, 25 profile, 23 calibration tests; actual r2 closure of 12,004 Artifacts and 12,209,702 parsed metadata bytes) was supplied, not independently rerun.

## Important findings

### 1. Same-size, restored-mtime changes after hashing survive closure closeout

Location: `src/video_ai/runtime/_scene_color_repair_profile.py:131-135`; related cached return at lines 102-106.

`_Evidence.verify` initially hashes a file, but `finish` compares only size, mtime and inode. A file changed after its first verification can retain all three values and therefore pass the final closure check. The returned Artifact then describes bytes no longer on disk. The existing drift tests change files before the initial verification, so they do not exercise this interval.

Reproducer (not executed): create `_Evidence(Reader())`, call `verify` on a valid identity, save the file's stat, overwrite one byte without changing length, restore its original mtime with `os.utime`, then call `finish()`. It returns the original Artifact without checking the changed digest. The same sequence can occur through a reader-check hook during a complete `verified_profile` call, after a dependency has been hashed and before closeout.

Smallest fix: rehash every captured dependency at closeout using bounded reads and deadline checks, compare to its captured digest, and retain the before/after stat checks. Add an adversarial mutation after initial verification, with size and mtime preserved.

### 2. A widened correction ceiling need not agree with any frozen measurement

Location: `src/video_ai/runtime/_scene_color_repair_profile.py:225-255`, `342-349`, and `409-440`.

Result files are completely hashed but their measurement rows are opaque. A ceiling is accepted whenever it is finite and in `(0, 8]`; equality between the profile and seal proves only that these two declarations agree. Nothing checks the ceiling against the saved calibration estimates or rechecks holdout claims against their saved result rows.

Concrete mutation reproducer (not executed), using the fixture helpers' `load` and `save` semantics:

1. Start from a complete valid study. Keep every calibration result, holdout result, independent result identity, source pack, frozen input and original source byte unchanged.
2. In `thresholds.SEALED.json`, change the ceiling of an already qualified direction to `8.0`. Save it and update `threshold-seal-identity.json` to that new identity.
3. Change only `evaluation.json`'s `thresholds` identity to the new seal identity, then save the evaluation.
4. Update the profile's `thresholds`, `evaluation`, and `calibrated_bounds` accordingly, preserving its equality with all evaluation fields.
5. `verified_profile` has no check that can reject this widening: the original result identities still match, the finite ceiling check succeeds, and all existing holdout case flags remain accepted. An originally approximately `0.019` qualified exposure ceiling can become `8.0`.

This finding concerns contradictory declarations versus unchanged measured evidence. It does not assume that adjacent digest sidecars provide an external authenticity anchor, which the design does not specify.

Smallest fix: stream the saved measurement rows and replay only the existing bound/qualification derivation used by calibration closeout. Compare the derived amplitude ceiling, injection limit and holdout case flags with the seal/evaluation. This requires neither refitting nor a new holdout run. Keep bulk rows outside the parsed-metadata budget by retaining only bounded per-direction aggregates. Add a test that changes the declarations and downstream digests while retaining all measurement files unchanged.

### 3. Holdout can qualify a direction with no eligible calibration sources

Location: `src/video_ai/runtime/_scene_color_repair_profile.py:339-359`.

Calibration and holdout coverage are computed, but a non-null calibration bound is permitted when `coverage['calibration']` is false. Qualification at line 359 depends only on holdout coverage and case flags. Consequently, the loader accepts a direction with an explicitly insufficient calibration population and still exposes a usable amplitude ceiling. The protocol requires minimum coverage in each split.

Minimal reproducer (not executed): call `_directions` with the complete ten-direction grid, twelve calibration sources marked ineligible, twelve eligible holdout sources covering all six genres, bounds containing `eligible_sources=[]`, `coverage_sufficient=False`, a valid non-null grid limit and positive ceiling, and checks containing complete passing holdout cases. The function returns qualified directions. It should refuse the non-null bounds or return no qualified directions. A full-profile equivalent updates the calibration metadata/result identities and matching seal source summaries; the missing coverage condition is unchanged.

Smallest fix: refuse non-null bounds when calibration coverage is insufficient and require coverage in both splits for qualification. Test insufficient calibration coverage with sufficient holdout coverage independently.

### 4. Frame-count rejection occurs after potentially unbounded allocation

Location: `src/video_ai/media/color_repair.py:90-103`, particularly line 95.

For `(F,N,3)` ndarray inputs, `_frames` executes `list(value)` before checking the 4,096-frame maximum. NumPy broadcast views can represent an enormous `F` using a three-byte backing buffer; this conversion creates one ndarray view and one list slot per frame before the input is rejected. Thus the advertised resource preflight can itself exhaust memory.

Reproducer (not executed): `seed = np.array([[[100,100,100]]], dtype=np.uint8)`; `frames = np.broadcast_to(seed, (10_000_000,1,3))`; call `score_repair_pairs(frames, frames, frames)` or the estimator. The first `_frames` call attempts to build ten million frame objects before reaching the frame-limit error, far beyond the 128 MiB working budget.

Smallest fix: validate ndarray dimensions and `shape[0]` before converting it into frame views; likewise check list/tuple length before copying. Add a broadcast-array regression that verifies rejection before iteration/materialization, without actually constructing millions of frame views.

## Minor findings

None reported. The reviewed transform, projection, quantization, per-frame scoring, informative-pair selection and qualified-direction sign mapping match the written numerical contract on inspection. Coordinate uniqueness, full-frame clipping and actual observation remain caller responsibilities and were not treated as defects in this scoped review.
