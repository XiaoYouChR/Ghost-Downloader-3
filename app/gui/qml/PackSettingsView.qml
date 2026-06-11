import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import RinUI

// 单个 pack 的数据驱动设置组：按引擎吐的 schema（[{kind,label,key,value,options/min/max}]）逐项渲染。
// 每个控件改动即时回发 setPackSetting(packId,key,value)——pack-agnostic，核心不认识具体 pack，只按 kind 画。
ColumnLayout {
    id: view
    property string packId
    property string title
    property var schema: []
    spacing: 6

    Text { text: view.title; typography: Typography.BodyStrong }

    Repeater {
        model: view.schema
        delegate: Loader {
            required property var modelData
            Layout.fillWidth: true
            sourceComponent: modelData.kind === "switch" ? switchRow
                           : modelData.kind === "combo" ? comboRow
                           : modelData.kind === "int" ? intRow
                           : modelData.kind === "folder" ? folderRow
                           : modelData.kind === "lines" ? linesRow
                           : modelData.kind === "status" ? statusRow
                           : modelData.kind === "action" ? actionRow
                           : modelData.kind === "biliLogin" ? biliLoginRow
                           : textRow
            onLoaded: item.modelData = modelData
        }
    }

    Component {
        id: switchRow
        RowLayout {
            property var modelData
            Layout.fillWidth: true
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            Item { Layout.fillWidth: true }
            Switch {
                id: sw
                checked: modelData ? modelData.value : false
                // 普通开关即时生效；带 confirmOn 的（如 GitHub 加速）开到该值要先确认协议，拒绝则弹回
                onToggled: {
                    if (modelData.confirmOn !== undefined && checked === modelData.confirmOn) {
                        confirmDialog.pendingSwitch = sw
                        confirmDialog.pendingKey = modelData.key
                        confirmDialog.title = modelData.confirmTitle || "确认"
                        confirmText.text = modelData.confirmText || ""
                        confirmDialog.open()
                    } else {
                        backend.setPackSetting(view.packId, modelData.key, checked)
                    }
                }
            }
        }
    }

    // 确认门：带 confirmOn 的设置改到该值时弹此框，同意才落、取消则把开关弹回原位
    Dialog {
        id: confirmDialog
        property var pendingSwitch: null
        property string pendingKey: ""
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        ScrollView {
            implicitWidth: 520
            implicitHeight: 280
            Text { id: confirmText; width: 500; wrapMode: Text.WordWrap }
        }
        onAccepted: backend.setPackSetting(view.packId, pendingKey, true)
        onRejected: if (pendingSwitch) pendingSwitch.checked = false
    }

    // biliLogin：B站账号登录（扫码 + 退出）。用户拍板的 gui↔bili 耦合；扫码框在 SettingsPage 接 backend 信号弹
    Component {
        id: biliLoginRow
        RowLayout {
            property var modelData
            Layout.fillWidth: true
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            Text { text: (modelData && modelData.value) ? "已登录" : "未登录"; opacity: 0.6 }
            Item { Layout.fillWidth: true }
            Button { text: "扫码登录"; onClicked: backend.startBiliLogin() }
            Button { text: "退出登录"; enabled: modelData && modelData.value; onClicked: backend.logoutBili() }
        }
    }

    // action：动作按钮（如「一键安装」），点了交引擎执行（建安装任务、当普通任务跑）
    Component {
        id: actionRow
        RowLayout {
            property var modelData
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Button {
                text: modelData ? modelData.label : ""
                onClicked: backend.runPackAction(view.packId, modelData.actionId)
            }
        }
    }

    // status：只读检测信息（如 N_m3u8DL-RE / FFmpeg 是否装好），引擎建 schema 时算好，界面只显
    Component {
        id: statusRow
        RowLayout {
            property var modelData
            Layout.fillWidth: true
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            Item { Layout.fillWidth: true }
            Text { text: modelData ? modelData.value : ""; opacity: 0.7; elide: Text.ElideMiddle; Layout.maximumWidth: 320 }
        }
    }

    Component {
        id: comboRow
        RowLayout {
            property var modelData
            Layout.fillWidth: true
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            Item { Layout.fillWidth: true }
            ComboBox {
                Layout.preferredWidth: 220
                textRole: "label"
                model: modelData ? modelData.options : []
                currentIndex: modelData
                    ? Math.max(0, modelData.options.findIndex(o => o.value === modelData.value)) : 0
                onActivated: backend.setPackSetting(view.packId, modelData.key, modelData.options[currentIndex].value)
            }
        }
    }

    Component {
        id: intRow
        RowLayout {
            property var modelData
            Layout.fillWidth: true
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            Item { Layout.fillWidth: true }
            SpinBox {
                from: modelData && modelData.min !== undefined ? modelData.min : 0
                to: modelData && modelData.max !== undefined ? modelData.max : 1000000
                value: modelData ? modelData.value : 0
                onValueModified: backend.setPackSetting(view.packId, modelData.key, value)
            }
        }
    }

    Component {
        id: textRow
        RowLayout {
            property var modelData
            Layout.fillWidth: true
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            Item { Layout.fillWidth: true }
            TextField {
                Layout.preferredWidth: 240
                text: modelData ? modelData.value : ""
                placeholderText: modelData && modelData.placeholder ? modelData.placeholder : ""
                onEditingFinished: backend.setPackSetting(view.packId, modelData.key, text)
            }
        }
    }

    Component {
        id: folderRow
        RowLayout {
            property var modelData
            Layout.fillWidth: true
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            Item { Layout.fillWidth: true }
            TextField {
                id: folderInput
                Layout.preferredWidth: 200
                text: modelData ? modelData.value : ""
                onEditingFinished: backend.setPackSetting(view.packId, modelData.key, text)
            }
            Button { text: "选择"; onClicked: { packFolderDialog.target = folderInput; packFolderDialog.key = modelData.key; packFolderDialog.open() } }
        }
    }

    Component {
        id: linesRow
        ColumnLayout {
            property var modelData
            Layout.fillWidth: true
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            TextArea {
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                text: modelData ? modelData.value.join("\n") : ""
                onEditingFinished: backend.setPackSetting(view.packId, modelData.key,
                    text.split("\n").map(s => s.trim()).filter(s => s !== ""))
            }
        }
    }

    FolderDialog {
        id: packFolderDialog
        property var target: null
        property string key: ""
        onAccepted: if (target) {
            target.text = String(selectedFolder).replace("file:///", "")
            backend.setPackSetting(view.packId, key, target.text)
        }
    }
}
