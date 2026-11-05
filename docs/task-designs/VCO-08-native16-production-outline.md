# VCO-08 生产接入调查提纲

状态：**候选接口设计，尚未实施或准入**。C四窗资格仍在运行，必须取得完整320帧实际技术/动态接受后才启用生产mode。此文保存当前调查与实现者拟作的选择，不替代`VCO-08-design.md`原五项Acceptance，也不把提议写成用户逐字要求。

## 已确认的边界

现有`scene_clip_records.scene_context`在预算前校验Wan模型/Comfy图，`validate_clip`重建Comfy事务，`collect_progress`要求父片已接受才允许后代；不能直接增加mode名称后共用这条事务路径。`scene_media.plan_scene_upscale`封闭schema2/3并调用旧单尾帧mapping。`scene_revision`封闭execution schema1/rendering identity2/3，prompt records只把schema2解释为whole。需要贯通所有这些消费者，保持旧版本字节/语义不变。

拟采用独立`temporal_extension_v1`分支：纯协议/预算、原生事务/记录、生产准入和子进程worker分别成模块；共享已证明的锁/不可变Artifact和下游帧贡献结构，不伪造SceneComfyClient POST或Wan graph。实际调用计划是原生workflow manifest，证明13历史像素→VAE4 latent→48层clean KV→新增采样→解码→仅追加新增。

## 待固化的实施选择

1. 初始仅fast768×432、16fps部署时钟、每窗原生93；生产窗口数按完整时间轴推导，不把320帧资格样片当成新的生产时长配额。首窗保留min(93,N)，后续各min(80,remaining)，非末窗满保留、末窗裁尾；不截短/自动切镜/切旧后端。实际可用磁盘/物理/commit/GPU守卫保持。已观察质量范围仅四窗320帧，更长新链不能预记视觉稳定，仍须实际逐窗静态与完整动态门禁。原模型没有fps输入的事实明记。
2. 新execution schema2、prompt schema3、rendering identity schema4、complete clips index schema4是候选版本分配；旧schema分支保持原精确字段。新预算含明确protocol与13历史输入kind，不能让旧schema借新mapping接受陌生字段。边界测试1/13/80/93/94/173/174/253/254/320/321/333/334及长链，完整覆盖原PCM/字幕/时间轴；资格范围与执行长度分开记录。
3. `scene_rendering`显式mode和独立temporal-evidence Artifact；不借用whole准入或Wan模型角色证明LongCat。配置/冻结身份绑定模型清单、工作流、运行核心、维度、时钟、步数/CFG、历史/新增规则及实际资格范围。缺失/failed/unknown/unverified或SHA漂移不得启用。
4. C资格worker锁定白鹭缓存和320预算，不能直接充当任意生产输入接口。正式子进程worker需要独立请求封装、场景预算和提示缓存身份。现有已编码提示只复用；新生产输入的不同提示才需新的独立编码，不能重编码本次已有缓存。缓存key包括确切正负提示/模型/编码算法/依赖身份，缺项不能静默换提示。
5. 已资格的数值核心/11官方源宜按原字节复制到稳定D:/VideoSi/tools下版本目录，附源码/依赖/模型许可清单，复用现有隔离依赖；不把可丢弃研究目录当作无版本生产入口。只复制小源码/收据，不复制权重、不升级Comfy或生产Torch。父进程3.12不导入Torch，子进程既有3.13+cu130，异步allocator必须在任何Torch导入前设置。
6. 正式worker的包装/输入源码若不同于C，不能声称全源SHA相同：分开记录不变数值核心和新封装，取得实际新封装对应资源/恢复证据。C质量接受不能自动变成所有新视频质量接受。
7. 每续窗从父**原生RGB frames**最后13帧取条件，绑定父result/frames及确切范围与消费哈希。父viewing.mp4/单张last-frame仅供观察或播放，不当作模型13帧输入。非末窗的父raw总93，所以范围始终[80,93)；末窗裁尾后没有下一窗消费。
8. 原生intent/原生job结果与Comfy事务分开：排他一次提交、PID和进程起点/命令身份、实际资源监督、原sample提交后decode-only。失败/unknown不自动重新采样或换后端；诊断重算不调用模型。无时间或人工占用上限，实际空闲门槛保持，精确停止资源值随终态保存。

## 完整动态观察需要单独设计

原segmented路径的父片逐个human接受不能被悄悄放宽。原生一镜多窗宜以每scene完整chain为观察单位：生成时各窗真实技术/静态筛查，最后完整chain播放一次，明确覆盖所有窗口与边界，再允许下游。记录一个真实chain观察及各片段覆盖映射，不伪造数次独立观看事件。

这需要原生专属进度/父绑定和观察记录：生成请求只绑定当时已存在的父技术/静态证据，不能预先引用未来的human接受SHA。完整chain接受后index明确指向同一真实观察及相应帧范围。VCO-04诊断与连续性准入也要认识这一范围，缺完整动态或当前有效报告时不许超分/合成/发布。旧segmented/whole观察契约保持。

## 媒体与恢复消费

- 320资格case及任意合法末窗必须保留原生93帧、采样latent/Generator、全部映射和被裁尾证据；历史只输出一次、PTS i/16。
- 下游提供浏览器可播放的generated/source/chain，原生RGB证据和13帧条件分开保存、明确绑定；编码色彩差异按既有VCO-02诊断，不把重新编码伪装逐像素相同。
- 模式或协议/模型/提示改变会使视频与其后代观察/诊断/超分/合成/交付失效；合法继承原文、语义计划、已接受图、PCM/字幕，不继承旧视频观看。
- 不把native mode命名为whole而借旧`WholeExecutionCheck`优化。若要媒体初次准入后避免逐帧重复昂贵上游重核验，需要新的明确guard类型和闭包证明；不能放宽未知guard或回滚用户已移除的whole重复检查。

## 软件验证范围

正式设计需列明文件/签名/精确命令，再按TDD实施。测试必须覆盖预算全部边界、旧冻结options/graphs/schema精确重放、13历史实际传入、parent/static/Generator/模型/工作流/cache漂移零采样、进程未知与部分提交恢复、成功latent仅解码、模式修订后代失效/合法继承、完整chain观察/VCO-04下游门禁、完整PCM/字幕/帧贡献与零重复调用。

最终全库仍未通过。已证明的751前缀和故障修复5项保留，未取得结果的4375列表在M。新产品改动按实际影响补充最终回归；不机械重跑无影响前缀，也不借旧源码结果宣布新模式通过。
