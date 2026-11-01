# VCO-06 numerical implementation evidence

Implemented Task 1 only in `media/color_repair.py` and its focused tests.

- `apply_constant_repair(rgb, *, operation, amplitude)` accepts nonempty uint8 RGB arrays, the four diagonal operations, and canonical finite numeric amplitudes with |a|<=8. It returns an independent array; candidate authority is enforced by the estimator, not this arithmetic primitive.
- `estimate_constant_repair(reference, current, *, operation, context, profile)` returns exactly `{status,operation,amplitude,correction_bound,fit_pairs,reasons}`. Context uses the exact six Request fields. The profile is supplied by the runtime closure validator; arithmetic checks its evidence-only identity and qualified/bound fields. It does not import experiments or open evidence files.
- Pair inputs are `(N,3)`, `(F,N,3)`, or a nonempty list/tuple of `(N_f,3)` uint8 arrays. Coordinates/deduplication and per-role 1024 sampling are runtime responsibilities. Every frame needs 81 points, and nonidentity fitting needs 81 informative points globally. Fitting deterministically selects at most 16384 informative pairs, retaining all points and frames for scoring.
- `score_repair_pairs(reference,current,repaired)` returns `{before,after,before_mae,after_mae,passed,reasons}`. Each before/after row is exactly `{source_frame_index,mae,p99_error,max_error,new_clip}`. Indices are zero-based source-frame sequence positions; aggregate MAE is weighted by all channels/pairs. Every frame enforces p99<=2, max<=4, no clipping increase and no MAE regression; aggregate improvement is strict.
- Stable maximum channel error <=2 is noop. Bounds are never clamped. Rejected fits have null amplitude. OpenCV threading and NumPy error settings are restored in a locked numerical context. Pixel work is preflighted conservatively; transform and scoring work in chunks.

TDD ran serially under the root agent's granted test token. Every command began with `. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment '<label>'` and invoked `$VideoAiPython` through `Invoke-VideoAiNative`. All pytest commands used `-q --tb=short -o cache_dir=D:/VideoSi/cache/video-ai/pytest/vco06-numeric --basetemp=D:/VideoSi/cache/video-ai/pytest-tmp/<label>`.

| Label / files | Result | Raw log under D:/VideoSi/cache/video-ai/logs |
|---|---|---|
| vco06-numeric-red / tests/unit/test_color_repair.py | 54 expected failures: numerical module absent | vco06-numeric-red-4d7ccecc19254f43805f6706c77584cf.log |
| vco06-numeric-green / same file | 54 passed | vco06-numeric-green-541796e9a13b4e38b0dbdf0d9131f4f9.log |
| vco06-numeric-corners-red / same file, `-k 'noncontiguous or preflights'` | 1 expected memory-preflight failure, 1 pass | vco06-numeric-corners-red-2e96bd841e6c4eb08f580d017cb1ef23.log |
| vco06-numeric-final / tests/unit/test_color_repair.py tests/unit/test_vco06_repair_calibration.py | 79 passed | vco06-numeric-final-a1a7cd926937456995e9bfc4dd5e2179.log |

Arithmetic byte equivalence covers every input code at negative/zero/positive amplitudes for all four supported operations against the frozen calibration script, imported only by tests. Independent literal fixtures also check linear-light encoding and rounding. Tests cover qualified intersection, existing-but-unqualified bounds, no-clamp refusal, context/support, variable frame counts, deterministic fitting, single-frame regression, sparse maximum error, reference-interior clipping and strict aggregate improvement.

No full suite was run: user deferred it to VCO-08. No commits or experiment refits. This is sampled conditional arithmetic evidence; it provides no full-frame semantic or production qualification. Whole-frame output clipping remains a runtime render check.

Read-only review subsequently identified frame-view allocation before the 4096-frame limit. A broadcast ndarray whose iterator raises reproduced this preflight defect in the five-test review RED run; `_frames` now checks ndarray frame count and list/tuple length before materialization. The final reviewed numeric count is 57; profile review evidence and shared final commands are recorded in `VCO-06-profile-report.md`.
