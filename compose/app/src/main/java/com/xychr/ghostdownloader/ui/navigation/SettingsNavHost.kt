package com.xychr.ghostdownloader.ui.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.toRoute
import com.xychr.ghostdownloader.ui.components.settings.LocalSettingsAnchor
import com.xychr.ghostdownloader.ui.pages.settings.AboutPage
import com.xychr.ghostdownloader.ui.pages.settings.CategoryEditPage
import com.xychr.ghostdownloader.ui.pages.settings.CategoryPage
import com.xychr.ghostdownloader.ui.pages.settings.CategoryViewModel
import com.xychr.ghostdownloader.ui.pages.settings.ClientProfilePage
import com.xychr.ghostdownloader.ui.pages.settings.DownloadPage
import com.xychr.ghostdownloader.ui.pages.settings.HeadersPresetEditPage
import com.xychr.ghostdownloader.ui.pages.settings.HeadersPresetsPage
import com.xychr.ghostdownloader.ui.pages.settings.IdentityPage
import com.xychr.ghostdownloader.ui.pages.settings.IdentityPresetEditPage
import com.xychr.ghostdownloader.ui.pages.settings.IdentityRulesPage
import com.xychr.ghostdownloader.ui.pages.settings.IdentityViewModel
import com.xychr.ghostdownloader.ui.pages.settings.AppearancePage
import com.xychr.ghostdownloader.ui.pages.settings.NetworkPage
import com.xychr.ghostdownloader.ui.pages.settings.PackInfoPage
import com.xychr.ghostdownloader.ui.pages.settings.PackSettingsPage
import com.xychr.ghostdownloader.ui.pages.settings.PermissionsPage
import com.xychr.ghostdownloader.ui.pages.settings.ProxyPage
import com.xychr.ghostdownloader.ui.pages.settings.RuntimesPage
import com.xychr.ghostdownloader.ui.pages.settings.ServicePage
import com.xychr.ghostdownloader.ui.pages.settings.SettingsHomePage
import com.xychr.ghostdownloader.ui.pages.settings.SettingsViewModel
import com.xychr.ghostdownloader.ui.pages.settings.UpdateViewModel

@Composable
internal fun SettingsNavHost(
    navController: NavHostController,
    bottomContentPadding: Dp,
    onReturnToTasks: () -> Unit,
    shouldOpenCategories: Boolean = false,
    onCategoriesOpened: () -> Unit = {},
    updateViewModel: UpdateViewModel,
    modifier: Modifier = Modifier,
) {
    LaunchedEffect(shouldOpenCategories) {
        if (shouldOpenCategories) {
            navController.navigate(CategorySettingsRoute(returnToTasks = true))
            onCategoriesOpened()
        }
    }
    val settingsVM: SettingsViewModel = viewModel()
    val categoryVM: CategoryViewModel = viewModel()
    val identityVM: IdentityViewModel = viewModel()

    var searchAnchor by remember { mutableStateOf<String?>(null) }
    var pendingAnchor by remember { mutableStateOf<String?>(null) }
    val currentEntry by navController.currentBackStackEntryAsState()
    LaunchedEffect(currentEntry) {
        searchAnchor = pendingAnchor
        pendingAnchor = null
    }
    val updateNotice by updateViewModel.updateNotice.collectAsStateWithLifecycle()

    CompositionLocalProvider(LocalSettingsAnchor provides searchAnchor) {
        NavHost(
            navController = navController,
            startDestination = SettingsRoute,
            modifier = modifier,
            enterTransition = navEnterTransition,
            exitTransition = navExitTransition,
            popEnterTransition = navPopEnterTransition,
            popExitTransition = navPopExitTransition,
        ) {
            val navigate: (Route) -> Unit = { navController.navigate(it) }
            val back: () -> Unit = { navController.popBackStack() }
            val onSearchResult: (Route, String) -> Unit = { route, title ->
                pendingAnchor = title
                navController.navigate(route)
            }

            composable<SettingsRoute> {
                SettingsHomePage(
                    onNavigate = navigate,
                    onSearchResult = onSearchResult,
                    viewModel = settingsVM,
                    updateVersion = updateNotice?.version,
                    bottomContentPadding = bottomContentPadding,
                )
            }
            composable<DownloadSettingsRoute> { DownloadPage(onBack = back, viewModel = settingsVM) }
            composable<NetworkSettingsRoute> { NetworkPage(onNavigate = navigate, onBack = back, viewModel = settingsVM) }
            composable<IdentitySettingsRoute> { IdentityPage(onNavigate = navigate, onBack = back, viewModel = identityVM) }
            composable<IdentityRulesRoute> { IdentityRulesPage(onNavigate = navigate, onBack = back, viewModel = identityVM) }
            composable<HeadersPresetsRoute> { entry ->
                val focus by entry.savedStateHandle.getStateFlow("headersFocus", -1).collectAsStateWithLifecycle()
                HeadersPresetsPage(onNavigate = navigate, onBack = back, viewModel = identityVM, focusIndex = focus,
                    onFocusConsumed = { entry.savedStateHandle["headersFocus"] = -1 })
            }
            composable<ClientProfileRoute> { ClientProfilePage(onBack = back, viewModel = identityVM) }
            composable<ProxySettingsRoute> { ProxyPage(onBack = back, viewModel = settingsVM) }
            composable<ServiceSettingsRoute> { ServicePage(onBack = back, viewModel = settingsVM) }
            composable<PackInfoRoute> { PackInfoPage(onBack = back) }
            composable<RuntimesSettingsRoute> { RuntimesPage(onBack = back) }
            composable<PermissionsSettingsRoute> { PermissionsPage(onBack = back) }
            composable<AppearanceSettingsRoute> { AppearancePage(onBack = back) }
            composable<AboutSettingsRoute> {
                AboutPage(
                    onNavigate = navigate,
                    onBack = back,
                    settingsViewModel = settingsVM,
                    updateViewModel = updateViewModel,
                )
            }
            composable<PackSettingsRoute> { entry ->
                PackSettingsPage(entry.toRoute<PackSettingsRoute>().pack, onBack = back, viewModel = settingsVM)
            }

            composable<CategorySettingsRoute> { entry ->
                val shouldReturnToTasks = entry.toRoute<CategorySettingsRoute>().returnToTasks
                val close = { back(); if (shouldReturnToTasks) onReturnToTasks() }
                BackHandler(enabled = shouldReturnToTasks, onBack = close)
                CategoryPage(onNavigate = navigate, onBack = close, viewModel = categoryVM)
            }
            composable<CategoryEditRoute> { entry ->
                CategoryEditPage(entry.toRoute<CategoryEditRoute>().categoryId, onBack = back, viewModel = categoryVM)
            }

            composable<IdentityPresetEditRoute> { entry ->
                IdentityPresetEditPage(entry.toRoute<IdentityPresetEditRoute>().index, onBack = back, viewModel = identityVM)
            }
            composable<HeadersPresetEditRoute> { entry ->
                val route = entry.toRoute<HeadersPresetEditRoute>()
                HeadersPresetEditPage(route.index, onBack = back, viewModel = identityVM, copyFrom = route.copyFrom,
                    onSaved = { navController.previousBackStackEntry?.savedStateHandle?.set("headersFocus", it) })
            }
        }
    }
}
