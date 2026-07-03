# Android package name: `io.github.xiaoyouchr.ghostdownloader`

The Android package name is `io.github.xiaoyouchr.ghostdownloader` with
display name "Ghost Downloader". The package name and display title are
decoupled via environment variables (`GD3_PKG_DOMAIN`, `GD3_PKG_NAME`,
`GD3_APP_TITLE`) in the build system — p4a's `--package` flag does not
tolerate spaces, but the display title needs them.

Once users install the app, the package name can never change — Android
identifies apps by package name, and a change would force a full uninstall
(losing user data and download history).
