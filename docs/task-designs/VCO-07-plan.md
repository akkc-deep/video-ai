# VCO-07 Implementation Plan

## 2026-10-31 07:30 无作者历史与当前报告恢复

- [x] native2635最终56 passed/130.29秒，7300fbf8edcc4b2aa9ffafefcaabc9fd退出0，包含真实confirmed-defect跨同媒体新epoch仍阻断及全部新absence/身份/预算回归。此批不再重复，接下来仅实际报告恢复。

- 新05a14d98 epoch已提交，但56797首段305.579秒在第二次报告核验超时；jobca72c3c1/attemptaa9e098d已有completed terminal，audit20261031-072315-7fa0eef1e1fb原report/metrics保持，assessment待恢复。新Engine已固定，禁止再建epoch或重测首段。
- 核实_historical_failures原先对无任何已提交作者raw/receipt的旧assessment也完整复验报告，无法产生confirmed defect却重复占用共享预算/时间。轻量头提取为_assessment_header，与当前完整_assessment共用原schema/run/UID/规范路径/epoch校验；无匹配raw且无receipt才continue，其他任何作者状态/孤立receipt仍走原完整证明和_reviews，原Reader逐个严格读全部raw，不跨调用缓存、不跳祖先、不放宽64/300。
- RED6e3ed569c3024257a6841be7f9badd6d为2失败9通过；新later-raw检查随定向与真实confirmed-defect重评单例运行7300fbf8edcc4b2aa9ffafefcaabc9fd，结果待返回。旧runtime按751b86b75ef3bbe5aea380c962fb56713822881cf49605af8d1b75fbe8b28d60归档为数据，不执行。
- Ruling: 无任何作者消费的历史报告不参与“同媒体已确认缺陷”谓词，因此不再因该旧报告内容损坏阻断当前；轻量身份仍必须有效，当前报告及任何已有作者raw/receipt的历史仍完整核验。若判断错误，代价是无法在本门槛发现未使用的旧报告损坏，故不能宣称全部历史报告重新通过；原件、旧terminal和旧审计保留，后来出现raw立即恢复完整检查。
- Final review: 无Critical/Important；Minor deferred：补“前一条无作者、后一条/继承来源有缺陷”和“matching raw后另有坏raw”两项组合回归。现有代码扫描无break、无作者仅continue，真实confirmed-defect单例保留；本轮不扩展无关测试。
- [ ] 定向通过后冻结runtime-only新库存，Engine保持05a；仅运行recover-shared-budget-and-gates.py恢复原首段、首次分析scene2/3并用正确RunLogger提交源回应。不要重跑旧编排。

## 2026-10-31 07:12 三报告共享预算与重复表示验证

- bddd epoch三份assessment实际齐备，analysis624793e6结果3 awaiting_review/0新源POST，1352/784/810个机器关注项全部保持unverified或not_comparable。已据用户真实完整观看整理review草稿3a0dda5e。源提交因旧操作助手logger=None被匹配生产日志入口拒绝，77228退出1，未执行超分；另存submit-current-continuity-reviews.py传RunLogger(RUN,production=True)，不覆盖旧助手。
- 独立核实仅前两报告/metrics/pairs已71,288,103 bytes，聚合Reader必超过64MiB。新13项回归e06765c6准确RED；metrics/pair仅可依据已严格验证report重建producer wire，实际length/SHA完全匹配则保留冻结字节/closure而免重复解析；任何其他表示走原strict parser和原收费，16MiB/64MiB/300秒/decoder展开上限不改、不退款。共享iter_document_bytes使writer与证明完全同格式；编码前字符串上限及增量输出限制防大分配。
- 初GREEN582d3110为12过1失败，fallback canonical digest分配31MB；改为逐值严格JSON类型比较、float repr区分负零且无巨量序列化。七文件e366为97过5失败，纯writer夹具绕过构造器缺deadline；仅补其合法300秒deadline，保留产品时限检查，并加真实writer过期零写入回归。
- 最终七文件103 passed/65.88秒（7b482ccc60ab4a14aa21144ded31130f退出0），独立审查无Critical/Important/Minor。旧三个模块原字节按301 SHA核对归档pre-expected-json-*.py.bin，仅数据不执行。
- 真实三历史报告同一Reader/原300秒/原64MiB只读验证34c3a815d65d4835bebc1c147aa52ad7退出0，结果shared-report-metadata-check-63f0a9fa0bc5433296ab06a04ec39158/result.json：累计解析35,025,219 bytes，closure分别4113/2587/2923，原三报告SHA及全部机器状态不变，0CV/0生产写入。
- Ruling: 精确派生重复表示只需完整字节证明，无需再次parse其已被严格report验证的同值内容；免去的是未发生的解析，不放宽/退款预算。不匹配的合法旧编码仍正常解析/收费，非法类型/重复键/非有限仍拒绝。若判断错误，风险是独立expected编码与writer漂移；共用纯函数、完整SHA和不匹配回退、原文件最终复核共同约束。
- [ ] 此media修复改变Engine，须新库存/新epoch和正式三报告，不伪签历史报告为当前；原三源及用户完整观看、所有旧报告/assessment/failed记录保持。后续源准入、超分/合成/最终观看与独立发布仍待实际结果。

## 2026-10-31 06:25 真实预算超时后的目录扫描优化

- [x] 实际只读profile cac6c4e002564721a85cb36720c1189a退出0，phase-bd57037282d947a68f767d715e4a779f：warm_context174.382、repeat_context157.014、epochs13.923、manifest_binding3.974秒，无生产写入/模型。较旧真实264秒context明显下降，正式300秒仍以真实结果为准。
- Ruling: 仅删除操作助手在真实API之外多做的一轮scene_context预热，改以已冻结budget/原请求准确顺序找epoch；软件/三源技术记录/SHA/原run库存核验仍在助手，真实API中的完整context、RunLock、Reader起点/300秒以及每次提交前守卫一律不动。预热重复扫描曾只减少约17秒，却额外耗时174秒，不应当作产品强制门槛。若判断错误，会失去操作助手额外提前报错，但产品入口在任何写入/分析前仍完整拒绝非法输入。
- [x] 最终299库存6b1c0f0dfc674cb59291ef4c69c73198由fdc23dc680574edd82fb5cf3b47eab1d准备退出0，追加新analyze-inventory-recovery.py及新操作助手身份；先前298只作历史，不用于运行。现单次新CPU编排启动，等待实际结果。

