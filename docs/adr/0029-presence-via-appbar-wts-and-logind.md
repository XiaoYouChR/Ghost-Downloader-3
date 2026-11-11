# 用 appbar、WTS 和 logind 判断能否打扰用户

Popup 置顶显示，必须避开全屏、演示和锁屏，否则会打断全屏游戏（独占全屏下出现置顶窗口，游戏可能被最小化），或在锁屏期间到时关闭而无人看见。这类时候 Popup 先暂存，等到可以打扰再显示。判断由 `Presence` 负责：`send` 时同步查询一次，此后只在系统事件唤醒时重新查询，不轮询。

- **Windows**：锁屏以 `WTSQuerySessionInformation` 的 `SessionFlags` 为准，全屏和演示以 `SHQueryUserNotificationState` 为准（`BUSY`、`RUNNING_D3D_FULL_SCREEN`、`PRESENTATION_MODE` 不能打扰）。唤醒事件有三个：
  - `ABN_FULLSCREENAPP`：用一个隐藏窗口 `ABM_NEW` 注册 appbar，不 `ABM_SETPOS`，所以不占屏幕空间；退出前 `ABM_REMOVE`。
  - `WM_WTSSESSION_CHANGE`：`WTSRegisterSessionNotification` 注册，锁屏、解锁时送达；退出前注销。
  - `TaskbarCreated`：Explorer 重启后会广播它，收到后重新注册 appbar。

  全屏应用的进出系统不会发任何通知，只有 appbar 能收到，这就是注册一个 appbar 的原因。
- **X11**：读 logind 会话的 `LockedHint`，订阅它的 `PropertiesChanged`。全屏交给窗口管理器处理：按 EWMH 的堆叠顺序，获得焦点的全屏窗口位于 ABOVE 层之上，Popup 盖不住它。

## Considered Options

- **轮询状态**：空耗 CPU。
- **锁屏也用 `SHQueryUserNotificationState`（`NOT_PRESENT`）**：实测它比会话事件慢半拍到 1 秒，解锁事件到达时仍报告 `NOT_PRESENT`，暂存的 Popup 要等下一条 Notice 才放出来。WTS 在事件到达时已是新状态。
- **`WM_SETTINGCHANGE`**：实测锁屏、解锁时都不发。
- **`org.freedesktop.ScreenSaver.ActiveChanged`**：不在 freedesktop 规范里（规范只定义了 `Inhibit` 和 `UnInhibit`），GNOME 把它放在 `org.gnome.ScreenSaver` 上。
- **用户忙时改走系统通知**：用户回到电脑前看不到 Popup，两个 Adapter 互相依赖，系统通知被用户关掉时 Notice 还会彻底丢失。

## Consequences

- 各项查询失败都按可以打扰处理。
- 只在 Popup 出现前判断。已经显示的 Popup 不因随后进入全屏或锁屏而收起，留到计时结束；这几秒的打扰换来实现简单。
- `QUNS_QUIET_TIME` 指新账户首次登录后的一小时，不是勿扰模式，按可以打扰处理；勿扰模式不影响 Popup。
- 不锁屏的屏保（`NOT_PRESENT`）不拦截 Popup。
- 演示模式退出时没有唤醒事件。每次 `send` 都会顺带重试暂存队列，漏掉的唤醒由下一条 Notice 补上。
- `WTSRegisterSessionNotification` 在远程桌面服务就绪前调用会失败。应用在登录后才自启，此时服务早已就绪，所以只注册一次，失败时记日志，不等待 `Global\TermSrvReadyEvent`。
- appbar 回调和会话事件每次都会先后送达两份，两份的查询结果可能不同，重新查询必须是幂等的。
- `ABN_FULLSCREENAPP` 是否涵盖副屏尚未验证。
- X11 上 Popup 可能在全屏窗口后面到时关闭，用户看不见。
- 没有 logind 的 Linux 一律视为可以打扰。
