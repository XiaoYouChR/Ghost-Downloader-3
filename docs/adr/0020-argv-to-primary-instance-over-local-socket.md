# 后启动的进程经 local socket 把 argv 交给 Primary Instance

桌面上所有后启动的进程——`ghd` 子命令、关联启动、重复打开——都把自己的 argv 和工作目录原样交给 Primary Instance，
由它解析、执行并回复输出与退出码；argv 语法只在 Primary Instance 一处定义。通道是一条 `QLocalServer`，每个连接一问一答。
后启动的进程连上就交出 argv；连不上就抢锁，抢不到就等胜者开门。没有 Primary Instance 时，`ghd` 静默拉起一个，同样等它开门。
这是 GApplication 的命令行转发模型。

## Considered Options

- **复用各平台原生通道**（WM_COPYDATA、D-Bus、QFileOpenEvent）：只有 D-Bus 能带回结果；Windows 要再建一个回程窗口；
  macOS 第二个实例根本不转发，要从零做。三套传输，且都是 Agent 需要回执时才缺的那部分。
- **客户端自己解析命令，发结构化请求**：命令结构写两遍，客户端和 Primary Instance 必须同步升级。
- **拉起的实例把回复写到 stdout**：抢不到锁的进程本来就要等胜者开门，再为冷启动维护一条 stdout 协议是第二套机制。

## Consequences

- 取代 WM_COPYDATA 和 `_sendToRunningLinux`。D-Bus 接收端（`DBusActivatable`）和 QFileOpenEvent 由操作系统调用，保留，
  收到的 URI 同样交给 Primary Instance 的 argv 入口。
- 占锁后立即开始接收，就绪后才执行：服务就绪前到达的请求按到达顺序排队，启动期间打开的文件和链接不会丢失。
- QSharedMemory 单实例锁保留：Windows 上 `listen` 不排他，不能兼作锁。清理崩溃残留只在 1 秒无人应答后才做：
  `QSharedMemory::create` 加锁前会重置 Qt 的系统信号量，并发启动时提前清理会删掉胜者刚建的段，出现两个 Primary Instance。
- 锁在 Engine 写完数据之后才释放，新的 Primary Instance 不会和正在退出的进程同时写任务。
- 锁和 socket 按用户区分（Unix 用 uid），与锁 key 为 `DESKTOP_ID` 的旧版本不再互斥。
- 以 `ghd` 调用的 argv 一律是子命令：打错的子命令报用法错误，不回落为打开链接，
  否则没有 Primary Instance 时，打错命令的进程会在 Agent 的 shell 里启动成 GUI。
- stdout 是终端时只把 JSON 缩进显示，不像 gh 那样换成表格：有的 Agent 在伪终端里执行命令，按 TTY 切换输出格式会让它们拿不到 JSON。
