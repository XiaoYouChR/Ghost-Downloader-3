# Feature Pack V1 接口标准

状态: Accepted / V1 收口
日期: 2026-04-28
适用仓库: `Ghost-Downloader-3`

## 1. 文档目标

这份文档定义 Ghost Downloader 当前 Feature Pack 的 V1 标准。

截至 2026-04-28，V1 接口已经在仓库中落地，旧 `app.bases` V0 接口和旧 payload 修改链路已经移除。本文档不再作为迁移计划使用，而是作为后续 Feature Pack 开发和 Codex 自动化轮次的接口标准。

它服务三个目标：

- 为人工开发者提供统一接口标准
- 为 LLM Agent 提供长期稳定的决策依据
- 为社区开发者提供低样板、低心智负担的 Pack 开发体验

本文档不追求“概念很多”，而追求：

- 名字自然
- 结构简单
- 规则稳定
- 社区作者容易上手

## 2. 设计北极星

### 2.1 Simple is Better than Complex

本项目后续应持续遵守这些原则：

- 简单优于复杂
- 显式优于隐式
- 可读性优先
- 遇到歧义时，不要猜
- 如果一个设计很难解释，那大概率不是好设计

### 2.2 名字要描述用途，而不是实现

公开 API 的名字必须首先服务阅读。

后续命名必须尽量做到：

- 看到名字就能猜到职责
- 看到方法就能猜到输入和输出
- 看到文件名就能知道里面放什么
- 公开名字描述用途，而不是实现细节

### 2.3 V1 应优先建设“作者接口”，而不是“插件框架技巧”

Ghost Downloader 真正需要优先提供的，不是复杂的 matcher DSL、hook matrix 或 DAG 引擎，而是社区作者马上能用的作者接口：

- 清晰的基类名称
- 通用 `Task` / `TaskStage` 模型
- 明确的 `单文件` / `多文件` 任务基类
- 统一的任务配置修改接口
- 默认配置对话框与默认多项选择对话框
- SettingPage 设置卡片注入能力
- 默认 UI 和默认测试夹具

### 2.4 `Task` 是工作流，`TaskStage` 是步骤

从领域语义上看，当前的 `Task` 更接近工作流实例，而不是某个 Pack 独占的数据类型。

因此本文档采用以下判断：

- `Task` 是通用工作流容器
- `TaskStage` 是工作流中的原子步骤
- Feature Pack 的主要价值，应体现在 `TaskStage` 的实现和工作流组装上

### 2.5 信息传递采用 Actor 风格

后续整个 `Task` 工作流的信息传递，应采用 Actor 风格，而不采用“谁拿到引用谁就顺手改状态”的方式。

这里的关系必须说清楚：

- Qt `Signal / Slot` 是消息传递机制
- Actor Model 是状态所有权与消息处理纪律

两者不是同一个概念，但它们可以很好地配合。

## 3. 当前代码告诉我们的高收益方向

精读现有 `features/` 后，可以得出三个非常明确的结论。

### 3.1 `Matcher` 不是 V1 的高收益重点

各 Pack 判断 URL 的逻辑确实存在重复，但它们的代码量本来就不大，也不复杂。

因此本文档正式给出判断：

- V1 不提供专门的 `Matcher DSL`
- Pack 自己写少量 `accepts(url)` 判断是可接受的
- 这不是当前最值得投入工程成本的方向

### 3.2 真正的重复，集中在 `Task` / `TaskStage` 和配置修改

现有 Pack 的高重复结构主要是：

- `setTitle()` / `syncStagePaths()`
- `applyPayloadToTask()`
- 路径、标题、headers、proxies、分块数等配置向 Stage 传播
- 单文件任务与多文件任务的公共行为
- 默认卡片与少量特化卡片
- 多文件选择树对话框
- SettingPage 设置组与设置卡片

所以后续应该优先抽的，不是 matcher，而是：

- 基类名称和接口
- `单文件` / `多文件` 任务基类
- 运行前 / 运行中配置变更接口

### 3.3 社区作者真正需要的是“少写胶水代码”

