# 线程归属：D 拥有服务状态，L 拥有 socket，J 只经 request 进入

Dispatcher 线程 D（桌面是 Qt 主线程，Android 上就是 loop 线程）拥有全部服务状态，`cfg.set` 只在 D 上调用；
loop 线程 L 拥有 socket、连接和协程；Android 的 JVM 线程 J 不拥有任何状态，所有 engine 调用只经 `request` 这一个入口切到 D。
de-Qt 之后 bind 在 D、close 在 L，JVM 线程直接改 `_sessions`、`_pendingPair`、TaskService，稳定性因此大幅下降。

## Considered Options

- **每个 engine 方法自己切线程**（装饰器或 `run_coroutine_threadsafe().result()`）：漏掉一个就是一个竞态，draft 方法各自为政正是这个病。
- **给服务加锁**：锁住的是症状；Signal 同步 emit 会把锁带进 View 和其他服务。

## Consequences

- J 阻塞等待 L 执行完调用，与原来 draft 方法的 `.result()` 等价；engine 方法不得在 L 上再阻塞等 L，需要等待的写成 `async`。
- Loopback Server 的启停不需要状态机：socket 操作全在 L 上按提交顺序发生，`stop(); start()` 在同一个 tick 内也正确。
