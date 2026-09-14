package com.xychr.ghostdownloader.features.bili_pack

import com.xychr.ghostdownloader.packs.*

import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.DraftOption
import com.xychr.ghostdownloader.model.DraftPreview
import com.xychr.ghostdownloader.ui.components.draft.DraftChoices
import com.xychr.ghostdownloader.ui.components.draft.DraftTracks
import com.xychr.ghostdownloader.ui.components.draft.DraftTrim
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

object BilibiliUi : PackUi {
    override val packId = "bili"

    override val settingsTitle = R.string.pack_bilibili

    override val searchItems = listOf(
        R.string.bili_scan_login to null,
        R.string.bili_import_cookie to null,
        R.string.bili_logout to null,
        R.string.bili_default_quality to null,
        R.string.bili_alternative_quality to null,
        R.string.bili_hdr to R.string.bili_hdr_desc,
        R.string.bili_dolby to R.string.bili_dolby_desc,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set ->
            BilibiliLoginRows()
            BilibiliSettings(config, keys, set)
        }

    override val draftExtra: (@Composable (JsonObject, String, suspend (String, List<Any>) -> Unit) -> Unit) =
        { packFields, url, send ->
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
