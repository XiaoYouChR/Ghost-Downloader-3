package com.xychr.ghostdownloader.ui.pages.settings

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeFlexibleTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SearchBar
import androidx.compose.material3.ExpandedFullScreenSearchBar
import androidx.compose.material3.SearchBarValue
import androidx.compose.material3.rememberSearchBarState
import androidx.compose.foundation.text.input.rememberTextFieldState
import androidx.compose.material3.SearchBarDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.EmptyRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SearchResults
import com.xychr.ghostdownloader.ui.components.settings.rememberSearchResults
import com.xychr.ghostdownloader.ui.navigation.*

private data class SettingsCategory(
    @StringRes val titleRes: Int,
    @StringRes val summaryRes: Int,
    @DrawableRes val iconRes: Int,
    val route: Route,
)

private data class SettingsGroup(
    @StringRes val titleRes: Int,
    val categories: List<SettingsCategory>,
)

private val settingsGroups = listOf(
    SettingsGroup(
        R.string.settings_group_download,
        listOf(
            SettingsCategory(R.string.settings_section_download, R.string.settings_summary_download, R.drawable.ic_download, DownloadSettingsRoute),
            SettingsCategory(R.string.settings_section_network, R.string.settings_summary_network, R.drawable.ic_network, NetworkSettingsRoute),
            SettingsCategory(R.string.settings_section_identity, R.string.settings_summary_identity, R.drawable.ic_account_box, IdentitySettingsRoute),
        ),
    ),
    SettingsGroup(
        R.string.settings_group_features,
        listOf(
            SettingsCategory(R.string.settings_section_packs, R.string.settings_summary_packs, R.drawable.ic_packs, PacksSettingsRoute),
            SettingsCategory(R.string.settings_section_runtimes, R.string.settings_summary_runtimes, R.drawable.ic_runtimes, RuntimesSettingsRoute),
            SettingsCategory(R.string.settings_section_local_service, R.string.settings_summary_service, R.drawable.ic_service, ServiceSettingsRoute),
        ),
    ),
    SettingsGroup(
        R.string.settings_group_app,
        listOf(
            SettingsCategory(R.string.settings_section_language, R.string.settings_summary_language, R.drawable.ic_language, LanguageSettingsRoute),
            SettingsCategory(R.string.settings_section_permissions, R.string.settings_summary_permissions, R.drawable.ic_permissions, PermissionsSettingsRoute),
            SettingsCategory(R.string.settings_section_about, R.string.settings_summary_about, R.drawable.ic_about, AboutSettingsRoute),
        ),
    ),
)

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun SettingsScreen(
    onNavigate: (Route) -> Unit,
    modifier: Modifier = Modifier,
    bottomContentPadding: Dp = 0.dp,
) {
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val scrollState = rememberScrollState()
    val keyboard = LocalSoftwareKeyboardController.current
    val searchState = rememberSearchBarState()
    val query = rememberTextFieldState()
    val scope = rememberCoroutineScope()
    val inputField = @Composable {
        SearchBarDefaults.InputField(
            textFieldState = query,
            searchBarState = searchState,
            onSearch = { keyboard?.hide() },
            placeholder = { Text(stringResource(R.string.settings_search_hint)) },
            leadingIcon = {
                if (searchState.currentValue == SearchBarValue.Expanded) {
                    IconButton(onClick = {
                        scope.launch {
                            searchState.animateToCollapsed()
                            query.edit { replace(0, length, "") }
                        }
                    }) {
                        Icon(
                            painterResource(R.drawable.ic_arrow_back),
                            contentDescription = stringResource(R.string.action_back),
                        )
                    }
                } else {
                    Icon(painterResource(R.drawable.ic_search), contentDescription = null)
                }
            },
            trailingIcon = if (query.text.isNotEmpty()) {
                {
                    IconButton(onClick = { query.edit { replace(0, length, "") } }) {
                        Icon(
                            painterResource(R.drawable.ic_close),
                            contentDescription = stringResource(R.string.settings_search_clear),
                        )
                    }
                }
            } else {
                null
            },
        )
    }

    Scaffold(
        topBar = {
            LargeFlexibleTopAppBar(
                title = { Text(stringResource(R.string.nav_settings)) },
                scrollBehavior = scrollBehavior,
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                    scrolledContainerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.surface,
        modifier = modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
    ) { innerPadding ->
        Box(
            Modifier.fillMaxSize().padding(innerPadding).consumeWindowInsets(innerPadding),
            contentAlignment = Alignment.TopCenter,
        ) {
            Column(Modifier.widthIn(max = 600.dp).fillMaxSize()) {
                SearchBar(
                    state = searchState,
                    inputField = inputField,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                )
                Column(
                    Modifier.fillMaxWidth().weight(1f).verticalScroll(scrollState)
                        .padding(top = 8.dp, bottom = bottomContentPadding + 16.dp),
                ) {
                    settingsGroups.forEach { group ->
                        SettingSection(title = stringResource(group.titleRes)) {
                            group.categories.forEach { category ->
                                ActionSettingRow(
                                    title = stringResource(category.titleRes),
                                    subtitle = stringResource(category.summaryRes),
                                    onClick = { onNavigate(category.route) },
                                    leading = {
                                        Icon(
                                            painterResource(category.iconRes),
                                            contentDescription = null,
                                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                    },
                                    trailing = {
                                        Icon(
                                            painterResource(R.drawable.ic_chevron_right),
                                            contentDescription = null,
                                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                    },
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    ExpandedFullScreenSearchBar(state = searchState, inputField = inputField) {
        if (query.text.isBlank()) {
            EmptyRow(stringResource(R.string.settings_search_hint))
        } else {
            SearchResults(
                results = rememberSearchResults(query.text.toString()),
                modifier = Modifier.align(Alignment.CenterHorizontally).widthIn(max = 600.dp).fillMaxWidth(),
                contentPadding = PaddingValues(vertical = 16.dp),
                onNavigate = { route ->
                    scope.launch {
                        searchState.animateToCollapsed()
                        onNavigate(route)
                    }
                },
            )
        }
    }
}
