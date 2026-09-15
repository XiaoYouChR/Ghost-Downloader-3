package com.xychr.ghostdownloader.engine

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json
import java.util.concurrent.ConcurrentHashMap

@PublishedApi internal object EngineFlows {

    @PublishedApi internal val json = Json {
        ignoreUnknownKeys = true
        classDiscriminator = "kind"
    }
    private val streams = ConcurrentHashMap<String, MutableSharedFlow<String>>()

    /**
     * replay 是给状态流的——新订阅者要立刻拿到当前快照。事件流（notice）也走这里，
     * 但它全进程只有 Notices 一个订阅者且订阅后不再重订阅，重放窗口实际上是关着的。
     */
    @PublishedApi internal fun streamOf(key: String): MutableSharedFlow<String> =
        streams.getOrPut(key) { MutableSharedFlow(replay = 1) }

    @JvmStatic
    fun emit(key: String, value: String) {
        streamOf(key).tryEmit(value)
    }

    inline fun <reified T> stream(key: String): Flow<T> =
        streamOf(key).map { json.decodeFromString(it) }
}
