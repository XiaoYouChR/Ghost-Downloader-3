# Compose

继承根目录 [CLAUDE.md](../CLAUDE.md)。Qt 规则只适用于桌面。术语见 [CONTEXT.md](CONTEXT.md)。

## 思想

- **View adapts Engine.** — Engine 是 source of truth，Compose 是投影。Engine 接口不为 Compose 改结构
- **Signal-driven across runtimes.** — Python 信号通过 EngineFlows 跨运行时推送到 Kotlin Flow。常态零 callAttr
- **Chaquopy 知识不出 App.kt.** — EngineRepository 只接收 PyObject 句柄，不 import Chaquopy

## EngineRepository

纯通信桥，零生命周期。依赖显式注入（`bind`）。

| 方法 | 语义 |
|---|---|
| `query<T>(name, args)` | 问，调用 Engine 方法，取返回值 |
| `invoke(name, args)` | 做，调用 Engine 方法，不取返回值 |
| `observe<T>(key)` | 看，订阅 Engine 推送的 Flow |
| `encode<T>(value)` | 编码，复杂参数包装为不透明 Encoded |

## Chaquopy

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

## 约定

- **单点消费** — 每种关注点（inset、padding、装饰）在组合树中恰好处理一次
- **延迟读取** — 逐帧变化的值在 graphicsLayer 或 layout 阶段读取
- **语义优先** — 交互用 Foundation 语义化 API，触控区至少 48dp
- 对外 Composable 提供 `modifier: Modifier = Modifier`，调用方的定制 seam
