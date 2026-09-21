package com.xychr.ghostdownloader.ui.components

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.TaskError

@Composable
fun ErrorText(error: TaskError?, modifier: Modifier = Modifier) {
    error ?: return
    Text(engineText(error), modifier, color = MaterialTheme.colorScheme.error)
}
