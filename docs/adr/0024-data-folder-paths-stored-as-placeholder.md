# Data Folder 内的路径以 `{data}` 占位符存储

Install Folder 等路径型配置项的默认值位于 Data Folder 内，但过去存成了带盘符的绝对路径。便携版换盘符、换父目录、换挂载点，或者"切换模式"复制数据后，这些路径全部失效，Binary Runtime 必须重装（#1016）。现在由 `PathSerializer` 在写盘时把 Data Folder 内的路径存成 `{data}/...`，读盘时再展开成绝对路径；Portable 模式和用户模式都是如此。内存中的值始终是绝对路径，调用方不用做任何改动。

## Considered Options

- **空值代表默认位置**：否决。用户自己选的、位于 Data Folder 内的路径仍会失效，"切换模式"的问题也修不了。
- **记下上次的 Data Folder，启动时按前缀批量替换**：否决。要多持久化一项状态，并且必须赶在 Pack 加载配置之前执行；对已中招的配置也没有用，因为它们没有"上次的 Data Folder"可以对比。
- **按相对 App Dir 的路径存储 Data Folder 外的同盘路径**：否决。同盘挪动 App Dir 时会算错。Data Folder 外的路径属于用户，应用不去猜。

## Consequences

- 读到一个不存在、但含有 `GhostDownloader/` 这一段的旧绝对路径时，如果把这一段之后的部分接到当前 Data Folder 下得到的路径存在，就改用这个新路径。这样升级前已经中招的配置可以自动修复。
- 分类自定义目录和 Task 记录中的路径不在范围内。
