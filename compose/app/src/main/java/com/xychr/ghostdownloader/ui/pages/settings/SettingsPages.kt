package com.xychr.ghostdownloader.ui.pages.settings

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.xychr.ghostdownloader.ui.navigation.*

@Composable
internal fun SettingsPages(
    navController: NavHostController,
    bottomContentPadding: Dp,
    onReturnToTasks: () -> Unit,
    shouldOpenCategories: Boolean = false,
    onCategoriesOpened: () -> Unit = {},
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

        composable<SettingsRoute> {
            SettingsScreen(onNavigate = navigate, bottomContentPadding = bottomContentPadding)
        }
        composable<DownloadSettingsRoute> { DownloadPage(onNavigate = navigate, onBack = back, viewModel = settingsVM) }
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
        composable<PacksSettingsRoute> { PacksPage(onNavigate = navigate, onBack = back, viewModel = settingsVM) }
        composable<PackInfoRoute> { PackInfoPage(onBack = back) }
        composable<RuntimesSettingsRoute> { RuntimesPage(onBack = back) }
        composable<PermissionsSettingsRoute> { PermissionsPage(onBack = back) }
        composable<LanguageSettingsRoute> { LanguagePage(onBack = back) }
        composable<AboutSettingsRoute> { AboutPage(onBack = back) }
        composable<PackSettingsRoute> { entry ->
            PackSettingsPage(entry.toRoute<PackSettingsRoute>().pack, onBack = back, viewModel = settingsVM)
        }

        composable<CategorySettingsRoute> { entry ->
            val shouldReturnToTasks = entry.toRoute<CategorySettingsRoute>().returnToTasks
            val close = {
                navController.popBackStack()
                if (shouldReturnToTasks) onReturnToTasks()
            }
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
