# Approved full narration default

User instruction: “后面的视频都按这一版来”, referring to the complete fresh Voyager 2 redub in `E:/VideoAI/work/20261128-203102-e4cae32ca40c`.

Keep the existing reference voice, reference-prompt transcript, seed 42, CFG 2, 20 steps, one atempo=.95 pass and whole-program -23dBFS target. New runs use 500ms paragraph silence and the exact spoken-guide/acoustic-removal process used for the approved delivery. Only delivered original speech is aligned. Older frozen 850ms runs remain readable and retain their original processing.

Implementation and verification:

- [x] Add failing checks for the new recipe, guard removal, request length, and historical recipe compatibility.
- [x] Add a standard-library acoustic guard helper and durable body cache; connect these before production alignment. Keep legacy behavior when the frozen recipe has no guard.
- [x] Run the targeted production/recovery checks and compare guard boundaries against the 137 real approved paragraphs without resynthesizing them.
- [x] Back up and update shared defaults, inline production config, repository recipe, persistent approved sample and project instructions. Verify all effective defaults agree.

Ruling: work in the current checkout because the existing uncommitted Vox production integration is the required base; retain all unrelated changes, make no commit or branch operation. No new voice design or visual-video generation is needed.

Verification: 19 targeted tests passed; the native helper reproduces all137 approved body PCM files byte-for-byte with the same cuts and no new TTS. Runtime default, legacy preference alias, repository recipe and inline production config agree. The persistent production sample is byte-identical to the approved full narration. Two independently reviewed ambiguous-boundary cases were reproduced RED and fixed GREEN; ambiguity now stops before body publication while preserving synthesis caches. A second review found no remaining Critical/Important issue.
