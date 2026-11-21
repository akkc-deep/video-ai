# LVA-07-04 final review and resolutions

Fresh read-only reviewer `/root/lva0704_final_review` reviewed base `75c45cbf` through `1af632d`, using the design, plan and five Review Focus items. Verdict: fixes required. The reviewer did not execute GPU/models/services. All nine findings were accepted and addressed in one author fix pass; no second review or independent approval of the final revision is claimed.

| Finding | Resolution | Verification |
| --- | --- | --- |
| Duplicate graph requests can queue another inference; extra envelope options | `/prompt` and `/api/prompt` require exactly prompt/client_id, original durable intent, one atomic mode claim before enqueue, original accepted UUID archive | worker claim test: wrong client, extra envelope, repeat/one slot; CPU route refusal |
| Collected media can differ from worker promotion; mutable tool/dimension fields | SHA against promoted proof, encoder intent/result and generation binding; profile-pinned tools/dimensions; owned content proof adopted without a second decode, restart decodes once | synthetic93-frame768x432 test, corrupt promotion receipt, tool drift, completed0HTTP and proof expiry |
| Controller can pass after crash/forced stop/resource error | success requires no error/timeout, exited/port closed, graceful exit0; GPU use remains unknown unless observed | controller finalization cases and actual CPU exit0/closed-port result |
| Archived history/media cannot finish without live server | strict original history/client/graph/prompt/output checks and local archive collection | removal of technical-complete then original-only recover,0HTTP/0producer |
| Native parent validator rejects Wrapper layout | Wrapper-aware same-mode/profile original completion, stopped service, exact accepted media, child input equals last PNG | accepted Wrapper parent plus wrong mode/input/review drift |
| Historical markers do not authenticate executed software | fixed Comfy Git blob inventory and independent installed runtime content snapshot; bootstrap binaries before launch, actual native binaries/core source once, imported source verified before execution with native leases and no unrelated pyc | software drift/deny-write test and updated actual CPU worker import/HTTP probe |
| Generic schema keys accept missing arguments/output drift | fixed required/optional argument types, consumed enum choices and exact output slots | missing model_name, missing wan choice and wrong VAE output slot |
| Real worker can accept offline fixtures; admission envelope is unbound | worker/controller require experiment kind and separate05 authorization; server matches original admission ID/profile/current epoch; admission lost-response GET only | offline fixture refusal, CPU routes, original admission response-loss test |
| Pair SHA excludes trace/ID; actual missing targets/exceptions can pass | receipt binds original admission ID and complete witness file SHA including trace; actual targets and exact no-img exception rechecked; sequential owner disposal | ten actual pinned-body CPU fixtures, success receipt/trace SHA and actual-target drift |

Review failure reproductions are preserved in scratch `LVA-07-04-review-*.log` and `LVA-07-04-review-runtime-red/`. Final validation is recorded in LVA-07-04-results.json; older failed/provisional logs are retained. The CPU runner's first reviewed attempt classified Wrapper utilities as Comfy core because the Wrapper lives beneath Comfy; the source-root predicate was corrected, then all ten fixtures passed. No algorithm/policy bytes were changed.

Declined-to-judge behavior: actual14B/GPU forward/offload, full resource peaks, real video quality and throughput. Ruling: retain all as unverified LVA-07-05/06 work; a CPU mechanism fixture cannot supply these outcomes. Cost if wrong: a future authorized run may fail its gate; it stops without replacement generation.

No deferred minor findings were returned. Existing production/default/native workflow and fixed patch/policy bytes are outside the diff. User workspace WIP is retained.
