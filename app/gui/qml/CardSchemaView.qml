import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import RinUI

// 数据驱动卡片通用渲染器：按引擎吐的 schema（[{kind,label,field,value}]）逐卡渲染，payload() 收回 {field:value}。
// pack-agnostic——核心不认识具体 pack，只按 kind 渲染。先实现 lineedit/folder，标头(multiline)/代理(proxies)等后续补。
ColumnLayout {
    id: root
    property var schema: []
    spacing: 10

    // 收集各卡当前值，回给 backend.editTask 重解析
    function payload() {
        let result = {}
        for (let i = 0; i < rep.count; i++) {
            let card = rep.itemAt(i)
            if (card)
                result[card.fieldName] = card.fieldValue
        }
        return result
    }

    Repeater {
        id: rep
        model: root.schema
        delegate: RowLayout {
            required property var modelData
            property string fieldName: modelData.field
            property string fieldValue: input.text
            Layout.fillWidth: true
            spacing: 8
            Text { text: modelData.label; typography: Typography.Body; Layout.preferredWidth: 84 }
            TextField { id: input; Layout.fillWidth: true; text: modelData.value }
            // folder kind 给个选目录钮（lineedit 只编辑）
            Button {
                text: "选择"
                visible: modelData.kind === "folder"
                onClicked: { schemaFolderDialog.target = input; schemaFolderDialog.open() }
            }
        }
    }

    FolderDialog {
        id: schemaFolderDialog
        property var target: null
        onAccepted: if (target) target.text = String(selectedFolder).replace("file:///", "")
    }
}
