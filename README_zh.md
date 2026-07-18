<h4 align="right">
  简体中文 | <a href="README.md">English</a>
</h4>

<!-- PROJECT LOGO -->
<div align="center">

![Banner](.github/assets/banner.webp)

<a href="https://trendshift.io/repositories/13847" target="_blank"><img src="https://trendshift.io/api/badge/repositories/13847" alt="XiaoYouChR%2FGhost-Downloader-3 | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

### AI 赋能的新一代跨平台多线程下载器

[![AtomGit Stars][atomgit-stars-shield]][atomgit-stars-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![Release][release-shield]][release-url]
[![Downloads][downloads-shield]][release-url]
[![QQGroup](https://img.shields.io/badge/QQ_Group-756042420-blue.svg?color=blue&style=for-the-badge)](https://qm.qq.com/q/gPk6FR1Hby)

##### [使用文档](https://gd.xychr.com/zh/docs/) · [Bug 报告](https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/new?template=bug_report.yml) · [功能需求](https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/new?template=feature_request.yml)

</div>

<!-- FEATURES -->
## 功能特性

* 像 IDM 一样智能分块⚡但又不需要合并文件，以及 AI 智能加速🚀
* 最小化到托盘后自动释放界面资源🍃，后台内存占用极低
* 支持 HTTP、磁力 / BT、FTP、M3U8、MPEG-DASH、eD2k 等几乎所有常用协议🌐
* 下载时模拟真实浏览器 TLS 指纹🥷，更不容易被网站风控拦截
* 支持解析 YouTube▶️ 与 Bilibili 视频——播放列表 / 多 P、最高 4K/HDR、字幕与账号登录
* 为 GitHub🐙 Release 与 HuggingFace🤗 模型提供专用解析和镜像加速
* 支持 M3U8 直播录制📺，边下边实时解密🔓，Android 端也是全链路支持
* 配套的浏览器扩展🦊可以嗅探网页媒体、接管浏览器下载，不用离开浏览器就能查看和控制任务
* 提供 aria2 兼容的 RPC 接口🔌，第三方工具可以直接推送下载任务
* 任务可以暂停后修改✏️链接、请求头、代理再继续，已下载的进度不会丢
* 完整的 Android 移动端界面📱，支持后台下载与完成通知🔔
* YouTube 音频下载完成后自动转码（MP3、WAV、FLAC、Opus）🎵
* YouTube 任务默认选择选项（例如新建任务时默认预选"仅音频"质量）🎧
* 右键完成的任务即可在本地 VLC 播放器中播放 📺
* 下载完成的压缩包（.zip, .tar, .7z, .rar）支持自动解压到同名文件夹 📦
* 任务下载时防止系统进入睡眠模式（跨平台 Wake Lock）🔒


<!-- ABOUT THE PROJECT -->
## 关于本项目

* 在兴趣驱动下完成的一个下载器，是本人的第一个 Python 项目😣
* 本来的目的是帮 Bilibili 上一位 UP 主做资源整合的😵‍💫
* 得益于 Python🐍 人人都可以开发的特性，本项目未来将会开放插件🧩功能 (等待插件 API 固定中...)，发挥 Python🐍 最大的优势

|       平台       |     版本要求      |       架构支持       | 兼容 |
|:--------------:|:-------------:|:----------------:|:--:|
|  🐧 **Linux**  | `glibc 2.35+` | `x86_64`/`arm64` | ✅  |
| 🪟 **Windows** |    `10+`      | `x86_64`/`arm64` | ✅  |
|  🍎 **macOS**  |    `13.0+`    | `x86_64`/`arm64` | ✅  |
| 🤖 **Android** |   `10.0+`     |   `arm64-v8a`    | ✅  |

> [!WARNING]
> 由于 Qt `6.6+` 已经不再支持 `不支持 AVX 指令集的 CPU`

> [!TIP]  
> **Arch Linux AUR 支持**：现已可通过社区维护的软件包 `ghost-downloader-bin` 和 `ghost-downloader-git` 进行安装（维护者：[@zxp19821005](https://github.com/zxp19821005)）

<!-- SCREEN SHOTS -->
## 截图

![QQ20260326-204347](https://github.com/user-attachments/assets/3e57b113-200c-4286-91cb-b52fe7d1711c)

<!-- ROADMAP -->
## 计划

- ❌ 公开插件 API
- ❌ 更强大的任务编辑功能 (一个任务绑定多个 Sessions 等强大功能)

到 [Open issues](https://github.com/XiaoYouChR/Ghost-Downloader-3/issues) 页面查看所有被请求的功能 (以及已知的问题) 。

<!-- SPONSOR -->
## 赞助商

| [![SignPath](https://signpath.org/assets/favicon-50x50.png)](https://signpath.org/) | 由 [SignPath.io](https://about.signpath.io/) 提供免费代码签名，由 [SignPath Foundation](https://signpath.org/) 提供证书 |
|-------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------|

<!-- CONTRIBUTING -->
## 贡献

贡献让开源社区成为了一个非常适合学习、启发和创新的地方。你所做出的任何贡献都是**受人尊敬**的。

如果你有好的建议，请分支（Fork）本仓库并且创建一个拉取请求（Pull Request）。你也可以简单地创建一个议题（Issue），并且添加标签「Enhancement」。不要忘记给项目点一个 Star⭐！再次感谢！

1. 复刻（Fork）本项目
2. 创建你的 Feature 分支 (git checkout -b feature/AmazingFeature)
3. 提交你的变更 (git commit -m 'Add some AmazingFeature')
4. 推送到该分支 (git push origin feature/AmazingFeature)
5. 创建一个拉取请求（Pull Request）

感谢所有为该项目做出贡献的人！

[![Contributors](http://contrib.nn.ci/api?repo=XiaoYouChR/Ghost-Downloader-3)](https://github.com/XiaoYouChR/Ghost-Downloader-3/graphs/contributors)

## 翻译贡献者

> [!TIP]
> 如果你想为 Ghost Downloader 贡献翻译，欢迎前往 Crowdin 项目页: [ghost-downloader](https://crowdin.com/project/ghost-downloader)

<!-- CROWDIN-CONTRIBUTORS-START -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/XiaoYouChR"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/17224586/medium/60e068e9c11d951cadf3eccec0afbeab.jpeg" />
          <br />
          <sub><b>XiaoYouChR</b></sub></a>
        <br />
        <sub><b>14249 words</b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/i0ntempest"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/17636930/medium/f6bf4e67c7b87221f2e7e04345f8c6b2.jpeg" />
          <br />
          <sub><b>i0ntempest</b></sub></a>
        <br />
        <sub><b>1988 words</b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/ReM2812"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/17626502/medium/8d12a395a224c0f9d5546a8e5621186c.jpg" />
          <br />
          <sub><b>ReM2812</b></sub></a>
        <br />
        <sub><b>1010 words</b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/Dima88888"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/16304162/medium/706302f8224fffaf9d81f8cc4168ed24_default.png" />
          <br />
          <sub><b>Dima88888</b></sub></a>
        <br />
        <sub><b>115 words</b></sub>
      </td>
    </tr>
  </tbody>
</table>
<!-- CROWDIN-CONTRIBUTORS-END -->

<!-- LICENSE -->
## 许可证

根据 GPL v3.0 许可证分发。打开 `LICENSE` 查看更多内容。

Copyright © 2024-2026 XiaoYouChR.

<!-- CONTACT -->
## 联系

> [!IMPORTANT]
> 欢迎加入 Ghost Downloader 用户交流群 [756042420](https://qm.qq.com/q/gPk6FR1Hby)

* [E-mail](mailto:XiaoYouChR@qq.com) - XiaoYouChR@qq.com

<!-- ACKNOWLEDGMENTS -->
## 引用

* [aioftp](https://github.com/aio-libs/aioftp) Ftp client/server for asyncio
* [cat-catch](https://github.com/xifangczy/cat-catch) 猫抓 浏览器资源嗅探扩展
* [desktop-notifier](https://github.com/samschott/desktop-notifier) Python library for cross-platform desktop notifications
* [FFmpeg](https://ffmpeg.org/) A complete, cross-platform solution to record, convert and stream audio and video
* [goed2k](https://github.com/monkeyWie/goed2k) The eD2k download daemon behind Ghost Downloader's eD2k support
* [libtorrent](https://github.com/arvidn/libtorrent) An efficient feature complete C++ bittorrent implementation
* [loguru](https://github.com/Delgan/loguru) A library which aims to bring enjoyable logging in Python
* [m3u8](https://github.com/globocom/m3u8) Python m3u8 parser
* [mpegdash](https://github.com/sangoma/mpegdash) MPEG-DASH MPD parser
* [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) Cross-platform DASH/HLS/MSS download tool powering Ghost Downloader's M3U8 support
* [Nuitka](https://github.com/Nuitka/Nuitka) The Python compiler
* [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) 强大、可扩展、美观优雅的 Fluent Design 风格组件库
* [PySide6](https://github.com/PySide/pyside-setup) The official Python module
* [QuickJS-NG](https://github.com/quickjs-ng/quickjs) A small and embeddable JavaScript engine
* [uvloop](https://github.com/MagicStack/uvloop) Ultra fast asyncio event loop
* [winloop](https://github.com/Vizonex/Winloop) An alternative to uvloop for Windows
* [wreq](https://github.com/0x676e67/wreq-python) An ergonomic Python HTTP client with TLS fingerprint emulation
* [yt-dlp](https://github.com/yt-dlp/yt-dlp) A feature-rich command-line audio/video downloader

## 致谢

* [@zhiyiYo](https://github.com/zhiyiYo/) 是大佬！为该项目的开发提供了很多帮助！
* [@空糖_SuGar](https://github.com/SuGar0218/) 制作了项目的 Banner！

<picture>
  <source
    media="(prefers-color-scheme: dark)"
    srcset="
      https://api.star-history.com/svg?repos=XiaoYouChR/Ghost-Downloader-3&type=Date&theme=dark
    "
  />
  <source
    media="(prefers-color-scheme: light)"
    srcset="
      https://api.star-history.com/svg?repos=XiaoYouChR/Ghost-Downloader-3&type=Date&theme=dark
    "
  />
  <img
    alt="Star History Chart"
    src="https://api.star-history.com/svg?repos=XiaoYouChR/Ghost-Downloader-3&type=Date&theme=dark"
  />
</picture>

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[forks-shield]: https://img.shields.io/github/forks/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[forks-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/network/members
[stars-shield]: https://img.shields.io/github/stars/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[stars-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/stargazers
[atomgit-stars-shield]: https://img.shields.io/badge/dynamic/xml?style=for-the-badge&label=AtomGit%20Stars&color=red&url=https%3A%2F%2Fgitcode.com%2FXiaoYouChR%2FGhost-Downloader-3%2Fstar%2Fbadge.svg&query=string%28%2F%2F*%5Blocal-name%28%29%3D%22span%22%20and%20contains%28%40class%2C%22star-num%22%29%5D%29
[atomgit-stars-url]: https://gitcode.com/XiaoYouChR/Ghost-Downloader-3
[issues-shield]: https://img.shields.io/github/issues/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[issues-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/issues
[release-shield]: https://img.shields.io/github/v/release/XiaoYouChR/Ghost-Downloader-3?style=for-the-badge
[release-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest
[downloads-shield]: https://img.shields.io/github/downloads/XiaoYouChR/Ghost-Downloader-3/total?style=for-the-badge
