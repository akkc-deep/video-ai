# LVA-03 Implementation Plan

> Execute inline using superpowers:executing-plans and test-driven-development.

**Goal:** Measure the existing owned phase and test a bounded read-only preparation candidate.
**Architecture:** One daemon worker owns only immutable job data, bytes and cancellation. The locked coordinator retains all validation, adaptation, network and evidence writes. Default remains serial.
**Tech Stack:** Python 3.12, threading, pytest, real FFmpeg, existing owned Comfy experiment tools.
**Spec:** `docs/task-designs/LVA-03-design.md`.

## Global Constraints

40 steps/CFG3.5 and original frames/IDs remain unchanged. Single Wan, serial chains, explicit parent acceptance, no persistence across review. LVA-02 remains strict. No old run changes, unknown POST retry, paid calls or production resume. GPU experiments require the pending explicit authorization.

## Review Focus

- Hung reads must not hold phase exit beyond two seconds or publish late results.
- Same-size source replacement and workflow/parameter drift cannot consume stale preparation.
- Worker must start with empty ContextVars and hold no store/logger/lock references.
- Cleanup/diagnostic errors must retain the original phase error.
- Already persisted intent/media must recover without a second POST/producer.

## Tasks

1. [x] RED/GREEN `tests/unit/test_scene_stage_preparation.py`: frozen job/result, single-slot budgets, independent first clips only, SHA/metadata, cancellation and empty context. Implement `PreparationJob`, `PreparedSceneInput`, `ScenePreparationPool`, `ScenePhaseMetrics` in `scene_stage_preparation.py`.
2. [x] RED/GREEN service identity and integration tests. Wire existing-handle verification, phase events and optional next-independent-first-clip preparation in `production_scene_clips.py`; expose only an experimental context manager, not a production config/schema flag. Keep graph creation/validation on coordinator; prepared graph consumption uses deepcopy and normal `_input`.
3. [x] Add `scripts/benchmark_scene_preparation.py`: four alternating real-FFmpeg offline normal/recovery pairs with direct producer/service/HTTP counts, original identities and existing probe PTS. GPU baseline/candidate cold1/hot3 only after explicit authorization, fixed LVA-01 inputs and parent review gates; default serial unless replicated benefit.
4. [x] Run design's targeted checks, independent review, JSON/Markdown results and board outcome. Complete only with real GPU and quality evidence; successor preparation follows board order after completion.

## Execution ledger

- Start: 2026-11-15 user requested “完成任务LVA-03”; complete design and linked handoff read; board READY -> IN_PROGRESS.
- Ruling: Use supplied checkout because required LVA-01/02 and cold-admission changes are uncommitted here; avoid reset/clean/stash/staging. Cost: shared-checkout interference; review focused diffs.
- Ruling: Existing detailed design fixes behavior, so execute the user's completion request without another design approval. No brainstorming of alternative architectures. Cost: any design flaw must be surfaced by tests/review.
- Pre-flight: task1 pool/job/event interfaces consumed by task2 coordinator and task3 benchmark; coordinator owns graphs and proof boundaries, worker only source read. The design explicitly retains graph_for on coordinator, so no worker template/store/context transfer.

- Task1 RED/GREEN: 17 missing/unsafe cases failed first, then passed. Task2 coordinator-copy and phase-log integration failures observed before wiring. Resource-start fallback and service startup-binding drift failed first, then passed. Current unit/transaction/send/GPU-driver/node target:79 passed in6.86s.
- GPU authorization: user explicitly replied that this local GPU comparison is authorized. Baseline low service root LVA-03-gpu-baseline-low-20261115-01, original40 steps/93frames cold1 followed by warm3; owned phases serial under scratch LVA-03 suite controller, child stages blocked on new parent reviews.
- Offline four alternating serial/candidate pairs and separate profiler samples are running; integration normal/completed recovery and prior generated-receipt interruption are running. No all-green/complete claim yet.

- Independent review: four material findings in GPU-only harness (stop-request persistence could bypass shutdown; diagnostic writes could mask original; consumed payload retained across next submit; idle/direct/recovery evidence missing). All five regression checks failed first, then fixes passed with85 unit/transaction/send/node tests in6.82s. No remaining review minor was reported.
- Runtime diagnosis RED/GREEN: Windows Python3.12 handle fstat ctime and path stat ctime differ (change vs creation). Existing unmodified source was rejected despite exactSHA. New os.utime case failed, then compare full handle-before/after and common path fields plus fullSHA passed. The original four-pair benchmark recorded2failed/discarded preparations per candidate and is NOT evidence of a functioning prefetch benefit; retain it, rerun corrected candidate in new report.
- Integration first command:6passed/1failed in781.39s; candidate consumption assertion exposed the above Windows mismatch. Corrected two-case phase integration is running. Prior generated-receipt recovery cases passed and their evidence remains valid; do not repeatedly decode them for bookkeeping.
- Final Ruling: GPU performance/quality/completion remains pending real samples and explicit human observations; code-review deferral is not acceptance. Cost if wrong: delayed completion rather than unsupported claims.
- Final Ruling: Predecessor GPU harness beyond new optional graph path and known legacy-model/invalid-run/continuity/delivery failures remain out of this change, not certified fixed. Cost if wrong: baseline defects persist and must remain named in reports.
- Final Ruling: Physical transfer counts cannot be inferred from model method hooks; report unmeasured. Device idle uses threshold5percent and max6s gap, whole phase observed spans, not exact CUDA idle. Cost if wrong: no weight-transfer acceleration claim.
- Final Ruling: Payload budget excludes small allocator/chunk overhead and normal active request graph; release consumed speculative source before next submit. Cost if wrong: RSS can exceed96MiB by allocator/normal-request memory; report is logical reserved payload, not RSS peak.
- Final Ruling: Existing single-service lifecycle is only audited, never claimed as a new speed improvement. Cost if wrong: no unsupported lifecycle acceleration attribution.

