package com.xychr.ghostdownloader.ui.pages

import androidx.activity.compose.BackHandler
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Settings
import com.xychr.ghostdownloader.ui.components.settings.AppearanceSections
import com.xychr.ghostdownloader.ui.components.settings.PathSettingRow
import com.xychr.ghostdownloader.ui.components.settings.PermissionRows
import com.xychr.ghostdownloader.ui.components.settings.RuntimeRows
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.platform.defaultDownloadFolder
import com.xychr.ghostdownloader.ui.platform.rememberFolderPicker
import kotlinx.coroutines.launch

private enum class OobeStep {
    WELCOME, PERMISSIONS, APPEARANCE, DOWNLOAD, FEATURES, RUNTIMES, COMPLETE,
}

@Composable
fun OobePage(
    settings: Settings,
    onSetSetting: (String, Any) -> Unit,
    onFinish: (Offset) -> Unit,
) {
    val scope = rememberCoroutineScope()
    val pagerState = rememberPagerState { OobeStep.entries.size }
    val folderPicker = rememberFolderPicker { onSetSetting("downloadFolder", it) }
    val back: () -> Unit = {
        scope.launch { pagerState.animateScrollToPage(pagerState.currentPage - 1) }
    }

    BackHandler(enabled = pagerState.currentPage > 0, onBack = back)

    // 背景要铺到系统栏下面，避让只落在内容上；否则窗口背景会从状态栏露出
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.surface,
    ) {
        Column(Modifier.windowInsetsPadding(WindowInsets.safeDrawing)) {
            HorizontalPager(
                state = pagerState,
                userScrollEnabled = false,
                modifier = Modifier.weight(1f),
            ) { page ->
                when (OobeStep.entries[page]) {
                    OobeStep.WELCOME -> WelcomeContent()

                    OobeStep.PERMISSIONS -> OobeStepContent(
                        R.string.settings_section_permissions,
                        R.string.oobe_permissions_subtitle,
                    ) {
                        SettingSection { PermissionRows() }
                    }

                    OobeStep.APPEARANCE -> OobeStepContent(
                        R.string.settings_section_appearance,
                        R.string.oobe_appearance_subtitle,
                    ) {
                        AppearanceSections()
                    }

                    OobeStep.DOWNLOAD -> OobeStepContent(
                        R.string.oobe_basic_title,
                        R.string.oobe_basic_subtitle,
                    ) {
                        SettingSection {
                            PathSettingRow(
                                title = stringResource(R.string.settings_download_folder),
                                path = settings.downloadFolder,
                                picker = folderPicker,
                                onReset = {
                                    onSetSetting("downloadFolder", defaultDownloadFolder())
                                },
                            )
                        }
                    }

                    OobeStep.FEATURES -> OobeStepContent(
                        R.string.oobe_features_title,
                        R.string.oobe_features_subtitle,
                    ) {
                        SettingSection {
                            SwitchSettingRow(
                                title = stringResource(R.string.category_enabled),
                                subtitle = stringResource(R.string.category_enabled_desc),
                                checked = settings.isCategoryEnabled,
                                onCheckedChange = { onSetSetting("isCategoryEnabled", it) },
                            )
                            SwitchSettingRow(
                                title = stringResource(R.string.settings_browser_extension),
                                subtitle = stringResource(R.string.settings_browser_extension_desc),
                                checked = settings.isBrowserExtensionEnabled,
                                onCheckedChange = { onSetSetting("isBrowserExtensionEnabled", it) },
                            )
                            SwitchSettingRow(
                                title = stringResource(R.string.settings_aria2_rpc),
                                subtitle = stringResource(R.string.settings_aria2_rpc_desc),
                                checked = settings.isAria2RpcEnabled,
                                onCheckedChange = { onSetSetting("isAria2RpcEnabled", it) },
                            )
                            SwitchSettingRow(
                                title = stringResource(R.string.settings_check_update_at_startup),
                                subtitle = stringResource(R.string.settings_check_update_at_startup_desc),
                                checked = settings.shouldCheckUpdateAtStartup,
                                onCheckedChange = { onSetSetting("shouldCheckUpdateAtStartup", it) },
                            )
                        }
                    }

                    OobeStep.RUNTIMES -> OobeStepContent(
                        R.string.settings_section_runtimes,
                        R.string.settings_summary_runtimes,
                    ) {
                        SettingSection { RuntimeRows() }
                    }

                    OobeStep.COMPLETE -> CompleteContent()
                }
            }

            OobeNavigation(
                step = OobeStep.entries[pagerState.currentPage],
                onBack = back,
                onNext = { scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) } },
                onFinish = onFinish,
            )
        }
    }
}

