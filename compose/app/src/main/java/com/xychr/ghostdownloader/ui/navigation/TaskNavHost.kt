package com.xychr.ghostdownloader.ui.navigation

import androidx.compose.animation.AnimatedVisibilityScope
import androidx.compose.animation.SharedTransitionLayout
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.CategoryState
import com.xychr.ghostdownloader.ui.components.draft.DraftViewModel
import com.xychr.ghostdownloader.ui.pages.DraftEditPage
import com.xychr.ghostdownloader.ui.pages.DraftPage
import com.xychr.ghostdownloader.ui.pages.TaskDetailPage
import com.xychr.ghostdownloader.ui.pages.TaskEditPage
import com.xychr.ghostdownloader.ui.pages.TaskFilesPage
import com.xychr.ghostdownloader.ui.pages.TasksPage
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
    val categories by engineRepository.observe<CategoryState>("categoryState")
        .collectAsStateWithLifecycle(CategoryState())
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
                        DraftPage(draftState, draft,
                            onConfirm = { autoStart -> draftScope.launch {
                                if (draft.confirm(autoStart)) back()
                            } },
                            onDiscard = { draftScope.launch { if (draft.cancel()) back() } },
                            onBack = back, onOpenEdit = { url -> navigate(DraftEditRoute(url)) },
                            categories = categories)
                    }
                }
                composable<DraftEditRoute> { entry ->
                    val url = remember(entry) { entry.toRoute<DraftEditRoute>().url }
                    val item = draftState.items.firstOrNull { it.url == url }
                    if (item == null) LaunchedEffect(Unit) { back() }
                    else DraftEditPage(item, draft, onBack = back)
                }
                composable<TaskDetailRoute> { entry ->
                    WithSharedElements {
                        TaskDetailPage(entry.toRoute<TaskDetailRoute>().taskId, onBack = back,
                            onNavigate = navigate, categories = categories)
                    }
                }
                composable<TaskFilesRoute> { entry ->
                    TaskFilesPage(entry.toRoute<TaskFilesRoute>().taskId, onBack = back, categories = categories)
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
