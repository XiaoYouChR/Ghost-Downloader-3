package com.xychr.ghostdownloader.ui.pages

import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.*

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
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

data class TaskOptionDraft(
    val outputFolder: String,
    val url: String? = null,
    val headers: String? = null,
    val clientProfile: String? = null,
    val userAgent: String? = null,
    val connections: String? = null,
    val recordLimit: String? = null,
    val decryptionKeys: String? = null,
    val decryptionKeyFile: String? = null,
    val muxImports: String? = null,
) {
    fun toOptions(): TaskOptions {
        val parsedHeaders = headers?.lineSequence()?.filter { it.isNotBlank() }?.associate { line ->
            val split = line.indexOf(':')
            require(split > 0) { "Use one Header: value per line" }
            line.substring(0, split).trim() to line.substring(split + 1).trim()
        }
        val count = connections?.let {
            requireNotNull(it.toIntOrNull()?.takeIf { n -> n in 1..256 }) { "Connections must be between 1 and 256" }
        }
        return TaskOptions(outputFolder.trim(), url?.trim(), parsedHeaders, clientProfile, userAgent, count,
            recordLimit, decryptionKeys?.lines()?.filter(String::isNotBlank), decryptionKeyFile,
            muxImports?.lines()?.filter(String::isNotBlank))
    }
}

fun TaskOptions.toDraft() = TaskOptionDraft(outputFolder, url,
    headers?.entries?.joinToString("\n") { "${it.key}: ${it.value}" }, clientProfile, userAgent,
    subworkerCount?.toString(), recordLimit, decryptionKeys?.joinToString("\n"), decryptionKeyFile,
    muxImports?.joinToString("\n"))

data class TaskEditState(
    val draft: TaskOptionDraft? = null,
    val initial: TaskOptionDraft? = null,
    val isSaving: Boolean = false,
    val isDone: Boolean = false,
    val needsConfirmation: Boolean = false,
    val error: String? = null,
) { val hasChanges get() = draft != initial }

class TaskEditViewModel(
    private val fetch: suspend () -> TaskOptions,
    private val send: suspend (TaskOptions, Boolean) -> TaskEditResult,
) : ViewModel() {
    private val mutableState = MutableStateFlow(TaskEditState())
    val state = mutableState.asStateFlow()
    init { refresh() }
    fun refresh() {
        viewModelScope.launch {
            try {
                val draft = fetch().toDraft()
                mutableState.value = TaskEditState(draft, draft)
            } catch (error: Exception) { mutableState.value = state.value.copy(error = error.message) }
        }
    }
    fun update(draft: TaskOptionDraft) {
        if (!state.value.isSaving) mutableState.value = state.value.copy(draft = draft, error = null)
    }
    fun cancelConfirmation() { mutableState.value = state.value.copy(needsConfirmation = false) }
    fun save(shouldDiscard: Boolean = false) {
        val before = state.value
        if (before.isSaving || !before.hasChanges) return
        mutableState.value = before.copy(isSaving = true, needsConfirmation = false, error = null)
        viewModelScope.launch {
            try {
                val result = send(requireNotNull(before.draft).toOptions(), shouldDiscard)
                mutableState.value = state.value.copy(isSaving = false,
                    needsConfirmation = result.needsConfirmation, isDone = !result.needsConfirmation)
            } catch (error: Exception) {
                mutableState.value = state.value.copy(isSaving = false, error = error.message)
            }
        }
    }
}

