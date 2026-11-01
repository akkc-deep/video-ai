# VCO-06 early runtime review

Scope: `production_scene_color_repair.py`, `scene_color_repair_records.py`, `_scene_color_repair_validation.py`, `_scene_color_repair_media.py`, `_scene_color_repair_engine.py`, `scripts/scene_color_repair.py`, and the four production-origin guards, against the VCO-06 design. Existing read-only dependencies were inspected where needed to establish what their validators actually guarantee.

This is an early static review. No tests, media commands, network, subagents, commits or product edits were performed. Reproducers below are code-path constructions, not executed results. The known fixture/independent-PNG failure is excluded. Successful real-video acceptance remains unverified: the environment lacks actual playback tools, and the existing actual source lacks a current VCO-04 precheck. This review does not change that acceptance boundary.

## Important findings

### 1. Saved candidates accept valid reports from an unrelated producer

Location: `src/video_ai/runtime/_scene_color_repair_validation.py:273-280`; recovery-related location: `src/video_ai/runtime/production_scene_color_repair.py:199-206`.

The fresh `_audit` path binds each report to its manifest, audit run and expected VCO-04 engine. The saved-candidate path calls `validate_continuity_report` without any of these expectations, and does not read the candidate's `pair-producer.json` or `after-producer.json`. The ordinary validator validates an internally consistent report; it only compares these external expectations when supplied. Therefore fresh proposal checks are not preserved during later status/review admission.

Reproducer: start with a complete saved candidate and another valid ordinary continuity report from a different audit/manifest. Replace `terminal.after_report` (or `pair_report`) with that report Artifact, refresh the terminal's sorted closure accordingly, and retain the original candidate's producer files unchanged. `validate_saved_candidate` validates the foreign report in isolation. Review then derives concerns from that foreign report. In recovery, a producer record's manifest is likewise not compared with the expected request/after manifest, and its engine epoch is not checked.

Small fix: centralize validation of candidate-owned report producers. Require exact producer schema, candidate ID, intent Artifact, bound epoch and expected manifest; pass its exact audit run, manifest and verified epoch engine to the ordinary report validator on every fresh, saved and recovery path. Rebuild/validate the after manifest's permitted substitution against the original assessment and this candidate's VCO-02 frame records. Require the returned report closure to be represented in the terminal closure. Add a foreign-report swap regression with otherwise valid report bytes and digests.

### 2. A shortened media frame declaration also shortens the required source playback

Location: `src/video_ai/runtime/_scene_color_repair_media.py:206-218`; consequence: `src/video_ai/runtime/_scene_color_repair_validation.py:228-229`.

`validate_media` checks that `media.frames`, `pts`, and frame-map rows agree with one another. It reads the original mapping but never requires `media.frames == original.retained_frames`. `review_expected` then uses this unverified count for both the original-source and playback review ranges. Complete native coverage is therefore not preserved when reloading a saved candidate.

Reproducer for any candidate with F > 1: change `media.frames` to `1`, retain only its first PTS and the first `frame_map.frames` row, and update the frame-map/media/terminal Artifacts and closure. Keep the actual source, master, playback and reports unchanged at F frames. All existing frame-map comparisons succeed for the retained first row. The expected review ranges become `[0,1)` for the F-frame original source and F-frame playback, and a review using those incomplete ranges passes the equality check.

Small fix: require exact equality with the original retained frame count before accepting media. Validate the saved source/master/playback measured frame tables against that count and rational timing. Derive each review range from its verified media identity and measured frame count. Add a saved-metadata truncation regression that keeps all actual media bytes unchanged.

### 3. Saved media can declare the original raw source as its repaired master

Location: `src/video_ai/runtime/_scene_color_repair_media.py:197-218`; related saved-output admission at `src/video_ai/runtime/_scene_color_repair_validation.py:259-280`.

The saved media validator hashes listed files and checks the frame map's self-declared candidate identity. It does not bind the candidate to the canonical `master.mp4`, inspect command receipt bodies, validate measured roundtrip/residual/full-frame records, or connect the after-report frame sources to `media.candidate`. Thus the declared candidate can change while all genuine rendering and after-report evidence still describes a different file.

Reproducer: on a valid completed candidate, set `media.candidate` to `intent.binding.source`, set `frame_map.candidate` to that same raw-source Artifact, and refresh the frame-map/media/terminal Artifacts and closure. Keep the genuine encoded master, playback, receipts and after report unchanged. Every current media check still succeeds: the source exists, frame-map media identities agree, the recipe declaration is unchanged, and the coordinates remain valid. Review can now bind `candidate` to the original uncorrected video while its playback and after evidence describe the repaired video.

Small fix: derive canonical candidate/playback/last-frame/map paths from the candidate folder and enforce them. Validate receipt schemas, successful command results, source/target/tool identities and exact recipe arguments; bind VCO-02 sidecars and after-report frame sources to the same master. Validate the persisted measured output checks on saved/recovery admission rather than accepting their Artifacts merely because the files hash correctly. Add a raw-source/master substitution regression.

### 4. A passed review can reclassify a confirmed original color defect as absent

Location: `src/video_ai/runtime/_scene_color_repair_validation.py:185-204`.

The validator checks whether `resolved_in_candidate` is legal when that disposition is chosen, but it does not require it for before-report color concerns already confirmed by the precheck. `not_observed_in_full_playback` accepts any concern when all checks pass. This contradicts the design rule that an original confirmed color issue can only be recorded as resolved in the candidate, retaining the original defect and supplying after/fit evidence.

Reproducer: take an otherwise valid passed review containing a confirmed before-color concern. Change that response from `resolved_in_candidate` to `not_observed_in_full_playback`, set `references=[]`, keep a nonempty reason and all checks passed. The response remains valid and contributes no failed/unverified state. The review no longer needs the corresponding after-report and fit references and denies the original issue the precheck confirmed.

Small fix: for a passed review, require each precheck-confirmed before-color concern to use `resolved_in_candidate` with the existing mandatory after/fit references. Continue to allow `confirmed_issue` or `unverified` to produce their corresponding nonpassed outcomes. Add a regression for replacing a resolved response with a not-observed response.

## Other reviewed boundaries

No separate Critical finding or minor finding is reported. The visible status path invokes readers/validators and contains no direct persistence, extraction or encoding call. The new origin guards reject explicit research paths/records at the four inspected low-level boundaries; no concrete production-import bypass was established in this scoped static review. Existing failed-review submissions take precedence over passed receipts on reread. These observations are limited to inspection and are not test or real-playback acceptance evidence.
