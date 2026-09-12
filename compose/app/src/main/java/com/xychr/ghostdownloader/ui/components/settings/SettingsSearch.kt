package com.xychr.ghostdownloader.ui.components.settings

import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.ui.navigation.*

data class SearchableItem(
    val titleRes: Int,
    val subtitleRes: Int? = null,
    val breadcrumbRes: Int,
    val route: Route,
)

private fun MutableList<SearchableItem>.section(
    breadcrumbRes: Int,
    route: Route,
    items: List<Pair<Int, Int?>>,
) = items.forEach { (title, subtitle) ->
    add(SearchableItem(title, subtitle, breadcrumbRes, route))
}

/**
 * 设置项的搜索索引。搜的是 string resource 的实际文案，所以跟随系统语言。
 * App 设置项在此声明；Pack 设置项由各 PackUi.searchItems 声明，运行时聚合。
 */
val settingsIndex: List<SearchableItem> by lazy { buildList {
    section(
        R.string.settings_section_download, DownloadSettingsRoute,
        listOf(
            R.string.settings_download_folder to null,
            R.string.settings_max_task_num to null,
            R.string.settings_pre_block_num to null,
            R.string.settings_auto_speed_up to R.string.settings_auto_speed_up_desc,
            R.string.settings_reassign_size to null,
            R.string.settings_preserve_modified to R.string.settings_preserve_modified_desc,
            R.string.settings_speed_limit_enabled to null,
            R.string.settings_speed_limit to null,
            R.string.settings_delete_files_on_remove to null,
        ),
    )
    section(
        R.string.settings_section_network, NetworkSettingsRoute,
        listOf(
            R.string.settings_system_dns to R.string.settings_system_dns_desc,
            R.string.settings_verify_ssl to null,
        ),
    )
    add(SearchableItem(R.string.settings_proxy, breadcrumbRes = R.string.settings_section_network, route = ProxySettingsRoute))
    add(SearchableItem(R.string.identity_client_profile, breadcrumbRes = R.string.settings_section_identity, route = ClientProfileRoute))
    add(SearchableItem(R.string.identity_rules, breadcrumbRes = R.string.settings_section_identity, route = IdentityRulesRoute))
    add(SearchableItem(R.string.identity_headers_presets, breadcrumbRes = R.string.settings_section_identity, route = HeadersPresetsRoute))
    section(
        R.string.category_manage, CategorySettingsRoute(),
        listOf(
            R.string.category_enabled to null,
            R.string.category_manage to null,
        ),
    )
    section(
        R.string.settings_section_local_service, ServiceSettingsRoute,
        listOf(
            R.string.settings_browser_extension to R.string.settings_browser_extension_desc,
            R.string.settings_taken_draft to R.string.settings_taken_draft_desc,
            R.string.settings_browser_port to null,
            R.string.settings_browser_token to null,
            R.string.settings_browser_status to null,
            R.string.settings_browser_export to R.string.settings_browser_export_desc,
            R.string.settings_browser_regenerate to R.string.settings_browser_regenerate_desc,
            R.string.settings_aria2_rpc to R.string.settings_aria2_rpc_desc,
            R.string.settings_aria2_rpc_port to null,
            R.string.settings_aria2_rpc_token to R.string.settings_aria2_rpc_token_desc,
            R.string.settings_aria2_rpc_emulate to R.string.settings_aria2_rpc_emulate_desc,
        ),
    )
    section(
        R.string.settings_section_runtimes, RuntimesSettingsRoute,
        listOf(R.string.settings_section_runtimes to null),
    )
    section(
        R.string.settings_section_permissions, PermissionsSettingsRoute,
        listOf(
            R.string.settings_storage_access to null,
            R.string.settings_notifications to null,
            R.string.settings_battery_unrestricted to R.string.settings_battery_unrestricted_desc,
            R.string.settings_install_packages to R.string.settings_install_packages_desc,
        ),
    )

    add(SearchableItem(R.string.settings_section_language, R.string.settings_summary_language, R.string.settings_group_app, LanguageSettingsRoute))

    PackRegistry.withSettings().forEach { entry ->
        val pack = entry.packUi
        section(pack.settingsTitle, PackSettingsRoute(pack.packId), pack.searchItems)
    }
} }

@Composable
fun rememberSearchResults(query: String): List<SearchableItem> {
    val haystack = settingsIndex.map { item ->
        item to (stringResource(item.titleRes) + " " + item.subtitleRes?.let { stringResource(it) }.orEmpty())
    }
    return remember(query, haystack) {
        if (query.isBlank()) emptyList()
        else haystack.filter { (_, text) -> text.contains(query, ignoreCase = true) }.map { it.first }
    }
}

@Composable
fun SearchResults(
    results: List<SearchableItem>,
    onNavigate: (Route) -> Unit,
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(0.dp),
) {
    if (results.isEmpty()) {
        EmptyRow(stringResource(R.string.settings_search_empty))
        return
    }

    LazyColumn(
        modifier.padding(horizontal = 16.dp),
        contentPadding = contentPadding,
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        items(results, key = { "${it.route}:${it.titleRes}" }) { item ->
            ActionSettingRow(
                title = stringResource(item.titleRes),
                subtitle = breadcrumbOf(item),
                onClick = { onNavigate(item.route) },
            )
        }
    }
}

/** Pack 的面包屑要带上「下载插件」前缀，否则只看到 pack 名不知道去哪找 */
@Composable
private fun breadcrumbOf(item: SearchableItem): String {
    val leaf = stringResource(item.breadcrumbRes)
    return if (item.route is PackSettingsRoute) {
        "${stringResource(R.string.settings_section_packs)} · $leaf"
    } else {
        leaf
    }
}
