# Linux 窗口阴影只走 KWin 的 org_kde_kwin_shadow 协议

Linux 上的窗口都是无边框窗口（qframelesswindow 设了 `FramelessWindowHint`），合成器不给它们画装饰，也就没有阴影。我们改用 KWin 专有的 `org_kde_kwin_shadow` 协议：把 8 块阴影贴图交给 KWin，由它画在 surface 外面。窗口几何不变，贴边、分屏、最大化都由合成器照常处理。这与 KDE 自己的 `KWindowShadow` 做法相同（Breeze 的菜单阴影就是这样实现的）。外观固定照搬 Breeze 默认的 Large 档，不读 `breezerc`。

只有注册表里存在 `org_kde_kwin_shadow_manager` 时才生效。GNOME、wlroots 系和 X11 都维持没有阴影。目前只有 KWin 实现了这个协议；以后有别的合成器实现，会自动生效。

PySide6 不提供取窗口 `wl_surface` 的接口，系统里的 KF6 `KWindowShadow` 又链接系统 Qt，与 PySide6 自带的 Qt 冲突，所以只能用 ctypes 调 Qt 私有符号（与 ADR 0019 同理）：先用 `QWindow::resolveInterface("QWaylandWindow", 1)` 取得私有接口，它是 `QtWaylandClient::QWaylandWindow` 的首个基类，指针可以直接作为 `this` 调用 `QWaylandWindow::wlSurface()`。缺少符号时只记一条警告，不画阴影。

## Considered Options

- **自绘阴影**：开启透明背景，在窗口四周留出透明边距自己画阴影。Wayland 下必须调用 `xdg_surface.set_window_geometry` 告诉合成器窗口实际在哪，而 Qt 只在私有的 `setCustomMargins` 里调用它；不告诉的话，贴边和分屏会把透明边距算进窗口，留出一圈缝。GNOME 下也只能走这条路。
- **改用系统标题栏**：KDE 会画原生边框和阴影，但 Fluent 标题栏和挂在上面的搜索框都要放弃，与 Windows、macOS 的观感也不再一致。
- **Plasma 6.8 的"Window manager draws titlebar, frame, and shadows"窗口规则**：在 Wayland 上不会自动生效，需要用户手动配置，也没有让客户端主动申请的协议。
- **同时自绘圆角**：Linux 上没有让合成器裁圆角的协议，只能自绘，与上面放弃自绘阴影的理由相同。窗口保持直角。

## Consequences

- 升级 PySide6 后，如果 Linux 上的阴影消失，先查日志里有没有符号加载失败的警告。
- Qt 隐藏窗口时会回收 `wl_surface`，所以阴影在 `Hide` 时销毁，在下一次 `Expose` 时重建。
- 验证只能在 KDE Wayland 上手动做：主窗口和对话框都有阴影；隐藏后再显示，阴影还在；最大化、贴边、分屏时窗口不留缝；在 GNOME 或 X11 下启动不报错。
