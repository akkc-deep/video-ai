# VCO-07 Task 1 implementation report

Task 1 software scope is complete in the existing shared workspace. The authoritative design is `docs/task-designs/VCO-07-design.md`; the task board and implementation plan were not modified. No worktree, Git metadata write, dependency installation, real model request, network request, media generation, or production observation was performed.

## Files and behavior

- Added `src/video_ai/planning/scene_execution.py`: pure `derive_scene_execution_clips`, `build_scene_execution_budget`, and `validate_scene_execution_budget` with the exact designed signatures and budget schema.
- Updated `src/video_ai/planning/scene_clip_continuation.py`: optional keyword `execution` in `_budgets`, `build_scene_wan_plan`, and `validate_scene_clip_frame_mappings`; historical calls retain the original budget/request/mapping path.
- Added `tests/unit/test_scene_execution.py` (73 cases), and extended `tests/unit/test_scene_clip_continuation.py` (50 total cases, including 12 new cases).
- Added this report. No other files were edited by this task worker.

Whole execution keeps one clip per scene, selected-image input, ordinal 1, no parent, zero conditioning head, and only explicit tail trimming. It checks integer types (including bool rejection), positive continuous complete scene coverage, unique exact scene identities, and the 320 retained-frame maximum. Whole derivation does not use the semantic plan's max_clip_seconds. Literal boundary cases include F=1/93/94/96/110/134/219/320; F=320 generates 321 and retains exactly [0,320). The three scenes 219/110/134 generate 221/113/137 and preserve all 463 timeline frames once. F=321 is rejected.

Segmented derivation invokes the original committed-budget checks, preserves every clip field, and retains the original 96 generated-frame guard. It never changes the input semantic plan. The whole request's seed_high is 264244520398999 plus that scene's first original semantic clip global index; seed_low remains zero. The tests distinguish the last scene's original index 4 from its new execution index 2. Whole requires the fast 768x432/native16/cut profile. Original text, PCM binding intervals, visual baselines, comparison images, and other fixed Wan parameters are preserved.

## Integration interfaces

`execution` is the full budget dictionary, not a replacement scene plan or bare clip list. `validate_scene_execution_budget(..., expected=...)` requires exactly `{run_id, mode, rendering_identity_sha256, admission}`. A runtime caller must obtain these expected identities from frozen inputs. Consumer planners revalidate budget structure, original plan/timeline digests, and derived clips using the metadata on the supplied budget; they cannot establish frozen evidence authenticity themselves.

The builder hashes the complete original semantic plan and complete `timeline.as_dict()` representation. Mapping timelines are also supported by the pure budget APIs; no timeline fields are dropped when computing the digest. The production request and mapping APIs retain their existing timeline-object interface. Admission is an exact `{path,bytes,sha256}` Artifact for whole, and null for explicit segmented; the pure layer checks its shape, absolute lexical path, positive integer bytes, and SHA syntax without file access. Runtime evidence closure, path containment, original-byte verification, locks, and persistence remain subsequent tasks.

Request planners reject execution with a legacy/old two-field configuration, mismatched explicit modes, and explicit modes without execution. Historical calls with no explicit mode and no execution remain supported. Prompt schema must be 2 for whole and 1 for other branches. Whole calls `validate_scene_video_prompt_contract(..., execution=execution)`; old and segmented calls retain the old validator arguments. Task 2's schema2 contract fixture is used directly for the whole request tests, so the tested whole positive prompt comes from reviewed whole-scene motion fields and excludes semantic legacy motion/audit data.

## RED evidence

All Python and pytest invocations dot-sourced `scripts/bootstrap.ps1`, called `Initialize-VideoAiEnvironment`, and used `Invoke-VideoAiNative $VideoAiPython`. Logs and pytest temporary/cache paths are under D:/VideoSi.

