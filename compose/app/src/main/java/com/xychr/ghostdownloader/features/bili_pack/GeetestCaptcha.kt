package com.xychr.ghostdownloader.features.bili_pack

import android.annotation.SuppressLint
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.annotation.StringRes
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

    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { context ->
                WebView(context).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    webChromeClient = WebChromeClient()
                    webViewClient = WebViewClient()
                    addJavascriptInterface(
                        object {
                            @JavascriptInterface
                            fun onResult(challenge: String, validate: String, seccode: String) {
                                post { onResult(CaptchaResult(challenge, validate, seccode)) }
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
                                post { onFailure(failure) }
                            }

                            @JavascriptInterface
                            fun onClosed() {
                                post { onCancel() }
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
<style>
  html, body { margin: 0; height: 100%; background: transparent; }
  .geetest_panel, .geetest_panel_ghost { background: transparent !important; }
  .geetest_panel {
    position: fixed; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    transform-origin: center center;
  }
  .geetest_panel_box, .geetest_panel_next, .geetest_panel_holder { animation: none !important; transition: none !important; }
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
