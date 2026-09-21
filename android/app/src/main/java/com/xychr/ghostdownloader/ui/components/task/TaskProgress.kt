package com.xychr.ghostdownloader.ui.components.task

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.LinearWavyProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.model.TaskStatus

@Composable
fun TaskProgress(status: String, progress: Double, isIndeterminate: Boolean, modifier: Modifier = Modifier) {
    val color by animateColorAsState(targetValue = toProgressColor(status), label = "bar-color")
    val shownProgress by animateFloatAsState(
        targetValue = (progress / 100.0).toFloat().coerceIn(0f, 1f),
        animationSpec = spring(dampingRatio = Spring.DampingRatioNoBouncy),
        label = "bar-progress",
    )
    val amplitude by animateFloatAsState(
        if (status == TaskStatus.RUNNING) 1f else 0f, tween(220), label = "wave-amplitude")
    val barModifier = modifier.fillMaxWidth().height(10.dp)
    val trackColor = color.copy(alpha = 0.2f)

    if (status == TaskStatus.RUNNING && isIndeterminate) {
        LinearWavyProgressIndicator(modifier = barModifier, color = color, trackColor = trackColor,
            amplitude = amplitude, waveSpeed = 40.dp)
    } else {
        LinearWavyProgressIndicator(
            progress = { shownProgress },
            modifier = barModifier,
            color = color,
            trackColor = trackColor,
            amplitude = { amplitude }, waveSpeed = if (status == TaskStatus.RUNNING) 40.dp else 0.dp,
            stopSize = 0.dp,
        )
    }
}

@Composable
private fun toProgressColor(status: String): Color = when (status) {
    TaskStatus.RUNNING -> MaterialTheme.colorScheme.primary
    TaskStatus.PAUSED -> MaterialTheme.colorScheme.tertiary
    TaskStatus.FAILED -> MaterialTheme.colorScheme.error
    TaskStatus.COMPLETED -> MaterialTheme.colorScheme.surfaceVariant
    else -> MaterialTheme.colorScheme.outline
}

