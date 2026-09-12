package com.xychr.ghostdownloader.ui.pages

import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.ui.navigation.*

import androidx.compose.animation.AnimatedVisibilityScope
import androidx.compose.animation.SharedTransitionLayout
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.xychr.ghostdownloader.ui.components.draft.DraftViewModel
import kotlinx.coroutines.launch

@Composable
internal fun TaskNavHost(
    draft: DraftViewModel,
    navController: NavHostController,
    modifier: Modifier,
    bottomContentPadding: Dp,
    onManageCategories: () -> Unit,
) {
    val draftState by draft.state.collectAsStateWithLifecycle()
    val draftScope = rememberCoroutineScope()
    SharedTransitionLayout(modifier) {
        CompositionLocalProvider(LocalSharedTransitionScope provides this) {
            NavHost(
                navController = navController,
                startDestination = TasksRoute,
                modifier = Modifier.fillMaxSize(),
                enterTransition = navEnterTransition,
                exitTransition = navExitTransition,
                popEnterTransition = navPopEnterTransition,
                popExitTransition = navPopExitTransition,
            ) {
                val navigate: (Route) -> Unit = { navController.navigate(it) }
                val back: () -> Unit = { navController.popBackStack() }

                composable<TasksRoute> {
                    WithSharedElements {
                        TasksPage(onNavigate = navigate, onManageCategories = onManageCategories,
                            bottomContentPadding = bottomContentPadding)
                    }
                }

                composable<DraftRoute> {
                    val categories by draft.categories.collectAsStateWithLifecycle()
                    WithSharedElements {
                        DraftPage(draftState, draft::setUrls,
                            onOpen = { navigate(DraftEditRoute(it)) },
                            onRetry = { draft.probe(it, draftState.probeErrors[it]?.kind ?: "media") },
                            onConfirm = { draftScope.launch {
                                if (draft.confirm()) back()
                            } },
                            onDiscard = { draftScope.launch { if (draft.cancel()) back() } },
                            onBack = back, categories = categories,
                            onSetCategory = draft::setCategory)
                    }
                }
                composable<DraftEditRoute> { entry ->
                    val route = entry.toRoute<DraftEditRoute>()
                    val categories by draft.categories.collectAsStateWithLifecycle()
                    DraftEditScreen(draftState.items.firstOrNull { it.url == route.url }, route.part, draftState,
                        onApply = { draft.update(route.url, it) },
                        onOpen = { navigate(DraftEditRoute(route.url, it)) },
                        onProbe = { draft.probe(route.url, it) },
                        fetchPreview = { EngineRepository.query("draftPreview", it) },
                        categories = categories, onBack = back)
                }
                composable<TaskDetailRoute> { entry ->
                    WithSharedElements {
                        TaskDetailPage(entry.toRoute<TaskDetailRoute>().taskId, onBack = back, onNavigate = navigate)
                    }
                }
                composable<TaskFilesRoute> { entry ->
                    TaskFilesPage(entry.toRoute<TaskFilesRoute>().taskId, onBack = back)
                }
                composable<TaskEditRoute> { entry ->
                    TaskEditPage(entry.toRoute<TaskEditRoute>().taskId, onBack = back)
                }
            }
        }
    }
}

@Composable
private fun AnimatedVisibilityScope.WithSharedElements(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalNavAnimatedVisibilityScope provides this, content = content)
}
