package com.xychr.ghostdownloader.features.yt_dlp_pack

import com.xychr.ghostdownloader.packs.*

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.DraftOption
import com.xychr.ghostdownloader.model.DraftPreview
import com.xychr.ghostdownloader.ui.components.draft.DraftChoices
import com.xychr.ghostdownloader.ui.components.draft.DraftTracks
import com.xychr.ghostdownloader.ui.components.draft.DraftTrim
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

object YtDlpUi : PackUi {
    override val packId = "ytdlp"

    override val settingsTitle = R.string.pack_yt_dlp

    override val searchItems = listOf(
        R.string.ytdlp_prefer_mp4 to R.string.ytdlp_prefer_mp4_desc,
        R.string.ytdlp_embed_metadata to R.string.ytdlp_embed_metadata_desc,
        R.string.ytdlp_embed_chapters to R.string.ytdlp_embed_chapters_desc,
        R.string.ytdlp_subtitle_languages to R.string.ytdlp_subtitle_languages_desc,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set -> YtDlpSettings(config, keys, set) }

    override val draftExtra: (@Composable (JsonObject, String, suspend (String, List<Any>) -> Unit) -> Unit) =
        { packFields, url, send ->
            val scope = rememberCoroutineScope()

            // Probe
            val canProbeMedia = packFields.bool("canProbeMedia")
            val hasMediaInfo = packFields.bool("hasMediaInfo")
            val canProbePlaylist = packFields.bool("canProbePlaylist")
            var isProbing by remember { mutableStateOf(false) }
            var probeError by remember { mutableStateOf<String?>(null) }

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

            // Media
            val videoTiers = packFields.optionList("videoTiers")
            val audioTiers = packFields.optionList("audioTiers")
            val hasCover = packFields.bool("hasCover")
            val subtitles = packFields.optionList("subtitles")
            val duration = packFields.int("duration")
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
            if (duration > 0 && (isVideoEnabled || isAudioEnabled)) {
                DraftTrim(url, duration, packFields.bool("hasPreview"),
                    packFields.int("startTime"), packFields.int("endTime"),
                    onChange = { start, end -> scope.launch { send("setTrim", listOf(start, end)) } },
                    fetchPreview = { EngineRepository.query<DraftPreview>("draftPreview", it) })
            }
        }
}

private fun JsonObject.optionList(key: String): List<DraftOption> =
    (this[key] as? JsonArray)?.map {
        val obj = it.jsonObject
        DraftOption(obj["key"]?.jsonPrimitive?.content ?: "", obj["label"]?.jsonPrimitive?.content ?: "")
    } ?: emptyList()

private fun JsonObject.stringList(key: String): List<String> =
    (this[key] as? JsonArray)?.mapNotNull { it.jsonPrimitive.contentOrNull } ?: emptyList()
