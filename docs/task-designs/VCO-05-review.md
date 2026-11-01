# VCO-05 独立审查

2026-10-27：按 brainstorming 的 builder check 与 requesting-code-review 各完成一次独立只读审查；审查者没有运行测试、读取凭证或执行GPU。实际运行结果由主执行者另行核验。

设计检查：既有B阶段方案可实施；补充逐帧色度分布、明暗截断与采样图，未知色彩解释不得强猜。

代码检查与处置：

| 问题 | 处置 | 复现/验证 |
|---|---|---|
| 冻结模型可能不是实际搜索路径加载的文件 | 复用生产模型路径守卫；按角色核对实际模型根，拒绝alternate搜索路径同名影子与extra_model_paths.yaml；禁用外部custom node hook，保留全部原graph内置节点 | `test_model_paths_must_match_actual_service_search_order` RED→GREEN |
| 大文件哈希期间自有服务退出后端口可能被接管 | 最后一次哈希后、创建intent前检查Popen仍存活并重查监听PID；回调失败时零POST且不生成intent | `test_post_guard_can_refuse_a_replaced_service_without_creating_intent` RED→GREEN |
| 审计缓存只核对生成原片 | 重读前核对审阅片、映射、原生帧清单及每个PNG身份 | `test_cached_audit_rejects_modified_review_or_native_png` 三种修改均拒绝，RED→GREEN |
| 旧probe只查相邻PTS，首帧可能非零 | 实验层额外逐帧验证Fraction(actualPTS×timebase)=i/16；stream时长精确等于count/16 | `test_nonzero_native_pts_origin_cannot_claim_i_over_16_mapping` 真实非零起点MP4 RED→GREEN |

额外实测发现：`test_scene_video_prompts.py` 原有继承绑定测试在模块首次导入时捕获了被临时patch的load_frozen_inputs别名，导致随后25项生成集成测试报SimpleNamespace不可序列化。测试先导入依赖模块、再patch，防止别名污染；未改生产语义。原合跑失败日志保留，修正后原顺序两用例单独回归2 passed。

环境适配：Windows WDDM的compute-apps列表包含桌面图形上下文、显存为N/A，不能把这些上下文当作模型任务或终止它们。先以Get-Process核对已知桌面进程身份，未知或Python/Ollama等工作负载拒绝；原进程保持运行。专门用例RED→GREEN。

重要问题均已修复并定向验证；没有延期的小问题。完整动态观察未被静态/软件检查升级。

2026-10-27 用户播放反馈后的修正：原检查只证明RGB High 4:4:4 Predictive无损文件技术有效，遗漏普通播放器兼容性。保留其RGB证据角色，增加单独High/yuv420p/faststart CRF16播放版及回归；不把有损副本标成RGB无损相等。新副本及原片/无损片/映射/后处理源码/工具身份单独绑定，旧case不改签。34项检查通过；系统播放器后台探测未启动，明确记录为不确定，不充当完整动态播放证据。本次为局部缺陷修复，由主执行者复核，没有新增独立审查声明。
