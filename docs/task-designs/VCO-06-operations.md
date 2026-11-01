# VCO-06 local research candidate operations

The entry point is `scripts/scene_color_repair.py`. It never advances generation, upscale, composition or publishing. `research_candidate_reviewed` means only that a candidate has a complete authored review; `production_ready` remains false.

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'scene-color-repair'
& $VideoAiPython -B scripts/scene_color_repair.py status --run-dir ABSOLUTE_RUN
& $VideoAiPython -B scripts/scene_color_repair.py propose --run-dir ABSOLUTE_RUN --request ABSOLUTE_REQUEST_JSON
& $VideoAiPython -B scripts/scene_color_repair.py review --run-dir ABSOLUTE_RUN --review ABSOLUTE_REVIEW_JSON
```

Use one operation per invocation. Proposal exits: noop/abstained 0, awaiting review 3, blocked 2, failed 1, interrupted 130. Review exits 0 only for a complete research review. Status reads existing records without creating an output directory or running new diagnostics.

The exact Request, Precheck, pair manifest, Review and artifact schemas are in `docs/task-designs/VCO-06-design.md`. All paths are explicit local absolute paths. Inputs bind the current original clip, current VCO-04 assessment/epoch, complete actual playback precheck, sealed repair profile and independent selected-image pair manifest. A normal production invocation without a request does not enable repair or add defaults to historical inputs.

The independent selected PNG needs an ordinary VCO-02 analysis record with a declared reference clip/time coordinate and a source-bound mapping proof. It is a still reference at the declared target coordinate, with no generated/retained frame index; it must not claim to be an extracted video frame. Empty or unproved mapping remains `unverified_mapping` in the ordinary analyzer and correctly causes abstention. This requirement was confirmed by the real CPU integration path; no geometry threshold is relaxed.

All F retained source frames, including frame zero, have `repair_ref_*` comparisons against that selected image. Adjacent and parent-join comparisons never enter the repair fit. The operation is chosen explicitly. Only sealed, qualified parameter directions are usable; there is no alternate-axis retry or clamp. Stable matched code values produce noop, missing support abstains, and failed encoding/roundtrip/after-report validation retains its failure outputs.

Candidate files are independent under `production/scene-color-repair/candidates/<UUID>/`. Original generated/source/request/graph, accepted or rejected observations, audio, subtitles and downstream media remain independent. `master.mp4` uses the fixed explicit sRGB/YUV444 recipe; `playback.mp4` is a standard High/yuv420p viewing copy. The viewing copy has its own identity and is the candidate media named in the actual playback ranges.

An interrupted partial attempt is retained. Repeating the same UUID verifies the retained state and does not rerender it. A new attempt requires a new UUID and `revision_of` pointing to the prior terminal, or its intent when no terminal exists. Every attempt starts from the original raw source. There are at most three attempts for the same raw source, operation and profile. Complete measured outputs can finish their terminal/template without another encode.

Complete viewing must cover each required original ancestor, the original source and the candidate viewing copy. Static frames, scores, an unfilled template and fixture-only declarations do not count as actual viewing. A confirmed original color issue remains recorded; a passed candidate review must explain its resolution using after-report and fit evidence. Any valid failed submission permanently rejects that UUID. A new epoch or changed evidence makes prior candidates stale.

The profile is conditional AI/oracle calibration on the old split, not a new blind test or proof of natural matching/lighting intent. It remains `production_eligible=false`. The software explicitly refuses importing research candidate media, records or receipts as production origins. Allowing repaired production parents requires a separately approved eligibility and import contract.
