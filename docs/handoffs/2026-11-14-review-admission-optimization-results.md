# 审查入账优化交付（视频仍暂停）

本次只修改读取、审查入账和暂停控制。没有启动模型服务、视频推理、真实视频审查或生产修订，没有处理第36镜未决任务及五处画面返工。原素材、观察、回执、停止文件和 RunLock 均保留，已有未提交修改未回退或整体覆盖。

## 实施内容

- `production_scene_clips.py` / `_scene_review_batch.py`：受保护批次只做一次全局 `collect_progress`，之后在原始观察写入后和回执写入后分别重建受影响镜头。`_finish` 使用该快照，保留全片状态计算、失败不可覆盖、父段接受及批量 blocked/failed 早停契约。任务脚本的收件箱循环显式使用同一批次。
- `_scene_revision_readers.py`：直接复用已准入的 `source_frozen`，仍验证冻结身份和源 guard；每次检查 row 参数、覆盖和父段身份，保留媒体重映射及 native 分支。
- `scene_revision_records.py` / `_scene_revision_origins.py` / `reference_image_records.py`：在已有 artifact batch 中缓存源 clip、参考图来源和源计划的语义结果。键包含对象及完整 typed frozen 身份和实际场景/计划输入；返回深复制。保留原始字节/文件身份/清单/缺失路径证明，命中时复核并向外层捕获器回放全部依赖，退出时复验，不跨线程或已关闭作用域复用。
- 补齐因复用而必须显式捕获的依赖：继承片段和图片的 owned 目录竞争、native owned chain 缺失、参考请求目录及非 JSON 文件、可选结果缺失、原始观察清单和回执缺失。模板缺失也纳入证明，只允许接收器实际写出的确定模板精确更新证明。
- `scene_review_control.py` / `_continuity_byte_guard.py` / `scene_comfy_transactions.py`：在昂贵读取、祖先/字节证明扫描、观察原子写边界、服务准备前后、能力校验后和新 POST 前检查暂停。扫描内部最多每100ms轮询一次，原子边界强制检查；不承诺中断单个系统读取或已在途操作。
- `.tools/resume_voyager2_after_reboot.py`：初始收件箱、冷准备和启动服务前均检查绑定 owner 的停止信号；控制文件用普通短时读取，避免进入不可变输入保护。区分准备源依赖与正式接收，按阶段变化/实际新回执通知，重复回执不重复计数。仅编辑和通过暂停入口测试，未执行真实继续流程。

## 公平性能对比

最终数据为 [performance.json](2026-11-14-review-admission-performance.json)：优化前后均使用相同 `whole_input_protection`，各3个独立 Python 进程，报告中位数、范围、调用量和源码 SHA256。早期探索报告不作为最终对比依据。

fixture 有6个待接收片段、2个已接受的继承片段、3层来源和共享祖先 DAG。使用真实观察校验、存储、进度组装、来源递归和回执写入；底层媒体及计划语义为替身。冷准备指准入上下文冷启动，包含保护/批次入口，排除 fixture 构建和完整冻结输入装载，不代表操作系统冷缓存。退出复验及句柄清理另计，未隐藏在计时之外。

| 阶段 | 优化前 | 优化后 | 变化 |
| --- | ---: | ---: | ---: |
| 冷准备 | 111.23 ms | 152.24 ms | 增加36.9% |
| 首份接收 | 207.12 ms | 121.52 ms | 减少41.3% |
| 暖批次接收3份 | 682.38 ms | 358.75 ms | 减少47.4% |
| 最终边界复验/清理 | 1.43 ms | 35.73 ms | 新证明带来额外成本 |

上述四阶段中位数之和从约1.002秒降至0.668秒，减少33.3%；这不是生产视频耗时预测。

| 关键调用 | 冷准备 前→后 | 首份接收 前→后 | 暖3份 前→后 |
| --- | ---: | ---: | ---: |
| 全局 `collect_progress` | 1→1 | 3→0 | 9→0 |
| `validate_clip` | 8→8 | 24→2 | 72→6 |
| `load_frozen_inputs` | 6→0 | 18→0 | 54→0 |
| `source_clip_record` / 实际重建 | 6→6 | 18→0 | 54→0 |
| `verify_reference_provenance` | 12→8 | 36→0 | 108→0 |
| 源计划重建 | 6→2 | 18→0 | 54→0 |
| 原始参考来源重建 | 6→1 | 18→0 | 54→0 |
| 修订 artifact 检查 | 138→93 | 438→84 | 1314→252 |

