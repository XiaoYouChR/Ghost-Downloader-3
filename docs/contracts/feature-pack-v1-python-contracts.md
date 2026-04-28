# Feature Pack V1 Python 契约

状态: Accepted / V1 收口
日期: 2026-04-28
来源: 基于 [feature-pack-interface-standard.md](../standards/feature-pack-interface-standard.md) 的代码契约化整理

## 1. 文档目标

这份文档直接用 Python 契约表达 Ghost Downloader 当前 Feature Pack V1 的核心类型和接口。

截至 2026-04-28，本文档描述的是已落地的 V1 契约。旧 `app.bases` V0 接口、旧 payload 修改链路和迁移期的 Pack 加载流程已经从仓库移除。

目标只有四个：

- 把公开名字收紧到足够少
- 把职责边界写清楚
- 让默认 UI 可复用，而不是每个 Pack 重写对话框
- 让社区作者能在少量样板代码下完成 Pack 开发

本文档是“契约文档”，不是可直接运行的实现代码。

## 2. 命名原则

本文档的命名遵守两条来自 Python 官方文档的长期原则：

- PEP 20: `Simple is better than complex.`、`Explicit is better than implicit.`、`Readability counts.`
- PEP 8: 公开 API 名字应服务于“怎么用”，而不是“怎么实现”

因此 V1 统一采用：

- 类名用 `CapWords`
- 方法名、函数名、变量名、字段名用 `camelCase`
- 优先使用短而完整的英文单词
- 避免 `handle`、`process`、`do`、`applyPayload` 这类含糊或带历史包袱的名字
- 同一件事只保留一个名字

本文档采用的关键名字如下：

- `FeaturePack`
- `FeatureService`
- `Manifest`
- `TaskConfig`
- `TaskInput`
- `Task`
- `SingleFileTask`
- `MultiFileTask`
- `TaskStage`
- `TaskFile`
- `TaskForm`
- `FormField`
- `TaskConfigDialog`
- `MultiFileSelectDialog`
- `SettingSection`
- `TaskSnapshot`
- `StageSnapshot`
- `accepts`
- `createTask`
- `owns`
- `configure`
- `syncOutput`
- `snapshot`
- `editForm`
- `editTask`
- `settingSection`

## 3. 元数据契约

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Manifest:
    id: str
    name: str
    version: str
    api: int
    entry: str = "pack.py"
    dependencies: tuple[str, ...] = ()
    schemes: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()
```

说明：

- Pack 元数据文件统一使用 `manifest.toml`
- `Manifest` 只是 `manifest.toml` 在 Python 中的只读数据模型
- 不再引入任何平行的元数据文件概念

## 4. 配置契约

V1 只保留一个配置类型：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskConfig:
    source: str
    folder: Path
    name: str
    headers: dict[str, str] = field(default_factory=dict)
    proxies: dict[str, str] | None = None
    chunks: int = 1
```

说明：

- `TaskConfig` 是任务的正式配置模型
- 下载前和下载中的配置修改，都重新提交一份完整的 `TaskConfig`
- 不再保留额外的 patch 配置类型

推荐改法：

```python
from dataclasses import replace


newConfig = replace(
    task.config,
    source=newSource,
    proxies=newProxies,
    folder=newFolder,
)

task.configure(newConfig)
```

这样做的原因很简单：

- 类型更少
- 入口只有一个
- `replace()` 是 Python 标准库已经提供的明确机制
- 对 LLM Agent 和社区作者都更容易理解

## 5. 输入契约

宿主进入 Pack 前，统一整理成一个输入对象：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskInput:
    config: TaskConfig
    size: int = 0
    hints: tuple[dict[str, Any], ...] = ()
```

说明：

- 这里不再长期使用 `payload: dict`
- 浏览器、粘贴链接、历史恢复、核心服务，都应先整理成 `TaskInput`
- Pack 只面对稳定输入，不面对宿主内部零散字段

## 6. Snapshot 契约

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class StageSnapshot:
    id: str
    kind: str
    name: str
    state: str
    progress: float
    doneBytes: int
    speed: int
    error: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskSnapshot:
    id: str
    packId: str
    kind: str
    name: str
    state: str
    progress: float
    doneBytes: int
    totalBytes: int
    canPause: bool
    target: str
    stages: tuple[StageSnapshot, ...] = ()
```

