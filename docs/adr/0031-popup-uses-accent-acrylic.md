# Popup 用 accent 亚克力，不用 DWM 系统背景

Win11 上 Popup 的亚克力用未公开的 `SetWindowCompositionAttribute(ACCENT_ENABLE_ACRYLICBLURBEHIND)`（qframelesswindow 的 `WindowEffect.setAcrylicEffect`），配合 `WA_TranslucentBackground` 和 `DWMWCP_ROUND` 圆角。有文档的 `DWMWA_SYSTEMBACKDROP_TYPE`（`DWMSBT_TRANSIENTWINDOW`）实测在 Popup 上不显示：DWM 只给激活的窗口画系统背景，而 Popup 永不激活。

## Considered Options

- **`DWMSBT_TRANSIENTWINDOW` + `ExtendFrame(-1)`**：窗口不是 layered 时客户区可交给 DWM，但非激活窗口不画背景；`WA_TranslucentBackground` 又会让无边框窗口变成 `WS_EX_LAYERED`，DWM 也不画。
- **再发 `WM_NCACTIVATE(TRUE)` 伪装激活**：实测无效。

## Consequences

- 窗口是 layered 的，客户区要用 alpha=1 的颜色铺满，否则透明处鼠标会点穿。
- 亚克力的混合色按应用主题取色。系统关闭"透明效果"时，accent 亚克力把混合色当不透明底色画，主题依然正确，不需要读该设置。
- Win10 上 accent 亚克力在窗口移动时会卡顿，而 Popup 的进入、退出、重排都是移动动画，所以 Win10 用纯色直角。
- 阴影来自 accent 的阴影标志位，不用 `QGraphicsDropShadowEffect`。
