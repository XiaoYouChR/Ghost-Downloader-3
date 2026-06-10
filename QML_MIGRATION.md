# Ghost Downloader — QML 迁移（feature/QmlMigration）

把 GD 从 QtWidgets + QFluentWidgets 迁到 **QML（RinUI）前端 + 消息驱动后台引擎**，并为 Android / 省内存做**后台引擎与前端彻底分离**。基点 `c189c89`（Android 适配之前）。

## 怎么跑

```bash
# 默认：同进程（前端 + 引擎在一个进程，开发最方便）
PYTHONUTF8=1 python -m app.gui.app

# 拆进程：前端作瘦客户端连独立 headless 后台（省内存/Android 形态）
PYTHONUTF8=1 GD_ENGINE=daemon python -m app.gui.app
#   gui 会自动 detached 启动 app.engine.daemon；gui 退出后 daemon 继续下载

# 测试
python -m pytest -q
```

## 架构（三层 + 可换 transport）

```
 gui 进程                          引擎（同进程 或 独立 daemon 进程）
┌─────────────────────────┐      ┌──────────────────────────────────┐
│ RinUI QML               │      │ Engine                            │
│  TaskPage/TaskCard/...   │      │  收 command、发 event、进度泵      │
│ Backend(QObject,@Slot)   │◄────►│  Downloads 边界 → coreService     │
│ TaskList/TaskItem(model) │ link │   + featureService(各 pack)       │
│ TaskFilter/FileSelection │      │  Store 边界 → taskService(持久化)  │
└─────────────────────────┘      └──────────────────────────────────┘
        ▲  command(gui→engine) / event(engine→gui)  ▲
        └──────── link ────────────────────────────┘
   MemoryLink(同进程直送)  ｜  SocketLink(QLocalSocket，跨进程)
```

- **`app/protocol`**：`Command`/`Event`（带 `toBytes`/`fromBytes` JSON）、`MemoryLink`、`framing`（长度前缀）、`SocketLink`（SocketServer/SocketClient）。
- **`app/engine`**：`Engine`（命令分发 + 进度泵 + `_toWire` 线缆格式）、`Downloads`/`Store`/`Config` 可注入边界、`daemon.py`（QCoreApplication headless 入口）。
- **`app/gui`**：`Backend`（@Slot 供 QML 调）、`TaskList`+`TaskItem`（QAbstractListModel + 角色）、`TaskFilter`（搜索/排序）、`FileSelection`、`app.py`（壳 + 两种模式）、`qml/`。

**缝先行**：换 transport（MemoryLink↔SocketLink）时 Engine/Backend 一行不改——拆进程已端到端验证（gui 瘦客户端连 daemon 收到全量状态）。

## 关键约定

- **QML logic-free**：禁 if/计算/格式化；判断/格式化在 Python（`TaskItem.running/metaText/...`）。命令经 `backend.xxx()`，不直接碰 service。
- **命名**：`engine/gui/link/command/event/backend/Engine/TaskItem/TaskList`，替掉 Transport/Client/ViewModel 等黑话（见 `/pyside6-style` 与记忆）。
- **TDD**：集成式穿真缝，只在边界注入 fake（`tests/fakes.py` 的 `FakeDownloads`/`FakeStore`）。

## 已做 / 待办

**已做**：多协议下载（http/bt/m3u8/ftp 路由）、实时进度/速度/大小、持久化、搜索/排序/多选+批量删/删除确认/重命名/打开文件/多文件选择/清空已完成/SHA-256 校验/失败显错/设置页（并发数·下载目录）/BT·M3U8 专属展示、**拆真进程（headless daemon + socket）**、**daemon 掉线自动重连+重启**（崩/退后 gui 回到“连接中”并拉起新 daemon，自动连回重新 attach）。

**待办**：config 全量迁移（cfg→`app/engine/config.py` 的 Config 存储，架构决策）、Android buildozer 对接 daemon、daemon 生命周期（何时停）、窗口浮层（update/tray/splash）、`coreService.stop()` teardown 噪声。