- 新epoch122e58bc已提交，但native19834第一段307.299秒TimeoutError，264秒用于前置核验；job0d863bd4/attempt8690cf4b failed terminal及audit20261031-061644-5a10babbaa58完整metrics（无report）保留，不能续写failed attempt。无新源POST。
- 实际1874文件5轮profile3d79ed39为1.053秒/约75000重复祖先lstat；inventory新回归b0e737d9为1失败5通过（100兄弟文件101祖先检查）。本次扫描共享父目录完整检查，逐文件仍lstat拒绝链接/重定向，结束再次完整父目录检查；每次verify仍重扫，不跨调用缓存，不放宽bytes/inventory/absence或300秒。
- 独立方案复核发现先收集全部files再校验会延迟拒绝junction；新回归03a9caaa准确RED后改为流式首次遇到parent立即safe_path，才继续下一文件。最终8项目录回归+句柄失败项隔离重跑9 passed/9.07秒（811277b565f64e7b8c223157a488e9ba）。先前五文件8dd1c03a为80 passed/1 failed，唯一失败是9000句柄计数比瞬时baseline少1，隔离已通过，原失败记录保留。
- 最终真实1874文件5轮microbench bdd2af59为0.226秒（原1.053），不等于完整300秒已通过；298软件e9fe0c7474004d9d926b9caac9b5edb3由c15adea819244e8f8adbf096ce5cb08c准备退出0，原293仅runtime/_whole_scene_admission.py变化，Engine保持，因已failed terminal仍需显式新epoch。
- [ ] 当前只读实际预检profile验证剩余耗时，无生产/GPU；结果后才运行新run-inventory-source-gates.py一次，不重复旧编排。原三源/全部观看/a5报告和failed记录保持。

## 2026-10-31 05:58 当前提升证明验证与执行

- [x] 接续上一轮已经实现的resolver，保留RED bf44c9c7和17项GREEN，不重写或重生成原媒体。
- [x] 使用历史Engine只读验证a5原report/metrics，dc070cc41944471fad45d66dd48a70b0退出0/4111项closure；历史代码仅哈希数据，不执行。
- [x] 六文件86 passed/62.52秒；独立审查发现1项Important：按声明frame count预分配列表可能超出元数据预算。新增小记录/500000声明帧回归RED e9bcda07a41041ba83fcc7bd92708cda，观察9,080,034字节峰值；先验证实际list长度，再enumerate逐项严格int/None比较后，六文件87 passed/62.33秒/02f5f389d4344b1f8a25154f5d70f175退出0。旧helper归档pre-budget-guard-continuity_promotions-7f180c704c55.py.bin，禁止执行。未重跑无关旧矩阵或全库。
- [x] 新293文件身份为diagnostics/implementation-promotion-proof-35184bae898b4f54ad239583a87de54d.json，准备3414dbd26ea1428790c5f27cd28b9f1c退出0；原287中仅report模块变化，新helper/测试和操作助手加入清单。
- Ruling: 已写a5报告经过新只读验证器成功不等于当前Engine正式报告。resolver改变Engine后按原设计以reassess API建立新epoch/新当前诊断，完整保留旧a5 report/metrics/attempt及更早failed terminal；不续写或伪装旧报告为新Engine结果。若判断错误，代价是增加本地CPU诊断工作，但不增加源模型POST。
- Ruling: run-promotion-source-gates.py仅串行编排现有epoch/analysis/review助手，外层沿用已有revision_scope和有界不可变句柄，减少相同输入重复准入；各API仍保留自己的锁、300秒Reader及完整字节/目录检查，异常停止。不合并GPU阶段，避免CPU助手的网络禁用作用域影响服务。若判断错误，风险是跨助手缓存生命周期过长；原owned root排除和Windows不可变句柄界定其可复用输入。
- [ ] 本次仅启动该CPU编排一次，完成正式三报告/风险回应/源片准入后再逐帧超分、合成、最终观看及独立发布；不得重跑整个编排去处理其部分失败。

## 2026-10-31：正式媒体提升后的历史路径闭包

原a5 epoch第一段report/metrics已写出；复用恢复在291.502秒进入完整闭包后，错误地要求已被os.rename提升的旧staging/source.mp4仍存在。正式source字节有效，source/generated/last_frame各有固定media-ready receipt；不得补造staging、改历史JSON或按相同SHA全局替换。新增media/_continuity_promotions.py只读resolver，接收已验证sidecars与_ReadWindow；从明确声明的同clip clip.json/mapping.json/media-ready/source.json锚点，验证clip绑定request/submission/last-frame的canonical摘要、完整budget映射、v1 technical recipes、三份固定receipt的字段/源链/target命名/同run/32hex staging目录/完整technical evidence。仅receipt本身和其绑定JSON技术证据可解析精确staging artifact，原字段/命令/报告和processing unknown保持。

resolver只在actual_inputs已比较后建立，额外证明加入closure而非回写原report.inputs；_expand_evidence携带当前JSON文档路径限制解析来源，并遍历新增证明。存在的stage必须按原身份检查，不能借有效target掩盖坏stage；缺stage仅在receipt证明后核验正式target，五字段历史identity还要匹配原mtime。最终window guard重核proof/target以及stage状态；错recipe/摘要/源链/路径/作用域/目标/漂移均拒绝。先做纯文件生命周期单测RED/GREEN与历史a5完整报告只读harness（禁止CV、服务、网络、归档执行），再保存新Engine并新epoch生成当前报告；旧a5 report/attempt及原3POST/媒体/观看均保留。当前无生产/GPU调用。

## 2026-10-31：真实整段分析的大体积审计恢复

实际275调用第一段在276.353秒进入分析后因metrics.json超过16MiB失败，job/failed terminal及436原pair全部保留。直接比较JSON compact也为44,516,216 bytes，不能只压缩缩进或提高16/64MiB上限。typed-geometry-packing-size-71777e442020401ca41e820755a60a6e的纯CPU保留数据验证：比较aggregate11,943,551 bytes，全部pair12,027,181，三份比较35,914,283，唯一展开geometry32,462,067，所有行/类型/值保留；其余报告元数据和实际整链预算仍待验证。

