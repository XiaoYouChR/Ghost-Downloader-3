# Compose Context

继承根目录 [CONTEXT.md](../CONTEXT.md) 的全部领域语言。以下术语仅适用于 compose/。

## 桥接

**Engine Bridge**:
Kotlin 与 Python Engine 的唯一通信通道。数据以 JSON string 跨越 Chaquopy seam，
单次 GIL crossing。Kotlin 侧实现为 EngineRepository object。
_Avoid_: repository、data source、API client

**View Projection**:
engine.py 为 Kotlin View 构建的 JSON 输出。从 Engine 内部状态选择、计算、合并字段，
形状由 Engine 决定，View 适应。与持久化序列化（serialization.py toDict）职责不同。
_Avoid_: DTO、response、payload

## 用户告知

**Outlet**:
Notice 送达用户的出口。应用可见时走应用内提示（Snackbar / Dialog），
不可见时走系统通知。出口由 Notice 的种类决定：已在界面上体现的不重复打扰，
纯告知的不在后台打扰。桌面没有这个概念——它的窗口提示和系统通知是并行的。
_Avoid_: channel（channel 是系统通知的分组，不是这里的出口）

## Pack UI

**Pack Dex**:
编译为独立 dex 的 FeaturePack Compose UI 模块。内附 manifest 声明
PackUi 实现类名。启动时从 packs 目录发现，DelegateLastClassLoader 加载。
_Avoid_: plugin、extension

**Pack Slot**:
PackUi 接口上的一个可选属性。六个 slot：
taskExtra、draftExtra、draftSummary、editExtra、detailExtra、settingsContent。
除 draftSummary（纯函数，返回概要文案）外均为 @Composable；Pack 只实现需要的 slot，
null 表示不提供。
_Avoid_: hook、extension point、render prop

**ComposeProxy**:
将 @Composable 函数包装为属性的技术。属性 getter 无参，
绕过 Compose Compiler 的 $composer/$changed 参数注入，使反射调用成为可能。
PackUi 的 slot 必须是属性不是函数，原因在此。
_Avoid_: reflection hack
