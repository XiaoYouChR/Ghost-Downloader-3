package com.xychr.ghostdownloader.engine

import com.chaquo.python.PyObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json

@JvmInline
value class Encoded(@PublishedApi internal val value: String)

lateinit var engineRepository: EngineRepository
    private set

fun createEngineRepository(engine: PyObject, flows: EngineFlows): EngineRepository {
    engineRepository = EngineRepository(engine, flows)
    return engineRepository
}

class EngineRepository(
    private val engine: PyObject,
    @PublishedApi internal val flows: EngineFlows,
) {
    @PublishedApi internal val json = Json { ignoreUnknownKeys = true }

    @PublishedApi internal suspend fun callEngine(name: String, vararg args: Any?): PyObject? {
        val unwrapped = Array(args.size) { i -> val a = args[i]; if (a is Encoded) a.value else a }
        return withContext(Dispatchers.IO) { engine.callAttr(name, *unwrapped) }
    }

    suspend inline fun <reified T> query(name: String, vararg args: Any?): T =
        json.decodeFromString(callEngine(name, *args)?.toString() ?: "null")

    suspend fun invoke(name: String, vararg args: Any?) {
        callEngine(name, *args)
    }

    inline fun <reified T> observe(key: String): Flow<T> =
        flows.observe(key).map { json.decodeFromString(it) }

    inline fun <reified T> observeEvent(key: String): Flow<T> =
        flows.observeEvent(key).map { json.decodeFromString(it) }

    inline fun <reified T> encode(value: T): Encoded = Encoded(json.encodeToString(value))
}
