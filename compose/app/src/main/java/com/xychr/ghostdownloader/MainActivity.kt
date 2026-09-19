package com.xychr.ghostdownloader

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import com.xychr.ghostdownloader.ui.platform.LocalSetThemeMode
import com.xychr.ghostdownloader.ui.platform.saveThemeMode
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.ClipOp
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.kyant.backdrop.backdrops.layerBackdrop
import com.kyant.backdrop.backdrops.rememberLayerBackdrop
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.PairRequest
import com.xychr.ghostdownloader.service.Notices
import com.xychr.ghostdownloader.ui.components.draft.DraftViewModel
import com.xychr.ghostdownloader.ui.components.liquid.BottomTab
import com.xychr.ghostdownloader.ui.components.liquid.LiquidBottomBar
import com.xychr.ghostdownloader.ui.components.notice.LocalSnackbar
import com.xychr.ghostdownloader.ui.components.notice.PairDialog
import com.xychr.ghostdownloader.ui.components.notice.noticeMessage
import com.xychr.ghostdownloader.ui.navigation.EXTRA_DESTINATION
import com.xychr.ghostdownloader.ui.navigation.RetainedTab
import com.xychr.ghostdownloader.ui.navigation.SettingsNavHost
import com.xychr.ghostdownloader.ui.navigation.SettingsRoute
import com.xychr.ghostdownloader.ui.navigation.TaskNavHost
import com.xychr.ghostdownloader.ui.navigation.TasksRoute
import com.xychr.ghostdownloader.ui.navigation.toRoute
import com.xychr.ghostdownloader.ui.pages.OobePage
import com.xychr.ghostdownloader.ui.pages.settings.SettingsViewModel
import com.xychr.ghostdownloader.ui.pages.settings.UpdateViewModel
import com.xychr.ghostdownloader.ui.platform.ThemeMode
import com.xychr.ghostdownloader.ui.platform.buildLocalizedContext
import com.xychr.ghostdownloader.ui.platform.loadIgnoredUpdateVersion
import com.xychr.ghostdownloader.ui.platform.loadThemeMode
import com.xychr.ghostdownloader.ui.platform.saveIgnoredUpdateVersion
import com.xychr.ghostdownloader.ui.theme.AppTheme
import com.xychr.ghostdownloader.ui.theme.EmphasizedDecelerate
import kotlin.math.hypot
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val draft by viewModels<DraftViewModel> {
        viewModelFactory { initializer {
            DraftViewModel(
                send = { name, args -> engineRepository.invoke(name, *args.toTypedArray()) },
                draftFlow = engineRepository.observe("draftState"),
                categoriesFlow = engineRepository.observe("categoryState"),
            )
        } }
    }
    private val settingsViewModel by viewModels<SettingsViewModel>()
    private val updateViewModel by viewModels<UpdateViewModel> {
        viewModelFactory { initializer {
            val appContext = applicationContext
            UpdateViewModel(
                loadIgnoredVersion = { loadIgnoredUpdateVersion(appContext) },
                saveIgnoredVersion = { saveIgnoredUpdateVersion(appContext, it) },
            )
        } }
    }
    private val destinations = Channel<String>(Channel.BUFFERED)

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(buildLocalizedContext(newBase))
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(EXTRA_DESTINATION)?.let { destinations.trySend(it) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        intent.getStringExtra(EXTRA_DESTINATION)?.let { destinations.trySend(it) }
        enableEdgeToEdge()
        setContent {
            val themeContext = LocalContext.current
            var themeMode by remember { mutableStateOf(loadThemeMode(themeContext)) }
            CompositionLocalProvider(
                LocalSetThemeMode provides { mode ->
                    saveThemeMode(themeContext, mode)
                    themeMode = mode
                },
            ) {
                AppTheme(
                    darkTheme = when (themeMode) {
                        ThemeMode.SYSTEM -> isSystemInDarkTheme()
                        ThemeMode.LIGHT -> false
                        ThemeMode.DARK -> true
                    },
                ) {
                    val settings by settingsViewModel.settings.collectAsStateWithLifecycle()

                    settings?.let { loaded ->
                        var origin by remember { mutableStateOf(Offset.Zero) }
                        var isRevealStarted by remember { mutableStateOf(loaded.hasCompletedOobe) }
                        val progress = animateFloatAsState(
                            targetValue = if (isRevealStarted) 1f else 0f,
                            animationSpec = tween(1_000, easing = EmphasizedDecelerate),
                            label = "oobeReveal",
                        )
                        val isRevealed by remember { derivedStateOf { progress.value >= 1f } }
                        var isAppMounted by remember { mutableStateOf(loaded.hasCompletedOobe) }
                        LaunchedEffect(Unit) {
                            withFrameNanos { }
                            isAppMounted = true
                        }

                        Box(Modifier.fillMaxSize()) {
                            if (isAppMounted) {
                                AppRoot(
                                    draft = draft,
                                    updateViewModel = updateViewModel,
                                    notices = (application as App).notices,
                                    destinations = destinations.receiveAsFlow(),
                                    pairFlow = engineRepository.observe("pairRequest"),
                                    onPairApproval = { requestId, isApproved ->
                                        lifecycleScope.launch {
                                            engineRepository.invoke("setBrowserPairApproval", requestId, isApproved)
                                        }
                                    },
                                )
                            }

                            if (!isRevealed) {
                                OobePage(
                                    settings = loaded,
                                    onSetSetting = settingsViewModel::set,
                                    onFinish = { center ->
                                        origin = center
                                        isRevealStarted = true
                                        settingsViewModel.set("hasCompletedOobe", true)
                                    },
                                    modifier = Modifier.oobeExit(
                                        origin = { origin },
                                        progress = { progress.value },
                                        borderColor = MaterialTheme.colorScheme.outline,
                                    ),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun Modifier.oobeExit(
    origin: () -> Offset,
    progress: () -> Float,
    borderColor: Color,
): Modifier =
    this.drawWithCache {
        val path = Path()
        val ringStroke = Stroke(2.dp.toPx())
        onDrawWithContent {
            val p = progress()
            if (p <= 0f) {
                this@onDrawWithContent.drawContent()
                return@onDrawWithContent
            }
            val center = origin()
            val radius = hypot(
                maxOf(center.x, size.width - center.x),
                maxOf(center.y, size.height - center.y),
            ) * p
            path.reset()
            path.addOval(Rect(center, radius))
            clipPath(path, clipOp = ClipOp.Difference) {
                this@onDrawWithContent.drawContent()
            }
            if (p < 1f) {
                drawCircle(
                    color = borderColor.copy(alpha = ((1f - p) / 0.15f).coerceAtMost(1f)),
                    radius = radius - ringStroke.width / 2,
                    center = center,
                    style = ringStroke,
                )
            }
        }
    }

@Composable
private fun AppRoot(
    draft: DraftViewModel,
    updateViewModel: UpdateViewModel,
    notices: Notices,
    destinations: Flow<String>,
    pairFlow: Flow<PairRequest?>,
    onPairApproval: (String, Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
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

    val context = LocalContext.current
    val snackbar = remember { SnackbarHostState() }
    val draftState by draft.state.collectAsStateWithLifecycle()
    val updateNotice by updateViewModel.updateNotice.collectAsStateWithLifecycle()
    val pair by pairFlow.collectAsStateWithLifecycle(null)

    val navigateTo: (String) -> Unit = { target ->
        selectedTab = BottomTab.TASKS
        taskNavController.navigate(toRoute(target))
    }

    LaunchedEffect(Unit) {
        destinations.collect(navigateTo)
    }

    LaunchedEffect(notices) {
        notices.inApp.collect { notice ->
            val message = context.noticeMessage(notice)
            val result = snackbar.showSnackbar(message.text, message.action, withDismissAction = true)
            if (result == SnackbarResult.ActionPerformed) message.destination?.let(navigateTo)
        }
    }

    pair?.let {
        PairDialog(it, onApprove = { onPairApproval(it.requestId, true) }, onReject = { onPairApproval(it.requestId, false) })
    }

    CompositionLocalProvider(LocalSnackbar provides snackbar) {
        Surface(
            modifier.fillMaxSize()
                .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal))
                .imePadding(),
            color = MaterialTheme.colorScheme.background,
        ) {
            Box(Modifier.fillMaxSize()) {
                Box(Modifier.fillMaxSize().layerBackdrop(backdrop)) {
                    RetainedTab(selectedTab == BottomTab.TASKS, Modifier.fillMaxSize()) {
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
                    }
                    RetainedTab(selectedTab == BottomTab.SETTINGS, Modifier.fillMaxSize()) {
                        SettingsNavHost(
                            navController = settingsNavController,
                            bottomContentPadding = bottomContentPadding,
                            modifier = Modifier.fillMaxSize(),
                            onReturnToTasks = { selectedTab = BottomTab.TASKS },
                            shouldOpenCategories = shouldOpenCategories,
                            onCategoriesOpened = { shouldOpenCategories = false },
                            updateViewModel = updateViewModel,
                        )
                    }
                }
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
                        draftCount = draftState.items.size,
                        hasUpdate = updateNotice != null,
                        backdrop = backdrop,
                        modifier = Modifier.navigationBarsPadding().onSizeChanged { barHeight = it.height },
                    )
                }
                SnackbarHost(
                    snackbar,
                    Modifier.align(Alignment.BottomCenter).padding(bottom = bottomContentPadding),
                )
            }
        }
    }
}


