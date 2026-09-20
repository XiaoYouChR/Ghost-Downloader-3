package com.xychr.ghostdownloader.ui.components.settings

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.ChoiceField
import com.xychr.ghostdownloader.ui.pages.settings.ClientProfiles

private sealed interface ProfileMode {
    data object Inherit : ProfileMode
    data object Auto : ProfileMode
    data object Raw : ProfileMode
    data object Custom : ProfileMode
}

private fun toMode(value: String, canInherit: Boolean): ProfileMode = when {
    canInherit && value.isEmpty() -> ProfileMode.Inherit
    value == "auto" || (!canInherit && value.isEmpty()) -> ProfileMode.Auto
    value == "raw" -> ProfileMode.Raw
    else -> ProfileMode.Custom
}

@Composable
fun ClientProfileRow(
    value: String,
    profiles: List<ClientProfiles>,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
    canInherit: Boolean = false,
    isEnabled: Boolean = true,
    globalProfile: String = "auto",
) {
    val mode = toMode(value, canInherit)
    val isCustom = mode is ProfileMode.Custom
    val family = profiles.firstOrNull { it.family == value || value in it.versions }
    var customValue by rememberSaveable {
        mutableStateOf(if (isCustom) value else profiles.firstOrNull()?.family.orEmpty())
    }
    LaunchedEffect(value) { if (isCustom) customValue = value }

    val modes = buildList {
        if (canInherit) add(ProfileMode.Inherit)
        add(ProfileMode.Auto)
        add(ProfileMode.Raw)
        if (profiles.isNotEmpty()) add(ProfileMode.Custom)
    }

    Column(modifier) {
        SettingSection {
            modes.forEach { m ->
                RadioSettingRow(
                    title = when (m) {
                        ProfileMode.Inherit -> stringResource(R.string.identity_profile_inherit)
                        ProfileMode.Auto -> stringResource(R.string.identity_profile_auto)
                        ProfileMode.Raw -> stringResource(R.string.identity_profile_raw)
                        ProfileMode.Custom -> stringResource(R.string.identity_profile_custom)
                    },
                    subtitle = if (m is ProfileMode.Inherit) stringResource(
                        R.string.identity_profile_current_global, clientProfileLabel(globalProfile),
                    ) else null,
                    isSelected = mode == m,
                    isEnabled = isEnabled,
                    onClick = {
                        when (m) {
                            ProfileMode.Inherit -> onSelect("")
                            ProfileMode.Auto -> onSelect("auto")
                            ProfileMode.Raw -> onSelect("raw")
                            ProfileMode.Custom -> onSelect(
                                customValue.ifEmpty { profiles.first().family },
                            )
                        }
                    },
                )
            }
        }

        AnimatedVisibility(isCustom, enter = expandVertically(), exit = shrinkVertically()) {
            Column(
                Modifier.padding(horizontal = 16.dp).padding(bottom = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                ChoiceField(
                    stringResource(R.string.identity_profile_family),
                    family?.family ?: value,
                    profiles.map { it.family to toProfileFamilyLabel(it.family) },
                    onSelect,
                    isEnabled = isEnabled,
                )
                if (family != null) {
                    ChoiceField(
                        stringResource(R.string.identity_profile_version),
                        value,
                        listOf(
                            family.family to stringResource(
                                R.string.identity_profile_latest,
                                toProfileFamilyLabel(family.family),
                            ),
                        ) + family.versions.map { it to toProfileVersionLabel(it) },
                        onSelect,
                        isEnabled = isEnabled,
                    )
                } else {
                    Text(
                        stringResource(R.string.identity_profile_unsupported),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }
    }
}

fun matchClientProfile(
    value: String,
    profiles: List<ClientProfiles>,
    canInherit: Boolean = false,
): Boolean =
    (canInherit && value.isEmpty()) || value in listOf("auto", "raw") ||
        profiles.any { it.family == value || value in it.versions }

@Composable
fun clientProfileLabel(value: String): String = when (value) {
    "" -> stringResource(R.string.identity_profile_inherit)
    "auto" -> stringResource(R.string.identity_profile_auto)
    "raw" -> stringResource(R.string.identity_profile_raw)
    else -> if (value.any(Char::isDigit)) toProfileVersionLabel(value)
    else stringResource(R.string.identity_profile_latest, toProfileFamilyLabel(value))
}

private fun toProfileVersionLabel(value: String): String =
    value.replace(Regex("(?<=[A-Za-z])(?=\\d)"), " ").replace('_', '.')

private fun toProfileFamilyLabel(family: String): String = when (family) {
    "chrome" -> "Chrome"
    "edge" -> "Edge"
    "firefox" -> "Firefox"
    "firefox-android" -> "Firefox Android"
    "opera" -> "Opera"
    "safari" -> "Safari"
    "safari-ios" -> "Safari iOS"
    "safari-ipad" -> "Safari iPad"
    "okhttp" -> "OkHttp"
    else -> family
}
