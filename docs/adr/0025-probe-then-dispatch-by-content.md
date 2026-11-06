# probe 之后按内容重新分派；Relink 只换同一文件的地址

压缩包、种子、流媒体清单要按链接背后文件的内容认领，而文件是什么只有 probe 之后才知道（如 `download.aspx?file=x` 返回的 zip）。
我们让来源 parser（HttpParser、GitHubParser）probe 后把 `file` 填进 Task Options，经 `parser.delegate` 再分派一次；格式 parser 按 `file` 的名字和类型认领，无人认领或认领后解析失败时，Feature Service 继续向后分派并回落为普通文件。
Relink 是"同一个文件换一个新地址"，直接将新链接 `parse` 出的 Task 交给原 Task 的 `relink` 校验并替换底层下载步骤；种类不合或内容不一致时一律拒绝（#1015）。

## Considered Options

- **Route：把 Proxy Site 下沉到请求层，格式 parser 按 URL 后缀抢先认领**：无后缀的链接认不出来；还要改 10 个 pack 的 `run` 签名、迁移 GitHub 旧记录。
- **FileParser：来源 parser probe 后把文件交给格式 pack**：每个来源 parser 都要记得转交，m3u8 需要原链接、被动识别要伪造文件对象，seam 位置不对。经 `parser.delegate` 再次分派后，无需新接口。
- **在 Feature Service 上另设 `probe` 与 `probeRelink` 接口，把预建的 `HttpTaskStep` 塞进 `TaskOptions.template`**：将传输实现泄漏到了模型层，且每个改写或加速链接的 parser 都要重复实现一套 `probe`；收敛为单一的 `parse` + `delegate` 后，Relink 直接复用 `parse`。

## Consequences

- GitHubParser 排在格式 parser 之前（priority 75），GitHub 上的 zip、种子、m3u8 先选站再按内容认领；它只为未 probe 的链接选站。
- 浏览器扩展给出名字和大小的资源不额外发起 `probe`；其中已标明支持 Range 的资源（非一次性链接）直接构造 `RemoteFile` 经 `delegate` 按内容分派，不支持 Range 的直接按普通文件处理，避免一次性链接被多余的请求耗掉。
- `Task.relink` 接收新解析出的 Task；只有支持更换链接的 Task（`HttpTask`、`ZipTask`、`FFmpegTask`）实现 `relink`，且只接受同一文件的新地址。
