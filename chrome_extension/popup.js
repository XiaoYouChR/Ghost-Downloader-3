// popup.js

// 获取状态元素和禁用按钮
const statusText = document.getElementById("status-text");
const disableButton = document.getElementById("disable-button");
const enableButton = document.getElementById("enable-button");

// 更新状态文本
function updateStatus() {
    chrome.storage.local.get("isConnected", (data) => {
        statusText.textContent = data.isConnected ? "已连接" : "已断开连接";
    });

    // 检查禁用状态
    chrome.storage.local.get("shouldDisableExtension", (result) => {
        if (result.shouldDisableExtension) {
            disableButton.style.display = "none";
            enableButton.style.display = "block";
        } else {
            disableButton.style.display = "block";
            enableButton.style.display = "none";
        }
    });
}

// 添加禁用按钮点击事件监听器
disableButton.addEventListener("click", () => {
    chrome.storage.local.set({ shouldDisableExtension: true }, () => {
        console.log("Extension disabled.");
        updateStatus();
    });
});

// 添加启用按钮点击事件监听器
enableButton.addEventListener("click", () => {
    chrome.storage.local.set({ shouldDisableExtension: false }, () => {
        console.log("Extension enabled.");
        updateStatus();
    });
});

// 读取连接状态并更新UI
chrome.storage.local.get(["isConnected"], (data) => {
    updateStatus();
});

// 更新状态
updateStatus();
