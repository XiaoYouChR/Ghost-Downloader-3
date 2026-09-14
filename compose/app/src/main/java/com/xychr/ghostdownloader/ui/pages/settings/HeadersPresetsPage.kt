package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.ui.navigation.HeadersPresetEditRoute
import com.xychr.ghostdownloader.ui.navigation.Route

@Composable
fun HeadersPresetsPage(onNavigate: (Route) -> Unit, onBack: () -> Unit,
    modifier: Modifier = Modifier, viewModel: IdentityViewModel, focusIndex: Int = -1, onFocusConsumed: () -> Unit = {}) {
    val uiState by viewModel.state.collectAsStateWithLifecycle()
    val isBusy by viewModel.isBusy.collectAsStateWithLifecycle()
    val state = uiState?.identity
    var removing by remember { mutableStateOf<HeadersPreset?>(null) }
    var removingIndex by remember { mutableIntStateOf(-1) }
    SettingsScaffold(stringResource(R.string.identity_headers_presets), onBack, modifier) {
        if (state == null) { LoadingRow(); return@SettingsScaffold }
        if (isBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
        SettingSection(description = stringResource(R.string.identity_headers_presets_desc), modifier = Modifier.selectableGroup()) {
            state.headersPresets.forEachIndexed { index, preset ->
                var isMenuOpen by remember(preset) { mutableStateOf(false) }
                val bringIntoView = remember { BringIntoViewRequester() }
                LaunchedEffect(focusIndex) {
                    if (focusIndex == index) {
                        withFrameNanos { }
                        bringIntoView.bringIntoView()
                        onFocusConsumed()
                    }
                }
                ActionSettingRow(title = preset.name,
                    subtitle = stringResource(R.string.identity_headers_count, preset.headers.size),
                    onClick = { if (!isBusy) viewModel.setActiveHeadersPreset(index) },
                    modifier = Modifier.bringIntoViewRequester(bringIntoView).semantics {
                        role = Role.RadioButton; selected = index == state.currentHeadersPreset
                    },
                    leading = { RadioButton(index == state.currentHeadersPreset, null, enabled = !isBusy) },
                    trailing = {
                        Row {
                            IconButton(onClick = { onNavigate(HeadersPresetEditRoute(index)) }, enabled = !isBusy) {
                                Icon(painterResource(R.drawable.ic_edit), stringResource(R.string.identity_headers_preset_edit) + " " + preset.name)
                            }
                            Box {
                                IconButton(onClick = { isMenuOpen = true }, enabled = !isBusy) {
                                    Icon(painterResource(R.drawable.ic_more_vert), stringResource(R.string.settings_more_for, preset.name))
                                }
                                DropdownMenu(isMenuOpen, { isMenuOpen = false }) {
                                    DropdownMenuItem(text = { Text(stringResource(R.string.settings_copy)) },
                                        onClick = { isMenuOpen = false; onNavigate(HeadersPresetEditRoute(copyFrom = index)) })
                                    DropdownMenuItem(text = { Text(stringResource(R.string.settings_delete)) }, enabled = state.headersPresets.size > 1,
                                        onClick = { isMenuOpen = false; removing = preset; removingIndex = index })
                                }
                            }
                        }
                    })
            }
        }
        if (state.headersPresets.size == 1) Text(stringResource(R.string.identity_last_preset),
            Modifier.padding(horizontal = 32.dp), style = MaterialTheme.typography.bodySmall)
        SettingSection {
            ActionSettingRow(stringResource(R.string.identity_headers_preset_add),
                onClick = { if (!isBusy) onNavigate(HeadersPresetEditRoute()) })
        }
    }
    removing?.let { preset ->
        val presets = state?.headersPresets ?: return@let
        val index = removingIndex.takeIf { presets.getOrNull(it) == preset } ?: -1
        val replacement = presets.filterIndexed { i, _ -> i != index }.firstOrNull()
        AlertDialog(onDismissRequest = { removing = null }, title = { Text(stringResource(R.string.identity_headers_preset_remove_title)) },
            text = { Text(stringResource(R.string.identity_headers_preset_remove_message, preset.name) +
                if (index == state.currentHeadersPreset && replacement != null)
                    "\n" + stringResource(R.string.identity_delete_active, replacement.name) else "") },
            confirmButton = {
                TextButton(enabled = index >= 0 && replacement != null && !isBusy,
                    onClick = { removing = null; viewModel.removeHeadersPreset(index) }) { Text(stringResource(R.string.settings_delete)) }
            }, dismissButton = {
                TextButton(onClick = { removing = null }) { Text(stringResource(R.string.action_cancel)) }
            })
    }
}
