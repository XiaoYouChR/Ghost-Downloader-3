package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.util.formatSizeProgress
import com.xychr.ghostdownloader.ui.util.formatSpeed
import com.xychr.ghostdownloader.ui.util.formatTimestamp
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes

import androidx.compose.animation.Crossfade
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import kotlinx.serialization.json.JsonObject

enum class TaskAction { RUN, DETAILS, FILES, EDIT, CATEGORY, COPY_URL, MOVE_TO_FRONT, REDOWNLOAD, DELETE, OPEN_FILE }

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
                LeadingMark(isSelecting, isSelected)
                Spacer(Modifier.width(12.dp))
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
                if (!isSelecting) Icon(
                    painterResource(R.drawable.ic_chevron_right), null,
                    Modifier.size(20.dp).graphicsLayer { rotationZ = if (isExpanded) 270f else 90f },
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            AnimatedVisibility(isExpanded && !isSelecting) {
                Column(Modifier.padding(top = 12.dp).fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .background(MaterialTheme.colorScheme.surfaceContainerHigh)
                    .padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    packExtra?.invoke(task.packFields)
                    if (task.fileCount > 1) Caption(stringResource(
                        R.string.task_selected_files, task.selectedFileCount, task.fileCount))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { onAction(TaskAction.DETAILS) }) {
                            Text(stringResource(R.string.task_details))
                        }
                        Spacer(Modifier.weight(1f))
                        TaskMenu(task, onAction, isCategoryEnabled)
                    }
                    if (task.fileCount > 1) TextButton(onClick = { onAction(TaskAction.FILES) }) {
                        Text(stringResource(R.string.task_choose_files))
                    }
                    if (task.canEdit && !task.isFinished) TextButton(onClick = { onAction(TaskAction.EDIT) }) {
                        Text(stringResource(R.string.task_edit_options))
                    }
                }
            }
        }
    }
}

@Composable
private fun LeadingMark(isSelecting: Boolean, isSelected: Boolean) {
    Crossfade(targetState = isSelecting to isSelected, label = "leading-mark") { (selecting, selected) ->
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(
                    when {
                        selected -> MaterialTheme.colorScheme.primary
                        selecting -> Color.Transparent
                        else -> MaterialTheme.colorScheme.secondaryContainer
                    }
                )
                .then(
                    if (selecting && !selected) {
                        Modifier.border(2.dp, MaterialTheme.colorScheme.outline, CircleShape)
                    } else {
                        Modifier
                    }
                ),
            contentAlignment = Alignment.Center,
        ) {
            when {
                selected -> Icon(
                    painter = painterResource(R.drawable.ic_check),
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimary,
                    modifier = Modifier.size(20.dp),
                )

                selecting -> Unit

                else -> Icon(
                    painter = painterResource(R.drawable.ic_file),
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSecondaryContainer,
                    modifier = Modifier.size(20.dp),
                )
            }
        }
    }
}

@Composable
private fun StatusLine(task: TaskUiState, isExpanded: Boolean) {
    val text = when {
        task.status == TaskStatus.FAILED -> task.error?.let { engineText(it.message, it.params) }
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

@Composable
private fun TaskMenu(task: TaskUiState, onAction: (TaskAction) -> Unit, isCategoryEnabled: Boolean) {
    var isOpen by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { isOpen = true }) {
            Icon(painterResource(R.drawable.ic_more_vert), stringResource(R.string.action_more))
        }
        DropdownMenu(expanded = isOpen, onDismissRequest = { isOpen = false }) {
            if (isCategoryEnabled) DropdownMenuItem(
                text = { Text(stringResource(R.string.task_change_category)) },
                onClick = { isOpen = false; onAction(TaskAction.CATEGORY) },
            )
            val actions = listOf(
                TaskAction.COPY_URL to R.string.task_detail_copy_url,
                TaskAction.MOVE_TO_FRONT to R.string.task_detail_move_to_front,
                TaskAction.REDOWNLOAD to R.string.task_detail_redownload,
                TaskAction.DELETE to R.string.action_delete,
            )
            actions.forEach { (action, label) ->
                if (action != TaskAction.MOVE_TO_FRONT || task.status == TaskStatus.WAITING || task.status == TaskStatus.PAUSED) {
                    DropdownMenuItem(text = { Text(stringResource(label)) }, onClick = {
                        isOpen = false
                        onAction(action)
                    })
                }
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
