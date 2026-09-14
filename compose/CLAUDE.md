# Compose

继承根目录 [CLAUDE.md](../CLAUDE.md)。Qt 规则只适用于桌面。术语见 [CONTEXT.md](CONTEXT.md)。

## 思想

- **View adapts Engine.** — Engine 是 source of truth，Compose 是投影。Engine 接口不为 Compose 改结构
- **Signal-driven across runtimes.** — Python 信号通过 EngineFlows 跨运行时推送到 Kotlin Flow。常态零 callAttr
- **engine.py 是 Android View Adapter.** — 和 Desktop `app/view/` 同构：投影 model 状态、处理用户命令。投影是纯读（`task.x`、`service.compute(task)`），不内联业务逻辑
- **Kotlin→Python 是内部调用.** — 根目录「View 是校验边界」的具体应用。SettingRanges 提供范围约束，格式检查在 Kotlin
- **Model 不为 Android 改.** — 现有 model 跑通了 Desktop，Android 通过 engine.py 投影适配，不往基类加接口

## EngineRepository

纯通信桥，零生命周期。依赖显式注入（`bind`）。

| 方法 | 语义 |
|---|---|
| `query<T>(name, args)` | 问，调用 Engine 方法，取返回值 |
| `invoke(name, args)` | 做，调用 Engine 方法，不取返回值 |
| `observe<T>(key)` | 看，订阅 Engine 推送的 Flow |
| `encode<T>(value)` | 编码，复杂参数包装为不透明 Encoded |

## Chaquopy

- Chaquopy 知识不出 App.kt——EngineRepository 只接收 PyObject 句柄，不 import Chaquopy
- JSON 是统一性选择——`Flow<String>` + `@Serializable` 给所有数据一条路径。不在个案上换 native PyObject
- dict/list 不自动转，批量数据走 JSON（1 次 GIL crossing vs 逐字段 N 次）
- callAttr 获取 GIL，多协程串行，始终 `Dispatchers.IO`

## Pack UI

android.py 声明 `UI_CLASS`，engine.start() 返回发现结果，PackRegistry 反射加载。
PackUi 的 slot 是属性不是函数（ComposeProxy 约束）。

## 目录

| 目录 | 放什么 | 判定标准 |
|---|---|---|
| `ui/pages/` | 页面级 Composable + ViewModel | 有 Route 对应 |
| `ui/components/{domain}/` | 领域组件 | 无 Route，被页面组合 |
| `ui/components/` | 跨域共享组件 | 多领域共用 |
| `ui/util/` | 纯 Kotlin 工具函数 | 无 Android SDK 依赖 |
| `ui/platform/` | Android 平台粘合 | Intent、FileProvider、SharedPreferences 等 |

## 命名

| 类别 | 规则 | 示例 |
|---|---|---|
| @Composable 发出 UI | PascalCase 名词 | TaskCard, DraftEditor |
| @Composable 返回值 | camelCase | rememberSelectionState() |
| ViewModel | {Feature}ViewModel | TaskViewModel |
| 状态类 | State 后缀 | DraftState, CategoryState |
| 回调参数 | on{Verb} / on{Noun}{Verb} | onClick, onValueChange |
| CompositionLocal | Local 前缀 | LocalSharedTransition |
| 页面 Composable | Page 后缀 | TasksPage, TaskDetailPage |