执行约定：新增media/_continuity_storage.py，只在geometry紧凑JSON总量超过1MiB的大measurement启用typed_geometry_zlib_v1；report、metrics及该measurement所有pair统一存储，普通小measurement保持原JSON字节。只转换geometry.vectors（严格JSON+zlib，保持float/int/null及负零）和geometry.sampled_pairs（固定[rows,2,2]的uint32小端整数+zlib），其余逻辑字段不变。每块精确字段codec/rows/bytes/sha256/data，data为严格base64；顶层schema_version=2且continuity_storage=typed_geometry_zlib_v1，解码后恢复原schema1逻辑对象，measure/scores/trajectory/metric_digest不变。

物理JSON仍逐文件16MiB、每调用唯一路径64MiB收费，不退款；解码额外限制每块原始字节16MiB、每window唯一块总展开64MiB，rows必须为正整数且受字节数约束。拒绝未知codec/多字段/错误形状或长度/摘要/非法base64/截断或尾随压缩流/非有限数/超限展开，先限量解压再构造数组。decoder缓存按完整descriptor绑定，重复内容不新增展开预算，返回独立列表以避免跨文档可变别名。_ReadWindow.read_path及AuditWindow.read_json共同还原；calibration现有window入口随之支持新旧格式；严格report/metrics/pair对比和producer闭包继续针对完整逻辑内容。

先做codec与真实writer-reader CPU回归RED/GREEN，覆盖普通旧字节、类型/负零、坏流与资源边界、三文档共享展开计数、真实小VCO-02证据强制packed贯通及篡改拒绝。独立审查后记录新software与Engine，使用reassess API建立新epoch并生成三个新请求；旧failed job/audit不改写，不续写旧attempt，不POST原模型。仍以原共享300秒真实分析验收；必要性能修复须另行RED/GREEN，不移动Reader或延长时限。源片接受、超分、完整PCM/字幕、最终观看、显式发布和零副作用重放顺序保持。

**2026-10-31 04:13+08当前执行身份与入口：** 仅native96290运行真实CPU分析；日志vco07-real-continuity-cached-proof-47b685b5e9584d818247404d8846a66a.log，阶段diagnostics/continuity-phase-4eb3b5865a9e46478c40c7b63a5d5887。准确新275软件清单为diagnostics/implementation-cached-proof-481c61c215ec4400a0b3138bc80feb69.json（90f9bf80487c4760a0f0aa9f2c01195c准备退出0）。相对269只改scene_revision_records.py的cached proof：相同frozen对象且显式whole时，verify_captured_bytes已包含verify_frozen，不重复紧邻的同一闭包扫描；不同对象/默认历史分支仍检查两次，所有字节/目录/absence守卫保留。新增测试RED78057d36为1 failed/8 passed，GREEN4fc5796653e640b99a63e5873eea99ed为86 passed/10.41秒/退出0，独立复核无Critical/Important。之前profile已完成warm_context294.954秒（scene_context291.149），重复闭包占主导，拿到完整热点后在无生产写入下停止剩余重复profile，native87350退出-1且agent-stop-after-diagnosis.json保留；不记完整profile通过。原模块数据归档pre-cached-proof-scene_revision_records-21dfae65843745869cacd3908b405c46.py.bin，SHA a78db45fab8be7cdb66c64d745dc81f2bec58a3705d7c49bbe884685fb8f4ba9，禁止执行。launcher已移除异步faulthandler，当前SHA c8ec94c85974cda445a70709c843ffa78468bb45594e83e9005b021ea171c780；原冻结分析助手/Reader/300秒不变。275同时绑定未执行的风险回应与超分助手；初次准备453661因str传read_json只读失败、未输出清单，四新助手已统一Path包装后最终准备通过。源3POST、媒体、epoch和观看均保持；本次实际分析结果尚待返回，不重跑旧矩阵或生成源片。

**2026-10-31 04:04+08实际失败点与唯一当前入口：** scoped分析第一段于04:01:32返回blocked / TimeoutError “continuity deadline expired”，耗时305.475946秒，结果在diagnostics/continuity-phase-b74cfb5b83e3464aa4e65a7d92e6c074/scene_0001_clip_0001.result.json。无analysis jobs/intent/attempt/report，无run锁、无新POST；不是质量失败，不需要新模型或新epoch。native28423随后清完输入句柄但异常诊断输出未退出、CPU不再增长，已只终止自有worker9416，native退出-1；worker-finalization.json保留真实API结果与处置，不能把native-1伪记成正常结束。当前仅native87350运行只读profile-continuity-preflight.py，日志vco07-real-preflight-boundary-profile-0155337bca8e44259ed40b3dd765d596.log，阶段diagnostics/preflight-profile-764a2b2c71234dad9f88113e45f6c910。以同步函数边界计时定位EvidenceReader/RevisionGuard/scene_context和逐帧manifest核验，禁止模型/服务/网络/SMTP与生产写入；不再使用异步faulthandler。原269软件、3源POST/媒体/epoch/观看保持。先读取profile进度定位剩余热点，不重复正式分析、旧软件矩阵或源片生成。

**2026-10-31 03:50+08唯一当前CPU调用：native28423。** 日志vco07-real-continuity-scoped-48769315cd8d499eb2e76b66f94fc0cf.log，阶段diagnostics/continuity-phase-b74cfb5b83e3464aa4e65a7d92e6c074。外部launcher launch-continuity-with-revision-scope.py（SHA a7e6416ccd5d2f8bfd79d52f8be744ab71d908cd0858be916ae4a54e3d58bc00）只在未改字节的269冻结分析助手外补正常make_video已有的revision_scope，并每120秒记录诊断栈，不改Reader/300秒。旧native98337已由agent在CPU预检阶段中止，native退出-1；当时没有preflight完成标记、run锁或analysis jobs，未执行检测器，不是一次检测失败。旧phase d7f95aec保留start及agent-interruption.json（03:49:41，worker44192，CPU544.28秒）；原因是操作助手未带正常入口的修订作用域，祖先证明被反复重建。产品源码、269清单、原媒体和三POST保持。先监测28423，不启动旧operator；两个所需集成已通过，不重跑。风险回应/超分助手也已补同样的正常revision_scope，尚未执行。

