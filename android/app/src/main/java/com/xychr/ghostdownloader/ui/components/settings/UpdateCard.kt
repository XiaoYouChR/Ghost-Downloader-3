package com.xychr.ghostdownloader.ui.components.settings

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearWavyProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.pages.settings.UpdateAvailable
import com.xychr.ghostdownloader.ui.pages.settings.UpdateDownloadState

@Composable
fun UpdateCard(
    available: UpdateAvailable?,
    dlState: UpdateDownloadState,
    onViewNotes: () -> Unit,
    onDownload: () -> Unit,
    onInstall: () -> Boolean,
    onIgnore: () -> Unit,
    onFixPermission: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var installFailed by remember { mutableStateOf(false) }
    val isError = dlState.state == "failed" || installFailed
    val containerColor = if (isError) MaterialTheme.colorScheme.errorContainer
        else MaterialTheme.colorScheme.primaryContainer
    val contentColor = if (isError) MaterialTheme.colorScheme.onErrorContainer
        else MaterialTheme.colorScheme.onPrimaryContainer

    Card(
        colors = CardDefaults.cardColors(containerColor = containerColor),
        shape = MaterialTheme.shapes.large,
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            val version = available?.version ?: dlState.filePath.substringAfterLast('/')
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(version, style = MaterialTheme.typography.titleLarge, color = contentColor)
                available?.publishedAt?.take(10)?.takeIf(String::isNotEmpty)?.let {
                    Spacer(Modifier.width(8.dp))
                    Text(it, style = MaterialTheme.typography.bodyMedium,
                        color = contentColor.copy(alpha = 0.7f))
                }
            }
            if (available?.prerelease == true) {
                Text(stringResource(R.string.settings_update_prerelease),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 4.dp))
            }

            Spacer(Modifier.height(12.dp))

            when (dlState.state) {
                "downloading" -> DownloadingContent(dlState.progress, contentColor)
                "ready" -> ReadyContent(
                    onInstall = { installFailed = !onInstall() },
                    installFailed = installFailed,
                    onFixPermission = onFixPermission,
                )
                "failed" -> FailedContent(dlState.error, contentColor, onDownload)
                else -> AvailableContent(onViewNotes, onIgnore, onDownload)
            }
        }
    }
}

@Composable
private fun DownloadingContent(progress: Double, contentColor: androidx.compose.ui.graphics.Color) {
    Text(stringResource(R.string.settings_update_downloading, progress.toInt()),
        style = MaterialTheme.typography.bodyMedium, color = contentColor)
    Spacer(Modifier.height(8.dp))
    val animatedProgress by animateFloatAsState(
        targetValue = (progress / 100).toFloat().coerceIn(0f, 1f),
        animationSpec = spring(dampingRatio = Spring.DampingRatioNoBouncy),
        label = "update-progress",
    )
    LinearWavyProgressIndicator(
        progress = { animatedProgress },
        modifier = Modifier.fillMaxWidth().height(10.dp),
        color = contentColor,
        trackColor = contentColor.copy(alpha = 0.2f),
        amplitude = { 1f },
        waveSpeed = 40.dp,
        stopSize = 0.dp,
    )
}

@Composable
private fun ReadyContent(
    onInstall: () -> Unit,
    installFailed: Boolean,
    onFixPermission: () -> Unit,
) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Button(onClick = onInstall) {
            Text(stringResource(R.string.settings_update_install))
        }
    }
    if (installFailed) {
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = onFixPermission) {
            Text(stringResource(R.string.settings_update_install_failed),
                color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun FailedContent(
    error: String,
    contentColor: androidx.compose.ui.graphics.Color,
    onRetry: () -> Unit,
) {
    Text(error, style = MaterialTheme.typography.bodyMedium, color = contentColor)
    Spacer(Modifier.height(8.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Button(onClick = onRetry, colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.error,
            contentColor = MaterialTheme.colorScheme.onError,
        )) {
            Text(stringResource(R.string.settings_update_download))
        }
    }
}

@Composable
private fun AvailableContent(
    onViewNotes: () -> Unit,
    onIgnore: () -> Unit,
    onDownload: () -> Unit,
) {
    TextButton(onClick = onViewNotes) {
        Text(stringResource(R.string.settings_update_notes))
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        TextButton(onClick = onIgnore) {
            Text(stringResource(R.string.settings_update_ignore))
        }
        Spacer(Modifier.width(8.dp))
        Button(onClick = onDownload) {
            Text(stringResource(R.string.settings_update_download))
        }
    }
}
