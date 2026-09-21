package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.AppearanceSections
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold

@Composable
fun AppearancePage(onBack: () -> Unit) {
    SettingsScaffold(stringResource(R.string.settings_section_appearance), onBack) {
        AppearanceSections()
    }
}