**最新运行入口（2026-10-31 03:43+08）：** native3110已退出0，恢复单例1 passed/609.83秒，所需两项集成均通过，不再poll3110。实际CPU连续性分析已启动，唯一native98337，日志vco07-real-continuity-analysis-f02ebe549b474be492ad872b096b1d55.log，阶段目录为diagnostics/continuity-phase-d7f95aec0eae4134943da4cd3895b1ee；先监测该调用，不重复分析或修改269冻结文件。三scene各一clip，现有单段完整观看即覆盖同scene前缀要求。尚无实际报告/准入/超分结果，GPU助手仅准备。

**2026-10-31 03:37+08执行补记：** 下方性能“尚未实施”已由实际whole专用有界输入保护修复取代；保持首次完整哈希、目录库存、默认分支、Reader及共享300秒不变。共享writer根引用计数修复通过竞态RED四项和最新53项GREEN，独立复核无剩余Critical/Important。贯通单例1 passed/1292.98秒；恢复单例仍在native3110。三段真实human_video均已准备未提交；准确269清单5a034c5b及CPU分析助手已准备未执行。下一步等恢复结果后执行原三请求真实分析，再按源片风险回应/逐帧超分/最终观看/显式发布/零副作用重放推进，日志见verification最新条目。

**2026-10-31当前续接：源片已生成，转CPU准入性能修复与连续性分析。** 原265软件调用8c2b已退出3（awaiting_continuity_review），三个原POST全部成功、471生成/463保留，原source3011字节未变，GPU/服务已释放；25d33344/fab81ff3的只读审计退出0且265原字节完整。前两段实际human_video已确认，第三段完整观看问题待回复；三段VCO-02/作者ROI/独立reference/manifest均已准备。旧BLOCKED/零POST/运行中为历史，不再启动旧advance。

**性能修复约束与验证（尚未实施）：** 实际whole源准入收尾耗时超过共享分析预算，78ddb647/8726ea7d profile定位大量小文件反复打开与路径核验（真实1000输入两轮0.619秒）。VCO-04分析持锁共享300秒保持，不能挪动/重置Reader来放宽此契约。只在whole调用扩展已有不可变输入保护：完整首次字节哈希后持Windows只读原生句柄，最多32768项；复用仍核验原生身份/元数据/规范路径，目录inventory不改；owned root与manifest继续每次完整哈希，进入writer须释放本root既有只读句柄，取消/异常/延迟ContextVar线程均关闭且不复用过期缓存。历史/segmented默认路径不启用此扩展，非Windows继续完整哈希。先RED证明接口缺失，再验证外部写/替换/删除拒绝、mtime变化、超过CRT描述符容量的有界句柄、overflow完整哈希、owned晋升、异常释放和延迟线程；随后既有相关单元/whole检查和真实相同输入profile。只在证据支持后继续实际CPU分析，重新保存实现身份，不新增模型POST，不重建修订，不重跑无关旧矩阵；原265模块字节只归档不执行。

**最新授权：** 用户“继完成当前任务，直到完成”已明确要求持续完成同一VCO-07，本次按BLOCKED -> READY -> IN_PROGRESS恢复，消费259库存及f558恢复audit推进目录修复后的真实入口。已授权的本地启动前软件/目录处理持续执行；已有模型intent按原记录恢复，实际完整观看和最终独立显式发布仍据真实材料验收。以下BLOCKED/待新授权为历史。

**当前最新状态：** 702d6b实际推进已于20:18:25+08退出1，桌面准入已过，Comfy CLI因user目录不存在退出2，0模型POST、原source未变。目录准备已修复，RED2/完整GREEN9及实际CPU CLI/新259库存与f558恢复audit均完成；新advance-production-after-directory.py未执行。当前BLOCKED等待本次服务失败后的明确继续授权，准确入口见VCO-07-handoff.md。5项桌面授权保留，不再次要求关闭应用；以下“运行中”段为历史。

**最新执行状态（2026-10-30 18:38+08）：** 已授权单次真实推进130ced3e53a9461c9f13f07e5bf876d1退出1，GpuBusyError；初始epoch已提交、第一scene输入及请求保留，0模型POST/技术输出、原source3011文件未变。未重跑已有软件检查/重建修订/改桌面策略/关闭用户应用。现BLOCKED于8项未批准桌面进程的解除选择及失败后继续执行授权；准确结果、1005文件停止库存和新恢复边界见VCO-07-handoff.md。旧inputs-only audit/operator不支持现有epoch/request，不清理现场、不自动重试、不准备VCO-08。

> **For agentic workers:** Use superpowers:subagent-driven-development for bounded implementation tasks and superpowers:executing-plans for tightly coupled integration. Track checked steps and evidence here; the existing design is authoritative.

**Goal:** 接入显式、证据约束的 whole_scene_v1 完整生产链。

**Architecture:** 保留语义plan；纯函数派生execution clips，冻结证据和渲染身份后持锁建立execution-budget。所有视频消费者使用execution，叙事和参考图继续使用原plan。

**Tech Stack:** 现有Python3.12、PowerShell bootstrap、pytest、FFmpeg；不新增依赖。

**Spec:** docs/task-designs/VCO-07-design.md

## Global Constraints

- 不新建worktree、不写.git、不覆盖已有未提交成果；当前工作区执行。
- 缺省/旧两字段配置保留原记录；显式segmented/whole才使用新schema。
- whole为fast768×432/16fps，1..320保留帧、最多321请求帧；原PCM/字幕完整，不自动重试/回退。
- JSON16MiB、同调用元数据64MiB；证据原字节和全部外部身份须核验，不重签旧观察。
- 每份新媒体独立完整观看；fixture不作真实视觉证据。真实源片、超分、合成、最终观看、发布分别记账。
- 定向和兼容逐文件检查；全库留VCO-08。测试与真实推理串行。

## Review Focus

- 显式配置与冻结role/schema不能交叉混入历史分支。
- 证据真伪必须来自闭包交叉核验，不依赖单个ready布尔值。
- 同名clip跨mode不得继承视频或观看；历史source预算不能被目标预算替代。
- 状态读取零写入，半成品预算只能持锁恢复，原intent恢复零第二POST。
- 超长或输入漂移必须在所有新POST前整批拒绝。

### Task 1: Pure execution budgets and requests

