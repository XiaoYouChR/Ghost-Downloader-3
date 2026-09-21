package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.RuntimeRows
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold

@Composable
fun RuntimesPage(onBack: () -> Unit) {
    SettingsScaffold(stringResource(R.string.settings_section_runtimes), onBack) {
        SettingSection { RuntimeRows() }
    }
}
