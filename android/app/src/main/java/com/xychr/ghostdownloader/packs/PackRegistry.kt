package com.xychr.ghostdownloader.packs

import android.util.Log
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

object PackRegistry {

    data class PackEntry(val packUi: PackUi, val configClass: String?)

    private val entries = mutableMapOf<String, PackEntry>()

    fun load(json: String) {
        val root = kotlinx.serialization.json.Json.parseToJsonElement(json).jsonObject
        for ((packId, value) in root) {
            val obj = value.jsonObject
            val uiClass = obj["uiClass"]?.jsonPrimitive?.content ?: continue
            val configClass = obj["configClass"]?.jsonPrimitive?.content
            try {
                val clazz = Class.forName(uiClass)
                val packUi = clazz.getDeclaredField("INSTANCE").get(null) as? PackUi ?: continue
                entries[packId] = PackEntry(packUi, configClass)
            } catch (e: Exception) {
                Log.w("PackRegistry", "Failed to load PackUi for $packId: $uiClass", e)
            }
        }
    }

    operator fun get(packId: String): PackUi? = entries[packId]?.packUi

    fun entry(packId: String): PackEntry? = entries[packId]

    fun withSettings(): List<PackEntry> =
        entries.values.filter { it.configClass != null && it.packUi.settingsContent != null }
}