**Files:** Create planning/scene_execution.py, tests/unit/test_scene_execution.py; modify planning/scene_clip_continuation.py.
**Interfaces:** derive_scene_execution_clips(plan,timeline,*,mode), build_scene_execution_budget(...), validate_scene_execution_budget(...,expected); optional execution keyword in request/mapping consumers.

- [x] 首先新增320/321、三scene463、321拒绝RED并bootstrap执行。
- [x] 实现精确预算、完整覆盖/整数校验、segmented逐字段兼容；请求保留原语义首clip全局seed索引。
- [x] 预算与原continuation定向GREEN；记录日志。

### Task 2: Explicit configuration, prompt and rendering identity

**Files:** config.py; planning/scene_video_prompts.py, scene_revision.py; runtime/scene_video_prompt_records.py; associated unit tests.
**Interfaces:** 精确旧/segmented/whole配置；schema2提示绑定纯execution摘要；schema3 rendering身份；source snapshot可带scene_execution。

- [x] RED覆盖四分支、whole要求advisory、非法证据路径/profile、prompt缺行/摘要变化、mode失效。
- [x] 实现无环prompt绑定和schema3身份；保留旧schema原行为。
- [x] config/prompts/revision定向GREEN。

### Task 3: Admission evidence and frozen execution records

**Files:** runtime/scene_execution_records.py, production_inputs.py, production_scene_revision.py; tests/unit/test_scene_execution_records.py and production inputs tests.
**Interfaces:** load_whole_scene_evidence(path,*,reader); load_scene_execution(frozen,plan,timeline,*,reader); ensure_scene_execution(...,lock); frozen whole_scene_evidence/whole_scene_evidence_closure roles.

- [x] RED覆盖真实证据读取、完整闭包、漂移/缺项/伪造拒绝、冻结role、只读缺预算拒绝。
- [x] 核验真实VCO-05 artifact、PNG、resources、模型/工作流与目录库存；冻结原字节/closure，持锁exclusive+fsync+rename预算。
- [x] 定向GREEN且独立只读核对真实输入；不执行归档runner。

### Task 4: Production consumers and revision recovery

**Files:** 设计消费者表中的runtime与planning/scene_media.py；whole flow/recovery CPU集成测试。
**Interfaces:** context.execution保留独立Artifact；显式inputs/complete为schema3并传递预算；source revision snapshot/guard使用源execution。

- [x] RED覆盖whole完整链及模式切换、只读状态、intent恢复、超长批拒绝。
- [x] 所有clip/映射/观察/超分/合成/祖先/恢复消费者接入同一预算，保留原plan SHA。
- [x] CPU真实FFmpeg媒体320帧与多scene完整贯通、崩溃恢复GREEN；网络/模型/SMTP用替身阻断。

### Task 5: Verification, operations and actual acceptance

**Files:** VCO-07-verification.md, VCO-07-operations.md, board completion evidence; successor preparation only after actual completion.

- [x] 按设计core/flow及13个compat文件分批串行检查并记录实际日志。
- [x] 独立代码审查并修复实际问题；不运行全库。
- [ ] 准备确切新修订及可审阅执行命令；真实执行、观察和发布按现有授权与事实分别推进。
- [ ] 只有全部真实验收成立才COMPLETED；否则保留实际进度与缺口，不预备VCO-08。

## Ledger

- [x] 网络上下文RED0278bfcb准确失败于worker缺少调用方已认证作用域；仅copy_context运行原work，10项有限HTTP/作用域GREEN4ef97b90退出0（3.32秒）。原guard/byte/inventory/deadline/cancellation均保留，没有改网络600/模型7200等预算。
- [x] 在0模型intent/HTTP/GPU租约时中止第二个CPU调用02de6cd/97fb，native35487退出1无产品result；b851dfd6/7e6e7f6f审计证明原3011/1005/262软件未变，原RunLock按死PID7840归档锁。新265库存554913ebee1443ca89971125e0930653和audit dfc0ad370eaf49f993519d95bc4bfb3b由64778835准备退出0；按当前持续完成授权继续普通入口，不重复询问。

- [x] 本轮持续完成授权下提前核对健康链：2387fa/da608aec CPU回归准确证明快速健康响应因完整模型准入日志耗尽2秒。为避免已知后续启动失败，agent在0模型intent/HTTP/GPU租约时中止484f/d9 CPU调用；native28132退出1无产品result，fd01dfa/8f8970cc审计核验原3011文件/1005状态/259软件不变，原RunLock按死PID29268证据归档其锁，未手动删除原始状态。
- Ruling: 健康GET原始证据使用相同production目录下真实run锁守卫，模型完整字节/inventory准入继续由原调用及每次提交守卫承担；网络2秒/服务300/模型7200均不增加。原因是服务身份探测不能因无关模型准入重复工作拒绝快速健康响应；若判断错误，风险是健康日志缺少模型闭包复核，但它不提交模型，提交路径的完整核验保留。
- [x] 健康/whole服务/通用服务合计23 passed/1.77秒，f6f3da9edb69478fa67f8374bebdb520退出0，含慢网络仍拒绝和锁丢失拒写。新prepare-health-recovery.py审计4e945f54d52f46f29af098dce395114e退出0，262库存17fde906ecf84fcfa716b3d5deb4dd6e/new audit1bba71bff899498d82490a0c35422022；沿用现有post-directory operator按持续授权继续，不重建修订/重跑旧全矩阵。

