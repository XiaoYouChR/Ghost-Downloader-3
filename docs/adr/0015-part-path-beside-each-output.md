# 未完成的数据放在最终路径旁的 `{p}.ghd`

Step 原地写入它的最终路径 `p`（Placeholder 本身），`p` 的未完成数据放在同级的 `{p}.ghd`：
只需进度记录时是文件（HTTP、FTP），还有中间文件时是文件夹（合并前的音视频、m3u8 分片），同一个 Task 中两者不同时出现。
基类只知道这一条规则：创建 Placeholder 时删除旁边残留的 `{p}.ghd`；Task 完成后删除成品的 `{p}.ghd`（进度记录由写它的 pack 删除）；Task 被移除时删除未完成 Step 的输出和全部 `{p}.ghd`；"删除文件"只决定已完成的成品。
记录格式仍是 pack 知识。

## Considered Options

- **所有未完成数据放进 `outputFolder/.ghd/{taskId}/`**：需要"最终路径 → Part Folder 路径"映射、完成时替换 Placeholder、
  旧版文件迁移三套代码；中间 Step 的路径已在 Part Folder 内，映射出现两种含义，暂停后继续因此失败；
  Windows 上 `.ghd` 不隐藏，用户只看到一个 taskId；BitTorrent、eD2k 仍是例外。
- **单文件和多步骤各用一种位置、各有一套删除逻辑**：`{p}.ghd` 是同一个路径，`deletePath` 同时处理文件和文件夹，不需要两套。

## Consequences

- 单文件 HTTP、FTP 的布局与 4.3 相同，旧版暂停的 Task 无需迁移。
- BitTorrent、eD2k 原地写入不再是例外。
- 下载中断后，`p` 可能是大小正确但内容不全的文件；旁边的 `{p}.ghd` 表示未完成。
- 可能不产出文件的 Step（没有字幕等）自己释放它的 Placeholder；基类不按文件大小猜测，0 字节的成品是合法的。
