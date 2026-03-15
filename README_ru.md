<h4 align="right">
  <a href="README_zh.md">简体中文</a> | <a href="README.md">English</a> | Русский
</h4>

> [!NOTE]
> По рабочим причинам скорость разработки этого проекта в последнее время замедлилась.
> Проект все еще находится на ранней стадии, и в нем пока много недоработок.

> [!TIP]
> Если вы хотите использовать Ghost-Downloader-3 на Windows 7, пожалуйста, скачайте версию `v3.5.8-Portable`.

<!-- PROJECT LOGO -->
<div align="center">

![Banner](app/assets/banner.webp)

<a href="https://trendshift.io/repositories/13847" target="_blank"><img src="https://trendshift.io/api/badge/repositories/13847" alt="XiaoYouChR%2FGhost-Downloader-3 | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

<h3>
    Кроссплатформенный многопоточный загрузчик нового поколения с поддержкой ИИ
</h3>

[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![Release][release-shield]][release-url]
[![Downloads][downloads-shield]][release-url]
[![QQGroup](https://img.shields.io/badge/QQ_Group-756042420-blue.svg?color=blue&style=for-the-badge)](https://qm.qq.com/q/gPk6FR1Hby)

<h4>
  <a href="https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/new?template=bug_report.yml">Сообщить об ошибке</a>
·    
  <a href="https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/new?template=feature_request.yml">Запросить функцию</a>
</h4>

</div>

<!-- ABOUT THE PROJECT -->
## О проекте

* Загрузчик, разработанный из личного интереса, и мой первый проект на Python 😣
* Изначально он задумывался, чтобы помочь одному Bilibili-аплоадеру с интеграцией ресурсов 😵‍💫
* Среди функций: интеллектуальное разбиение на части как в IDM без объединения файлов и умное ускорение на базе ИИ 🚀
* Благодаря доступности Python🐍 в будущем проект будет поддерживать плагины🧩, чтобы максимально раскрыть преимущества Python🐍

|    Платформа    | Требуемая версия |  Архитектуры   | Совместимость |
|:--------------:|:----------------:|:--------------:|:-------------:|
|  🐧 **Linux**  |  `glibc 2.35+`   | `x86_64`/`arm64` |      ✅       |
| 🪟 **Windows** |     `7 SP1+`     | `x86_64`/`arm64` |      ✅       |
|  🍎 **macOS**  |     `11.0+`      | `x86_64`/`arm64` |      ✅       |

> [!TIP]
> **Поддержка Arch Linux AUR**: теперь доступны поддерживаемые сообществом пакеты `ghost-downloader-bin` и `ghost-downloader-git` (сопровождающий: [@zxp19821005](https://github.com/zxp19821005))

<!-- ROADMAP -->
## Дорожная карта

- ✅ Глобальные настройки
- ✅ Более подробная информация о загрузке
- ✅ Запланированные задачи
- ✅ Оптимизация расширения браузера
- ✅ Глобальное ограничение скорости
- ✅ Оптимизация памяти
  - ✅ Обновление версии Qt
  - ✅ Повторное использование HttpClient
  - ✅ Замена части многопоточности на корутины (В процессе... см. ветку: feature/Structure)
- ❌ Переход MVC → MVVM и новая архитектура на основе событий
- ❌ Расширенное редактирование задач (мощные функции вроде привязки нескольких клиентов к одной задаче)
- ❌ Загрузка Magnet/BT (рассматривается реализация на libtorrent)
- ❌ Мощная система плагинов (В процессе... см. ветку: feature/Plugins)
- ❌ Расширенные возможности расширения браузера

Посетите [Open issues](https://github.com/XiaoYouChR/Ghost-Downloader-3/issues), чтобы увидеть все запрошенные функции (и известные проблемы).

<!-- SPONSOR -->
## Спонсор

| [![SignPath](https://signpath.org/assets/favicon-50x50.png)](https://signpath.org/) | Бесплатная подпись кода на Windows предоставлена [SignPath.io](https://signpath.io), сертификат — [SignPath Foundation](https://signpath.org) |
|-------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------|

<!-- CONTRIBUTING -->
## Вклад

Вклад делает сообщество открытого ПО удивительным местом для обучения, вдохновения и творчества. Любой ваш вклад **очень ценится**.

Если у вас есть предложение, сделайте форк репозитория и создайте pull request. Также можно просто открыть issue с меткой "Enhancement". Не забудьте поставить проекту звезду⭐! Еще раз спасибо!

1. Сделайте форк проекта
2. Создайте свою ветку для функции (git checkout -b feature/AmazingFeature)
3. Зафиксируйте изменения (git commit -m 'Add some AmazingFeature')
4. Отправьте ветку (git push origin feature/AmazingFeature)
5. Откройте pull request

Спасибо всем участникам, которые внесли вклад в этот проект!

[![Contributors](http://contrib.nn.ci/api?repo=XiaoYouChR/Ghost-Downloader-3)](https://github.com/XiaoYouChR/Ghost-Downloader-3/graphs/contributors)

<!-- SCREEN SHOTS -->
## Скриншоты

[![Demo Screenshot][product-screenshot]](https://space.bilibili.com/437313511)

<!-- LICENSE -->
## Лицензия

Распространяется по лицензии GPL v3.0. Подробнее смотрите в `LICENSE`.

Copyright © 2025 XiaoYouChR.

<!-- CONTACT -->
## Контакты

* [E-mail](mailto:XiaoYouChR@qq.com) - XiaoYouChR@qq.com
* [QQ Group](https://qm.qq.com/q/PlUBdzqZCm) - 531928387

<!-- ACKNOWLEDGMENTS -->
## Ссылки

* [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) Powerful, extensible and beautiful Fluent Design widgets
* [Curl-cffi](https://github.com/lexiforest/curl_cffi) A http client that can impersonate browser tls/ja3/http2 fingerprints
* [Loguru](https://github.com/Delgan/loguru)  A library which aims to bring enjoyable logging in Python
* [Nuitka](https://github.com/Nuitka/Nuitka) The Python compiler
* [PySide6](https://github.com/PySide/pyside-setup) The official Python module
* [Darkdetect](https://github.com/albertosottile/darkdetect) Allow to detect if the user is using Dark Mode on
* [pyqt5-concurrent](https://github.com/AresConnor/pyqt5-concurrent) A QThreadPool based task concurrency library
* [Desktop-notifier](https://github.com/samschott/desktop-notifier)Python library for cross-platform desktop notifications

## Благодарности

* [@zhiyiYo](https://github.com/zhiyiYo/) Оказал большую помощь проекту!
* [@一只透明人-](https://space.bilibili.com/554365148/) Протестировал почти каждую версию, начиная с Ghost-Downloader-1!
* [@Sky·SuGar](https://github.com/SuGar0218/) Создал баннер проекта!
* [@ReM2812](https://github.com/ReM2812/) Перевёл интерфейс программы и README на русский язык! 

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
[product-screenshot]: app/assets/screenshot.png
[release-shield]: https://img.shields.io/github/v/release/XiaoYouChR/Ghost-Downloader-3?style=for-the-badge
[release-url]: https://github.com/XiaoYouChR/Ghost-Downloader-3/releases/latest
[downloads-shield]: https://img.shields.io/github/downloads/XiaoYouChR/Ghost-Downloader-3/total?style=for-the-badge