- 2026-10-30 20:03实际新失败：本次702d6b桌面准入已通过并启动自有Comfy PID43744；其CLI因`--user-directory`目标run/comfy/user不存在退出2（stderr services/11cca27c4d5c40e8a8695d7dede082b9.stderr）。当前仍0模型intent/POST/技术输出，无OOM证据；worker33404正在失败收尾，不追加advance、不在退出前修改256库存覆盖的源码/操作助手。
- [x] 服务目录缺失的CPU回归RED：397b24137e2645ed8cd0eb3aaa9e5ca3，定向新2项均准确失败于资源启动前目录未准备；使用真实run目录/RunLock/manifest，外部服务和GPU边界替身，无模型调用。该测试文件此前不在256库存中，当前Comfy已退出，无GPU推理并行。
- [x] operator80152已退出1、原3011文件后检不变，20:18释放run/GPU锁。原production_scene_clips.py准确33779字节已核对256库存后归档0f4756155cf8447fa6973ea76ef82a4f.py.bin（SHA256 42af26a0ad695445faef3f69b912a3be1c07c8cd29af9600cafa39a70372e3e0）；source增加持锁四目录准备。完整服务9passed/0.43秒，53df470401a6468fa056a3bf7172f77c退出0。
- [x] 准备助手实际持锁建立目标目录，冻结原服务完整命令追加--help退出0，无服务/模型调用。10c19b1dd8154c62946bd98c1dcc1cd3最终审计退出0：原source3011/保留1005/当前epoch/桌面准入均匹配，另存259库存453818f3a24c474ea1e8e25ee9ff70ac和audit f55864933bae4558abdbee5ced7f1332。首次46d891f假定failed服务记录仍有args而失败，改从startup原日志取参且逐项匹配冻结配置后通过；保留记录。
- [ ] 服务失败后明确授权到达才运行已准备的advance-production-after-directory.py一次；旧253/256库存和旧operator不再使用。已刷新handoff并IN_PROGRESS -> BLOCKED，不以CPU CLI成功冒充服务/推理/观看/交付通过，不准备VCO-08。

- 2026-10-30 GPU阻塞续接计划：用户“已关闭，剩余未关闭的不用关，现在继续吧”明确允许当前余下桌面程序并继续同一目标。使用现有brainstorming快速明确任务分支、TDD与inline执行技能；不重做既有设计/检查。只读GPU样本95d7204d38a747749dd2ddc5b0a1fa46核实4个准确路径（PyCharm CEF/AweSun/M365Copilot/WeGame browser），Chrome/媒体播放器原阻塞已不在样本中。
- Ruling: 通过gpu_desktop.desktop_approval_scope(run, exact_paths, authorization)给这4个已观察桌面可执行文件本调用例外，并记录实际授权；使用ContextVar在退出后恢复默认，不把例外写进永久全局名单。只接受准确绝对.exe路径，不用名称/通配符放行，纯C/未知身份/其他run继续阻止。用户已明确选择保留应用，故不再次询问；若判错，风险是允许非用户预期的同路径桌面进程，本次作用域和审计记录限制其范围。
- [x] 新桌面作用域6项回归RED：5d0db8dfe8164931aa1cd4d8960a2ad6，6 failed/4 passed，准确缺少API；不涉及模型调用。
- [x] test_gpu_desktop.py及test_resources.py共23 passed，0.63秒，日志c487a6ca192840a797df50e95f99e2d4退出0。首GREEN6699bbe一例失败是测试外run目录名不合法，修正为合法生成run名后验证作用域隔离；不改产品边界。快速预检新增WPS准确路径，按用户保留应用授权一并记录，最终sample external_pids为空。
- [x] 恢复审计7f9f1fd1eb1f4567b26b5177e4047fb7退出0：原253库存只gpu_desktop.py变化，原字节从已验证旧归档保留，新256库存69e8de39720f495f9211b0924f07aee0；原3011源文件/1005保留状态/当前已提交epoch完整匹配。新audit6a232ef82e684d62a3a2a1ddb2c46ba4，授权1779a04168024c9dbd825d72dc57ff68，单次operator为advance-production-after-gpu.py。0aed快速审计被新WPS进程拒绝，865f后续只读审计遇合法空归档文件；修正仅允许按已记录SHA核对空文件，均未调用模型，旧证据保留。
- [x] 记录BLOCKED -> READY -> IN_PROGRESS及实际授权，新普通推进已且仅启动一次，日志702d6b02528041f3b149166b2a8cd787/start35608f06c4ff4c429904810a32ec67ae；publish=False/automatic_retry=False。当前等待结果，不重跑已有core/兼容/whole，不准备VCO-08。

- 用户明确回复“同意，继续执行”后，已记录BLOCKED -> READY -> IN_PROGRESS及授权原文。准确新audit、253库存和零POST状态由新operator重新核验通过；修复后普通推进仅启动一次，日志130ced3e53a9461c9f13f07e5bf876d1，start c2276ff54bb44d198e74293fa6244598。publish=False，原请求/资源/失败停止限制不变，未重复任何既有软件检查或新建修订。当前等待原调用结果，不追加advance。

- 本轮收尾准备：恢复audit5d1bfb576ff1474db117757d12d8885f退出0，准确报告b02ddab7d18142f085b867b4623e1c10确认原3011文件/零模型intent与POST/253新库存。新operator已完成准备但未执行。按入口交接失败停止要求，已询问新的继续执行授权并保持停止；先刷新pause handoff，再将VCO-07 IN_PROGRESS -> BLOCKED，VCO-08不变。旧入口交接11607字节及失败时250软件文件原字节均已归档核对SHA。当前阻塞为待授权，不是尚未修复已知CPU故障，不得自动再调用旧或新advance。

- 本轮唯一真实advance 41cd4eed35de4a9b913201b8805d4ebb退出1：source_clips/TimeoutError continuity deadline expired，0真实POST、无epoch intent、原3011文件字节不变。Ruling: 初始epoch是源准入完成后的新本地事务，其300秒Reader应在完整source_context预检通过后才创建；不把耗时的whole准入预检计为已开始的epoch IO。不改分析入口共享300、媒体300、原模型intent7200或任何byte/inventory门槛。代价是epoch之前的准入耗时仍可能很长，不能据此宣称性能已解决。新增两个时钟回归RED1failed/1passed，最小改动后全文件16passed退出0（f813609722f343e0a1e09c6d9bfb655d）。真实执行按失败停止，不自动再advance；已准备253文件新库存和零POST部分状态的只读audit/新operator，保留旧失败软件250文件原字节archive，准确路径见verification/operations。

- 本轮软件门槛最终：定向最后一例`vco07-whole-lost-response-final-4ea944c44493454196d7e31dc5edaff3.log`退出0，1 passed，721.28秒（call 688.27秒），包括按clip恰好一次POST/原graph与client_id不变及缺预算只读拒绝、writer零提交且不补预算。whole六例由原268a6487批的前两项、本轮9f4d批的前三项及4ea944批最后一项逐项组成，不声称单批六例通过。规定core347、13兼容304和服务7保留原通过证据；本轮无产品源码变化。默认git diff --check退出0，日志3c971a1d83594b4fa732664fcb2443db。下一步只刷新库存、审计已有准确真实修订并单次advance；无真实GPU/观看/交付通过，不登记COMPLETED。

