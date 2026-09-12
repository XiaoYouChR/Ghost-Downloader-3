package com.xychr.ghostdownloader.ui.pages
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.navigation.*
import com.xychr.ghostdownloader.ui.components.draft.*

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.xychr.ghostdownloader.R
import kotlinx.coroutines.launch

data class DraftEditorState(
    val item: DraftItem,
    val part: DraftPart,
    val initial: DraftEdits,
    val edits: DraftEdits,
    val isWorking: Boolean = false,
    val error: String? = null,
    val isProbing: Boolean = false,
    val probeError: String? = null,
    val categories: CategoryState = CategoryState(),
)

fun buildEdits(item: DraftItem) = DraftEdits(item.name, item.files, item.isVideoEnabled,
    item.isAudioEnabled, item.isCoverEnabled, item.videoTier, item.audioTier,
    item.subtitleLanguages, item.selectedAudioLanguages, item.startTime, item.endTime,
    item.categoryChoice, item.outputFolder)

fun buildChanges(initial: DraftEdits, edited: DraftEdits, part: DraftPart): List<DraftChange> = buildList {
    fun addChange(action: String, vararg args: Any) { add(DraftChange(action, args.toList())) }
    when (part) {
        DraftPart.Summary -> {
            if (edited.name.trim() != initial.name) addChange("setName", edited.name.trim())
            if (edited.categoryChoice != initial.categoryChoice)
                addChange("setCategory", edited.categoryChoice.orEmpty(), edited.categoryChoice == null)
            if (edited.outputFolder != initial.outputFolder) addChange("setOutputFolder", edited.outputFolder.trim())
        }
        DraftPart.Files -> {
            if (edited.files.map { it.index to it.isSelected } != initial.files.map { it.index to it.isSelected })
                addChange("setSelection", edited.files.filter { it.isSelected }.joinToString(",") { it.index.toString() })
            edited.files.forEach { file ->
                if (file.path != initial.files.first { it.index == file.index }.path)
                    addChange("setFileName", file.index, file.path.trim())
            }
        }
        DraftPart.Media -> {
            if (edited.isVideoEnabled != initial.isVideoEnabled) addChange("setTrack", "video", edited.isVideoEnabled)
            if (edited.isAudioEnabled != initial.isAudioEnabled) addChange("setTrack", "audio", edited.isAudioEnabled)
            if (edited.isCoverEnabled != initial.isCoverEnabled) addChange("setTrack", "cover", edited.isCoverEnabled)
            if (edited.videoTier != initial.videoTier) addChange("setQuality", "video", edited.videoTier)
            if (edited.audioTier != initial.audioTier) addChange("setQuality", "audio", edited.audioTier)
            if (edited.audioLanguages != initial.audioLanguages) addChange("setAudioLanguages", edited.audioLanguages.joinToString(","))
        }
        DraftPart.Subtitles -> if (edited.subtitles != initial.subtitles) addChange("setSubtitles", edited.subtitles.joinToString(","))
        DraftPart.Trim -> if (edited.start != initial.start || edited.end != initial.end)
            addChange("setTrim", edited.start, edited.end)
    }
}

class DraftEditor(initialItem: DraftItem) : ViewModel() {
    var initial by mutableStateOf(buildEdits(initialItem))
        private set
    var edits by mutableStateOf(initial)
        private set
    fun set(edits: DraftEdits) { this.edits = edits }
    fun setApplied() { initial = edits }
    fun updateName(name: String) {
        if (edits.name == initial.name) edits = edits.copy(name = name)
        initial = initial.copy(name = name)
    }
}

