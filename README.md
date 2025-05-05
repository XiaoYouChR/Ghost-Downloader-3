<h4 align="right">
  <a href="README_zh.md">简体中文</a> | English
</h4>
 
> [!NOTE]
> Due to the developer's preparation for the college entrance exam (Gaokao), project updates are temporarily suspended 😭 Join QQ group [`531928387`](https://qm.qq.com/q/PlUBdzqZCm) for latest updates

> [!TIP]
> If you want to use Ghost-Downloader-3 on Windows 7, please download the version `v3.5.8-Portable`.

<!-- PROJECT LOGO -->
<div align="center">

![Banner](resources/banner.webp)

<h3>
    AI-powered next-generation cross-platform multithreaded downloader
</h3>

[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![Release][release-shield]][release-url]
[![Downloads][downloads-shield]][release-url]

<h4>
  <a href="https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/new?template=bug_report.yml">Report Bug</a>
·    
  <a href="https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/new?template=feature_request.yml">Request Feature</a>
</h4>

</div>

<!-- ABOUT THE PROJECT -->
## About The Project

* A downloader developed out of personal interest, and my first Python project 😣
* Originally intended to help a Bilibili Uploader with resource integration 😵‍💫
* Features include IDM-like intelligent chunking without file merging, and AI-powered smart boost 🚀
* Thanks to Python's🐍 accessibility, the project will support plugins🧩 in the future to maximize Python's🐍 advantages

|    Platform    | Required Version |  Architectures   | Compatible |
|:--------------:|:----------------:|:----------------:|:----------:|
|  🐧 **Linux**  |  `glibc 2.35+`   | `x86_64`/`arm64` |     ✅      |
| 🪟 **Windows** |     `7 SP1+`     | `x86_64`/`arm64` |     ✅      |
|  🍎 **macOS**  |     `11.0+`      | `x86_64`/`arm64` |     ✅      |

> [!TIP]
> **Arch Linux AUR support**: Community-maintained packages `ghost-downloader-bin` and `ghost-downloader-git` are now available (Maintainer: [@zxp19821005](https://github.com/zxp19821005))

<!-- ROADMAP -->
## Roadmap

- ✅ Global settings
- ✅ More detailed download information
- ✅ Scheduled tasks
- ✅ Browser extension optimization
- ✅ Global speed limit
- ✅ Memory optimization
  - ✅ Upgrade Qt version
  - ✅ Implement HttpClient reuse
  - ✅ Replace some multithreading with coroutines
- ❌ MVC -> MVVM architecture upgrade and plugin support (In progress...see Folk: feature/Plugins)
- ❌ Enhanced task editing (powerful features like binding multiple Clients to one task)
- ❌ Magnet/BT download (Considering libtorrent implementation)

Visit [Open issues](https://github.com/XiaoYouChR/Ghost-Downloader-3/issues) to see all requested features (and known issues).

<!-- SCREEN SHOTS -->
## Screenshots

[![Demo Screenshot][product-screenshot]](https://space.bilibili.com/437313511)

<!-- CONTRIBUTING -->
## Contributing

Contributions make the open source community an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion, fork the repo and create a pull request. You can also simply open an issue with the "Enhancement" tag. Don't forget to give the project a star⭐! Thanks again!

1. Fork the Project
2. Create your Feature Branch (git checkout -b feature/AmazingFeature)
3. Commit your Changes (git commit -m 'Add some AmazingFeature')
4. Push to the Branch (git push origin feature/AmazingFeature)
5. Open a Pull Request

Thanks to all contributors who have participated in this project!

[![Contributors](http://contrib.nn.ci/api?repo=XiaoYouChR/Ghost-Downloader-3)](https://github.com/XiaoYouChR/Ghost-Downloader-3/graphs/contributors)

<!-- LICENSE -->
## License

Distributed under the GPL v3.0 License. See `LICENSE` for more information.

Copyright © 2025 XiaoYouChR.

<!-- CONTACT -->
## Contact

* [E-mail](mailto:XiaoYouChR@qq.com) - XiaoYouChR@qq.com
* [QQ Group](https://qm.qq.com/q/PlUBdzqZCm) - 531928387

<!-- ACKNOWLEDGMENTS -->
## References

* [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) Powerful, extensible and beautiful Fluent Design widgets
* [Httpx](https://github.com/projectdiscovery/httpx) A fast and multi-purpose HTTP toolkit
* [Aiofiles](https://github.com/Tinche/aiofiles) File support for asyncio
* [Loguru](https://github.com/Delgan/loguru) A library which aims to bring enjoyable logging in Python
* [Nuitka](https://github.com/Nuitka/Nuitka) The Python compiler
* [PySide6](https://github.com/PySide/pyside-setup) The official Python module
* [Darkdetect](https://github.com/albertosottile/darkdetect) Allow to detect if the user is using Dark Mode on
* [pyqt5-concurrent](https://github.com/AresConnor/pyqt5-concurrent) A QThreadPool based task concurrency library

## Acknowledgments

* [@ZhiYiyo](https://github.com/zhiyiYo/) Provided great help for this project!
* [@一只透明人-](https://space.bilibili.com/554365148/) Tested almost every version since Ghost-Downloader-1！
* [@Sky·SuGar](https://github.com/SuGar0218/) Created the project banner！

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
[issues-shield]: https://img.shields.io/github/issues/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[issues-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/issues
[product-screenshot]: resources/screenshot.png
[release-shield]: https://img.shields.io/github/v/release/XiaoYouChR/Ghost-Downloader-3?style=for-the-badge
[release-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest
[downloads-shield]: https://img.shields.io/github/downloads/XiaoYouChR/Ghost-Downloader-3/total?style=for-the-badge
