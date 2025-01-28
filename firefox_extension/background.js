// background.js

let socket;
let isConnected = false;
let shouldDisableExtension = false;
let heartbeatInterval = null;

// 创建 WebSocket 连接
function connectWebSocket() {
    try {
        socket = new WebSocket("ws://localhost:14370");

        socket.onopen = () => {
            console.log("WebSocket connection opened");
            updateConnectionStatus(true);
            startHeartbeat();
        };

        socket.onmessage = function(event) {
            const message = JSON.parse(event.data);
            // console.log("Received message", message.ClientVersion, message.LatestExtensionVersion);
            if (message.type === "version") {
                // 保存版本信息到 browser.storage.local
                browser.storage.local.set({ ClientVersion: message.ClientVersion }, function() {
                    // console.log("ClientVersion stored:", message.ClientVersion);
                });
                browser.storage.local.set({ LatestExtensionVersion: message.LatestExtensionVersion }, function() {
                    // console.log("LatestExtensionVersion stored:", message.LatestExtensionVersion);
                });
            } else {
                console.log("Received message:", event.data);
            }
        };

        socket.onerror = (error) => {
            console.log("WebSocket error: ", error);
            updateConnectionStatus(false);
            stopHeartbeat(); // 关闭连接时停止心跳
        };

        socket.onclose = () => {
            console.log("WebSocket connection closed, retrying in 2500 microseconds");
            updateConnectionStatus(false);
            if (!shouldDisableExtension) {
                setTimeout(connectWebSocket, 2500);
            }
            stopHeartbeat(); // 关闭连接时停止心跳
        };
    } catch (e) {
        console.log("Exception in WebSocket connection: ", e);
        setTimeout(connectWebSocket, 2500);
    }
}

// 更新连接状态并更新扩展状态和徽章
function updateConnectionStatus(connected) {
    isConnected = connected;
    updateBadge(connected ? "connected" : "disconnected");
    updateStatus(connected);
}

// 更新扩展图标徽章
function updateBadge(status) {
    const badgeColor = (status === "connected") ? "green" : "pink";
    const badgeText = (status === "connected") ? "√" : "×";
    browser.browserAction.setBadgeBackgroundColor({ color: badgeColor });
    browser.browserAction.setBadgeText({ text: badgeText });

}

// 更新扩展状态
function updateStatus(connected) {
    browser.storage.local.set({ isConnected: connected }, () => {
        console.log(`Status updated: ${connected ? "Connected" : "Disconnected"}`);
    });
}

// 启动心跳机制
function startHeartbeat() {
    if (!heartbeatInterval) { // 检查是否已有定时器
        heartbeatInterval = setInterval(() => {
            if (socket.readyState === WebSocket.OPEN) {
                try {
                    socket.send(JSON.stringify({ type: 'heartbeat', timestamp: Date.now() }));
                    console.log("Heartbeat sent");
                } catch (error) {
                    console.error("Error sending heartbeat:", error); // 仅记录错误，不影响执行
                }
            }
        }, 5000); // 每5秒发送一次心跳
    }
}

// 停止心跳机制
function stopHeartbeat() {
    if (heartbeatInterval) {
        clearInterval(heartbeatInterval); // 清除定时器
        heartbeatInterval = null; // 重置定时器变量
    }
}

// 根据浏览器类型添加不同的下载事件监听器, 监听下载开始事件并阻止下载
browser.downloads.onCreated.addListener((downloadItem) => {
    if (downloadItem.state === "in_progress") {
        browser.storage.local.get(["shouldDisableExtension"], (result) => {
            if (!result.shouldDisableExtension && isConnected && socket.readyState === WebSocket.OPEN) {
                console.log("Download started: ", downloadItem);
                if (downloadItem.url.startsWith("http")) {
                    browser.downloads.cancel(downloadItem.id);
                    browser.downloads.erase({id: downloadItem.id})


                    // 从映射表中获取对应的请求头
                    const requestHeaders = requestHeadersMap.get(downloadItem.url) || {};

                    console.log(downloadItem.fileSize)

                    // 构造完整的请求信息
                    const requestInfo = {
                        url: downloadItem.url,
                        filename: downloadItem.filename.replaceAll("\\", "/").split('/').pop(),
                        referer: downloadItem.referrer || "",
                        headers: requestHeaders,
                    };

                    console.log("捕获到的下载请求信息:", requestInfo);

                    // 将请求信息发送到 WebSocket
                    sendDownloadInfo(requestInfo);

                    // 清空 requestHeadersMap
                    requestHeadersMap.clear();
                }
            }
        });
    }
})

let requestHeadersMap = new Map(); // 存储请求头信息的映射表

// 监听 onBeforeSendHeaders 事件，捕获请求头信息并转为字典形式
browser.webRequest.onBeforeSendHeaders.addListener(
    (details) => {
        // 将请求头数组转换为字典（键值对形式）
        const requestHeadersDict = details.requestHeaders.reduce((acc, header) => {
            acc[header.name.toLowerCase()] = header.value;
            return acc;
        }, {});

        // 存储请求头信息到映射表中，以请求 ID 为键
        requestHeadersMap.set(details.url, requestHeadersDict);
        console.log("Details url:", details.url);
    },
    {
        urls: ["<all_urls>"], // 监听所有请求
        types: ["main_frame", "sub_frame", "xmlhttprequest", "other"], // 资源类型
    },
    typeof browser !== 'undefined' ? ["requestHeaders"] : ["requestHeaders", "extraHeaders"]  // 根据浏览器类型添加不同的参数
);

// 修改 sendDownloadInfo 函数，将请求信息发送到 WebSocket
function sendDownloadInfo(requestInfo) {
    if (isConnected && socket.readyState === WebSocket.OPEN) {
        try {
            socket.send(JSON.stringify(requestInfo));
        } catch (error) {
            console.error("发送下载信息时发生错误:", error);
        }
    } else {
        console.error("WebSocket 未连接");
    }
}


// 启动 WebSocket 连接
connectWebSocket();

// 在扩展启动时检查禁用状态
browser.storage.local.get(["shouldDisableExtension"], (result) => {
    shouldDisableExtension = result.shouldDisableExtension || false;
    console.log("Extension disable status:", shouldDisableExtension);
});
