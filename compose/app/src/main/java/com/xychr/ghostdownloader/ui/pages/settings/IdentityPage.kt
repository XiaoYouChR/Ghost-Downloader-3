package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.clientProfileLabel
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.ui.navigation.ClientProfileRoute
import com.xychr.ghostdownloader.ui.navigation.HeadersPresetsRoute
import com.xychr.ghostdownloader.ui.navigation.IdentityRulesRoute
import com.xychr.ghostdownloader.ui.navigation.Route

@Composable
fun IdentityPage(onNavigate: (Route) -> Unit, onBack: () -> Unit,
    modifier: Modifier = Modifier, viewModel: IdentityViewModel) {
    val uiState by viewModel.state.collectAsStateWithLifecycle()
    val state = uiState?.identity
    SettingsScaffold(stringResource(R.string.identity_title), onBack, modifier) {
        if (state == null) { LoadingRow(); return@SettingsScaffold }
        SettingSection {
            ActionSettingRow(stringResource(R.string.identity_default_profile),
                subtitle = clientProfileLabel(state.clientProfile),
                onClick = { onNavigate(ClientProfileRoute) })
            ActionSettingRow(stringResource(R.string.identity_rules),
                subtitle = stringResource(R.string.identity_rules_summary,
                    state.identityPresets.size, state.identityPresets.count { it.isEnabled }),
                onClick = { onNavigate(IdentityRulesRoute) })
            val active = state.headersPresets.getOrNull(state.currentHeadersPreset)
            ActionSettingRow(stringResource(R.string.identity_headers_presets),
                subtitle = active?.let { stringResource(R.string.identity_headers_summary, it.name, it.headers.size) },
                onClick = { onNavigate(HeadersPresetsRoute) })
        }
    }
}
