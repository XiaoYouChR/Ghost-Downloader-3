package com.xychr.ghostdownloader.engine

import com.xychr.ghostdownloader.model.Notice
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class EngineFlowsTest {

    @Test fun burstOnStateChannelStopsAtNewestFrame() = runTest {
        val flows = EngineFlows()
        val seen = mutableListOf<String>()
        val subscriber = launch {
            flows.observe("tasks").collect {
                seen += it
                delay(1_000)
            }
        }
        runCurrent()

        flows.setState("tasks", "[t1]")
        flows.setState("tasks", "[t1,t2]")
        flows.setState("tasks", "[t1,t2,t3]")

        advanceUntilIdle()
        assertEquals("[t1,t2,t3]", seen.last())
        subscriber.cancel()
    }

    @Test fun lateSubscriberSeesCurrentStateNotFirstFrame() = runTest {
        val flows = EngineFlows()
        flows.setState("tasks", "[t1]")
        flows.setState("tasks", "[t1,t2,t3]")

        assertEquals("[t1,t2,t3]", flows.observe("tasks").first())
    }

    @Test fun lateSubscriberSeesNoEvent() = runTest {
        val flows = EngineFlows()
        flows.sendEvent("notice", "n1")

        val seen = mutableListOf<String>()
        val subscriber = launch { flows.observeEvent("notice").collect { seen += it } }
        runCurrent()

        assertEquals(emptyList<String>(), seen)
        subscriber.cancel()
    }

    @Test fun laggingSubscriberKeepsEveryEvent() = runTest {
        val flows = EngineFlows()
        val seen = mutableListOf<String>()
        val subscriber = launch {
            flows.observeEvent("notice").collect {
                seen += it
                delay(1_000)
            }
        }
        runCurrent()

        flows.sendEvent("notice", "n1")
        flows.sendEvent("notice", "n2")
        flows.sendEvent("notice", "n3")

        advanceUntilIdle()
        assertEquals(listOf("n1", "n2", "n3"), seen)
        subscriber.cancel()
    }

    @Test fun keyCannotSwitchBetweenStateAndEvent() {
        val flows = EngineFlows()
        flows.setState("tasks", "[]")

        assertThrows(IllegalStateException::class.java) { flows.sendEvent("tasks", "[]") }
    }

    @Test fun engineRepositoryDecodesNoticeThroughEventChannel() = runTest {
        val seen = mutableListOf<Notice>()
        val subscriber = launch {
            EngineRepository.observeEvent<Notice>("notice").collect { seen += it }
        }
        runCurrent()

        EngineRepository.sendEvent("notice", """{"kind":"extensionUpdated","version":"1"}""")
        advanceUntilIdle()

        assertEquals(listOf<Notice>(Notice.ExtensionUpdated("1")), seen)
        subscriber.cancel()
    }
}
