# Windows 的 Command Line Tool 是一个转发 exe

Windows 上 PATH 里只放 `{app}\bin`，里面只有一个 C 写的 console 程序 `ghd.exe`：找到上一级的 `Ghost-Downloader-3.exe`，
在命令行最前面插入 `ghd` 后原样转交命令行和 std 句柄，等它退出并返回它的退出码，不含任何其他逻辑。
这是 Git for Windows `cmd\git.exe` 的做法。macOS 和 Linux 用指向可执行文件的 symlink。

转发 exe 解决两件事：

- **PATH 污染**：App Dir 里的 libcrypto、libssl、Qt6*.dll 不能进入其他程序的 DLL 搜索路径；Git 以 OpenSSL 冲突为由拒绝了把 App Dir 放进 PATH。
- **主程序是 GUI 子系统**（`--windows-console-mode=attach`）：shell 不等 GUI 程序退出，也拿不到它的退出码，而退出码是 `ghd` 输出契约的一部分。
  转发 exe 是 console 程序，shell 等的是它。（尚待 Windows 实测确认）

## Considered Options

- **App Dir 直接进 PATH**：上面两件事都没解决，命令名也只能是 `Ghost-Downloader-3`。
- **把主程序复制或硬链接到 `bin\`**：Nuitka standalone 从 exe 所在目录加载 DLL，放进 `bin\` 无法启动；且仍是 GUI 子系统。
- **再用 Nuitka 编一个 console 版客户端**：要再带一份 Python 和 Qt 运行时。
- **`.cmd` shim**（VS Code 的 `bin\code.cmd`）：cmd.exe 的参数解析无法被可靠转义（BatBadBut，CVE-2024-24576），而 URL 里的 `&`、`%` 正是 `ghd` 的核心输入。
- **`.ps1` shim**：只在 PowerShell 里可用，受执行策略限制。
- **App Paths 注册表**：只有 ShellExecute 查它，cmd 和 PowerShell 不查。
- **并入 `updater.exe`，按 argv[0] 分派**：两个程序职责无关。

## Consequences

- Windows 构建多一步 MSVC 编译，结构与 `tools/updater` 相同；转发 exe 随 App Dir 一起被 Updater 替换，Portable 模式同样可用。
- 转发 exe 显式把 std 句柄交给主程序，不依赖 Nuitka `attach` 模式继承管道。
- 插入的 `ghd` 标明这是子命令；argv[0] 不能改，打包版靠它定位自身。
- Uninstaller 用 `[Code]` 从用户 PATH 删去 `{app}\bin`，两端补 `;` 匹配首尾条目。
