package com.xychr.ghostdownloader.engine

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json
import java.util.concurrent.ConcurrentHashMap

@PublishedApi internal object EngineFlows {

    @PublishedApi internal val json = Json { ignoreUnknownKeys = true }
    private val streams = ConcurrentHashMap<String, MutableSharedFlow<String>>()

    @PublishedApi internal fun streamOf(key: String): MutableSharedFlow<String> =
        streams.getOrPut(key) { MutableSharedFlow(replay = 1) }

    @JvmStatic
    fun emit(key: String, value: String) {
        streamOf(key).tryEmit(value)
    }

    inline fun <reified T> stream(key: String): Flow<T> =
        streamOf(key).map { json.decodeFromString(it) }
}
