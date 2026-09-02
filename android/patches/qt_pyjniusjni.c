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
