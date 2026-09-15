# compose 的命令失败走 View 防御，不建第二条 i18n 链

引擎运行时错误的 i18n 通路已经存在：`TaskError(message, params)` → `engineText()` → 生成的
`EngineStrings.kt` → 8 个 locale。Desktop 侧是 `toTaskError` catch-all + `toLocalizedError`
单一出口。

compose 的缺口在展示：`PyException.getMessage()` 是 `"{TypeName}: {str(e)}"`，已包装的 catch
点直接显示 `e.message`，而 ViewModel 又没有 `Context`，翻译不了——所以它们把错误存成
`String?`，在渲染时已经是一句死的英文。

决定：

- **展示侧归一化，桥不加接口。** 加 `Throwable.toTaskError()` 与 `engineText(TaskError)` /
  `engineText(Throwable)` 重载：剥掉 `"{TypeName}: "` 前缀，**命中 `engineStrings` 就当作模板**，
  否则包进已注册的兜底模板 `发生了意外错误：{detail}`——与 Desktop 的 `toTaskError` 同一契约。
  盲剥会把 `"HTTP 403: Forbidden"` 剥成 `"Forbidden"`，所以先用 `containsKey` 判别。
- **ViewModel 的错误状态一律是 `TaskError?`，不是 `String?`。** 这是根 `CONTEXT.md:105`
  的既有约定（model 存机器可读 key，View 映射到翻译文本），`TaskUiState.error` 早就是这个形状。
  统一到它，而不是新造。渲染统一走 `ui/components/ErrorText.kt`。
- **不加 `EngineError` 类型。** 删除测试：删掉它调用方 `catch (e: Exception)` 一字不用改，
  它不提供任何东西。需要区分「引擎说不行」和「桥断了/解码失败」时再加。
- **不加 `post()`。** 需要它是基于「约 10 处裸 `launch` 会崩进程」的判断，而那个判断没验。
- **`engine.py` 的校验按桥的两个方法分开**：`query` 语义（View 要拿数据）的失败必须
  `raise`，View 显示翻译后的消息；`invoke` 语义（发了就行）的竞态守卫**静默返回**，与引擎
  自己的既有模式同构（`pause` / `remove` / `stopTask` 查不到 id 就 `return`）。View 仍然要
  禁用注定失败的操作（「View 是校验边界」），引擎的静默只兜住 render 与 tap 之间那 100ms 的
  窗口——两者都要，不是二选一。
- **`engine.py` 的值/能力校验一律删除**（`raise ValueError` 归零）。View 是校验边界——它用引擎
  投影出的能力字段（`canEdit`、`canRename`、`canProbeMedia`）提前禁用操作，Service 信任它送来的
  值，不重复校验。只保留「按 id 查不到就 `return`」这一种守卫，因为那是引擎自己的既有模式
  （`pause` / `remove` / `stopTask` 都这样），是查找失败的一致处理而非防御。

## Considered Options

- **把裸 `launch` 逐条加防护**：曾写进本 ADR，撤销。引擎的命令层是防御式写的——`pause`
  `resume` `stopTask` `remove` `redownload` `installRuntime` `setBrowserPairApproval` 查不到
  id 就 `return`，**不抛**。给它们加 catch 是 hypothetical 防御。逐条查完，真正可能抛的只有
  `setSetting`（`cfg.byName[name]` 的 `KeyError`）和 `requestPack`（pack 业务错误），而前者
  只在传了不存在的设置名时发生——那是编程错误，不是用户条件。
- **`EngineRepository` 补 catch-all，抛携带模板的类型化异常**：曾写进本 ADR，撤销。catch 后
  再抛不解决崩溃；而带参数的模板在 `TaskError.__str__` 里就被 `format_map` 替换掉了，过桥后
  已不是模板，剥前缀对它们无效。
- **建 Android 侧独立 i18n 链，逐条翻译那 14 条**：把 bug 当需求做。这些错误本不该出现——
  `canEdit` 已经在数据里，View 本该禁用按钮；「查不到」是竞态，正确反应是刷新而不是弹文案。
- **把 `compose/app/src/main/python` 加进 `sync_i18n_res.py` 的扫描 roots**：方向反了。
  共享链服务 Desktop + engine + packs，让 App 的知识进共享层会污染 Desktop 的 `.ts` 资产。
  对称于「Packs 知识不进 App」：App 知识也不进共享层。
- **`invoke` 吞掉异常并推 Notice**：会剥夺已包装点的能力——`TaskViewModel` 的失败计数、
  `TasksPage` 的 snackbar 会变成死代码。
