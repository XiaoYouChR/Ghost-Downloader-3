package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable

@Serializable
data class Settings(
    val downloadFolder: String = "",
    val maxTaskNum: Int = 3,
    val preBlockNum: Int = 8,
    val autoSpeedUp: Boolean = true,
    val maxReassignSize: Int = 512,
    val shouldPreserveLastModified: Boolean = false,
    val shouldUseSystemDns: Boolean = true,
    val shouldDraftTakenDownload: Boolean = false,
    val isSpeedLimitEnabled: Boolean = false,
    val speedLimitation: Int = 4194304,
    val shouldDeleteFilesOnRemove: Boolean = false,
    val shouldVerifySsl: Boolean = false,
    val proxyServer: String = "Auto",
    val isAria2RpcEnabled: Boolean = false,
    val aria2RpcPort: Int = 16800,
    val aria2RpcToken: String = "",
    val aria2RpcEmulateFingerprint: Boolean = false,
    val isBrowserExtensionEnabled: Boolean = false,
    val browserExtensionPort: Int = 14370,
)
