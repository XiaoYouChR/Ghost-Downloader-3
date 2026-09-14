package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.EmptyRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.ui.navigation.IdentityPresetEditRoute
import com.xychr.ghostdownloader.ui.navigation.Route

@Composable
fun IdentityRulesPage(onNavigate: (Route) -> Unit, onBack: () -> Unit,
    modifier: Modifier = Modifier, viewModel: IdentityViewModel) {
    val uiState by viewModel.state.collectAsStateWithLifecycle()
    val isBusy by viewModel.isBusy.collectAsStateWithLifecycle()
    val state = uiState?.identity
    var removing by remember { mutableStateOf<IdentityPreset?>(null) }
    SettingsScaffold(stringResource(R.string.identity_rules), onBack, modifier) {
        if (state == null) { LoadingRow(); return@SettingsScaffold }
        if (isBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
        SettingSection(description = stringResource(R.string.identity_rules_desc)) {
            state.identityPresets.forEachIndexed { index, preset ->
                var isMenuOpen by remember(preset) { mutableStateOf(false) }
                val switchLabel = stringResource(R.string.identity_enabled_for, preset.name)
                ActionSettingRow(title = preset.name,
                    subtitle = stringResource(R.string.identity_rule_position, index + 1, preset.hosts.joinToString(", ")),
                    onClick = { if (!isBusy) onNavigate(IdentityPresetEditRoute(index)) },
                    trailing = {
                        Row {
                            Switch(preset.isEnabled, { viewModel.setIdentityEnabled(index, it) }, enabled = !isBusy,
                                modifier = Modifier.semantics { contentDescription = switchLabel })
                            Box {
                                IconButton(onClick = { isMenuOpen = true }, enabled = !isBusy) {
                                    Icon(painterResource(R.drawable.ic_more_vert), stringResource(R.string.settings_more_for, preset.name))
                                }
                                DropdownMenu(isMenuOpen, { isMenuOpen = false }) {
                                    DropdownMenuItem(text = { Text(stringResource(R.string.settings_move_up)) }, enabled = index > 0,
                                        onClick = { isMenuOpen = false; viewModel.setIdentityOrder(index, index - 1) })
                                    DropdownMenuItem(text = { Text(stringResource(R.string.settings_move_down)) },
                                        enabled = index < state.identityPresets.lastIndex,
                                        onClick = { isMenuOpen = false; viewModel.setIdentityOrder(index, index + 1) })
                                    DropdownMenuItem(text = { Text(stringResource(R.string.settings_delete)) },
                                        onClick = { isMenuOpen = false; removing = preset })
                                }
                            }
                        }
                    })
            }
            if (state.identityPresets.isEmpty()) EmptyRow(stringResource(R.string.identity_rules_empty))
            ActionSettingRow(stringResource(R.string.identity_rule_add),
                onClick = { if (!isBusy) onNavigate(IdentityPresetEditRoute()) })
        }
    }
    removing?.let { preset ->
        val index = state?.identityPresets?.indexOf(preset) ?: -1
        AlertDialog(onDismissRequest = { removing = null }, title = { Text(stringResource(R.string.identity_rule_remove_title)) },
            text = { Text(stringResource(R.string.identity_rule_remove_message, preset.name)) },
            confirmButton = {
                TextButton(enabled = index >= 0 && !isBusy, onClick = { removing = null; viewModel.removeIdentityPreset(index) }) {
                    Text(stringResource(R.string.settings_delete))
                }
            }, dismissButton = {
                TextButton(onClick = { removing = null }) { Text(stringResource(R.string.action_cancel)) }
            })
    }
}
