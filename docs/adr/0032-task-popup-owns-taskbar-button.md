# Task Popup 拥有自己的任务栏按钮

用户要在任务栏上看到下载进度，并能把进度卡片最小化（#960、#1089）；主窗口在后台运行时被隐藏，任务栏上没有按钮可画进度。所以 Task Popup 不用 Notice 卡片的 `Qt.Tool`，在 Windows 上显式加 `WS_EX_APPWINDOW` 和 `WS_MINIMIZEBOX`，用 `ITaskbarList3` 在自己的按钮上画本任务进度。Notice 和 Request 仍是 `Tool` 窗口，不占任务栏。

实测（Win11 26200，任务栏分开显示）：只去掉 `Tool` 不出按钮，因为 `WindowDoesNotAcceptFocus` 对应的 `WS_EX_NOACTIVATE` 会隐藏按钮；加 `WS_EX_APPWINDOW` 后按钮出现、进度正常，显示时不抢焦点；有 `WS_MINIMIZEBOX` 时点按钮可以最小化和还原。

## Considered Options

- **独立进度窗口**（IDM 式）：与 Popup 形成两套外观，且普通窗口弹出会抢走浏览器里的焦点。
- **下载期间主窗口最小化代替隐藏**：改变"关闭即消失"的既有行为，且只能显示汇总进度。
- **托盘图标画进度环**：Win11 默认把托盘图标收进溢出区，多数用户看不到。

## Consequences

- Task Popup 出现在 Alt+Tab 中。
- 从任务栏关闭（右键菜单、缩略图 ×）等同于点卡片上的关闭。
- 最小化的 Task Popup 退出右下角堆叠，还原时重新插入。
- 任务结束后 Task Popup 被普通 Popup 形式的结果提示取代，任务栏按钮随之消失；最小化中的任务完成时，结果提示直接出现在右下角，不闪烁任务栏按钮。
- Linux 只有应用级的 LauncherEntry 进度，Task Popup 有按钮但无单任务进度；macOS 和 Wayland 不显示 Popup。
- 任务栏"合并"显示时合并按钮显示谁的进度、Win10 上的表现，均未实测。