说明：

- Snapshot 是 UI 和测试看到的稳定投影
- Snapshot 必须保持 Qt-free

## 7. `TaskFile` 契约

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, kw_only=True)
class TaskFile:
    id: str
    path: str
    size: int
    selected: bool = True
    note: str = ""
    doneBytes: int = 0
    finished: bool = False
```

说明：

- `TaskFile` 是多文件任务的统一文件条目
- `path` 是给选择对话框和树视图使用的逻辑路径
- `note` 用于补充显示分集信息、清晰度或其他摘要信息
- `ftp_pack`、`bittorrent_pack`、`bili_pack` 的多项选择能力都应向这个模型收敛

## 8. 编辑表单契约

普通配置项不应要求 Pack 作者手写一整个 `QDialog`。

V1 的默认做法是：

- Pack 或 Task 声明一个小而稳定的表单
- 宿主用默认 `TaskConfigDialog` 渲染它
- 只有在标准控件不够时，Pack 才写自定义 UI

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


EditMode = Literal["before", "running"]
FieldKind = Literal["text", "folder", "headers", "proxy", "int", "choice", "files"]


@dataclass(frozen=True, slots=True, kw_only=True)
class FormChoice:
    value: str
    label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FormField:
    key: str
    label: str
    kind: FieldKind
    choices: tuple[FormChoice, ...] = ()
    placeholder: str = ""
    note: str = ""
    min: int | None = None
    max: int | None = None
    step: int = 1
    modes: frozenset[EditMode] = field(
        default_factory=lambda: frozenset({"before", "running"})
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskForm:
    title: str = "编辑任务"
    fields: tuple[FormField, ...] = ()
```

说明：

- `TaskForm` 只描述“有哪些可编辑项”
- `FormField` 只描述字段语义，不直接持有 widget
- `files` 是一个特殊字段，它不直接在表单里展开，而是打开 `MultiFileSelectDialog`

## 9. 默认对话框契约

### 9.1 `TaskConfigDialog`

默认编辑对话框负责两件事：

- 用标准字段编辑 `TaskConfig`
- 在 `MultiFileTask` 场景下，代管多项选择入口

```python
from __future__ import annotations

from qfluentwidgets import MessageBoxBase


class TaskConfigDialog(MessageBoxBase):
    def __init__(
        self,
        *,
        task: Task,
        form: TaskForm,
        mode: EditMode,
        parent=None,
    ) -> None:
        super().__init__(parent)

    def config(self) -> TaskConfig:
        raise NotImplementedError

    def selectedIds(self) -> set[str]:
        raise NotImplementedError
```

说明：

- 宿主默认使用 `QFormLayout` 组装普通字段
- `ResultCard` 和 `TaskCard` 不应各自重写编辑对话框
- 默认卡片只需要调用宿主的 `editTask()`

### 9.2 `MultiFileSelectDialog`

现有 `FileSelectDialog` 已经证明这类树选择器有价值。  
V1 不应再保留 Pack-specific 版本，而应把它提升成正式内部 API。

```python
from __future__ import annotations

from qfluentwidgets import MessageBoxBase


class MultiFileSelectDialog(MessageBoxBase):
    def __init__(
        self,
        *,
        task: MultiFileTask,
        title: str = "选择内容",
        parent=None,
    ) -> None:
        super().__init__(parent)

    def selectedIds(self) -> set[str]:
        raise NotImplementedError
```

说明：

- 对 `ftp_pack` / `bittorrent_pack`，它显示的是待下载文件
- 对 `bili_pack`，它显示的是可下载分集
- 它应该沿用 Qt model/view 的思路，而不是手工堆很多 checkbox widget

## 10. SettingPage 契约

Feature Pack 需要能在 `SettingPage` 中提供自己的设置卡片。  
这也是现有项目已经具备的真实能力，V1 必须正式收进契约。

推荐做法不是让 Pack 直接操作 `SettingPage` 内部结构，而是：

