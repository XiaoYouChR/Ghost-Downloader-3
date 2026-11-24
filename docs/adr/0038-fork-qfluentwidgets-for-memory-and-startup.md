---
status: accepted
---

# 用独立 Fork 的 PySide6-Fluent-Widgets 显式管理生命周期并优化性能

桌面端不迁移至 QML（见 [qml-vs-qwidgets-memory.md](../research/qml-vs-qwidgets-memory.md)），而是维护窄改造面软分叉仓库 `XiaoYouChR/PyQt-Fluent-Widgets`，通过 `pyproject.toml` 的 `[tool.uv.sources]` 锁定 Git Tag 或 Commit SHA 接入。本次重构保留 `qconfig` 等纯数据单例与全部控件构造签名（使独立 Publish 的 FeaturePack 零改动运行），以四条统一实施原则收拢职责边界与生命周期。

## 统一实施原则

1. **所有权即生命周期**：进程级 UI 资源（`.rcc` 与应用级 QSS 块）归 `QApplication`，由顶层唯一两个新函数 `qfluentwidgets.load(app)` / `unload()` 显式装卸并挂接 `app.aboutToQuit`；控件级子对象、动画、定时器、样式绑定（`StyleSheetBinding`）与浮层动画组一律挂在父 `QObject` 树上由 Qt 析构连带回收；短期浮窗（`ToolTip`）借 `destroyed -> deleteLater` 联动销毁；跨树全局索引（`qrouter`）仅存弱引用并在 `destroyed` 自动摘除。
2. **工作跟随可见性**：无限动画与周期定时器（`IndeterminateProgressBar`、`IndeterminateProgressRing`、`StateToolTip`、背景过渡动画）由 `showEvent` / `hideEvent` 门控停机，隐藏态零空转；背景过渡动画按需分配，悬停提示延迟用 `QObject.startTimer` 零堆分配，一次性过渡动画一律 `DeleteWhenStopped`。
3. **优先 Qt 原生机制，不造平行轮子**：
   - 16 份无裸选择器且无通用 ID 冲突的 `FluentStyleSheet` 合并为单一受管块（`/* qfw:begin */ ... /* qfw:end */`）写入 `QApplication.setStyleSheet()`；其余 18 份非提升样式与自定义样式挂控件自有 `StyleSheetBinding(parent=widget)`，在 Qt 原生 `StyleChange` / `Show` 时按 `(theme, color, fonts)` 更新，替代全局样式表注册表与 `DirtyStyleSheetWatcher`。
   - `BackgroundAnimationWidget` 改用 `changeEvent(EnabledChange | StyleChange | ThemeChange)` + `showEvent` / `hideEvent`，以 `self._backgroundColor is None` 为单一未解析态，移除自装 `eventFilter` 与全局 `qconfig.themeChanged` 订阅。
   - `updateDynamicStyle(widget)` 原地改为 `style.unpolish` -> `style.polish` -> `update`，替换全库全部 `setStyle(QApplication.style())` 调用。
   - 系统配色优先使用 Qt 6 `QGuiApplication.styleHints().colorScheme()` 与 `colorSchemeChanged`（无 `QGuiApplication` 时懒回退 `darkdetect`）；`common/icon.py` 保留上游 `QDomDocument` 仅改为函数内懒导入（与 `QSvgRenderer` 一并延迟，避免启动期加载）；单次异步回调统一采用三参数 `QTimer.singleShot(ms, receiver, slot)`；跨层级事件过滤器在 `showEvent` / `hideEvent` 成对装卸。
4. **边界清晰，校验止于入口**：
   - QFW Fork 只管通用控件的懒导出、`.rcc` 与样式引擎、对象生命周期和通用缺陷（收编 `unregisterRouter` 与 `patchStackedWidgetAnimation`）；Ghost Downloader 宿主负责启动顺序（`qconfig.load` -> `Application` -> `qfluentwidgets.load(app)`）、关窗退托盘销毁重建、Win32 DWM / macOS Cocoa 材质、`patchMaskDialogAnimation` 与容器精确选择器纪律（`.MainWindow` / `.QWidget`）。
   - 参数与资源校验止于 `load(app)` 入口，内部信任启动不变量；不建单调用方浅包装类，不留兼容别名，不保留可派生的冗余状态变量。

