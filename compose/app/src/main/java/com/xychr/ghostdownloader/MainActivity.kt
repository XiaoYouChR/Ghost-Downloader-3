package com.xychr.ghostdownloader

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
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
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import kotlin.math.hypot
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
import com.xychr.ghostdownloader.ui.navigation.SettingsNavHost
import com.xychr.ghostdownloader.ui.platform.buildLocalizedContext
import com.xychr.ghostdownloader.ui.navigation.TaskNavHost
import com.xychr.ghostdownloader.ui.pages.OobePage
import com.xychr.ghostdownloader.ui.pages.settings.SettingsViewModel
import com.xychr.ghostdownloader.ui.theme.AppTheme

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
    private val settingsViewModel by viewModels<SettingsViewModel>()

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(buildLocalizedContext(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AppTheme {
                val settings by settingsViewModel.settings.collectAsStateWithLifecycle()
                val hasCompleted = settings?.hasCompletedOobe

                when (hasCompleted) {
                    null -> {}
                    true -> AppRoot(draft)
                    false -> OobeWithReveal(
                        downloadFolder = settings?.downloadFolder.orEmpty(),
                        onSetSetting = settingsViewModel::set,
                        appContent = { AppRoot(draft) },
                    )
                }
            }
        }
    }
}

private val EmphasizedDecelerate = CubicBezierEasing(0.05f, 0.7f, 0.1f, 1.0f)

@Composable
private fun OobeWithReveal(
    downloadFolder: String,
    onSetSetting: (String, Any) -> Unit,
    appContent: @Composable () -> Unit,
) {
    var revealCenter by remember { mutableStateOf(Offset.Zero) }
    var isRevealing by remember { mutableStateOf(false) }
    var isOobeVisible by remember { mutableStateOf(true) }

    val revealProgress = animateFloatAsState(
        targetValue = if (isRevealing) 1f else 0f,
        animationSpec = tween(durationMillis = 600, easing = EmphasizedDecelerate),
        finishedListener = {
            if (isRevealing) {
                isOobeVisible = false
                onSetSetting("hasCompletedOobe", true)
            }
        },
    )

    Box(Modifier.fillMaxSize()) {
        if (isOobeVisible) {
            OobePage(
                downloadFolder = downloadFolder,
                onSetSetting = onSetSetting,
                onFinish = { center ->
                    revealCenter = center
                    isRevealing = true
                },
            )
            if (isRevealing) {
                Box(
                    Modifier
                        .fillMaxSize()
                        .background(Color.Black.copy(alpha = 0.3f * revealProgress.value)),
                )
            }
        }

        if (isRevealing || !isOobeVisible) {
            Box(
                Modifier.fillMaxSize().circularReveal(revealCenter, revealProgress),
            ) {
                appContent()
            }
        }
    }
}

private fun Modifier.circularReveal(
    center: Offset,
    progress: androidx.compose.runtime.State<Float>,
): Modifier = drawWithCache {
    val path = Path()

    onDrawWithContent {
        val p = progress.value
        if (p >= 1f) {
            drawContent()
        } else {
            path.rewind()
            val maxRadius = hypot(
                maxOf(center.x, size.width - center.x),
                maxOf(center.y, size.height - center.y),
            )
            path.addOval(Rect(center, maxRadius * p))
            clipPath(path) {
                this@onDrawWithContent.drawContent()
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
                SettingsNavHost(
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

