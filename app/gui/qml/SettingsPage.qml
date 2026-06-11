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
        Text { text: "按类型归类到子目录"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        Button { text: "管理分类"; visible: backend.config.enableCategory; onClicked: categoryDialog.open() }
        Switch {
            checked: backend.config.enableCategory
            onToggled: backend.setConfig("enableCategory", checked)
        }
    }

    Dialog {
        id: categoryDialog
        title: "管理分类规则"
        modal: true
        standardButtons: Dialog.Close
        ColumnLayout {
            implicitWidth: 560
            spacing: 10
            ListView {
                Layout.fillWidth: true
                implicitHeight: 240
                clip: true
                model: backend.categoryRuleModel
                delegate: RowLayout {
                    width: ListView.view.width
                    spacing: 8
                    Icon { icon: "ic_fluent_tag_20_regular"; size: 16 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Text { text: model.name; typography: Typography.BodyStrong }
                        Text { text: model.extensionsText; opacity: 0.6; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    Text { text: model.folder; opacity: 0.5; elide: Text.ElideMiddle; Layout.preferredWidth: 140 }
                    ToolButton { icon.name: "ic_fluent_delete_20_regular"; onClicked: backend.categoryRuleModel.removeAt(index) }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                TextField { id: catNameField; Layout.preferredWidth: 96; placeholderText: "名称" }
                TextField { id: catExtField; Layout.fillWidth: true; placeholderText: "扩展名，逗号分隔" }
                TextField { id: catFolderField; Layout.preferredWidth: 150; placeholderText: "{default}/子目录" }
                ComboBox {
                    id: catIconCombo
                    Layout.preferredWidth: 120
                    model: ["VIDEO", "MUSIC", "PHOTO", "CHAT", "DOCUMENT", "ZIP_FOLDER", "APPLICATION", "HELP"]
                }
                Button {
                    text: "添加"
                    onClicked: {
                        backend.categoryRuleModel.add(catNameField.text, catExtField.text, catFolderField.text, catIconCombo.currentText)
                        catNameField.text = ""
                        catExtField.text = ""
                        catFolderField.text = ""
                    }
                }
            }
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
        visible: backend.config.enableSpeedLimitation  // 开关关时无意义，藏起来
        Text { text: "限速值"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        SpinBox {
            from: 1
            to: 102400
            stepSize: 512
            value: Math.round(backend.config.speedLimitation / 1024)  // cfg 存字节，界面按 KB/s
            onValueModified: backend.setConfig("speedLimitation", value * 1024)
        }
        Text { text: "KB/s"; typography: Typography.Body; opacity: 0.7 }
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
        Text { text: "下载 User-Agent"; typography: Typography.Body }
        Item { Layout.fillWidth: true }
        ComboBox {
            id: uaCombo
            Layout.preferredWidth: 240
            textRole: "name"
            model: backend.userAgentOptions()
            // 初始选中当前生效的 UA（按 value 匹配）
            Component.onCompleted: {
                for (let i = 0; i < model.length; i++)
                    if (model[i].value === backend.config.activeUserAgent) { currentIndex = i; break }
            }
            onActivated: backend.setConfig("activeUserAgent", model[currentIndex].value)
        }
        Button { text: "管理"; onClicked: uaDialog.open() }
    }

    Dialog {
        id: uaDialog
        title: "管理 User-Agent"
        modal: true
        standardButtons: Dialog.Close
        ColumnLayout {
            implicitWidth: 520
            spacing: 10
            ListView {
                Layout.fillWidth: true
                implicitHeight: 220
                clip: true
                model: backend.userAgentModel
                delegate: RowLayout {
                    width: ListView.view.width
                    spacing: 8
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Text { text: model.name; typography: Typography.BodyStrong }
                        Text { text: model.value; opacity: 0.6; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    ToolButton { icon.name: "ic_fluent_delete_20_regular"; onClicked: backend.userAgentModel.removeAt(index) }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                TextField { id: uaNameField; Layout.preferredWidth: 120; placeholderText: "名称" }
                TextField { id: uaValueField; Layout.fillWidth: true; placeholderText: "User-Agent 字符串" }
                Button {
                    text: "添加"
                    onClicked: {
                        backend.userAgentModel.add(uaNameField.text, uaValueField.text)
                        uaNameField.text = ""
                        uaValueField.text = ""
                    }
                }
            }
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
