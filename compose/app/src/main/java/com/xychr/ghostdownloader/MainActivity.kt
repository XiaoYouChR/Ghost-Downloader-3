package com.xychr.ghostdownloader

import android.Manifest
import android.content.Context
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.kyant.backdrop.backdrops.layerBackdrop
import com.kyant.backdrop.backdrops.rememberLayerBackdrop
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.ui.components.draft.DraftViewModel
import com.xychr.ghostdownloader.ui.components.liquid.BottomTab
import com.xychr.ghostdownloader.ui.components.liquid.LiquidBottomBar
import com.xychr.ghostdownloader.ui.navigation.RetainedTab
import com.xychr.ghostdownloader.ui.navigation.SettingsRoute
import com.xychr.ghostdownloader.ui.navigation.TasksRoute
import com.xychr.ghostdownloader.ui.pages.settings.SettingsPages
import com.xychr.ghostdownloader.ui.platform.buildLocalizedContext
import com.xychr.ghostdownloader.ui.pages.TaskNavHost
import com.xychr.ghostdownloader.ui.theme.GhostDownloaderTheme

class MainActivity : ComponentActivity() {
    private val draft by viewModels<DraftViewModel> {
        viewModelFactory { initializer {
            DraftViewModel(
                fetchItems = { EngineRepository.query("draft") },
                send = { name, args -> EngineRepository.invoke(name, *args.toTypedArray()) },
                categoriesFlow = EngineRepository.observe("categoryState"),
            )
        } }
    }
    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(buildLocalizedContext(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerForActivityResult(ActivityResultContracts.RequestPermission()) { }
                .launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent {
            GhostDownloaderTheme {
                AppRoot(draft)
            }
        }
    }
}

@Composable
private fun AppRoot(draft: DraftViewModel) {
    val taskNavController = rememberNavController()
    val settingsNavController = rememberNavController()

    var selectedTab by rememberSaveable { mutableStateOf(BottomTab.TASKS) }
    var shouldOpenCategories by remember { mutableStateOf(false) }
    val taskEntry by taskNavController.currentBackStackEntryAsState()
    val settingsEntry by settingsNavController.currentBackStackEntryAsState()
    val isTopLevel = when (selectedTab) {
        BottomTab.TASKS -> taskEntry?.destination?.hasRoute(TasksRoute::class) != false
        BottomTab.SETTINGS -> settingsEntry?.destination?.hasRoute(SettingsRoute::class) != false
    }

    val backdrop = rememberLayerBackdrop()
    var barHeight by remember { mutableIntStateOf(0) }
    val bottomContentPadding = if (barHeight == 0) 80.dp else with(LocalDensity.current) { barHeight.toDp() + 8.dp }
    val haptics = LocalHapticFeedback.current
    val focus = LocalFocusManager.current
    BackHandler(enabled = isTopLevel && selectedTab == BottomTab.SETTINGS) {
        selectedTab = BottomTab.TASKS
    }
    LaunchedEffect(selectedTab) { focus.clearFocus() }

    Box(
        Modifier.fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal))
            .imePadding(),
    ) {
        HomeTabs(
            selectedTab = selectedTab,
            modifier = Modifier.fillMaxSize().layerBackdrop(backdrop),
            taskContent = {
                TaskNavHost(
                    draft = draft,
                    navController = taskNavController,
                    modifier = Modifier.fillMaxSize(),
                    bottomContentPadding = bottomContentPadding,
                    onManageCategories = {
                        shouldOpenCategories = true
                        selectedTab = BottomTab.SETTINGS
                    },
                )
            },
            settingsContent = {
                SettingsPages(
                    navController = settingsNavController,
                    bottomContentPadding = bottomContentPadding,
                    modifier = Modifier.fillMaxSize(),
                    onReturnToTasks = { selectedTab = BottomTab.TASKS },
                    shouldOpenCategories = shouldOpenCategories,
                    onCategoriesOpened = { shouldOpenCategories = false },
                )
            },
        )
        AnimatedVisibility(
            visible = isTopLevel,
            enter = slideInVertically { it },
            exit = slideOutVertically { it },
            modifier = Modifier.align(Alignment.BottomCenter),
        ) {
            LiquidBottomBar(
                selectedTab = selectedTab,
                onTabSelected = { tab ->
                    if (tab != selectedTab) {
                        selectedTab = tab
                        haptics.performHapticFeedback(HapticFeedbackType.SegmentTick)
                    }
                },
                backdrop = backdrop,
                modifier = Modifier.navigationBarsPadding().onSizeChanged { barHeight = it.height },
            )
        }
    }
}

@Composable
private fun HomeTabs(
    selectedTab: BottomTab,
    taskContent: @Composable () -> Unit,
    settingsContent: @Composable () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(modifier) {
        RetainedTab(
            isActive = selectedTab == BottomTab.TASKS,
            modifier = Modifier.fillMaxSize(),
            content = taskContent,
        )
        RetainedTab(
            isActive = selectedTab == BottomTab.SETTINGS,
            modifier = Modifier.fillMaxSize(),
            content = settingsContent,
        )
    }
}

