# Notice 直接使用 desktop-notifier 的类型

Notice 有两个送达渠道：Popup 和系统通知。两者共用同一个接口 `send(notification: Notification)`，参数直接用 desktop-notifier 的 `Notification`、`Button`、`Icon`、`Sound`，不另外定义 Notice 类型。这样系统通知渠道原样转交即可，没有转换代码；Popup 也和系统通知一样，按 desktop-notifier 的字段语义行事（例如 `timeout`：`-1` 跟随系统、`0` 不关闭、正数为秒数，与 freedesktop 规范一致）。

## Considered Options

- **自定义 Notice dataclass，两个 Adapter 各自转换**：字段与 `Notification` 几乎一一对应，多出一层纯转发。

## Consequences

- View 层（Popup）依赖第三方类型。导入只走 `desktop_notifier.common`，不触发后端加载。
- Popup 忽略 `reply_field`、`attachment`、`thread`。
- 同一个 `Notification` 可能在 asyncio 线程（系统通知）或 Qt 主线程（Popup）回调，所以回调只能做线程无关的事。
