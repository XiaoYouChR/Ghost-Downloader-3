import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI

// 「资源下载」页（复刻原版 jack_yao 资源中心）：拉远程资源列表 → 每个资源选版本下载。
// 用户拍板接受的 gui↔jack_yao 耦合；远程列表 + 真实下载需联网验。
FluentPage {
    id: root
    title: "资源下载"

    property var resources: []
    property string status: "正在加载…"

    Component.onCompleted: backend.loadJackYaoResources()

    Connections {
        target: backend
        function onJackYaoResources(list) { root.resources = list; root.status = "" }
        function onJackYaoError(message) { root.status = "加载失败：" + message }
    }

    Text {
        text: root.status
        visible: root.resources.length === 0
        opacity: 0.6
    }

    Button {
        text: "刷新"
        visible: root.resources.length === 0 && root.status.indexOf("失败") >= 0
        onClicked: { root.status = "正在加载…"; backend.loadJackYaoResources() }
    }

    Repeater {
        model: root.resources
        delegate: Frame {
            required property var modelData
            Layout.fillWidth: true
            RowLayout {
                anchors.fill: parent
                spacing: 12
                Image {
                    Layout.preferredWidth: 56; Layout.preferredHeight: 56
                    source: modelData.Icon ? "data:image/png;base64," + modelData.Icon : ""
                    sourceSize.width: 56; sourceSize.height: 56
                    fillMode: Image.PreserveAspectFit
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text { text: modelData.Name || ""; typography: Typography.BodyStrong }
                    Text {
                        Layout.fillWidth: true
                        text: (modelData.Intro || "").replace(/\\n/g, "\n")
                        wrapMode: Text.WordWrap; opacity: 0.7; typography: Typography.Caption
                    }
                }
                ComboBox {
                    id: versionCombo
                    Layout.preferredWidth: 140
                    textRole: "Version"
                    model: modelData.List || []
                }
                Button {
                    text: "下载"
                    onClicked: if (modelData.List && modelData.List.length > 0)
                        backend.addJackYaoResource(modelData.List[versionCombo.currentIndex].Url)
                }
            }
        }
    }
}
