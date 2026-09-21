package com.xychr.ghostdownloader.ui.pages.settings

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.input.rememberTextFieldState
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
import androidx.compose.material3.SearchBarDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberSearchBarState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
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
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.packs.has
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.EmptyRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SearchResults
import com.xychr.ghostdownloader.ui.components.settings.rememberSearchResults
import com.xychr.ghostdownloader.ui.navigation.*
import kotlinx.serialization.json.JsonObject

private data class SettingsRow(
    val title: String,
    val subtitle: String?,
    @DrawableRes val iconRes: Int?,
    val route: Route,
)

@Composable
private fun row(@StringRes titleRes: Int, @StringRes summaryRes: Int, @DrawableRes iconRes: Int, route: Route) =
    SettingsRow(stringResource(titleRes), stringResource(summaryRes), iconRes, route)

@Composable
private fun downloadRows() = listOf(
    row(R.string.settings_section_download, R.string.settings_summary_download, R.drawable.ic_download, DownloadSettingsRoute),
    row(R.string.category_manage, R.string.settings_summary_category, R.drawable.ic_folder, CategorySettingsRoute()),
    row(R.string.settings_section_network, R.string.settings_summary_network, R.drawable.ic_network, NetworkSettingsRoute),
    row(R.string.settings_section_identity, R.string.settings_summary_identity, R.drawable.ic_account_box, IdentitySettingsRoute),
)

@Composable
private fun featuresRows() = listOf(
    row(R.string.settings_section_runtimes, R.string.settings_summary_runtimes, R.drawable.ic_runtimes, RuntimesSettingsRoute),
    row(R.string.settings_section_local_service, R.string.settings_summary_service, R.drawable.ic_service, ServiceSettingsRoute),
)

@Composable
private fun appRows(updateVersion: String?) = listOf(
    row(R.string.settings_section_appearance, R.string.settings_summary_language, R.drawable.ic_language, AppearanceSettingsRoute),
    row(R.string.settings_section_permissions, R.string.settings_summary_permissions, R.drawable.ic_permissions, PermissionsSettingsRoute),
    SettingsRow(
        title = stringResource(R.string.settings_section_about),
        subtitle = updateVersion?.let { stringResource(R.string.settings_update_ready, it) }
            ?: stringResource(R.string.settings_summary_about),
        iconRes = R.drawable.ic_about,
        route = AboutSettingsRoute,
    ),
)

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun SettingsHomePage(
    onNavigate: (Route) -> Unit,
    onSearchResult: (Route, String) -> Unit,
    viewModel: SettingsViewModel,
    updateVersion: String?,
    modifier: Modifier = Modifier,
    bottomContentPadding: Dp = 0.dp,
) {
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val scrollState = rememberScrollState()
    val keyboard = LocalSoftwareKeyboardController.current
    val searchState = rememberSearchBarState()
    val query = rememberTextFieldState()
    val scope = rememberCoroutineScope()
    val config by viewModel.config.collectAsStateWithLifecycle()
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
                    SettingsGroup(R.string.settings_group_download, downloadRows(), onNavigate)
                    SettingsGroup(R.string.settings_group_features, featuresRows(), onNavigate)
                    SettingsGroup(R.string.settings_section_packs, packRows(config), onNavigate,
                        emptyText = stringResource(R.string.settings_packs_empty))
                    SettingsGroup(R.string.settings_group_app, appRows(updateVersion), onNavigate)
                }
            }
        }
    }

    ExpandedFullScreenSearchBar(state = searchState, inputField = inputField) {
        if (query.text.isBlank()) {
            EmptyRow(stringResource(R.string.settings_search_hint))
        } else {
            val results = rememberSearchResults(query.text.toString())
            SearchResults(
                results = results,
                modifier = Modifier.align(Alignment.CenterHorizontally).widthIn(max = 600.dp).fillMaxWidth(),
                contentPadding = PaddingValues(vertical = 16.dp),
                onNavigate = { route, title ->
                    scope.launch {
                        searchState.animateToCollapsed()
                        query.edit { replace(0, length, "") }
                        onSearchResult(route, title)
                    }
                },
            )
        }
    }
}

@Composable
private fun ColumnScope.SettingsGroup(
    @StringRes titleRes: Int,
    rows: List<SettingsRow>,
    onNavigate: (Route) -> Unit,
    emptyText: String? = null,
) {
    SettingSection(title = stringResource(titleRes)) {
        if (rows.isEmpty()) {
            emptyText?.let { EmptyRow(it) }
            return@SettingSection
        }
        rows.forEach { row ->
            ActionSettingRow(
                title = row.title,
                subtitle = row.subtitle,
                onClick = { onNavigate(row.route) },
                leading = row.iconRes?.let { icon ->
                    { Icon(painterResource(icon), contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant) }
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

@Composable
private fun packRows(config: JsonObject?): List<SettingsRow> {
    val packs = remember(config) {
        config?.let { blob ->
            PackRegistry.withSettings().filter { entry -> blob.has(PackKeys(entry.configClass!!)) }
        }.orEmpty()
    }
    return packs.map { entry ->
        SettingsRow(stringResource(entry.packUi.settingsTitle), null, null, PackSettingsRoute(entry.packUi.packId))
    }
}
