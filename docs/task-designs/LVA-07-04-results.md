# LVA-07-04 implementation results

已交付隔离 Wrapper profile、同一比较组的control/fast图、单专家私有静态覆盖/双侧准入、三个组合节点、owned worker、原ID恢复和标准媒体接口。范围为CPU/离线实现；完整14B应用、GPU采样、真实质量、1080P收益及生产接入均未验证、未执行。

代码入口：[benchmark_wan_wrapper.py](../../scripts/benchmark_wan_wrapper.py)、[observe_wan_wrapper_comfy.py](../../scripts/observe_wan_wrapper_comfy.py)。设计/数值与schema合同分别为 LVA-07-04-design.md、LVA-07-04-contract.json、LVA-07-04-node-contract.json。完整实际证据索引在 LVA-07-04-results.json。

验收覆盖：

1. 固定两套mode profile，control零LoRA；共同comparison关联不同profile SHA，fast只能消费对应control接受和本epoch完整pair。固定40/4步sigmas、15/25与2/2切片、768×432/93帧/16fps；整数time步与原生浮点不严格等价。
2. 真实固定函数体CPU fixture验证只读mmap来源不写入、仅静态目标私有clone、两次reload与meta恢复不累加、真实CustomLinear rank64/alpha/scale forward、真实parser对象保留、异常不发布pair及单owner。原256MiB pair helper、repair/policy均未改；2959/290完整来源政策机制保留，未把小fixture升级为完整14B准入。
3. 合成93帧768×432媒体的完整PTS/尺寸/FPS/黑帧/末PNG通过。finite在uint8前检查，固定H264参数；worker晋升证明和原prompt/profile/graph/epoch绑定，完成原媒体0HTTP/0producer，重启清进程证明后只重新验真一次。合成样本不代表模型画质。
4. unknown原ID不重POST、UUID/冲突接受、一次性入队、归档已完成history但未落最终记录的离线收集、Wrapper父片接受/尾帧/同mode绑定均有定向覆盖。节点准备顺序验证T5释放后才进入VAE；sampler保留原首个LATENT，实际调用数不符会拒绝并释放owner。
5. 实际CPU worker当前13类HTTP schema通过：PID41804，start identity134395049390251801，epoch3c9ac4bf-a073-4a58-92df-3d8219a817c6，峰值RSS1009172480 bytes，31.875s，合作退出0、8297关闭。此前PID18200的初版注册也成功；前项07-03两次exit -1仍为历史强退，不改写成graceful。CUDA构建torch被CPU模式导入，未使用GPU、未提交生成或读取大模型payload。

软件身份清单 LVA-07-04-software.json：固定Comfy树逐blob与2c75提交比较；独立已安装runtime的当前内容快照，总49797文件/4668099441 bytes。首次完整清单生成230.891s，只做一次。服务启动时只核对bootstrap/native binaries/core源码及实际导入模块，持deny-write/delete lease，避免每次扫描全部49797文件；不在denoise/逐帧路径增加源或模型全局校验。完整模型首次授权准入时才对原六文件哈希一次并保留lease。

资源：CPU4GiB私有commit硬限/RSS停止阈值、512MiB新fixture磁盘预留；未来完整模型要求可用RAM26GiB、空闲VRAM22GiB、私有commit8GiB/RSS24GiB/GPU allocator20GiB且单Wan owner。主机当前可用容量仍须后项重新只读观察，不凭历史值放行；完整模型实测峰值为null。

最终审查提出九项关键/重要缺口，处理与测试见 [review](LVA-07-04-review.md)。没有二次复审或质量接受声明。完整pytest仅运行相关新测试与四组既有邻居，遵守AGENTS.md不做无关全库、旧payload矩阵或历史GPU重跑。

工程裁决：保留隔离分支及原工作区WIP；原生workflow测试固定的是Windows CRLF字节，在隔离checkout仅复制原文件做基线，不交付native workflow修改。编码末PNG使用stdlib实现、资源观察复用既有Windows API，无新依赖。Wrapper父片需要独立适配原ID/接受语义，不能调用强制native布局的helper。软件全清单只封存一次，运行时按实际执行内容保护；若判断有误，后续源身份或恢复测试/准入将停止，不能绕过后项真实门槛。

最终交付仍不授权LVA-07-05，亦不恢复暂停生产、付费调用或推送/合并共享分支。

最终验证：77项相关pytest通过（37新、40既有邻居），10项固定函数体CPU fixture通过；原工作区最终路径绑定冒烟root为 `E:/VideoAI/scratch/benchmarks/LVA-07-04-delivered-profile-final`。交付34个任务文件，原v2分支/WIP保留；05只准备READY。模型固定pins独立于可变manifest，双改descriptor/profile也不能更换原六文件。
