# TTS-VOX-06 Male Sleep Narration Correction

> **For agentic workers:** Use superpowers:executing-plans for the focused correction below.

**Goal:** 用户明确纠正音色要求：“纪录片的旁白，用来助眠，需要男声”。独立设计成年男声，提供舒缓短样本，并使 06 真正冻结该音色而不是旧网络参考。
**Architecture:** 可选的独立 Vox 音色资产，显式传入服务启动和 freeze_voice；保留旧配置/旧任务的默认绑定。声音设计生成参考，不克隆旧参考。随后用相同新参考生成短旁白以验证可控克隆链路。
**Tech Stack:** 现有 Python 3.12 / VoxCPM2 CUDA、标准库、pytest。
**Spec:** 用户本轮音色纠正；继承 docs/task-designs/TTS-VOX-06-design.md 的无损分段、停顿和实际采样点契约。

## Global Constraints

- 不覆盖旧音频或 GPT-SoVITS voice.json；不更改历史任务绑定。
- 不重复整篇长文/视频验证，只生成一个音色参考和一个短篇可控克隆样本。
- 主观男声/助眠效果等待真实试听，不用程序替代用户判断。
- 沿用当前 v4 未提交直接依赖，不提交、合并或推送。

## Review Focus

- 新服务与新 FrozenVoice 的 voice_id/reference_sha256 必须一致，旧缓存不得混用。
- 参考路径留在运行根；启动时只核对一次参考摘要。
- 未选择新资产时，旧配置及默认绑定不变。

## Task 1: Explicit voice asset selection

**Files:** Create `src/video_ai/voxcpm/voices.py`; modify engine.py/process.py/server.py/planning/speech.py; add tests/unit/test_voxcpm_voice_assets.py.
**Interfaces:** `load_voice_asset(path, runtime_root)`; `freeze_voice(config, voice_profile=...)`; `VoxServiceProcess(..., voice_profile=...)`; `load_assets(..., voice_profile=...)`.

- [x] RED：新音色/风格绑定、旧路径兼容、非法资产路径/摘要及服务参数传递。
- [x] GREEN：有限资产解析、显式传递、启动一次摘要校验；相关回归。

## Task 2: Concrete male sleep sample

**Files:** `scripts/experiments/voxcpm2_sleep_voice.py`, `config/voxcpm2-sleep-voice.json`, `docs/voxcpm2-sleep-voice.md`, new research record.
**Interfaces:** 生成独立 generic male reference.wav + voice.json；用新资产启动现有服务，生成舒缓短篇 WAV 和采样点结果。

- [x] 设计音色参考，不传旧 reference_wav_path；固定种子和现有模型参数。
- [x] 用新参考生成短旁白，保存资产与证据，停止本次拥有服务。
- [x] 相关检查、一次独立审查、更新使用文档和 06 音色状态。

## Execution ledger

开始：旧 load_assets 硬绑定 production voice_config，freeze_voice 也从同一旧 GPT 参考摘要取值。实际资产是从 CosyVoice 示例下载的 online-reference.wav；上一版“固定音色”只固定了该资产，没有满足用户本轮明确的男声助眠要求。
实现选择：音色描述为成年男声、温润中低音、沉稳自然、舒缓平稳、轻声但清楚、情绪克制；避免将“激动/惊叹”作为助眠默认风格。新资产显式选择，旧配置保持兼容。

Task 1 complete: 初始 11 failed / 1 旧路径兼容 passed；实现后 111 passed / 3 skipped。一个新测试错误沿用 fixture 配置内的真实 runtime_root，写入了两个独占测试文件；确认内容与创建身份后用 apply_patch 清理这两个文件，并将测试改为 tmp_path 的替换配置，后续不再写真实运行根。

Task 2 complete: 新资产 E:/VideoAI/shared/assets/voices/male-sleep-documentary-v1-20261127-011350-715610/voice.json；独立无参考声音设计 16.64 秒，随后实际控声克隆旁白 5 单元 / 35.074333 秒 / 1,683,568 采样点。样本 E:/VideoAI/scratch/benchmarks/TTS-VOX-06-male-sleep/20261127-011350-715610/audio/narration.wav。本次拥有服务退出 0。持久偏好 shared/config/tts/male-sleep-documentary.json，pending_user；旧配置/旧音频未改动。

Review: 一次独立审查，无 P1，3 个 P2（相对 profile 路径回读、停止异常时偏好发布顺序及保留原始错误、声音设计源码 provenance）。6 个复现测试先失败；修复后新增测试 18 passed。实际生成的源码提交与冻结提交一致，无需重生成音频。

Final verification: 12 个相关文件 271 passed / 3 skipped，6.79 秒，E:/VideoAI/scratch/logs/vox06-male-final.txt；仅跳过 Windows 符号链接权限。git diff --check 通过。主观男声/助眠效果待用户试听，不重跑完整长文或视频。代码和文档留在 v4 未提交。
