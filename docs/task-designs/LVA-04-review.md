# LVA-04 independent review

Read-only reviewer inspected the full new experiment path and native installed source, with no GPU, model import, download or repository mutation. No Critical findings or deferred Minors.

Three Important findings were reproduced as RED tests and fixed:

1. Launcher installation overrides could select unprofiled Comfy/Python. `verify_installation` now binds selected roots/executable in both parent and worker.
2. Native base-model resolution could shadow profiled model files through alternate search roots. Native UNET/CLIP/VAE lookups now check their resolved paths before loading; original weight contents are protected by the existing invocation leases.
3. Completed media authenticated only file SHA, allowing foreign trial reuse. Recovery now requires original profile/intent/accepted bindings and exact graph/input/trial/prompt identities, plus owned media paths and all three content hashes. Parent admission consumes the same authenticated completion.

A phase-failure cleanup regression was also reproduced and fixed during review: exact owned-PID stop request is written in finally without masking the original error.

Additional environment/manifest execution findings: native version module is `comfyui_version.py`; valid zero-byte package sources must admit an empty SHA; repeated `parent_child` IDs in prior results must preserve distinct parent/child source roots. Corrected with targeted regression where applicable. Draft manifest was corrected before authorization, updating only changed small source SHA and routing; successful large-weight admission was not repeated for that correction.

Declined-to-judge rulings:

- Native numerical compatibility, executed sigma, speed/VRAM and visual quality require the authorized GPU phase; remain explicitly unverified, so no speed/adoption claim is made.
- Remote downloaded bytes require the authorized download; local staging/SHA/no-overwrite implementation exists, but no download success is claimed.
- Existing production/predecessor defects remain outside LVA-04 and are not certified fixed.
