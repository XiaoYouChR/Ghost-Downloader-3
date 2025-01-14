<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/XiaoYouChR/Ghost-Downloader-3">
    <img src="images/logo.png" alt="Logo" width="100" height="100">
  </a>

<h3 align="center">Ghost-Downloader 3</h3>

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![License][license-shield]][license-url]

  <p align="center">
    AI 赋能的基于 PySide6 的新一代多线程下载器, 使用 QThread 实现多线程功能
    <br />
    由于项目开发者高三开学，项目更新十分缓慢😭 可加QQ群获取项目作者最新消息: 531928387
    <br />
    <a href="https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/new?labels=bug&template=bug-report---.md">Report Bug</a>
    ·
    <a href="https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>目录</summary>
  <ol>
    <li><a href="#关于本项目">关于本项目</a></li>
    <li><a href="#须知">须知</a></li>
    <li><a href="#计划">计划</a></li>
    <li><a href="#贡献">贡献</a></li>
    <li><a href="#许可证">许可证</a></li>
    <li><a href="#联系">联系</a></li>
    <li><a href="#致谢">致谢</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## 关于本项目

[![Demo Screenshot][product-screenshot]](https://space.bilibili.com/437313511)

在兴趣驱动下完成的一个下载器，是本人的第一个Python项目😫，本来的目的是帮B站上一位UP主做资源整合的😵。支持多线程下载、AI加速、断点续传、下载记录、校验文件等功能。特点是能像IDM一样智能分块但又不需要合并文件，还有 AI 自动调整线程数的功能。但是Python和Qt💩一样的内存占用成为项目很大的槽点😭不过得益于Python人人都可以开发的特性。本项目未来将会开放插件功能，发挥Python最大的优势。

## 须知
* 在开发环境中运行 `main.py` 时请加上 `--debug` 实参。


<!-- ROADMAP -->
## 计划

- [x] 全局设置
- [x] 更详细的下载信息
- [x] 计划任务功能
- [ ] 全局限速（还没找到一个合适的实现方法）
- [x] 浏览器插件优化
- [ ] 开放捐赠入口
- [ ] 磁力 / BT 下载
- [ ] 插件市场
- [x] 内存占用优化
    - [x] 升级 Qt 版本
    - [x] 实现 HttpClient 复用
    - [x] 用协程来代替部分多线程功能

到 [Open issues](https://github.com/XiaoYouChR/Ghost-Downloader-3/issues) 页面查看所有被请求的功能 (以及已知的问题) 。


<!-- CONTRIBUTING -->
## 贡献

贡献让开源社区成为了一个非常适合学习、启发和创新的地方。你所做出的任何贡献都是**受人尊敬**的。

如果你有好的建议，请分支（Fork）本仓库并且创建一个拉取请求（Pull Request）。你也可以简单地创建一个议题（Issue），并且添加标签「Enhancement」。不要忘记给项目点一个 Star⭐！再次感谢！

1. 复刻（Fork）本项目
2. 创建你的 Feature 分支 (git checkout -b feature/AmazingFeature)
3. 提交你的变更 (git commit -m 'Add some AmazingFeature')
4. 推送到该分支 (git push origin feature/AmazingFeature)
5. 创建一个拉取请求（Pull Request）


<!-- LICENSE -->
## 许可证

根据 GPL v3.0 许可证分发。打开 `LICENSE` 查看更多内容。





<!-- CONTACT -->
## 联系

* [@晓游ChR](https://space.bilibili.com/437313511) - XiaoYouChR@outlook.com


<!-- ACKNOWLEDGMENTS -->
## 引用

* [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) 强大且方便的 UI 库
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template)  方便的 README 模板

## 致谢

* [@ZhiYiyo](https://github.com/zhiyiYo/) 是大佬！为该项目的开发提供了很多帮助！
* [@一只透明人-](https://space.bilibili.com/554365148/) 测试了几乎从 Ghost-Downloader-1 开始的每个程序版本



<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[contributors-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[forks-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/network/members
[stars-shield]: https://img.shields.io/github/stars/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[stars-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/stargazers
[issues-shield]: https://img.shields.io/github/issues/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[issues-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/issues
[license-shield]: https://img.shields.io/github/license/XiaoYouChR/Ghost-Downloader-3.svg?style=for-the-badge
[license-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/blob/master/LICENSE
[product-screenshot]: images/screenshot.png