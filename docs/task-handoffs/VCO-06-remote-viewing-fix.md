# VCO-06 远程观看记录修复交付

2026-10-29。用户远控看完整段后遇到“播放结束，完整覆盖尚未成立，可从头重看”。该提示表示原页的严格逐帧记录条件未成立，不能据此断言人没有看完或需要打开实体显示器。本轮没有取得用户实际导出的播放草稿，具体缺帧和事件原因仍未知。

## 使用入口

[更新后的同址修复页](D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261028-acquire-62d31ee3276941ecb65e35e23e4db250/observe-12-save-fixed.html)

刷新此修复页。原修复页已缓存的字段按相同collection、视频和原图身份恢复；原始旧页没有缓存的填写不能自动恢复。旧版本未保存native ended和played时间范围，因此不能事后补写为远程完整观看证明；新版需要一次实际播放取得这些数据。

若逐帧回调不齐，新版显示真实回调数量、缺失帧编号及事件。实际完整时间范围成立且本人确实看清整段时，勾选“我通过远程画面以原速看清了整段的开始、过程和结尾”，再保存填写结果。程序不代勾，缺帧不补写；其余颜色、结构、动作和光照选择沿用原答案。开始新一轮播放仅重置属于上一轮的本人观看确认。条件不齐仍可保存原答案草稿和完整诊断；下载之外保留完整JSON复制出口。

## 修复与证据边界

- 原49帧严格v1、冻结Python/CLI及validator原字节不变。结束事件立即记录真实结束时间和实际经过时间；最多1000ms只等待真实晚回调，不延长播放计时。旧结束任务、旧加载/播放任务和异常不能关闭或重置新会话。
- 结束后切页面或改速等操作不追记成已结束观看的中断。启动期间禁用重复启动，并识别已恢复播放时排队到达的pause通知。
- 新增独立 `natural_material_observation_remote_v2` 和 `human_remote_video`。原 `playback.completed=false`、真实回调数组与事件逐项保留。独立时间范围、原速原生时长、ended、足够实际时间、可见性、无真实中断及人类明确声明一起验证；不把声明当作机器独立证明。
- `stalled` 是网络取流通知，已有缓冲仍可能连续播放。严格v1继续拒绝；独立remote-v2原样留存该事件，仅不将其等同于实际暂停。waiting、pause、seek、error、播放期间隐藏、非原速或时间不足仍拒绝。
- 新intake核验冻结collection、真实生成事务、原图/原片身份、生成完成后的实际观看时间及development split。只在独立 `remote-observations/<case>/<raw-sha>.json` 保存所验证的原字节，不混写到旧 `observations`。
- 旧冻结observe/status明确不接受/消费v2。未来资格流程需显式支持独立方法及其限制；本轮没有刷新冻结库存、重写旧观察、创建实际人类标签或升级任何profile/candidate/production状态。

新增入口（经bootstrap）：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-real-remote-observation'
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/experiments/vco06_remote_observe.py',
 '--root','D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261028-acquire-62d31ee3276941ecb65e35e23e4db250',
 '--observation','<实际用户导出的JSON绝对路径>')
exit $VideoAiExitCode
```

上面只是使用说明；本轮未用合成观察调用真实集合intake。

## 验证与保全

初始RED复现晚于100ms的真实尾帧被丢弃、旧ended结算关闭新观看及无具体诊断；remote-v2模块/入口当时尚不存在，初始37失败/7通过/7错误。新增复现结束后事件污染、跨素材异步开始、旧play异常和取流通知误判，再逐项修复。只读独立审查指出3个P2，修复复核后无剩余P1/P2。

最终串行运行下列3文件，**88 passed in 1.61s，exit0**：

```text
tests/unit/test_vco06_remote_viewing.py
tests/unit/test_vco06_observer_saving.py
tests/unit/test_natural_acquisition_observation.py
```

最终日志：`D:/VideoSi/cache/video-ai/logs/vco06-remote-viewing-final-62a0ad5a3a7845fcab51e7e070b76259.log`。

Node执行真实页面JavaScript，但事件/时钟为合成测试，不能计作实际观看。另试独立profile的原生headless Edge技术检查，因受限环境GPU进程退出而出现 `Target crashed`，退出1；未取得原生浏览器通过结果，未据此推断用户远控浏览器情况。日志保留在 `D:/VideoSi/cache/video-ai/temp/vco06-remote-browser-smoke-3c9872150a03433692a1cd7bf6b6542c/edge.stderr.log`。测试浏览器已停止，没有操作用户现有浏览器。未发模型/推理请求、安装依赖、运行全库或写Git；全库仍留VCO-08。

部署前已复核整个collection和4份冻结软件，复核12个development媒体/参考身份，保存旧修复页及旧receipt原字节归档，并在同一URL发布。新旧嵌入DATA完全相同，localStorage命名空间保持不变；原 `observe-12.html` 和collection不变。

- 旧修复页SHA：`fac11270be719c80dde353de48fad75689c11a3b120dee81a01ebb38a08319b4`。
- 新修复页SHA：`aea9d3dbfe6b8982b53a632058179db249f1b70eba65f6331181629505c88692`。
- 旧页面/receipt归档：采集根 `observer-ui-history/before-remote-89ecbcceafa743429f5cc4c8d70add9e/`。
- 新修订收据：采集根 `observer-remote-viewing-fix.receipt.json`。
- 实际部署日志：`D:/VideoSi/cache/video-ai/logs/vco06-remote-viewing-deploy-a7c627f63f594f26ac709f6b8b78d5ba.log`，exit0。

VCO-06仍BLOCKED：没有本轮实际用户观察、自然资格profile、真实候选或改善验收通过。软件修复不能代替这些证据。
