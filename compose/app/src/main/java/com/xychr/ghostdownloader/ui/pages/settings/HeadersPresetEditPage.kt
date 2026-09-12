package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.HeaderEntry
import com.xychr.ghostdownloader.ui.components.settings.HeaderImportError
import com.xychr.ghostdownloader.ui.components.settings.InfoSettingRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsEdit
import com.xychr.ghostdownloader.ui.components.settings.SettingsEditState
import com.xychr.ghostdownloader.ui.components.settings.SettingsEditor
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.ui.components.settings.buildMergedHeaders
import com.xychr.ghostdownloader.ui.components.settings.matchHeaderEntries
import com.xychr.ghostdownloader.ui.components.settings.matchHeaderName
import com.xychr.ghostdownloader.ui.components.settings.matchHeaderValue
import com.xychr.ghostdownloader.ui.components.settings.parseHeaderImport
import com.xychr.ghostdownloader.ui.components.settings.parseHeaderText
import com.xychr.ghostdownloader.ui.components.settings.toHeaderText
import kotlinx.coroutines.launch
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

private data class HeaderLine(val id: Int, val name: String, val value: String)

@Composable
fun HeadersPresetEditPage(index: Int, onBack: () -> Unit, viewModel: IdentityViewModel,
    modifier: Modifier = Modifier, copyFrom: Int = -1, onSaved: (Int) -> Unit = {},
    edit: SettingsEdit = viewModel()) {
    val uiState by viewModel.state.collectAsStateWithLifecycle()
    val editState by edit.state.collectAsStateWithLifecycle()
    val identityState = uiState
    if (identityState == null) {
        SettingsPage(stringResource(R.string.identity_headers_preset_edit), onBack, modifier) { LoadingRow() }
        return
    }
    val state = identityState.identity
    val defaults = identityState.defaultHeaders
    val existing = state.headersPresets.getOrNull(index)
    val source = state.headersPresets.getOrNull(copyFrom)
    if ((index >= 0 && existing == null) || (copyFrom >= 0 && source == null)) {
        SettingsPage(stringResource(R.string.identity_headers_preset_edit), onBack, modifier) { LoadingRow() }
        return
    }
    val initial = existing ?: HeadersPreset(
        name = source?.let { stringResource(R.string.settings_copy_name, it.name) }.orEmpty(),
        headers = source?.headers ?: state.headersPresets.getOrNull(state.currentHeadersPreset)?.headers.orEmpty(),
    )
    HeadersForm(initial, defaults, index < 0, index == state.currentHeadersPreset, editState,
        onSave = { preset -> edit.save {
            if (index < 0) viewModel.addHeadersPreset(preset) else viewModel.updateHeadersPreset(index, preset)
        } }, onBack = {
            if (editState.isSaved) onSaved(if (index < 0) state.headersPresets.size else index)
            onBack()
        }, modifier = modifier)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HeadersForm(initial: HeadersPreset, defaults: Map<String, String>, isCreating: Boolean, isActive: Boolean,
    state: SettingsEditState, onSave: (HeadersPreset) -> Unit, onBack: () -> Unit, modifier: Modifier = Modifier) {
    var name by rememberSaveable { mutableStateOf(initial.name) }
    var nextId by rememberSaveable { mutableIntStateOf(initial.headers.size) }
    var lines by rememberSaveable(stateSaver = listSaver<List<HeaderLine>, String>(
        save = { it.flatMap { row -> listOf(row.id.toString(), row.name, row.value) } },
        restore = { it.chunked(3).map { row -> HeaderLine(row[0].toInt(), row[1], row[2]) } },
    )) { mutableStateOf(initial.headers.entries.mapIndexed { id, entry -> HeaderLine(id, entry.key, entry.value) }) }
    var isTextMode by rememberSaveable { mutableStateOf(false) }
    var raw by rememberSaveable { mutableStateOf(toHeaderText(initial.headers.map { HeaderEntry(it.key, it.value) })) }
    var fieldsSource by rememberSaveable { mutableStateOf(raw) }
    var shouldValidate by rememberSaveable { mutableStateOf(false) }
    var isImporting by rememberSaveable { mutableStateOf(false) }
    var isMenuOpen by remember { mutableStateOf(false) }
    var focusId by remember { mutableIntStateOf(-1) }
    val nameFocus = remember { FocusRequester() }
    val textFocus = remember { FocusRequester() }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val parsed = remember(raw) { parseHeaderText(raw) }
    val entries = if (isTextMode) parsed.entries else lines.map { HeaderEntry(it.name, it.value) }
    val isValid = if (isTextMode) parsed.isValid else matchHeaderEntries(entries)
    val isChanged = name != initial.name ||
        if (isTextMode) raw != toHeaderText(initial.headers.map { HeaderEntry(it.key, it.value) })
        else entries != initial.headers.map { HeaderEntry(it.key, it.value) }
    val switchError = stringResource(R.string.headers_switch_invalid)
    val undoLabel = stringResource(R.string.settings_undo)
    val removedText = stringResource(R.string.headers_removed)
    val restoredText = stringResource(R.string.headers_restored)
    val importedText = stringResource(R.string.headers_import_applied)
    val isSaving by rememberUpdatedState(state.isSaving)

    SettingsEditor(
        title = stringResource(if (isCreating) R.string.identity_headers_preset_add else R.string.identity_headers_preset_edit),
        state = state, isChanged = isChanged, canSave = name.isNotBlank() && isValid,
        canSubmitUnchanged = isCreating,
        onInvalid = {
            shouldValidate = true
            if (name.isBlank()) nameFocus.requestFocus()
            else if (isTextMode) textFocus.requestFocus()
            else focusId = lines.firstOrNull { line ->
                !matchHeaderName(line.name) || !matchHeaderValue(line.value) ||
                    lines.count { it.name.trim().equals(line.name.trim(), true) } > 1
            }?.id ?: -1
        },
        onSave = {
            snackbar.currentSnackbarData?.dismiss()
            onSave(HeadersPreset(name.trim(), entries.associate { it.name.trim() to it.value.trim() }))
        },
        onBack = onBack, modifier = modifier, snackbarHost = { SnackbarHost(snackbar) },
        actions = {
            Box {
                IconButton(onClick = { isMenuOpen = true }, enabled = !state.isSaving) {
                    Icon(painterResource(R.drawable.ic_more_vert), stringResource(R.string.settings_more_for, name))
                }
                DropdownMenu(isMenuOpen, { isMenuOpen = false }) {
                    DropdownMenuItem(text = { Text(stringResource(R.string.headers_restore)) }, onClick = {
                        isMenuOpen = false
                        snackbar.currentSnackbarData?.dismiss()
                        val previousLines = lines
                        val previousRaw = raw
                        lines = defaults.map { HeaderLine(nextId++, it.key, it.value) }
                        raw = toHeaderText(defaults.map { HeaderEntry(it.key, it.value) })
                        val restoredLines = lines
                        val restoredRaw = raw
                        scope.launch {
                            if (snackbar.showSnackbar(restoredText, undoLabel) == SnackbarResult.ActionPerformed &&
                                !isSaving && lines == restoredLines && raw == restoredRaw) {
                                lines = previousLines; raw = previousRaw
                            }
                        }
                    })
                }
            }
        },
    ) {
        OutlinedTextField(name, { name = it }, label = { Text(stringResource(R.string.identity_headers_preset_name)) },
            singleLine = true, enabled = !state.isSaving, isError = shouldValidate && name.isBlank(),
            supportingText = { if (shouldValidate && name.isBlank()) Text(stringResource(R.string.settings_name_required)) },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp).focusRequester(nameFocus))
        Text(stringResource(if (isActive && !isCreating) R.string.identity_active_edit else R.string.identity_saved_inactive),
            Modifier.padding(horizontal = 16.dp), style = MaterialTheme.typography.bodySmall)
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
            listOf(R.string.headers_mode_fields, R.string.headers_mode_text).forEachIndexed { index, label ->
                SegmentedButton(selected = isTextMode == (index == 1), enabled = !state.isSaving,
                    shape = SegmentedButtonDefaults.itemShape(index, 2), label = { Text(stringResource(label)) },
                    onClick = {
                        if (isTextMode == (index == 1)) return@SegmentedButton
                        snackbar.currentSnackbarData?.dismiss()
                        if (!isValid) {
                            shouldValidate = true
                            scope.launch { snackbar.showSnackbar(switchError) }
                        } else {
                            if (index == 1) {
                                raw = if (parseHeaderText(fieldsSource).entries == entries) fieldsSource else toHeaderText(entries)
                            } else {
                                fieldsSource = raw
                                lines = entries.map { HeaderLine(nextId++, it.name, it.value) }
                            }
                            isTextMode = index == 1
                        }
                    })
            }
        }
        TextButton(enabled = !state.isSaving, onClick = {
            if (isValid) isImporting = true
            else { shouldValidate = true; scope.launch { snackbar.showSnackbar(switchError) } }
        }, modifier = Modifier.padding(horizontal = 8.dp)) { Text(stringResource(R.string.headers_import)) }
        if (isTextMode) {
            OutlinedTextField(raw, { raw = it; snackbar.currentSnackbarData?.dismiss() }, enabled = !state.isSaving,
                label = { Text(stringResource(R.string.headers_text_label)) }, minLines = 8,
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
                isError = shouldValidate && !parsed.isValid,
                supportingText = {
                    Text(if (shouldValidate && !parsed.isValid) stringResource(R.string.headers_invalid_lines,
                        parsed.invalidLines.joinToString(", ")) else stringResource(R.string.headers_text_hint))
                }, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp).focusRequester(textFocus))
        } else {
            lines.forEach { line -> key(line.id) {
                val duplicate = lines.count { it.name.trim().equals(line.name.trim(), true) } > 1
                HeaderFields(line.name, line.value, shouldValidate, duplicate, focusId == line.id, !state.isSaving,
                    onName = { value ->
                        snackbar.currentSnackbarData?.dismiss()
                        lines = lines.map { if (it.id == line.id) it.copy(name = value) else it }
                    },
                    onValue = { value ->
                        snackbar.currentSnackbarData?.dismiss()
                        lines = lines.map { if (it.id == line.id) it.copy(value = value) else it }
                    },
                    onFocused = { focusId = -1 },
                    onRemove = {
                        snackbar.currentSnackbarData?.dismiss()
                        val position = lines.indexOf(line)
                        lines = lines.filterNot { it.id == line.id }
                        scope.launch {
                            if (snackbar.showSnackbar(removedText, undoLabel) == SnackbarResult.ActionPerformed &&
                                !isSaving && lines.none { it.id == line.id }) {
                                lines = lines.toMutableList().apply { add(position.coerceAtMost(size), line) }
                            }
                        }
                    })
            } }
            TextButton(enabled = !state.isSaving, onClick = {
                snackbar.currentSnackbarData?.dismiss()
                val id = nextId++; lines = lines + HeaderLine(id, "", ""); focusId = id
            }, modifier = Modifier.padding(horizontal = 8.dp)) { Text(stringResource(R.string.identity_header_add)) }
        }
    }
    if (isImporting) HeaderImportDialog(entries, onBack = { isImporting = false }, onApply = { imported ->
        snackbar.currentSnackbarData?.dismiss()
        val merged = buildMergedHeaders(entries, imported)
        lines = merged.map { HeaderLine(nextId++, it.name, it.value) }
        raw = toHeaderText(merged)
        isImporting = false
        scope.launch { snackbar.showSnackbar(importedText) }
    })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HeaderFields(name: String, value: String, shouldValidate: Boolean, isDuplicate: Boolean,
    shouldFocus: Boolean, isEnabled: Boolean, onName: (String) -> Unit, onValue: (String) -> Unit,
    onFocused: () -> Unit, onRemove: () -> Unit) {
    val focus = remember { FocusRequester() }
    var isSuggesting by remember { mutableStateOf(false) }
    val suggestions = listOf("Accept", "Accept-Encoding", "Accept-Language", "Authorization", "Cache-Control",
        "Cookie", "Origin", "Referer", "User-Agent", "Range").filter { it.contains(name, true) && !it.equals(name, true) }
    LaunchedEffect(shouldFocus) { if (shouldFocus) { focus.requestFocus(); onFocused() } }
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            ExposedDropdownMenuBox(isSuggesting && suggestions.isNotEmpty(), { isSuggesting = it }) {
                OutlinedTextField(name, { onName(it); isSuggesting = true }, enabled = isEnabled,
                    label = { Text(stringResource(R.string.identity_header_name)) }, singleLine = true,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
                    isError = shouldValidate && (!matchHeaderName(name) || isDuplicate),
                    supportingText = {
                        if (shouldValidate && !matchHeaderName(name)) Text(stringResource(R.string.headers_name_invalid))
                        else if (shouldValidate && isDuplicate) Text(stringResource(R.string.headers_duplicate))
                    }, modifier = Modifier.fillMaxWidth().focusRequester(focus)
                        .menuAnchor(ExposedDropdownMenuAnchorType.PrimaryEditable))
                ExposedDropdownMenu(isSuggesting && suggestions.isNotEmpty() && isEnabled, { isSuggesting = false }) {
                    suggestions.forEach { suggestion -> DropdownMenuItem(text = { Text(suggestion) },
                        onClick = { onName(suggestion); isSuggesting = false }) }
                }
            }
            OutlinedTextField(value, onValue, enabled = isEnabled, label = { Text(stringResource(R.string.identity_header_value)) },
                isError = shouldValidate && !matchHeaderValue(value),
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
                supportingText = { if (shouldValidate && !matchHeaderValue(value)) Text(stringResource(R.string.headers_value_invalid)) },
                modifier = Modifier.fillMaxWidth())
        }
        IconButton(onClick = onRemove, enabled = isEnabled) {
            Icon(painterResource(R.drawable.ic_close), stringResource(R.string.settings_delete) + " " + name)
        }
    }
}

