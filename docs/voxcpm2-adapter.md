# TTS-VOX-04 双后端适配

04 已实现双后端配置、统一 WAV 调用契约及旧任务兼容。默认继续使用 GPT-SoVITS；07 才将新的异步身份/恢复逻辑接入生产编排，10 才切换默认。现有 `make-video` 和旧服务规格遇到 Vox 配置明确拒绝，不会选 Vox 却实际启动 GPT。

## 配置

项目 JSON 缺省 `tts` 或显式 `"tts": {"engine": "gpt-sovits"}` 使用旧后端。旧 `VoiceConfig`、GPT payload、`/tts`、resolved 快照字段均不变。已冻结的旧任务不读取当前配置默认值；现有恢复/修订约束继续适用。

显式 Vox 项目配置示例（合并到完整项目 JSON）：

```json
{
  "services": {
    "ollama": "http://127.0.0.1:11435",
    "comfyui": "http://127.0.0.1:8188",
    "tts": "http://127.0.0.1:9881"
  },
  "tts": {
    "engine": "voxcpm2",
    "model_revision": "7936080b41163874f38610f46f438e2c0757f9fd",
    "voice_id": "existing-reference",
    "emotion": "narrative",
    "emotion_intensity": 0.3,
    "instruction": "",
    "seed": 42,
    "cfg_value": 2.0,
    "inference_timesteps": 10
  }
}
```

Vox 必填 engine/model_revision，其他参数可省略；加载时把有效缺省值物化到 `config.raw.tts`，随后随 raw 冻结，避免未来默认值改变影响未提交语音。解析不修改传入字典或源文件。非法/未知字段在加载时拒绝。参考身份来自既有 `voice.reference_sha256`，服务使用 03 已配置音色；不支持在请求中传任意参考或输出路径。03 服务仍从 runtime 的 production.json 读取参考音频，因此调用配置的参考身份必须与其一致。

## 调用契约

```python
from video_ai.adapters.common import HttpClient
from video_ai.adapters.tts import create_tts_client

client = create_tts_client(
    frozen_config,
    HttpClient(frozen_config.services['tts'], frozen_config.timeouts['tts_request'], logger),
    request_scope='持久化的工作修订或尝试身份',
)
payload = client.payload('原文保持不变。')
response = client.synthesize('原文保持不变。', unit_id='speech_0001')
# 与旧 TtsClient 相同的 HttpResponse：body 为 WAV，evidence_path 指向原始响应证据。
```

Vox 的 `request_scope` 必须非空，恢复使用原值。`client.request_id(unit_id)` 将 scope 和单元 ID 映射为稳定 ID；payload 不含 ID，提交时添加。GPT 工厂分支直接返回既有 `TtsClient`，不新增请求。工厂核对 HTTP origin 与冻结 services.tts 相同，构造不启动进程、不加载模型。

调用方用 03 的 `VoxServiceProcess(runtime_root, state_dir, port=...)` 拥有整个 TTS 阶段的服务，在 finally 中 stop，只停止其拥有的 Popen。一个服务/模型处理所有有限语音单元；适配器不逐句启停。state-dir 沿用 work 修订音频目录或实验 scratch。

Vox 首次调用核对一次模型/参考身份，查询稳定 ID，确认 404 才提交；queued/running 在总调用期限内查询。POST 响应丢失只查询原 ID，绝不换 ID 或自动补单。每个任务记录核对原文、有效参数、合成文本和模型/参考身份；不接受另一个任务的结果。完成后从受控 audio 路由下载并检查 WAV 容器头，下游继续负责既有采样检查，不重复解码或增加 ASR。

错误沿用 `AdapterError`：确定失败/取消/输入冲突为 explicit，未知/中断后的提交状态为 ambiguous，非法结果为 invalid_result，提交前不可用为 unavailable。cancel_requested 表示服务仍在取消中，不声称推理已结束。超时不自动取消、不重试，原 ID 可查询。一个单元最多 250 字，超长直接拒绝；长文案语义分段属于 06。切换已生成旁白继续要求修订，不能覆盖或混用；生产恢复的完整接线和证明属于 07。

## 验证证据

[设计](task-designs/TTS-VOX-04-design.md)、[计划](superpowers/plans/2026-11-25-tts-vox-04.md)、[原始实测和验证汇总](research/TTS-VOX-04-result.json)。

真实 GPU 实验：`E:/VideoAI/scratch/benchmarks/TTS-VOX-04/20261125-200228-960822/`，含 `adapter.wav`、有效配置、HTTP 证据、SQLite/完成回执和服务日志。仅生成一个短样本，3.52 秒、168,960 样本、48 kHz/单声道/PCM16；服务冷就绪 23.141 秒，统一适配调用 7.609 秒，推理 7.426 秒。全新客户端使用同 scope 再调用，WAV 字节及原任务完整记录相同，无重新生成；拥有进程退出码 0。这是功能验收，不是新的质量试听或性能达标声明。

测试覆盖真实 HTTP/SQLite 协议、丢失响应、查询不可用不提交、身份/参数冲突、失败和取消、总超时、不合法 WAV、模型/参考不匹配、历史 manifest 往返和缺省参数冻结。独立审查发现 Vox 缺省参数未物化会在未来默认值改变时漂移，已通过新增回归 RED→GREEN 修复。

扩大相关回归曾得到 225 passed、3 skipped、8 failed；将本次五个已修改模块通过只读导入钩子还原为 HEAD 源码后，两个相关旧测试文件原样复现同一组 8 failed / 19 passed。根因涉及假字体 `invalid font tables` 和旧预检未产生预期 tts_yaml 检查；没有为本任务修改字体/预检业务。日志：`E:/VideoAI/scratch/logs/vox04-protocol.txt` 和 `vox04-baseline.txt`。三个 symlink 用例因 Windows 权限跳过。最终适配/配置/旧服务/manifest/旧 pipeline/生产 HTTP 适配器相关绿色回归数量见 JSON；不声称全套测试通过。

复现（先 bootstrap，再执行）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vox04-tests'
$env:PYTHONPATH = "$PWD\src;$PWD\tests"
& $VideoAiPython -B -m pytest tests/unit/test_tts_backends.py tests/unit/test_tts.py tests/unit/test_config.py tests/unit/test_voxcpm_service.py tests/unit/test_services.py tests/unit/test_manifest.py tests/unit/test_pipeline.py tests/unit/test_production_adapters.py -q -o cache_dir=E:/VideoAI/scratch/tests/vox04-cache
# 需要真实 GPU 的单短样本实验，按需执行：
& $VideoAiPython -B -u scripts/experiments/voxcpm2_adapter_smoke.py
```
