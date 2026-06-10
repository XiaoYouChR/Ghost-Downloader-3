import QtQuick
import RinUI

// Ghost Downloader gui 壳：单导航项 → 下载任务页。后续按 IA 补「新建/设置」。
FluentWindow {
    id: window
    visible: true  // RinUI 0.4 的窗口基类不再自动显示，得自己点亮
    width: 900
    height: 600
    minimumWidth: 720
    minimumHeight: 480
    title: "Ghost Downloader"

    Component.onCompleted: {
        Theme.setBackdropEffect("mica")
        Theme.setThemeColor("#0078D4")     // 对齐 GD 跟随系统的蓝，而非 RinUI 默认紫
        applyTheme(backend.config.customThemeMode)
    }

    // cfg 里的主题模式（Light/Dark/System）到达或被设置页改动时应用；System 映射到 RinUI 的 Auto
    function applyTheme(mode) {
        Theme.setTheme(mode === "System" ? Theme.mode.Auto : mode)
    }
    Connections {
        target: backend
        function onConfigChanged() { applyTheme(backend.config.customThemeMode) }
    }

    defaultPage: Qt.resolvedUrl("TaskPage.qml")

    navigationItems: [
        {
            title: "下载任务",
            page: Qt.resolvedUrl("TaskPage.qml"),
            icon: "ic_fluent_arrow_download_20_regular"
        },
        {
            title: "设置",
            page: Qt.resolvedUrl("SettingsPage.qml"),
            icon: "ic_fluent_settings_20_regular",
            position: Position.Bottom
        }
    ]

    // 链接解析失败时弹个提示——这种失败没有任务卡片可挂，只能用浮层
    Connections {
        target: backend
        function onTaskAddFailed(reason) {
            floatLayer.createInfoBar({title: "添加失败", text: reason, severity: Severity.Error, timeout: 4000})
        }
        function onUpdateAvailable(version) {
            floatLayer.createInfoBar({title: "发现新版本 " + version, text: "可前往 GitHub 发布页下载更新", severity: Severity.Info, timeout: 8000})
        }
    }
}
