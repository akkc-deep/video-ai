# TTS-VOX-05 情绪导演

## Goal and scope

实现总设计第 4、7、9 节的完整文案 Ollama 结构化情绪规划、原文覆盖与明确默认回退。独立可调用模块供 06/07 消费；不在本任务改生产编排、字幕、默认后端或历史配置，不生成视频。既有 03/04 未提交实现是直接依赖。

## Approach

采用独立 EmotionDirector，复用 HttpClient、ollama_body、parse_completed_response 和 RunLogger。直接扩展现有镜头 OllamaPlanner 会混入镜头请求身份和恢复契约；让模型返回重写文本则无法保证原文。选择让模型只返回原文半开范围和有限风格字段，由程序切片还原文本。此选择是实施者按既定总设计作出的实现决定。

## Interface and behavior

`EmotionDirector(http, *, base_style=..., cpu_only=False).plan(text) -> dict`。完整文本一次请求，不逐句请求或自动纠错重试。用既有 segment_text 生成带 Python Unicode code point 半开坐标的原文提示块；它们只是模型定位提示，不是最终语音单元。输出 spans 中每项是 start/end、emotion（复用 03 的 12 枚举）、emotion_intensity（0–1）、tone（自然/沉稳/舒缓/轻柔/有力/急促/沉思）、pause_after_ms（0–650）。提示要求默认 narrative/.3，情绪按上下文渐变，只增强关键段落，可合并同情绪。

只接受按源序排列、连续、无重叠、非空、边界属于提示块边界且完整覆盖 `[0,len(text))` 的范围；不做第二次资产或音频扫描。输出原文和 synthesis_text 均由源切片生成，不接受模型提供文本。保留空白、CRLF、数字、英文、单位和 emoji；不做发音规范化。每项补稳定 emotion_0001 等 ID、固定 base_style 与受限 tone 组成的 instruction。emotion/intensity 交由 03 已有自然语言强度映射消费，不伪装原生数值模型参数。05 范围允许超过 250 字；06 再分为有限语音单元，停顿仅是建议，不插音频或伪造时间戳。

结果包含 schema_version=1、status（planned/fallback）、source_text/source_sha256、model、base_style、spans、fallback（成功为 null，失败为 kind/message/evidence_paths）、evidence_paths。每次日志使用独立 UUID 子目录 `tts-emotion/<id>/`，保存 intent、outer、emotion-plan.json 和事件；复用同一 logger 不覆盖既有结果，最终路径可从 evidence_paths 取得，供 07 冻结到 revision。落盘失败向上抛出，不冒充已记录的回退。

Ollama 未完成、截断、模型不符、HTTP/JSON/结构/覆盖失败均记录原因，整篇回退成一个 narrative/.3/沉稳 范围，pause_after_ms=0；不保留局部错误结果，不丢字，不重试。空白/空文案属于调用错误，在请求前拒绝。context 使用完整提示的 UTF-8 字节保守上界，加 schema、2048 模板余量与 16384 输出预算，按 32768 起倍增到最多 131072；超出明确 capacity 回退，不截原文。默认 keep_alive=0，既有服务生命周期由调用方负责，不接管或停止外部服务。

## Verification and acceptance

先 RED 后 GREEN：多情绪成功、原文精确往返、重复段落/Unicode/换行、全体情绪枚举、强度与停顿边界、空白输入、缺漏/重叠/乱序/越界/错误类型/新增字段/改写拒绝、未完成/截断/错误模型/非法 JSON/断线回退、重复调用独立持久化、磁盘错误传播、整篇长文一次请求与容量回退。跑新增与 Ollama/TTS/分段相关回归。

真实验证只调用现有本地 Ollama 做一个含数字、单位、英文和情绪变化的完整短文规划，保留原始证据与覆盖结果，再从规划的一个短范围通过 04 工厂生成一个 GPU WAV，确认 03 实际合成指令消费了 emotion/intensity/instruction。只关闭本次拥有的服务，不替代 02 主观质量验收，不声称 06/07/08 完成。
