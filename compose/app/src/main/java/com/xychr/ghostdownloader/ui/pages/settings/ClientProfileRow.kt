package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingsEdit
import com.xychr.ghostdownloader.ui.components.settings.SettingsEditor
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChoiceField(label: String, value: String, options: List<Pair<String, String>>, onSelect: (String) -> Unit,
    modifier: Modifier = Modifier, isEnabled: Boolean = true) {
    var isExpanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(isExpanded && isEnabled, { if (isEnabled) isExpanded = it }, modifier) {
        OutlinedTextField(value = options.firstOrNull { it.first == value }?.second ?: value,
            onValueChange = {}, readOnly = true, enabled = isEnabled, label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(isExpanded) },
            modifier = Modifier.menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable, enabled = isEnabled).fillMaxWidth())
        ExposedDropdownMenu(isExpanded && isEnabled, { isExpanded = false }) {
            options.forEach { (key, text) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { isExpanded = false; onSelect(key) })
            }
        }
    }
}

@Composable
fun ClientProfileRow(value: String, profiles: List<ClientProfiles>, onSelect: (String) -> Unit,
    modifier: Modifier = Modifier, canInherit: Boolean = false, isEnabled: Boolean = true,
    globalProfile: String = "auto") {
    val family = profiles.firstOrNull { it.family == value || value in it.versions }
    val isCustom = value !in listOf("", "auto", "raw")
    var customValue by rememberSaveable { mutableStateOf(if (isCustom) value else profiles.firstOrNull()?.family.orEmpty()) }
    LaunchedEffect(value) { if (isCustom) customValue = value }
    val choices = buildList {
        if (canInherit) add("" to stringResource(R.string.identity_profile_inherit))
        add("auto" to stringResource(R.string.identity_profile_auto))
        add("raw" to stringResource(R.string.identity_profile_raw))
        if (profiles.isNotEmpty()) add("custom" to stringResource(R.string.identity_profile_custom))
    }
    Column(modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ChoiceField(stringResource(R.string.identity_client_profile), if (isCustom) "custom" else value,
            choices, { onSelect(if (it == "custom") customValue.ifEmpty { profiles.first().family } else it) },
            isEnabled = isEnabled)
        if (value.isEmpty() && canInherit) Text(stringResource(R.string.identity_profile_current_global,
            clientProfileLabel(globalProfile)), style = MaterialTheme.typography.bodySmall)
        if (isCustom) {
            ChoiceField(stringResource(R.string.identity_profile_family), family?.family ?: value,
                profiles.map { it.family to toProfileFamilyLabel(it.family) }, onSelect, isEnabled = isEnabled)
            if (family != null) ChoiceField(stringResource(R.string.identity_profile_version), value,
                listOf(family.family to stringResource(R.string.identity_profile_latest, toProfileFamilyLabel(family.family))) +
                    family.versions.map { it to toProfileVersionLabel(it) }, onSelect, isEnabled = isEnabled)
            else Text(stringResource(R.string.identity_profile_unsupported), color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
fun ClientProfilePage(onBack: () -> Unit, viewModel: IdentityViewModel, modifier: Modifier = Modifier,
    edit: SettingsEdit = viewModel()) {
    val uiState by viewModel.state.collectAsStateWithLifecycle()
    val editState by edit.state.collectAsStateWithLifecycle()
    val identityState = uiState
    if (identityState == null) {
        SettingsPage(stringResource(R.string.identity_profile_choose), onBack, modifier) { LoadingRow() }
        return
    }
    var value by rememberSaveable { mutableStateOf(identityState.identity.clientProfile) }
    SettingsEditor(stringResource(R.string.identity_profile_choose), editState,
        isChanged = value != identityState.identity.clientProfile, canSave = matchClientProfile(value, identityState.profiles),
        onSave = { val selected = value; edit.save { viewModel.setClientProfile(selected) } }, onBack = onBack,
        modifier = modifier) {
        ClientProfileRow(value, identityState.profiles, { value = it }, isEnabled = !editState.isSaving)
    }
}

fun matchClientProfile(value: String, profiles: List<ClientProfiles>, canInherit: Boolean = false): Boolean =
    (canInherit && value.isEmpty()) || value in listOf("auto", "raw") || profiles.any { it.family == value || value in it.versions }

@Composable
fun clientProfileLabel(value: String): String = when (value) {
    "" -> stringResource(R.string.identity_profile_inherit)
    "auto" -> stringResource(R.string.identity_profile_auto)
    "raw" -> stringResource(R.string.identity_profile_raw)
    else -> if (value.any(Char::isDigit)) toProfileVersionLabel(value)
        else stringResource(R.string.identity_profile_latest, toProfileFamilyLabel(value))
}

private fun toProfileVersionLabel(value: String): String =
    value.replace(Regex("(?<=[A-Za-z])(?=\\d)"), " ").replace('_', '.')

private fun toProfileFamilyLabel(family: String): String = when (family) {
    "chrome" -> "Chrome"
    "edge" -> "Edge"
    "firefox" -> "Firefox"
    "firefox-android" -> "Firefox Android"
    "opera" -> "Opera"
    "safari" -> "Safari"
    "safari-ios" -> "Safari iOS"
    "safari-ipad" -> "Safari iPad"
    "okhttp" -> "OkHttp"
    else -> family
}
