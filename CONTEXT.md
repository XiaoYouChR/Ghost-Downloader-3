# Ghost Downloader

基于 PySide6 的多协议下载器。桌面端（Windows、macOS、Linux）和 Android 共享同一业务引擎，浏览器扩展捕获资源并发送到应用。

## Language

### 任务

**Task**:
用户可见的下载项。拥有 Name（成品文件的基本名）和 Output Folder（下载目标目录）。
五个状态：WAITING、RUNNING、PAUSED、COMPLETED、FAILED。持久化为 Task Record。
_Avoid_: download、job；Name 不叫 title 或 filename；Output Folder 不叫 directory

**Saved Tasks**:
应用启动时从上次运行加载的 Task Record。

**Task Files**:
一个 Task 产生的下载文件和分片临时文件。
_Avoid_: 与 Selectable File 混淆

**Name Conflict**:
新 Task 的 Name 在 Output Folder 中已被占用。以磁盘为准：路径上有文件或文件夹即被占用。
处理方式（Choice）有三种：保留两者（新 Task 改用带序号的 Name）、覆盖（旧文件移到回收站；移不了则退回保留两者）、询问（弹出对话框由用户选择）。
占用者是未完成的 Task 时不适用 Choice，总是保留两者。
Name 在 Task 加入时确定，Task Run 不改 Name。
_Avoid_: 重名、duplicate（留给重复链接）

**Placeholder**:
Task 加入时为它将产出的每个最终路径（成品和 Side File）创建的空文件或空文件夹，用来占住 Name。
任一路径被占用即为 Name Conflict。Task 存在期间一直持有，Task 被移除时释放。
_Avoid_: 占位符文件、lock file

**Side File**:
随成品一起产出、以成品 Name 为前缀的附属文件——字幕、封面、种子文件。
_Avoid_: side product、sidecar；与 Selectable File 混淆

**Part Path**:
最终路径旁存放其未完成数据的 `{最终路径}.ghd`。只有进度记录时是文件，还有中间文件时是文件夹。
成品原地写入 Placeholder。Task 完成后 Part Path 被删除；Task 被移除时，未完成的输出和 Part Path 总是删除，"删除文件"只决定已完成的成品。
_Avoid_: Part Folder、work folder、temp、cache、Staging（Staging 指更新下载物）

**Replace**:
新 Task 取得旧 Task Record 的路径时，旧 Task Record 被移除、由新 Task 顶替。只移除记录，不删磁盘。
_Avoid_: merge、overwrite（覆盖指磁盘文件）

**Pausable**:
Task 的可暂停性，派生属性。取决于当前运行 Step 是否支持断点恢复。

**Checksum**:
用户为已完成成品按选定算法算出的校验值。每种算法各存一份，随 Task Record 持久化，重新下载时清空。
计算 Checksum 不是 Task Run，不改变 Task 状态。
_Avoid_: hash、digest、哈希值

**Task Error**:
任务执行过程中的已知失败——服务器错误、磁盘空间不足、运行时未安装等。Task 有单一错误边界。

### 文件选择

**Selectable File**:
多文件 Task 内的一个可勾选下载单元——仓库文件、播放列表视频、多分 P 页面或种子文件。
任何 Task 状态下都允许改变选择；取消选择的文件保留部分进度。
Task 有多于一个 Selectable File 时，成品是以 Name 命名的文件夹；只有一个时，成品就是这个文件本身。
_Avoid_: 与 Task Files 混淆

**Revive**:
已完成的 Task 因新选中的文件有待下载工作而回到下载状态。仅对 COMPLETED 状态的 Task 生效。

### 任务创建

**Task Options**:
用于解析、创建或编辑 Task 的应用层选项。
_Avoid_: payload（仅在原始传输 seam 使用）

**Task Parser**:
FeaturePack 提供的能力，将 Task Options 转为 Task。声明优先级和匹配规则。

**Task Draft**:
用户确认前的未确认任务状态。内含一个或多个 Draft Item，每个 Draft Item 跟踪一条 URL，
处于三个状态之一：Parsing、Resolved（持有 Task）、Failed。Failed 不是终态。
_Avoid_: pending task、unconfirmed task

**Resource**:
浏览器扩展捕获的可下载物。由 Browser Service 转换为 Task Options 进入任务创建流程。
_Avoid_: 与泛义"资源"混淆

### 任务执行

**Task Run**:
Task 在下载循环中的当前执行。一个 Task 同时只有零或一个活跃的 Task Run。
_Avoid_: execution、session

**Seeding**:
已完成的 Task 继续向他人提供其成品。不是 Task Run，不占任务槽，Task 保持 COMPLETED。
用户可随时开关；到达上限或用户关掉后不再自动恢复，否则随应用启动恢复。
_Avoid_: 与 Seed（Pack 同步）混淆；sharing；第六个 Task 状态

**Bootstrap List**:
Pack 从订阅地址拉取、用来发现对等方的列表：BT 的 Tracker 列表，eD2k 的服务器列表和 KAD 节点列表。
由应用拉取并缓存，Pack 自带内置快照，任何时候都有一份可用；刷新只在后台进行，Task 从不等它。
_Avoid_: Source（指更新分发）、节点源、mirror

**Task Step**:
Task 内的一个可执行步骤。一个 Task 可能有一个或多个 Step。
_Avoid_: stage、phase、action

**Subworker**:
HTTP 或 FTP Step 内的一个分片传输单元，负责一个 byte-range 区间。
_Avoid_: worker、thread、chunk