Ghost Downloader 如果要支持社区生态，应该让社区作者把精力主要放在：

- 业务识别
- Stage 实现
- 工作流组装

而不是把时间浪费在：

- 任务骨架
- 配置传递
- 标题和路径同步
- 默认 UI 外壳
- 契约测试样板

## 4. V1 明确不做什么

为了保持 Taste，V1 需要主动克制。

V1 不优先做：

- matcher DSL
- capability matrix
- hook framework
- DAG workflow engine
- Pack-to-Pack 代码复用

这不是说这些方向永远不能做，而是它们不应早于更高收益的基础问题：

- 名字起对
- 任务基类抽对
- 配置修改接口抽对

## 5. 公开 API 的核心命名

这一节是 V1 的关键。

名字如果起错，后面所有 API 都会变得难读、难讲、难扩展。

### 5.1 顶层概念名称

后续建议稳定使用以下公共类型名：

- `FeaturePack`
- `TaskInput`
- `Task`
- `TaskStage`
- `SingleFileTask`
- `MultiFileTask`
- `TaskFile`
- `TaskConfig`
- `TaskForm`
- `SettingSection`
- `TaskSnapshot`
- `StageSnapshot`

### 5.2 为什么保留 `FeaturePack`

`FeaturePack` 这个名字虽然不算极致简短，但它有两个优点：

- 与项目现有术语一致
- 能容纳下载类 Pack 和 UI-only Pack

因此 V1 不建议把顶层概念改成更窄的名字，例如 `DownloadPack`。

### 5.3 为什么保留 `TaskStage`

`TaskStage` 比 `Step` 更贴近当前项目语境，也更容易和现有代码迁移对齐。

因此 V1 继续使用：

- `Task`
- `TaskStage`

不建议在 V1 同时引入 `TaskStep` 作为并行命名。

### 5.4 关键方法命名

建议公开方法逐步收敛到：

- `accepts(source: str) -> bool`
- `createTask(data: TaskInput) -> Task | None`
- `owns(task: Task) -> bool`
- `configure(config: TaskConfig) -> None`
- `editForm(mode: str) -> TaskForm | None`
- `snapshot() -> TaskSnapshot | StageSnapshot`

这些名字的共同点是：

- 都接近自然语言
- 都直接描述用途
- 都尽量不依赖实现细节

### 5.5 从现有名字迁移到目标名字

| 现有名字 | 目标名字 | 原因 |
|----------|----------|------|
| `canHandle(url)` | `accepts(source)` | 更短，也更接近 Python 社区常见谓词命名 |
| `parse(payload)` | `createTask(data)` | 输出本质上是 Task，而不是 parse 结果 |
| `canHandleTask(task)` | `owns(task)` | 这里表达的是归属，不是模糊处理能力 |
| `_featurePackName` | `packId` | 临时属性应变成正式身份字段 |
| `applyPayloadToTask(payload)` | `configure(config)` | 我们真正做的是提交一份正式配置 |
| `syncStagePaths()` | `syncOutput()` | 语义不只是 path，同步的是输出目标 |
| `preBlockNum` | `parallelChunks` | 更接近真实含义 |

## 6. 文件与模块命名

### 6.1 Python 文件名

推荐：

- `requests.py`
- `task.py`
- `stage.py`
- `task_config.py`
- `snapshots.py`
- `cards.py`
- `testing.py`

不推荐：

- `interfaces.py`
- `models.py`
- `helpers.py`
- `common.py`
- `utils.py`

### 6.2 Pack 元数据文件名

这里正式敲定：

- 每个 Feature Pack 的元数据文件统一使用 `manifest.toml`
- 元数据语义在文档和实现中统一称为 `manifest.toml`

后续不得再引入任何额外的 Python 元数据文件概念。

原因：

- `manifest.toml` 是静态、声明式、可读、可 diff 的元数据文件
- TOML 本身就适合做小而稳定的元数据描述
- Python 3.11 起标准库已有 `tomllib`
- 元数据不应依赖导入 Python 代码才能读取

## 7. Pack 的公开接口

