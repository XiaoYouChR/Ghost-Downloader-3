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
import com.xychr.ghostdownloader.packs.PackRegistry
import kotlinx.coroutines.launch

data class DraftEditorState(
    val item: DraftItem,
    val part: DraftPart,
    val initial: DraftEdits,
    val edits: DraftEdits,
    val isWorking: Boolean = false,
    val error: String? = null,
    val categories: CategoryState = CategoryState(),
)

data class DraftEdits(
    val name: String,
    val files: List<DraftFile>,
    val categoryChoice: String? = null,
    val outputFolder: String = "",
)

fun buildEdits(item: DraftItem) = DraftEdits(item.name, item.files, item.categoryChoice, item.outputFolder)

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
    sendPack: suspend (String, List<Any>) -> Unit,
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
        categories),
        onChange = { if (!state.isWorking) editor.set(it) },
        onApply = { scope.launch {
            if (onApply(buildChanges(editor.initial, editor.edits, part))) {
                editor.setApplied()
                onBack()
            }
        } },
        onOpen = { if (!state.isWorking) onOpen(it) },
        sendPack = sendPack, onBack = onBack, modifier = modifier)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DraftEditorPage(
    state: DraftEditorState,
    onChange: (DraftEdits) -> Unit,
    onApply: () -> Unit,
    onOpen: (DraftPart) -> Unit,
    sendPack: suspend (String, List<Any>) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val (item, part, initial, edits, isWorking, error) = state
    val changes = buildChanges(initial, edits, part)
    var shouldDiscard by remember { mutableStateOf(false) }
    val back = { if (!isWorking) { if (changes.isNotEmpty()) shouldDiscard = true else onBack() } }
    BackHandler(enabled = isWorking || changes.isNotEmpty(), onBack = back)
    val title = when (part) {
        DraftPart.Summary -> R.string.draft_edit
        DraftPart.Files -> R.string.draft_select_files
    }
    val isValid = when (part) {
        DraftPart.Summary -> edits.name.isNotBlank()
        DraftPart.Files -> edits.files.any { it.isSelected } && edits.files.all { it.path.isNotBlank() }
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
                if (item.files.size > 1) TextButton(onClick = { onOpen(DraftPart.Files) }) {
                    Text(stringResource(R.string.draft_files_selected, item.files.count { it.isSelected }, item.files.size))
                }
                PackRegistry[item.packId]?.draftExtra?.invoke(item.packFields, item.url, sendPack)
            }
        }
    }
    if (shouldDiscard) DiscardDialog(onDismiss = { shouldDiscard = false }, onDiscard = onBack)
}
