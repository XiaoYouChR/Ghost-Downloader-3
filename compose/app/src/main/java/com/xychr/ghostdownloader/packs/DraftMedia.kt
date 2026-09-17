package com.xychr.ghostdownloader.packs

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.DraftOption
import com.xychr.ghostdownloader.model.DraftPreview
import com.xychr.ghostdownloader.ui.components.draft.DraftChoices
import com.xychr.ghostdownloader.ui.components.draft.DraftTrim
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

fun JsonObject.optionList(key: String): List<DraftOption> =
    (this[key] as? JsonArray)?.map {
        val obj = it.jsonObject
        DraftOption(obj["key"]?.jsonPrimitive?.content ?: "", obj["label"]?.jsonPrimitive?.content ?: "")
    } ?: emptyList()

@Composable
fun DraftMediaSection(packFields: JsonObject, url: String, send: suspend (String, List<Any?>) -> Unit) {
    val scope = rememberCoroutineScope()
    val subtitles = packFields.optionList("subtitles")
    val duration = packFields.int("duration")

    if (packFields.bool("hasCover")) DraftToggle(
        label = stringResource(R.string.draft_track_cover),
        isChecked = packFields.bool("isCoverEnabled"),
    ) { scope.launch { send("setControl", listOf("cover", if (it) "1" else "")) } }

    if (subtitles.isNotEmpty()) DraftChoices(subtitles, packFields.strings("subtitleLanguages"),
        onChange = { langs -> scope.launch { send("setSubtitles", listOf(langs.joinToString(","))) } })

    if (duration > 0) DraftTrim(url, duration, packFields.bool("hasPreview"),
        packFields.int("startTime"), packFields.int("endTime"),
        onChange = { start, end -> scope.launch { send("setTrim", listOf(start, end)) } },
        fetchPreview = { engineRepository.query<DraftPreview>("draftPreview", it) })
}

@Composable
private fun DraftToggle(label: String, isChecked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(isChecked, role = Role.Switch,
        onValueChange = onChange), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f))
        Switch(checked = isChecked, onCheckedChange = null)
    }
}
