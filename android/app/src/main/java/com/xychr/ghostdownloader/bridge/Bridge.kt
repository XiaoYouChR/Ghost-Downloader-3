package com.xychr.ghostdownloader.bridge

import com.chaquo.python.PyObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json

@JvmInline
value class Encoded(@PublishedApi internal val value: String)

lateinit var bridge: Bridge
    private set

fun createBridge(python: PyObject, flows: BridgeFlows): Bridge {
    bridge = Bridge(python, flows)
    return bridge
}

class Bridge(
    private val python: PyObject,
    @PublishedApi internal val flows: BridgeFlows,
) {
    @PublishedApi internal val json = Json { ignoreUnknownKeys = true }

    @PublishedApi internal suspend fun request(name: String, vararg args: Any?): PyObject? {
        val unwrapped = Array(args.size) { i -> val a = args[i]; if (a is Encoded) a.value else a }
        return withContext(Dispatchers.IO) { python.callAttr("request", name, *unwrapped) }
    }

    suspend inline fun <reified T> query(name: String, vararg args: Any?): T =
        json.decodeFromString(request(name, *args)?.toString() ?: "null")

    suspend fun invoke(name: String, vararg args: Any?) {
        request(name, *args)
    }

    inline fun <reified T> observe(key: String): Flow<T> =
        flows.observe(key).map { json.decodeFromString(it) }

    inline fun <reified T> observeEvent(key: String): Flow<T> =
        flows.observeEvent(key).map { json.decodeFromString(it) }

    inline fun <reified T> encode(value: T): Encoded = Encoded(json.encodeToString(value))
}