- Corrected offline four alternating pairs + separate profiler complete: normal18.965071/18.774368s, completed-recovery3.791601/3.720468s; every candidate normal consumes2, fails0, logical peak20288bytes. Recovery starts no worker yet varies1.88percent, so do not infer causal speedup from normal1.01percent. Source/generatedSHA and all frame/PTS evidence retained; normal3POST/12producer, recovery0/0. Report E:/VideoAI/scratch/benchmarks/LVA-03-preparation-corrected-results.json.
- Corrected real-FFmpeg phase tests2passed in98.66s. Current GPU baseline-low service session96514/trials5582, serial suite controller89684, state file records active root/completed phases. Old controllers28741 stopped/replaced before any later GPU phase; controller v2 reloads final driver before each phase. All streams log to new scratch LVA-03 paths.

- Final source-growth budget RED/GREEN: a14-byte file growing during read caused8192 underlying bytes to be read through BufferedReader. Switch worker file to buffering=0; new underlying-read counter verifies <=declared+1. Final target86passed in7.04s. Running GPU controller has already imported buffered preparation module; immutable fixed-source experiments remain valid for identical payload/media but are disclosed as that variant. No GPU regeneration solely for this resource-only implementation detail.

- GPU low/high four phases/16 native samples technically complete, each owned phase closed before review. Low/high baseline user-accepted4each. User explicitly authorized later high identical-content binding; actual candidate high fixed identities/video/tail match and4receipts written after completion, total12accepted. Low candidate equality proved but no future consent given for low; ask with next parent QA.
- Low observed warmP50 baseline473.314/candidate485.536s (+2.58percent); high476.574/482.310s (+1.20percent). Model method counts equal pertrial. Prefetch3consumed per candidate, read totals~6.5/7ms. No promotion; low idle-span single-tick difference is not precise idle improvement. Rebuilt actual full-frame/PTS evidence from existing stdout only, no probe/decode rerun; analyzer scratch LVA-03-enrich-existing.py. Parent baseline phase now running; child still not started.

- 2026-11-16 review gate: all6first-clip phases/24native samples technically complete; all6owned services verified start1/close1, no listener8189.12quality acceptances recorded. Low candidate4binding and baseline parent4watching+candidate parent4equivalence authorization remain pending; child0, no future-tail prefetch. Parent observed warmP50 baseline470.293/candidate470.362s (+0.015percent), method counts equal; whole-phase low-util spans24.555/12.265s include startup and do not prove pre-read causal benefit. Actual all24frame/PTS evidence extracted without new probe/decode.
- Continuation: state docs/task-designs/LVA-03-gpu-run-state.json contains exact original child source scene_0003_clip_0002 and pending replies. Do not re-run completed first phases, re-submit original IDs, create parent acceptances before user decision, mark taskcomplete or prepare LVA-04 yet. Once replies authorize, bind actual completed matching results then start fresh baseline/candidate child services, cold1/hot3, original81generated/77retained frames and accepted parent actualtail.

- Resume: user replied 没问题 to the prior final parent acceptance/equal-content and low-candidate binding questions. Actual completed fixtures/video/tail validated at admission;12new receipts recorded after that reply, all24first samples accepted. Child controller new roots LVA-03-gpu-{baseline,candidate}-child-20261116-01 starts one owned service at a time only after require_parent_reviews passes. Original81generated/77retained frames, real accepted parent tail, no default quality/config change. Controller session73024, log scratch/benchmarks/LVA-03-child-controller.log.

- Child startup uncovered driver/established-helper contract mismatch before any intent/POST: prepare_child seals on parent_root, run_child_trial copies child definition into fresh child root and retains requires_new_parent=True there. Corrected driver parent-side sealing before service launch and recovery via bound run_child_trial, not unbound run_trial. Two adapter/recovery tests failed first; real-file accepted-parent-tail contract test passed as existing-helper evidence. Final88passed in6.85s. Failed setup baseline-child-20261116-01 closed normally, zero child inferences; preserved as failed_setup_phases, not called a GPU redo. Fresh paired roots suffix02, controller session96776/log LVA-03-child-controller-v2.log. No first24GPU regeneration.

- Final outcome: user explicitly accepted the10.625s native parent/child chain and actual identical candidates. Final8receipts bound after checking input/profile/video/tail, all32accepted. All8measurement services and1zero-POST failed setup closed; all completed recoveries0HTTP/0media, observed28normalPOST plus4original first-baseline receipts kept separate.88unit target passed,2corrected phase integrations +5prior recovery cases passed. LVA-03 COMPLETED recorded before successor work.
- Successor: selected predefinedOrder4 LVA-04, observedNOT_STARTED, read complete design template and direct LVA-01/02 inputs. Researched official HF pair/revision/SHA and actual Wrapper sigma reference, native4step switch lacks LoRA, localSage/Triton/cache capabilities absent. Detailed native-first experimental design/handoff linked, NOT_STARTED->READY. No LVA-04 implementation/download/install/GPU or old-production resume.
