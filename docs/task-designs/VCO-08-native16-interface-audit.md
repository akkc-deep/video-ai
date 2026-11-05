# VCO-08 正式16fps接口调查

状态：只读调查与候选记录，不是生产接入合同。当前15fps案例003三窗及整段动态已接受；用户已选“按建议直接推进，无需逐步确认”。新的资格合同和账本分别为`VCO-08-native16-qualification-design.md`、`VCO-08-native16-qualification-plan.md`。本文保留调查过程，不预记432p/16fps通过，不修改原25项冻结执行源。

## 已确认的现有接口

- `planning/scene_execution.py`的MODES只有segmented_v1和whole_scene_v1，budget schema1；whole分支每scene最多320帧，调用旧`_clip`验证。不能仅向MODES追加名称后沿用Wan预算。
- `planning/scene_clip_continuation.py::_clip`要求续片head=1、input_kind=parent_retained_last_frame、generated_frames按Wan公式推导。LongCat续窗13历史/80新增必须有独立协议验证和映射，且所有消费者一致。
- `planning/scene_video_prompts.py::parse_scene_rendering`的字段封闭；schema2 prompt仅允许whole_scene_v1。新模式需新的明确schema/绑定，旧schema1/2逐字恢复保持。
- `planning/scene_revision.py`固定旧rendering identity版本与mode；模式/协议/模型/工作流/提示的变化须建立新视频身份，视频及其后代诊断/超分/合成/交付失效。原文、PCM/字幕、语义计划和接受图按现有合法继承规则保留。
- `runtime/production_scene_clips.py::_produce`按SceneComfyClient事务提交，`_input`是单图；新原生worker不能仅写13历史的审计字段而继续提交单图Comfy图。需实际历史像素输入、官方VAE时序编码与clean KV调用证据。
- `runtime/scene_execution_records.py::verify_current_environment`的whole准入强绑定Wan四模型、原Comfy workflow及fast768×432/native16。LongCat须独立准入；不得把旧whole evidence当作新后端证明。
- `runtime/scene_clip_records.py::SceneClipStore`已有真实RunLock、不可变记录和原子写入机制；可评估复用容器，但其请求/graph/媒体消费者必须明确认识原生后端。
- `runtime/scene_media_records.py::SceneMediaStore.recheck_inputs`只对whole关闭重复上游核验；`_scene_media_check_coverage.py`严格验证现有guard类型和来源。新模式不能借名称获得旧whole优化闭包。是否需要新闭包应在设计中明确，避免把慢但安全的fallback当作新模式已优化。

## 官方pipeline的已确认限制

来源为案例003 `working/longcat_video/pipeline_longcat_video.py`，固定官方提交6b3f4b8582a8bc3f20f795735f5383716c4ba794。

- `generate_i2v`与`generate_vc`没有fps或显式height/width入口，分别在约673/910行调用`get_condition_shape`，后者定义约352行。只声明16fps输出不能伪造模型具有fps条件输入。
- 续窗约1007行传num_cond_frames，约1016行按VAE时间scale推导num_cond_latents；13像素历史对应4 latent，clean历史与新增采样分开。须保留官方数值路径及历史帧实际来源。
- 768×432需新的固定shape adapter及实际前向/VAE/资源证据。候选覆写实例的`get_condition_shape`，让两个官方入口都消费同一432×768；不修改已运行的15fps worker。
- 推导latent为[1,16,24,54,96]，历史KV token=4×27×48=5184。这些只是推导，尚无该shape的实际模型检查/视频证据。

## 已提出但尚待选择的资格样片路线

延续已验证隔离原生worker；新案例采样前冻结768×432、16fps部署输出时钟、50步/CFG4/seed42和既有数值适配。复用同revision模型和现有精确文本缓存，不下载、重新文本编码或制作权重副本。每窗原生93帧；四窗保留93+80+80+67=320帧/20秒，末窗只裁尾13帧；历史输出一次，无插帧、重复、混合或现有15fps视频变速。三条边界frame93/173/253分别为93/16、173/16、253/16秒。

432p资源、实际shape/KV/VAE、四窗技术及完整动态观看均需新证据。15fps三窗仍单独记账；首窗已接受不代替当前253帧整链接受，也不代替正式新样片接受。资格上限和生产适用范围须按真实成功证据声明，不能声称任意长度稳定。

