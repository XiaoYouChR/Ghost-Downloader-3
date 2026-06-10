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
    }
}
