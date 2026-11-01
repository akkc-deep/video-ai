# VCO-07 removal review

Reviewed the product delta against the archived pre-removal bytes in `pre-remove-media-rechecks-de6f86c927144078826bb2f844950d90`, the removal plan, and the focused regressions. Archived code was read as data only.

Critical: none. Important: none. Minor: none.

The new branches apply to whole-scene media. Historical stores keep their prior checks. Whole-scene context still performs initial continuity admission; recurring input, tool, inventory, ancestor and capability audits are deliberately removed under the user's instruction. Lock ownership remains checked before sends and around immutable commits. Saved request/graph identity, durable-intent GET-only recovery, original-task evidence validation and PNG validation remain in place. The transaction's existing-intent branch cannot enter its new-intent POST branch. Final human review and publication requirements are unchanged.

Validation evidence: inspected the supplied final log, which reports **128 passed in 10.23s**, `exit_code=0`. Tests were not rerun. No production services or runs were invoked. This is one scoped code review; actual post-change throughput and completion remain operational verification work.

Additional recovery review: compared only the `process_started_at` exit-FILETIME change against its archived original and inspected the actual retained-child-handle/live-current-process regressions. Critical: none. Important: none. Minor: none. `GetProcessTimes` supplies exit time as its second FILETIME; a nonzero exit time proves termination even while handles retain the process object. The existing handle cleanup, live creation identity and refusal on access/query uncertainty remain intact. Inspected `vco07-ended-owner-green-8ef2c3da4edc44dc914e96485c1700ed.log`: **42 passed in 1.51s**, `exit_code=0`. No reruns or production calls.
