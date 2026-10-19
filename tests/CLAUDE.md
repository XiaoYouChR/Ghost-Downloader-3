# 测试

## 命名

测试文件对应一个概念，文件名取 [CONTEXT.md](../CONTEXT.md) 的术语，如 `test_task.py`；没有对应术语时，取被测模块的文件名，如 `test_sysio.py`。FeaturePack 的测试文件置于 `tests/<pack>/`，其余置于 `tests/`；真实样本置于 `tests/samples/`。

用例名是"动作 + 结果"的 snake_case 短句。主语由文件名给出，用例名从动作写起，如 `test_task.py` 中的 `test_delete_finished_keeps_file`。动作取自[根目录 CLAUDE.md](../CLAUDE.md) 的动词表或被测公开接口的方法（如 `redownload`、`edit`），结果写用户可见的变化，名词取 CONTEXT.md 的术语。用例平铺在测试文件中；一组用例须共享 fixture 或参数时，才放进测试类。

## 第三个平台

测试是继桌面与 Android 之后的第三个平台：桌面在 `app/startup.py`、Android 在 `bridge.py`、测试在 `tests/conftest.py` 中以相同方式组装 Engine。平台向 Engine 提供的只有三项，替身只用于这三处：

- Engine 的构造参数；
- 注册到 Feature Service 的 FeaturePack；
- 由 `cfg.load` 读取的配置文件。

FeaturePack 的测试中，平台提供的是 `PackServices`、Binary Runtime 与 Pack 级的 session，替身只用于这些对象。其余一律使用真实代码，远端服务器由 `startServer` fixture 在本机回环上充当。替身以 `Fake` 为前缀，集中定义于 `tests/conftest.py`。

## 断言

用例只经由公开接口驱动和观察被测概念。若某项行为只能经由私有成员观察，说明接口有误，应修改实现，使其在公开接口上可见。

每个用例对应一项用户行为，断言公开接口向用户作出的承诺：Task 的状态、发出的信号、磁盘上的文件。例如"安装后的程序可以执行"写作 `os.access(path, os.X_OK)`。期望值来自需求或真实样本，而非按实现的算法推算。每个用例都须回答"它变红时用户会遇到什么问题"；答不出来的，或者只有替身才能使其变红的，不写。

## 范围

测试覆盖 Engine 与 FeaturePack 的引擎部分。View 只投影 Engine 的状态，由截图与真机验证，包括桌面的 `app/view/`、Android 的 `bridge.py`、FeaturePack 的 card 与 `android.py`，以及界面文案。若 View 中出现逻辑，应将其移入 Engine，并在 Engine 中测试。

## 操作系统与事件循环

同一组断言须在 Windows、macOS 与 Linux 上同时成立，操作系统差异只出现在 `app/platform` 中。需要真实的系统行为时使用真实对象，例如以 `startProgram` 在指定路径上启动真实进程。仅当运行环境缺少某项能力（如 IPv6）时方可跳过用例，并在 reason 中注明所缺的能力。

涉及连接与传输的用例须同时在桌面与 Android 的事件循环上运行：在测试文件或测试类中以 `@pytest.fixture(params=["desktop", "android"])` 覆盖 `engine`，返回 `startEngine(request.param)`。不经由 Engine 的传输模块（如 `WebSocketStream`）改用 `pytest.mark.asyncio(loop_factories=["asyncio", "uvloop"])`。
