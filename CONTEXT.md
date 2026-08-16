# Ghost Downloader

基于 PySide6 的多协议下载器。桌面端（Windows、macOS、Linux）和 Android 共享同一业务引擎，浏览器扩展捕获资源并发送到桌面应用。

## Language

### 任务

**Task**:
用户可见的下载项。拥有 Name（成品文件的基本名）和 Output Folder（下载目标目录）。
单文件任务的最终路径为 Output Folder / Name；多文件任务为包含各文件的目录。
五个状态：WAITING（排队等待）、RUNNING（正在下载）、PAUSED（用户暂停）、COMPLETED（已完成）、FAILED（失败）。
持久化为 Task Record；应用启动时从上次运行加载的 Task Record 称为 Saved Tasks。
_Avoid_: download、job；Name 不叫 title 或 filename；Output Folder 不叫 directory

**Task Files**:
一个 Task 产生的下载文件和分片临时文件。
_Avoid_: 与 Selectable File 混淆

**Pausable**:
Task 的可暂停性，派生属性。取决于当前运行 Step 是否能从断点恢复
（对传输类 Step，取决于服务器是否支持 byte-range）。

**Task Error**:
任务执行过程中的已知失败——服务器错误、磁盘空间不足、运行时未安装等。
携带用户可见的消息模板（同时作为 i18n key）和格式化参数。Task 有单一错误边界。
失败后 Step 上记录 Step Error（message + params），仅运行时存在，不持久化。

### 文件选择

**Selectable File**:
多文件 Task 内的一个可勾选下载单元——仓库文件、播放列表视频、多分 P 页面或种子文件。
通过稳定索引标识，索引不随选择变化。改变选择不创建或销毁 Step，任何 Task 状态下都允许；
取消选择的文件保留部分进度。
_Avoid_: 与 Task Files 混淆

**Revive**:
已完成的 Task 因新选中的文件有待下载工作而回到下载状态。
清除完成时间戳并自动启动 Task。仅对 COMPLETED 状态的 Task 生效。

### 任务创建

**Task Options**:
用于解析、创建或编辑 Task 的应用层选项。
四种来源：浏览器 Resource、页面媒体、合并请求、二进制安装。
_Avoid_: payload（仅在原始传输 seam 使用）

**Task Parser**:
FeaturePack 提供的能力，将 Task Options 转为 Task。
声明优先级和匹配规则；高优先级的 Parser 先检查。

**Task Draft**:
用户确认前的未确认任务状态。内含一个或多个 Draft Item，每个 Draft Item 跟踪一条 URL，
处于三个状态之一：Parsing（解析中）、Resolved（解析成功，持有 Task）、Failed（解析失败）。
用户确认时尚在解析的 item 会在后台等待解析完成后自动提交（延迟确认）。
Task Service 不理解 draft 状态。
_Avoid_: pending task、unconfirmed task

**Resource**:
浏览器扩展捕获的可下载物。由 Browser Service 接收后转换为 Task Options 进入任务创建流程。
_Avoid_: 与泛义"资源"混淆

### 任务执行

**Task Run**:
Task 在下载循环中的当前执行。一个 Task 同时只有零或一个活跃的 Task Run。
Task Run 按待完成 Step 的顺序迭代 Task Step。
_Avoid_: execution、session

**Task Step**:
Task 内的一个可执行步骤。一个 Task 可能有一个或多个 Step。
_Avoid_: stage、phase、action

**Subworker**:
HTTP 或 FTP Step 内的一个分片传输单元，负责一个 byte-range 区间。
_Avoid_: worker、thread、chunk

### 应用角色

**Task Service**:
拥有用户可见任务工作流的唯一公共入口：add、start、pause、delete、
redownload、edit、setCategory、applySelection、resumeSaved、stop。
_Avoid_: 直接操作 Task 的状态转换

**Feature Service**:
拥有 pack 发现、parser 优先级路由和 pack 生命周期。
将 Task Options 路由到匹配的 Parser。若无 parser match，失败；
此失败发生在 Task 创建之前，不属于 Task Error。

**FeaturePack**:
全栈垂直切片——从 parser 到 card 自包含。可提供 task parser、card、file type、binary runtime、page 或 setting group。
Pack 内部依赖方向：cards（View）可 import task/config/session，反过来不行。engine 代码不知道 View 存在。
用户可见文本的 i18n 归 View 层——model 存机器可读 key，View 映射到翻译文本。error_catalog 是给 lupdate 的声明文件，不参与运行时。
_Avoid_: module、extension

**Binary Runtime**:
FeaturePack 可探测或提供安装任务的外部可执行文件家族。

**Browser Service**:
浏览器扩展的协议适配器：接收扩展消息，翻译为 Task Service 动词，返回结果。

**Clipboard Listener**:
剪贴板监听器。监控剪贴板变化，过滤出 URL 后发出通知。

**Category**:
下载分类和目标目录规则。将文件扩展名匹配到分类并解析下载目录。
_Avoid_: group、tag、type

**Coroutine Runner**:
运行异步工作并桥接回 UI 线程的应用 actor。对 Task 一无所知。

**Speed Meter**:
全局下载速度监视器。下载引擎喂入字节数据，聚合后每秒发出速度变更通知。
同时提供全局限速门控。

**Signal Bus**:
进程级事件总线。只承载跨模块的应用级事件，不承载任务或业务信号——那些在各自的 Service 上。

**Client**:
带可选 TLS 指纹模拟的 HTTP 客户端。

**Plan**:
"所有任务完成后做 X" 的意图：关机、重启、休眠或打开文件。

**Settings**:
应用级用户配置。
_Avoid_: options（options 是每个 Task 的输入，不是应用配置）


### 更新分发

**Origin**:
应用更新与附属二进制的权威托管方。构建、打 tag、发布资产以 Origin 为准。当前是 GitHub。
_Avoid_: source of truth 单独当术语；不叫 primary / 主镜像

**Source**:
客户端竞速拉取更新元数据和资产的一个托管端点。当前集合是 github 与 gitcode。
_Avoid_: Mirror、CDN、channel；CNB 不是 Source


## Example dialogue

> **Dev:** "用户按暂停时，我们删除 Task 吗？"
> **Domain expert:** "不。Pause 停止 Task Run。Task Record 和 Task Files 保留。"

> **Dev:** "用户按重新下载时，我们创建新 Task 吗？"
> **Domain expert:** "不。Redownload 停止 Task Run、删除 Task Files、重置同一个 Task、启动新的 Task Run。"
