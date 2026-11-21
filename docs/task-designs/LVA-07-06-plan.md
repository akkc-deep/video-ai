# LVA-07-06 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Execute the approved Wrapper cold/warm matrix with exact fixtures, recoverable original IDs, human quality gates and honest performance conclusions.

**Architecture:** Extend the existing isolated experiment with an explicit v2 contract. Matrix owns immutable fixtures, group/trial identities and authorization; existing loaders, samplers and durable transport retain their mathematical behavior. Each group owns one service epoch and four serial trials.

**Tech Stack:** Python, pytest, existing independent Comfy/Wrapper CUDA environment, existing FFmpeg/RealESRGAN; no dependency installation.

**Spec:** `docs/task-designs/LVA-07-06-design.md`, approved by user “同意” on 2026-11-20 following the concrete design and 32-sample/10–12-hour proposal.

## Global Constraints

- Preserve all pre-existing WIP and old runs; no production, Jimeng, native workflow, fixed third-party source, model or dependency changes.
- v1 remains 05/two samples; v2 is 06/8 groups/4 trials/32 samples, exact authorization and source identity.
- 768×432/16fps, original seeds/prompts; child81 generated/77 retained, other fixtures93/93.
- Single GPU/owner; RAM14GiB/VRAM21GiB/available commit26GiB startup; private18GiB/RSS24GiB/allocator20GiB; no total GPU deadline.
- Once necessary full decode; reuse content-bound proofs and completed outputs; no broad validation runs.
- Human acceptance gates control→fast and new same-profile parent→child. Never infer acceptance.

## Review Focus

- Cross-group authorization or path substitution must fail before POST (Task1).
- Same-seed warm trials must execute both experts rather than return cached outputs (Task2).
- An unknown accepted request must remain bound to its original client/prompt ID after restart (Task3).
- Generated81→retained77 must bind the retained last frame and preserve all original frames (Task4).
- Source changes must not turn old-v1 offline recovery into permission for new POSTs (Task3).

---

### Task 1: Matrix identities, profiles and authorization

**Files:** Create `src/video_ai/experiments/wan_wrapper_matrix.py`, `tests/unit/test_wan_wrapper_matrix.py`; modify `wan_wrapper_backend.py` v2 profile dispatch.

**Interfaces:** `create_profiles(common, contracts, kind='experiment') -> dict[str,WrapperProfile]`; `validate_profile(value) -> None`; `validate_fixture(profile,fixture) -> dict`; `graph(profile,fixture,trial) -> dict`; `authorize_group(root,authorization) -> dict`; `prepare_group(root,profile) -> dict`.

- [x] Write tests rejecting edited seeds/frame budgets, mixed profile identities, wrong group authorization and an unauthorized fifth trial; assert exact high/parent/child seeds and81/77.
- [x] Run `python -m pytest tests/unit/test_wan_wrapper_matrix.py -q -p no:cacheprovider`; expected missing v2 behavior before implementation.
- [x] Implement immutable fixture contracts, exact matrix/group manifests, explicit v2 profiles and frozen per-trial graphs; retain v1 dispatch.
- [x] Run same test command; expected all passing. Save result and source backup, no mixed-WIP commit.

### Task 2: Worker execution and per-trial cache/shape evidence

**Files:** Modify `wan_wrapper_nodes.py`, `wan_wrapper_text.py`, `wan_wrapper_vae.py`, `scripts/observe_wan_wrapper_comfy.py`; create v2 node contract and add tests in `test_wan_wrapper_matrix.py`.

**Interfaces:** worker `is_matrix`, `fixture`, `trial_id`, `require_gpu`, `validate_graph`, `claim_prompt`; `graph(...)` from Task1; expected token lengths and frame budget from frozen fixture contracts.

