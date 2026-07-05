# Runtime Update Service 实现总结

## 概述

本次重构将应用更新逻辑泛化为通用的 **BinaryRuntime 更新服务**，支持所有外部依赖运行时（yt-dlp, N_m3u8DL-RE, FFmpeg 等）的自动下载和安装。

## 设计决策

基于需求讨论，确定了以下设计方案：

1. **多实例并发模式** - 允许多个 Runtime 同时更新
2. **手动 + 自动触发** - 支持用户点击和启动时自动检查
3. **独立下载模式** - 使用 StateToolTip 显示进度，不进入任务队列
4. **松耦合集成** - 与 RuntimeStatusService 通过信号通信
5. **复用 installTask()** - 避免重复实现 Task 管理逻辑

## 新增文件

### 1. `app/services/runtime_update_service.py`
**核心业务服务**，负责管理所有 BinaryRuntime 的下载和安装。

**关键特性：**
- 多实例并发：每个 Runtime 独立下载，互不干扰
- 状态管理：`RuntimeUpdateStatus` 枚举（IDLE, CHECKING, AVAILABLE, DOWNLOADING, SUCCEEDED, FAILED）
- 进度追踪：每秒查询任务进度并通过信号发送
- 信号驱动：
  - `progressChanged(runtimeId, progress, speed)` - 进度更新
  - `downloadSucceeded(runtimeId, installedPath)` - 下载成功
  - `downloadFailed(runtimeId, errorMessage)` - 下载失败
  - `updateAvailable(runtimeId, updateInfo)` - 有可用更新

**主要方法：**
- `downloadRuntime(runtime: BinaryRuntime)` - 启动下载
- `isDownloading(runtimeId: str)` - 检查下载状态
- `cancelDownload(runtimeId: str)` - 取消下载

### 2. `app/view/components/runtime_update_cards.py`
**UI 组件**，提供运行时更新的用户界面。

**包含两个类：**

#### `RuntimeUpdatePrompt`
管理运行时下载的 UI 提示（StateToolTip 和 InfoBar）。

**方法：**
- `showProgress()` - 显示下载进度提示
- `updateProgress()` - 更新进度显示
- `showSuccess()` - 显示下载成功通知
- `showError()` - 显示下载失败通知

#### `BatchRuntimeUpdateCard`
批量运行时更新卡片，在设置页面显示。

**功能：**
- "检查全部更新" 按钮 - 刷新所有运行时状态
- "全部更新" 按钮 - 批量启动所有可安装运行时的下载

## 修改的文件

### 1. `app/view/components/setting_cards.py`
**修改 `RuntimeCard` 类**，集成新的更新服务。

**变更：**
- 添加 `_stateToolTip` 成员变量
- 修改 `_onInstallClicked()` - 使用 `RuntimeUpdateService` 替代直接创建任务
- 添加进度回调方法：
  - `_onUpdateProgressChanged()` - 更新进度显示
  - `_onUpdateSucceeded()` - 处理下载成功
  - `_onUpdateFailed()` - 处理下载失败
- 显示 StateToolTip 实时进度而非静态 InfoBar

### 2. `app/view/pages/setting_page.py`
**在设置页面添加运行时管理组**。

**变更：**
- 修改 `_initLayout()` - 添加 `_addRuntimeUpdateGroup()` 调用
- 新增 `_addRuntimeUpdateGroup()` 方法 - 创建运行时管理设置组，包含批量更新卡片

### 3. `app/services/feature_service.py`
**扩展 FeatureService**，提供运行时收集功能。

**变更：**
- 新增 `runtimes()` 方法 - 遍历所有 Feature Pack，收集它们的 BinaryRuntime 实例

### 4. `app/config/paths.py`
**添加更新目录常量**。

**变更：**
- 新增 `UPDATE_DIR = f"{APP_DATA_DIR}/update"` - 统一的临时下载目录

### 5. `app/startup.py`
**添加运行时更新检查和清理逻辑**。

**变更：**
- 新增 `checkRuntimeUpdatesAtStartup()` - 启动时检查所有运行时状态
- 新增 `_cleanupUpdateDirectory()` - 清理 update 目录中的临时文件
- 修改 `startEngine()` - 调用清理函数
- 修改 `stopEngine()` - 退出时再次清理

### 6. `Ghost-Downloader-3.py`
**主程序集成**。

**变更：**
- 导入 `checkRuntimeUpdatesAtStartup`
- 在 `startApp()` 中调用 `checkRuntimeUpdatesAtStartup()`

## 工作流程

### 手动触发流程

1. 用户在设置页面的 `RuntimeCard` 点击"一键安装"
2. `RuntimeCard._onInstallClicked()` 调用 `runtimeUpdateService.downloadRuntime(runtime)`
3. `RuntimeUpdateService` 创建下载任务：
   - 调用 `runtime.installTask()` 创建任务
   - 设置输出目录为 `UPDATE_DIR`
   - 启动任务运行
   - 启动定时器查询进度
4. 每秒触发 `_onTick()`，发送 `progressChanged` 信号
5. `RuntimeCard` 监听信号，更新 `StateToolTip` 显示
6. 下载完成：
   - 发送 `downloadSucceeded` 信号
   - 关闭 `StateToolTip`
   - 显示成功 `InfoBar`
   - 刷新运行时状态

