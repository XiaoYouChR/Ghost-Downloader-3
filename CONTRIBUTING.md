# Contributing to Ghost Downloader

## AI 工具使用政策

Ghost Downloader 欢迎使用 AI 工具辅助开发，但请在提交 PR 时如实声明。

### 为什么？

声明 AI 的参与程度，有助于维护者在 review 时有针对性地关注相关部分。

### 怎么声明？

在 PR 模板的 "AI 工具使用" 部分勾选适用的选项：

- **辅助开发** — AI 用于代码补全、查阅 API 用法、辅助调试等。勾选即可，无需额外说明。
- **主要生成** — AI 生成了 PR 中的大量代码或核心逻辑。请注明使用的工具和模型（如 `Cursor + Claude Sonnet 4`）。不确定模型的话写"模型未知"即可。

## 贡献者许可协议（CLA）

首次提交 PR 时，CLA Assistant 会请你签署 [贡献者许可协议](https://gist.github.com/XiaoYouChR/45552e04f1ba6234fa372e11e37dc91d)。

### 为什么？

引擎（`app/` 中桌面界面以外的部分和 `features/`）也会用在不开源的移动端里。CLA 让你的贡献可以随引擎一起进入移动端。

### 桌面版和引擎仍然开源吗？

是。公开仓库中的代码始终以 GPL v3 提供，CLA 第 7 条对此做了承诺。

### 只改桌面界面需要签吗？

只改 `app/view/` 的 PR 不会进入移动端，不签也可以合并。

---

## AI Tool Usage Policy

Ghost Downloader welcomes the use of AI tools in development, but please disclose AI usage when submitting a PR.

### Why?

Disclosing AI involvement helps maintainers focus their review on the parts that need closer attention.

### How to disclose?

Check the applicable option in the "AI Tool Usage" section of the PR template:

- **Assisted development** — AI was used for code completion, looking up API usage, debugging assistance, etc. Just check the box, no further explanation needed.
- **Primarily generated** — AI generated a significant portion of the code or core logic in the PR. Please specify the tool and model (e.g. `Cursor + Claude Sonnet 4`). If you're unsure about the model, just write "model unknown".

## Contributor License Agreement (CLA)

When you open your first PR, CLA Assistant will ask you to sign the [Contributor License Agreement](https://gist.github.com/XiaoYouChR/45552e04f1ba6234fa372e11e37dc91d).

### Why?

The engine (`features/` and everything in `app/` except the desktop UI) is also used in a mobile app that is not open source. The CLA lets your contribution ship there along with the engine.

### Are the desktop app and the engine still open source?

Yes. Code in the public repository is always available under GPL v3, as promised in section 7 of the CLA.

### Do I need to sign for desktop UI changes only?

PRs that only touch `app/view/` never reach the mobile app and can be merged without signing.
