// background.js

let socket;
let isConnected = false;
let shouldDisableExtension = false;

// 创建 WebSocket 连接
function connectWebSocket() {
    try {
        socket = new WebSocket("ws://localhost:14370");

        socket.onopen = function () {
            console.log("WebSocket connection opened");
            isConnected = true;
            updateBadge("connected");
            updateStatus(true);
        };

        socket.onerror = function (error) {
            // 仅打印错误信息，而不抛出异常
            console.error("WebSocket error: ", error);
            isConnected = false;
            updateBadge("error");
            updateStatus(false);
        };

        socket.onclose = function () {
            // 打印连接关闭信息
            console.log("WebSocket connection closed, retrying in 5 seconds");
            isConnected = false;
            updateBadge("disconnected");
            updateStatus(false);

            if (!shouldDisableExtension) {
                // 在连接关闭后尝试重新连接
                setTimeout(connectWebSocket, 5000);
            }
        };
    }
    catch (e) {
        // 捕获并打印任何其他异常
        console.error("Exception in WebSocket connection: ", e);
    }
}

// 更新扩展图标徽章
function updateBadge(status) {
    chrome.action.setBadgeBackgroundColor({ color: status === "connected" ? "green" : "red" });
    chrome.action.setBadgeText({ text: status === "connected" ? "" : "!" });
}

// 更新扩展状态
function updateStatus(connected) {
    chrome.storage.local.set({ isConnected: connected }, () => {
        console.log(`Status updated: ${connected ? "Connected" : "Disconnected"}`);
    });
}

// 监听下载开始事件并阻止下载
chrome.downloads.onCreated.addListener((downloadItem) => {
    // 检查扩展是否被禁用
    chrome.storage.local.get(["shouldDisableExtension"], (result) => {
        if (result.shouldDisableExtension) {
            console.log("Extension is disabled, not processing downloads.");
            return;
        }

        console.log("Download started: ", downloadItem);

        const downloadInfo = {
            id: downloadItem.id,
            url: downloadItem.url,
            // filename: downloadItem.filename,
            mime: downloadItem.mime,
            fileSize: downloadItem.fileSize,
            startTime: downloadItem.startTime,
            state: downloadItem.state,
        };

        // 取消下载
        chrome.downloads.cancel(downloadItem.id, () => {
            console.log(`Download cancelled: ${downloadItem.id}`);
        });

        // 发送下载信息到服务器
        if (isConnected && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(downloadInfo));
        } else {
            console.error("WebSocket is not open");
        }
    });
});

// 启动 WebSocket 连接
connectWebSocket();

// 在扩展启动时检查禁用状态
chrome.storage.local.get(["shouldDisableExtension"], (result) => {
    shouldDisableExtension = result.shouldDisableExtension || false;
    console.log("Extension disable status:", shouldDisableExtension);
});
