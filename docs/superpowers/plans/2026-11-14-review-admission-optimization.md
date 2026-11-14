# Review admission optimization implementation plan

**Goal:** Reduce repeated review admission work without resuming video production.
**Spec:** `docs/handoffs/2026-11-14-review-admission-optimization-handoff.md` and the user's scoped execution request.
**Architecture:** Reuse admitted source inputs and semantic reads only within an owning artifact batch. Keep byte/identity/inventory dependency proofs and replay them to enclosing captures. Share a review progress snapshot, refreshing only the affected scene at atomic observation boundaries.
**Tech:** Python 3.12, pytest, existing revision/byte guards; no new dependencies.

## Constraints and execution decisions

- Work in the requested checkout against its existing uncommitted baseline; snapshot touched files under `.tools/review-admission-optimization-baseline`. Do not reset, commit unrelated work, create production revisions, run models or render/review existing video.
- User delegated design and implementation details, so execute inline without an additional design approval round.
- Preserve failed-observation immutability, parent acceptance, raw-byte receipt bindings, native/temporal behavior and batch early stop on blocked/failed results.
- Recheck source content, same-byte replacement, inventories, absences, shared ancestors and typed input identity; never reuse across closed scopes or threads.

## Tasks

- [x] 1. Add a small offline fixture for multiple inherited layers/shared ancestors and consecutive observations. Record baseline cold preparation, first receive and warm batch timing/calls. Add failing regression assertions before source edits.
- [x] 2. Reuse `source_frozen`, cache source clip/provenance semantic reconstruction with original byte guards in the existing artifact batch. Verify changes, mutable return isolation and capture completeness.
- [x] 3. Factor per-scene progress reconstruction; add an owning review batch snapshot. Refresh affected scenes and validate byte dependencies around original/receipt writes. Preserve public result/early-stop semantics and temporal fallback.
- [x] 4. Check cooperative stop before preparation, between reviews/read phases and before service/inference entry. Report precise phase transitions and receipt counts without repeated unchanged notices. Update the paused continuation script without executing it.
- [x] 5. Run only affected unit tests plus one representative offline admission integration flow. Measure the same fixture again; save comparison, checks, limitations and remaining issues in the handoff directory. Keep production paused.

Outcome: 139 focused checks passed (137 unit + 2 integration), benchmark in six isolated processes. Fair comparison uses the same input protection and includes final boundary cleanup: first receive -41.3%, warm three -47.4%, cold preparation +36.9%. See `docs/handoffs/2026-11-14-review-admission-optimization-results.md`. Independent review findings were reproduced RED and fixed GREEN. Production remains paused; no commit/reset/integration of unrelated work.

## Review focus

Source same-stat edits/replacement; new or missing dependency files; stale parent/request bindings; copied/closed cache contexts; cancellation after raw persistence but before receipt. Each belongs in the focused regression fixture or existing guard tests. Compare this task's diff against the saved working baseline, not HEAD.
