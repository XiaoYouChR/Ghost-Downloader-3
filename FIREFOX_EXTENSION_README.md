# Firefox Extension 集成说明

## 概述

本项目现已完整支持 Firefox 浏览器扩展，与现有的 Chrome 扩展并行运行。Firefox 扩展与 Chrome 扩展共享核心代码，通过浏览器 API 兼容层来处理差异。

## 新增文件

### 1. **Firefox 特定的 Manifest**
- `browser_extension/app/public/manifest-firefox.json`
  - Firefox Manifest V3 配置
  - 包含 Firefox 特定的 browser_specific_settings
  - 扩展 ID: `ghost-downloader@xiaoyouchr.com`

### 2. **构建脚本**
- `browser_extension/app/scripts/build-firefox.mjs`
  - 编译 Firefox 扩展的主构建脚本
  - 使用 IIFE 格式编译 background script（Firefox 兼容性更好）
  - 输出目录: `browser_extension/firefox/`

- `browser_extension/app/scripts/package-firefox-xpi.mjs`
  - 打包 Firefox 扩展为 .xpi 文件
  - 输出: `firefox_extension.xpi`

### 3. **浏览器兼容性层**
- `browser_extension/app/src/shared/browser-compat.ts`
  - 提供统一的跨浏览器 API
  - 自动检测 Chrome/Firefox 环境
  - 封装常用 API（storage, tabs, downloads 等）

### 4. **修改的源文件**
- `browser_extension/app/src/content-script.ts`
  - 现在使用 `browserRuntime` 变量兼容两种浏览器
  - 自动检测并使用正确的 runtime API

### 5. **项目配置更新**
- `browser_extension/app/package.json`
  - 新增脚本: `build:firefox` 和 `package:firefox`
  - 新增依赖: `archiver` (用于生成 .xpi 文件)

- `app/assets/resources.qrc`
  - 启用 `firefox_extension.xpi` 资源引用

## 快速开始

### 构建 Firefox 扩展

```bash
cd browser_extension/app

# 构建 Firefox 扩展
npm run build:firefox

# 生成 .xpi 文件（可选）
npm run package:firefox
```

### 测试 Firefox 扩展

#### 方式一：临时加载（推荐用于开发）

1. 打开 Firefox，访问 `about:debugging`
2. 点击左侧的 "This Firefox"
3. 点击 "Load Temporary Add-on"
4. 选择 `browser_extension/firefox/` 目录下的 `manifest.json`

#### 方式二：使用 web-ext 工具

```bash
cd browser_extension/firefox
npx web-ext run
```

### 同时构建两个平台

```bash
cd browser_extension/app

# Chrome
npm run build

# Firefox
npm run build:firefox
```

## 技术细节

### Manifest 差异

| 特性 | Chrome | Firefox |
|------|--------|---------|
| 最低版本 | 114 | 109 |
| Service Worker | ESM 模块 | 支持 ESM 和 IIFE |
| Background | service_worker | scripts |
| Browser ID | 不需要 | 需要 (gecko) |
| storage.session | 支持 | 不支持 (fallback: local) |

### 浏览器 API 检测

```typescript
// 自动检测
const isFirefox = typeof (global as any).browser !== "undefined";
const runtime = isFirefox ? browser.runtime : chrome.runtime;

// 或使用兼容性层
import { browserAPI, detectBrowser } from "./shared/browser-compat";
const browser_type = detectBrowser(); // "chrome" | "firefox"
```

### 权限映射

Firefox 使用与 Chrome 相同的权限格式：

```json
{
  "permissions": ["alarms", "downloads", "scripting", "storage", "tabs", ...],
  "host_permissions": ["<all_urls>"]
}
```

## 文件改动总结

### 新建文件
- ✅ `browser_extension/app/public/manifest-firefox.json`
- ✅ `browser_extension/app/scripts/build-firefox.mjs`
- ✅ `browser_extension/app/scripts/package-firefox-xpi.mjs`
- ✅ `browser_extension/app/src/shared/browser-compat.ts`
- ✅ `browser_extension/FIREFOX_BUILD.md`
- ✅ `FIREFOX_EXTENSION_README.md` (本文件)