- Pack 返回一个声明式的 `SettingSection`
- 宿主统一把它挂到 `SettingPage`
- 只有在标准设置卡片不够时，Pack 才写自定义 `SettingCard`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True, kw_only=True)
class SettingItem:
    key: str
    label: str
    kind: str
    note: str = ""
    options: tuple[FormChoice, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class SettingSection:
    id: str
    title: str
    items: tuple[SettingItem, ...] = ()
```

说明：

- `SettingSection` 表达“这一组设置卡片属于哪个 Pack”
- `SettingItem` 表达“这里要渲染哪种设置卡片”
- 宿主默认把它映射到 `SettingCardGroup`
- 复杂场景仍允许 Pack 返回自定义 `QWidget` 或 `SettingCard`

## 11. `TaskStage` 基类契约

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from .task import Task
    from .config import TaskConfig
    from .snapshot import StageSnapshot


class TaskStage(QObject, ABC):
    stateChanged = Signal(str)
    progressChanged = Signal(float)
    snapshotChanged = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        id: str,
        kind: str,
        version: int,
        name: str,
    ) -> None:
        super().__init__()
        self.id = id
        self.kind = kind
        self.version = version
        self.name = name

    def attach(self, task: "Task") -> None:
        self._task = task

    @abstractmethod
    async def run(self) -> None:
        raise NotImplementedError

    def canPause(self) -> bool:
        return True

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    def configure(self, config: "TaskConfig") -> None:
        """
        Task 下发完整配置。
        Stage 可选择立刻应用、延后应用，或请求受控重启。
        """

    @abstractmethod
    def snapshot(self) -> "StageSnapshot":
        raise NotImplementedError
```

说明：

- `TaskStage` 是主要能力承载点
- `TaskStage` 是运行时对象，允许带 `Signal`
- 配置下发统一走 `configure(config)`
- 不再为单个字段继续扩散 `setProxy()` / `setHeaders()` / `setPath()`

## 12. `Task` 基类契约

`Task` 是通用工作流容器，不是某个下载协议的细节实现。

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from PySide6.QtCore import QObject, Signal


class Task(QObject, ABC):
    stateChanged = Signal(str)
    progressChanged = Signal(float)
    snapshotChanged = Signal(object)

    def __init__(
        self,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
    ) -> None:
        super().__init__()
        self.id = id
        self.packId = packId
        self.kind = kind
        self.version = version
        self.config = config
        self.stages = stages

    def addStage(self, stage: TaskStage) -> None:
        stage.attach(self)
        self.stages.append(stage)

    def configure(self, config: TaskConfig) -> None:
        self.config = config
        self.syncOutput()
        for stage in self.stages:
            stage.configure(config)

    def editForm(self, mode: EditMode) -> TaskForm | None:
        return None

    @abstractmethod
    def syncOutput(self) -> None:
        """
        把当前配置中的输出目标同步到各 Stage。
        """
        raise NotImplementedError

    def iterStages(self) -> Iterable[TaskStage]:
        return self.stages

    def canPause(self) -> bool:
        return all(stage.canPause() for stage in self.stages)

    async def run(self) -> None:
        for stage in self.iterStages():
            await stage.run()

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> TaskSnapshot:
        raise NotImplementedError
```

说明：

- `Task` 负责 workflow 编排
- `TaskStage` 负责具体工作
- `configure()` 是唯一公开配置入口
- `editForm()` 让 Pack 用声明式方式扩展默认编辑对话框

## 13. `SingleFileTask` 契约

```python
from __future__ import annotations

from abc import ABC
from dataclasses import replace
from pathlib import Path


class SingleFileTask(Task, ABC):
    @property
    def folder(self) -> Path:
        return self.config.folder

    @property
    def filename(self) -> str:
        return self.config.name

    @property
    def path(self) -> Path:
        return self.folder / self.filename

    def rename(self, name: str) -> None:
        self.configure(replace(self.config, name=name))

    def move(self, folder: Path) -> None:
        self.configure(replace(self.config, folder=folder))
```

说明：

- `SingleFileTask` 适用于最终只产出一个目标文件的任务
- 它应该吸收现有多个 Pack 中重复的改名、改路径、路径同步逻辑

## 14. `MultiFileTask` 契约

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class MultiFileTask(Task, ABC):
    def __init__(
        self,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
        files: list[TaskFile],
    ) -> None:
        super().__init__(
            id=id,
            packId=packId,
            kind=kind,
            version=version,
            config=config,
            stages=stages,
        )
        self.files = files

    @property
    def root(self) -> Path:
        return self.config.folder / self.config.name

    @property
    def fileCount(self) -> int:
        return len(self.files)

    @property
    def selectedCount(self) -> int:
        return sum(1 for file in self.files if file.selected)

    @property
    def selectedIds(self) -> set[str]:
        return {file.id for file in self.files if file.selected}

    @abstractmethod
    def select(self, ids: set[str]) -> None:
        raise NotImplementedError
```

说明：

- `MultiFileTask` 适用于产出多个结果项的任务
- `bili_pack` 的分集选择和 `ftp_pack` / `bittorrent_pack` 的文件选择都应留在这里
- 默认 `MultiFileSelectDialog` 直接面向这个基类

## 15. `FeaturePack` 契约

```python
from __future__ import annotations

from abc import ABC, abstractmethod


class FeaturePack(ABC):
    manifest: Manifest

    @abstractmethod
    def accepts(self, source: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def createTask(self, data: TaskInput) -> Task | None:
        raise NotImplementedError

    @abstractmethod
    def owns(self, task: Task) -> bool:
        raise NotImplementedError

    def settingSection(self):
        return None

    def createTaskCard(self, task: Task, parent=None):
        return None

    def createResultCard(self, task: Task, parent=None):
        return None

    def install(self, window) -> None:
        return None
```

说明：

- Pack 的公开面要尽量小
- V1 不把重心放在复杂 matcher 上
- Pack 主要负责组装 `Task` 和实现 `TaskStage`
- Pack 也可以声明自己的 `SettingSection`

## 16. `FeatureService` 契约

这部分必须和 Pack 一起重做，因为它是 Pack 的直接调用者。

```python
from __future__ import annotations

from abc import ABC, abstractmethod


class FeatureService(ABC):
    @abstractmethod
    def discoverPacks(self) -> list[Manifest]:
        """
        扫描 `features/` 中的 `manifest.toml`。
        """
        raise NotImplementedError

    @abstractmethod
    def loadPacks(self, window) -> None:
        """
        根据 manifest 加载 Pack，并完成宿主注册。
        """
        raise NotImplementedError

    @abstractmethod
    def pack(self, packId: str) -> FeaturePack | None:
        raise NotImplementedError

    @abstractmethod
    def packForSource(self, source: str) -> FeaturePack | None:
        raise NotImplementedError

    @abstractmethod
    def packForTask(self, task: Task) -> FeaturePack | None:
        raise NotImplementedError

    @abstractmethod
    async def createTask(self, data: TaskInput) -> Task:
        raise NotImplementedError

    @abstractmethod
    def configureTask(self, taskId: str, config: TaskConfig) -> None:
        raise NotImplementedError

    @abstractmethod
    def installSettings(self, page) -> None:
        raise NotImplementedError

    @abstractmethod
    def editTask(self, task: Task, mode: EditMode, parent=None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def createTaskCard(self, task: Task, parent=None):
        raise NotImplementedError

    @abstractmethod
    def createResultCard(self, task: Task, parent=None):
        raise NotImplementedError
```

说明：

- `FeatureService` 应该只暴露宿主真正需要的入口
- 它的工作是发现、加载、路由、创建任务、转发配置修改、安装设置卡片、打开默认编辑对话框
- 它不应该继续暴露历史性的 `payload` 协议

## 17. `FeatureService` 的内部切分

为了避免 `FeatureService` 再次膨胀，推荐内部拆成以下职责：

```python
class PackRegistry(ABC):
    def discover(self) -> list[Manifest]:
        raise NotImplementedError

    def load(self) -> None:
        raise NotImplementedError

    def pack(self, packId: str) -> FeaturePack | None:
        raise NotImplementedError


class TaskRouter(ABC):
    def packForSource(self, source: str) -> FeaturePack | None:
        raise NotImplementedError

    def packForTask(self, task: Task) -> FeaturePack | None:
        raise NotImplementedError


class CardFactory(ABC):
    def createTaskCard(self, task: Task, parent=None):
        raise NotImplementedError

    def createResultCard(self, task: Task, parent=None):
        raise NotImplementedError


class TaskEditor(ABC):
    def configure(self, taskId: str, config: TaskConfig) -> None:
        raise NotImplementedError

    def edit(self, task: Task, mode: EditMode, parent=None) -> bool:
        raise NotImplementedError


class SettingsInstaller(ABC):
    def install(self, page) -> None:
        raise NotImplementedError
```

说明：

- 对外仍然可以保持单一 `FeatureService`
- 但内部必须按职责拆开
- 这会直接降低宿主复杂度，也方便长期维护

## 18. 配置修改与选择修改的统一流转

用户已经明确需要支持：

- 下载中换链
- 下载前 / 中改代理
- 下载前 / 中改文件位置
- 下载前 / 中改请求头
- 下载前选择分集或文件

V1 的统一做法是：

1. `ResultCard` 或 `TaskCard` 调用 `FeatureService.editTask()`
2. 宿主打开默认 `TaskConfigDialog`
3. 对普通字段，生成一份新的 `TaskConfig`
4. 对多项选择字段，读取 `MultiFileSelectDialog.selectedIds()`
5. 宿主先调用 `task.select(ids)`，再调用 `task.configure(config)`

推荐流转：

```text
TaskCard / ResultCard
    -> FeatureService.editTask(task, mode, parent)
    -> TaskConfigDialog
    -> MultiFileSelectDialog (optional)
    -> Task.select(ids)        # only for MultiFileTask
    -> Task.configure(config)
    -> Task.syncOutput()
    -> TaskStage.configure(config)
```

这条链路的价值在于：

- 卡片层没有业务样板代码
- 配置编辑与多项选择有统一入口
- Task 仍然是工作流总控
- Stage 仍然保留是否立刻应用变更的自由

## 19. 当前目录结构

```text
app/
  feature_pack/
    api/
      __init__.py
      cards.py
      pack.py
      config.py
      input.py
      form.py
      manifest.py
      runtime.py
      settings.py
      task.py
      stage.py
      snapshot.py
      service.py
      testing.py
    ui/
      dialogs.py
      cards.py
```

这里故意不再引入任何额外的 Python 元数据文件名。服务发现只读取每个 Pack 目录下的 `manifest.toml`。

## 20. 最小社区开发体验

一个社区 Pack 理想上只需要写：

- `manifest.toml`
- `pack.py`
- 少量自定义 `TaskStage`

只有在基类不够时，才再写：

- 自定义 `task.py`
- 自定义 UI 文件

Ghost Downloader 应该主动提供：

- 可直接继承的 `SingleFileTask`
- 可直接继承的 `MultiFileTask`
- 稳定的 `TaskConfig`
- 稳定的 `TaskInput`
- 稳定的 `TaskForm`
- 稳定的 `SettingSection`
- 默认 `TaskConfigDialog`
- 默认 `MultiFileSelectDialog`
- 默认 SettingPage 注入入口
- 稳定的 `FeatureService` 调用入口

仓库内的最小可运行样板 Pack 位于：

- `examples/community_sample_pack/manifest.toml`
- `examples/community_sample_pack/pack.py`

它用一个 `pack.py` 展示 `FeaturePack`、`TaskStage`、`TaskForm` 和 `SettingSection` 的最小组合；对应 authoring 契约测试位于 `tests/feature_pack/test_community_sample_pack.py`。

## 21. 收口结论

V1 收紧后的核心契约只有这些：

1. `manifest.toml`
2. `Manifest`
3. `TaskConfig`
4. `TaskInput`
5. `TaskForm`
6. `SettingSection`
7. `Task`
8. `SingleFileTask`
9. `MultiFileTask`
10. `TaskStage`
11. `TaskFile`
12. `TaskConfigDialog`
13. `MultiFileSelectDialog`
14. `FeaturePack`
15. `FeatureService`
16. `FeaturePackSettings`
17. `TaskStatus`
18. `SpecialFileSize`

V1 不再保留额外的 patch 配置类型。  
普通配置编辑统一通过“提交一份新的 `TaskConfig`”完成。  
多项选择统一通过 `MultiFileSelectDialog + MultiFileTask.select()` 完成。  
设置页扩展统一通过 `SettingSection` 和宿主注入完成。  
运行时状态枚举与特殊文件大小哨兵位于 `app.feature_pack.api.runtime`，Pack 持久化设置基类位于 `app.feature_pack.api.settings`。这比继续让每个 Pack 直接操作旧基类或 `SettingPage` 内部结构更简单，也更符合 Ghost Downloader 作为 GUI 宿主应提供的默认能力。
