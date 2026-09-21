package com.xychr.ghostdownloader.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.util.formatDuration
import com.xychr.ghostdownloader.ui.util.parseDuration

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FileTrimSheet(
    name: String,
    startTime: Int,
    endTime: Int,
    onApply: (Int, Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var start by remember { mutableStateOf(if (startTime > 0) formatDuration(startTime.toLong()) else "") }
    var end by remember { mutableStateOf(if (endTime > 0) formatDuration(endTime.toLong()) else "") }

    val parsedStart = parseDuration(start)
    val parsedEnd = parseDuration(end)
    val isCleared = start.isBlank() && end.isBlank()
    val isValid = isCleared || (parsedStart != null && parsedEnd != null && parsedStart < parsedEnd)

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 24.dp)) {
            Text(stringResource(R.string.task_trim_title), style = MaterialTheme.typography.titleLarge)
            Text(
                text = name,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
            Spacer(Modifier.height(16.dp))
            Row {
                OutlinedTextField(
                    value = start,
                    onValueChange = { start = it },
                    label = { Text(stringResource(R.string.draft_trim_start)) },
                    singleLine = true,
                    isError = start.isNotBlank() && parsedStart == null,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(12.dp))
                OutlinedTextField(
                    value = end,
                    onValueChange = { end = it },
                    label = { Text(stringResource(R.string.draft_trim_end)) },
                    singleLine = true,
                    isError = end.isNotBlank() && parsedEnd == null,
                    modifier = Modifier.weight(1f),
                )
            }
            Text(
                text = stringResource(R.string.task_trim_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 8.dp),
            )
            Spacer(Modifier.height(16.dp))
            Row(Modifier.fillMaxWidth()) {
                TextButton(onClick = { start = ""; end = "" }) {
                    Text(stringResource(R.string.task_trim_clear))
                }
                Spacer(Modifier.weight(1f))
                Button(
                    onClick = { onApply(parsedStart ?: 0, parsedEnd ?: 0) },
                    enabled = isValid,
                ) {
                    Text(stringResource(R.string.task_apply))
                }
            }
        }
    }
}
