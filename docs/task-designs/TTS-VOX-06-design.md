# TTS-VOX-06 音色及长文案

## Goal and scope

完成总设计第 4/7/9 节的音色冻结、无损长文分段、停顿补足、全篇后处理及实际采样点对齐。消费 05 已保存的情绪计划和 04 配置/适配器；提供独立模块供 07 接入。生产恢复、缓存、现有时间轴接线和默认后端切换属于 07/10。

2026-11-27 最终音色已获用户确认：后续所有视频固定使用 `provided-reference-narration-v1`。运行根 `shared/config/tts/default-narration.json` 为权威配方，仓库副本为 `config/approved-narration.json`；[完整冻结规范与正式入口状态](../approved-narration.md)。以下早期候选及通用分段参数保留为实现历史；后续生产必须消费已确认配方，不能用通用默认值覆盖其参考续读、语速、停顿或响度设置。本次确认不代表 07/10 已完成。

## Approach

现有时间轴使用独立 TTS 的实际时长，没有强制对齐器。选择较细分段独立生成，再按实际 WAV 采样点合并；不引入额外 ASR 或按字数估算时间。按句子、段落和情绪变化断开，同风格短语与空白合并；长句以 180 字为软目标，250 字为硬上限。为了真实句级边界，短句允许低于 80 字，不跨句合并。大块生成后新增强制对齐会扩大依赖和校验成本；直接使用旧逐词/空格分段则增加大量请求。这是实施者依据既有契约作出的选择。

## Interface and behavior

`freeze_voice(config, *, base_style=None) -> FrozenVoice` 固定 model_revision、voice_id、reference_sha256、seed/cfg_value/inference_timesteps 和基础风格，参数不可变，提供可序列化身份。使用配置已验证的参考音频摘要，服务阶段启动时仍由既有逻辑校验并复制参考，不在每段重算。

2026-11-27 用户明确指定纪录片助眠男声：新增可选 `voice_profile` 参数，与 `VoxServiceProcess(..., voice_profile=...)` 选择同一独立声音设计资产。新资产提供 voice_id/reference_sha256/base_style，相对 profile 路径相对于运行根；默认旧绑定保持兼容。偏好保存于 `shared/config/tts/male-sleep-documentary.json`，07 必须显式消费该偏好；[配方、资产和短样本](../voxcpm2-sleep-voice.md)。主观状态 pending_user。

`plan_speech(emotion_plan, voice, *, target_chars=180, max_chars=250) -> dict` 一次检查原文范围连续覆盖、原文/合成文本映射和情绪请求参数，保留 Python Unicode 半开范围。数字、英文、单位、CRLF、emoji 原样保留。只按真实句末、段落、非空白情绪变化形成语义组；超过软目标时优先短语/空白边界，无可用边界才硬切。空白和标点附着相邻语音单元，绝不提交纯空白/纯标点请求；极长空白保留为 skip 范围。每个单元保存稳定 ID、start/end、original_text/synthesis_text、emotion/intensity/instruction、voice_id、seed、pause_after_ms 和情绪来源 ID。末尾不补停顿；句间默认 220ms（建议限制在 150–300），段间默认 450ms（建议限制在 350–650），普通短语只保留边界建议（最多 300ms）。内部被合并的情绪停顿建议不机械累加。

真实实验发现单独的三字引语“看啊，”产生近乎静音坏样本。因此，同一句内的情绪切点如会形成少于 8 个可发声字符的片段，抑制该切点，按合并范围内可发声字符数最多的风格生成（平票保留先出现的风格），保留全部情绪来源 ID。句末和段末仍是硬语义边界，不合并完整短句。这是显式的情绪平滑策略，不改原文，也不保证模型绝无坏样本。超长无标点文本按 180 字软目标硬切，避免 251 字形成 250+1 的尾段。阶段 06 单独过滤英文词内点号、常见称谓缩写及后接小写词的 U.S./e.g.，不修改旧分段契约；英文缩写边界是启发式，不声称完整 NLP 句法识别。

`LongFormSynthesizer(http, voice, *, request_scope).synthesize(plan, output_dir) -> dict` 用同一 VoxTtsClient 的阶段就绪检查串行生成，逐单元选择已冻结情绪参数，不改请求身份/重试语义。每个单元 WAV 和 request_id 写入独立输出目录，逐段失败向上抛出，不发布成功结果或旁白。恢复编排留给 07。

`assemble_narration(plan, audio_paths, target, *, target_rms_db=-20) -> dict` 每个 PCM WAV 一次读取，确认 48kHz/mono/PCM16 和完整采样点，保留全部音频，不剪头尾。仅检测边缘连续低于 32/32768 的静音，边界补量为 `max(0, desired - previous_trailing - next_leading)`。只在已有边缘静音内作最多 3ms 淡入淡出。流式临时 WAV 累计全片能量/峰值，随后一次全篇恒定增益（目标 RMS -20dB、峰值上限 .95；不是 LUFS，也不逐段压缩）；不降噪、不重复解码验证。

合并结果保存每单元实际 start_sample/end_sample、edge silence、added_pause_samples、pause_end_sample，映射回完整原文并标记 alignment=independent-tts-units。原文 skip 范围没有伪造音频时间。长句拆分后的短语是真实独立 TTS 边界，不提供字级或词级估算。全篇采样点等于各 WAV 采样点加实际补静音；恒定增益不改变时长。临时文件成功后原子发布，失败清理临时文件，已存在产物拒绝覆盖。07 消费该映射适配原有字幕/镜头时间轴。

## Verification and acceptance

RED→GREEN 覆盖：长文和混排原文往返、重复段落、纯空白/标点、超长无标点和空白、细粒度情绪合并与变化、句/段边界、不可变音色及种子、非法映射拒绝；合并的真实采样点、已有静音不叠加、不剪尾音、全篇单增益、坏 WAV/缺失片段不发布；真实适配器消费冻结单元且复用阶段健康检查。

真实验证使用已有 05 混排情绪计划，加 02 冻结长稿前 1,029 字的显式 narrative 范围，合计 1,153 字，固定音色生成多句 GPU 旁白，保留各单元 WAV、合并旁白与对齐 JSON。初次 42 单元全部生成，但合并拒绝近乎静音的“看啊，”。修复分段后 41 单元，仅合并变化范围重新生成，输入完全匹配的 40 个原请求通过 04 查询复用；独立实验修复工具不表示 07 生产恢复已完成。长文数千字的分段/映射另由测试覆盖；不将本次样本冒充 10–30 分钟质量或 30 分钟音色稳定试听。报告客观结果与主观试听未验证边界，不编造质量达标，不生成视频。
