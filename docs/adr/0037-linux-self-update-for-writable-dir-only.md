# Linux 应用内自更新仅覆盖可写目录安装

Linux 官方发布仅保留 `.tar.xz`（配合 `scripts/install.sh` 或手动解压到用户目录）与 `.AppImage`，另有社区维护的 AUR 等系统包。我们在 `UpdateService.canSelfUpdate()` 中收口自更新能力判断：Linux 上仅当 `updater` 二进制存在、未处于 `APPIMAGE` 环境、且 `App Dir` 与其父目录均对当前用户可写时，才启用与 Windows / macOS 一致的应用内自更新（优先 HDiffPatch 目录增量 `Patch`，跨版本自动回退全量 `.tar.xz`）；其余形态（`.AppImage`、只读系统目录、源码运行）统一回退到下载发布包。

## Considered Options

- **为 `.AppImage` 增加单文件原地替换**：需要在 `versions.json`、`UpdateService` 与 `updater.c` 各增加一条单文件分支，无法复用目录级 HDiffPatch 补丁，且用户选择 `.AppImage` 本身即偏好免安装单文件管理。
- **通过 `pkexec` 提权更新只读系统目录**：官方已停止发布 `.deb`，只读系统目录基本来自发行版包管理器（如 AUR），应用绕过包管理器强行覆写 `/usr` 会破坏包数据库；同时提权后在 Wayland/D-Bus 会话下重新拉起 GUI 进程极易丢失会话环境变量。
- **Linux 仅做全量 `.tar.xz` 自更新、不生成增量 `Patch`**：全量包约 70 MB，而目录增量 `Patch` 通常不足 10 MB；`UpdateService`、`updater.c` 与 `finalize` 已有完整的增量链路，接入 `hdiffz` / `hpatchz` 的额外维护成本极低。

## Consequences

- `build-ubuntu` 在 `Build .AppImage` 之后再编译并装入 `updater`、`hpatchz` 与 `logo.png`，保证 `.AppImage` 不夹带无效的更新器二进制，同时让 `hdiffz` 直接对齐 `.tar.xz` 内容。
- `Updater` 在 Linux 上保持单一职责，仅负责 `App Dir` 的 `Patch`、`Install`（优先 `renameat2(RENAME_EXCHANGE)` 原子交换，不支持时回退两步 `moveDir`）与重启，不触碰 XDG `.desktop` 与图标文件。
- 首次携带 `updater` 的版本发布前，旧版（如 `v4.5.11`）用户仍通过 `install.sh` 或手动覆盖升级；升入该版本后，后续版本即可直接在应用内完成自更新。