- [x] Add failing tests for distinct four trial claims, duplicate/skip/epoch rejection, per-trial node schemas/tokens,81-frame conditioning and variable complete text lengths.
- [x] Run focused tests and observe failures before changing worker code.
- [x] Implement v2-only worker guards, exact claim/accepted paths, graph token inputs, fixture seed/shape/token guards and per-trial evidence/stage metrics. Keep all model math, offload and pair validation unchanged.
- [x] Verify focused tests plus v1 backend/text/VAE/worker neighbors once; expected passing.

### Task 3: Matrix CLI, reviews, recovery and resource controller

**Files:** Create `scripts/benchmark_wan_wrapper_matrix.py`, `tests/integration/test_wan_wrapper_matrix_recovery.py`; extend client dispatch in `wan_wrapper_backend.py` and matrix module.

**Interfaces:** `MatrixClient` reuses existing original-ID transport; `init_matrix(root) -> dict`, `seal_child(root,group) -> dict`, `review(root,group,trial,decision,evidence) -> dict`, `report(root) -> dict`; CLI init/start-group/prepare/run/recover/review/seal-child/stop-group/report/postprocess.

- [x] Add failing tests for response-loss one POST, unknown no replay, completed recovery no HTTP/producer, exact control review and same-mode parent binding; unauthorized CLI must leave no intent.
- [x] Implement sealed group startup, immutable prepare/pair intents and v2 trial graph/client binding. Disallow old root restart and cross-profile/epoch continuation.
- [x] Implement original fixture/tokenizer-only preparation, explicit actual-user authorization, scoped metrics and resources; report must only read receipts.
- [x] Run matrix recovery and v1 recovery/CLI tests; expected passing and no model/GPU use.

### Task 4: Single-decode media and existing 1080P adapter

**Files:** Modify `wan_wrapper_media.py`; create `wan_wrapper_matrix_postprocess.py`, `tests/unit/test_wan_wrapper_matrix_postprocess.py`; narrowly adapt `scripts/postprocess_local_gpu.py`.

**Interfaces:** frame encoder/checker accept explicit expected frames default93; v2 collects generated and retained proofs, per-frame PNG sources and retained last frame. Postprocess accepts verified Wrapper result/fixture via explicit validators, never native marker forgery.

- [x] Add failing81/77 synthetic-media and review/source refusal cases; completed frame/parent reuse must not run producer again.
- [x] Implement generated full proof plus PNG extraction in one decode, exact[1,78) retained encoding/proof and content-bound result recovery;93 keeps generated=retained.
- [x] Reuse existing upscale/narration/font/subtitle/compose functions through explicit validation callbacks; cold parent frames shared among four matching child outputs.
- [x] Run focused real FFmpeg synthetic tests and neighboring Wrapper media tests; expected passing without GPU samples.

### Task 5: Review, seal and actual experiments

**Files:** matrix scratch root, task result JSON/Markdown, task board; no original-run writes.

**Interfaces:** final verified CLI and manifests from Tasks1–4.

- [x] Run the two focused verification commands in approved design; record exact outcomes, excluding no failures silently.
- [x] Request one independent whole-change review; address important findings with targeted RED/GREEN checks and preserve limitations.
- [x] Seal exact source/profile/matrix and real approval evidence; observe capacity, start first owned group, prepare once and run cold/warm trials serially.
- [x] Show actual videos at human gates; retain owner for thermal continuity, never auto-accept. Continue approved groups without asking for execution permission again.
- [x] After native acceptance, run full-frame postprocess under separate single owner, review actual1080P outputs and collect actual original-ID recovery/exit evidence.
- [x] Write outcome-level results and transition task toCOMPLETED only on successful acceptance or a real designed failure-stop branch. Missing execution or review remains unfinished.

## Execution ledger

