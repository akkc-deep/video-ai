# VCO-06 real input eligibility audit

2026-10-27. The user delegated sample selection with “你自己挑吧”. Selected `scene_0003_clip_0001` in original run `20261021-014723-4ebdc1fecab2`: the white egret first clip has a retained complete `human_video` acceptance and no parent. The other two accepted first clips were also checked as alternatives. This is an eligibility audit, not a completed repair proposal or new playback observation.

## Evidence

- Audit summary: `D:/VideoSi/projects/video-ai/runs/20261027-203906-a928789daa38/logs/real-input-eligibility.json`.
- Audit command/log: bootstrap + `Initialize-VideoAiEnvironment 'vco06-real-input-eligibility'`; `Invoke-VideoAiNative $VideoAiPython @('-B','D:/VideoSi/cache/video-ai/temp/vco06_real_input_audit.py')`; exit0; `D:/VideoSi/cache/video-ai/logs/vco06-real-input-eligibility-968dd9f9876c4e2898cd21b0c4cf91f7.log`.
- Reference metadata: `D:/VideoSi/cache/video-ai/temp/vco06-real-reference-95b4a518608849339b10a7fa970ad8cd.json`; strict PNG parser checks raw selected originals and preserves their byte identities.
- Reference command/log: bootstrap + `Initialize-VideoAiEnvironment 'vco06-real-reference-metadata'`; `Invoke-VideoAiNative $VideoAiPython @('-B','D:/VideoSi/cache/video-ai/temp/vco06_real_reference_probe.py')`; exit0; `D:/VideoSi/cache/video-ai/logs/vco06-real-reference-metadata-d58c88ad27c04a2694c40741b1160396.log`.
- Actual VCO-02 reference gate: `D:/VideoSi/projects/video-ai/runs/20261027-213719-2a4859b7241d/logs/real-reference-gate.json`; byte-identical canonical PNG copy, real ffprobe/PNG interpretation and `decode_analysis_frame` returned **interpretation=unknown,analysis=unverified,pixels=null**. The original bytes/mtime were rechecked unchanged. Bootstrap command `Invoke-VideoAiNative $VideoAiPython @('-B','D:/VideoSi/cache/video-ai/temp/vco06_real_reference_gate.py')` exited0; log `D:/VideoSi/cache/video-ai/logs/vco06-real-reference-gate-91936edb662b495290b5acfc74715f8c.log`.
- A prior inline `python -c` probe failed in Windows argument quoting before opening the source; retained log `vco06-real-reference-readonly-4a6dcc726e9547f1a781d76473bc69dc.log`. The file-based command above supplies the actual metadata evidence.

## Observed facts

| Clip | Retained native media | Original color interpretation | Existing observation |
|---|---|---|---|
| scene_0003_clip_0001 | 93 frames,16/1,exact per-frame PTS | BT.709 primaries/matrix,sRGB transfer,limited range;resolved | human_video passed;motion and color checks passed |
| scene_0001_clip_0001 | 93 frames,16/1,exact per-frame PTS | same supported declarations;resolved | human_video passed;motion and color checks passed |
| scene_0002_clip_0001 | 93 frames,16/1,exact per-frame PTS | same supported declarations;resolved | human_video passed;motion and color checks passed |

Selected source SHA256: `fb0d55e89f22fcf96a99ef55ba7433f40d7d41092eac025183d0c1101cab7639` (632088 bytes). Selected original image SHA256: `d29e1f201a58691c97eb221ff1c5bb5d675c7a0442c436d7fff8b3bb8fb5e94f` (2004519 bytes). Its `.original` suffix contains genuine PNG bytes; an explicitly bound byte-identical `.png` reference copy is an engineering format adaptation, not a color conversion or new truth image.

All three original selected PNGs have `srgb_intent=null,gamma=null,chromaticities=null,icc_sha256=null`. Their reference interpretation cannot be proved sRGB through the frozen VCO-02 supported PNG path. Renaming a byte-identical copy does not add missing color evidence. The existing original run also has no frozen VCO-04 continuity policy/current epoch and no current assessment or repair Precheck. Old complete playback acceptance confirms the original media; it does not supply this task's new color-issue/axis/intent precheck or candidate review.

The VCO-05 preserved source inventory was checked before and after this audit: **3011/3011 paths,bytes,SHA256 and mtime_ns matched both times**. Sources were only read. No candidate, new viewing claim, model request, GPU inference, production change or publication occurred.

## Consequence

These samples establish real source/native/metadata and preservation evidence. They do not yet establish an applicable natural-video correction or full candidate playback acceptance. The chosen clip cannot enter a valid research proposal until its independent reference color interpretation is supported and a new explicitly frozen diagnostic context/current assessment and actual repair precheck exist. A truly applicable candidate then still requires complete actual playback of original and candidate, including material/motion/flicker checks.

The task's natural-video acceptance remains unverified. Keep the conditional profile's `production_eligible=false`, preserve the original run, and report this gap alongside software verification. Do not count tiny CPU fixtures, static image inspection, file renaming, color relabeling or the original “正常” acceptance as a new repaired-video result.
