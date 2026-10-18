# 固定工作流模板

三份 API 图来自任务1的 workflow-baseline.json；provenance.json 记录旧来源路径、源文件 SHA256、提取模板 SHA256 和原 Wan 映射。各 *.mapping.json 为 schema_version=1，集中记录可替换输入、模型、节点类型及唯一输出。运行实例进入 runs/<id>/workflows，不能改写这些模板。

SDXL 与历史成功 PNG prompt 相等。Wan 保留完整30节点、两专家连接、40步/15步切换、euler/simple、CFG3.5、shift5、batch1，唯一输出108.images。超分来自已成功脚本的5节点 PyTorch RealESRGAN_x4plus 流程，先四倍模型超分，再 lanczos 缩至1920×1080；动态 image=<inputName> 与 filename_prefix=<prefix> 必须由实际帧信息替换。

图内原飞船/雕像提示词、旧图片名、旧输出前缀只是历史模板值，不能作为新片默认素材或内容。映射验证不提交 /prompt；远程 object_info 与具体运行输入替换属于后续任务。历史单镜头成功不表示迁移环境或多镜头成片通过。
