import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI

// 设置页（最小）：并发数可改、下载目录展示。改动经 backend.setConfig 发命令落到 cfg。
FluentPage {
    title: "设置"

    // 直接做 FluentPage 的内容项：自动进它的内容列（居中、留白），不再 anchors（那会落在布局管理的子项上）
    RowLayout {
        Layout.fillWidth: true
        Text { text: "同时下载任务数"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        SpinBox {
            from: 1
            to: 64
            value: backend.config.maxTaskNum
            onValueModified: backend.setConfig("maxTaskNum", value)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "每任务分块数"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        SpinBox {
            from: 1
            to: 256
            value: backend.config.preBlockNum
            onValueModified: backend.setConfig("preBlockNum", value)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "自动提速"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        Switch {
            checked: backend.config.autoSpeedUp
            onToggled: backend.setConfig("autoSpeedUp", checked)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "校验 SSL 证书"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        Switch {
            checked: backend.config.SSLVerify
            onToggled: backend.setConfig("SSLVerify", checked)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "主题"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        RadioButton { text: "浅色"; checked: backend.config.customThemeMode === "Light"; onClicked: backend.setConfig("customThemeMode", "Light") }
        RadioButton { text: "深色"; checked: backend.config.customThemeMode === "Dark"; onClicked: backend.setConfig("customThemeMode", "Dark") }
        RadioButton { text: "跟随系统"; checked: backend.config.customThemeMode === "System"; onClicked: backend.setConfig("customThemeMode", "System") }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "限速下载"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        Switch { checked: backend.config.enableSpeedLimitation; onToggled: backend.setConfig("enableSpeedLimitation", checked) }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "线程重分配阈值"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        SpinBox {
            from: 1
            to: 100
            value: backend.config.maxReassignSize
            onValueModified: backend.setConfig("maxReassignSize", value)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "代理服务器"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        TextField {
            Layout.preferredWidth: 200
            text: backend.config.proxyServer
            placeholderText: "Auto / Off / http://..."
            onEditingFinished: backend.setConfig("proxyServer", text)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "监听剪贴板链接"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        Switch { checked: backend.config.enableClipboardListener; onToggled: backend.setConfig("enableClipboardListener", checked) }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "启动时检查更新"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        Switch { checked: backend.config.checkUpdateAtStartUp; onToggled: backend.setConfig("checkUpdateAtStartUp", checked) }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "开机自启"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        Switch { checked: backend.config.autoRun; onToggled: backend.setConfig("autoRun", checked) }
    }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "下载目录"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        Text { text: backend.config.downloadFolder; opacity: 0.7 }
    }
}
