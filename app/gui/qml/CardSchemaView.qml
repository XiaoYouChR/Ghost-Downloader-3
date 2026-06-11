import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import RinUI

// 数据驱动卡片通用渲染器：按引擎吐的 schema（[{kind,label,field,value}]）逐卡渲染，payload() 收回 {field:value}。
// pack-agnostic——核心不认识具体 pack，只按 kind 渲染。每种 kind 一个组件，各自暴露 cardValue（已转成该字段的目标类型）。
ColumnLayout {
    id: root
    property var schema: []
    spacing: 10

    function payload() {
        let result = {}
        for (let i = 0; i < rep.count; i++) {
            let card = rep.itemAt(i)
            if (card && card.item)
                result[card.modelData.field] = card.item.cardValue
        }
        return result
    }

    Repeater {
        id: rep
        model: root.schema
        delegate: Loader {
            required property var modelData
            Layout.fillWidth: true
            sourceComponent: modelData.kind === "headers" ? headersCard
                           : modelData.kind === "proxies" ? proxiesCard
                           : modelData.kind === "folder" ? folderCard
                           : modelData.kind === "file" ? fileCard
                           : modelData.kind === "combo" ? comboCard
                           : modelData.kind === "lines" ? linesCard
                           : lineeditCard
            onLoaded: item.modelData = modelData
        }
    }

    // lineedit：横排 label + 单行框（cardValue=字符串）
    Component {
        id: lineeditCard
        RowLayout {
            property var modelData
            property alias cardValue: input.text
            Layout.fillWidth: true; spacing: 8
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body; Layout.preferredWidth: 84 }
            TextField {
                id: input; Layout.fillWidth: true
                text: modelData ? modelData.value : ""
                placeholderText: modelData && modelData.placeholder ? modelData.placeholder : ""
            }
        }
    }

    // file：横排 label + 路径框 + 选文件钮（解密密钥文件等单文件场景）
    Component {
        id: fileCard
        RowLayout {
            property var modelData
            property alias cardValue: fileInput.text
            Layout.fillWidth: true; spacing: 8
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body; Layout.preferredWidth: 84 }
            TextField { id: fileInput; Layout.fillWidth: true; text: modelData ? modelData.value : "" }
            Button { text: "选择"; onClicked: { schemaFileDialog.target = fileInput; schemaFileDialog.open() } }
        }
    }

    // combo：横排 label + 下拉（options=[{label,value}]）；cardValue=所选项的 value（如 M3U8 轨道的 selectExpr）
    Component {
        id: comboCard
        RowLayout {
            property var modelData
            property var cardValue: (modelData && combo.currentIndex >= 0)
                ? modelData.options[combo.currentIndex].value : ""
            Layout.fillWidth: true; spacing: 8
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body; Layout.preferredWidth: 84 }
            ComboBox {
                id: combo
                Layout.fillWidth: true
                textRole: "label"
                model: modelData ? modelData.options : []
                currentIndex: modelData
                    ? Math.max(0, modelData.options.findIndex(o => o.value === modelData.value)) : 0
            }
        }
    }

    // lines：竖排 label + 多行框（每行一项）；cardValue 转成去空的字符串列表（解密密钥、导入音轨等）
    Component {
        id: linesCard
        ColumnLayout {
            property var modelData
            property var cardValue: larea.text.split("\n").map(s => s.trim()).filter(s => s !== "")
            Layout.fillWidth: true; spacing: 4
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            TextArea {
                id: larea
                Layout.fillWidth: true
                Layout.preferredHeight: 90
                text: modelData ? modelData.value.join("\n") : ""
                placeholderText: modelData && modelData.placeholder ? modelData.placeholder : ""
            }
        }
    }

    // folder：横排 label + 路径框 + 选目录钮
    Component {
        id: folderCard
        RowLayout {
            property var modelData
            property alias cardValue: finput.text
            Layout.fillWidth: true; spacing: 8
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body; Layout.preferredWidth: 84 }
            TextField { id: finput; Layout.fillWidth: true; text: modelData ? modelData.value : "" }
            Button { text: "选择"; onClicked: { schemaFolderDialog.target = finput; schemaFolderDialog.open() } }
        }
    }

    // headers：竖排 label + 多行框（每行 Name: Value）；cardValue 转成 dict 回引擎（pack 的 parse 收 dict）
    Component {
        id: headersCard
        ColumnLayout {
            property var modelData
            property var cardValue: {
                let result = {}
                for (let line of harea.text.split("\n")) {
                    let idx = line.indexOf(":")
                    if (idx > 0) result[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
                }
                return result
            }
            Layout.fillWidth: true; spacing: 4
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body }
            TextArea {
                id: harea
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                text: modelData ? Object.keys(modelData.value).map(k => k + ": " + modelData.value[k]).join("\n") : ""
            }
        }
    }

    // proxies：combo(不使用/自定义) + 条件 url 框；cardValue=null 或 {http://:url, https://:url}（pack parse 收此 dict）
    Component {
        id: proxiesCard
        RowLayout {
            property var modelData
            property var cardValue: pcombo.currentIndex === 0 ? null
                : ({"http://": purl.text.trim(), "https://": purl.text.trim()})
            Layout.fillWidth: true; spacing: 8
            Text { text: modelData ? modelData.label : ""; typography: Typography.Body; Layout.preferredWidth: 84 }
            ComboBox {
                id: pcombo
                Layout.preferredWidth: 110
                model: ["不使用", "自定义"]
                currentIndex: (modelData && modelData.value) ? 1 : 0
            }
            TextField {
                id: purl
                Layout.fillWidth: true
                visible: pcombo.currentIndex === 1
                text: modelData ? modelData.value : ""
                placeholderText: "http://host:port"
            }
        }
    }

    FolderDialog {
        id: schemaFolderDialog
        property var target: null
        onAccepted: if (target) target.text = String(selectedFolder).replace("file:///", "")
    }

    FileDialog {
        id: schemaFileDialog
        property var target: null
        onAccepted: if (target) target.text = String(selectedFile).replace("file:///", "")
    }
}