V1 的 Pack 公开接口应保持小而清楚。

```python
class FeaturePack(ABC):
    manifest: object

    def accepts(self, source: str) -> bool:
        ...

    async def createTask(
        self,
        data: TaskInput,
    ) -> "Task | None":
        ...

    def owns(self, task: "Task") -> bool:
        ...
```

这三个入口足以覆盖当前宿主和大多数 Pack 的核心路径：

- 识别来源
- 构造任务
- 在恢复时识别任务归属

### 7.1 为什么这里不用复杂 capability

因为 V1 目前最重要的不是再拆很多接口，而是先把公共 API 讲清楚。

只有当这一层真正稳定后，再考虑更细的 capability 抽象才有意义。

### 7.2 UI 能力仍然是侧边能力

UI 相关能力可以继续存在，例如：

- `createTaskCard(...)`
- `createResultCard(...)`
- `load(...)`
- `settingSection()`

但必须明确：

- 它们不是 Pack 的主路径
- 它们不能反过来污染 `Task` / `TaskStage` 核心模型

## 8. `Task` 的基类层次

这是 V1 最该重点建设的部分。

### 8.1 总体判断

后续不应让每个 Pack 都先发明自己的 Task 子类世界，而应建立一个简单、稳定的层次：

```text
Task
  ├─ SingleFileTask
  └─ MultiFileTask
```

如果未来需要再细分，可在 `MultiFileTask` 之下再引入：

- `SelectableFilesTask`

但这不应妨碍 V1 先把 `SingleFileTask` 和 `MultiFileTask` 做稳。

### 8.2 `Task` 基类负责什么

`Task` 作为通用工作流基类，至少负责：

- 任务身份
- 所属 Pack 身份
- 工作流 Stage 列表
- 基础状态与进度
- 配置持有与配置变更入口
- 对 UI 暴露 Snapshot

建议至少包含这些正式字段：

- `taskId`
- `packId`
- `taskKind`
- `taskSchemaVersion`
- `title`
- `state`
- `stages`
- `currentStageIndex`
- `createdAt`
- `updatedAt`
- `config`

### 8.3 `Task` 基类的核心公开接口

建议 `Task` 基类至少提供：

- `configure(config: TaskConfig) -> None`
- `snapshot() -> TaskSnapshot`
- `setState(...)`
- `reset()`
- `canPause() -> bool`
- `iterStages()`
- `syncOutput()`

这里要特别说明：

- `configure()` 是未来统一配置变更入口
- `syncOutput()` 是对现有 `syncStagePaths()` 的语义升级

## 9. `SingleFileTask` 应该怎么抽

### 9.1 适用范围

`SingleFileTask` 适用于“逻辑上只产生一个最终输出目标”的任务。

典型例子：

- `http_pack`
- `github_pack`
- `m3u8_pack` 的最终媒体输出
- `ffmpeg_pack` 的媒体合并任务

### 9.2 `SingleFileTask` 应该提供什么

建议 `SingleFileTask` 在 `Task` 基础上补充：

- `path`
- `folder`
- `filename`
- `move(folder)`
- `rename(name)`

以及一个关键内部钩子：

- `syncOutput()`

这个基类应替 Pack 处理掉以下共性：

- 标题规范化
- 目标路径拼接
- 修改标题后同步 Stage 输出路径
- 修改下载目录后同步 Stage 输出路径

### 9.3 `SingleFileTask` 不应该做什么

它不应替 Pack 决定：

- 如何探测文件大小
- 如何下载
- 如何合并媒体
- 如何恢复特定进度文件

这些属于 Stage 层职责。

## 10. `MultiFileTask` 应该怎么抽

### 10.1 适用范围

`MultiFileTask` 适用于“逻辑上包含多个输出文件”的任务。

典型例子：

- `ftp_pack`
- `bittorrent_pack`

### 10.2 `TaskFile` 数据模型

建议引入正式的 `TaskFile`，承载多文件任务中的文件条目。

至少包含：

- `id`
- `path`
- `size`
- `selected`
- `doneBytes`
- `finished`