- 本轮四例批次9f4d3729be9e41c088027eeb5f00dca7退出1，3 passed / 1 failed，4471.41秒。Ruling: lost-response测试的全局POST数恒定期望错误：实际三个scene各一次，首scene仅原POST及GET恢复，后续普通推进合法启动其余scene。改为每clip恰好一次、原graph/client_id前缀不变、预算缺失段零新增POST；不改产品停止/恢复契约。若判断错误则会把重复提交误当合法新scene，因此使用冻结execution的准确clip集合逐项计数而非只放宽总数。最后用例复用既有flow的fixture证据接缝，避免重复证据认证掩盖事务验证耗时；records/whole观察门槛已有真实漂移覆盖，预算缺失拒绝保持真实。只继续这一个失败用例及尚未执行尾部，不重跑已通过三项或core/兼容。

- 2026-10-30本次续接：按用户明确要求恢复同一VCO-07，PAUSED -> IN_PROGRESS。Ruling: whole最终失败是新测试错误期待，既有delivery在缺完整最终观察时明确ProductionRefused/blocked，且已通过的media_recovery:402覆盖相同行为；只修正whole测试，并补充拒绝后零发布输出断言，生产门槛保持原值。若判断错误会错误解释公开接口状态，因此保留旧RED日志并验证后续真实CPU观察/交付/重放和完整六例；不重跑core/13兼容或重建真实修订。
- Ruling: 用户明确要求从失败点继续、不从头重做；本轮没有产品变更，故保留268a6487a1d44b86a54c7fe476881faf中whole前两项的完整通过证据，只运行失败的第三项及未执行的三个recovery。六例验收按这两批逐项汇总，绝不声称本轮单批六例通过。若发现产品或相关夹具再变化，再评估旧两项是否需要重验；代价是六例证据跨命令，必须保留准确身份与各批结果。

- 当前暂停交接：用户明确要下一个对话继续VCO-07，不是把范围交给VCO-08。已写pause交接并将本任务IN_PROGRESS -> PAUSED，VCO-08不变，不再继续测试或推理。最终whole全量268a6487a1d44b86a54c7fe476881faf已2 passed/1 failed、退出1（缺最终观察的delivery应blocked却测试期待awaiting）；后3恢复未运行。下一对话直接查这个失败，保留347 core/304兼容/7服务的已通过证据。准确续接路径、实际修订及软件库存刷新要求见docs/task-handoffs/VCO-07-handoff.md。

- 2026-10-30恢复：服务器重启后三个旧session不存在、无Python存活，且仅启动日志，没有退出证据；旧compat/whole/实际修订均不计通过。八个兼容集成按原顺序串行重跑，session80830，通过后同进程继续whole；本地修订原请求恢复session78258，无模型/发布。不得手工删除旧锁或覆盖现场。
- 已核验日志：八个core及contracts/service/transactions/verification扩展共12文件424 passed；审查修复单元78 passed；common失效修订集成1 passed；Windows暂存晋升保护22 passed，均退出0。三项Important和额外句柄问题均有RED/GREEN，详见verification；无须重复独立审查修复结果。
- 后续兼容RED：源片26、提示7、修订31项均通过；第四文件管线恢复3 passed/1 failed，日志c7516ffa975642739771923fafc400ed。定位为VCO-07新增的upscale服务stage设置把可替换的_OwnedService构造工厂用于isinstance类型参数，公开管线测试替换为可调用工厂后TypeError。只改为检查返回服务是否支持stage属性，保留真实服务upscale资源分类及ensure/close协议；不改测试断言。重跑该完整文件和whole服务单元；原八文件串行在首失败处正常停止，后四文件及whole尚未执行。当前产品源码库存因这一行修复已变化，真实执行前必须重新记录软件身份，不可直接使用旧审计的software Artifact。
- 第二次管线回归越过上述产品故障和完整发布恢复后，在最后continuation继承检查RED：测试的monkeypatch.undo把微型模型验证接缝提前撤销，生产验证器正确拒绝fixture路径。仅分离测试公开故障注入与fixture替换生命周期，保留全部断言；先以已完成CPU夹具重跑continuation子流程（session30584），通过后重跑完整文件，不重新执行前三个已通过文件，不跑全库。
- 性能定位：上述独立诊断30584运行约50分钟仍在OfflineUpscale构造器的源片只读核验，Windows计数显示约千万次读取、数亿路径操作持续增长，无真实模型调用。定位为夹具独立调用缺少生产协调器已有revision_scope，反复重建相同修订证明。仅在tests/scene_media_helpers.py的这一次源片读取加入既有revision_scope；命中仍逐项检查完整bytes/inventory，不增加跨调用缓存，不修改生产reader或模型路径验证。已核对PID30216的名称、开始时间和CPU归属后停止该任务自有诊断进程，保留日志退出-1，不计通过。新session继续从已有CPU目标的未开始超分部分验证，精确脚本check-persisted-upscale-tail.py及日志见verification；正式完整文件仍待GREEN。
- 最新状态：诊断停止前8个重做帧及18帧完整索引已提交；尾部精确重放69044退出0，210.11秒，禁止服务/网络，验证8次原始POST、10帧继承和源/目标内容不变。正式最终串行session70755：whole服务单元7 passed（60ce9bd6803e46fd91e30398e277b062）；第四兼容文件pipeline recovery正在运行（dfa8fa30ac9f41de8d1b9cfcc690f7b9），通过后依次continuity_recovery/media_flow/media_recovery/composition_recovery，每文件独立bootstrap/日志；然后whole flow/recovery。前三个集成文件26/7/31项已通过，不重跑。模型推理仍未开始；产品代码仅upscale工厂修复这一处变化，需以refresh-production-software.py另存新库存并重新只读审计准确真实目标后才启动。
- 最新完成：session70755中正式pipeline recovery全文件4 passed（3596.25秒）、continuity recovery22 passed，均退出0。当前media_flow日志2e3f82cfd0904ec38a03cf8611dea95d；随后仍按原序media_recovery/composition_recovery/whole。完整管线已证明两次问题修复和夹具作用域调整后所有原断言GREEN，局部尾部诊断不再作为完整文件的替代。
- 最新兼容边界：media_flow3 passed退出0。media_recovery首例因装饰器在原有准备拒绝前读取不存在config.raw而AttributeError，串行70755退出1。四个新分派回归RED后，仅在raw不可用时回读冻结snapshot；显式mode和null不可隐藏，缺省交回原准备拒绝。新回归/既有null/六个公共拒绝11 passed，05a94633bdfa49389f72684389143f7c。已启动新最终串行：重跑规定八个core（分派模块改动的必要覆盖），然后剩余media_recovery、composition_recovery、whole；不重跑已通过的前六个集成，不跑全库。最终软件库存允许且必须记录已验证的upscale工厂与scene_execution_records分派这两个产品文件变动。
- 最新最终串行session56503：规定八个core 347 passed、153.52秒、退出0，日志0ee51b8e6eaf45a390a17a042e1d010d。正在完整media_recovery（43e0845f03994fd8992ff9d9065d319c）；之后composition_recovery与whole。旧424项实际为12文件扩展批次，已按原命令参数纠正标签，不与347相加充作不同用例数。
- session56503继续：media_recovery全文件61 passed、1046.36秒、退出0；当前最后规定兼容文件composition_recovery（5849094151c94e3b984eaa39f324723f），通过后同进程whole flow/recovery。至此前12个规定兼容文件都有退出0日志，不重复执行。
- 规定兼容全部完成：composition_recovery8 passed、577.90秒、退出0；13文件矩阵共304项逐文件退出0，无缺依赖skip。session56503当前运行whole flow/recovery（1f5d2340940b490aa7f564cf687fb1f8），仍不计通过。下一步仅在该批通过后刷新两处已验证产品文件的当前软件库存、重新审计准确真实目标，再执行已授权的单次普通advance。
- whole夹具同类性能边界：旧whole最终批在首例直接scene_context等单次读取缺少协调器revision_scope，反复构建相同证明，约33分钟CPU仍未开始源片写入。核对PID8584与日志创建时间及CPU归属后停止，退出-1不计通过；仅给whole_setup准备步骤及独立scene_context/acceptance/delivery读取分别加入既有revision_scope，每个独立调用仍各自新建，所有byte/inventory漂移检查和断言不变，未改生产模块。新全量6例session8872，日志268a6487a1d44b86a54c7fe476881faf。原13兼容和347core都已完整通过，不重复。操作audit脚本也仅在其单次只读操作内复用revision_scope，并在刷新后对照首次3011文件源基线，禁止重新签署漂移。
- Final: Ruling: 审查不判断真实观看/发布、当前产品操作库存、包络外能力及全库竞态——分别由实际验收、独立软件库存、有限能力声明和VCO-08承担，不以fixture补证；若边界判断错误则不能获得真实生产准入。
- Final: minor：verification过期模块说明已随句柄生命周期修复同步更正；malformed media配置错误类型已单独RED/GREEN，无待延期minor。

