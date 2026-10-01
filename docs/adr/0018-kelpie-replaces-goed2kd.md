# Kelpie 取代 goed2kd，放在新仓库

eD2k 引擎、引擎进程和 Python 包统一改名为 Kelpie，放在新仓库 `XiaoYouChR/Kelpie`。
`Python-eD2k` 停在 v0.2.4 并归档；新版 GD 只安装 Kelpie。

## Considered Options

- **原地改名 `Python-eD2k`**：旧版 GD 会顺着重定向拿到 Kelpie 的 latest release，找不到 `goed2kd-*` 资产，安装失败；
  除非每次发版都永久附带别名资产。
- **只给新引擎起名，其余保持原名**：用户在设置页、代码 import、发版资产里看到两套名字。

## Consequences

- 旧版 GD 继续安装 Python-eD2k v0.2.4（含写盘修复），永远不会遇到 Kelpie，所以 Kelpie 的协议从干净的 v1 开始。
- Kelpie 第一版直接带自研引擎发布；GD 只迁移一次接口。
- Kelpie 读取 goed2kd 写下的 `state.json`，数据目录 `ed2k_data` 不变；旧的 goed2kd 二进制不自动清理。
- 版本检查由 Kelpie 的 Python 包在握手时完成，GD 不再自己比较版本。