@Composable
private fun OobeNavigation(
    step: OobeStep,
    onBack: () -> Unit,
    onNext: () -> Unit,
    onFinish: (Offset) -> Unit,
) {
    // 两个分支互斥，track 只挂在一个按钮上，点击时读到的就是它自己的中心
    var finishCenter by remember { mutableStateOf(Offset.Zero) }
    val track = Modifier.onGloballyPositioned { finishCenter = it.boundsInRoot().center }

    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 24.dp, vertical = 16.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        when (step) {
            OobeStep.WELCOME -> {
                TextButton(onClick = { onFinish(finishCenter) }, modifier = track) {
                    Text(stringResource(R.string.oobe_skip))
                }
                Button(onClick = onNext) {
                    Text(stringResource(R.string.oobe_start))
                }
            }
            OobeStep.COMPLETE -> {
                Spacer(Modifier.weight(1f))
                FloatingActionButton(
                    onClick = { onFinish(finishCenter) },
                    modifier = track.size(64.dp),
                    shape = CircleShape,
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                ) {
                    Icon(
                        painterResource(R.drawable.ic_check),
                        contentDescription = stringResource(R.string.oobe_finish),
                    )
                }
                Spacer(Modifier.weight(1f))
            }
            else -> {
                TextButton(onClick = onBack) {
                    Text(stringResource(R.string.oobe_back))
                }
                PageIndicator(step)
                Button(onClick = onNext) {
                    Text(stringResource(R.string.oobe_next))
                }
            }
        }
    }
}

@Composable
private fun PageIndicator(current: OobeStep) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OobeStep.entries.forEach { step ->
            val color by animateColorAsState(
                if (step == current) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.outlineVariant,
            )
            Canvas(Modifier.size(8.dp)) { drawCircle(color) }
        }
    }
}

@Composable
private fun OobeStepContent(
    titleRes: Int,
    descriptionRes: Int,
    content: @Composable ColumnScope.() -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        Column(
            Modifier
                .verticalScroll(rememberScrollState())
                .heightIn(min = maxHeight)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                stringResource(titleRes),
                style = MaterialTheme.typography.headlineSmall,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
            Spacer(Modifier.height(4.dp))
            Text(
                stringResource(descriptionRes),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
            Spacer(Modifier.height(16.dp))
            content()
        }
    }
}

@Composable
private fun WelcomeContent() {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Image(
            painterResource(R.drawable.ghost_logo),
            contentDescription = null,
            modifier = Modifier.size(88.dp),
        )
        Spacer(Modifier.height(24.dp))
        Text(
            stringResource(R.string.oobe_welcome_title),
            style = MaterialTheme.typography.headlineMedium,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            stringResource(R.string.oobe_welcome_subtitle),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun CompleteContent() {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            painterResource(R.drawable.ic_check),
            contentDescription = null,
            modifier = Modifier.size(72.dp),
            tint = MaterialTheme.colorScheme.primary,
        )
        Spacer(Modifier.height(24.dp))
        Text(
            stringResource(R.string.oobe_complete_title),
            style = MaterialTheme.typography.headlineMedium,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            stringResource(R.string.oobe_complete_subtitle),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}