最终边界另有27次修订 artifact 检查。两侧冷准备均为12次应用层 SHA 读取、606字节，暖阶段均无新增 SHA 读取：性能收益来自减少语义重建和重复遍历，不应宣称节省了这些阶段的物理磁盘读取。

复现：

```powershell
$env:PYTHONPATH='src;tests'
& 'E:/VideoAI/shared/envs/video-ai/Scripts/python.exe' scripts/benchmark_review_admission.py --baseline-dir .tools/review-admission-optimization-baseline --output docs/handoffs/2026-11-14-review-admission-performance.json --repeats 3
```

基线是本次修改前保存的工作树文件，包含用户此前修改，不是 `HEAD`。脚本只在独立子进程内加载这些源文件，不覆盖工作树或生产目录。

## 聚焦验证

最终共 **139项通过**（137项单测、2项集成）；另有1项性能用例在普通测试中按设计跳过、11项无关节点未选择。性能用例另在6个隔离进程中完成。没有运行全套测试。

主要单测命令（135 passed, 1 skipped, 11 deselected）：

```powershell
& 'E:/VideoAI/shared/envs/video-ai/Scripts/python.exe' -m pytest tests/unit/test_review_admission_optimization.py tests/unit/test_review_loading_performance.py tests/unit/test_revision_guard_shared_ancestors.py tests/unit/test_scene_clip_records.py tests/unit/test_scene_comfy_transactions.py tests/unit/test_scene_revision_records.py -k 'not identity_copy and not copy_refuses and not target_reference and not image_decode and not native_decode and not hash_consistent' -q -p no:cacheprovider
```

另2项 native 定向检查：`test_native_source_snapshot_reads_its_schema2_execution`、`test_native_decode_cache_shared_only_inside_invocation_and_rechecks_bytes`，均通过。

集成命令（2 passed，49.77秒）：

```powershell
& 'E:/VideoAI/shared/envs/video-ai/Scripts/python.exe' -m pytest tests/integration/test_review_admission_batch.py tests/integration/test_scene_revision_flow.py::test_second_revision_preserves_explicit_choice_and_traces_original_candidate -q -p no:cacheprovider
```

接收集成使用隔离测试目录内新建的少量 testsrc 媒体和内存 HTTP 响应，无模型服务/真实网络；核对原始字节、clip/request 摘要、父段接受后暴露待处理子段的早停，不重渲染或重审真实视频。修订集成仅在隔离 fixture 中建立多层修订并检查祖先变更。

回归包含：源同大小/恢复mtime字节变化、同字节替换、缺失/新增文件、共享祖先、外层依赖回放、返回对象污染、row参数/父段不符、竞争 owned 证据、非 JSON 参考请求证据、错误模板、跨线程/已关闭作用域、暂停留存原始观察但不伪造回执，以及服务/能力准备后暂停时零 POST。关键优化断言及审查发现的问题均先观察失败，再修复通过。独立只读审查发现的缺口已补齐；未发现需保留的重要审查问题。

`git diff --check` 对本次触及的既有文件通过。源码精确增量见 [optimization.patch](2026-11-14-review-admission-optimization.patch)，以保存的用户工作树为基线；不包含其他既有修改。

## 剩余问题及暂停状态

1. 冷准备和最终复验有新增依赖证明成本，本次没有解决完整生产冷加载耗时；未对真实137镜/265片段做性能外推。
2. 暖批次仍做必要的字节/文件身份/祖先/清单检查；受影响镜头及其父链仍会局部重建。没有进一步缓存跨批次或跨生成阶段的可变进度。
3. temporal 原生观察接收保留原协议，不在本次改为增量快照。当前优化面向现有 Wan/分段审查路径。
4. 协作暂停在读取阶段之间和原子写边界生效，不能撤销已在途系统调用或已提交的模型任务。第36镜的原未决身份及五处画面返工完全未处理。

交付前只读核对：两个协调状态仍为 `paused_by_user`；已交接的生产/包装/旧服务 PID 均不存在，8188无监听；停止文件和 RunLock 仍绑定原token。没有手动删锁，没有修改真实观察/回执。优化完成后继续保持视频暂停，只有用户另行要求才恢复。
