package com.xychr.ghostdownloader.features.yt_dlp_pack

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.i18n.toTaskError
import com.xychr.ghostdownloader.model.DraftPreview
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.packs.PackSettingsContent
import com.xychr.ghostdownloader.packs.PackUi
import com.xychr.ghostdownloader.packs.bool
import com.xychr.ghostdownloader.packs.int
import com.xychr.ghostdownloader.packs.optionList
import com.xychr.ghostdownloader.packs.strings
import com.xychr.ghostdownloader.ui.components.ErrorText
import com.xychr.ghostdownloader.ui.components.draft.DraftChoices
import com.xychr.ghostdownloader.ui.components.draft.DraftTrim
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

object YtDlpUi : PackUi {
    override val packId = "ytdlp"

    override val settingsTitle = R.string.pack_yt_dlp

    override val searchItems = listOf(
        R.string.ytdlp_cookie to R.string.ytdlp_cookie_desc,
        R.string.ytdlp_prefer_mp4 to R.string.ytdlp_prefer_mp4_desc,
        R.string.ytdlp_embed_metadata to R.string.ytdlp_embed_metadata_desc,
        R.string.ytdlp_embed_chapters to R.string.ytdlp_embed_chapters_desc,
        R.string.ytdlp_subtitle_languages to R.string.ytdlp_subtitle_languages_desc,
    )

    override val settingsContent: PackSettingsContent =
        { config, keys, set, send -> YtDlpSettings(config, keys, set, send) }

    override val draftExtra: (@Composable (JsonObject, String, suspend (String, List<Any?>) -> Unit) -> Unit) =
        { packFields, url, send ->
            val scope = rememberCoroutineScope()

            ProbeSection(packFields, send)

            val subtitles = packFields.optionList("subtitles")
            val duration = packFields.int("duration")

            if (packFields.bool("hasCover")) Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp)
                    .toggleable(packFields.bool("isCoverEnabled"), role = Role.Switch,
                        onValueChange = { scope.launch { send("setControl", listOf("cover", if (it) "1" else "")) } }),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(stringResource(R.string.draft_track_cover), Modifier.weight(1f))
                Switch(checked = packFields.bool("isCoverEnabled"), onCheckedChange = null)
            }

            if (subtitles.isNotEmpty()) DraftChoices(subtitles, packFields.strings("subtitleLanguages"),
                onChange = { langs -> scope.launch { send("setSubtitles", listOf(langs.joinToString(","))) } })

            if (duration > 0) DraftTrim(url, duration, packFields.bool("hasPreview"),
                packFields.int("startTime"), packFields.int("endTime"),
                onChange = { start, end -> scope.launch { send("setTrim", listOf(start, end)) } },
                fetchPreview = { engineRepository.query<DraftPreview>("draftPreview", it) })
        }
}

@Composable
private fun ProbeSection(packFields: JsonObject, send: suspend (String, List<Any?>) -> Unit) {
    val scope = rememberCoroutineScope()
    val canProbeMedia = packFields.bool("canProbeMedia")
    val hasMediaInfo = packFields.bool("hasMediaInfo")
    var isProbing by remember { mutableStateOf(false) }
    var probeError by remember { mutableStateOf<TaskError?>(null) }

    suspend fun probe(target: String) {
        isProbing = true
        probeError = null
        try { send("probe", listOf(target)) }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { probeError = failure.toTaskError() }
        finally { isProbing = false }
    }

    LaunchedEffect(canProbeMedia, hasMediaInfo) {
        if (canProbeMedia && !hasMediaInfo && !isProbing) probe("media")
    }

    if (isProbing) {
        Text(stringResource(R.string.draft_media_loading))
        LinearProgressIndicator(Modifier.fillMaxWidth())
    }
    probeError?.let { message ->
        ErrorText(message)
        TextButton(onClick = { scope.launch { probe("media") } }) {
            Text(stringResource(R.string.draft_retry))
        }
    }
    if (packFields.bool("canProbePlaylist")) {
        TextButton(onClick = { scope.launch { probe("playlist") } }, enabled = !isProbing) {
            Text(stringResource(R.string.draft_load_playlist))
        }
    }
}