### 10.3 `MultiFileTask` 应该提供什么

建议 `MultiFileTask` 在 `Task` 基础上补充：

- `files: list[TaskFile]`
- `root`
- `selectedCount`
- `fileCount`
- `select(ids: set[str])`
- `syncOutput()`

如果未来需要，可继续细分：

- `SelectableFilesTask`

但 V1 先把 `MultiFileTask + TaskFile` 稳定下来更重要。

### 10.4 `MultiFileTask` 的基类职责

这个基类应替 Pack 处理掉以下共性：

- 多文件根目录计算
- 文件选择状态汇总
- 根据根目录变化同步 Stage 输出路径
- 多文件任务的基础摘要信息

### 10.5 `MultiFileSelectDialog` 应该成为宿主默认能力

当前 `FileSelectDialog` 已经说明这类对话框是高价值复用点，不应继续留在临时实现层。

V1 应正式提供：

- `MultiFileSelectDialog`

它的设计目标应是：

- 输入只依赖 `MultiFileTask.files`
- 默认提供树形勾选
- 默认提供全选 / 全不选 / 反选
- 默认提供按类型选择
- 允许额外显示 `note`

这样 `ftp_pack`、`bittorrent_pack`、`bili_pack` 都能共用同一套选择交互，而不是各写一份。

## 11. 任务配置模型

这是另一个 V1 的高收益重点。

现有代码里最痛的点之一，就是配置散在：

- `Task` 自己身上
- `TaskStage` 自己身上
- `applyPayloadToTask()`
- `syncStagePaths()`

后续必须收敛成正式模型。

### 11.1 推荐的最小配置结构

V1 不需要一口气拆出很多配置类，但至少应该先稳定：

- `TaskConfig`

推荐 `TaskConfig` 至少覆盖这些用户可编辑信息：

- `source`
- `headers`
- `proxies`
- `folder`
- `name`
- `chunks`

### 11.2 为什么只保留 `TaskConfig`

V1 不再保留额外的 patch 配置类型。

原因很直接：

- 类型更少
- 用户入口更少
- `dataclasses.replace()` 已经足够表达“基于旧配置改几个字段”
- 对社区作者和 LLM Agent 都更容易理解

## 12. 运行前 / 运行中配置变更的统一接口

用户已经明确希望支持：

- 下载中换链
- 下载前 / 中改代理
- 下载前 / 中改文件位置
- 下载前 / 中改请求头

这意味着后续设计必须把“配置变更”当成一等公民，而不是补丁逻辑。

### 12.1 对用户暴露的统一入口

对外应统一暴露：

- `configure(config: TaskConfig) -> None`

这是唯一的任务配置修改入口。

不再鼓励继续扩大：

- `applyPayloadToTask(payload)`

这种“把浏览器 payload 顺便当成配置修改协议”的写法。

### 12.2 对 Pack 作者暴露的简单能力

对 Pack 作者，基类应尽量简单。

推荐只暴露两个关键点：

- `Task.configure(config)`
- `TaskStage.configure(config)`

工作流内部建议这样流动：

1. UI 基于当前配置生成新的 `TaskConfig`
2. `Task` 替换自己的 `TaskConfig`
3. `Task` 更新自己的 Snapshot
4. `Task` 调用当前 Stage 的 `configure(config)` 或在下一个安全边界应用变更

### 12.3 为什么需要默认 `TaskConfigDialog`

Ghost Downloader 是 GUI 宿主，因此“可编辑配置”不能只停留在模型层。

V1 推荐默认提供：

- `TaskConfigDialog`

它的职责不是承载业务逻辑，而是把常见字段控件标准化：

- `folder`
- `name`
- `source`
- `headers`
- `proxies`
- `chunks`

Pack 或 Task 只需要声明一份小的 `TaskForm`，宿主就能自动渲染对话框。

只有在标准字段不够时，Pack 才应该写自定义 Dialog。

### 12.4 三类配置变更

为了让这个接口足够简单但仍可落地，后续把配置变更分成三类就够了：

- `immediate`
  当前 Stage 可以立刻吸收
