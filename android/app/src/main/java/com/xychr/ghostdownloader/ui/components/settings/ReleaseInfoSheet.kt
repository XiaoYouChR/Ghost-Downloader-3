package com.xychr.ghostdownloader.ui.components.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mikepenz.markdown.m3.Markdown
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.ui.pages.settings.UpdateAvailable

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReleaseInfoSheet(
    available: UpdateAvailable,
    onDismiss: () -> Unit,
    onDownload: () -> Unit,
    onOpenInBrowser: () -> Unit,
) {
    var body by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        body = engineRepository.query<String>("releaseBody")
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
    ) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 24.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(available.version, style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.width(8.dp))
                Text(
                    available.publishedAt.take(10),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (available.prerelease) {
                Text(
                    stringResource(R.string.settings_update_prerelease),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
            Spacer(Modifier.height(16.dp))
            val loaded = body
            if (loaded == null) {
                CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally))
            } else {
                Markdown(
                    loaded.ifEmpty { stringResource(R.string.settings_update_no_notes) },
                    modifier = Modifier
                        .weight(1f, fill = false)
                        .verticalScroll(rememberScrollState()),
                )
            }
            Spacer(Modifier.height(16.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = onOpenInBrowser) {
                    Text(stringResource(R.string.settings_update_open_in_browser))
                }
                Spacer(Modifier.width(8.dp))
                Button(onClick = { onDownload(); onDismiss() }) {
                    Text(stringResource(R.string.settings_update_install))
                }
            }
        }
    }
}