### 修改文件
- ✅ `browser_extension/app/src/content-script.ts` - 添加浏览器检测和兼容的 API 调用
- ✅ `browser_extension/app/package.json` - 新增脚本和依赖
- ✅ `app/assets/resources.qrc` - 启用 firefox_extension.xpi

### Chrome 兼容性
✅ Chrome 扩展构建和打包完全不受影响

## 关键设计决策

### 1. **共享代码库**
- 最小化代码重复
- 通过浏览器检测在运行时选择正确的 API

### 2. **IIFE 格式用于 Background Script**
- Firefox 对 IIFE 格式的兼容性更好
- Chrome 的 Service Worker 格式仍然使用 ESM

### 3. **兼容性层结构**
- `browser-compat.ts` 提供高级 API
- `content-script.ts` 自动检测浏览器

## 已知限制

1. **Firefox 不支持 chrome.storage.session**
   - 自动 fallback 到 `chrome.storage.local`
   - 在 background 脚本中通过 `bridgeStorageArea()` 处理

2. **内容脚本隔离上下文**
   - Chrome: 完全隔离的世界 (isolated world)
   - Firefox: 内容脚本沙箱
   - 都支持相同的消息传递 API

3. **下载拦截**
   - Chrome: `chrome.downloads` API 支持完整功能
   - Firefox: 同样支持，但某些高级特性可能有差异

## 版本管理

两个平台共享相同的版本号，更新时需要修改：

```json
// manifest.json 和 manifest-firefox.json
"version": "1.2.1"

// package.json
"version": "1.2.1"
```

## 后续开发

### 如何添加新功能

1. **编辑共享源文件** (`src/background.ts`, `src/popup/*` 等)
2. **测试两个平台**:
   ```bash
   npm run build        # Chrome
   npm run build:firefox # Firefox
   ```
3. **如需特定于浏览器的代码**，使用检测：
   ```typescript
   import { detectBrowser } from "./shared/browser-compat";
   if (detectBrowser() === "firefox") {
     // Firefox 特定的代码
   }
   ```

### 添加新权限

1. 在两个 manifest 文件中添加相同的权限
2. 在 `chrome-helpers.ts` 中添加相应的 API 包装
3. 或在 `browser-compat.ts` 中扩展兼容性层

## 分发和发布

### Firefox 官方分发 (AMO)

Firefox 扩展可以提交到 [Mozilla Add-ons](https://addons.mozilla.org/)：

1. 注册开发者账号
2. 上传 .xpi 文件或源代码
3. 通过审核后自动分发

### 自托管

对于自托管分发：
- 使用生成的 `.xpi` 文件
- 配置正确的 MIME 类型 (`application/x-xpinstall`)

## 调试和故障排除

### 查看扩展日志

1. 打开 `about:debugging`
2. 找到扩展，点击 "Inspect"
3. 在 Console 标签查看输出

### 常见问题

**问**: 为什么 Firefox 构建失败？
**答**: 检查是否运行了 `npm install` 并且 `archiver` 已安装

**问**: Content script 报错 "chrome is not defined"？
**答**: 确保使用了 `browserRuntime` 变量而不是直接 `chrome`

**问**: Storage 操作失败？
**答**: Firefox 不支持 `chrome.storage.session`，使用 `chrome.storage.local`

## 相关文档

- [Firefox WebExtensions 文档](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/)
- [Chrome Extensions 文档](https://developer.chrome.com/docs/extensions/mv3/)
- [WebExtensions API 兼容表](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API)
- 本项目的 `browser_extension/FIREFOX_BUILD.md`

## 贡献指南

当提交与浏览器扩展相关的 PR 时：

1. 确保两个平台都能正常编译
2. 在 Firefox 上手动测试新功能
3. 更新相关文档
4. 如有特定于浏览器的代码，请添加注释说明原因

---

**最后更新**: 2026-03-29
**主要版本**: 1.2.1
