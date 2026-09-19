package com.xychr.ghostdownloader.features.bittorrent_pack

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.SheetValue
import androidx.compose.material3.rememberBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.sizes
import com.xychr.ghostdownloader.packs.str
import com.xychr.ghostdownloader.packs.strings
import com.xychr.ghostdownloader.i18n.toTaskError
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.ui.components.ErrorText
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import java.net.URI

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WebTrackerSheet(
    config: JsonObject,
    keys: PackKeys,
    set: (String, Any) -> Unit,
    send: suspend (String, List<Any?>) -> JsonElement,
    onDismiss: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    val cachedCounts = remember(config) { config.sizes(keys("webTrackerSourceCache")) }
    var sources by remember { mutableStateOf(config.strings(keys("webTrackerSources"))) }
    var customText by remember { mutableStateOf(config.str(keys("webTrackerCustomList"))) }
    var hasValidated by remember { mutableStateOf(false) }
    var isRefreshing by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<TaskError?>(null) }

    fun save() {
        hasValidated = true
        val normalized = sources.map(String::trim).filter(String::isNotEmpty).distinct()
        if (normalized.any { !isSourceUrl(it) }) return
        scope.launch {
            isRefreshing = true
            error = null
            try {
                send("setWebTrackerSources", listOf(normalized.joinToString("\n")))
                set(keys("webTrackerCustomList"), customText.lines().map(String::trim)
                    .filter(String::isNotEmpty).joinToString("\n"))
                send("refreshWebTrackers", emptyList())
                onDismiss()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                error = failure.toTaskError()
            } finally {
                isRefreshing = false
            }
        }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberBottomSheetState(
            initialValue = SheetValue.Hidden,
            enabledValues = setOf(SheetValue.Hidden, SheetValue.Expanded),
        ),
    ) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp).padding(bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    stringResource(R.string.bt_web_tracker_sources),
                    style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { sources = sources + "" }) {
                    Text(stringResource(R.string.bt_web_tracker_add))
                }
            }

            sources.forEachIndexed { index, url ->
                val isInvalid = hasValidated && url.isNotBlank() && !isSourceUrl(url)
                OutlinedTextField(
                    value = url,
                    onValueChange = { sources = sources.toMutableList().also { list -> list[index] = it } },
                    isError = isInvalid,
                    singleLine = true,
                    placeholder = { Text("https://example.com/best.txt") },
                    supportingText = {
                        Text(
                            when {
                                isInvalid -> stringResource(R.string.bt_web_tracker_invalid)
                                cachedCounts[url] == null -> stringResource(R.string.bt_web_tracker_never)
                                else -> stringResource(R.string.bt_web_tracker_source_count, cachedCounts.getValue(url))
                            }
                        )
                    },
                    trailingIcon = {
                        IconButton(onClick = { sources = sources.filterIndexed { i, _ -> i != index } }) {
                            Icon(
                                painterResource(R.drawable.ic_delete),
                                contentDescription = stringResource(R.string.action_delete),
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            Text(
                stringResource(R.string.bt_custom_trackers),
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = 8.dp),
            )
            OutlinedTextField(
                value = customText,
                onValueChange = { customText = it },
                placeholder = { Text(stringResource(R.string.bt_custom_trackers_desc)) },
                minLines = 3,
                modifier = Modifier.fillMaxWidth(),
            )

            error?.let { ErrorText(it) }

            Button(
                onClick = { save() },
                enabled = !isRefreshing,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            ) {
                Text(
                    if (isRefreshing) stringResource(R.string.bt_web_tracker_refreshing)
                    else stringResource(R.string.bt_web_tracker_save)
                )
            }
        }
    }
}

private fun isSourceUrl(url: String): Boolean {
    val parsed = runCatching { URI(url.trim()) }.getOrNull() ?: return false
    return parsed.scheme?.lowercase() in setOf("http", "https") && !parsed.host.isNullOrEmpty()
}
