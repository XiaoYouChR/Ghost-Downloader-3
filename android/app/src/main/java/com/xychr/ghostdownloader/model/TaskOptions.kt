package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable

@Serializable
data class TaskOptions(
    val outputFolder: String,
    val url: String? = null,
    val headers: Map<String, String>? = null,
    val clientProfile: String? = null,
    val userAgent: String? = null,
    val subworkerCount: Int? = null,
    val recordLimit: String? = null,
    val decryptionKeys: List<String>? = null,
    val decryptionKeyFile: String? = null,
    val muxImports: List<String>? = null,
    val streams: List<DraftOption>? = null,
    val selectVideo: String? = null,
    val packId: String = "",
)

@Serializable
data class TaskEditResult(val needsConfirmation: Boolean = false)
