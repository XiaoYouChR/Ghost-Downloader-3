# Compose Context

继承根目录 [CONTEXT.md](../CONTEXT.md) 的全部领域语言。以下术语仅适用于 compose/。

## 桥接
**State Push**:
一次推送代表该 key 当前的全部真相。幂等、可覆盖；迟到的订阅者立刻拿到当前快照。
_Avoid_: snapshot、state sync、increment

**Event Push**:
一次推送代表发生了一件事。不重放；迟到的订阅者看不到订阅前的事件。
_Avoid_: notification、message

**View Projection**:
engine.py 为 Kotlin View 构建的 JSON 输出，形状由 Engine 决定，与持久化序列化职责不同。
_Avoid_: DTO、response、payload

## Pack UI

**Pack Dex**:
编译为独立 dex 的 FeaturePack Compose UI 模块。
_Avoid_: plugin、extension

**Pack Slot**:
PackUi 接口上的可选 UI 挂载点。Pack 只实现需要的 slot。
`draftExtra` 是 pack 专属草稿参数区，不是草稿的编辑入口。
_Avoid_: hook、extension point、render prop
