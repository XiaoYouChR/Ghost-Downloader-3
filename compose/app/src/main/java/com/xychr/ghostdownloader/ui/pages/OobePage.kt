package com.xychr.ghostdownloader.ui.pages

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.provider.Settings as SystemSettings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.pages.settings.toFolderPath
import kotlinx.coroutines.launch

private const val PAGE_COUNT = 4

@Composable
fun OobePage(
    downloadFolder: String,
    onSetSetting: (String, Any) -> Unit,
    onFinish: (center: Offset) -> Unit,
) {
    val scope = rememberCoroutineScope()
    val pagerState = rememberPagerState { PAGE_COUNT }

    Column(
        Modifier
            .fillMaxSize()
            .windowInsetsPadding(WindowInsets.safeDrawing)
            .navigationBarsPadding(),
    ) {
        HorizontalPager(
            state = pagerState,
            userScrollEnabled = false,
            modifier = Modifier.weight(1f),
        ) { page ->
            when (page) {
                0 -> WelcomeContent()
                1 -> PermissionsContent()
                2 -> BasicSettingsContent(downloadFolder, onSetSetting)
                3 -> CompleteContent()
            }
        }

        OobeNavigation(
            currentPage = pagerState.currentPage,
            onBack = { scope.launch { pagerState.animateScrollToPage(pagerState.currentPage - 1) } },
            onNext = { scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) } },
            onFinish = onFinish,
        )
    }
}

@Composable
private fun OobeNavigation(
    currentPage: Int,
    onBack: () -> Unit,
    onNext: () -> Unit,
    onFinish: (center: Offset) -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 24.dp, vertical = 16.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        when (currentPage) {
            0 -> {
                TextButton(onClick = { onFinish(Offset.Zero) }) {
                    Text(stringResource(R.string.oobe_skip))
                }
                Button(onClick = onNext) {
                    Text(stringResource(R.string.oobe_start))
                }
            }
            in 1 until PAGE_COUNT - 1 -> {
                TextButton(onClick = onBack) {
                    Text(stringResource(R.string.oobe_back))
                }
                PageIndicator(currentPage)
                Button(onClick = onNext) {
                    Text(stringResource(R.string.oobe_next))
                }
            }
            PAGE_COUNT - 1 -> {
                Spacer(Modifier.weight(1f))
                FinishButton(onFinish)
                Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun FinishButton(onFinish: (center: Offset) -> Unit) {
    var buttonCenter by remember { mutableStateOf(Offset.Zero) }

    Button(
        onClick = { onFinish(buttonCenter) },
        modifier = Modifier.onGloballyPositioned { coords ->
            val pos = coords.positionInWindow()
            buttonCenter = Offset(
                pos.x + coords.size.width / 2f,
                pos.y + coords.size.height / 2f,
            )
        },
    ) {
        Text(stringResource(R.string.oobe_finish))
    }
}

@Composable
private fun PageIndicator(currentPage: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        repeat(PAGE_COUNT) { index ->
            val color by animateColorAsState(
                if (index == currentPage) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.outlineVariant,
            )
            androidx.compose.foundation.Canvas(Modifier.size(8.dp)) {
                drawCircle(color)
            }
        }
    }
}

// ---- Page 0: Welcome ----

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

// ---- Page 1: Permissions ----

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun PermissionsContent() {
    val context = LocalContext.current

    var hasStorageAccess by remember { mutableStateOf(false) }
    var hasNotificationAccess by remember { mutableStateOf(false) }
    var isBatteryUnrestricted by remember { mutableStateOf(false) }

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        hasStorageAccess = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Environment.isExternalStorageManager()
        } else {
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.WRITE_EXTERNAL_STORAGE,
            ) == android.content.pm.PackageManager.PERMISSION_GRANTED
        }
        hasNotificationAccess = NotificationManagerCompat.from(context).areNotificationsEnabled()
        isBatteryUnrestricted = context.getSystemService(PowerManager::class.java)
            .isIgnoringBatteryOptimizations(context.packageName)
    }

    Column(
        Modifier.fillMaxSize().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            stringResource(R.string.oobe_permissions_title),
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(4.dp))
        Text(
            stringResource(R.string.oobe_permissions_subtitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(24.dp))

        SettingSection {
            PermissionRow(
                icon = R.drawable.ic_folder,
                title = stringResource(R.string.settings_storage_access),
                isGranted = hasStorageAccess,
                onClick = {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                        val intent = Intent(
                            SystemSettings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                            "package:${context.packageName}".toUri(),
                        )
                        runCatching { context.startActivity(intent) }.onFailure {
                            runCatching {
                                context.startActivity(
                                    Intent(SystemSettings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION),
                                )
                            }
                        }
                    }
                },
            )
            PermissionRow(
                icon = R.drawable.ic_notification_download,
                title = stringResource(R.string.settings_notifications),
                isGranted = hasNotificationAccess,
                onClick = {
                    val intent = Intent(SystemSettings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(SystemSettings.EXTRA_APP_PACKAGE, context.packageName)
                    runCatching { context.startActivity(intent) }
                },
            )
            PermissionRow(
                icon = R.drawable.ic_download,
                title = stringResource(R.string.settings_battery_unrestricted),
                subtitle = stringResource(R.string.settings_battery_unrestricted_desc),
                isGranted = isBatteryUnrestricted,
                onClick = {
                    val request = Intent(
                        SystemSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        "package:${context.packageName}".toUri(),
                    )
                    runCatching { context.startActivity(request) }.onFailure {
                        runCatching {
                            context.startActivity(
                                Intent(SystemSettings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS),
                            )
                        }
                    }
                },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun PermissionRow(
    icon: Int,
    title: String,
    isGranted: Boolean,
    onClick: () -> Unit,
    subtitle: String? = null,
) {
    val statusText = stringResource(
        if (isGranted) R.string.permission_granted else R.string.permission_denied,
    )
    val displaySubtitle = if (isGranted) statusText else (subtitle ?: statusText)

    ActionSettingRow(
        title = title,
        subtitle = displaySubtitle,
        leading = { Icon(painterResource(icon), contentDescription = null) },
        colors = if (isGranted) ListItemDefaults.segmentedColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            supportingContentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            leadingContentColor = MaterialTheme.colorScheme.onPrimaryContainer,
        ) else ListItemDefaults.segmentedColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow,
        ),
        onClick = onClick,
    )
}

// ---- Page 2: Basic Settings ----

@Composable
private fun BasicSettingsContent(
    downloadFolder: String,
    onSetSetting: (String, Any) -> Unit,
) {
    val folderPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri -> uri?.let { onSetSetting("downloadFolder", it.toFolderPath()) } }

    Column(
        Modifier.fillMaxSize().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            stringResource(R.string.oobe_basic_title),
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(4.dp))
        Text(
            stringResource(R.string.oobe_basic_subtitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(24.dp))

        SettingSection {
            ActionSettingRow(
                title = stringResource(R.string.settings_download_folder),
                subtitle = downloadFolder,
                leading = { Icon(painterResource(R.drawable.ic_folder), contentDescription = null) },
                onClick = { folderPicker.launch(null) },
            )
        }
    }
}

// ---- Page 3: Complete ----

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
