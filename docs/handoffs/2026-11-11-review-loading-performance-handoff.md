# 旅行者2号审核加载耗时问题交接

记录日期：2026-11-11，北京时间（UTC+08:00）。工作目录：`E:\code\py\video-ai`。

用户要求下一任务修复素材加载和审核记录提交缓慢的问题，**暂时不要生成视频**。视频目标已暂停，实际续段进程也已停止。接手任务应先测量、优化这一阶段，不要运行会自动进入视频生成的入口。

## 本次实际耗时

| 项目 | 记录 |
| --- | --- |
| 任务 | 加载 08 版已有素材，提交第 1 段完整帧序列审核记录，然后继续流水线 |
| 启动时间 | 2026-11-11 20:48:05.348495 +08:00，来自实际 Python 进程创建时间 |
| 停止时间边界 | 在 2026-11-11 20:54:31.6084056 +08:00 的后续检查之前，已按用户要求停止 |
| 耗时结论 | **约 6 分钟仍未完成第 1 条审核记录提交**；这是被中止运行的观察耗时，不是成功完成耗时 |
| 正式接受记录数 | 0；第 1 段 `observation-accepted.json` 仍不存在 |
| 新增续段 | 0；停止时已有 `clip.json` 共 137 个 |

20:54:31 是停止后的检查时刻，不是精确停止时刻，不能用两端时间相减声称精确耗时。现有阶段日志只有无时间戳的 `[review] submitting scene_0001_clip_0001.json` 等消息，**无法准确拆分首次素材加载、场景上下文构建、审核验证、落盘各自用了多少秒**。本次没有得到成功提交的总耗时，也没有优化后的速度数据。

## 定位证据

停止前对实际 Python PID `33380` 做了一次 `py-spy dump`，主线程处于以下调用链：

```text
consume_scene_clip_observation
  _entry
    scene_context
      require_reference_image_acceptance
        build_reference_image_acceptance
          verify_reference_provenance
            verify_reference_provenance（递归来源修订）
              ProductionTimeline.from_dict
                validate_production_timeline
                  _strict_json
                    manifest.thaw
```

这证明采样时进程正在做本地参考图来源追溯、时间线重建及规范化校验，尚未进入审核记录写入。单次堆栈不能证明全部 6 分钟都消耗在这一函数，也不能替代各函数累计耗时统计。

相关代码位置：

- `src/video_ai/runtime/reference_image_records.py`：`verify_reference_provenance` 的继承分支逐层调用 `load_frozen_inputs`、`common`，并直接调用 `ProductionTimeline.from_dict(prefix['timeline'])`；`build_reference_image_acceptance` 按场景调用来源验证。
- `src/video_ai/runtime/_scene_revision_origins.py`：已有 `origin_timeline`，在本地 artifact batch 内复用类型化时间线；上述来源追溯分支未使用它。是否可安全复用，需要核实实际批次作用域和来源保护条件。
- `src/video_ai/planning/production_timeline.py`：`validate_production_timeline` 重建规范时间线，并对预期值和实际值做 `_strict_json` 比较。
- `src/video_ai/runtime/production_scene_clips.py`：每次公开调用 `consume_scene_clip_observation` 都通过 `_entry` 构建 `scene_context`。逐条调用可能重复整批准备成本，尚未测得批量提交总耗时。
- `.tools/continue_voyager2_cached.py`：任务局部的字节校验复用仅减少部分来源字节重复检查，不能避免上述对象重建和时间线校验。本问题尚未修复。

## 建议下一任务的修复范围

1. 先为以下边界添加单调时钟计时、调用次数和明确阶段日志：`load_frozen_inputs`、`load_prepared_inputs`、`scene_context`、参考图来源追溯、时间线解析、审核验证、接受记录落盘、最终进度汇总。
2. 在同一次受保护读取或批次作用域内复用已验证的类型化时间线、来源修订公共上下文和逐场景 provenance；保持必要的文件变化与目录清单检查，避免跨变化错误复用。
3. 设计批量审核记录提交，尽量一次构建上下文后处理多条真实观察记录，避免每条重建全量上下文。
4. 用相同 08 版、相同审核输入比较修改前后各阶段实测耗时，区分首次加载和同批次后续提交；报告失败、中止和成功分别用了多久。

不要通过取消全部校验、伪造审核记录或重生成原素材来获得表面提速。遵守 `AGENTS.md`：生成视频过程中不要过度校验。仅做与本次性能修改相关的必要测试和测量。

## 可复用现场与操作限制

- 运行目录：`E:\VideoAI\work\0002-旅行者2号-即梦版\process\revisions\08`。
- 137 个场景的首段视频已保存。原分镜计划共 265 段，仍有 128 个续段尚未生成，放大和整片合成未完成。
- 审核输入：`.tools/clip-review/admissions/scene_0001_clip_0001.json`；真实方式为 `agent_frame_sequence`，不是实时连续播放。
- 机器可读诊断：`.tools/clip-review/loading-performance-20261111.json`。
- 素材清单：`.tools/clip-review/source-inventory.json`。
- 第 3 段已确认机身与天线盘结构分离，相关观察和修复要求位于 `.tools/clip-review/sequence-observations-0002-0004.json`、`.tools/clip-review/scene_0003-repair-requirements.json`；不要顺带放行它。
- `.tools/accept_voyager_frame_review_and_continue.py` 在接受审核后会调用 `produce_scene_pipeline` 并可能开始生成视频。**本次暂停期间不要直接运行它**，需拆出只读准备或仅提交审核的诊断入口。
- 旧 session `40977` 已在停止后返回退出码 1，PID `33380` 已停止；不要继续轮询旧 session，也不要根据旧 PID 操作新进程。不要按名称批量终止 Python。
- 当前工作区包含此前任务的修改（包括审核方式支持和任务局部缓存脚本）；接手时先查看差异，保留不相关修改。

## 验收要求

修复后应能解释重复工作从哪里消除，并提供实际阶段耗时和调用次数；实际完成至少一次审核提交准备，若测试会写入正式审核记录，则需明确记录写入结果。确认素材变化会使相关缓存失效，未查看的片段不能因缓存而自动通过。全过程不得启动 Wan、ComfyUI、放大或全片合成，除非用户之后重新授权视频生成。

此前来源重复读取问题另见 [2026-11-09 交接](2026-11-09-repeated-read-handoff.md)。该旧文档描述的是更早现场，当前素材与进程状态以本次记录及接手时的实际状态为准。