@Composable
fun HeaderImportDialog(current: List<HeaderEntry>, onApply: (List<HeaderEntry>) -> Unit, onBack: () -> Unit,
    modifier: Modifier = Modifier) {
    Dialog(onDismissRequest = onBack,
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnBackPress = false,
            dismissOnClickOutside = false, decorFitsSystemWindows = false)) {
        HeaderImportForm(current, onApply, onBack, modifier.fillMaxSize())
    }
}

@Composable
fun HeaderImportForm(current: List<HeaderEntry>, onApply: (List<HeaderEntry>) -> Unit, onBack: () -> Unit,
    modifier: Modifier = Modifier) {
    var source by rememberSaveable { mutableStateOf("") }
    var shouldPreview by rememberSaveable { mutableStateOf(false) }
    val result = remember(source, shouldPreview) { if (shouldPreview) parseHeaderImport(source) else null }
    val conflicts = result?.entries?.count { incoming -> current.any { it.name.trim().equals(incoming.name.trim(), true) } } ?: 0
    SettingsEditor(stringResource(R.string.headers_import), SettingsEditState(), source.isNotBlank(),
        canSave = result != null && result.error == null,
        onSave = { onApply(result!!.entries) }, onBack = onBack, modifier = modifier,
        saveLabel = stringResource(if (conflicts > 0) R.string.headers_import_replace else R.string.headers_import_apply),
        onInvalid = { shouldPreview = true }) {
        OutlinedTextField(source, { source = it; shouldPreview = false },
            label = { Text(stringResource(R.string.headers_import_source)) }, minLines = 6,
            isError = result?.error != null,
            supportingText = {
                Text(stringResource(when (result?.error) {
                    HeaderImportError.QUOTES -> R.string.headers_import_quotes
                    HeaderImportError.MULTIPLE_REQUESTS -> R.string.headers_import_multiple
                    HeaderImportError.FILE_INPUT -> R.string.headers_import_file
                    HeaderImportError.INVALID_HEADERS -> R.string.headers_import_invalid
                    HeaderImportError.EMPTY -> R.string.headers_import_empty
                    null -> R.string.headers_import_help
                }))
            }, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp))
        TextButton(enabled = source.isNotBlank(), onClick = { shouldPreview = true },
            modifier = Modifier.padding(horizontal = 8.dp)) { Text(stringResource(R.string.headers_import_preview)) }
        if (result != null && result.error == null) {
            Text(stringResource(R.string.headers_import_count, result.entries.size, conflicts), Modifier.padding(horizontal = 16.dp))
            Text(stringResource(R.string.headers_import_sensitive), Modifier.padding(horizontal = 16.dp),
                style = MaterialTheme.typography.bodySmall)
            SettingSection {
                result.entries.forEach { InfoSettingRow(it.name) }
            }
        }
    }
}
