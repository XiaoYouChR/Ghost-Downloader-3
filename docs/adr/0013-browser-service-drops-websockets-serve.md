# Browser Service 不用 websockets.serve

Browser Service 与 Aria2 RPC Server 都挂在 Loopback Server 上，由它统一跟踪、关闭连接；WebSocket 由共享的
WebSocketStream（websockets 的 Sans-I/O `ServerProtocol` 加 asyncio 流）实现。Aria2 必须在同一端口上同时服务 HTTP POST 和 WebSocket，
而 `websockets.serve` 无法处理带 body 的 POST，所以 Aria2 本来就需要 Sans-I/O；让 Browser Service 也用它，
连接生命周期和 RFC 6455 行为各只有一份实现。

## Considered Options

- **Loopback Server 以 `open(sockets) -> Listening` 为 seam，Browser 保留 `websockets.serve`**：每个适配器都要自己实现「关闭时带走全部连接」，
  而这正是 uvloop 下 Aria2 停止后 WebSocket 连接仍然存活的缺陷所在。
