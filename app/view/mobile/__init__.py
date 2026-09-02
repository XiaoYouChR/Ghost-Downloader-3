def setupAndroid() -> None:
    from .device import setupFont, setupTheme
    from .patches import (
        patchDialogWidth, patchFileDialogs, patchGroupTouch,
        patchIconRendering, patchMenus, patchOptionCardLayout,
    )

    setupTheme()
    setupFont()
    patchIconRendering()
    patchFileDialogs()
    patchDialogWidth()
    patchGroupTouch()
    patchMenus()
    patchOptionCardLayout()
