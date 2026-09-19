package com.xychr.ghostdownloader.ui.components.task

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.TaskActionSource
import com.xychr.ghostdownloader.model.TaskStatus
import com.xychr.ghostdownloader.model.TaskUiState
import com.xychr.ghostdownloader.model.hasSingleFile

enum class TaskAction {
    STOP, PAUSE, RESUME,
    OPEN_FILE, OPEN_FOLDER, SHARE_FILE,
    FILES, EDIT, CATEGORY, COPY_URL, SHARE_URL, MOVE_TO_FRONT, REDOWNLOAD, VERIFY_HASH, DELETE,
}

data class TaskActionSpec(
    val action: TaskAction,
    @StringRes val label: Int,
    @DrawableRes val icon: Int,
    val isEnabled: Boolean = true,
)

data class TaskActions(
    val main: TaskActionSpec,
    val inline: List<TaskActionSpec>,
    val menu: List<TaskActionSpec>,
)

fun buildTaskMainAction(source: TaskActionSource): TaskActionSpec = when {
    source.canStop -> TaskActionSpec(TaskAction.STOP, R.string.task_stop_save, R.drawable.ic_check)
    source.status == TaskStatus.RUNNING -> TaskActionSpec(
        TaskAction.PAUSE, R.string.action_pause, R.drawable.ic_pause, isEnabled = source.canPause,
    )
    source.status == TaskStatus.FAILED ->
        TaskActionSpec(TaskAction.RESUME, R.string.task_retry, R.drawable.ic_refresh)
    source.status == TaskStatus.COMPLETED && source.hasSingleFile && source.isFileMissing ->
        redownloadSpec
    source.status == TaskStatus.COMPLETED && source.hasSingleFile ->
        TaskActionSpec(TaskAction.OPEN_FILE, R.string.task_detail_open_file, R.drawable.ic_open_in_new)
    source.status == TaskStatus.COMPLETED -> openFolderSpec
    else -> TaskActionSpec(TaskAction.RESUME, R.string.action_resume, R.drawable.ic_play)
}

internal fun buildVerifyHashAction(source: TaskActionSource): TaskActionSpec? =
    if (source.status != TaskStatus.COMPLETED || !source.hasSingleFile) null
    else TaskActionSpec(TaskAction.VERIFY_HASH, R.string.task_hash_title, R.drawable.ic_fingerprint,
        isEnabled = !source.isFileMissing)

@StringRes
fun toFileSelectLabel(kind: String): Int = when (kind) {
    "season" -> R.string.task_select_season
    "pages" -> R.string.task_select_pages
    else -> R.string.task_choose_files
}

fun buildTaskActions(task: TaskUiState, isCategoryEnabled: Boolean): TaskActions {
    val main = buildTaskMainAction(task)

    val inline = when {
        task.status == TaskStatus.COMPLETED -> buildList {
            if (main.action != TaskAction.OPEN_FOLDER) add(openFolderSpec)
            if (main.action == TaskAction.OPEN_FILE) add(shareFileSpec)
            if (main.action != TaskAction.REDOWNLOAD) add(redownloadSpec)
        }
        task.status == TaskStatus.FAILED -> listOf(redownloadSpec)
        task.status == TaskStatus.WAITING || task.status == TaskStatus.PAUSED -> listOf(moveToFrontSpec)
        else -> emptyList()
    }

    val menu = buildList {
        if (task.fileCount > 1 && task.canSelectFiles) {
            add(TaskActionSpec(TaskAction.FILES, toFileSelectLabel(task.fileSelectKind), R.drawable.ic_file))
        }
        if (task.canEdit && task.status != TaskStatus.COMPLETED) {
            add(TaskActionSpec(TaskAction.EDIT, R.string.task_edit_options, R.drawable.ic_edit))
        }
        if (isCategoryEnabled) {
            add(TaskActionSpec(TaskAction.CATEGORY, R.string.task_change_category, R.drawable.ic_folder))
        }
        buildVerifyHashAction(task)?.let { add(it) }
        add(copyUrlSpec)
        add(shareUrlSpec)
        if (main.action != TaskAction.REDOWNLOAD && redownloadSpec !in inline) add(redownloadSpec)
        add(deleteSpec)
    }

    return TaskActions(main, inline, menu)
}

private val openFolderSpec =
    TaskActionSpec(TaskAction.OPEN_FOLDER, R.string.task_detail_open_folder, R.drawable.ic_folder_open)

internal val shareFileSpec =
    TaskActionSpec(TaskAction.SHARE_FILE, R.string.task_share_file, R.drawable.ic_share)

internal val copyUrlSpec =
    TaskActionSpec(TaskAction.COPY_URL, R.string.task_detail_copy_url, R.drawable.ic_copy)

internal val shareUrlSpec =
    TaskActionSpec(TaskAction.SHARE_URL, R.string.task_share_url, R.drawable.ic_share)

internal val moveToFrontSpec =
    TaskActionSpec(TaskAction.MOVE_TO_FRONT, R.string.task_detail_move_to_front, R.drawable.ic_arrow_upward)

internal val redownloadSpec =
    TaskActionSpec(TaskAction.REDOWNLOAD, R.string.task_detail_redownload, R.drawable.ic_restore)

internal val deleteSpec =
    TaskActionSpec(TaskAction.DELETE, R.string.action_delete, R.drawable.ic_delete)
