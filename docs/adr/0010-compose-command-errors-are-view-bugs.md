# Compose 命令失败是 View 的 bug，不是用户条件

Engine 投影能力字段（`canEdit`、`canRename`、`canProbeMedia`），View 据此禁用操作。命令到达
engine.py 时它已经合法——如果不合法，是 View 漏了校验。不为 View 的 bug 建错误报告基础设施。

错误展示复用已有 i18n 链：`Throwable.toTaskError()` 剥 PyException 前缀，`engineText(TaskError)`
查 `engineStrings` 翻译模板，未命中则兜底 `发生了意外错误：{detail}`。ViewModel 存 `TaskError?`
（机器可读 key），View 在渲染时翻译。`query` 失败 raise，View 显示翻译消息；`invoke` 的竞态守卫
静默 return（与 `pause`/`remove`/`stopTask` 查不到 id 就 return 同构）。

## Consequences

- engine.py 的 `raise ValueError` 归零——View 是校验边界，Engine 不重复校验。
- 只保留「按 id 查不到就 return」这一种守卫，是查找失败的一致处理。

## Considered Options

- **建 Android 侧独立 i18n 链**：把 bug 当需求做。这些错误本不该出现。
- **EngineRepository 补 catch-all 再抛类型化异常**：catch 后再抛不解决崩溃；模板过桥后已被
  `format_map` 替换，不再是模板。
- **`invoke` 吞异常并推 Notice**：剥夺已包装点的能力（TaskViewModel 失败计数、snackbar）。
