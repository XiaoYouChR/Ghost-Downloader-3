package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.model.CategoryState
import com.xychr.ghostdownloader.ui.components.category.CategoryFilterRow
import com.xychr.ghostdownloader.ui.util.formatSize
import com.xychr.ghostdownloader.ui.util.formatSpeed

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandHorizontally
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkHorizontally
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R

/**
 * 顶栏与列表之间那一条：速度读数固定在行首，只有分类 chip 横滑——状态读数滑出视口就失去意义。
 *
 * 这一行永远非空：有速度就显示读数，有分类就显示 chip，两者都没有时 note 兜底。
 */
@Composable
fun TaskListHeader(
    summary: TaskSummary,
    readState: TaskReadState,
    categories: CategoryState,
    categoryFilter: String?,
    onCategorySelect: (String?) -> Unit,
    modifier: Modifier = Modifier,
) {
    val hasSpeed = readState == TaskReadState.READY && summary.running + summary.waiting > 0
    val note = when (readState) {
        TaskReadState.LOADING -> stringResource(R.string.task_bar_loading)
        TaskReadState.UNAVAILABLE -> stringResource(R.string.task_bar_unavailable)
        // 有 chip 或速度读数时不再占宽度说「无活动任务」——那时它只是噪声
        TaskReadState.READY -> stringResource(R.string.task_bar_idle)
            .takeIf { !categories.isEnabled && !hasSpeed }
    }

    Row(
        modifier = modifier.fillMaxWidth().heightIn(min = 48.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AnimatedVisibility(
            visible = hasSpeed,
            enter = fadeIn() + expandHorizontally(),
            exit = fadeOut() + shrinkHorizontally(),
        ) { TaskSpeedBadge(summary) }
        if (!hasSpeed) note?.let {
            Text(
                text = it,
                modifier = Modifier.padding(horizontal = 16.dp),
                style = MaterialTheme.typography.labelLarge,
                color = if (readState == TaskReadState.UNAVAILABLE) MaterialTheme.colorScheme.error
                else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (categories.isEnabled) CategoryFilterRow(
            categoryFilter = categoryFilter,
            categories = categories.categories,
            onSelect = onCategorySelect,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun TaskSpeedBadge(summary: TaskSummary) {
    val label = stringResource(R.string.task_bar_speed, formatSize(summary.speed)) + " · " +
        stringResource(R.string.task_bar_counts, summary.running, summary.waiting)
    Row(
        modifier = Modifier
            .padding(start = 16.dp, end = 4.dp)
            .semantics(mergeDescendants = true) { contentDescription = label },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            painter = painterResource(R.drawable.ic_download),
            contentDescription = null,
            modifier = Modifier.size(18.dp),
            tint = MaterialTheme.colorScheme.primary,
        )
        Spacer(Modifier.width(4.dp))
        Text(
            text = formatSpeed(summary.speed).ifEmpty { "0 KB/s" },
            style = MaterialTheme.typography.labelLarge.copy(fontFeatureSettings = "tnum"),
            color = MaterialTheme.colorScheme.primary,
            maxLines = 1,
        )
    }
}
