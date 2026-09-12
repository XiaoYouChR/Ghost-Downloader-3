package com.xychr.ghostdownloader.ui.components.draft
import com.xychr.ghostdownloader.model.*

import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R

@Composable
fun DraftTracks(item: DraftItem, edits: DraftEdits, onChange: (DraftEdits) -> Unit, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (item.videoTiers.isNotEmpty()) {
            DraftToggle(stringResource(R.string.draft_track_video), edits.isVideoEnabled) { onChange(edits.copy(isVideoEnabled = it)) }
            if (edits.isVideoEnabled) DraftQuality(item.videoTiers, edits.videoTier) { onChange(edits.copy(videoTier = it)) }
        }
        if (item.audioTiers.isNotEmpty()) {
            DraftToggle(stringResource(R.string.draft_track_audio), edits.isAudioEnabled) { onChange(edits.copy(isAudioEnabled = it)) }
            if (edits.isAudioEnabled) {
                DraftQuality(item.audioTiers, edits.audioTier) { onChange(edits.copy(audioTier = it)) }
                DraftChoices(item.audioLanguages, edits.audioLanguages,
                    onChange = { onChange(edits.copy(audioLanguages = it)) })
            }
        }
        if (item.hasCover) DraftToggle(stringResource(R.string.draft_track_cover), edits.isCoverEnabled) {
            onChange(edits.copy(isCoverEnabled = it))
        }
    }
}

@Composable
internal fun DraftToggle(label: String, isChecked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(isChecked, role = Role.Switch,
        onValueChange = onChange), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f))
        Switch(checked = isChecked, onCheckedChange = null)
    }
}

@Composable
private fun DraftQuality(options: List<DraftOption>, selected: String, onSelect: (String) -> Unit) {
    Column(Modifier.selectableGroup()) {
        options.forEach { option ->
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(selected == option.key,
                role = Role.RadioButton, onClick = { onSelect(option.key) }),
                verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected == option.key, onClick = null)
                Text(option.label, Modifier.padding(start = 12.dp))
            }
        }
    }
}

@Composable
fun DraftChoices(
    options: List<DraftOption>,
    selected: List<String>,
    onChange: (List<String>) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier) {
        options.forEach { option ->
            val isChecked = option.key in selected
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(isChecked, role = Role.Checkbox,
                onValueChange = { onChange(if (it) selected + option.key else selected - option.key) }),
                verticalAlignment = Alignment.CenterVertically) {
                Checkbox(isChecked, onCheckedChange = null)
                Text(option.label, Modifier.padding(start = 12.dp))
            }
        }
    }
}
