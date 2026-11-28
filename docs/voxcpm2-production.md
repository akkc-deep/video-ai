# TTS-VOX-07：生产语音与恢复

## 2026-11-28 当前默认：已确认的完整重配音版

用户要求后续视频全部沿用旅行者2号完整重配音版。新默认保留相同参考资产、reference-prompt、seed=42/cfg=2/steps=20、一次0.95倍语速和全篇RMS -23dBFS，段间静音改为500ms，并冻结 `onset_guard` 处理。固定可丢弃上下文“下面继续讲述。”在变速后按真实长静音分界移除；正文单独对齐，避免参考残留被错配成首字。原文最大请求长度会预留引导语容量。安全分界缺失时明确停止，复用已保存的原始及变速语音恢复，不擅自截字或重新发起已完成请求。

正式处理函数在已确认的137段真实音频上重现相同截点与逐字节相同的正文；配置、生产流程、纯正文对齐和中断恢复有针对回归。持久样本及最新批准记录见[已确认旁白](approved-narration.md)。以下07数据为旧850ms配方的历史记录；旧冻结任务继续使用旧路径。

正式 `make-video` 的语音阶段已接入 `provided-reference-narration-v1`。运行根 `shared/config/production.json` 保存显式内联配方，当前服务地址为 `http://127.0.0.1:9881`。普通新视频无需添加音色参数；旧运行从自己的 options 快照继续，不读取新默认。

## 固定配方与存储

任务开始时把配方、voice.json 和参考 WAV 冻结到 `production/inputs/vox/`，检查一次参考身份。冻结模型/源码版本、参考转写、seed=42、cfg=2、steps=20。正文使用同一参考的 reference-prompt，不添加情绪前缀。每个段落最多 250 字，超长段落按有限边界拆分；原文与原有字幕单元完整保留。

`production/vox/speech_XXXX/intent.json` 保存稳定请求 ID 和原始请求；`raw.json`、`processed.json` 分别绑定原始生成与仅一次 atempo=.95 的结果。新默认的 `body.json` 绑定去引导后正文及实际截点，随后才对齐；全篇按已有静音补足段间500ms，并应用一次 RMS -23dBFS 恒定增益（保留 .95 峰值上限）。旧冻结850ms配方不增加引导处理。不升降调、不添加背景音。

本地 FunASR timestamp 模型在已变速音频上预测时间，使用实测相邻 token 边界切分连续 PCM。切片拼接逐字节等于完整旁白，生成原有 speech checkpoints 和 envelope，现有字幕、镜头、合成接口保持兼容。时间轴的额外句间/段间停顿为零；保留原配置的片头/片尾空白和最终帧填充。

## 恢复与服务

恢复先查同一 Vox 请求 ID，已完成结果直接取回，不重复提交。原始结果已保存而对齐/合并中断时，复用原始及变速缓存。中断发生于服务完成后、客户端记录前时，也从服务 SQLite/完成回执取回。已确认失败或硬崩溃且没有有效回执的推理保留失败诊断，不自行重置请求身份或无限重试。

只启动并停止当前阶段拥有的服务；外来占用端口明确拒绝。临时网络错误退出时，服务先完成已接受请求并保存结果，再退出，避免把可恢复请求取消。超过退出等待期限则停止本次拥有的进程，未提交结果保持明确失败。进程被强制终止后遗留的外部服务不接管。

依赖已安装的 Vox 专用环境和模型，以及 `shared/models/funasr/timestamp/`。时间戳预测使用现有 GPT 工具环境中的 FunASR **CPU 对齐库**，不调用旧 TTS 合成。当前本地对齐支持基本汉字、ASCII 英文和数字；希腊字母、带重音字母等不支持的字母会在生成前明确拒绝，不静默丢弃或估算时间。模型无法完整对齐时保留缓存并报错。

如需在另一份已部署配置启用同一默认配方：

```powershell
python scripts/configure_approved_narration.py --config E:/VideoAI/shared/config/production.json
```

该脚本读取 `shared/config/tts/default-narration.json`，核对批准声学身份和运行依赖，保存旧配置备份，再写入显式内联配方。`config/production.example.json` 保留为旧任务兼容样例；10 已补齐固定安装、批准默认、离线迁移和显式回退，见 [安装迁移说明](voxcpm2-installation.md)。

## 验证证据

真实运行：`E:/VideoAI/work/20261127-233334-87f1980149c6`。通过正式生产函数完成 units、speech、timeline：两次真实 GPU 段落请求，470,524 个旁白采样点 / 9.802583 秒，FunASR 实测边界及现有时间轴通过；重建客户端并再次恢复后请求总数仍为 2。音频路径及详细元数据见 [结果 JSON](research/TTS-VOX-07-result.json)。

```powershell
python scripts/experiments/voxcpm2_production_smoke.py
python scripts/experiments/voxcpm2_production_smoke.py --run E:/VideoAI/work/20261127-233334-87f1980149c6
```

新增测试覆盖冻结配方、全局参考变化、超长段落、实测切点、对齐中断恢复、PCM 完整性、停顿不重复、完成恢复、接受请求的优雅退出和不支持字符的生成前拒绝。独立审查的两项 P2 均通过 RED→GREEN 修复，复查通过。

最终相关回归为 172 passed / 3 skipped / 8 失败：3 项 Windows 无符号链接权限跳过；8 项旧字体夹具失败集中在 production_inputs 的三个 preflight 测试及 production_speech 的五个测试，完整名称记录于 `E:/VideoAI/scratch/tts-vox-07-final-regression.txt`。未修改 HEAD 的独立源码基线复现相同 8 项失败，记录为 `E:/VideoAI/scratch/benchmarks/tts-vox-07-baseline/result.txt`。不将相关测试结果冒称全套通过。

本任务未生成完整视觉视频、未增加主观试听结论、未证明 30 分钟稳定或性能达标。用户之前确认的音色结论保持，完整视频验证属于 TTS-VOX-08。
