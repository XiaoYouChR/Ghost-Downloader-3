package com.xychr.ghostdownloader.features.bili_pack

import android.annotation.SuppressLint
import android.graphics.Color
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.xychr.ghostdownloader.R
import org.json.JSONObject
import java.util.Locale

enum class CaptchaFailure(@StringRes val message: Int) {
    Script(R.string.bili_captcha_script_failed),
    Init(R.string.bili_captcha_init_failed),
    Verify(R.string.bili_captcha_verify_failed),
}

private const val BRIDGE = "CaptchaBridge"
private const val BASE_URL = "https://www.bilibili.com/"
private const val GEETEST_JS = "https://static.geetest.com/static/js/gt.0.4.9.js"

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun GeetestCaptcha(
    params: CaptchaParams,
    onResult: (CaptchaResult) -> Unit,
    onCancel: () -> Unit,
    onFailure: (CaptchaFailure) -> Unit,
) {
    var isReady by remember { mutableStateOf(false) }

    Box(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.scrim.copy(alpha = 0.32f)),
        contentAlignment = Alignment.Center,
    ) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { context ->
                val webView = WebView(context)
                var hasFinished = false

                fun finish(action: () -> Unit) {
                    webView.post {
                        if (hasFinished) return@post
                        hasFinished = true
                        action()
                    }
                }

                webView.apply {
                    setBackgroundColor(Color.TRANSPARENT)
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    settings.useWideViewPort = true
                    webChromeClient = WebChromeClient()
                    webViewClient = WebViewClient()
                    addJavascriptInterface(
                        object {
                            @JavascriptInterface
                            fun onResult(challenge: String, validate: String, seccode: String) {
                                finish { onResult(CaptchaResult(challenge, validate, seccode)) }
                            }

                            @JavascriptInterface
                            fun onReady() {
                                post { isReady = true }
                            }

                            @JavascriptInterface
                            fun onFailed(kind: String) {
                                val failure = when (kind) {
                                    "init" -> CaptchaFailure.Init
                                    "verify" -> CaptchaFailure.Verify
                                    else -> CaptchaFailure.Script
                                }
                                finish { onFailure(failure) }
                            }

                            @JavascriptInterface
                            fun onClosed() {
                                finish { onCancel() }
                            }
                        },
                        BRIDGE,
                    )
                    loadDataWithBaseURL(
                        BASE_URL,
                        captchaHtml(params.gt, params.challenge),
                        "text/html", "utf-8", BASE_URL,
                    )
                }
            },
            onRelease = { view ->
                view.stopLoading()
                view.removeJavascriptInterface(BRIDGE)
                view.destroy()
            },
        )
        if (!isReady) CircularProgressIndicator()
    }
}

private fun captchaHtml(gt: String, challenge: String): String {
    val language = Locale.getDefault().language.let { if (it.startsWith("zh")) "zh-cn" else it }
    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: transparent; }
  /* 遮罩由原生画，WebView 只负责面板本身 */
  .geetest_panel, .geetest_panel_ghost { background: transparent !important; }
  /* 极验用内联样式摆面板，只有 !important 盖得过 */
  .geetest_panel_box {
    left: 50% !important;
    top: 50% !important;
    right: auto !important;
    bottom: auto !important;
    margin: 0 !important;
    transform: translate(-50%, -50%) !important;
    transform-origin: center center !important;
  }
  /* 入场动画逐帧改外框尺寸，面板会跟着抖 */
  .geetest_panel_box, .geetest_panel_next, .geetest_panel_next > .geetest_holder {
    animation: none !important;
    transition: none !important;
  }
</style>
<script src="$GEETEST_JS" onerror="CaptchaBridge.onFailed('script')"></script>
</head>
<body>
<script>
window.onload = function () {
  if (typeof initGeetest !== "function") { CaptchaBridge.onFailed('script'); return; }
  initGeetest({
    gt: ${quote(gt)},
    challenge: ${quote(challenge)},
    offline: false,
    new_captcha: true,
    product: "bind",
    width: "300px",
    lang: ${quote(language)},
    https: true,
    onError: function (e) { CaptchaBridge.onFailed((e && e.msg) || 'init'); }
  }, function (captcha) {
    captcha.onReady(function () { CaptchaBridge.onReady(); captcha.verify(); });
    captcha.onSuccess(function () {
      var r = captcha.getValidate();
      if (r) CaptchaBridge.onResult(r.geetest_challenge, r.geetest_validate, r.geetest_seccode);
    });
    captcha.onError(function (e) { CaptchaBridge.onFailed((e && e.msg) || 'verify'); });
    captcha.onClose(function () { CaptchaBridge.onClosed(); });
  });
};
</script>
</body>
</html>
""".trimIndent()
}

private fun quote(value: String) = JSONObject.quote(value)
