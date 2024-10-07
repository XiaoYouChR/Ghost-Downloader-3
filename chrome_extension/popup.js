// popup.js

// 获取状态元素和禁用按钮
const statusText = document.getElementById("status-text");
const disableButton = document.getElementById("disable-button");
const enableButton = document.getElementById("enable-button");

// 更新状态文本
function updateStatus() {
    chrome.storage.local.get("isConnected", (data) => {
        statusText.textContent = data.isConnected ? "连接成功" : "连接已断开";
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

// 监听存储变化
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local' && changes.isConnected) {
        updateStatus(); // 当 isConnected 发生变化时，更新状态
    }
});

function isVersionNewer(v1, v2) {
    const parts1 = v1.split('.').map(Number);
    const parts2 = v2.split('.').map(Number);

    for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
        const num1 = parts1[i] || 0;
        const num2 = parts2[i] || 0;
        if (num1 !== num2) {
            return num1 > num2; // 如果 v1 更新，返回 true
        }
    }
    return false;
}

// 打印插件版本到插件页面
// 打印插件版本到插件页面
document.addEventListener('DOMContentLoaded', () => {

    const ExtensionVersion = chrome.runtime.getManifest().version;

    // 获取客户端版本和最新插件版本
    chrome.storage.local.get(["ClientVersion", "LatestExtensionVersion"], (result) => {
        const ClientVersion = result.ClientVersion || "Unknown";
        const LatestExtensionVersion = result.LatestExtensionVersion || "Unknown";
        // console.log(ExtensionVersion, ClientVersion, LatestExtensionVersion);

        if (isVersionNewer(LatestExtensionVersion, ExtensionVersion)) {
            document.getElementById('version').innerHTML = `插件版本: ${ExtensionVersion}&nbsp;&nbsp客户端版本: ${ClientVersion}<br/><span style="color: palevioletred;">插件有新版本，请前往客户端手动更新!</span>`;
        } else {
            document.getElementById('version').innerHTML = `插件版本: ${ExtensionVersion}&nbsp;&nbsp客户端版本: ${ClientVersion}`;
        }
    });
});

// 更新状态
updateStatus();