- `next_stage`
  当前 Stage 不改，从下一个 Stage 开始生效
- `restart_stage`
  需要受控重启当前 Stage 才能生效

例如：

- 改代理:
  通常属于 `immediate` 或 `next_stage`
- 改 headers:
  通常属于 `immediate` 或 `next_stage`
- 改输出目录 / 文件名:
  通常属于 `restart_stage` 或 `next_stage`
- 下载中换链:
  通常属于 `restart_stage`

这三类已经足以覆盖大部分真实场景，没有必要在 V1 设计更复杂的分类系统。

### 12.5 为什么这样设计

这套设计同时满足三个要求：

- 对用户只有一个统一入口
- 对 Pack 作者只多一个 `configure(config)` 约定
- 对宿主仍然保留足够的控制力

它也符合 Actor / 工作流系统的常见经验：

- 改状态要通过消息进入状态拥有者
- 长流程运行中接收变更，应通过受控更新，而不是直接改共享字段

## 13. `TaskStage` 的配置接口

### 13.1 Stage 应该如何接收配置变更

后续 `TaskStage` 默认不直接暴露一堆散乱 setter。

推荐统一约定为：

- `configure(config: TaskConfig) -> None`

如果某个 Stage 不关心某些字段，就忽略即可。

### 13.2 为什么不用一堆专用 setter

例如：

- `setProxy(...)`
- `setHeaders(...)`
- `setOutputPath(...)`

这些 setter 看似直接，实际会让 Stage API 很快膨胀。

`configure(config)` 的优点是：

- 公开接口更小
- 未来字段增加时，基类不必频繁改接口
- `Task` 可以统一做 patch merge，再把完整配置下发

### 13.3 Stage 何时真正应用变更

这里的判断权应在 Stage 手里。

Stage 可以选择：

- 立刻应用
- 在下一次请求前应用
- 要求 Task 触发当前 Stage 重启

这比把所有判断都堆在 UI 或 Pack 里更合理。

## 14. Actor 风格的信息传递

### 14.1 核心判断

后续 `Task` 工作流中的对象，应遵守 Actor 风格的三条铁律：

- 状态有且只有一个拥有者
- 对外只通过消息通信
- 每个对象按顺序处理自己的消息

### 14.2 角色分工

在本项目中，建议按以下方式理解对象角色：

- `TaskStage`:
  actor-like worker。拥有 stage-local state，负责一步具体工作
- `Task`:
  workflow supervisor。拥有 task-level state，负责组装、推进、监督和汇总
- `TaskCard`:
  UI projection endpoint。负责展示状态、发出用户命令，不拥有工作流内部状态

### 14.3 推荐消息流

推荐的默认消息流如下：

```text
TaskCard --command--> Task
Task --command--> TaskStage
TaskStage --event--> Task
Task --snapshot/event--> TaskCard
```

### 14.4 Qt `Signal` 在这里扮演什么角色

Qt `Signal` 在这里承担的是消息通道角色，而不是共享状态角色。

推荐约束：

- `TaskCard` 用 `Signal` 发用户命令
- `TaskStage` 用 `Signal` 发阶段事件
- `Task` 用 `Signal` 发任务投影和任务级事件

### 14.5 运行时对象与纯数据对象分层

这里正式区分两层对象：

- 运行时对象:
  `Task`、`TaskStage` 可以作为 `QObject`-based active object 存在
- 纯数据对象:
  `TaskInput`、`TaskConfig`、`TaskSnapshot`、`StageSnapshot` 必须保持 Qt-free

## 15. Ghost Downloader 应提供的内部 API

Ghost Downloader 若要支持社区作者，必须主动提供一层稳定作者接口。

### 15.1 V1 最值得提供的内部 API

V1 应优先提供这些，而不是 matcher DSL：

- `FeaturePack`
- `Task`
- `TaskStage`
- `SingleFileTask`
- `MultiFileTask`
- `TaskFile`
- `TaskConfig`
- `TaskForm`
- `TaskSnapshot`
- `StageSnapshot`
- 默认 `TaskConfigDialog`
- 默认 `MultiFileSelectDialog`
- 默认 SettingPage 注入支持
- 默认 TaskCard / ResultCard 支持
- 默认测试夹具

