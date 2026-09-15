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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.kyant.backdrop.backdrops.layerBackdrop
import com.kyant.backdrop.backdrops.rememberLayerBackdrop
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.Notice
import com.xychr.ghostdownloader.model.PairRequest
import com.xychr.ghostdownloader.service.Notices
import com.xychr.ghostdownloader.ui.components.draft.DraftViewModel
import com.xychr.ghostdownloader.ui.components.liquid.BottomTab
import com.xychr.ghostdownloader.ui.components.liquid.LiquidBottomBar
import com.xychr.ghostdownloader.ui.components.notice.LocalSnackbar
import com.xychr.ghostdownloader.ui.components.notice.PairDialog
import com.xychr.ghostdownloader.ui.components.notice.noticeMessage
import com.xychr.ghostdownloader.ui.navigation.DraftRoute
import com.xychr.ghostdownloader.ui.navigation.RetainedTab
import com.xychr.ghostdownloader.ui.navigation.SettingsNavHost
import com.xychr.ghostdownloader.ui.navigation.SettingsRoute
import com.xychr.ghostdownloader.ui.navigation.TaskDetailRoute
import com.xychr.ghostdownloader.ui.navigation.TaskNavHost
import com.xychr.ghostdownloader.ui.navigation.TasksRoute
import com.xychr.ghostdownloader.ui.pages.OobePage
import com.xychr.ghostdownloader.ui.pages.settings.SettingsViewModel
import com.xychr.ghostdownloader.ui.platform.buildLocalizedContext
import com.xychr.ghostdownloader.ui.theme.AppTheme
import kotlinx.coroutines.launch

const val EXTRA_DESTINATION = "destination"
const val DESTINATION_DRAFT = "draft"

fun toTaskDestination(taskId: String) = "task:$taskId"

class MainActivity : ComponentActivity() {
    private val draft by viewModels<DraftViewModel> {
        viewModelFactory { initializer {
            DraftViewModel(
                send = { name, args -> EngineRepository.invoke(name, *args.toTypedArray()) },
                draftFlow = EngineRepository.observe("draftState"),
                categoriesFlow = EngineRepository.observe("categoryState"),
            )
        } }
    }
    private val settingsViewModel by viewModels<SettingsViewModel>()
    private val destination = mutableStateOf<String?>(null)

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(buildLocalizedContext(newBase))
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        destination.value = intent.getStringExtra(EXTRA_DESTINATION)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        destination.value = intent.getStringExtra(EXTRA_DESTINATION)
        enableEdgeToEdge()
        setContent {
            AppTheme {
                val settings by settingsViewModel.settings.collectAsStateWithLifecycle()
                val hasCompleted = settings?.hasCompletedOobe

                if (hasCompleted != null) {
                    OobeGate(
                        initiallyCompleted = hasCompleted,
                        downloadFolder = settings?.downloadFolder.orEmpty(),
                        onSetSetting = settingsViewModel::set,
                        appContent = {
                            AppRoot(
                                draft = draft,
                                notices = (application as App).notices,
                                noticeDestination = destination.value,
                                onDestinationHandled = { destination.value = null },
                            )
                        },
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun OobeGate(
    initiallyCompleted: Boolean,
    downloadFolder: String,
    onSetSetting: (String, Any) -> Unit,
    appContent: @Composable () -> Unit,
) {
    var isRevealed by remember { mutableStateOf(initiallyCompleted) }
    var revealOrigin by remember { mutableStateOf(Offset.Zero) }

    val revealProgress by animateFloatAsState(
        targetValue = if (isRevealed) 1f else 0f,
        animationSpec = MaterialTheme.motionScheme.slowSpatialSpec(),
        label = "oobeReveal",
    )

    Box(Modifier.fillMaxSize()) {
        OobePage(
            downloadFolder = downloadFolder,
            onSetSetting = onSetSetting,
            onFinish = {
                isRevealed = true
                onSetSetting("hasCompletedOobe", true)
            },
            containerModifier = Modifier.onGloballyPositioned { coordinates ->
                revealOrigin = coordinates.boundsInRoot().center
            },
        )

        if (isRevealed) {
            val backgroundColor = MaterialTheme.colorScheme.background
            Box(
                Modifier
                    .fillMaxSize()
                    .drawWithCache {
                        val maxX = maxOf(revealOrigin.x, size.width - revealOrigin.x)
                        val maxY = maxOf(revealOrigin.y, size.height - revealOrigin.y)
                        val maxRadius = kotlin.math.sqrt(maxX * maxX + maxY * maxY)
                        val shadowSpread = 4.dp.toPx()
                        val revealPath = Path()
                        onDrawWithContent {
                            val radius = maxRadius * revealProgress
                            if (radius > 0f) {
                                drawCircle(Color.Black, radius + shadowSpread, revealOrigin, alpha = 0.12f)
                            }
                            revealPath.reset()
                            revealPath.addOval(androidx.compose.ui.geometry.Rect(revealOrigin, radius))
                            clipPath(revealPath) {
                                drawRect(backgroundColor)
                                this@onDrawWithContent.drawContent()
                            }
                        }
                    },
            ) {
                appContent()
            }
        }
    }
}

@Composable
private fun AppRoot(
    draft: DraftViewModel,
    notices: Notices,
    noticeDestination: String?,
    onDestinationHandled: () -> Unit,
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
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    val draftState by draft.state.collectAsStateWithLifecycle()
    val pair by EngineRepository.observe<PairRequest?>("pairRequest")
        .collectAsStateWithLifecycle(null)

    val navigateTo: (String) -> Unit = { target ->
        selectedTab = BottomTab.TASKS
        taskNavController.navigate(
            if (target == DESTINATION_DRAFT) DraftRoute
            else TaskDetailRoute(target.removePrefix("task:"))
        )
    }

    LaunchedEffect(noticeDestination) {
        noticeDestination?.let { navigateTo(it); onDestinationHandled() }
    }

    LaunchedEffect(notices) {
        notices.inApp.collect { notice ->
            val message = context.noticeMessage(notice)
            val result = snackbar.showSnackbar(message.text, message.action, withDismissAction = true)
            if (result == SnackbarResult.ActionPerformed) message.destination?.let(navigateTo)
        }
    }

    pair?.let {
        val approve: (Boolean) -> Unit = { isApproved ->
            scope.launch { EngineRepository.invoke("setBrowserPairApproval", it.requestId, isApproved) }
        }
        PairDialog(it, onApprove = { approve(true) }, onReject = { approve(false) })
    }

    CompositionLocalProvider(LocalSnackbar provides snackbar) {
        Box(
            Modifier.fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
                .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal))
                .imePadding(),
        ) {
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


