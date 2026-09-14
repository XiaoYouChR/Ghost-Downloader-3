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
fun DraftTracks(
    videoTiers: List<DraftOption>,
    audioTiers: List<DraftOption>,
    hasCover: Boolean,
    isVideoEnabled: Boolean,
    isAudioEnabled: Boolean,
    isCoverEnabled: Boolean,
    videoTier: String,
    audioTier: String,
    audioLanguages: List<DraftOption>,
    selectedAudioLanguages: List<String>,
    onToggleTrack: (String, Boolean) -> Unit,
    onSelectQuality: (String, String) -> Unit,
    onSelectAudioLanguages: (List<String>) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (videoTiers.isNotEmpty()) {
            DraftToggle(stringResource(R.string.draft_track_video), isVideoEnabled) { onToggleTrack("video", it) }
            if (isVideoEnabled) DraftQuality(videoTiers, videoTier) { onSelectQuality("video", it) }
        }
        if (audioTiers.isNotEmpty()) {
            DraftToggle(stringResource(R.string.draft_track_audio), isAudioEnabled) { onToggleTrack("audio", it) }
            if (isAudioEnabled) {
                DraftQuality(audioTiers, audioTier) { onSelectQuality("audio", it) }
                DraftChoices(audioLanguages, selectedAudioLanguages, onChange = onSelectAudioLanguages)
            }
        }
        if (hasCover) DraftToggle(stringResource(R.string.draft_track_cover), isCoverEnabled) {
            onToggleTrack("cover", it)
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
