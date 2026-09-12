package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.runtime.remember
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsEdit
import com.xychr.ghostdownloader.ui.components.settings.SettingsEditor
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.ui.components.settings.matchHeaderValue

@Composable
fun IdentityPresetEditPage(
    index: Int,
    onBack: () -> Unit,
    viewModel: IdentityViewModel,
    edit: SettingsEdit = viewModel(),
) {
    val uiState by viewModel.state.collectAsStateWithLifecycle()
    val editState by edit.state.collectAsStateWithLifecycle()
    val isCreating = index < 0
    val identityState = uiState
    if (identityState == null) {
        SettingsPage(stringResource(R.string.identity_rule_edit), onBack) { LoadingRow() }
        return
    }
    val existing = identityState.identity.identityPresets.getOrNull(index)
    if (!isCreating && existing == null) {
        SettingsPage(stringResource(R.string.identity_rule_edit), onBack) { LoadingRow() }
        return
    }

    var name by rememberSaveable(index) { mutableStateOf(existing?.name.orEmpty()) }
    var profile by rememberSaveable(index) {
        mutableStateOf(existing?.clientProfile.orEmpty())
    }
    var userAgent by rememberSaveable(index) { mutableStateOf(existing?.userAgent.orEmpty()) }
    var hosts by rememberSaveable(index) {
        mutableStateOf(existing?.hosts?.joinToString("\n").orEmpty())
    }
    var shouldValidate by rememberSaveable { mutableStateOf(false) }
    val nameFocus = remember { FocusRequester() }
    val hostsFocus = remember { FocusRequester() }
    val hasValidHosts = hosts.toHostList().isNotEmpty() && hosts.toHostList().all(::matchIdentityHost)

    val preset = IdentityPreset(
        name = name.trim(), clientProfile = profile, userAgent = userAgent.trim(),
        hosts = hosts.toHostList(), isEnabled = existing?.isEnabled ?: true,
    )
    SettingsEditor(
        title = stringResource(
            if (isCreating) R.string.identity_rule_add else R.string.identity_rule_edit
        ),
        onBack = onBack,
        state = editState,
        canSubmitUnchanged = isCreating,
        isChanged = preset != (existing ?: IdentityPreset()),
        canSave = name.isNotBlank() && hasValidHosts && matchClientProfile(profile, identityState.profiles, canInherit = true) && matchHeaderValue(userAgent),
        onInvalid = {
            shouldValidate = true
            if (name.isBlank()) nameFocus.requestFocus() else hostsFocus.requestFocus()
        },
        onSave = {
            edit.save {
                if (isCreating) viewModel.addIdentityPreset(preset)
                else viewModel.updateIdentityPreset(index, preset)
            }
        },
    ) {
        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text(stringResource(R.string.identity_rule_name)) },
            singleLine = true,
            enabled = !editState.isSaving,
            isError = shouldValidate && name.isBlank(),
            supportingText = { if (shouldValidate && name.isBlank()) Text(stringResource(R.string.settings_name_required)) },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp).focusRequester(nameFocus),
        )
        SettingSection {
            ClientProfileRow(
                value = profile,
                profiles = identityState.profiles,
                onSelect = { profile = it },
                canInherit = true,
                isEnabled = !editState.isSaving,
                globalProfile = identityState.identity.clientProfile,
            )
        }
        OutlinedTextField(
            value = userAgent,
            isError = shouldValidate && !matchHeaderValue(userAgent),
            enabled = !editState.isSaving,
            onValueChange = { userAgent = it },
            label = { Text(stringResource(R.string.identity_user_agent)) },
            supportingText = { Text(stringResource(R.string.identity_user_agent_desc)) },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        )
        OutlinedTextField(
            value = hosts,
            enabled = !editState.isSaving,
            onValueChange = { hosts = it },
            label = { Text(stringResource(R.string.identity_hosts)) },
            placeholder = { Text("*.example.com") },
            isError = shouldValidate && !hasValidHosts,
            supportingText = { Text(stringResource(
                if (shouldValidate && !hasValidHosts) R.string.identity_hosts_invalid else R.string.identity_hosts_desc,
            )) },
            minLines = 3,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp).focusRequester(hostsFocus),
        )
    }
}

private fun matchIdentityHost(value: String): Boolean {
    val host = value.removePrefix("*.")
    return host.isNotEmpty() && host.none { it.isWhitespace() || it in "*/:#?@\\" } &&
        host.split('.').all { it.isNotEmpty() && !it.startsWith('-') && !it.endsWith('-') }
}

private fun String.toHostList(): List<String> =
    lines().map(String::trim).filter(String::isNotEmpty)
