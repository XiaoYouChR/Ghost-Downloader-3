# 提示音不用 QtMultimedia

Popup 的提示音在 Windows 上用标准库的 `winsound.PlaySound`，在 Linux 上依次尝试 `pw-play`、`paplay`、`canberra-gtk-play`，并给音频流打上事件 role，不用 `QSoundEffect`。这样打包体积不增加，提示音也跟随系统"系统声音"那一路的音量和静音。

## Considered Options

- **`QSoundEffect`**：跨平台，只有一条代码路径。在 PySide6 6.10 上实测，只播放 WAV 不需要 FFmpeg 后端，但仍要多打包 `libQt6Multimedia` 和绑定，约 2.5 MB；而且 Nuitka 默认插件列表一旦把 `multimedia` 族加进去，FFmpeg（约 19 MB）就会被带进来。
- **libcanberra / GSound**：Linux 上的正统做法，但 PySide 没有绑定，上游也已停止维护。
- **`aplay`**：直通 ALSA，绕过声音服务器，用户的系统声音设置对它无效。

## Consequences

- Linux 上能否出声取决于用户 PATH 里有没有这几个播放器；都没有时只记 debug 日志，不报错。
- `winsound` 不支持从内存异步播放，wav 要先从 qrc 释放到临时目录。
