package com.xychr.ghostdownloader.model

import androidx.compose.runtime.Immutable
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

object TaskStatus {
    const val RUNNING = "RUNNING"
    const val WAITING = "WAITING"
    const val PAUSED = "PAUSED"
    const val COMPLETED = "COMPLETED"
    const val FAILED = "FAILED"
}

interface TaskActionSource {
    val status: String
    val canPause: Boolean
    val canStop: Boolean
    val hasOutputFile: Boolean
    val isOutputFolder: Boolean
}

@Serializable
data class TaskError(
    val message: String,
    val params: Map<String, String> = emptyMap(),
)

@Immutable
@Serializable
data class TaskUiState(
    val id: String = "",
    val packId: String = "",
    override val canPause: Boolean = false,
    val canEdit: Boolean = false,
    val categoryId: String = "",
    val outputPath: String = "",
    val outputFolder: String = "",
    override val hasOutputFile: Boolean = false,
    override val isOutputFolder: Boolean = false,
    val selectedFileCount: Int = 0,
    val name: String = "",
    val url: String = "",
    val progress: Double = 0.0,
    val speed: Long = 0,
    val received: Long = 0,
    override val status: String = "",
    val fileSize: Long = 0,
    val fileCount: Int = 0,
    val createdAt: Long = 0,
    val completedAt: Long = 0,
    val error: TaskError? = null,
    val progressMode: String = "determinate",
    val statusText: String = "",
    val secondarySpeed: Long = 0,
    override val canStop: Boolean = false,
    val fileSelectKind: String = "",
    val canSelectFiles: Boolean = true,
    val packFields: JsonObject = JsonObject(emptyMap()),
) : TaskActionSource

val TaskUiState.isActive: Boolean
    get() = status != TaskStatus.COMPLETED

val TaskUiState.isFinished: Boolean
    get() = status == TaskStatus.COMPLETED

@Serializable
data class TaskSnapshot(
    val progress: Double = 0.0,
    val speed: Long = 0,
    val received: Long = 0,
)

@Immutable
@Serializable
data class TaskDetail(
    val id: String = "",
    val packId: String = "",
    override val canPause: Boolean = false,
    val categoryId: String = "",
    val outputPath: String = "",
    override val hasOutputFile: Boolean = false,
    override val isOutputFolder: Boolean = false,
    val name: String = "",
    val url: String = "",
    val progress: Double = 0.0,
    val speed: Long = 0,
    val received: Long = 0,
    override val status: String = "",
    val fileSize: Long = 0,
    val createdAt: Long = 0,
    val completedAt: Long = 0,
    val canEdit: Boolean = false,
    val canRename: Boolean = false,
    val outputFolder: String = "",
    val error: TaskError? = null,
    val files: List<TaskFile> = emptyList(),
    val progressMode: String = "determinate",
    val statusText: String = "",
    val secondarySpeed: Long = 0,
    override val canStop: Boolean = false,
    val fileSelectKind: String = "",
    val canSelectFiles: Boolean = true,
    val packFields: JsonObject = JsonObject(emptyMap()),
) : TaskActionSource

@Serializable
data class TaskFile(
    val index: Int = 0,
    val categoryId: String = "",
    val path: String = "",
    val groups: List<String> = emptyList(),
    val size: Long = 0,
    val isSelected: Boolean = true,
    val isCompleted: Boolean = false,
    val progress: Double = 0.0,
    val startTime: Int? = null,
    val endTime: Int? = null,
)