1. `vco07-task1-red-budget`: the first three tests were written before any implementation. Exit 1, **3 failed**, expected missing `scene_execution` API. Log: `D:/VideoSi/cache/video-ai/logs/vco07-task1-red-budget-8c64de36ead24946a0644f543c0ccc86.log`.
2. `vco07-task1-red-original-budget`: executed those same three assertions against the actual original `_budgets(plan,timeline)` through an in-memory module adapter, with no production code changes. Exit 1, **3 failed, 70 deselected**. The 320 and three-scene assertions fail because original budgets remain segmented; the 321 rejection fails because the original budget accepts it. Log: `D:/VideoSi/cache/video-ai/logs/vco07-task1-red-original-budget-fc0beef4a50141af8b5340bf9c431620.log`.
3. `vco07-task1-red-contract`: after adding the remaining pure and continuation contract tests, before implementation. Exit 1, **80 failed, 38 passed**, all new failures due to the missing module. Log: `D:/VideoSi/cache/video-ai/logs/vco07-task1-red-contract-b28a1a1ca8704c208dc179a7ed25f1ad.log`.
4. `vco07-task1-red-mode-boundary`: after the first core GREEN, new mode guard tests exposed the missing request/config boundary. Exit 1, **3 failed, 2 passed, 45 deselected**. Failures: `test_requests_refuse_missing_or_mixed_explicit_execution_modes[legacy_execution]`, `[mode_mismatch]`, and `[missing_execution_segmented]`, each because no ValueError was raised. Log: `D:/VideoSi/cache/video-ai/logs/vco07-task1-red-mode-boundary-b411cc9d7a40448ea8753609c2bdf53a.log`.

The first, third, and final runs used this command shape, with the listed command name and applicable files:

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco07-task1-green-final'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_scene_execution.py','tests/unit/test_scene_clip_continuation.py',
 '-q','--basetemp',"D:/VideoSi/cache/video-ai/temp/vco07-task1-green-final-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $VideoAiExitCode
```

The initial RED used only `tests/unit/test_scene_execution.py`. The original-budget RED used the following Python argument to `Invoke-VideoAiNative $VideoAiPython @('-B','-c',$Vco07RedScript,...)`, then the execution test file and `-k 'whole_320 or whole_three_scenes or whole_rejects_321'` with its own command-ID basetemp:

```python
import sys, types, pytest
from video_ai.planning.scene_clip_continuation import _budgets
baseline = types.ModuleType('video_ai.planning.scene_execution')
baseline.derive_scene_execution_clips = lambda plan, timeline, *, mode: _budgets(plan, timeline)
sys.modules[baseline.__name__] = baseline
raise SystemExit(pytest.main(sys.argv[1:]))
```

The mode-boundary RED used only the continuation test file and `-k requests_refuse_missing_or_mixed`, with its own command-ID basetemp. Each expected RED was followed by inspection and the corresponding implementation; no failed batch was reported as passing.

## GREEN and review evidence

- Initial core GREEN: exit 0, **118 passed**. Log: `D:/VideoSi/cache/video-ai/logs/vco07-task1-green-core-febe346b4b94482da3990c0794429d65.log`.
- Final core and continuation GREEN after mode guards and real schema2 whole request tests: exit 0, **123 passed in 0.26s**, no skips or warnings. Log: `D:/VideoSi/cache/video-ai/logs/vco07-task1-green-final-1d837baba949460bb2fe674c534ccd08.log`.
- Read-only `git diff --check -- src/video_ai/planning/scene_execution.py src/video_ai/planning/scene_clip_continuation.py tests/unit/test_scene_execution.py tests/unit/test_scene_clip_continuation.py` produced no whitespace findings. Git emitted its ordinary LF-to-CRLF working-copy notices for the tracked continuation files; no Git metadata was changed.

The final targeted run covers deterministic budgets, complete native frame mapping, strict identity/schema drift rejection, expected admission shape, unchanged semantic inputs, segmented equivalence, original semantic seed indexing, complete narration, schema2 prompt consumption, and invalid profile/mode/budget rejection. Full-suite testing is explicitly reserved for VCO-08 by the authoritative task design and was not run. Runtime evidence authenticity, persistence/recovery, consumer integration, actual generated media quality, observations, upscale/composition, and publishing are outside this Task 1 software result.
