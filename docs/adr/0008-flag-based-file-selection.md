# 文件选择用标志过滤，不增删 Step

多文件任务（HuggingFace 仓库、FTP 目录、种子、YouTube 播放列表、B 站多 P）曾有五套
选择实现，其中基类的做法是"取消勾选就删掉对应 Step，重新勾选再重建"。我们改为唯一
语义：**Step 在解析/发现时全量创建、永不因选择而删除，`selected` 标志决定状态聚合、
进度快照与 `pendingSteps()` 是否跳过它**（`Task._isStepSelected`）。

选择增删模型的原因：

1. **进度不丢**。删 Step 再由 `fromFile` 重建会把 `downloadedBytes` 断点清零；
   标志翻转天然保留部分下载。
2. **运行时改选变得安全**。增删正在被 run 循环迭代的 `steps` 列表有生命周期风险；
   翻标志没有。这是"任意状态下都能改选择"（`taskService.applySelection`）的地基。
3. **一个文件可对应多个 Step**。YouTube 一个视频是 extract/video/audio/merge 四步一组，
   B 站一个分 P 是 3~4 步，`fromFile` 返回单个 Step 的协议装不下；标志过滤按
   `step.fileIndex` 关联，组大小无关紧要。

代价与后果：

- 未选中文件的 Step 常驻 `steps` 列表并被序列化（体积可忽略）。
- 状态聚合的四个入口（`updateStatus`/`setStatus`/`pendingSteps`/`currentSnapshot`）
  必须全部过滤未选中 Step——漏掉 `updateStatus` 会导致任务永远无法完成。
- Step 构建是 pack 私有职责（解析器或 `__post_init__` 旧存档补建），基类不再有
  `stepType`/`fromFile` 协议。
- BT 例外：选择映射为 libtorrent 文件优先级（单 Step，无 `fileIndex`），覆盖
  `setSelection` 自治。
- 多 P/播放列表的输出文件名跟"总数 > 1"走而非"选中数"，保证改选不引发重命名。
