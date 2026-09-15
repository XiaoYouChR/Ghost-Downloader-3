package com.xychr.ghostdownloader.bili

import androidx.lifecycle.ViewModelStore
import com.xychr.ghostdownloader.features.bili_pack.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class BilibiliAccountViewModelTest {
    @Before fun setMain() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun clearMain() { Dispatchers.resetMain() }

    @Test fun commandsSendPackActionNames() = runBlocking {
        val calls = mutableListOf<Pair<String, List<Any>>>()
        val store = ViewModelStore()
        val viewModel = BilibiliAccountViewModel(
            send = { action, args -> calls.add(action to args) },
            accountFlow = emptyFlow(),
            qrFlow = emptyFlow(),
        )
        store.put("bili", viewModel)
        try {
            viewModel.startQrLogin()
            viewModel.cancelQrLogin()
            viewModel.setCookie("SESSDATA=x")
            viewModel.logout()

            assertEquals(
                listOf("startQrLogin", "cancelQrLogin", "setCookie", "logout"),
                calls.map { it.first },
            )
            assertEquals(emptyList<Any>(), calls[0].second)
            assertEquals(emptyList<Any>(), calls[1].second)
            assertEquals(listOf("SESSDATA=x"), calls[2].second)
            assertEquals(emptyList<Any>(), calls[3].second)
        } finally { store.clear() }
    }
}