## 设计阶段必须解决的接口

1. 独立temporal协议、execution/schema版本、config和prompt绑定，所有mapping/媒体/诊断消费者的兼容分支。
2. 真实原生worker运行清单、隔离Python/deps/源码和模型身份；机器可验证的原生调用计划，不能伪造Comfy graph。
3. 独立实验/生产准入及适用题材、尺寸、时钟和最长实测链范围；失败/unknown/unverified拒绝启用。
4. intent排他提交、owned-worker身份、持久化起点、单次采样、已提交latent后的同身份decode-only、父结果/历史像素/筛查SHA绑定；unknown不自动重跑。
5. 无人工占用和执行时间上限；实际空闲物理/commit/GPU/磁盘守卫、资源审计及仅自有进程停止保持。
6. 模式修订与视频后代失效、旧冻结run零改写、全链完整动态观察和VCO-04连续性报告接入。
7. 精确单元/CPU事务集成/真实资格样片与最终软件回归分账；不能把5127项旧collection身份直接外推到新增产品源码。

## 当前软件回归断点

已报告751 PASS、1 FAIL，4375未完成；细节在案例003的regression-resume-manifest.json和regression-checkpoint-boundary-proof.json。当前GPU结束后先单点复现原timeout故障，若确认故障注入被production无时限覆盖，仅修测试注入策略；生产时间规则保持。然后继续余下精确nodeid，不重跑已完成前缀。将来新产品改动须依据实际变更补充验证。

## 正式消费者补充调查（Q首窗运行期间，仅只读）

- `runtime/scene_clip_records.py::scene_context`在预算加载前即校验Wan模型/WorkflowTemplate；正式temporal上下文需独立分支，不能在此路径上贴mode标签。`validate_clip`重建Comfy请求/提交与schema2技术记录，原生事务也需要独立验证分支。`collect_progress`、`complete_value`、`require_scene_clip_acceptance`可评估复用核心父链/观察流程，但index须明确版本和协议。
- `planning/scene_media.py::plan_scene_upscale`只接受schema2/3 index，并对每片调用`scene_clip_frame_mapping`。新13历史映射必须显式贯通此消费者，旧schema不可接受新的预算标记；不能只修生成端。`runtime/scene_media_records.py`对execution-budget的读取亦只有schema3分支。
- `runtime/scene_clip_observations.py::build_observation_template`主要消费已验证clip/request/mapping/last-frame和父观察，支持复用真实观看契约；父last-frame是审计/观察引用，不能冒充13帧模型输入。原生输入必须另外保存完整13帧来源和调用证据。
- `planning/scene_revision.py::snapshot_execution_clips`严格要求execution schema1/algorithm scene_execution_v1；rendering identity仅schema2/3。新execution/protocol/schema应有独立分支及准确source快照验证，旧版本不得因加入新mode而被重解释。
- `runtime/scene_video_prompt_records.py`以schema2==whole_scene_v1判定；新temporal prompt需独立版本、完整覆盖新的执行clip ID，并仍按VCO-01只把视觉字段送模型。
- Q的worker明确锁定93+80+80+67、原白鹭文本缓存SHA，因而只是资格执行器。不能直接对其他生产提示调用它；正式worker须支持新输入独立缓存身份及合法未满窗裁尾，且不得重编码本案例已经存在的文本。实际模型/API无fps条件的事实仍必须保留。
- 初始生产适用帧数/窗口上限须依据Q成功范围声明；若拟支持1..320帧，预算应让非末窗始终全保留、仅末窗裁尾，续窗条件仍取父原生93帧最后13帧。纯预算与所有媒体/修订消费者需测试覆盖1/13/80/93/94/173/253/254/320及321拒绝。此处是候选设计要求，不是已实现/已准入。
- 新worker的软件身份与Q资格身份若不同，不能沿用Q全源SHA宣称相同；必须明确区分数值核心/输入封装差异、重新取得新源码对应资源证据并完成必要真实生产验证。禁止通过关闭旧守卫绕过身份差异。

原timeout已实际RED→GREEN（5项通过）；后续4375 batch在会话中断后进程消失、无完成结果，不能从tmp目录或诊断marker推造PASS。当前先推进已授权Q，未解决余项留软件收尾。此段覆盖上段旧“待复现”操作状态。
