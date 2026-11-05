# Online Windows installation plan

**Goal:** A standalone installer downloads the public project, Python, tool runtimes, models and reference audio on a fresh Windows x64 PC, creates valid production configuration and opens video generation.

**Architecture:** `scripts/install_online.ps1` uses Windows curl for resumable downloads and portable 7-Zip for archive extraction. Tools and model revisions are pinned to checked public sources. No old-computer files, local credentials or historical acceptance records are required by the default existing legacy `make-video` strategy. Existing unrelated installations are protected.

**Constraints:** Canonical `D:\VideoSi` and `D:\code\py\video-ai` paths; compatible NVIDIA GPU/driver; public Chinese reference audio with its published transcript; GPT-SoVITS CPU/v2/non-half route; Windows Chinese font component for the existing Microsoft YaHei subtitle face. Keep existing generation review behavior. Do not run video/model inference during installer development or repeatedly hash large models.

- [x] Test URL construction, archive layout normalization, native exit propagation, configuration creation and source-independent generation launcher with small fixtures. Also tested partial download recovery and completed-file reuse.
- [x] Implement the standalone PowerShell installer and CMD entry. Download Python 3.12.10, Microsoft VC++ runtime, portable 7-Zip, ComfyUI v0.44.0, GPT-SoVITS v2pro-20250604-nvidia50, FFmpeg 9.0.2, Ollama v0.40.14, SDXL/Wan/RealESRGAN and GPT-SoVITS v2 model resources.
- [x] Create fresh voice/production/TTS YAML configuration and a generation launcher; pull qwen3:8b through an installer-owned temporary Ollama server. Only declare ready after startup and configuration checks pass.
- [x] Replace the primary migration instructions with online installation, retain offline scripts as an optional separate method, and run focused tests/static syntax checks. Result: 25 focused online/offline/bootstrap tests passed; PowerShell syntax parsed. Independent review confirmed public-source template and model-list compatibility. Corrected ownership receipt interruption windows. Public reference downloaded during source inspection (IEEE float WAV); a follow-up duration probe timed out. No large tool/model downloads or inference performed.

**Sources:** Public `akkc-deep/video-ai` commit `242f8a05f2ac69bb3ec3aa6d79c9a3257f1760b3`; public CosyVoice reference and transcript at `QwenAudio/CosyVoice` commit `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`; official GitHub tool releases and Hugging Face model repositories (selectable HF mirror endpoint).

**Limits:** Unpublished local changes/private voices cannot be downloaded without publication/URLs. The default is the project's supported legacy local pipeline, with its existing image review checkpoint. Actual video inference on a second computer remains untested here. Hardware drivers are a prerequisite; the script does not guess a GPU driver package.