@Composable
fun DraftEditScreen(
    item: DraftItem?,
    part: DraftPart,
    state: DraftState,
    onApply: suspend (List<DraftChange>) -> Boolean,
    onOpen: (DraftPart) -> Unit,
    onProbe: (String) -> Unit,
    fetchPreview: suspend (String) -> DraftPreview,
    categories: CategoryState,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (item == null) {
        Column(modifier.padding(24.dp)) {
            Text(stringResource(R.string.draft_missing))
            TextButton(onClick = onBack) { Text(stringResource(R.string.action_back)) }
        }
        return
    }
    val editor: DraftEditor = viewModel(key = item.url + part.name,
        factory = viewModelFactory { initializer { DraftEditor(item) } })
    LaunchedEffect(item.name) { editor.updateName(item.name) }
    val scope = rememberCoroutineScope()
    DraftEditorPage(DraftEditorState(item, part, editor.initial, editor.edits, state.isWorking, state.error,
        item.url in state.probing, state.probeErrors[item.url]?.message, categories),
        onChange = { if (!state.isWorking) editor.set(it) },
        onApply = { scope.launch {
            if (onApply(buildChanges(editor.initial, editor.edits, part))) {
                editor.setApplied()
                onBack()
            }
        } },
        onOpen = { if (!state.isWorking) onOpen(it) },
        onProbe = { onProbe(if (it == "retry") state.probeErrors[item.url]?.kind ?: "media" else it) },
        fetchPreview = fetchPreview, onBack = onBack, modifier = modifier)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DraftEditorPage(
    state: DraftEditorState,
    onChange: (DraftEdits) -> Unit,
    onApply: () -> Unit,
    onOpen: (DraftPart) -> Unit,
    onProbe: (String) -> Unit,
    fetchPreview: suspend (String) -> DraftPreview,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val (item, part, initial, edits, isWorking, error, isProbing, probeError) = state
    val changes = buildChanges(initial, edits, part)
    var shouldDiscard by remember { mutableStateOf(false) }
    val back = { if (!isWorking) { if (changes.isNotEmpty()) shouldDiscard = true else onBack() } }
    BackHandler(enabled = isWorking || changes.isNotEmpty(), onBack = back)
    val title = when (part) {
        DraftPart.Summary -> R.string.draft_edit
        DraftPart.Files -> R.string.draft_select_files
        DraftPart.Media -> R.string.draft_media
        DraftPart.Subtitles -> R.string.draft_subtitle
        DraftPart.Trim -> R.string.draft_trim
    }
    val isValid = when (part) {
        DraftPart.Summary -> edits.name.isNotBlank()
        DraftPart.Files -> edits.files.any { it.isSelected } && edits.files.all { it.path.isNotBlank() }
        DraftPart.Media -> (item.videoTiers.isNotEmpty() && edits.isVideoEnabled) ||
            (item.audioTiers.isNotEmpty() && edits.isAudioEnabled) || (item.hasCover && edits.isCoverEnabled)
        DraftPart.Trim -> edits.start >= 0 && edits.start < (if (edits.end == 0) item.duration else edits.end) &&
            edits.end in 0..item.duration
        else -> true
    }
    Scaffold(modifier = modifier, topBar = {
        TopAppBar(title = { Text(stringResource(title)) }, navigationIcon = {
            IconButton(onClick = back, enabled = !isWorking) {
                Icon(painterResource(R.drawable.ic_arrow_back), stringResource(R.string.action_back))
            }
        }, actions = {
            TextButton(onClick = onApply, enabled = !isWorking && isValid && changes.isNotEmpty()) {
                Text(stringResource(R.string.draft_apply))
            }
        })
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding()) {
            if (isWorking) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (error != null) Text(error, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp))
            if (part == DraftPart.Files) {
                FileSelectPage(edits.files, item.canRenameFiles,
                    onChange = { onChange(edits.copy(files = it)) }, modifier = Modifier.weight(1f))
            } else Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                when (part) {
                    DraftPart.Summary -> {
                        OutlinedTextField(edits.name, { onChange(edits.copy(name = it)) },
                            label = { Text(stringResource(R.string.draft_name)) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(edits.outputFolder, { onChange(edits.copy(outputFolder = it)) },
                            label = { Text(stringResource(R.string.task_output_folder)) }, modifier = Modifier.fillMaxWidth())
                        if (state.categories.isEnabled) {
                            DraftCategoryField(edits.categoryChoice, state.categories.categories,
                                { onChange(edits.copy(categoryChoice = it)) }, isEnabled = !isWorking)
                            Text(stringResource(R.string.task_category_creation_hint), style = MaterialTheme.typography.bodySmall)
                        }
                        Text(if (changes.isEmpty()) stringResource(R.string.task_target_folder, item.targetFolder)
                            else stringResource(R.string.task_target_folder_pending), style = MaterialTheme.typography.bodySmall)
                        if (isProbing) {
                            Text(stringResource(R.string.draft_media_loading))
                            LinearProgressIndicator(Modifier.fillMaxWidth())
                        }
                        if (probeError != null) {
                            Text(probeError, color = MaterialTheme.colorScheme.error)
                            TextButton(onClick = { onProbe("retry") }) { Text(stringResource(R.string.draft_retry)) }
                        }
                        if (item.files.size > 1) TextButton(onClick = { onOpen(DraftPart.Files) }) {
                            Text(stringResource(R.string.draft_files_selected, item.files.count { it.isSelected }, item.files.size))
                        }
                        if (item.canProbePlaylist && item.files.size <= 1) TextButton(
                            onClick = { onProbe("playlist") }, enabled = !isProbing) {
                            Text(stringResource(R.string.draft_load_playlist))
                        }
                        if (item.videoTiers.isNotEmpty() || item.audioTiers.isNotEmpty() || item.hasCover)
                            TextButton(onClick = { onOpen(DraftPart.Media) }) { Text(stringResource(R.string.draft_media)) }
                        if (item.subtitles.isNotEmpty() && (item.isVideoEnabled || item.isAudioEnabled))
                            TextButton(onClick = { onOpen(DraftPart.Subtitles) }) {
                            Text(stringResource(R.string.draft_subtitle_count, item.subtitleLanguages.size))
                        }
                        if (item.duration > 0 && (item.isVideoEnabled || item.isAudioEnabled))
                            TextButton(onClick = { onOpen(DraftPart.Trim) }) {
                            Text(stringResource(R.string.draft_trim))
                        }
                    }
                    DraftPart.Media -> DraftTracks(item, edits, onChange)
                    DraftPart.Subtitles -> DraftChoices(item.subtitles, edits.subtitles,
                        onChange = { onChange(edits.copy(subtitles = it)) })
                    DraftPart.Trim -> DraftTrim(item, edits.start, edits.end,
                        onChange = { start, end -> onChange(edits.copy(start = start, end = end)) },
                        fetchPreview = fetchPreview)
                }
            }
        }
    }
    if (shouldDiscard) DiscardDialog(onDismiss = { shouldDiscard = false }, onDiscard = onBack)
}
