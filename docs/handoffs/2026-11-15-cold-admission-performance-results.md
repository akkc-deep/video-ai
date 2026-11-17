# 旅行者2号冷准备耗时优化

当前尚未宣称完整优化完成：最终真实冷准备探测正在运行，视频生成进程仍未恢复。本文件将补入完整测量和恢复结果。

## 实施

根因是来源准入把同一份字节、目录和祖先证明反复解释成新的文件系统读取；新的依赖捕获器还会绕过已有缓存。原生产进程在冷准备超过五小时后仍未产生新推理。

- 分离不可变依赖回放与物理检查，保留冲突、容量上限和失败捕获处理；移除字节和目录的重复观察。
- 同步只读作用域共享原生文件、共同父目录、目录清单、缺失路径以及完整不可变证明。只有全部文件仍有合格原生句柄的证明可以整份复用；普通未保护文件继续实际读取。
- 源图片/片段范围纳入语义缓存键，保留“实际内容”和“仅声明 sibling”的区别。增长中的修订 guard 带依赖版本。
- 缓存冻结输入比较时捕获并回放完整读取依赖，退出时重新执行原加载器；进度扫描共享一个只读事务和 artifact batch。
- 写入、checkpoint、物理失败和关闭使复用失效。失效只禁用复用，保留全部退出复验义务；借用外层读取作用域的事务同样接收失效。
- 保留严格任意路径/惰性扫描检查、真实 Windows reparse 边界拒绝、原始观察与回执、失败不可覆盖、父段接受和未知任务 GET-only 恢复。

## 验证

最新聚焦验证：349 passed，1项独立性能测量用例按设计跳过。包含依赖捕获、原生文件保护、来源范围、修订与 checkpoint、场景记录/任务事务，以及真实回执入账集成；未运行无关全套或额外生产媒体审查循环。

日志：`E:/VideoAI/scratch/logs/cold-final-prior-suite-a752b543c0b44ee7ab096bf328ce4e4b.log`。

一次独立完整审查发现两项 Important：清空事务 guard 注册表会漏掉退出复验，借用外层物理作用域的事务会漏掉失效通知。三项复现先失败、修复后全部通过，并通过上述完整聚焦检查。无 Critical 或待处理 Minor。

独立审查之后，真实尾段采样又定位到已有合格记录仍重建祖先路径、增长 guard 重查缺失路径、成功语义读取后立即再遍历完整依赖，以及 `_prior` 手写回放绕过新纯回放函数四处成本。作者分别完成 RED/GREEN 并运行349项检查；这些尾段补丁未另行独立复审。实际命中仍绑定完整基线、原生保护对象和活动句柄，失效及新鲜边界检查不变。

扩展的 `test_reference_image_records.py` 有6项既有夹具失败，全部在调用参考图代码前拒绝位于独立测试根目录之外的共享ffmpeg.exe；准确保存的基线同样复现6 failed/1 passed，因此未修改无关路径政策。失败用例是 `test_prompt_contains_only_referenced_stable_bible_rows`、`test_reference_bindings_deduplicate_one_original_preserving_all_uses`、`test_wan_builder_rejects_legacy_text_only_related_candidates`、`test_reference_resolution_rejects_tampered_commit[source/schema/extra]`。基线日志为 `cold-prior-baseline-fixture-6537b6852d11468cb9cc22002b5e573d.log`。

## 测量边界

工具：`scripts/benchmark_cold_admission.py`，独立进程依次覆盖冻结输入、原生保护设置、准备输入、实际入口/进度重建、最终保护清理。只读审计禁止网络、推理、新渲染及生产数据写入；仅允许公共 RunLock 生命周期、外部报告及解码到 stdout/空设备。

基线是优化前准确工作树 `.tools/cold-admission-optimization-baseline-20261115-011834`，含644份文件和SHA清单，不能用HEAD代替。当前用户已有修改均保留，未整体提交。

探索报告全部明确记录完成状态：baseline31.374秒仍在冻结输入；v1/v2在120秒截止时准备输入未完成；v3在216.225秒被探测工具错误拒绝空设备写入；v4/v5在定位后被取消，报告为complete=false。这些前缀不能用于全程倍率。

冻结输入阶段共同父目录的原生检查从v2的337160次降至v3的7182次。它是调用量改善证据，不是整个视频的耗时预测。

v6在1200秒截止时推进到第一个来源片段的scene_context，1034个capture_origin调用已开始，仍未完成。其尾段有6,875,770次verify_record，暴露了上述完整依赖重复遍历，不能把它当成成功优化。

v7尾段采样找到了 `_prior` 仍用observe_file/inventory/absence重新解释既有证明的问题。已取消该旧版只读探测并明确标记complete=false；完整源码保存，未停止生产进程。

最终报告待填：`E:/VideoAI/scratch/voyager2-cold-admission-optimized-v8-20261115.json`。计时含仪器开销，应用缓存冷启动，不清空操作系统磁盘缓存。

## 工作流保护

原生产进程通过停止控制在读取边界退出130。开发未生成或删除媒体，未改写观察、原始任务 intent 或失败记录。探索探测被取消时只停止了核对过身份的只读探测进程；公共锁历史保留，由RunLock自行处理已终止owner。

完整探测成功后归档原停止控制，再恢复revision10；保留第36镜旧任务未知状态并只用GET核对，已有观察直接按原字节接收入账。五个失败镜头的后续修订仍须保留原视频目标和正式来源协议。
