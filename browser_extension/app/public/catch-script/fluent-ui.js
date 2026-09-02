(function installCatCatchFluentUI() {
    if (window.CatCatchFluentUI?.installed) { return; }

    const panelTitles = {
        catCatchRecorder: "视频录制",
        catCatchWebRTC: "录制 WebRTC",
        CatCatchCatch: "缓存捕捉",
    };
    const nativeAttachShadow = Element.prototype.attachShadow;
    const nativeAttachShadowSource = nativeAttachShadow.toString();

    const panelStyle = {
        background: "rgba(255, 255, 255, 0.96)",
        border: "1px solid #d1d1d1",
        borderRadius: "8px",
        boxSizing: "border-box",
        boxShadow: "0 16px 32px rgba(0, 0, 0, 0.14), 0 2px 8px rgba(0, 0, 0, 0.12)",
        color: "#242424",
        fontFamily: '"Segoe UI", "Microsoft YaHei", Arial, sans-serif',
        fontSize: "13px",
        lineHeight: "18px",
        minWidth: "248px",
        maxWidth: "340px",
        padding: "12px",
    };

    const contentStyle = {
        alignItems: "stretch",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
    };

    const stylesheet = `
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch),
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) * {
            box-sizing: border-box;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) {
            backdrop-filter: blur(18px);
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) .cat-catch-fluent-header {
            display: flex;
            width: 100%;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) .cat-catch-fluent-title {
            color: #242424;
            font-size: 13px;
            font-weight: 600;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) img {
            width: 24px !important;
            height: 24px !important;
            padding: 3px;
            border: 1px solid #d1d1d1;
            border-radius: 6px;
            background: #ffffff;
            cursor: pointer;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) button {
            min-height: 28px !important;
            margin: 0 !important;
            padding: 4px 12px !important;
            border: 1px solid #d1d1d1 !important;
            border-radius: 4px !important;
            background: #ffffff !important;
            color: #242424 !important;
            cursor: pointer;
            font: inherit;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) button:hover {
            background: #f5f5f5 !important;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) button:active {
            background: #e0e0e0 !important;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) select {
            min-height: 28px;
            max-width: 292px !important;
            padding: 3px 8px;
            border: 1px solid #d1d1d1;
            border-radius: 4px;
            background: #ffffff;
            color: #242424;
            font: inherit;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) label {
            display: flex;
            align-items: center;
            gap: 6px;
            margin: 0;
            color: #424242;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) input[type="checkbox"] {
            width: 16px;
            height: 16px;
            accent-color: #0f6cbd;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) #tips,
        #catCatchWebRTC #time {
            width: 100%;
            padding: 7px 9px;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            background: #f5f5f5;
            color: #242424;
            overflow-wrap: anywhere;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) details {
            width: 100%;
            padding-top: 8px;
            border-top: 1px solid #e0e0e0;
        }
        :is(#catCatchRecorder, #catCatchWebRTC, #CatCatchCatch) summary {
            cursor: pointer;
            color: #0f6cbd;
            font-weight: 600;
        }
    `;

    function panelId(panel) {
        if (Object.hasOwn(panelTitles, panel.id)) { return panel.id; }
        if (panel.querySelector("#videoTrack") && panel.querySelector("#audioTrack")) {
            panel.id = "catCatchWebRTC";
            return panel.id;
        }
        return "";
    }

    function contentElement(panel, id) {
        if (id === "catCatchRecorder") {
            return panel.querySelector("#catCatchRecorderContent");
        }
        if (id === "CatCatchCatch") {
            return panel.querySelector("#catCatch");
        }

        let content = panel.querySelector("#catCatchWebRTCContent");
        if (content) { return content; }

        content = document.createElement("div");
        content.id = "catCatchWebRTCContent";
        for (const node of Array.from(panel.childNodes)) {
            if (node.nodeType === Node.ELEMENT_NODE) {
                const element = node;
                if (element.matches("style, .cat-catch-fluent-header, #close")) {
                    continue;
                }
            }
            content.appendChild(node);
        }
        panel.appendChild(content);
        return content;
    }

    function addHeader(panel, id) {
        const icon = panel.querySelector("img");
        if (!icon || panel.querySelector(".cat-catch-fluent-header")) { return; }

        if (window.CatCatchFluentUIIcon) {
            icon.src = window.CatCatchFluentUIIcon;
        }

        const header = document.createElement("div");
        header.className = "cat-catch-fluent-header";
        icon.parentNode.insertBefore(header, icon);
        header.appendChild(icon);

        const title = document.createElement("span");
        title.className = "cat-catch-fluent-title";
        title.textContent = panelTitles[id] || "";
        header.appendChild(title);
    }

    function decorate(panel) {
        const id = panelId(panel);
        if (!id || panel.dataset.fluentUi === "true") { return; }
        panel.dataset.fluentUi = "true";

        if (!panel.querySelector("#close") && (id === "catCatchRecorder" || id === "catCatchWebRTC")) {
            const closeButton = document.createElement("button");
            closeButton.id = "close";
            closeButton.hidden = true;
            closeButton.style.display = "none";
            panel.appendChild(closeButton);
        }

        const style = document.createElement("style");
        style.textContent = stylesheet;
        panel.prepend(style);

        addHeader(panel, id);
        const content = contentElement(panel, id);
        if (id === "catCatchWebRTC") {
            const toggleContent = () => {
                const hidden = content.style.display === "none";
                content.style.display = hidden ? "flex" : "none";
                panel.style.opacity = hidden ? "" : "0.5";
            };
            panel.querySelector("#hide")?.addEventListener("click", (event) => {
                event.stopImmediatePropagation();
                toggleContent();
            }, true);
            panel.querySelector(".cat-catch-fluent-header img")?.addEventListener("click", toggleContent);
        }

        Object.assign(panel.style, panelStyle);
        Object.assign(content.style, contentStyle);
    }

    function patchShadowRoot(shadowRoot) {
        if (shadowRoot.__catCatchFluentUI) { return; }

        const appendChild = shadowRoot.appendChild;
        try {
            Object.defineProperty(shadowRoot, "__catCatchFluentUI", { value: true });
            shadowRoot.appendChild = function appendCatCatchFluentUI(node) {
                if (node instanceof Element) { decorate(node); }
                return appendChild.call(this, node);
            };
        } catch {
            // Styling must never block the upstream recorder/catcher logic.
        }
    }

    function patchedAttachShadow(init) {
        const shadowRoot = nativeAttachShadow.call(this, init);
        patchShadowRoot(shadowRoot);
        return shadowRoot;
    }

    patchedAttachShadow.toString = () => nativeAttachShadowSource;
    try {
        Element.prototype.attachShadow = patchedAttachShadow;
    } catch {
        return;
    }

    window.CatCatchFluentUI = {
        installed: true,
        decorate,
    };
})();
