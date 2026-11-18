# LVA-07-02 官方基模与img分支只读核对

2026-11-18。用户要求继续核对官方基模header和加载规则。本轮未下载完整模型、未读取tensor payload、未执行节点/推理或修改修复代码。

**结论：为解决290项缺失而下载官方BF16基模没有依据；官方基模同样没有这些目标。当前已审查Wrapper有显式排除规则，但采用它需要调整现有“全部输入都必须应用”的验收范围。已准备精确290项清单，保持关闭，尚未执行排除。**

## 官方来源与有界header

官方LoRA说明在固定revision `57adea585d1d21085e2dfc91ce3c7b646cdd9345` 指向 `lightx2v/Wan2.2-Official-Models`。按已公开文件commit `18634b66f04c2e564e550b2c6bd092c64f2ce5c6` 查询API，并只取每文件8字节长度和113504字节header。4个响应均为精确HTTP206/Content-Range，总模型头body **227024 bytes，约221.7KiB**；服务器若返回整文件200则collector拒绝读取。

| 官方文件 | 文件bytes（仅元数据） | 元数据SHA256 | header结构 |
| --- | ---: | --- | --- |
| `wan2.2_i2v_A14b_high_noise_lightx2v.safetensors` | 28577915880 | `766066ac462ccfc2ffec9bb62721732b42de4a8a68c5f9b39b2c8c46555ad315` | 1095 tensors，全部BF16，img key=0 |
| `wan2.2_i2v_A14b_low_noise_lightx2v.safetensors` | 28577915880 | `515bbb21a2008bf74107878bd748c9a6aafa9a733f1724a49ce7fde3001338f7` | 1095 tensors，全部BF16，img key=0 |

两份header SHA都是 `f40c5e3943554fa03cf2b873620e0d3293fcbfa89825d7c52b291ef6533cc67c`；这不表示两个模型payload相同。文件SHA来自官方API，未以完整下载重新验真。本机既有FP8 base的已匹配目标shape与对应官方BF16 header一致；dtype/量化和payload并非同一变量，未推断其数值相同。

官方固定来源：[模型API](https://huggingface.co/api/models/lightx2v/Wan2.2-Official-Models/revision/18634b66f04c2e564e550b2c6bd092c64f2ce5c6?blobs=true)、[LoRA说明](https://huggingface.co/lightx2v/Wan2.2-Distill-Loras/blob/57adea585d1d21085e2dfc91ce3c7b646cdd9345/README.md)。

## 参考图、源码与版本区别

固定官方参考图SHA `aecf199c8451c2272fb53f6a96854c12cd596297326f426a6d7bf4533c7383b8`、37227 bytes。两个WanVideoSetLoRAs节点79/80均mode0启用，并分别连接Sampler90/27；Low/High LoRA输入也实际连接，非仅放置未使用节点。

参考图的节点properties记录Wrapper commit **`998a69cc0acbec503001b8b0ce0a5d5404420e1e`**。本轮读取了该确切版本源码：`setlora`没有显式img过滤，委托外部Comfy解析器；当时Comfy版本和完整权重应用未得到固定验证。因此不能把参考图当作“这290项已经正确应用”或“当时明确排除290项”的证明。

我们此前已审查并修复的基线为 **`a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`**。它的 `WanVideoSetLoRAs.setlora` 明确执行：

```python
if not any('img' in k for k in model.model.diffusion_model.state_dict().keys()):
    lora_sd = {k: v for k, v in lora_sd.items() if 'img' not in k}
```

来源：[a743固定源码](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/a7439db30bed0c5b5fa437d77ae8a7bb220dfd00/nodes_model_loading.py#L777)、[参考图记录的998旧源码](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/998a69cc0acbec503001b8b0ce0a5d5404420e1e/nodes_model_loading.py#L658)。两版本都仅只读，没有为本轮切换或回退实现版本。

## 与290项逐一对账

| 专家 | 原始输入tensor | 本机base无目标 | 官方base无目标 | a743规则会排除 | 剩余适用输入 |
| --- | ---: | ---: | ---: | ---: | ---: |
| High | 1500 | 0 | 0 | 0 | 1500 |
| Low | 1749 | 290 | 290 | 290 | 1459 |

三组Low source key集合完全相等，不只是数量相同。290项是82 down、82 up、84 bias、42 diff，均为`k_img/v_img/norm_k_img/img_emb`相关输入。其余2959个输入对应的本机/官方目标shape差异为0。以上是header和真实标准化函数的映射证据，不是payload消费/应用或质量结果。

这说明此前“290项无目标”是正确的观测，但不能进一步认定本机一定选错了基模。下载官方High/Low约57.16GB也不能创造这些img层。

## 建议的范围调整（待确认，未启用）

精确机器可读提案为 [LVA-07-02-img-exclusion-proposal.json](LVA-07-02-img-exclusion-proposal.json)，`enabled=false` / `PROPOSED_NOT_ENABLED`。

- 保留本机既有base、原LoRA全文件和已交付修复。仅对固定Low LoRA SHA `8833bd4f…`、固定当前base身份且实际运行时也没有img目标的情况，允许清单中的**精确290项**标记为`declared_not_applicable`。
- 不启用泛化的“名字含img就丢弃”。额外一个未知/缺失目标、身份/shape改变、实际模型出现img层或清单变化，都拒绝整个pair。
- 其余High1500 + Low1459 = **2959个适用输入**仍须逐项证明实际consumed/applied，继续有限性、dtype、scale、重复和两专家原子性检查。输入tensor数不是patch数。
- 排除项只记“不适用”，绝不记为已应用；不物理改写LoRA，不放宽任何其他未加载权重，也不据此授权GPU/生产。

既有设计要求全量输入实际应用并要求未应用即停止；本提案改变了该验收语义。因此只读核对已完成，实际策略激活及后续实现须先有用户对这份精确范围调整的明确确认。本轮没有重新索取已获准的下载或独立修复授权。

## 证据与限制

结构化结果：[LVA-07-02-base-review.json](LVA-07-02-base-review.json)。原始API/README、workflow、两个官方header、Range响应记录、两版源码和对账在 `E:/VideoAI/scratch/benchmarks/LVA-07-02-base-review/`。collector `read_remote_headers.py` exit0，范围/字节符合；`mapping-comparison.json`记录精确集合比较。完整模型下载、tensor payload读取、依赖安装、GPU/服务、产品/修复代码修改和策略激活均0。

未证明历史官方运行时的所有权重消费、实际完整模型属性、BF16/FP8等价、视频质量或加速。没有重跑已通过的21项修复测试，因为本轮没有改实现；LVA-07-02仍BLOCKED，不准备后继。
