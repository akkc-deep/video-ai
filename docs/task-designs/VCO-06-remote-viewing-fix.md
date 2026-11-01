# VCO-06 远程观看记录兼容修复

2026-10-29。用户通过远控看完整段，却收到逐帧覆盖未成立提示。当前没有用户导出的实际回调记录，不能断言具体漏帧数。已确认实现仅凭requestVideoFrameCallback逐帧回调判定，且ended后固定100ms结算；浏览器回调是尽力交付，不能据其缺失断言用户没有看完。

保留旧v1的49帧严格规则和原始callback数组，绝不补造缺帧。修改非冻结HTML的结束结算，接纳同一次播放实际到达的延迟回调，取消旧结束任务对新播放的影响；无论结果如何均可保存草稿并显示具体诊断。

新增独立remote v2研究观察：仅在真实ended事件、原生时长/速度、完整连续played时间范围、足够实际经过时间、页面可见、无跳转/暂停/缓冲等中断，且用户明确确认实际完整观看时可导出。逐帧callback覆盖仍保持其真实不完整状态，不能冒充旧v1。新validator及独立intake明确识别schema2，核验真实case/collection/媒体/生成完成时间，development-only，保留原字节；不生成资格profile或候选ready。

补充事件语义：`stalled` 仅表示网络取流无进展，已有缓冲仍可能保持连续播放。事件原文继续保存在 `playback.interruptions`，严格v1照旧拒绝；独立remote-v2仅将精确的 `stalled` 当作取流诊断，不能把它当作实际呈现暂停。`waiting`、`pause`、`seeking`、error、倍速、播放期间隐藏等仍拒绝。native ended后的可见性/速率等操作不追记为已结束观看的中断；等待晚回调不延长实际观看时间。异步开始、加载完成、播放异常和结束结算都需绑定同一素材和会话，避免旧任务污染新观看。

主设计要求实际完整动态观察而非浏览器每一帧回调；本修复将人类完整观看声明与逐帧遥测分开记录，保留二者限制，不降低源视频全49帧分析/时序、颜色、自然资格或候选改善要求。旧冻结自然采集Python/CLI与旧validator不改字节。

修改：scripts/experiments/vco06_observe.html。新增：src/video_ai/experiments/natural_remote_observation.py、scripts/experiments/vco06_remote_observe.py、tests/unit/test_vco06_remote_viewing.py。按RED/GREEN验证晚回调、旧结束任务、远控缺callback但有完整时间/真实作者确认、缺时间/隐藏/暂停/跳转/倍速/未确认/错媒体/holdout/漂移拒绝及草稿不升级。

部署：归档此前save-fixed页面及receipt；在同一个save-fixed URL发布新UI版本，保留DATA与localStorage命名空间，便于刷新后恢复已暂存填写。独立新receipt记录修订链，不刷新旧receipt的SHA。旧observe-12.html不变。模拟浏览器只验证软件，不构成任何实际观看；用户仍需亲自确认，不能由助手代选。

旧缓存没有原生ended/played范围的记录不能补造这些证据或自动升级为v2；保留原选择和原逐帧记录。新一轮播放只重置属于上一轮的本人观看确认，不重置颜色/结构/动作/光照答案。v2在独立 `remote-observations` 留存，旧冻结status/observe不消费此schema；未来资格流程必须显式处理独立方法及其限制，不得混写成原v1标签、刷新冻结库存或改旧分母。
