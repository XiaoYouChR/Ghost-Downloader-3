from PySide6.QtWidgets import QApplication
from qfluentwidgets import setTheme, Theme, FluentIcon

from app.components.custom_components import IconBodyLabel

if __name__ == "__main__":
    app = QApplication([])

    setTheme(Theme.LIGHT, save=False)

    window = IconBodyLabel("Sample Text", FluentIcon.WIFI, None)
    window.show()

    app.exec()
