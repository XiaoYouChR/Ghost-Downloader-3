# Name Conflict 以磁盘为准，Placeholder 在加入时占住

`TaskService.add` 让 Task 用 `O_EXCL` 为它将产出的每个最终路径（成品和 Side File）创建 Placeholder，失败即 Name Conflict；
路径是否被占用只看磁盘，Task Record 只用来识别占用者是不是未完成的 Task。Task 从加入到被移除一直持有 Placeholder，Task Run 不改 Name。
这样「路径是否被占用」只有一个事实来源，#781（文件已删仍加 `(1)`）和 #658（同批任务互相覆盖）由同一条规则解决，
Windows/macOS 大小写不敏感和多实例并发也由文件系统原子保证。

## Considered Options

- **查 store 中其他 Task 的 `outputPath` + 磁盘**（`2652bb6` 至本 ADR 前的做法）：记录与磁盘两个事实来源，
  文件被删后记录仍占着路径，即 #781；字符串比较对大小写不敏感的文件系统失效。
- **各 pack 在 Task Run 中自己占位**（`e64c411`，后在 `d65b373` 删除）：各 pack 创建文件的时机不统一，
  WAITING 与链式任务合并前存在窗口期，同名任务看不到占用。
- **Task 声明 `claimedPaths()` 由 TaskService 逐个查**：yt-dlp 在提取前不知道格式，接口近乎等于实现，浅模块。

## Consequences

- 排队中的 Task 在 Output Folder 中表现为 0 字节文件或空文件夹。
- 新 Task 取得某路径时，占用该路径的旧 Task Record 被 Replace（只移除记录）。
- 覆盖经注入的 `deleteRecoverably`（桌面为 `QFile.moveToTrash`）移到回收站；移不了则退回保留两者，不静默永久删除。
- goed2kd 放行目标路径上的 0 字节文件以接管 Placeholder；协议版本不变，以兼容安装 latest goed2kd 的旧版 GD。
