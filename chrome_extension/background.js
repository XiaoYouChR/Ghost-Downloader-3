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
                // 保存版本信息到 chrome.storage.local
                chrome.storage.local.set({ ClientVersion: message.ClientVersion }, function() {
                    // console.log("ClientVersion stored:", message.ClientVersion);
                });
                chrome.storage.local.set({ LatestExtensionVersion: message.LatestExtensionVersion }, function() {
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
    chrome.action.setBadgeBackgroundColor({ color: badgeColor });
    chrome.action.setBadgeText({ text: badgeText });
}

// 更新扩展状态
function updateStatus(connected) {
    chrome.storage.local.set({ isConnected: connected }, () => {
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

// 监听下载开始事件并阻止下载
chrome.downloads.onCreated.addListener((downloadItem) => {
    if (downloadItem.state === "in_progress") {
        chrome.storage.local.get(["shouldDisableExtension"], (result) => {
            if (!result.shouldDisableExtension && isConnected && socket.readyState === WebSocket.OPEN) {
                console.log("Download started: ", downloadItem);
                if (downloadItem.url.startsWith("http")) {
                    cancelDownload(downloadItem);
                }
            }
        });
    }
});

// 取消下载并发送下载信息到服务器
function cancelDownload(downloadItem) {
    chrome.downloads.cancel(downloadItem.id, () => {
        console.log(`Download cancelled: ${downloadItem.id}`);

        let url = downloadItem.url, cookiesData = [], cookieString = '';

        chrome.cookies.getAll( {url}, (cookies) => {
            if(cookies){
                cookiesData=cookies
            }else{
                cookiesData=''
            }
        });

        cookieString = '';
        for(let i=0;i<cookiesData.length;i++){
            cookieString += cookiesData[i].name + '=' + cookiesData[i].value + '; ';
        }

        const downloadInfo = {
            cookiesData: cookieString,
            id: downloadItem.id,
            url: downloadItem.url,
            mime: downloadItem.mime,
            fileSize: downloadItem.fileSize,
            startTime: downloadItem.startTime,
            state: downloadItem.state,
        };

        sendDownloadInfo(downloadInfo);
    });
}

// 发送下载信息到服务器
function sendDownloadInfo(downloadInfo) {
    if (isConnected && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(downloadInfo));
    } else {
        console.error("WebSocket is not open");
    }
}

// 启动 WebSocket 连接
connectWebSocket();

// 在扩展启动时检查禁用状态
chrome.storage.local.get(["shouldDisableExtension"], (result) => {
    shouldDisableExtension = result.shouldDisableExtension || false;
    console.log("Extension disable status:", shouldDisableExtension);
});
