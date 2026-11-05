# probe 之后按内容重新分派；Relink 只走 probe

压缩包、种子、流媒体清单要按链接背后文件的内容认领，而文件是什么只有 probe 之后才知道（如 `download.aspx?file=x` 返回的 zip）。
我们让来源 parser（HttpParser、GitHubParser）probe 后把 `file` 和 `template` 填进 Task Options，经 `pack.parse` 再分派一次；格式 parser 按 `file` 的名字和类型认领，无人认领或认领后解析失败时，来源 parser 回落为普通文件。
Relink 是"同一个文件换一个新地址"，只需 probe 的结果，不再创建 Task，因而不会因按内容识别而改变 Task 的种类（#1015）。

## Considered Options

- **Route：把 Proxy Site 下沉到请求层，格式 parser 按 URL 后缀抢先认领**：无后缀的链接认不出来；还要改 10 个 pack 的 `run` 签名、迁移 GitHub 旧记录。
- **FileParser：来源 parser probe 后把文件交给格式 pack**：每个来源 parser 都要记得转交，m3u8 需要原链接、被动识别要伪造文件对象，seam 位置不对。复用 `pack.parse` 后只剩 HttpParser 与 GitHubParser 两处，且无需新接口。
- **Relink 仍然重新解析，用标志关掉按内容分派**：Task 与 Task Options 各多一个字段，还要检查种类是否改变；Relink 本来就不需要回答"这是什么"。

## Consequences

- GitHubParser 排在格式 parser 之前（priority 75），GitHub 上的 zip、种子、m3u8 先选站再按内容认领；它只为未 probe 的链接选站。
- 浏览器扩展给出名字和大小的资源仍不 probe，也就不按内容识别，避免一次性链接被多余的请求耗掉。
- `Task.canReuseProgress` 与 `Task.replaceWith` 接收 probe 后的 Task Options；只有提供 Relink 的 Task 实现 `replaceWith`。
