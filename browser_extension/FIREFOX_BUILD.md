# Firefox Browser Extension Build Guide

## Overview

This guide explains how to build and package the Ghost Downloader Firefox extension alongside the existing Chrome extension.

## Directory Structure

```
browser_extension/
├── app/
│   ├── public/
│   │   ├── manifest.json              # Chrome manifest (Manifest V3)
│   │   └── manifest-firefox.json      # Firefox manifest (Manifest V3)
│   ├── scripts/
│   │   ├── build.mjs                  # Chrome build script
│   │   ├── build-firefox.mjs          # Firefox build script
│   │   └── package-firefox-xpi.mjs    # XPI packaging script
│   ├── src/
│   │   ├── shared/
│   │   │   └── browser-compat.ts      # Browser compatibility layer
│   │   ├── background.ts              # Shared background script
│   │   ├── content-script.ts          # Content script (browser-compatible)
│   │   └── popup/                     # React UI components
│   └── package.json
├── chromium/                           # Built Chrome extension (output)
├── firefox/                            # Built Firefox extension (output)
└── upstream/                           # Upstream resources
```

## Building the Firefox Extension

### Prerequisites

1. Node.js 18+ 
2. Dependencies installed: `npm install`

### Build Steps

#### Step 1: Build the Firefox Extension

```bash
cd browser_extension/app
npm run build:firefox
```

This command:
- Builds the React popup UI with Vite
- Compiles TypeScript background script with ESBuild for Firefox (IIFE format)
- Compiles TypeScript content script with ESBuild for Firefox
- Copies upstream resources
- Copies the Firefox-specific manifest.json

Output directory: `browser_extension/firefox/`

#### Step 2: Create the XPI Package

```bash
npm run package:firefox
```

This creates a compressed XPI file at `firefox_extension.xpi`

### Building Both Chrome and Firefox Extensions

```bash
npm run build              # Chrome
npm run build:firefox      # Firefox
npm run package:firefox    # Package Firefox as XPI
```

## Key Differences Between Chrome and Firefox

### Manifest Version
- **Chrome**: Manifest V3 (required, V2 is deprecated)
- **Firefox**: Manifest V3 (supported since Firefox 109)

### Permissions Model
- **Chrome**: Uses `permissions` and `host_permissions` arrays
- **Firefox**: Same format as Chrome, but with some API differences

### Background Scripts
- **Chrome**: Uses Service Worker (ESM format with `type: "module"`)
- **Firefox**: Can use background scripts (both IIFE and ESM supported)
  - We use IIFE format for better compatibility

### API Compatibility
- **chrome.storage.session**: Not available in Firefox
  - Fallback to chrome.storage.local
- **chrome.downloads**: Supported in both
- **chrome.tabs**: Supported in both
- **chrome.action**: Supported in both (previously chrome.browserAction)

### Content Scripts
- **Chrome**: Uses isolated world for content scripts
- **Firefox**: Uses content script sandbox
  - Both browsers support the same messaging API

## Firefox Manifest Specifics

Key additions in `manifest-firefox.json`:

```json
{
  "browser_specific_settings": {
    "gecko": {
      "id": "ghost-downloader@xiaoyouchr.com",
      "strict_min_version": "109.0"
    }
  }
}
```

The browser ID (UUID or email format) is required for Firefox self-hosted extensions.

## Browser Compatibility in Code

The `src/content-script.ts` detects and uses the appropriate browser API:

```typescript
const isFirefox = typeof (global as any).browser !== "undefined";
const browserRuntime = isFirefox 
  ? (global as any).browser.runtime 
  : (global as any).chrome.runtime;
```

### Available Compatibility Layer (`src/shared/browser-compat.ts`)

For future development, a dedicated compatibility module is available:

```typescript
import { browserAPI, detectBrowser } from "./shared/browser-compat";

const browser = detectBrowser(); // "chrome" | "firefox"
const isFirefox = browserAPI.isFirefox;

// Use browserAPI.runtime, browserAPI.tabs, etc.
```

## Testing the Firefox Extension

### Manual Testing

1. Open Firefox and navigate to `about:debugging`
2. Click "This Firefox" in the left sidebar
3. Click "Load Temporary Add-on"
4. Select the `manifest.json` from `browser_extension/firefox/`

### Automated Testing

The extension logs all communication with the desktop app. Check the browser console:

```
about:debugging → Select the extension → Inspect → Console
```

## Distribution

For production, Firefox extensions should be submitted to:
- **Mozilla Add-ons**: https://addons.mozilla.org/

The XPI file can be:
- Self-hosted with proper signed certificates
- Submitted to AMO for official distribution
- Side-loaded for testing

## Troubleshooting

### `firefox_extension.xpi` not found after build

Ensure you've run `npm run build:firefox` first to generate the build output.

### Content script errors about `chrome` undefined

The content script now auto-detects Firefox and uses `browser` API. Check browser console for details.

### Background script communication fails

Verify the manifest permissions match what the backend needs. Compare with `manifest-firefox.json`.

### Build fails with TypeScript errors

Run `npm run typecheck` to see full TypeScript diagnostics.

## Related Files

- `/app/assets/resources.qrc` - Includes firefox_extension.xpi reference
- `/app/supports/config.py` - Firefox add-ons URL reference
- `README.md` - Main project documentation

## Updates to Chrome Extension

When updating the shared source code (e.g., `background.ts`, `content-script.ts`):

1. Ensure changes are backward compatible with Chrome
2. Test both platforms: `npm run build && npm run build:firefox`
3. Update both manifest files if permissions change
4. Update this documentation if API usage changes

## Version Management

Both Chrome and Firefox extensions share the same version number in their manifests. Update in both files when releasing:

- `public/manifest.json` - Chrome
- `public/manifest-firefox.json` - Firefox
- `package.json` - Build tooling

## Additional Resources

- [Firefox WebExtensions API](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API)
- [Chrome Extensions Documentation](https://developer.chrome.com/docs/extensions/mv3/)
- [Web Manifest V3 Spec](https://w3c.github.io/webextensions/)
