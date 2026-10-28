# Task 加入失败由 `add` 的调用方处理，并退回 Task Draft

Output Folder 无法创建时，`TaskService.add` 把 `OSError` 转成 `TaskError` 抛出，不发信号；由应用内调用 `add` 的模块决定怎么恢复：Task Draft 留下失败的 Draft Item，Browser Service、aria2 RPC 和更新包下载把 Task 连同原因送进 Task Draft，CLI 在终端报错。
用户期望的是知道原因、换个目录重试，而不必重做已经做过的操作；只有调用方知道失败后该退回哪里，所以由调用方处理（#152）。

## Considered Options

- **TaskService 发广播信号，View 弹 InfoBar**：订阅者分不清是哪个调用方，只能丢掉 Task 再提示，草稿里粘贴、解析过的链接随之丢失。
- **浏览器扩展收到失败后放行，让浏览器自己下载**：不可行。扩展把下载交给桌面端之前已经取消了浏览器下载，交接失败无法退回。

## Consequences

- 新增 Task 加入入口时，必须处理 `TaskError`。
- 同步完成的操作失败时抛出 `TaskError`，由调用方处理；`edit` 这类要等 Task 停下才执行的操作，调用方届时已不在，改发 `editFailed` 信号。与 parse 的做法一致。
- 配置层不再创建目录；Default Folder 和 Recent Folders 不因文件夹暂时不存在而被改动。