### 用户告知

**Notice**:
一次性的、需要告知用户的事件。发出即完成，不可撤回也不需要消解。
_Avoid_: message、alert、event

**Pair Request**:
待决的浏览器配对请求，有始有终——用户批准或拒绝后消解。同时只有零或一个。
_Avoid_: 与 Notice 混淆（Notice 发出即完成，Pair Request 会被消解）

**Pair Token**:
Browser Service 与浏览器扩展共享的连接凭证，Pairing 的产物。
_Avoid_: 密钥、密码、token

### 应用角色

**Task Service**:
拥有用户可见任务工作流的唯一公共入口。
_Avoid_: 直接操作 Task 的状态转换

**Feature Service**:
拥有 pack 发现、parser 优先级路由和 pack 生命周期。将 Task Options 路由到匹配的 Parser。

**FeaturePack**:
全栈垂直切片——从 parser 到 card 自包含。可提供 task parser、card、file type、binary runtime、page 或 setting group。
_Avoid_: module、extension

**Binary Runtime**:
FeaturePack 可探测、安装和卸载的外部可执行文件家族。安装由 Binary Runtime 自己完成，不是 Task。
_Avoid_: 安装任务

**Install Folder**:
用户为一个 Binary Runtime 选定的文件夹。应用不独占它：安装只覆盖该 Runtime 自己的文件，卸载只删除这些文件，其他内容不动。
_Avoid_: 运行时目录、安装路径

**Browser Service**:
浏览器扩展的协议适配器：接收扩展消息，翻译为 Task Service 动词，返回结果。

**Clipboard Listener**:
剪贴板监听器。监控剪贴板变化，过滤出 URL 后发出通知。

**Category**:
下载分类和目标目录规则。将文件扩展名匹配到分类并解析下载目录。
_Avoid_: group、tag、type

**Coroutine Runner**:
运行异步工作并桥接回 UI 线程的应用 actor。

**Speed Meter**:
全局下载速度监视器与限速门控。

**Signal Bus**:
进程级事件总线。只承载跨模块的应用级事件，不承载任务或业务信号。

**Client**:
带可选 TLS 指纹模拟的 HTTP 客户端。

**Plan**:
"所有任务完成后做 X" 的意图：关机、重启、休眠或打开文件。

**Settings**:
应用级用户配置。
_Avoid_: options（options 是每个 Task 的输入，不是应用配置）

### 应用更新

**App Dir**:
正在使用的安装目录。
_Avoid_: install dir、program folder

**Portable Folder**:
App Dir 内名为 `GhostDownloader` 的目录。Portable 模式下数据住在这里。
_Avoid_: 单独说 GhostDownloader 文件夹

**Seed Features**:
App Dir 内 `features/` 目录。只读的出厂默认 Pack 集合，运行时不修改。
_Avoid_: factory packs、bundled packs

**Features Dir**:
APP_DATA_DIR 内 `features/` 目录。可变的 Pack 运行时目录。
_Avoid_: 与 Seed Features 混淆

**Seed**:
启动时按版本号将 Seed Features 同步到 Features Dir。版本低于种子的 Pack 被覆盖，高于或等于种子的保留。
_Avoid_: copy、sync、migrate

**Uninstaller**:
Inno Setup 写在 App Dir 里的卸载程序与日志。
_Avoid_: setup、installer

**Patch**:
一份目录级增量文件。
_Avoid_: delta、diff

**Staging**:
更新下载物的落地目录。
_Avoid_: cache、temp

**New Dir**:
App Dir 旁已经打好的新树。
_Avoid_: dest、out

**Backup Dir**:
App Dir 改名让出后的旧树。
_Avoid_: old、prev

**Updater**:
进程外的更新程序：等应用退出后做 Patch 与 Install。
_Avoid_: helper、installer

**Apply**:
退出时把已就绪的更新交出去：Pack 暂存到 Features Dir，应用则启动 Updater。
_Avoid_: install、commit

**Install**:
Updater 把 New Dir 换成 App Dir。
_Avoid_: swap、rename、deploy

**Restructure**:
macOS 上 Install 后，Updater 在 `Contents/MacOS/` 为 `Contents/Resources/` 的每个条目创建 symlink。
_Avoid_: relocate、move

### 更新分发

**Origin**:
应用更新与附属二进制的权威托管方。当前是 GitHub。
_Avoid_: source of truth 单独当术语；不叫 primary / 主镜像

**Source**:
客户端竞速拉取更新元数据和资产的一个托管端点。当前集合是 github 与 gitcode。
_Avoid_: Mirror、CDN、channel

## Example dialogue

> **Dev:** "用户按暂停时，我们删除 Task 吗？"
> **Domain expert:** "不。Pause 停止 Task Run。Task Record 和 Task Files 保留。"

> **Dev:** "用户按重新下载时，我们创建新 Task 吗？"
> **Domain expert:** "不。Redownload 停止 Task Run、删除 Task Files、重置同一个 Task、启动新的 Task Run。"
### GitHub 加速

**Proxy Site**:
把 GitHub 文件 URL 作为路径前缀转发下载的第三方反向代理。
_Avoid_: Mirror、Source、CDN

**Auto Site**:
选站方式之一：每个任务解析时让直连与全部 Proxy Site 竞速，取第一个合格响应。不跨任务记忆胜出者。
_Avoid_: 测速、最快站（不比较全部结果）

