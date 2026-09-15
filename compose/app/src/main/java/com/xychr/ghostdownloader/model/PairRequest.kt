package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable

/**
 * 待决的浏览器配对请求。有始有终——用户批准或拒绝后消解，引擎发 null 收尾。
 * peerAddress 是判断"这是不是我刚发起的配对"的唯一依据，别省。
 */
@Serializable
data class PairRequest(
    val requestId: String = "",
    val clientKind: String = "",
    val extensionVersion: String = "",
    val peerAddress: String = "",
)
