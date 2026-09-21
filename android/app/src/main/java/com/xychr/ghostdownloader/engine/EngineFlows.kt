package com.xychr.ghostdownloader.engine

import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import java.util.concurrent.ConcurrentHashMap

class EngineFlows {

    private enum class Kind { STATE, EVENT }

    private class Slot(val kind: Kind, val flow: MutableSharedFlow<String>)

    private val channels = ConcurrentHashMap<String, Slot>()

    fun setState(key: String, value: String) {
        channel(key, Kind.STATE).tryEmit(value)
    }

    fun sendEvent(key: String, value: String) {
        channel(key, Kind.EVENT).tryEmit(value)
    }

    fun observe(key: String): Flow<String> = channel(key, Kind.STATE)

    fun observeEvent(key: String): Flow<String> = channel(key, Kind.EVENT)

    private fun channel(key: String, kind: Kind): MutableSharedFlow<String> {
        val channel = channels.computeIfAbsent(key) { Slot(kind, buildFlow(kind)) }
        check(channel.kind == kind) { "\"$key\" is already a ${channel.kind} channel" }
        return channel.flow
    }

    private fun buildFlow(kind: Kind): MutableSharedFlow<String> = when (kind) {
        Kind.STATE -> MutableSharedFlow(replay = 1, onBufferOverflow = BufferOverflow.DROP_OLDEST)
        Kind.EVENT -> MutableSharedFlow(
            extraBufferCapacity = 8,
            onBufferOverflow = BufferOverflow.DROP_OLDEST,
        )
    }
}