- 2026-10-30：用户“完成VCO-07”是明确开始请求；已完整读取主设计/交接，READY -> IN_PROGRESS。
- Ruling: 原设计明确要求当前工作区且.git只读，跳过技能默认worktree/commit脚本，使用本文件ledger及D:/VideoSi命令日志保留证据；代价是无独立git提交边界，审查必须基于本轮文件库存。
- Pre-flight: Task1 clips -> Task2 prompt canonical_digest -> Task3 rendering/budget，顺序无环；Task4 source revision必须保留其源execution，不能传目标execution。
- Task 1: 纯预算/请求123项GREEN，独立pure review通过；详见Task1报告。
- Task 2: 四配置分支/schema2提示/schema3身份和源snapshot已接入；初版186项GREEN。真实集成又发现mandatory advisory被当common内容：新schema3 planning摘要移除admission策略，跨新旧mode仅在有准确target_config时比较同一规范化common；旧身份字节保持原算法。139项修订回归GREEN。
- Task 3: 首轮44项frozen/records + scope/memo分项GREEN，真实历史闭包18,453文件/六inventory核验；模型/软件从未执行。writer与reader仅在各自validation_session内复用已认证语义，命中仍完整核对bytes/目录，独立调用重建。Task3报告及后续memo日志见verification。
- Task 4: execution/schema3已接入source/media/revision/origin/guard；新增whole失败全局停止、原始deadline保留、whole自有GPU租约/资源采样。RED/GREEN已覆盖后两项；whole集成与规定兼容仍在运行，未登记完成。
- Ruling: VCO-04 complete.json继续是不可改写的历史源片/观看聚合，当前诊断另由require_scene_clip_acceptance检查；whole测试不能要求诊断pending时删除/重写历史complete marker。代价是调用者必须使用当前facade而非只看marker；真实生产仍受原VCO-04门槛约束。
- Ruling: 既有media race单元测试mock了已不被使用的public reader，导致在语义接缝前KeyError；只将mock指向现有base reader，保留全部篡改拒绝结果。代价是该测试接缝随真实reader接口演进，但不削弱产品验证。
- 历史进程：旧compat13597和whole10618因重复实模型哈希成本中断，不计通过；core27446已424 passed；重启前compat35249/whole31748/修订98255仅启动日志且进程消失，不计通过。当前compat80830按八文件串行后继续whole；第一文件26项通过（日志986166a6ed3d4d7a88134058686244c6），第二提示文件正在运行（日志ec4dd1d3723f4eeea65fa319bf6688dd）。实际修订原草稿78258已revision_ready但不用于推理，新版准备34119已创建准确ready/budget后在操作助手自检漏root参数退出1；独立只读审计45709退出0，确认目标 `20261029-202326-3adf41844095`、247份软件身份、3011份原run文件基线和完整463帧预算。准确报告/下一执行命令见operations；不得重跑修订或把助手退出1计通过。此前失败/旧模块版本75436已退出1，不计通过。
- 实际准备：已读取原463帧案例并实际查看三张原图，创建operation-side配置/提示/请求和软件库存。旧草稿将字体路径改为冻结副本，导致语义common失效，因此保留但不执行；v2保留原配置路径并验证字体SHA，新的失效清单确认common/plan/三图及选择可复用，旧视频/观看/超分全部不复用。准确新版路径和日志见operations；尚无模型请求、观看或发布。