### 批量更新流程

1. 用户在设置页面点击"检查全部更新"
2. `BatchRuntimeUpdateCard._onCheckAllClicked()` 刷新所有运行时状态
3. 用户点击"全部更新"
4. `BatchRuntimeUpdateCard._onUpdateAllClicked()` 遍历所有运行时：
   - 跳过不支持自动安装的
   - 跳过已在下载中的
   - 调用 `runtimeUpdateService.downloadRuntime()` 启动下载
5. 每个运行时独立并发下载，互不干扰

### 启动自动检查流程

1. 应用启动，`checkRuntimeUpdatesAtStartup()` 被调用
2. 遍历所有运行时，调用 `runtimeStatusService.refresh(runtime)`
3. 异步探测每个运行时的版本信息
4. 用户进入设置页面时，看到最新的运行时状态

## 与现有系统的集成

### 与 RuntimeStatusService 的关系

- **职责分离**：
  - `RuntimeStatusService` - 探测版本、管理状态显示
  - `RuntimeUpdateService` - 下载安装、管理下载任务
  
- **松耦合通信**：
  - 下载完成后，`RuntimeCard` 调用 `runtimeStatusService.refresh()` 刷新状态
  - 不直接修改彼此的内部状态

### 与 TaskService 的关系

- **完全独立**：
  - Runtime 更新不进入 `TaskService` 的任务队列
  - 使用独立的下载逻辑，用户无需在任务页面管理
  - 通过 `StateToolTip` 实时显示进度

### 与应用更新的对比

|  | 应用更新 | Runtime 更新 |
|---|---|---|
| **触发方式** | 启动时检查 + 手动 | 启动时刷新状态 + 手动 + 批量 |
| **下载模式** | 独立下载 | 独立下载 |
| **进度显示** | StateToolTip | StateToolTip |
| **完成操作** | 弹窗询问安装 | 自动完成 + 通知 |
| **任务队列** | 不进入 | 不进入 |
| **并发支持** | 单例 | 多实例并发 |

## 目录结构

```
update/                     # 临时下载目录（启动和退出时自动清理）
├── yt-dlp.exe             # 下载中的运行时文件
├── N_m3u8DL-RE.zip        # 下载中的压缩包
└── ...

GhostDownloader/
├── YtDlp/                 # yt-dlp 最终安装位置（由 YtDlpConfig 控制）
│   └── yt-dlp.exe
├── M3U8DL/                # N_m3u8DL-RE 最终安装位置
│   └── N_m3u8DL-RE.exe
└── ...
```

## 优势

1. **用户体验优化**
   - 实时进度显示，无需查看任务页
   - 批量操作，一键更新所有运行时
   - 自动清理临时文件

2. **代码复用**
   - 直接复用 `runtime.installTask()`，避免重复实现
   - 参考应用更新的成熟设计模式

3. **架构清晰**
   - 业务/视图分层明确
   - 信号驱动，松耦合
   - 多实例并发，互不干扰

4. **扩展性强**
   - 新增 Runtime 无需修改更新服务
   - 易于添加版本比对、自动更新等功能

## 未来可扩展功能

1. **版本比对**
   - 在 `checkUpdate()` 中实现版本检查逻辑
   - 仅提示有新版本的运行时

2. **自动更新**
   - 添加配置项控制是否自动更新
   - 检测到新版本后自动下载

3. **更新通知**
   - 启动时显示有可用更新的通知
   - 系统托盘通知

4. **更新日志**
   - 显示每个运行时的更新说明
   - 版本变更历史

## 测试建议

1. **手动下载测试**
   - 在设置页面点击各个 Runtime 的"一键安装"
   - 验证 StateToolTip 显示进度
   - 验证下载完成后状态刷新

2. **批量更新测试**
   - 点击"检查全部更新"
   - 点击"全部更新"
   - 验证多个运行时同时下载

3. **并发测试**
   - 同时点击多个 Runtime 的"一键安装"
   - 验证互不干扰

4. **清理测试**
   - 检查启动时 update 目录被清空
   - 检查退出时 update 目录被清空

5. **异常处理测试**
   - 网络中断时的行为
   - 磁盘空间不足时的提示
   - 下载失败后的错误显示

## 注意事项

1. **下载目录**
   - `UPDATE_DIR` 仅用于临时下载
   - 最终安装位置由各 Runtime 的 `installTask()` 内部逻辑决定

2. **兼容性**
   - 未修改任何现有的 Runtime 实现
   - 完全向后兼容

3. **资源清理**
   - 启动和退出时自动清理 update 目录
   - 避免磁盘空间浪费

## 提交信息建议

```
feat(runtime): 统一 BinaryRuntime 更新管理服务

- 新增 RuntimeUpdateService：多实例并发更新所有 BinaryRuntime
- 新增批量更新卡片：设置页面一键更新所有运行时
- RuntimeCard 集成新服务：实时进度显示，独立下载模式
- 启动时自动检查运行时状态，update 目录自动清理
- 复用 installTask() 逻辑，避免重复实现，架构清晰

参考 baf7c83..1ec147f 的应用更新优化设计。
```

---

**实现完成时间**: 2026-07-05  
**参考提交**: baf7c83 到 1ec147f（远程分支的应用更新优化）
