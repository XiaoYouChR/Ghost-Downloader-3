# Compose

继承根目录 [CLAUDE.md](../CLAUDE.md)。Qt 规则只适用于桌面。
术语见 [CONTEXT.md](CONTEXT.md)。

## 根本原则

**View adapts Engine。** Engine 是 source of truth，Compose 是 Engine 状态的投影。

- Engine JSON 接口不为 Compose 改结构——Kotlin 数据类用 @SerialName 适应
- Engine 不出 UI schema——控件类型、label、布局是 View 知识
- 新功能的状态和逻辑加在 Engine，Compose 只渲染和收集输入
- Draft 流程、Task 状态机、Settings 校验全在 Engine，Compose 不重复

## Chaquopy

Python 模块通过 Chaquopy 嵌入，Kotlin 用 callAttr 调用：

```kotlin
val module = Python.getInstance().getModule("engine")
val json: String = module.callAttr("tasks").toString()
```

- 原始类型（String/Int/Bool/Double）和 null↔None 双向自动转换
- dict/list 不自动转——批量数据必须走 JSON（1 次 GIL crossing vs 逐字段 N 次）
- callAttr 获取 GIL，多协程串行等待——始终用 `Dispatchers.IO`
- Python 异常表面为 `PyException`
- PyObject 引用安全，不需手动 close

**EngineRepository** 封装上述模式，是 bridge 的单 adapter：

```kotlin
fetch<T>(name, vararg args)   // callAttr → toString → decodeFromString<T>
request(name, vararg args)    // callAttr，无返回值
poll<T>(name, intervalMs)     // 定时 fetch → StateFlow
```

三种数据流，按变化驱动方选：

| 模式 | 驱动方 | 用法 |
|---|---|---|
| Poll | Engine 自主变化 | tasks(500ms), keepAlive(1s) |
| Read-after-Push | 用户操作触发 | settings: request → fetch |
| Fire-and-Forget | 单向命令 | pause, remove |

## 包结构

```
com.xychr.ghostdownloader/
  model/      ← @Serializable 数据类（Engine JSON 的 Kotlin 投影）
  engine/     ← EngineRepository（bridge 单 adapter）
  service/    ← Android 系统服务
  packs/      ← PackUi 实现 + 发现
  i18n/       ← Engine 字符串映射
  ui/
    task/     draft/     settings/     ← feature 包（Screen + ViewModel + 组件）
      packs/  ← Pack 设置页
    components/  navigation/  theme/  liquid/
```

ViewModel 与 Screen 同包。packs/ 顶级——跨 feature。

## 命名

继承根 CLAUDE.md 的 camelCase 动词前缀规则。Compose 特有：

| 类别 | 规则 | 示例 |
|---|---|---|
| @Composable 发出 UI | PascalCase 名词（官方 MUST） | TaskCard, DraftEditor |
| @Composable 返回值 | camelCase（官方 MUST） | rememberSelectionState() |
| remember 工厂 | remember 前缀（官方 MUST） | rememberSearchResults() |
| ViewModel | {Feature}ViewModel | TaskViewModel |
| 状态类 | State 后缀 | DraftState, SelectionState |
| 回调参数 | on{Verb} / on{Noun}{Verb} | onClick, onValueChange |
| CompositionLocal | Local 前缀（项目约定） | LocalSharedTransition |
| Modifier 扩展 | camelCase | Modifier.fadingEdge() |

Screen 做顶层路由目标，Page 做导航子页面。

## Pack UI

PackUi 的 slot 是属性不是函数（ComposeProxy 约束）。
Pack Dex 通过 DelegateLastClassLoader 加载，回退到宿主类。
添加 pack UI：packs/ 下实现 PackUi → 覆盖需要的 slot → manifest 声明类名。

## Compose 约定

**状态下行，事件上行。** Composable 接收不可变状态和事件 callback。
状态归属于读写它的最窄作用域——ViewModel 归 Screen，NavController 归导航宿主，
动画状态归 Composition。

**单点消费。** 每种关注点（inset、padding、装饰）在组合树中恰好处理一次。
消费已应用的 inset，滚动末尾留白与页面外边距分别处理。

**延迟读取。** 逐帧变化的值在 graphicsLayer 或 layout 阶段读取，
将重组推迟到最窄范围。长生命周期手势和 effect 捕获最新回调。

**语义优先。** 交互用 Foundation 语义化 API，触控区至少 48dp。
对外 Composable 提供 `modifier: Modifier = Modifier`——这是调用方的定制 seam。
