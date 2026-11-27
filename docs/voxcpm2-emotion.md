# VoxCPM2 情绪导演（TTS-VOX-05）

已实现完整文案的一次 Ollama 结构化规划、原文范围覆盖检查，以及带原因记录的默认叙事回退。[任务设计](task-designs/TTS-VOX-05-design.md)；[原始实测和验证结果](research/TTS-VOX-05-result.json)。本模块供 06/07 消费，当前 make-video 入口和默认 GPT-SoVITS 后端不变。

## 调用

```python
from video_ai.adapters.common import HttpClient
from video_ai.adapters.ollama_emotion import EmotionDirector

# logger 是当前调用方的 RunLogger，服务生命周期由调用方持有。
director = EmotionDirector(
    HttpClient(config.services['ollama'], config.timeouts['ollama_request'], logger),
    base_style='保持固定音色，沉稳自然，具有纪录片叙事感',
)
plan = director.plan(original_text)
```

模型为现有 `qwen3:8b`，使用 `/api/generate`、JSON schema、temperature=0、think=false、stream=false、keep_alive=0。每篇一次请求，没有自动纠错或重试。`cpu_only=True` 可显式关闭 GPU offload。完整输入和输出预算从 32768 起倍增，最多 131072 上下文；超过容量保留全部原文并回退，实际模型或设备不支持请求容量时也记录服务失败并回退。没有裁剪原文或暗中分批。

`plan` 包含：

- `schema_version=1`、`status=planned|fallback`、`model`、`base_style`。
- `source_text`、`source_sha256`，以及有序 `spans`。
- 每个范围的 `span_id`、`start/end`（Python Unicode 字符半开坐标）、`original_text/synthesis_text`、`emotion`、`emotion_intensity`、`tone`、`pause_after_ms`、`instruction`。
- `fallback`：成功为 null；失败为 `kind/message/evidence_paths`，可用于向用户展示降级原因。
- `evidence_paths`：本次请求/结果路径，最后一项为持久化的 `emotion-plan.json`。

原文和合成文本都由源切片构造，模型不能返回或改写正文。数字、英文、单位、emoji、空白和 CRLF 不被规范化；字幕继续使用原文。规划范围连续、非空、无重叠且完整覆盖全文。情绪与 03 的十二种枚举一致，强度 0–1；tone 限于自然/沉稳/舒缓/轻柔/有力/急促/沉思，instruction 仅由调用方固定 base_style 与 tone 构造。

## 回退与持久化

每次调用使用独立 `logs/tts-emotion/<uuid>/`，保存 intent、成功解码的 outer、最终 emotion-plan.json，HTTP 原始证据沿用现有日志。重复调用不会覆盖旧计划。未完成、错误模型、截断、HTTP/JSON/非法 Unicode、格式或原文覆盖错误，都保存原因并整篇回退：`narrative / 0.3 / 沉稳 / pause_after_ms=0`，不接受局部成功，不丢字。空文案/纯空白直接拒绝；磁盘落盘错误向调用方抛出，不冒充已记录的正常回退。

这些范围是情绪规划，不能直接当作最终语音单元。真实模型可能按较细的提示块返回（本次 122 字样例返回 27 个范围，包含空白范围）；06 负责合并同风格、形成 80–180 字目标的有限语音单元并处理纯空白、停顿和对齐。05 不插静音、不构造时间戳、不执行发音规范化，也不声称每个范围都满足 03 的 250 字服务边界。

消费一个已由 06 整理好的语音单元时，将 `emotion`、`emotion_intensity`、`instruction` 放入已有冻结 `tts` 参数，再使用 04 的 `create_tts_client`。03 已将强度转为轻微/适度/明显等自然语言：强度不是 VoxCPM 原生数值参数。07 再负责将计划绑定修订、持久状态和恢复；切后端不能覆盖既有任务。

## 验证

真实实验目录：`E:/VideoAI/scratch/benchmarks/TTS-VOX-05/20261126-005551-440958`。

- Ollama 0.40.14 / qwen3:8b，完整 122 字混合文案单次规划耗时 57.672 秒，原文和合成映射精确覆盖。
- 规划产生 narrative、awe、sad、gentle；仅表示结构化情绪识别，不代表四种音色效果经过试听验收。
- 选中 `星云在黑暗中绽放，`：awe / 0.6。通过 04 工厂生成一个真实 GPU 样本 `directed.wav`，48kHz、PCM16、单声道、138240 采样点（2.88 秒），调用耗时 8.390 秒。
- 服务冻结请求确实包含该范围的 emotion/intensity/instruction，实际合成前缀包含“适度惊叹敬畏”。本次持有的 Vox 服务退出码 0；本次持有的 Ollama 使用 terminate 结束，Windows 返回码 1，进程已结束，未接管或停止外来服务。
- 新增测试初始 34 failed（缺失模块），实现后 34 passed。独立审查发现非法 Unicode 模型结果绕过回退，新增测试复现 `UnicodeEncodeError` 后修复，35 passed。最终相关回归 **341 passed / 3 skipped**（9.78 秒）；跳过项为 Windows 缺少创建符号链接权限。日志 `E:/VideoAI/scratch/logs/vox05-final.txt`。

未重复完整视频、02 质量盲听或真实 10–30 分钟语音实验。本任务没有主观试听结论；原有 02 情绪可辨度与性能限制仍然保留。长文一次请求/无截断/容量回退有单元测试覆盖，真实长文质量、音色稳定、分段停顿与时间轴属于后续任务。

复现相关测试（PowerShell）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vox05-tests'
$env:PYTHONPATH = "$PWD\src;$PWD\tests"
& $VideoAiPython -B -m pytest tests/unit/test_emotion_director.py tests/unit/test_ollama.py tests/unit/test_ollama_direct.py tests/unit/test_ollama_json_payload.py tests/unit/test_ollama_pattern_transport.py tests/unit/test_ollama_shared_grounding.py tests/unit/test_ollama_units_transport.py tests/unit/test_tts_backends.py tests/unit/test_tts.py tests/unit/test_voxcpm_service.py tests/unit/test_segments.py tests/unit/test_config.py tests/unit/test_manifest.py -q -o cache_dir=E:/VideoAI/scratch/tests/vox05-cache
# 真实实验仅在需要重新验收时运行，每次创建新 scratch 目录：
& $VideoAiPython -B -u scripts/experiments/voxcpm2_emotion_smoke.py
```
