/* 提供 WebView_AndroidGetJNIEnv(): pyjnius 要它才能 dlopen, 但 qt bootstrap 的 libmain 不含此符号 → jnius.so 加载失败。
 * JNI_OnLoad 抓 VM; 但 qt bootstrap 下 libmain 可能不经 System.loadLibrary 加载致其不触发, 故回退 JNI_GetCreatedJavaVMs。 */

#include <jni.h>
#include <dlfcn.h>
#include <android/log.h>

#define LOG_TAG "gd3_pyjniusjni"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

static JavaVM *g_vm = NULL;

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved)
{
    g_vm = vm;
    return JNI_VERSION_1_6;
}

static JavaVM *resolve_vm(void)
{
    if (g_vm) {
        return g_vm;
    }
    /* 回退：从运行时查已创建的 VM。JNI_GetCreatedJavaVMs 不在稳定 NDK API 里，dlsym 取。 */
    typedef jint (*get_vms_fn)(JavaVM **, jsize, jsize *);
    get_vms_fn get_vms = (get_vms_fn)dlsym(RTLD_DEFAULT, "JNI_GetCreatedJavaVMs");
    if (!get_vms) {
        void *handle = dlopen("libnativehelper.so", RTLD_NOW);
        if (handle) {
            get_vms = (get_vms_fn)dlsym(handle, "JNI_GetCreatedJavaVMs");
        }
    }
    if (get_vms) {
        JavaVM *vm = NULL;
        jsize count = 0;
        if (get_vms(&vm, 1, &count) == JNI_OK && count > 0) {
            g_vm = vm;
            return vm;
        }
    }
    LOGE("failed to resolve JavaVM");
    return NULL;
}

void *WebView_AndroidGetJNIEnv(void)
{
    JavaVM *vm = resolve_vm();
    if (!vm) {
        return NULL;
    }
    JNIEnv *env = NULL;
    (*vm)->AttachCurrentThread(vm, &env, NULL);
    return env;
}
