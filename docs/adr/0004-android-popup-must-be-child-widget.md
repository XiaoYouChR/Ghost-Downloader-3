# Android popups must be child widgets, not top-level windows

PySide6 on Android with EGL: any second top-level window (`Qt.Popup`,
`Qt.Dialog` without a parent, or a detached `RoundMenu`) triggers the
`AndroidDeadlockProtector` in the surfaceflinger path. The EGL surface is
single-threaded; a second surface creation deadlocks against the first.
The result is a crash on devices with slow GL drivers — device-specific, not
reproducible in the emulator.

All popup-like widgets (RoundMenu, Flyout, TeachingTip) must be reparented
as child widgets of the main window. `patches.py` does this globally via
`patchMenus()`. A side-effect: `WA_DeleteOnClose` menus crash on focus
teardown during destruction (`SIGSEGV` via `libsigchain`). Fix:
`host.setFocus()` before the menu hides.

## Considered Options

- **Use QDialog with parent** — rejected: QDialog still creates a separate
  window handle on Android. Only embedding as a plain child widget avoids the
  second surface.
- **Disable hardware acceleration** — rejected: unacceptable rendering
  performance.
