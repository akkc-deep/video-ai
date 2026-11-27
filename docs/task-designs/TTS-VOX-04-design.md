# TTS-VOX-04 现有 TTS 适配

## Goal and scope

按总设计第 6、7、9 节实现双后端配置和统一有限语音调用契约，保持历史 GPT-SoVITS 配置、payload、快照不变。生产编排、故障恢复及时间轴接线属于 07；默认切换属于 10。本任务不做情绪导演、分段、重试或视频生成。

## Approach

采用独立 VoxTtsClient + create_tts_client 工厂，保留现有 TtsClient 的同步 GPT 契约。相比修改旧类所有调用点，独立适配器不改变旧恢复代码对 `/tts` 和 HTTP 证据的假设；相比兼容 HTTP 代理，不引入第三个服务。此选择由实施者依据已有任务边界确定。

项目 JSON 可选 `tts`：缺省或 `{engine: gpt-sovits}` 解析旧后端；Vox 配置为 `engine: voxcpm2`、必填 `model_revision`，以及 03 的 voice_id/emotion/emotion_intensity/instruction/seed/cfg_value/inference_timesteps。服务地址仍使用 services.tts，参考身份使用既有 voice.reference_sha256。解析属性不新增 dataclass 字段，历史快照序列化不改变；Vox 加载时在 raw.tts 物化所有有效缺省参数，恢复消费冻结 raw，不读取实时默认值。

`create_tts_client(config, http, request_scope=...)` 返回支持 `payload(text)` 和 `synthesize(text, unit_id=...) -> HttpResponse` 的客户端。Vox 必须有非空 request_scope（工作修订/尝试的持久身份）；SHA256(scope, unit_id) 产生稳定请求 ID。重试新尝试由调用者提供新 scope，客户端不补单。文本原样保留，超过 250 字拒绝，等待状态使用整个调用的有限超时。

Vox 首次调用核对一次 health/voices 的模型和参考身份，查询稳定 ID，只有确认 404 才 POST。POST 响应不确定时查询同 ID，无二次 POST。查询、返回记录均核对请求 ID、engine、冻结字段及模型/参考绑定；completed 下载受控 audio 路由，以现有 HttpResponse/WAV 契约返回。failed/cancelled/cancel_requested 明确失败；deadline 或查询失败保留歧义，不自动取消或重试。只验证 WAV 容器头，采样等检查沿用 03 和下游，不重复解码。

07 接线前，现有生产入口和 GPT 服务规格构造明确拒绝 Vox 配置，防止配置选 Vox 却实际启动 GPT。Vox 使用 03 的 VoxServiceProcess，生命周期仍由调用方拥有，不接管外部进程。

## Verification and acceptance

先观察新增测试失败再实现。覆盖缺省/显式双后端、非法参数、旧 manifest 精确往返、冻结 raw 重载；GPT payload 原样；Vox 查询/提交/轮询/下载、同 ID 复用、不同输入拒绝、丢失响应不重发、失败取消、超时、绑定不匹配。用真实 03 HTTP/SQLite 服务配轻量模型替身验证协议，再用拥有者进程做一个真实 GPU 短样本，通过统一工厂返回 WAV，再调用同 scope 验证完成记录复用。保留原始 JSON/音频，运行必要相关回归；已有无关全套失败不宣称修复。不重跑 02 或完整视频。
