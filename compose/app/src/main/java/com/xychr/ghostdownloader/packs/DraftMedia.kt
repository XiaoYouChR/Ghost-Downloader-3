package com.xychr.ghostdownloader.packs

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.DraftOption
import com.xychr.ghostdownloader.model.DraftPreview
import com.xychr.ghostdownloader.ui.components.draft.DraftChoices
import com.xychr.ghostdownloader.ui.components.draft.DraftTracks
import com.xychr.ghostdownloader.ui.components.draft.DraftTrim
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*

internal fun JsonObject.optionList(key: String): List<DraftOption> =
    (this[key] as? JsonArray)?.map {
        val obj = it.jsonObject
        DraftOption(obj["key"]?.jsonPrimitive?.content ?: "", obj["label"]?.jsonPrimitive?.content ?: "")
    } ?: emptyList()

internal fun JsonObject.stringList(key: String): List<String> =
    (this[key] as? JsonArray)?.mapNotNull { it.jsonPrimitive.contentOrNull } ?: emptyList()

@Composable
internal fun DraftMediaSection(
    packFields: JsonObject,
    send: suspend (String, List<Any>) -> Unit,
    fetchPreview: (suspend (String) -> DraftPreview)? = null,
    url: String = "",
) {
    val scope = rememberCoroutineScope()
    val videoTiers = packFields.optionList("videoTiers")
    val audioTiers = packFields.optionList("audioTiers")
    val hasCover = packFields.bool("hasCover")
    val subtitles = packFields.optionList("subtitles")
    val duration = packFields.int("duration")
    val hasPreview = packFields.bool("hasPreview")
    val isVideoEnabled = packFields.bool("isVideoEnabled")
    val isAudioEnabled = packFields.bool("isAudioEnabled")

    if (videoTiers.isNotEmpty() || audioTiers.isNotEmpty() || hasCover) {
        DraftTracks(videoTiers, audioTiers, hasCover,
            isVideoEnabled = isVideoEnabled,
            isAudioEnabled = isAudioEnabled,
            isCoverEnabled = packFields.bool("isCoverEnabled"),
            videoTier = packFields.str("videoTier"),
            audioTier = packFields.str("audioTier"),
            audioLanguages = packFields.optionList("audioLanguages"),
            selectedAudioLanguages = packFields.stringList("selectedAudioLanguages"),
            onToggleTrack = { track, enabled -> scope.launch { send("setTrack", listOf(track, enabled)) } },
            onSelectQuality = { track, key -> scope.launch { send("setQuality", listOf(track, key)) } },
            onSelectAudioLanguages = { langs -> scope.launch { send("setAudioLanguages", listOf(langs.joinToString(","))) } },
        )
    }
    if (subtitles.isNotEmpty() && (isVideoEnabled || isAudioEnabled)) {
        DraftChoices(subtitles, packFields.stringList("subtitleLanguages"),
            onChange = { langs -> scope.launch { send("setSubtitles", listOf(langs.joinToString(","))) } })
    }
    if (duration > 0 && (isVideoEnabled || isAudioEnabled) && fetchPreview != null) {
        DraftTrim(url, duration, hasPreview,
            packFields.int("startTime"), packFields.int("endTime"),
            onChange = { start, end -> scope.launch { send("setTrim", listOf(start, end)) } },
            fetchPreview = fetchPreview)
    }
}

@Composable
internal fun DraftProbeSection(
    packFields: JsonObject,
    send: suspend (String, List<Any>) -> Unit,
) {
    val canProbeMedia = packFields.bool("canProbeMedia")
    val hasMediaInfo = packFields.bool("hasMediaInfo")
    val canProbePlaylist = packFields.bool("canProbePlaylist")
    var isProbing by remember { mutableStateOf(false) }
    var probeError by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(canProbeMedia, hasMediaInfo) {
        if (canProbeMedia && !hasMediaInfo && !isProbing) {
            isProbing = true
            probeError = null
            try { send("probe", listOf("media")) }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { probeError = e.message ?: e.toString() }
            finally { isProbing = false }
        }
    }

    if (isProbing) {
        Text(stringResource(R.string.draft_media_loading))
        LinearProgressIndicator(Modifier.fillMaxWidth())
    }
    if (probeError != null) {
        Text(probeError!!, color = MaterialTheme.colorScheme.error)
        TextButton(onClick = {
            probeError = null
            scope.launch {
                isProbing = true
                try { send("probe", listOf("media")) }
                catch (e: CancellationException) { throw e }
                catch (e: Exception) { probeError = e.message ?: e.toString() }
                finally { isProbing = false }
            }
        }) { Text(stringResource(R.string.draft_retry)) }
    }
    if (canProbePlaylist) {
        TextButton(onClick = {
            scope.launch {
                isProbing = true
                probeError = null
                try { send("probe", listOf("playlist")) }
                catch (e: CancellationException) { throw e }
                catch (e: Exception) { probeError = e.message ?: e.toString() }
                finally { isProbing = false }
            }
        }, enabled = !isProbing) {
            Text(stringResource(R.string.draft_load_playlist))
        }
    }
}
