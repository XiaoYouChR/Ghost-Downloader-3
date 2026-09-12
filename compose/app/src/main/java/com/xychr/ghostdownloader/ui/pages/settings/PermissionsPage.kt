package com.xychr.ghostdownloader.ui.pages.settings
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.navigation.*
import com.xychr.ghostdownloader.ui.components.*
import com.xychr.ghostdownloader.service.*

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.provider.Settings as SystemSettings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage

@Composable
fun PermissionsPage(onBack: () -> Unit) {
    val context = LocalContext.current
    var hasStorageAccess by remember { mutableStateOf(false) }
    var hasNotificationAccess by remember { mutableStateOf(false) }
    var isBatteryUnrestricted by remember { mutableStateOf(false) }
    var canInstallPackages by remember { mutableStateOf(false) }

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        hasStorageAccess = context.hasStorageAccess()
        hasNotificationAccess = NotificationManagerCompat.from(context).areNotificationsEnabled()
        isBatteryUnrestricted = context.isBatteryUnrestricted()
        canInstallPackages = context.packageManager.canRequestPackageInstalls()
    }

    SettingsPage(stringResource(R.string.settings_section_permissions), onBack) {
        SettingSection {
            ActionSettingRow(
                title = stringResource(R.string.settings_storage_access),
                subtitle = stringResource(grantedLabel(hasStorageAccess)),
                onClick = { context.openStorageAccessSettings() },
            )
            ActionSettingRow(
                title = stringResource(R.string.settings_notifications),
                subtitle = stringResource(grantedLabel(hasNotificationAccess)),
                onClick = { context.openNotificationSettings() },
            )
            ActionSettingRow(
                title = stringResource(R.string.settings_battery_unrestricted),
                subtitle = stringResource(
                    if (isBatteryUnrestricted) R.string.permission_granted
                    else R.string.settings_battery_unrestricted_desc
                ),
                onClick = { context.requestBatteryUnrestricted() },
            )
            ActionSettingRow(
                title = stringResource(R.string.settings_install_packages),
                subtitle = stringResource(
                    if (canInstallPackages) R.string.permission_granted
                    else R.string.settings_install_packages_desc
                ),
                onClick = { context.openInstallPackagesSettings() },
            )
        }
    }
}

private fun grantedLabel(granted: Boolean) =
    if (granted) R.string.permission_granted else R.string.permission_denied

private fun Context.hasStorageAccess(): Boolean =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        Environment.isExternalStorageManager()
    } else {
        ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE) ==
            PackageManager.PERMISSION_GRANTED
    }

private fun Context.openStorageAccessSettings() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        val perApp = Intent(
            SystemSettings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
            "package:$packageName".toUri(),
        )
        if (start(perApp)) return
        if (start(Intent(SystemSettings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))) return
    }
    start(appDetailsIntent())
}

/** 灭屏进 Doze 后系统会挂起网络，白名单是文档给出的唯一豁免。 */
private fun Context.isBatteryUnrestricted(): Boolean =
    getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)

private fun Context.requestBatteryUnrestricted() {
    val request = Intent(
        SystemSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
        "package:$packageName".toUri(),
    )
    if (!start(request)) start(Intent(SystemSettings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
}

private fun Context.openNotificationSettings() {
    val intent = Intent(SystemSettings.ACTION_APP_NOTIFICATION_SETTINGS)
        .putExtra(SystemSettings.EXTRA_APP_PACKAGE, packageName)
    if (!start(intent)) start(appDetailsIntent())
}

private fun Context.appDetailsIntent() =
    Intent(SystemSettings.ACTION_APPLICATION_DETAILS_SETTINGS, "package:$packageName".toUri())

private fun Context.openInstallPackagesSettings() {
    val intent = Intent(
        SystemSettings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
        "package:$packageName".toUri(),
    )
    if (!start(intent)) start(appDetailsIntent())
}

// 这些 Settings 页面在部分设备上不存在，官方文档要求调用方自行兜底
private fun Context.start(intent: Intent): Boolean = runCatching {
    startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}.isSuccess
