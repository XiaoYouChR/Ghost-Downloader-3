package com.xychr.ghostdownloader.features.yt_dlp_pack

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.bool
import com.xychr.ghostdownloader.packs.str
import com.xychr.ghostdownloader.i18n.toTaskError
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.ui.components.ErrorText
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

@Composable
fun YtDlpSettings(
    config: JsonObject,
    k: PackKeys,
    set: (String, Any) -> Unit,
    send: suspend (String, List<Any?>) -> JsonElement,
) {
    YtDlpCookieRows(send)

    SettingSection {
        SwitchSettingRow(
            title = stringResource(R.string.ytdlp_prefer_mp4),
            subtitle = stringResource(R.string.ytdlp_prefer_mp4_desc),
            checked = config.bool(k("shouldPreferMp4")),
            onCheckedChange = { set(k("shouldPreferMp4"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.ytdlp_embed_metadata),
            subtitle = stringResource(R.string.ytdlp_embed_metadata_desc),
            checked = config.bool(k("shouldEmbedMetadata")),
            onCheckedChange = { set(k("shouldEmbedMetadata"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.ytdlp_embed_chapters),
            subtitle = stringResource(R.string.ytdlp_embed_chapters_desc),
            checked = config.bool(k("shouldEmbedChapters")),
            onCheckedChange = { set(k("shouldEmbedChapters"), it) },
        )
        TextSettingRow(
            title = stringResource(R.string.ytdlp_subtitle_languages),
            value = config.str(k("subtitleLanguages")),
            onConfirm = { set(k("subtitleLanguages"), it) },
            emptyHint = stringResource(R.string.ytdlp_subtitle_languages_desc),
            placeholder = "en,zh-Hans",
        )
    }
}

@Composable
private fun YtDlpCookieRows(send: suspend (String, List<Any?>) -> JsonElement) {
    val scope = rememberCoroutineScope()
    var hasCookies by remember { mutableStateOf(false) }
    var isImporting by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<TaskError?>(null) }

    suspend fun refresh() {
        val state = runCatching { send("cookieState", emptyList()) }.getOrNull() as? JsonObject
        hasCookies = state?.bool("hasCookies") == true
    }

    suspend fun run(action: String, args: List<Any?> = emptyList()) {
        error = null
        try {
            send(action, args)
            refresh()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            error = failure.toTaskError()
        }
    }

    LaunchedEffect(Unit) { refresh() }

    SettingSection {
        ActionSettingRow(
            title = stringResource(R.string.ytdlp_cookie),
            subtitle = if (hasCookies) stringResource(R.string.ytdlp_cookie_imported)
            else stringResource(R.string.ytdlp_cookie_desc),
            onClick = { isImporting = true },
        )
        if (hasCookies) {
            ActionSettingRow(
                title = stringResource(R.string.ytdlp_cookie_clear),
                onClick = { scope.launch { run("clearCookies") } },
            )
        }
        ErrorText(error)
    }

    if (isImporting) {
        CookieImportDialog(
            onDismiss = { isImporting = false },
            onSave = { text ->
                isImporting = false
                scope.launch { run("saveCookies", listOf(text)) }
            },
        )
    }
}

@Composable
private fun CookieImportDialog(onDismiss: () -> Unit, onSave: (String) -> Unit) {
    var text by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.ytdlp_cookie_import)) },
        text = {
            Column {
                Text(
                    stringResource(R.string.ytdlp_cookie_hint),
                    style = MaterialTheme.typography.bodyMedium,
                )
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    placeholder = { Text("SID=xxx; HSID=xxx; ...") },
                    minLines = 4,
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(text.trim()) }, enabled = text.isNotBlank()) {
                Text(stringResource(R.string.action_ok))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        },
    )
}
