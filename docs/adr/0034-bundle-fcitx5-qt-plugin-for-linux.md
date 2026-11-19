# Linux 发行包内置自编译的 fcitx5-qt 输入法插件

Linux 上的 `.AppImage`、`.deb` 与 `.tar.xz` 三种产物共用同一份 Nuitka 打包结果（`dist/Ghost-Downloader-3.dist`），自带 PySide6 捆绑的 Qt6 运行时。此前 `scripts/deploy.py` 只传了 `--include-qt-plugins=platforms`，不仅没有 fcitx5 插件，连 PySide6 自带的 `ibus` 和 `compose` 输入法插件也被漏掉，导致打包版无法在输入框中调起中文输入法（#1109）。

我们改为在打包阶段同时包含 `platforminputcontexts`（排除 `libqtvirtualkeyboardplugin.so` 及其库，避免拖入虚拟键盘与 QML 运行时），并在 Linux CI 构建中用与当前 PySide6 同版本的官方 Qt6 SDK（通过 `aqtinstall` 只拉取 `qtbase`、`qtwayland`、`icu`）以 `-DBUILD_ONLY_PLUGIN=ON` 编译 `fcitx/fcitx5-qt`，将产出的 `libfcitx5platforminputcontextplugin.so` 放入 venv 的 `PySide6/Qt/plugins/platforminputcontexts/`，交由 Nuitka 自动打包并修正 RPATH。

`BUILD_ONLY_PLUGIN=ON` 会把 `Fcitx5Qt6DBusAddons` 编为内部对象文件并静态链入插件，产出的 `.so` 不依赖宿主任何 `libfcitx5*` 动态库，仅依赖 PySide6 自带的 Qt6 库与系统基础库（`libxkbcommon`、`libxcb`），运行时通过 D-Bus 与宿主 fcitx5/fcitx4 通信。默认开启 `WITH_FCITX_PLUGIN_NAME=ON` 使单个插件同时响应 `QT_IM_MODULE=fcitx` 与 `fcitx5`，`ENABLE_QT6_WAYLAND_WORKAROUND=ON` 兼顾 Wayland 下显式设置 `QT_IM_MODULE=fcitx` 的场景。上游 `fcitx5-qt` 不写死版本，构建时动态解析最新稳定 semver tag，并以 `(architecture, pyside6_version, fcitx5_qt_tag)` 作为缓存键缓存 `.so`。

## Considered Options

- **复用宿主系统的 `fcitx5-qt` 插件（或升级 PySide6 对齐发行版 Qt 版本）**：`fcitx5-qt` 链接 `Qt6::GuiPrivate`，依赖 Qt 小版本专属的私有 API 符号（如 `QtPrivate_6_10_3`）。各 Linux 发行版自带的 Qt6 版本跨度极大（Ubuntu 22.04 为 6.2、Debian 12 为 6.4、Debian 13 为 6.8、Arch 滚动更新至 6.12+），靠升级 PySide6 对齐宿主版本无法跨发行版工作。
- **零编译方案（仅打包 PySide6 自带 `ibus` + 运行时改写环境变量走 Wayland 原生协议或 fcitx5 的 IBus Portal）**：改动小且零 CI 编译成本，但需要在应用启动时篡改进程内 `QT_IM_MODULES` / `IBUS_USE_PORTAL`，且依赖宿主 fcitx5 未关闭 `IBus Frontend`，同时不支持 fcitx4。相比之下，自编译插件运行时 0 改动、全环境原生兼容，配合缓存后长期维护成本也很低。
- **拆到独立仓库预编译 `fcitx5-qt`**：纯插件编译很轻，拆仓反而增加了每次升级 PySide6 时的手动联动成本。

## Consequences

- `scripts/deploy.py` 不夹带 fcitx5 特例，开发者在 Linux 本地直接运行 `deploy.py` 时不强制要求先编译 `fcitx5-qt`；发布包的完整性由 `build.yml` 中的插件存在性与 `ldd` 检查兜底。
- 升级 PySide6 后首次 Linux CI 构建会缓存未命中，自动拉取对应版本 Qt6 SDK 并重新编译 `fcitx5-qt` 插件；若上游 `fcitx5-qt` 某版出现编译回归，可通过 `scripts/build_fcitx5_plugin.py --tag` 临时指定版本排查。
- 仅靠 `ldd` 只能验证动态库依赖完整，实际输入体验仍需在 Linux（Wayland 与 X11 下均设置 `QT_IM_MODULE=fcitx`）手动验证。
