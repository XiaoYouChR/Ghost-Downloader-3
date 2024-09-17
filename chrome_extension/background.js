// background.js

let socket;
let isConnected = false;
let shouldDisableExtension = false;

// 创建 WebSocket 连接
function connectWebSocket() {
    try {
        socket = new WebSocket("ws://localhost:14370");

        socket.onopen = () => {
            console.log("WebSocket connection opened");
            updateConnectionStatus(true);
        };

        socket.onerror = (error) => {
            console.log("WebSocket error: ", error);
            updateConnectionStatus(false);
        };

        socket.onclose = () => {
            console.log("WebSocket connection closed, retrying in 2500 microseconds");
            updateConnectionStatus(false);
            if (!shouldDisableExtension) {
                setTimeout(connectWebSocket, 2500);
            }
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

// 监听下载开始事件并阻止下载
chrome.downloads.onCreated.addListener((downloadItem) => {
    chrome.storage.local.get(["shouldDisableExtension"], (result) => {
        if (!result.shouldDisableExtension && isConnected && socket.readyState === WebSocket.OPEN) {
            console.log("Download started: ", downloadItem);
            cancelDownload(downloadItem);
        }
    });
});

// 取消下载并发送下载信息到服务器
function cancelDownload(downloadItem) {
    chrome.downloads.cancel(downloadItem.id, () => {
        console.log(`Download cancelled: ${downloadItem.id}`);

        const downloadInfo = {
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
