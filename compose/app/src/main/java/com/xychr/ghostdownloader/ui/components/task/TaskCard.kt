package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.util.formatSizeProgress
import com.xychr.ghostdownloader.ui.util.formatSpeed
import com.xychr.ghostdownloader.ui.util.formatTimestamp
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandHorizontally
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkHorizontally
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import kotlinx.serialization.json.JsonObject

enum class TaskAction {
    RUN, DETAILS, FILES, EDIT, CATEGORY, COPY_URL, MOVE_TO_FRONT, REDOWNLOAD, DELETE,
    OPEN_FILE, OPEN_FOLDER,
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun TaskCard(
    task: TaskUiState,
    isSelecting: Boolean,
    isSelected: Boolean,
    isExpanded: Boolean,
    onClick: () -> Unit,
    onLongClick: () -> Unit,
    onAction: (TaskAction) -> Unit,
    modifier: Modifier = Modifier,
    category: Category? = null,
    isCategoryEnabled: Boolean = false,
    packExtra: (@Composable (JsonObject) -> Unit)? = null,
) {
    val expandedText = stringResource(if (isExpanded) R.string.task_expanded else R.string.task_collapsed)
    Card(
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (isSelected) MaterialTheme.colorScheme.secondaryContainer
            else MaterialTheme.colorScheme.surfaceContainerLow,
        ),
        modifier = modifier
            .fillMaxWidth()
            .sharedContainer("task-${task.id}")
            .semantics {
                if (isSelecting) selected = isSelected else stateDescription = expandedText
            }
            .combinedClickable(onClick = onClick, onLongClick = onLongClick,
                onLongClickLabel = stringResource(R.string.task_select)),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                // 常态不占位——勾选框只在选择模式滑入，名字区拿回这段宽度
                AnimatedVisibility(
                    visible = isSelecting,
                    enter = fadeIn() + expandHorizontally(),
                    exit = fadeOut() + shrinkHorizontally(),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = isSelected, onCheckedChange = null)
                        Spacer(Modifier.width(8.dp))
                    }
                }
                Column(Modifier.weight(1f)) {
                    Text(
                        text = task.name,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = if (isExpanded) Int.MAX_VALUE else 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    StatusLine(task, isExpanded)
                }
                if (!isSelecting) RunButton(task) {
                    onAction(if (task.isFinished) TaskAction.OPEN_FILE else TaskAction.RUN)
                }
            }

            if (task.status != TaskStatus.COMPLETED && task.status != TaskStatus.FAILED && task.progressMode != "hidden") {
                Spacer(Modifier.height(8.dp))
                TaskProgress(task.status, task.progress,
                    task.progressMode == "indeterminate" || task.fileSize <= 0 && task.progress <= 0)
            }
            Spacer(Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Caption(formatSizeProgress(task.received, task.fileSize))
                    if (task.secondarySpeed > 0) Caption("↑ ${formatSpeed(task.secondarySpeed)}")
                }
                if (isCategoryEnabled && category != null) Row(
                    Modifier.weight(0.7f).padding(horizontal = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Icon(painterResource(categoryIconRes(category.icon)), null, Modifier.size(14.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(category.name, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (task.fileCount > 1) FileCountChip(task.fileCount)
                if (!isSelecting) ExpandChevron(isExpanded)
            }

            AnimatedVisibility(isExpanded && !isSelecting) {
                Column(
                    modifier = Modifier.padding(top = 12.dp).fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(MaterialTheme.colorScheme.surfaceContainerHigh)
                        .padding(horizontal = 4.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Column(
                        modifier = Modifier.padding(horizontal = 8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        packExtra?.invoke(task.packFields)
                        if (task.fileCount > 1) Caption(stringResource(
                            R.string.task_selected_files, task.selectedFileCount, task.fileCount))
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TaskIconButton(R.drawable.ic_folder_open,
                            stringResource(R.string.task_detail_open_folder)) {
                            onAction(TaskAction.OPEN_FOLDER)
                        }
                        TaskIconButton(R.drawable.ic_delete, stringResource(R.string.action_delete)) {
                            onAction(TaskAction.DELETE)
                        }
                        Spacer(Modifier.weight(1f))
                        TaskCardMenu(task, onAction, isCategoryEnabled)
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusLine(task: TaskUiState, isExpanded: Boolean) {
    val text = when {
        task.status == TaskStatus.FAILED -> task.error?.let { engineText(it) }
            ?: stringResource(R.string.task_status_failed)
        task.status == TaskStatus.COMPLETED -> stringResource(R.string.task_status_completed) +
            formatTimestamp(task.completedAt).takeIf { it.isNotEmpty() }?.let { " · $it" }.orEmpty()
        task.status == TaskStatus.WAITING -> stringResource(R.string.task_status_waiting)
        task.statusText.isNotEmpty() -> engineText(task.statusText, emptyMap())
        task.status == TaskStatus.PAUSED -> stringResource(R.string.task_status_paused)
        task.status == TaskStatus.RUNNING ->
            formatSpeed(task.speed).ifEmpty { "0 B/s" } +
                if (task.fileSize > 0 || task.progress > 0) " · ${task.progress.toInt()}%" else ""
        else -> ""
    }

    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = if (task.status == TaskStatus.FAILED) MaterialTheme.colorScheme.error
        else MaterialTheme.colorScheme.onSurfaceVariant,
        maxLines = if (isExpanded) Int.MAX_VALUE else 2,
        overflow = TextOverflow.Ellipsis,
    )
}

@Composable
private fun RunButton(task: TaskUiState, onClick: () -> Unit) {
    val isRunning = task.status == TaskStatus.RUNNING
    IconButton(onClick = onClick, enabled = !isRunning || task.canStop || task.canPause) {
        Icon(
            painter = painterResource(when {
                task.isFinished -> R.drawable.ic_open_in_new
                task.canStop -> R.drawable.ic_check
                isRunning -> R.drawable.ic_pause
                task.status == TaskStatus.FAILED -> R.drawable.ic_refresh
                else -> R.drawable.ic_play
            }),
            contentDescription = stringResource(when {
                task.isFinished -> if (task.hasOutputFile) R.string.task_detail_open_file else R.string.task_details
                task.canStop -> R.string.task_stop_save
                isRunning -> R.string.action_pause
                task.status == TaskStatus.FAILED -> R.string.task_retry
                else -> R.string.action_resume
            }),
        )
    }
}

@Composable
private fun FileCountChip(fileCount: Int) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            painter = painterResource(R.drawable.ic_folder),
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(14.dp),
        )
        Spacer(Modifier.width(4.dp))
        Caption(stringResource(R.string.task_file_count, fileCount))
    }
}

/** 低频入口：跳转类操作和不常用命令。高频的开始／暂停／打开／删除在卡片上直接点。 */
@Composable
private fun TaskCardMenu(task: TaskUiState, onAction: (TaskAction) -> Unit, isCategoryEnabled: Boolean) {
    var isOpen by remember { mutableStateOf(false) }
    Box {
        TaskIconButton(R.drawable.ic_more_vert, stringResource(R.string.action_more)) { isOpen = true }
        DropdownMenu(expanded = isOpen, onDismissRequest = { isOpen = false }) {
            TaskMenuItem(stringResource(R.string.task_details), R.drawable.ic_info) {
                isOpen = false; onAction(TaskAction.DETAILS)
            }
            if (task.fileCount > 1) TaskMenuItem(
                stringResource(R.string.task_choose_files), R.drawable.ic_file,
            ) { isOpen = false; onAction(TaskAction.FILES) }
            if (task.canEdit && !task.isFinished) TaskMenuItem(
                stringResource(R.string.task_edit_options), R.drawable.ic_edit,
            ) { isOpen = false; onAction(TaskAction.EDIT) }
            HorizontalDivider()
            if (isCategoryEnabled) TaskMenuItem(
                stringResource(R.string.task_change_category), R.drawable.ic_folder,
            ) { isOpen = false; onAction(TaskAction.CATEGORY) }
            TaskMenuItem(stringResource(R.string.task_detail_copy_url), R.drawable.ic_copy) {
                isOpen = false; onAction(TaskAction.COPY_URL)
            }
            if (task.status == TaskStatus.WAITING || task.status == TaskStatus.PAUSED) TaskMenuItem(
                stringResource(R.string.task_detail_move_to_front), R.drawable.ic_arrow_upward,
            ) { isOpen = false; onAction(TaskAction.MOVE_TO_FRONT) }
            TaskMenuItem(stringResource(R.string.task_detail_redownload), R.drawable.ic_refresh) {
                isOpen = false; onAction(TaskAction.REDOWNLOAD)
            }
        }
    }
}

@Composable
private fun Caption(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}
