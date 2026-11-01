# VCO-04 production integration guards

The integration keeps schema-2 clip admissions separate from current continuity eligibility. `_require_scene_clip_base_acceptance()` and `_scene_media_base_context()` reconstruct historical media without granting a new operation. Public clip/media admission, media writer guards, new child submission guards, pipeline completion shortcuts and delivery check current continuity eligibility.

Existing child requests with a durable original intent retain their original GET recovery protocol. New children require their parent's current eligibility before input/request creation, service startup and submission callback checks. Completed historical descendants remain readable during reassessment.

The coordinator returns the existing `SceneClipResult` with `awaiting_continuity_review` at `source_clips` when a completed prefix or a missing aggregate encounters pending continuity evidence. It does not invoke model writers to resolve that wait. Original schema-2 complete data stays unchanged.

`make-video --continuity-review PATH` is a run-only action mutually exclusive with selection, observations, retry, revision and publication. It calls the evidence consumer and does not advance production. Completed delivery replay permits this consume action and checks current eligibility before reporting a delivery as currently admitted.

Revision origin reconstruction uses historical media admission. Enabled clip/upscale origin snapshots retain continuity records, raw review submissions and prefix observations so a subsequent run cannot omit later confirmed defects. New current eligibility remains local to the new run.

Verification so far:

- RED: bootstrap command `vco04-guards-red`, `tests/integration/test_scene_continuity_recovery.py`: 6 expected failures, exit 1. Missing review keyword/CLI flag, private base separation, completed-prefix guard and media writer callback were each observed. Log: `D:/VideoSi/cache/video-ai/logs/vco04-guards-red-18082d9b8c8647abb944a5c81635d384.log`.
- Additional recovery tests cover original source aggregate retention and waiting before any model writer when the aggregate is missing.
- GREEN: bootstrap command `vco04-guards-green2`, the recovery file plus `tests/integration/test_scene_pipeline_cli.py` and `tests/unit/test_scene_clip_runtime_recovery.py`: 26 passed, exit 0. Log: `D:/VideoSi/cache/video-ai/logs/vco04-guards-green2-bf875df7057544c894fdcd9aa85c80bc.log`. The first attempt had 24 passed and two legacy-mock failures caused by accessing missing `frozen.options`; the policy reader now accepts the existing lightweight legacy mocks.
- Further focused tests cover new-submit parent callbacks versus durable original GET recovery and the difference between confirmed defects and pending responses. Their run is pending the controller's serialized test slot.
- A subsequent read-only review of the continuity records/transaction implementation identified missing prefix-wide parent admission, exact original video receipt matching, historical prefix assessment provenance, and metadata origins for inherited copied media. Focused regressions for these findings are added to the recovery file; the controller owns the corresponding records-module fixes and serialized RED/GREEN execution.
- No actual model services, network, GPU work, publication or full-suite run was performed by this integration task.

These tests validate software admission behavior using explicit synthetic evidence; they make no claim of actual dynamic playback or production visual accuracy.
