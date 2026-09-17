package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.util.formatSizeProgress
import com.xychr.ghostdownloader.ui.util.formatSpeed
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import com.xychr.ghostdownloader.ui.theme.CardShape
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandHorizontally
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkHorizontally
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
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
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import kotlinx.serialization.json.JsonObject

@OptIn(ExperimentalFoundationApi::class, ExperimentalLayoutApi::class)
@Composable
fun TaskCard(
    task: TaskUiState,
    isSelecting: Boolean,
    isSelected: Boolean,
    onClick: () -> Unit,
    onLongClick: () -> Unit,
    onAction: (TaskAction) -> Unit,
    modifier: Modifier = Modifier,
    category: Category? = null,
    isCategoryEnabled: Boolean = false,
    packExtra: (@Composable (JsonObject) -> Unit)? = null,
) {
    val actions = buildTaskActions(task, isCategoryEnabled)
    Card(
        shape = CardShape,
        colors = CardDefaults.cardColors(
            containerColor = if (isSelected) MaterialTheme.colorScheme.secondaryContainer
            else MaterialTheme.colorScheme.surfaceContainerLow,
        ),
        modifier = modifier
            .fillMaxWidth()
            .sharedContainer("task-${task.id}")
            .semantics { if (isSelecting) selected = isSelected }
            .combinedClickable(
                onClick = onClick,
                onLongClick = onLongClick,
                onClickLabel = stringResource(R.string.task_details),
                onLongClickLabel = stringResource(R.string.task_select),
            ),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                AnimatedVisibility(
                    visible = isSelecting,
                    enter = fadeIn(MaterialTheme.motionScheme.fastEffectsSpec<Float>()) +
                        expandHorizontally(MaterialTheme.motionScheme.fastSpatialSpec<IntSize>()),
                    exit = fadeOut(MaterialTheme.motionScheme.fastEffectsSpec<Float>()) +
                        shrinkHorizontally(MaterialTheme.motionScheme.fastSpatialSpec<IntSize>()),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        SelectionMark(isSelected)
                        Spacer(Modifier.width(12.dp))
                    }
                }
                Column(Modifier.weight(1f)) {
                    Text(
                        text = task.name,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    TaskStatusLine(
                        status = task.status,
                        error = task.error,
                        statusText = task.statusText,
                        completedAt = task.completedAt,
                        speed = task.speed,
                        progress = task.progress,
                    )
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
            }

            if (!isSelecting && task.packFields.isNotEmpty() && packExtra != null) {
                Spacer(Modifier.height(4.dp))
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) { packExtra(task.packFields) }
            }

            if (!isSelecting) TaskActionRow(actions, onAction)
        }
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun TaskActionRow(actions: TaskActions, onAction: (TaskAction) -> Unit) {
    val main = actions.main
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        FilledTonalButton(
            onClick = { onAction(main.action) },
            enabled = main.isEnabled,
            contentPadding = ButtonDefaults.ButtonWithIconContentPadding,
        ) {
            Icon(painterResource(main.icon), null, Modifier.size(ButtonDefaults.IconSize))
            Spacer(Modifier.width(ButtonDefaults.IconSpacing))
            Text(stringResource(main.label), maxLines = 1)
        }
        Spacer(Modifier.weight(1f))
        for (spec in actions.inline) {
            TaskIconButton(spec.icon, stringResource(spec.label), spec.isEnabled) { onAction(spec.action) }
        }
        TaskCardMenu(actions.menu, onAction)
    }
}

@Composable
private fun SelectionMark(isSelected: Boolean) {
    val shape = CircleShape
    Box(
        modifier = Modifier
            .size(24.dp)
            .clip(shape)
            .then(
                if (isSelected) Modifier.background(MaterialTheme.colorScheme.primary)
                else Modifier.border(2.dp, MaterialTheme.colorScheme.onSurfaceVariant, shape),
            ),
        contentAlignment = Alignment.Center,
    ) {
        if (isSelected) Icon(
            painterResource(R.drawable.ic_check), null,
            Modifier.size(16.dp),
            tint = MaterialTheme.colorScheme.onPrimary,
        )
    }
}

@Composable
private fun FileCountChip(fileCount: Int) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            painterResource(R.drawable.ic_folder),
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(14.dp),
        )
        Spacer(Modifier.width(4.dp))
        Caption(stringResource(R.string.task_file_count, fileCount))
    }
}

@Composable
private fun TaskCardMenu(menu: List<TaskActionSpec>, onAction: (TaskAction) -> Unit) {
    var isOpen by remember { mutableStateOf(false) }
    Box {
        TaskIconButton(R.drawable.ic_more_vert, stringResource(R.string.action_more)) { isOpen = true }
        DropdownMenu(expanded = isOpen, onDismissRequest = { isOpen = false }) {
            for (spec in menu) {
                if (spec.action == TaskAction.DELETE) HorizontalDivider()
                TaskMenuItem(stringResource(spec.label), spec.icon, spec.isEnabled) {
                    isOpen = false
                    onAction(spec.action)
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
