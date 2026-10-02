# Binary Runtime 安装不是 Task，只覆盖、只删自己的文件

Binary Runtime 的安装是 `BinaryRuntime.install(version, onProgress)` 里的一段直线代码：`fetchFile` 下载、`matchSha256` 校验、`installArchive` 覆盖解压。
不套 Task，也不复用 http_pack 的 `HttpTaskStep`。安装从不进 TaskService、不持久化、不可暂停、对用户不可见，不符合 Task 的定义；
为套用 Task 而付出的必填字段、手写 `stepIndex`、手动 `setStatus(RUNNING)`、速度与 fileSize 维护，全部换不来能力。
Install Folder 由用户选定、可能是共用目录，所以安装只覆盖、卸载只删除 `installedPaths()` 声明的路径，从不清空文件夹。

## Considered Options

- **InstallTask + Step**（37b3b75 至本 ADR 前）：37b3b75 拆掉了 parse 路由，留下了 Task 外壳；通用 `InstallStep` 的清空文件夹、拆外层目录、rglob 找可执行文件，四个 Runtime 都用不上。
- **安装下载复用 `HttpTaskStep`**：多连接、断点续传可加速国内直连，但它依赖 Task 外壳（`outputPath`、`.ghd`、Placeholder）并让引擎层依赖 http_pack。安装包只有 4～13 MB，超时由 `fetchFile` 自己补齐。
- **清空 Install Folder 时移到回收站**：保住了误放的用户文件，但回收站里零散 N 项、移不了时状态说不清；各 Runtime 包都是平铺的固定文件，覆盖解压即完整替换，不需要清空。

## Consequences

- 安装不受 Download Speed Limit 约束，也不进 Speed Meter。
- `RuntimeStatus.progress` 只表示主安装包的下载百分比：0 为准备、1～99 为下载、100 为安装。
- 安装和卸载一律先改名再替换/删除，运行中的程序也能更新：原地覆盖时 macOS 会杀掉被覆盖的程序，Linux 写入失败，Windows 不能覆盖或删除但三平台都允许改名。
  新文件先写到同目录的临时文件，旧文件改名为 `<名>.<随机>.old` 再换入；删不掉的 `.old` 在下次安装或卸载时清理。
- 第三方包布局变了（例如多出外层目录）时，安装后 `isAppManaged()` 为假，安装以「安装后未找到」失败，需要在 pack 里改 `root`。