@Composable
fun TaskEditPage(taskId: String, onBack: () -> Unit) {
    val model: TaskEditViewModel = viewModel(key = taskId) {
        TaskEditViewModel(
            fetch = { EngineRepository.query("taskOptions", taskId) },
            send = { options, discard -> EngineRepository.query("updateTaskOptions", taskId,
                EngineRepository.encode(options), discard) },
        )
    }
    val state by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val close: () -> Unit = {
        scope.launch {
            runCatching { EngineRepository.invoke("cancelTaskEdit", taskId) }
            onBack()
        }
    }
    LaunchedEffect(state.isDone) { if (state.isDone) onBack() }
    TaskOptionsEditor(state, model::update, { model.save() }, close, onRetry = model::refresh)
    if (state.needsConfirmation) AlertDialog(
        onDismissRequest = model::cancelConfirmation,
        title = { Text(stringResource(R.string.task_change_source)) },
        text = { Text(stringResource(R.string.task_change_source_warning)) },
        confirmButton = { TextButton(onClick = { model.save(true) }) { Text(stringResource(R.string.task_apply_start)) } },
        dismissButton = { TextButton(onClick = model::cancelConfirmation) { Text(stringResource(R.string.action_cancel)) } },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskOptionsEditor(
    state: TaskEditState, onChange: (TaskOptionDraft) -> Unit, onSave: () -> Unit, onBack: () -> Unit,
    modifier: Modifier = Modifier, onRetry: () -> Unit = {},
) {
    var shouldDiscard by remember { mutableStateOf(false) }
    val close = { if (state.hasChanges) shouldDiscard = true else onBack() }
    BackHandler { if (!state.isSaving) close() }
    Scaffold(modifier = modifier, topBar = {
        TopAppBar(title = { Text(stringResource(R.string.task_edit_options)) },
            navigationIcon = { IconButton(onClick = close, enabled = !state.isSaving) {
                Icon(painterResource(R.drawable.ic_arrow_back), stringResource(R.string.action_back))
            } })
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.task_edit_execution_hint), style = MaterialTheme.typography.bodyMedium)
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            val draft = state.draft
            if (draft == null) {
                if (state.error == null) CircularProgressIndicator()
                else TextButton(onClick = onRetry) { Text(stringResource(R.string.task_retry)) }
            } else {
                OutlinedTextField(draft.outputFolder, { onChange(draft.copy(outputFolder = it)) },
                    label = { Text(stringResource(R.string.task_output_folder)) }, enabled = !state.isSaving, modifier = Modifier.fillMaxWidth())
                draft.url?.let { OptionText(it, R.string.task_detail_url, !state.isSaving) { value -> onChange(draft.copy(url = value)) } }
                draft.headers?.let { OptionText(it, R.string.task_headers, !state.isSaving) { value -> onChange(draft.copy(headers = value)) } }
                draft.connections?.let { OptionText(it, R.string.task_connections, !state.isSaving) { value -> onChange(draft.copy(connections = value)) } }
                draft.clientProfile?.let { OptionText(it, R.string.task_client_profile, !state.isSaving) { value -> onChange(draft.copy(clientProfile = value)) } }
                draft.userAgent?.let { OptionText(it, R.string.task_user_agent, !state.isSaving) { value -> onChange(draft.copy(userAgent = value)) } }
                draft.recordLimit?.let { OptionText(it, R.string.task_record_limit, !state.isSaving) { value -> onChange(draft.copy(recordLimit = value)) } }
                draft.decryptionKeys?.let { OptionText(it, R.string.task_decryption_keys, !state.isSaving) { value -> onChange(draft.copy(decryptionKeys = value)) } }
                draft.decryptionKeyFile?.let { OptionText(it, R.string.task_key_file, !state.isSaving) { value -> onChange(draft.copy(decryptionKeyFile = value)) } }
                draft.muxImports?.let { OptionText(it, R.string.task_mux_imports, !state.isSaving) { value -> onChange(draft.copy(muxImports = value)) } }
                Button(onClick = onSave, enabled = state.hasChanges && !state.isSaving, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.task_apply_start))
                }
                if (state.isSaving) LinearProgressIndicator(Modifier.fillMaxWidth())
            }
        }
    }
    if (shouldDiscard) DiscardTaskChanges(onDismiss = { shouldDiscard = false }, onDiscard = onBack)
}

@Composable
private fun OptionText(value: String, label: Int, isEnabled: Boolean, onChange: (String) -> Unit) {
    OutlinedTextField(value, onChange, label = { Text(stringResource(label)) }, enabled = isEnabled,
        modifier = Modifier.fillMaxWidth())
}
