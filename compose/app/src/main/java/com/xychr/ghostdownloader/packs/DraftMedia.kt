package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.DraftOption
import com.xychr.ghostdownloader.model.DraftPreview
import com.xychr.ghostdownloader.ui.components.draft.DraftChoices
import com.xychr.ghostdownloader.ui.components.draft.DraftTracks
import com.xychr.ghostdownloader.ui.components.draft.DraftTrim
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

fun JsonObject.optionList(key: String): List<DraftOption> =
    (this[key] as? JsonArray)?.map {
        val obj = it.jsonObject
        DraftOption(obj["key"]?.jsonPrimitive?.content ?: "", obj["label"]?.jsonPrimitive?.content ?: "")
    } ?: emptyList()

fun JsonObject.stringList(key: String): List<String> =
    (this[key] as? JsonArray)?.mapNotNull { it.jsonPrimitive.contentOrNull } ?: emptyList()

@Composable
fun DraftMediaSection(packFields: JsonObject, url: String, send: suspend (String, List<Any?>) -> Unit) {
    val scope = rememberCoroutineScope()
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
            fetchPreview = { engineRepository.query<DraftPreview>("draftPreview", it) })
    }
}

fun mediaSummary(packFields: JsonObject): String? = buildList {
    if (packFields.bool("isVideoEnabled")) tierLabel(packFields, "videoTiers", "videoTier")?.let(::add)
    if (packFields.bool("isAudioEnabled")) tierLabel(packFields, "audioTiers", "audioTier")?.let(::add)
}.joinToString(" · ").ifEmpty { null }

private fun tierLabel(packFields: JsonObject, tiersKey: String, tierKey: String): String? {
    val tier = packFields.str(tierKey).ifEmpty { return null }
    return packFields.optionList(tiersKey).firstOrNull { it.key == tier }?.label ?: tier
}
