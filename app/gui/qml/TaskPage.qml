import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import RinUI

// 下载任务页：工具栏（全部开始/暂停）、加链接、任务列表。所有动作经 backend 发命令。
// 根用 Item 而非 FluentPage：任务列表要填满页面高度、靠 anchors 贴着页面定位；
// FluentPage 的内容区是 Flickable 里高度由内容撑开的，给不出填充高度（会塌成 0）。
Item {
    id: taskPage

    property string pendingDelete: ""

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Button {
                text: "新建"; icon.name: "ic_fluent_add_20_filled"; highlighted: true
                onClicked: {
                    addUrlsField.text = ""
                    addPathField.text = ""
                    addTaskDialog.open()
                }
            }
            Button { text: "全部开始"; icon.name: "ic_fluent_play_20_filled"; onClicked: backend.startAll() }
            Button { text: "全部暂停"; icon.name: "ic_fluent_pause_20_regular"; onClicked: backend.pauseAll() }
            ToolButton { icon.name: "ic_fluent_select_all_off_20_regular"; size: 18; onClicked: taskList.setSelectionMode(true) }
            Button { text: "清空已完成"; onClicked: backend.clearCompleted() }
            // 限速快切（复刻原版工具栏；限速值在设置页）
            ToolButton {
                icon.name: backend.config.enableSpeedLimitation ? "ic_fluent_top_speed_20_filled" : "ic_fluent_top_speed_20_regular"
                highlighted: backend.config.enableSpeedLimitation
                size: 18
                onClicked: backend.setConfig("enableSpeedLimitation", !backend.config.enableSpeedLimitation)
            }

            Row {
                Layout.leftMargin: 6
                spacing: 5
                visible: backend.globalSpeedText !== ""
                Icon {
                    icon: "ic_fluent_gauge_20_regular"; size: 15
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.currentTheme.colors.textSecondaryColor
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: backend.globalSpeedText
                    color: Theme.currentTheme.colors.textSecondaryColor
                }
            }

            Item { Layout.fillWidth: true }
            ToolButton {
                icon.name: "ic_fluent_arrow_sort_20_regular"; size: 18
                onClicked: sortMenu.popup()
            }
            ToolButton {
                icon.name: "ic_fluent_filter_20_regular"; size: 18
                onClicked: filterMenu.popup()
            }
            TextField {
                Layout.preferredWidth: 200
                placeholderText: "搜索任务"
                onTextChanged: taskFilter.keyword = text
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            TextField {
                id: urlInput
                Layout.fillWidth: true
                placeholderText: "粘贴下载链接，回车或点添加"
                onAccepted: addCurrent()
            }
            Button {
                text: "添加"
                onClicked: addCurrent()
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Text {
                anchors.centerIn: parent
                horizontalAlignment: Text.AlignHCenter
                text: backend.connected ? "还没有下载任务\n粘贴链接开始" : "连接后台中…"
                opacity: 0.6
                visible: listView.count === 0
            }

            ListView {
                id: listView
                anchors.fill: parent
                clip: true
                spacing: 6
                model: taskFilter
                delegate: TaskCard {
                    width: ListView.view.width
                    taskId: model.taskId
                    fileName: model.title
                    url: model.url
                    typeIcon: model.typeIcon
                    categoryIcon: model.categoryIcon
                    running: model.running
                    completed: model.completed
                    progress: model.progress
                    speedText: model.speedText
                    leftTimeText: model.leftTimeText
                    progressText: model.progressText
                    statusText: model.statusText
                    segments: model.segments
                    chips: model.chips
                    actionKind: model.actionKind
                    errorText: model.error
                    selectionMode: taskList.selectionMode
                    selected: model.selected
                    fileCount: model.fileCount
                    output: model.output
                    onDeleteRequested: function(taskId) {
                        taskPage.pendingDelete = taskId
                        deleteDialog.open()
                    }
                    onEditRequested: function(taskId, fileName, url) {
                        backend.requestEditSchema(taskId)  // 引擎回发该任务的编辑 schema，由 Connection 弹编辑框
                    }
                    onRedownloadRequested: function(taskId) { backend.redownload(taskId) }
                    onHashRequested: function(taskId) {
                        backend.verifyHash(taskId)
                        hashDialog.open()
                    }
                }
            }
        }
    }

    // 选择模式的浮动批量操作栏（复刻 GD 的 CommandBar，浮在列表底部）
    Frame {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        visible: taskList.selectionMode
        padding: 6

        RowLayout {
            spacing: 4
            Text { Layout.leftMargin: 6; text: "已选 " + taskList.selectedCount; typography: Typography.Body }
            ToolSeparator {}
            Button { flat: true; text: "全选"; onClicked: taskList.selectAll() }
            Button { flat: true; text: "反选"; onClicked: taskList.invertSelection() }
            Button { flat: true; text: "删除选中"; onClicked: backend.removeSelected() }
            Button { flat: true; text: "取消"; onClicked: taskList.setSelectionMode(false) }
        }
    }

    Menu {
        id: sortMenu
        MenuItem { text: "按时间"; onTriggered: taskFilter.sortMode = "time" }
        MenuItem { text: "按名称"; onTriggered: taskFilter.sortMode = "name" }
    }

    Menu {
        id: filterMenu
        MenuItem { text: "全部任务"; onTriggered: taskFilter.statusFilter = "all" }
        MenuItem { text: "进行中"; onTriggered: taskFilter.statusFilter = "active" }
        MenuItem { text: "已完成"; onTriggered: taskFilter.statusFilter = "complete" }
    }

    // 两段式添加（复刻原版）：贴多条链接 → 解析预览 → 下载提交。per-URL 编辑/分类、设置卡后续分层补。
    Dialog {
        id: addTaskDialog
        title: "新建任务"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: backend.discardPreviews()  // 清旧预览；URL 字段由开启者（新建/剪贴板）各自设

        ColumnLayout {
            implicitWidth: 520
            spacing: 10
            TextArea {
                id: addUrlsField
                Layout.fillWidth: true
                Layout.preferredHeight: 88
                placeholderText: "每行一个下载链接"
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "下载目录"; typography: Typography.Body }
                Item { Layout.fillWidth: true }
                TextField { id: addPathField; Layout.preferredWidth: 240; placeholderText: "默认（按配置/分类）" }
                Button { text: "选择"; onClicked: addFolderDialog.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "线程数"; typography: Typography.Body }
                Item { Layout.fillWidth: true }
                Slider { id: addThreadsSlider; Layout.preferredWidth: 180; from: 1; to: 32; stepSize: 1; value: backend.config.preBlockNum }
                Text { text: Math.round(addThreadsSlider.value); typography: Typography.Body; Layout.preferredWidth: 22 }
            }
            Button {
                Layout.fillWidth: true
                text: "解析"
                onClicked: {
                    const urls = addUrlsField.text.split("\n").map(s => s.trim()).filter(s => s !== "")
                    backend.discardPreviews()  // 重新解析前清旧预览
                    const opts = {preBlockNum: Math.round(addThreadsSlider.value)}
                    if (addPathField.text.trim() !== "") opts.path = addPathField.text.trim()
                    backend.parsePreview(urls, opts)
                }
            }
            ListView {
                Layout.fillWidth: true
                implicitHeight: 200
                clip: true
                model: backend.previewList
                delegate: RowLayout {
                    width: ListView.view.width
                    spacing: 8
                    Image {
                        Layout.preferredWidth: 24; Layout.preferredHeight: 24
                        source: "image://fileicon/" + encodeURIComponent(model.title)
                        sourceSize.width: 24; sourceSize.height: 24
                        fillMode: Image.PreserveAspectFit
                    }
                    Text { text: model.title; Layout.fillWidth: true; elide: Text.ElideRight }
                    // pack 解析出的元信息（M3U8「HLS·点播」等），复用任务卡的 chips
                    Row {
                        spacing: 6
                        Repeater {
                            model: chips
                            delegate: Text { text: modelData; opacity: 0.55; typography: Typography.Caption }
                        }
                    }
                    Text { text: model.sizeText; opacity: 0.6 }
                    // per-URL 编辑：复用数据驱动编辑框（链接/标头/代理/目录），提交前改这一条
                    ToolButton {
                        icon.name: "ic_fluent_edit_20_regular"; size: 15
                        onClicked: backend.requestEditSchema(model.taskId)
                    }
                }
            }
        }

        FolderDialog {
            id: addFolderDialog
            // 原生目录对话框返回 file:/// URL，剥成本地路径喂给路径框
            onAccepted: addPathField.text = String(selectedFolder).replace("file:///", "")
        }

        onAccepted: backend.commit()
        onRejected: backend.discardPreviews()
        Component.onCompleted: {
            const ok = standardButton(Dialog.Ok)
            if (ok) ok.text = "下载"
            const cancel = standardButton(Dialog.Cancel)
            if (cancel) cancel.text = "取消"
        }
    }

    Dialog {
        id: deleteDialog
        title: "删除任务"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        Text { text: "确定删除这个任务吗？" }
        onAccepted: backend.remove(taskPage.pendingDelete)
        Component.onCompleted: {
            const ok = standardButton(Dialog.Ok)
            if (ok) ok.text = "删除"
            const cancel = standardButton(Dialog.Cancel)
            if (cancel) cancel.text = "取消"
        }
    }

    // 数据驱动编辑框：引擎吐该任务的 schema → CardSchemaView 渲染 → 确定收 payload 回 editTask 重解析
    Dialog {
        id: editDialog
        title: "编辑任务"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        property string editTaskId: ""
        CardSchemaView { id: editSchemaView; implicitWidth: 480 }
        onAccepted: backend.editTask(editDialog.editTaskId, editSchemaView.payload())
        Component.onCompleted: {
            const ok = standardButton(Dialog.Ok)
            if (ok) ok.text = "确定"
            const cancel = standardButton(Dialog.Cancel)
            if (cancel) cancel.text = "取消"
        }
    }

    Connections {
        target: backend
        function onEditSchemaReady(taskId, schema) {
            editDialog.editTaskId = taskId
            editSchemaView.schema = schema
            editDialog.open()
        }
    }

    Dialog {
        id: hashDialog
        title: "文件校验 (SHA-256)"
        modal: true
        standardButtons: Dialog.Ok
        Text {
            width: 440  // Text.implicitWidth 只读，定宽换行用 width
            wrapMode: Text.WrapAnywhere
            text: backend.hashText !== "" ? backend.hashText : "计算中…"
        }
        Component.onCompleted: {
            const ok = standardButton(Dialog.Ok)
            if (ok) ok.text = "关闭"
        }
    }

    Connections {
        target: backend
        function onFilesRequested() { fileDialog.open() }
        function onClipboardUrlsDetected(urls) {
            // 剪贴板抓到链接：预填进新建对话框（多条逐行），用户点解析→确认，不静默添加
            addUrlsField.text = urls.join("\n")
            addPathField.text = ""
            addTaskDialog.open()
        }
    }

    Dialog {
        id: fileDialog
        title: "选择下载文件"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: backend.confirmFiles()

        ListView {
            implicitWidth: 460
            implicitHeight: 320
            clip: true
            model: backend.filesModel
            delegate: RowLayout {
                width: ListView.view.width
                spacing: 10
                CheckBox { checked: model.selected; onClicked: backend.filesModel.toggle(index) }
                Text { text: model.path; Layout.fillWidth: true; elide: Text.ElideMiddle }
                Text { text: model.sizeText; opacity: 0.7 }
            }
        }

        Component.onCompleted: {
            const ok = standardButton(Dialog.Ok)
            if (ok) ok.text = "确定"
            const cancel = standardButton(Dialog.Cancel)
            if (cancel) cancel.text = "取消"
        }
    }

    function addCurrent() {
        if (urlInput.text.trim() === "")
            return
        backend.addTask(urlInput.text.trim())
        urlInput.text = ""
    }
}