- Start: user approved design with “同意”; execution proceeds inline under the existing completion request.
- Ruling: work in the established `E:/code/py/video-ai` v2 branch, with per-file pre-change backups — existing absolute source pins, large untracked predecessor delivery and approved source-root constraint make an extra checkout unnecessary — changes remain reversible; preserve all WIP and do not commit it.
- Pre-flight: Task1 profile/graph interfaces are consumed by2/3/4; Task2 claim/trial token is consumed by3/4; Task4 verified results feed5. All signatures above use frozen fixture contracts; no conflicting seed/frame authority.
- Ruling: run only approved focused tests, not the unrelated full suite — AGENTS.md and approved validation budget take precedence over generic skill defaults.
- Task1: complete; initial6RED failures from missing v2 module, then17 matrix/backend tests passed. Exact fixture budgets/seeds, profile/graph drift and authorization tests recorded in this session.
- Task2: implemented;4RED worker/token/81-frame failures then27 matrix/text/VAE tests passed. Rejected replay mutating active trial was reproduced with a failing assertion and fixed by updating active state only after the immutable claim succeeds.
- Task3: implemented; v2 reuses the existing original-ID transport (five recovery tests passed directly, without claiming a new protocol implementation). Missing CLI tests failed twice then17 matrix/recovery tests passed. Completed-real-media archive scenario is being added before final review.
- Task4: implemented;2RED encoding/81-frame failures then7 real-media/neighbor tests passed; missing postprocess adapter2RED then4GREEN, and interrupted owner archival1RED→1GREEN. Postprocess recovery archives the exited service identity, preserves frame receipts, and only starts remaining fresh frame intents; unknown original requests retain original IDs.
- Focused combined check before final additions:90passed in7.71s. This is software evidence only, no GPU or quality acceptance.

- Final review:12 concrete findings graded and addressed in one fix pass; mapping `docs/task-designs/LVA-07-06-review.json`. Latest102focused tests passed10.76s; no GPU.
- Ruling: request.input_sha256 is a canonical INPUT RECORD digest, not the adapted PNG digest; match the original input.json chain and selected/source/target identities independently. Actual frozen fixtures and05 read-only archive pass.
- Ruling: approval/all-native status checks use content-bound immutable metadata; only the selected artifact at a necessary recovery boundary rebuilds its full proof, avoiding32 repeated decodes for each later request.

- Actual matrix: `E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01`; matrixSHA5977b065d2056dc72e9e1a3f2fe113610aabb15df85a9c61cf387ebae0be5d86. Complete pair passed in epoch4cecf0fe-2236-4945-a2f5-f962b3a6c03d. Cold1 technical complete, human review pending; warm1 original04e8091c is executing. Hidden driverPID15800 (launcher17940) observes this warm1, then runs onlywarm2/warm3 with original-ID recovery, stops the owned service after this group or rejection/failure. It never starts fast or invents acceptance. Check its stateJSON before any manual warm action.

- Actual interruption: aftercold1/warm1 complete, hidden warm2 CLI hit OEM/UTF8 netstat decoding beforeintent/POST. Driver obeyed failure stop and originalepoch exited0; no warm2/3 samples. Actual user 视频没问题 binds cold and byte-identical warm1. Listener fix16RED→118focusedGREEN/11.09s plus actual hidden UTF8mode1/CP936 probe; three whole_scene recovery fixtures fail identically with old helper due exact-runtime-JSON config.
- Ruling: do not restart originalepoch, stitch fresh samples as warm, rehash/re-render completed videos, or silently increase32 authorization. New fullmatrix would require32 fresh+2 retained=34 total (~80minutes extra); scope decision pending. Task remainsIN_PROGRESS.

- Budget resolution: user replied 继续 to the concrete32→34/extra80minute complete-matrix proposal. Approved root02 allocation32new+2retained=34task total; no oldepoch restart. Existing118focused tests and actual hiddenCP936 probe stand; no code/recipe change or repeated test matrix needed before new sealing.

- Actual continuation checkpoint: root02 authorized32new+2historical=34total;309 source/small metadata artifacts archived. Low-control/low-fast/high-control each completed same-epoch cold1/warm3; all3owners gracefulexit0/unforced/portclosed. Fresh12technical/8qualityaccepted/4high-control pending actual response. Low fast user explicitly accepted same-byte repetitions. High-fast and allparent/child/final outputs unrun; no full matrix claim. Read root02/RESUME.json and results JSON; never restart completed groups.

