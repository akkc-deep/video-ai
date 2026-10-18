# JIM-01 验证记录

日期：2026-10-18。范围：`docs/task-designs/JIM-01-design.md` 和任务板 JIM-01 的五项验收。

## 自动验证

项目环境：`. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment 'jim-01-review-green'`。

```powershell
& $VideoAiPython -B -m pytest tests/unit/test_jimeng.py tests/unit/test_jimeng_config.py tests/unit/test_jimeng_inputs.py tests/integration/test_jimeng_candidates.py -q --tb=short
```

结果：**79 passed in 8.59s**，退出码 0。日志入口 `D:/VideoSi/cache/video-ai/logs/jim-01-review-green-73f2b86cdc3a4472a77c74424eaa9246.log`。

| 任务板验收 | 实际证据 |
| --- | --- |
| 配置/CLI 换模型，模型参数隔离，冻结恢复拒绝改模 | `test_model_override_uses_own_preset_and_unknown_requires_explicit_config`、`test_unknown_model_explicit_parameters_are_preserved`、`test_cli_image_model_is_forwarded`、`test_freeze_new_strategy_skips_missing_sdxl_and_locks_model` |
| 官方业务错误、空 data、各状态、多图 | `test_signature_fixed_utf8_vector`、`test_business_error_and_empty_data_refused_before_reading_task`、`test_each_official_state_is_preserved`、`test_invalid_results_are_not_completed`、`test_original_multimage_outputs_are_durable_and_replay_has_no_http` |
| 受理后中断查询原任务、未知提交不重提、部分下载恢复 | `test_accepted_then_interrupted_queries_original_task`、`test_lost_submission_response_never_submits_again`、`test_query_and_partial_download_resume_without_paid_resubmit`、`test_interrupted_after_original_download_reuses_original`、`test_poll_deadline_leaves_original_task_resumable` |
| 原图/哈希/尺寸持久化，凭证与签名 URL 脱敏 | `test_real_media_decoder_validates_original_bytes` 实际运行 FFprobe/FFmpeg 完整解码合法 PNG 并拒绝坏图；`test_wrong_model_dimensions_refused_without_cropping`、`test_stale_or_tampered_identity_is_refused`、`test_response_redaction_removes_credentials_and_nested_signed_urls`、`test_transport_error_never_exposes_signed_url_or_credentials` |
| 旧配置缺省保持，新策略不要求 SDXL | `test_defaults_preserve_legacy_and_explicit_strategy_loads`、`test_new_preflight_does_not_require_sdxl`、`test_new_config_can_omit_sdxl_entirely`，以及下述历史回归 |

## 历史回归

基线配置/冻结/本机 HTTP：**84 passed in 3.46s**。

配置/冻结/制作 CLI 兼容专项：**74 passed in 145.58s**。过程中发现新增 ProjectConfig 字段改变旧快照形状，已在 `manifest.thaw` 保留旧字段集合后重新验证通过。

全套命令：`& $VideoAiPython -B -m pytest -q --tb=short`，完整输出 `D:/VideoSi/cache/video-ai/logs/jim-01-full-verified.txt`。最终结果：**2628 passed in 3758.32s (1:02:38)**，退出码 0，无失败或跳过。首次扩展回归曾为应用独立审查修复而主动中断；上述数字是修复后的完整重跑结果。

## 独立审查

独立 reviewer 只读审查明确改动文件，发现两项 Important，无 Critical。两项均先用失败测试复现，再修正：

1. 下载原图可复用前先持久化 SHA256/bytes 收据，防止图片在候选元数据写入前被替换并误接受；完成结果同样核验下载收据。
2. 外层有限等待覆盖阻塞 OS DNS；HTTPS 传输工作线程延迟返回时会检查截止期限，不自动重放 POST。

独立复核 **4 passed**，确认两项均关闭。DNS 阻塞替身配置 timeout=0.02 秒，原实现实际 0.250 秒，修正后复核为 0.047 秒（含客户端初始化）。根代理新增对应回归包含于上述 79 项。

## 实际边界

没有调用真实火山引擎账号、收费生成、TOS 上传或 SMTP 发送。没有生成真实样片，也没有作出人工视觉一致性判断。JIM-01 验收明确允许无真实账号的自动验证；这些后续真实验收仍属于任务板 JIM-08。

新策略提供候选 Python API；段落规划、邮件选图、新视频协调器尚未接入，当前 `make-video` 不会把新策略偷偷落回旧 SDXL 流程。旧策略保持其原有制作与恢复路径。
