# VCO-04 本地诊断操作

实现契约：[VCO-04-design.md](VCO-04-design.md)。实际结果与限制：[VCO-04-verification.md](VCO-04-verification.md)。本页给出操作顺序，不代表任何真实生产视频已经观察通过。

## 启用与查看

只在创建新 `paragraph_jimeng_v1` run 前的配置中显式加入：

```json
"scene_continuity": {"schema_version": 1, "policy": "advisory_v1"}
```

原冻结 run 的启用状态来自它自己的配置副本和 FileIdentity。不能通过补目录、修改当前配置或手工改旧 options 开启策略。

所有 Python 使用现有 bootstrap；将示例中的绝对 run 路径替换为实际路径：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'scene-continuity-status'
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/scene_continuity_audit.py',
 'status','--run-dir','D:/VideoSi/projects/video-ai/runs/ACTUAL_RUN_ID')
exit $VideoAiExitCode
```

`status` 只读，不提取新的分析帧、重新测分、补文件或生成视频。原有技术媒体核验仍可能调用ffprobe/CPU解码并复核尾帧，因此完整历史链的查询可能较慢。输出策略、当前 epoch、逐 clip 的 assessment/review/state/reasons。ready 退出0，等待退出3，损坏退出2。

## 提交本地分析

先保留真实技术完成片段，再准备完整 same-scene 保留帧前缀的 VCO-02 分析记录、明确作者的起点/独立首帧参考 ROI、可选合理变化 context 和 ordinary manifest。实际生成→保留→全局输出映射与原生16fps时间须一致。没有这些输入时保持等待；不猜主体、不补色彩声明、不截短前缀。分析器的单JSON16MiB、同调用元数据64MiB、4096帧/65536比较上限仍有效。

写入明确的 Analysis Request 文件，精确字段：

```text
schema_version = 1
run_id = 当前run名称
assessment_id = 新的规范UUID
epoch = status返回的当前commit Artifact
clip_id = 已提交plan中的准确clip ID
manifest = 已准备ordinary manifest的Artifact
```

Artifact 是准确的 `{path,bytes,sha256}`；分析 manifest 内的来源继续使用原五字段 FileIdentity。请求路径、manifest 和来源均是 `D:/VideoSi` 下明确绝对本地文件。

通过同一 bootstrap 调用：

```powershell
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/scene_continuity_audit.py',
 'analyze','--run-dir',$ActualRunDirectory,'--request',$ActualAnalysisRequest)
```

分析只写新的独立 CPU audit 和当前run的旁路事务，不调用生成服务。有效报告返回 `awaiting_review`/退出3；结果中给出准确 assessment 与 review-template 路径。无profile时保留机器unverified测量。

## 完整播放与回应

读取 job 下的 `review.md`、原机器报告和原schema2视频观察模板。实际完整播放者产出原观察和当前 `review-template.json` 的完成版本：作者/时间、原观察Artifact、所有concerns的一一回应必须准确。三段及以上还需要同一作者按顺序完整播放整个prefix的PrefixObservation。

只填 `human_video` 或确实具备完整播放能力的 `agent_video`。静帧、数字、模板或没有实际播放能力的环境保持unverified等待。无需正式双人校准表。无concern的报告也要提交有效Review和完整视频观察。

提交证据：

```powershell
Invoke-VideoAiNative $VideoAiPython @('-B','-m','video_ai','make-video',
 '--run-dir',$ActualRunDirectory,'--continuity-review',$ActualCompletedReview)
```

这一步仅消费原始材料，保留原视频观察及SHA命名的Review/PrefixObservation原始字节，不自动推进后代。未确认提交可以随后补齐；已确认缺陷和更晚的有效失败原文会阻断同源候选，即使先前有ready receipt。机器unverified/no_candidate不会被改成机器passed。

## 重评与恢复

显式 Reassess Request 精确为 `{schema_version,run_id,epoch_id,previous_commit,reason,requested_at}`。新UUID和当前准确链头是必需的；算法/包身份由当前安装捕获，不接收外部阈值。

```powershell
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/scene_continuity_audit.py',
 'reassess','--run-dir',$ActualRunDirectory,'--request',$ActualReassessRequest)
```

新代次覆盖整个plan，返回awaiting_analysis/退出3。原模型请求、视频、超分、成片、PCM、字幕和历史观察保留；当前诊断与回应重新建立。精确同媒体/父片上下文的旧播放证据可以被新的回应显式引用，旧ready不能自动继承。

同一分析请求可显式恢复；完整报告不重测，部分audit保留，每次至多新增一个本地attempt，每个assessment最多三个本地attempt。failed或超出次数时需要新epoch。诊断恢复不会重POST模型。原模型未知结果继续沿原request/prompt_id恢复。

真实生产启用、播放观察、外观准确率、研究profile转生产和后续任务都须各自有实际证据；本任务的软件测试不替代这些结论。