- Next actual checkpoint: user 没问题 accepted high-control actual media and exact-byte repeats;4reviews saved. High-fast freshowner45604/epoch4611f8d0-8076-4e34-9771-eff98626273b passed fullpair and all4technical samples98.453/95.422/92.500/92.375s; then gracefulexit0/unforced/portclosed. High-fast quality question remains unanswered. Fresh16technical/12qualityaccepted, original2 separate historical; parent/child/1080P unrun. Continue only from actual high-fast review via root02/RESUME.json; completed groups never restart.

- Parent checkpoint: user 没问题 accepted high-fast actual media and all exact-byte repeats;4reviews saved. Parent-control freshowner46008/epoche8a20748-31c0-4c35-aba9-54c0850ef673 passed fullpair and all4technical samples1261.781/1255.625/1256.125/1255.609s; gracefulexit0/unforced/portclosed. Parent-control actual quality question unanswered; no child sealing or inference. Fresh20technical/16qualityaccepted; original2 historical. Parent-fast,child,1080P unrun; continue root02/RESUME.json after real response, never restart completed groups.

- Parent-fast checkpoint: user 没问题 accepted parent-control actual media and all exact-byte repeats;4reviews saved. Parent-fast freshowner28528/epochf0d4ef52-08f9-4af5-8b5f-9f3f369cd92e passed fullpair and all4technical samples98.406/92.344/92.453/92.688s; gracefulexit0/unforced/portclosed. Parent-fast actual quality question unanswered; no child sealing/inference. Cold parent last-frame SHAs differ (control716105b6…,fastfc70dcfa…); preserve own-mode input and whole-chain interpretation. Fresh24technical/20qualityaccepted; original2 historical. Child/1080P unrun; continue root02/RESUME.json after real response, never restart completed groups.

- Native technical complete: all8groups cold1/warm3,32unique prompt IDs,2880generated/2848retained frames; all8owned exit0/unforced/portclosed. User accepted control-child real quality/parent continuity and exact generated+retained repeats;28accepted total. Child-fast4technical89.969/84.484/84.422/83.391s pending actual quality/continuity response; actual170frame streamcopy preview provided. Actual completed child-control original-ID recovery0HTTP/submit/archive-producer, technical unchanged. Native quota fresh32/task34 exhausted; NEVER regenerate. 1080P unrun,26operations/2290new frames/24outputs plan prepared, human final gates retained. Continue root02/RESUME.json after real fast-child response.

- 1080P technical checkpoint: user 没问题 accepted final fast-child actual quality/parent continuity and exact generated+retained associates; all32native accepted.26serial postprocess operations completed2290unique accepted frameIDs/24finals; two parentcold93-frame sequences reused in matching chains. All8Wan+26upscale owners gracefulexit0/unforced/portclosed. All24finals technical1920x1080/16fps/AAC48k;6distinct complete media SHA cohorts,4trials each. Actual six final representatives and original audio/subtitles/continuity batch gate provided, unanswered. Evidence-summary and results drafted with cold/setup boundaries, filesystem UTC phase spans labelled, observed human interval union, scoped resources, extra2history and real0HTTP archive recovery. No native rerun or new tests. Task IN_PROGRESS until actual final24 acceptance; do not rerun any producer.

- Task5: complete successful outcome. Actual final user 没问题 accepted all24 final1080P picture/audio/subtitles/parent continuity plus6exact-byte cohorts;24review_final receipts saved. Fresh receipt-only CLIreport exit0 complete=true, native32/final24accepted, all8Wan+26postowners exit0/unforced/portclosed. Evidence-summary/results refreshed with actual final quality endpoints and closed response-interval union. Completion record docs/task-designs/LVA-07-06-completion.json; taskboard12/12COMPLETED, aggregate07updated with full prior05snapshot preserved, no successor/handoff. No new inference, media decode or tests at closure; sourceWIP preserved, no commit/push/production change.
