# First scene video preview

User explicitly requested starting video production after approving request01. The full 107-scene production retains its own image-validation/selection pipeline. An isolated first-scene preview starts the installed Wan 2.2 I2V workflow immediately from the actually approved image, without inventing all-images or video acceptance.

- Source run: `D:/VideoSi/projects/video-ai/runs/20261104-053708-1a5f92e2ac83`.
- Selected candidate: `request_01_image_01`, SHA256 `c98a903bafaa77233f845b62b7c955d0d9fbd181f5d663bc7441d1113809c83f`.
- Preview run: `D:/VideoSi/projects/video-ai/runs/20261104-183353-8f8489730a99`.
- Original versioned Wan workflow/mapping/model files are reused and remotely validated.
- 93 frames at 16fps, 768x432, matching the first planned clip's frame budget. Motion text preserves the original departure line and adds the user's direction feedback (Earth behind on the left, probe moves away).
- Actual Comfy prompt: `e19d2840-2971-4830-a3ad-3216ad187e29`; client `e90713c3-f4b9-4c81-ad49-4668cb02eace`.
- Executor session: `90642`; launcher log `first-video-preview-a0ad8bc0c737470aa5f97a5de4c5f1c1.log`.
- Pointer/state: `D:/VideoSi/cache/video-ai/voyager-first-video-preview.json` and preview-run `preview/state.json`.
- Helpers: `D:/VideoSi/cache/video-ai/render_first_scene_preview.py` and `.ps1`.

The initial preparation `20261104-183234-9787c025b12d` was retired before any service or model submission because the source frozen effective config differed from its original source path configuration. The retry materializes correct absolute source paths using the existing revision configuration helper. The failed prefix remains preserved; no inference was repeated.

Actual verification: Comfy queue confirmed this prompt running, GPU 100% / ~16.9GB, websocket progress 14/25 at the low-noise sampler. Expected result `preview/scene_0001_preview.mp4`; the worker verifies matching graph/client/prompt history, one owned output, decoded frame count and dimensions before setting preview_ready. Preview remains separate from formal source-clips acceptance and publishing.

Full multi-scene background job remains session `81256`, log `reference-resume-6353ec10d1f5416abea7cc58337c8586.log`. Check its real status before reporting progress or starting a duplicate.

Completed: executor 90642 exited 0 and reported VIDEO_PREVIEW_READY at preview/scene_0001_preview.mp4. Worker checked original Comfy history graph/client/prompt/output identity, decoded 93 frames and 768x432 dimensions using ffprobe. State is preview_ready; video remains a standalone unaccepted visual preview (no narration or formal publication). Owned Comfy service closed after rendering. Do not submit this completed preview again.