## 延迟导入与资源瘦身

- **单层扁平延迟导入（`qfluentwidgets._symbols`）**：构建脚本纯 AST 静态生成 12 个 `__init__.py` 的单跳 `{symbol -> leafModule}` 映射，移除 `common/config.py` 导入期 Pro 横幅；仅读取 `qconfig` 时不拉入控件、`QtSvg`、`QtXml`、`QtSvgWidgets`、`.rcc` 与 `darkdetect`。
- **二进制 `.rcc` 资源**：用 `pyside6-rcc --binary` 编译的 `_rc/resource.rcc` 替代 98,899 行 `_rc/resource.py`，由 `qfluentwidgets.load(app)` 显式注册、`unload()` 反注册；移除无用的 `PySide6.QtSvgWidgets` 导入。

## Considered Options

- **全量迁移至 QML（`FluentWinUI3`）**：重写成本高，且 D3D11 RHI 带来约 51 MB 驱动私有提交与 22-37 MB 显存，对非 UI 内存无帮助（见 [qml-vs-qwidgets-memory.md](../research/qml-vs-qwidgets-memory.md)）。
- **彻底硬分叉或将 Button 家族改为 Python `paintEvent` 自绘**：抬高上游同步成本且 PySide6 高频 `paintEvent` / `QProxyStyle` 带来跨语言调用开销；保留 QSS 资产并守住容器精确选择器纪律可兼得纯 C++ 渲染与低维护面。
- **在 `icon.py` 用 `xml.etree.ElementTree` 替代 `QDomDocument`**：实测 `ElementTree` 首次导入慢 20 倍（30.23 ms vs 1.47 ms），且上游 `qframelesswindow` 已必带 `Qt6Xml.dll`（连同 `QtXml.pyd` 共 360 KB），换解析器既省不下 DLL 又增大 diff 与序列化差异风险。
- **散落按需懒加载 `resources.load()` 或内部遍布 `requireLoaded()` 校验**：前者在 6 个上游文件散布十余处样板，后者违背 "trust internals, validate at boundaries"；统一由 `load(app)` 在启动入口校验一次最简洁。
- **公开 `FluentRuntime` / `AppScope` / `WindowScope` / `ResourceBundle` 等句柄或包装类**：单一调用方下均未通过 Deletion Test，直接收拢为 `load(app)` / `unload()` 两个扁平函数。

## Consequences

- Ghost Downloader 宿主在 `app/startup.py` 的 `loadResources(application)` 中显式调用 `qfluentwidgets.load(application)`，退出时由 `aboutToQuit` 自动执行 `unload()`；`app/view/qfw_patch.py` 删除 `unregisterRouter` 与 `patchStackedWidgetAnimation`。
- 主仓与 `FeaturePack` 须遵守应用级 QSS 纪律：容器透明样式只能使用精确类选择器（`.QWidget` / `.MainWindow`）、对象 ID 选择器或 `setAutoFillBackground(False)`，禁止非限定 `setStyleSheet("background: transparent")`。
- `scripts/deploy.py` 接入 Fork 时须同步三项 Nuitka 配置：`EXTRA_INCLUDE_PACKAGES` 加入 `"qfluentwidgets"`（确保独立 Publish 的 FeaturePack 可按需导入任意控件），配套 `--nofollow-import-to=qfluentwidgets.multimedia`（遵守 [ADR 0028](./0028-notice-sound-without-qtmultimedia.md)，避免带入 `QtMultimedia` 与 FFmpeg），以及 `dataArgs` 附带 `qfluentwidgets/_rc/resource.rcc`。
- 上游升级时重跑 Fork 构建脚本再生 `_symbols.py` 与 `resource.rcc`，并以 `pytest` 验收：12 个包导出符号集与上游一致（仅多 `load` / `unload`）、16 份提升 `.qss` 无裸选择器、透明容器不击穿 Button 背景、显式 `load` / `unload` 与 `MainWindow` 关窗重建零泄漏。
- 应用侧自身的 `--silence` 延迟创建主窗口与 TaskCard 视口对象池复用，留作独立任务推进，不混入本 Fork。
