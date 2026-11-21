# LVA-07-06 本地化监听检查修复与范围决定

2026-11-20，用户对首份control回复“视频没问题”。已绑定本轮cold_1，及与其完整媒体SHA完全一致的warm_1；warm_1为同字节关联，不声称独立观看。两份均93帧/16fps，高30/低50前向、LoRA0，分别1261.844秒和1255.453秒。原始root为 `E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-01`。

后台warm_2在写intent/POST之前失败。隐藏子进程中，Windows `netstat` 输出OEM/GBK本地化标题，Python `-X utf8` 的文本解码线程抛UnicodeDecodeError，随后stdout为None造成AttributeError。没有warm_2或warm_3推理/未知请求。后台按失败停止规则合作退出原owned12804/epoch4cecf0fe-2236-4945-a2f5-f962b3a6c03d：exit0、forced=false、graceful=true、端口关闭。原完整pair已成为历史证据，不能用于新epoch。

修复仅涉及两个监听检查入口：`src/video_ai/experiments/whole_scene_runner.py::_listener_owned` 按原始bytes解析ASCII TCP地址/状态/PID，忽略本地化标题；`scripts/observe_wan_wrapper_comfy.py::owned_listener` 委托同一检查并保持其ValueError接口。仍要求唯一127.0.0.1监听、确切端口与PID；非零返回码、缺输出、错误PID/端口、wildcard、重复/截断行均拒绝。未改模型、数值、帧数、即梦或原生workflow，未重发旧请求。

验证：

- 新16用例先RED（复现stdoutNone/bytes路径），修复后全部通过。
- 新用例加原Wrapper定向集合共118通过，11.09秒；日志 `E:/VideoAI/scratch/benchmarks/LVA-07-06-implementation-20261120-01/listener-fix/focused-pytest.log`。
- 实际普通及CREATE_NO_WINDOW隐藏子进程均在UTF8mode1、Windows ACP/OEMCP936下正确核对临时本机监听；隐藏probe输出 `listener-fix/actual-hidden-probe.stdout`，未启动GPU。
- 扩展相邻集合78通过、3个既有whole_scene恢复fixture失败：`test_whole_reconfigure_defers_budget_when_common_must_be_rebuilt`、`test_whole_rejected_request_stops_following_scenes`、`test_whole_lost_response_and_missing_budget_never_submit_twice`。均在scene revision准备阶段报 `whole_scene_evidence requires an exact absolute configured runtime JSON file`，尚未进入监听检查；将修改前的原监听函数装入独立测试进程后三项仍同样失败（24.14秒）。基线日志 `listener-fix/baseline-recovery.log`。未越界修复该配置fixture。

现有有效样本已保留，不能删除/覆盖或把新进程拼作同一owned服务的热3。当前只有冷1热1，缺热2；fast/高运动/父子/1080P均未执行。不能登记完整矩阵通过或稳定速度收益。

待用户决定的具体方案：

1. **完整补齐原验收：** 新root建议 `E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-02`，使用修复后的源身份，完整测量32个新样本；原2个保留为额外历史样本，不掺入新epoch冷/热统计。任务总生成上限由32增至34。与无故障继续剩余任务相比，增加一次约38分钟准入及净2份约42分钟control采样，总计约80分钟。其余环境、模型、资源额度、质量门槛、单GPU串行与不恢复生产约束保持。批准前不建立新的approved授权、不启动新GPU。
2. **按真实中止分支收尾：** 只交付已完成2份及修复/中止证据，完整冷/热、fast、高运动、父子和1080P结论均保留未验证，不推广。该选择尚未由用户作出。

新GPU授权或结束范围未确定，任务保持IN_PROGRESS等待该决定。本文件不是新增授权；用户“视频没问题”是质量反馈，不扩张32份预算。

## 已获继续批准

用户对追加2份预算、总上限34及完整补齐方案明确回复“继续”。选择方案1，新矩阵root为 `E:/VideoAI/scratch/benchmarks/LVA-07-06-20261120-02`；原2份保留，不重发、不拼接旧epoch；新矩阵最多32份，合计最多34。原文/此前质量反馈与分配关系将绑定新授权。记录时刻 2026-11-20T13:06:12.077113+00:00。上方待决表述为批准前快照。
