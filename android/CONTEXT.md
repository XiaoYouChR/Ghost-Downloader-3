# Compose Context

继承根目录 [CONTEXT.md](../CONTEXT.md) 的全部领域语言。以下术语仅适用于 android/。

## 桥接

**State Push**:
一次推送代表该 key 当前的全部真相。幂等、可覆盖；迟到的订阅者立刻拿到当前快照。
_Avoid_: snapshot、state sync、increment

**Event Push**:
一次推送代表发生了一件事。不重放；迟到的订阅者看不到订阅前的事件。
_Avoid_: notification、message

**View Projection**:
engine.py 为 Kotlin View 构建的 JSON 输出，形状由 Engine 决定。
_Avoid_: DTO、response、payload

## Pack UI

**Pack Dex**:
编译为独立 dex 的 FeaturePack Compose UI 模块。
_Avoid_: plugin、extension

**Pack Slot**:
PackUi 接口上的可选 UI 挂载点，Pack 拥有渲染。
_Avoid_: hook、extension point、render prop

**Draft Control**:
草稿卡上的紧凑选择控件。FeaturePack 在 draftFields 投影里声明，core 渲染——不是 Pack Slot。
_Avoid_: 与 Task Options 混淆

## 任务列表

**Section**:
任务列表内按完成与否做的分组：未完成、已完成。桌面端没有这个形态。
_Avoid_: 与 Category Filter 互指

**Category Filter**:
把任务列表收窄到分类上的筛选，三态：全部分类、未分类、某个分类。桌面端只有二态（无「未分类」）。
_Avoid_: 与「更改分类」混淆
