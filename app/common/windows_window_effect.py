import warnings
from ctypes import c_int
from ctypes.wintypes import DWORD
from sys import getwindowsversion

from PySide6.QtGui import QColor
from _ctypes import byref, pointer
from qframelesswindow.utils.win32_utils import isGreaterEqualWin11, isCompositionEnabled, isGreaterEqualWin8_1
from qframelesswindow.windows import WindowsWindowEffect
from qframelesswindow.windows.c_structures import MARGINS, WINDOWCOMPOSITIONATTRIB, ACCENT_STATE


class WindowsWindowEffect(WindowsWindowEffect):

    def addShadowEffect(self, hWnd):
        """ Add DWM shadow to window

        Parameters
        ----------
        hWnd: int or `sip.voidptr`
            Window handle
        """
        if not isCompositionEnabled():
            return

        hWnd = int(hWnd)
        margins = MARGINS(1, 0, 0, 0)   # 防止 Windows 7 渲染多余的 Aero 效果
        self.DwmExtendFrameIntoClientArea(hWnd, byref(margins))

    def setAeroEffect(self, hWnd):
        """ Add the aero effect to the window

        Parameters
        ----------
        hWnd: int or `sip.voidptr`
            Window handle
        """
        hWnd = int(hWnd)
        if isGreaterEqualWin8_1():
            self.winCompAttrData.Attribute = WINDOWCOMPOSITIONATTRIB.WCA_ACCENT_POLICY.value
            self.accentPolicy.AccentState = ACCENT_STATE.ACCENT_ENABLE_BLURBEHIND.value
            self.SetWindowCompositionAttribute(hWnd, pointer(self.winCompAttrData))
        else:
            margins = MARGINS(-1, -1, -1, -1)
            self.DwmExtendFrameIntoClientArea(hWnd, byref(margins))

    def setBorderAccentColor(self, hWnd, color:QColor):
        """ Set the border color of the window"""

        # if not isGreaterEqualWin10():
        #     return

        hWnd = int(hWnd)
        colorref =  DWORD(color.red() | (color.green() << 8) | (color.blue() << 16))
        self.DwmSetWindowAttribute(hWnd,
                                   34,
                                   byref(colorref),
                                   4)

    def removeBorderAccentColor(self, hWnd):
        """ Remove the border color of the window"""

        # if not isGreaterEqualWin10():
        #     return

        hWnd = int(hWnd)
        self.DwmSetWindowAttribute(hWnd,
                                   34,
                                   byref(DWORD(0xFFFFFFFF)),
                                   4)

    def setMicaEffect(self, hWnd, isDarkMode=False, isAlt=False, isBlur=False):
        """ Add the mica effect to the window (Win11 only)

        Parameters
        ----------
        hWnd: int or `sip.voidptr`
            Window handle

        isDarkMode: bool
            whether to use dark mode mica effect

        isAlt: bool
            whether to enable mica alt effect
        """
        if not isGreaterEqualWin11():
            warnings.warn("The mica effect is only available on Win11")
            return

        hWnd = int(hWnd)
        margins = MARGINS(16777215, 16777215, 0, 0)
        self.DwmExtendFrameIntoClientArea(hWnd, byref(margins))

        self.winCompAttrData.Attribute = WINDOWCOMPOSITIONATTRIB.WCA_ACCENT_POLICY.value
        self.accentPolicy.AccentState = ACCENT_STATE.ACCENT_ENABLE_HOSTBACKDROP.value
        self.SetWindowCompositionAttribute(hWnd, pointer(self.winCompAttrData))

        if isDarkMode:
            self.winCompAttrData.Attribute = WINDOWCOMPOSITIONATTRIB.WCA_USEDARKMODECOLORS.value
            self.SetWindowCompositionAttribute(hWnd, pointer(self.winCompAttrData))

        if getwindowsversion().build < 22523:
            self.DwmSetWindowAttribute(hWnd, 1029, byref(c_int(1)), 4)
        else:
            if isBlur:
                _ = 3
            else:
                _ = 4 if isAlt else 2
            self.DwmSetWindowAttribute(hWnd, 38, byref(c_int(_)), 4)

        self.DwmSetWindowAttribute(hWnd, 20, byref(c_int(1*isDarkMode)), 4)