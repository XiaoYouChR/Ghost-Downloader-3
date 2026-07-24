# Ghost Downloader Browser Extension

Chromium / Firefox 浏览器扩展。捕获页面中的可下载资源，通过持久连接发送到桌面应用。

与桌面应用共享 **Resource** 和 **Task Options** 的定义（见根目录 CONTEXT.md）。

## Language

### 上游依赖

**cat-catch**:
嵌入的第三方开源扩展，提供三个能力面：
DOM 媒体发现（addMedia 通道）、媒体播放控制（getVideoState 协议）、功能脚本库（recorder、webrtc 等）。
MSE Probe 参照 cat-catch 重写为独立实现，只发信号不缓存数据。
_Avoid_: 把 cat-catch 功能与自研 Page Media 系统混为一谈

### 桌面连接

**Desktop Bridge**:
与桌面 Browser Service 的持久连接。支持断线自动重连和离线排队。
离线期间下载请求排入 Task Queue，重连后自动 flush。
_Avoid_: desktop connection、socket

**Pairing**:
Desktop Bridge 建立连接前的授权流程。用户在桌面端确认授权后，扩展获得连接凭证。

**Task Queue**:
扩展侧的离线发送队列。Desktop Bridge 不可达时缓存下载请求，重连后逐条发送。
_Avoid_: 与桌面应用的 Task Queue 混淆——这里是扩展侧的离线缓冲

**Connection State**:
Desktop Bridge 的连接状态：missing\_token、connecting、authenticating、
connected、unauthorized、disconnected。Popup UI 据此显示连接指示器。

**Task Summary**:
桌面推送的任务摘要。扩展不拥有 Task，只拥有 Task Summary 作为任务状态的只读视图。

### 资源捕获

**Resource Bridge**:
资源捕获器。从网络请求和页面脚本（cat-catch）两个途径捕获可下载资源，
缓存到 Resource Cache 后转换为桌面可理解的 Task Options。
_Avoid_: resource manager

**Resource Cache**:
已捕获资源的内存缓存。同时保存 Header Snapshot——网络请求的请求头快照，
让桌面端能复用浏览器的认证凭据下载需要登录的资源。
_Avoid_: resource store、resource map

### 页面媒体

**Page Media**:
Content script 侧的媒体检测和归因系统。检测页面中正在播放的媒体，将网络 URL
归因到具体的 video 元素，为用户提供下载按钮。由四个协作层组成：
MSE Probe → Attribution Engine → Download Button，Resolution Strategy 提供按站点的解析逻辑。
同一个 URL 可能同时存在于 Resource Cache（作为 Resource）和 Attribution Engine
（作为 Video Session 的归因 URL）。Popup 资源面板走 Resource 路径，Download Button 走 Page Media 路径。

**MSE Probe**:
观察浏览器媒体流内部机制，将事件通过 Attribution Signal 报告给 Attribution Engine。
拦截对象 URL 创建、缓冲区添加、数据追加和网络请求，
以建立"哪个网络请求喂了哪个播放器"的关联。

**Attribution Signal**:
MSE Probe 与 Attribution Engine 之间的跨执行环境通信通道。
两者运行在不同的脚本隔离环境中，Signal 是唯一桥接机制。

**Attribution Engine**:
将网络 URL 归因到播放中的 video 元素。核心数据模型是 Video Session。
使用 Attribution Tier 判断归因置信度，使用 Attribution Ledger 仲裁 URL 所有权争议。

**Video Session**:
Attribution Engine 中一个 video 元素的生命周期追踪单元。
状态：inert → armed → ready → waiting → resolving → dispatched / failed / refused。
追踪归因到该视频的所有 URL。
_Avoid_: video tracker、media session

**Attribution Tier**:
归因置信度分级。决定 URL 归属的优先级——从最高置信（缓冲追加确认）
到最低（唯一 session 兜底）。高 tier 可以从低 tier 夺取 URL 所有权。

**Attribution Ledger**:
跨 session 的 URL 所有权账本。仲裁多个 Video Session 争抢同一 URL 的情况
（如预加载场景中多个视频共享相同的 CDN URL）。

**Download Button**:
悬浮在活跃媒体上的下载按钮。点击时请求 Attribution Engine 解析，
获取 Resolution 后发送到 Resource Bridge 转发给桌面。

**Resolution Strategy**:
按站点分发的下载解析逻辑（YouTube、X、Douyin、Instagram、generic）。
纯函数，不能回调 Attribution Engine。输出 Resolution。

**Resolution**:
Resolution Strategy 的输出。三种结果：
selection（下载决定）、pending（等待更多信息）、refused（拒绝处理）。

**Selection**:
Resolution 中的下载决定。四种形态：
single（单文件）、stream（流媒体段）、merge（视频+音频合并）、external（交给桌面端外部工具处理）。

### 媒体控制

**Media Bridge**:
媒体播放控制。通过 cat-catch content script 获取视频播放状态和发送控制命令。
Media Snapshot 是单一真相源。

**Media Snapshot**:
当前 tab 的媒体播放状态快照。包含播放列表、当前索引、播放/暂停状态。
消除多数据源的状态分裂。

### 功能开关

**Feature Bridge**:
每个 tab 的功能开关管理。开关分两类：动态注入型（切换后立即生效）
和需要刷新型（切换后需重新加载页面）。持久化到本地存储；加载时与活跃 tab 列表调和。

### Popup 通信

**Popup Protocol**:
Popup 与 background 之间的类型化通信协议。
命令分两类：StateCommand（查询状态）和 ActionCommand（执行动作）。
_Avoid_: popup API、popup bridge
