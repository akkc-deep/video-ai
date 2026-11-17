# LVA-06 independent review

One fresh-context read-only reviewer inspected all new benchmark/execution/offline,
CLI/observer and tests against the complete design/ledger. No Critical finding.
No live GPU/quality claim was reviewed. No second review was commissioned.

Material findings and fixes:

- Saved quality: original measurement stayed unaccepted after genuine final review;
  added immutable measurement event and saved-decision rehydration. Integration
  now obtains reproducible accepted cost from disk (observed RED -> GREEN).
- Copied native source/graph admission: current fixture/request/graph and exact
  planned rebind are verified before POST; actual parent tail/acceptance and frame
  input are checked too. Native image drift observed RED -> GREEN; added copied
  fixture refusal integration. Offline workflow identity explicitly admitted.
- Cross-invocation counts: persist each stage's actual counter delta; aggregate
  once, retain invocation counters separately. Fresh-backend regression observed
  372 instead of376 POSTs RED -> GREEN. Count direct subprocess and file-digest
  work without new media/file reads (direct-hash counter RED -> GREEN).
- Recovery mode: derive from recorded stage/trial evidence; interrupted active
  spans retain null monotonic duration and counters_complete=false. Regression
  includes native recovery mode and resource preservation.
- Native resources: expose native plus upscale resources by phase rather than
  dropping native device/RSS/model-method evidence. Regression asserts inclusion.

Additional self-checks: final pending review replay observed RED -> GREEN;
lossless concat has exact native16 contribution durations to avoid MP4 rounded
format.duration creating invalid joint PTS in tiny fixtures. Producer success
and technical proof are independently durable; unknown command never reruns.

Final verification: 77 passed /26.24s, command/log in LVA-06-results.json.
Real CPU offline actual helper paths: 16 fake native requests, 48 fake frame
requests, 12 real x264 compositions, all three fixtures, distinct original IDs,
actual ordered RGB/PTS/AV proofs. Completed replay delta is zero HTTP/producer/
decode/probe and zero stage-operation hashes; mandatory replay authenticity
hashes outside the operation are not represented as zero physical reads. Simulated user decisions are explicitly not real quality.

No deferred minor findings. Workspace ruling is recorded in LVA-06-plan.md.