### 15.2 推荐目录

推荐方向：

```text
app/
  feature_pack/
    api/
      __init__.py
      requests.py
      settings.py
      task.py
      stage.py
      task_config.py
      snapshots.py
      cards.py
      testing.py
    internal/
      ...
```

### 15.3 社区作者默认应只依赖什么

社区 Pack 应默认只依赖：

- `app.feature_pack.api`
- 自己 Pack 内部模块

默认不应依赖：

- 其他 Pack 的模块路径
- 宿主私有实现目录

### 15.4 SettingPage 扩展也应走宿主接口

现有代码已经说明，Feature Pack 确实需要在 `SettingPage` 中挂自己的设置卡片。

V1 应把这项能力正式收进宿主 API，而不是继续把它留在“Pack 直接操作页面布局”的状态。

推荐方向：

- Pack 返回 `SettingSection`
- 宿主统一把它映射到 `SettingCardGroup`
- 简单设置默认渲染
- 复杂设置允许自定义卡片

这样做的价值是：

- 社区作者不用研究 `SettingPage` 内部布局
- 宿主可以统一设置分组顺序和注入时机
- SettingPage 结构以后重构时，不会波及每个 Pack

## 16. 面向社区作者的目标体验

### 16.1 一个简单 Pack 默认只需要写什么

理想情况下，一个普通社区 Pack 默认只需要写：

- `manifest.toml`
- `pack.py`
- `task_data.py`
- 少量自定义 Stage

只有在需要 UI 扩展时，才再写：

- `ui/task_card.py`
- `ui/settings_ui.py`

### 16.2 社区作者默认不应该再写什么

默认不应该自己写：

- Pack 元数据解析
- Task / Stage 骨架
- 普通配置对话框骨架
- 多文件选择树对话框骨架
- 标题 / 路径同步骨架
- 默认卡片外壳
- 契约测试样板

### 16.3 仓库内可运行样板

当前仓库提供一个最小社区样板 Pack，路径为：

- `examples/community_sample_pack/manifest.toml`
- `examples/community_sample_pack/pack.py`

这个样板只依赖 `app.feature_pack.api` 和标准库，覆盖 `FeaturePack`、`SingleFileTask`、`TaskStage`、`TaskForm`、`SettingSection` 的最小组合，并由 `tests/feature_pack/test_community_sample_pack.py` 验证加载、创建任务和运行输出。

## 17. V1 落地状态

本仓库已经完成以下 V1 收口项：

- Pack 元数据统一为 `manifest.toml`，Python 侧模型为 `Manifest`。
- Pack 主路径统一为 `accepts(source)`、`createTask(data)`、`owns(task)`。
- 宿主作者接口集中在 `app.feature_pack.api`，社区 Pack 默认只依赖该 API 和自身模块。
- 任务模型统一为 `Task`、`SingleFileTask`、`MultiFileTask`、`TaskStage`、`TaskFile`。
- 配置修改统一为提交完整 `TaskConfig`，并通过 `Task.configure()` 下发到 Stage。
- 默认 UI 已提供 `TaskConfigDialog`、`MultiFileSelectDialog`、`DefaultTaskCard`、`DefaultResultCard` 和 `SettingSection` 注入。
- `CoreService`、`BrowserService`、添加任务流程、主窗口 Pack 加载和设置页注入已经切换到 V1 入口。
- `http_pack`、`github_pack`、`ftp_pack`、`bittorrent_pack`、`bili_pack`、`m3u8_pack`、`ffmpeg_pack`、`extract_pack`、`jack_yao` 已改写到 V1。
- 旧 `app.bases` V0 接口、旧 payload 修改链路、旧 `ParseSettingCard` 流程和遗留命名已经删除。
- 最小社区样板 Pack 位于 `examples/community_sample_pack/`，authoring 测试位于 `tests/feature_pack/test_community_sample_pack.py`。

## 18. LLM Agent 工作规则

