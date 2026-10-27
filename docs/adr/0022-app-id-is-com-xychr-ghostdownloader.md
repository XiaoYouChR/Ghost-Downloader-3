# 应用 ID 统一为 `com.xychr.ghostdownloader`

Linux 的 `.desktop` 文件与 D-Bus 服务名、macOS 的 `CFBundleIdentifier` 与 LaunchAgent label、Android 包名，统一使用同一个应用 ID `com.xychr.ghostdownloader`。
之前桌面端用 `io.github.xiaoyouchr.GhostDownloader`，macOS LaunchAgent 用 `com.xiaoyouchr.ghostdownloader`，Android 用 `com.xychr.ghostdownloader`，
三种写法各管一部分。Linux 任务栏进度要靠 `setDesktopFileName` 把窗口和 `.desktop` 对应起来，借这个机会统一，以 Android 已发布的包名为准。

## Consequences

- macOS 上 bundle ID 变了，系统会把它当作新 App：用户需要重新授权通知，系统设置里可能残留一条旧的通知项。
- 启动时清掉旧 ID 留下的 Linux `.desktop`、D-Bus `.service`、自启动文件和 macOS LaunchAgent，并按当前设置用新 ID 重写。大部分用户升级后，删掉这段迁移代码。
- 改用 `setDesktopFileName` 后，Wayland 下窗口的 app_id 和 X11 下的 `_GTK_APPLICATION_ID` 就是这个 ID。deb 和 AppImage 里的 `.desktop` 也以它命名，任务栏才能把窗口和 LauncherEntry 对应到同一个图标。
