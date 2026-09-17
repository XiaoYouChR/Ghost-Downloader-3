package com.xychr.ghostdownloader.model

import androidx.compose.runtime.Immutable
import kotlinx.serialization.Serializable

@Immutable
@Serializable
data class HashState(
    val taskId: String = "",
    val algorithm: String = "",
    val progress: Int = 0,
    val digest: String = "",
    val error: TaskError? = null,
) {
    val isRunning: Boolean get() = taskId.isNotEmpty() && digest.isEmpty() && error == null
}