任何 Agent 在改动 Feature Pack 相关代码时，必须先问自己六个问题：

1. 这次改动是在优化名字，还是在发明新概念？
2. 这次改动是否让 `Task` 更通用，还是更私有化？
3. 这次改动是否把差异沉到 `TaskStage`，还是又堆回 Pack / Task？
4. 这次改动是否继续扩大了隐式 `dict` 契约？
5. 这次改动是否破坏了单一写者 + 消息驱动的 Actor 风格边界？
6. 这次改动是否本该提升成 Ghost Downloader 内部 API？

### 18.1 明确禁止

- 禁止继续新增 `_featurePackName`
- 禁止把类名当作持久化 type id
- 禁止在多个 Pack 中复制输入兼容逻辑
- 禁止默认新建新的 Pack-specific Task 骨架
- 禁止 `TaskCard` 直接改 `TaskStage` 内部状态
- 禁止跨线程 direct call 修改其他对象状态
- 禁止再引入任何额外的 Python 元数据文件概念
- 禁止 Pack 之间通过模块路径直接复用实现代码

### 18.2 默认应该做

- 优先把名字起对
- 优先让接口更自然
- 优先把复杂度推迟到真正需要时
- 优先把 Pack 差异收敛到 Stage
- 优先把重复结构提升成 Ghost Downloader 内部 API
- 优先用 `configure()` 而不是继续扩大 `applyPayloadToTask()`

## 19. 契约测试要求

接口标准必须由契约测试守住。

最低测试面：

- Manifest 解析测试
- Task 身份与序列化测试
- Stage 身份与序列化测试
- `SingleFileTask` 路径同步测试
- `MultiFileTask` 文件选择与根路径同步测试
- `TaskConfig` 替换测试
- 运行前配置变更测试
- 运行中配置变更测试
- queued connection 跨线程传递测试
- `TaskCard -> Task -> TaskStage` 命令链测试
- `TaskStage -> Task -> TaskCard` 事件投影测试

建议目录：

- `tests/feature_pack/`
- `tests/features/<pack_id>/`

## 20. 外部依据

本文档主要基于以下一手资料与工程推断：

- Python PEP 20: 强调简单、显式、可读、拒绝猜测
- Python PEP 8: 强调公开名字应反映用途，且项目内部一致性高于教条一致性
- Qt `Signals & Slots`: 给出信号槽的通信语义
- Qt `Threads and QObjects`: 给出 `QObject` 线程归属、queued connection 与跨线程调用边界
- Microsoft Orleans 官方文档: 强调 actor 风格下状态封装、异步消息和单线程执行带来的简化收益
- `pluggy` 文档: 强调宿主与插件之间需要小而清晰、可验证的契约
- TOML 规范与 Python `tomllib`: 支持把 Pack 元数据固定为 `manifest.toml`
- `warehouse-style-guide.md`: 提供本仓库倾向的命名、分层、类型与 UI 架构约束

需要明确说明的推断：

- “`Task` 是 workflow supervisor、`TaskStage` 是 actor-like worker” 是本文档基于 Actor Model 和当前项目结构做出的工程推断
- “V1 不优先提供 matcher DSL” 是本文档基于现有 `features/` 的重复度与收益分析做出的工程结论
- “统一用 `configure(TaskConfig)` 处理运行前 / 运行中改配置” 是本文档基于当前项目真实需求和工作流系统常见实践做出的工程判断

## 21. 收口判断

Ghost Downloader Feature Pack V1 的关键，不是引入多少新抽象，而是持续守住五件事：

1. 把名字起得自然
2. 把 `manifest.toml` 的边界固定
3. 把 `Task` / `SingleFileTask` / `MultiFileTask` 的基类体系抽清楚
4. 把 `configure(TaskConfig)` 变成运行前 / 运行中统一配置接口
5. 把 `TaskStage` 做成 Pack 的主要能力承载点

这五件事已经作为当前 V1 标准落地。后续新增 Pack 或宿主能力时，应优先沿用这些边界；只有在现有契约无法表达真实需求时，才进入新的版本化设计。
