package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import kotlinx.serialization.json.JsonObject

interface PackUi {
    val packId: String

    val settingsTitle: Int get() = 0

    val searchItems: List<Pair<Int, Int?>> get() = emptyList()

    val settingsContent: (@Composable (config: JsonObject, keys: PackKeys, set: (String, Any) -> Unit) -> Unit)?
        get() = null

    val taskExtra: (@Composable (packFields: JsonObject) -> Unit)?
        get() = null

    val detailExtra: (@Composable (packFields: JsonObject) -> Unit)?
        get() = null

    val draftExtra: (@Composable (packFields: JsonObject) -> Unit)?
        get() = null

    val editExtra: (@Composable (packFields: JsonObject) -> Unit)?
        get() = null
}
