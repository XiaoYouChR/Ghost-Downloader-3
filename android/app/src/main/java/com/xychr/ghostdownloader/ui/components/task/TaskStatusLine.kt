package com.xychr.ghostdownloader.ui.components.task

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.model.TaskStatus
import com.xychr.ghostdownloader.ui.util.formatSpeed
import com.xychr.ghostdownloader.ui.util.formatTimestamp

@Composable
fun TaskStatusLine(
    status: String,
    error: TaskError?,
    statusText: String,
    completedAt: Long,
    speed: Long,
    progress: Double,
    isFileMissing: Boolean,
    style: TextStyle = MaterialTheme.typography.bodyMedium,
    maxLines: Int = 2,
) {
    val parts = when {
        status == TaskStatus.FAILED ->
            listOf(error?.let { engineText(it) } ?: stringResource(R.string.task_status_failed))

        isFileMissing -> listOf(stringResource(R.string.task_status_file_missing))

        status == TaskStatus.COMPLETED && statusText.isNotEmpty() -> listOf(engineText(statusText))

        status == TaskStatus.COMPLETED ->
            listOf(stringResource(R.string.task_status_completed), formatTimestamp(completedAt))
                .filter(String::isNotEmpty)

        status == TaskStatus.WAITING -> listOf(stringResource(R.string.task_status_waiting))

        statusText.isNotEmpty() -> listOf(engineText(statusText))

        status == TaskStatus.PAUSED -> listOf(stringResource(R.string.task_status_paused))

        status == TaskStatus.RUNNING -> buildList {
            add(stringResource(R.string.task_status_running))
            add(formatSpeed(speed).ifEmpty { "0 B/s" })
            if (progress > 0) add("${progress.toInt()}%")
        }

        else -> listOf("")
    }
    val color = when {
        status == TaskStatus.FAILED -> MaterialTheme.colorScheme.error
        isFileMissing -> MaterialTheme.colorScheme.tertiary
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Text(
            text = parts.first(),
            style = style,
            color = color,
            maxLines = maxLines,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        for (part in parts.drop(1)) {
            Text(
                text = part,
                style = style,
                color = color,
                maxLines = 1,
                modifier = Modifier.padding(start = 16.dp),
            )
        }
    }
}
