/*
 * Usage:  updater <appPID> <appDir> <appExe> [patchFile]
 * Exit:   0 ok · 1 patch · 2 rename · 3 timeout · 4 launch · 5 args
 */

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
    #define WIN32_LEAN_AND_MEAN
    #include <windows.h>
    #include <shellapi.h>
    #include <shlobj.h>
    #include <wchar.h>
    typedef wchar_t pchar;
    #define PFMT "%ls"
    #define wsnprintf(buf, n, ...) do { _snwprintf((buf), (n), __VA_ARGS__); (buf)[(n) - 1] = L'\0'; } while (0)
#else
    #include <errno.h>
    #include <ftw.h>
    #include <pwd.h>
    #include <signal.h>
    #include <spawn.h>
    #include <sys/stat.h>
    #include <sys/wait.h>
    #include <unistd.h>
    extern char **environ;
    #ifdef __APPLE__
        #include <mach-o/dyld.h>
        #include <sysdir.h>
    #endif
    typedef char pchar;
    #define PFMT "%s"
#endif

#define PATH_BUF 4096

enum {
    EXIT_OK           = 0,
    EXIT_PATCH_FAILED = 1,
    EXIT_RENAME_FAILED= 2,
    EXIT_WAIT_TIMEOUT = 3,
    EXIT_LAUNCH_FAILED= 4,
    EXIT_BAD_ARGS     = 5,
};

static FILE *g_log;
#ifdef _WIN32
static wchar_t g_logPath[PATH_BUF];
#else
static char g_logPath[PATH_BUF];
#endif

static void toDirname(pchar *path) {
#ifdef _WIN32
    wchar_t *sep = wcsrchr(path, L'/');
    wchar_t *bsep = wcsrchr(path, L'\\');
    if (bsep && (!sep || bsep > sep)) sep = bsep;
    if (sep) *sep = L'\0';
    else     path[0] = L'\0';
#else
    char *sep = strrchr(path, '/');
    if (sep) *sep = '\0';
    else     path[0] = '\0';
#endif
}

static void openLog(void) {
#ifdef _WIN32
    wchar_t dir[MAX_PATH];
    if (FAILED(SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, 0, dir)))
        return;
    wsnprintf(g_logPath, PATH_BUF, L"%ls\\GhostDownloader", dir);
    CreateDirectoryW(g_logPath, NULL);
    size_t dirLen = wcslen(g_logPath);
    wsnprintf(g_logPath + dirLen, PATH_BUF - dirLen, L"\\updater.log");
    g_log = _wfopen(g_logPath, L"a");
#elif defined(__APPLE__)
    char rawPath[PATH_BUF];
    sysdir_search_path_enumeration_state state =
        sysdir_start_search_path_enumeration(
            SYSDIR_DIRECTORY_APPLICATION_SUPPORT,
            SYSDIR_DOMAIN_MASK_USER);
    sysdir_get_next_search_path_enumeration(state, rawPath);
    if (rawPath[0] == '\0') return;

    char dir[PATH_BUF];
    if (rawPath[0] == '~') {
        struct passwd pw, *result;
        char pwBuf[4096];
        if (getpwuid_r(getuid(), &pw, pwBuf, sizeof(pwBuf), &result) != 0
            || !result)
            return;
        snprintf(dir, sizeof(dir), "%s%s", result->pw_dir, rawPath + 1);
    } else {
        snprintf(dir, sizeof(dir), "%s", rawPath);
    }

    snprintf(g_logPath, PATH_BUF, "%s/GhostDownloader", dir);
    mkdir(g_logPath, 0755);
    size_t dirLen = strlen(g_logPath);
    snprintf(g_logPath + dirLen, PATH_BUF - dirLen, "/updater.log");
    g_log = fopen(g_logPath, "a");
#else
    const char *base = getenv("XDG_STATE_HOME");
    char dir[PATH_BUF];
    if (base && base[0] == '/') {
        snprintf(dir, sizeof(dir), "%s", base);
    } else {
        const char *home = getenv("HOME");
        if (!home || home[0] != '/') {
            struct passwd pw, *result;
            char pwBuf[4096];
            if (getpwuid_r(getuid(), &pw, pwBuf, sizeof(pwBuf), &result) != 0
                || !result)
                return;
            home = result->pw_dir;
        }
        snprintf(dir, sizeof(dir), "%s/.local/state", home);
    }

    mkdir(dir, 0755);
    snprintf(g_logPath, PATH_BUF, "%s/GhostDownloader", dir);
    mkdir(g_logPath, 0755);
    size_t dirLen = strlen(g_logPath);
    snprintf(g_logPath + dirLen, PATH_BUF - dirLen, "/updater.log");
    g_log = fopen(g_logPath, "a");
#endif
}

static void logMsg(const char *fmt, ...) {
    if (!g_log) return;

    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    if (t)
        fprintf(g_log, "%04d-%02d-%02d %02d:%02d:%02d ",
                t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
                t->tm_hour, t->tm_min, t->tm_sec);

    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);

    fputc('\n', g_log);
    fflush(g_log);
}

static void closeLog(void) {
    if (g_log) fclose(g_log);
}

static void findExeDir(pchar *buf, size_t len) {
#ifdef _WIN32
    if (!GetModuleFileNameW(NULL, buf, (DWORD)len)) {
        buf[0] = L'\0';
        return;
    }
    buf[len - 1] = L'\0';
#elif defined(__APPLE__)
    uint32_t size = (uint32_t)len;
    if (_NSGetExecutablePath(buf, &size) != 0) {
        buf[0] = '\0';
        return;
    }
#else
    ssize_t n = readlink("/proc/self/exe", buf, len - 1);
    if (n > 0)
        buf[n] = '\0';
    else {
        buf[0] = '\0';
        return;
    }
#endif
    toDirname(buf);
}

#ifdef _WIN32
static int waitForProcessExit(unsigned long pid, int timeoutMs) {
    HANDLE h = OpenProcess(SYNCHRONIZE, FALSE, pid);
    if (!h) return 0;
    DWORD r = WaitForSingleObject(h, (DWORD)timeoutMs);
    CloseHandle(h);
    return (r == WAIT_OBJECT_0 || r == WAIT_ABANDONED) ? 0 : -1;
}
#else
static int waitForProcessExit(unsigned long pid, int timeoutMs) {
    if (pid == 0) return 0;
    for (int elapsed = 0; elapsed < timeoutMs; elapsed += 100) {
        if (kill((pid_t)pid, 0) != 0 && errno == ESRCH) return 0;
        usleep(100 * 1000);
    }
    return -1;
}
#endif

static int runHpatchz(const pchar *dir, const pchar *oldDir,
                      const pchar *patchFile, const pchar *newDir) {
#ifdef _WIN32
    wchar_t hpatchz[PATH_BUF];
    wsnprintf(hpatchz, PATH_BUF, L"%ls\\hpatchz.exe", dir);

    logMsg("running: " PFMT " -f \"" PFMT "\" \"" PFMT "\" \"" PFMT "\"",
           hpatchz, oldDir, patchFile, newDir);

    wchar_t cmd[PATH_BUF * 2];
    wsnprintf(cmd, PATH_BUF * 2, L"\"%ls\" -f \"%ls\" \"%ls\" \"%ls\"",
               hpatchz, oldDir, patchFile, newDir);

    SECURITY_ATTRIBUTES sa = { .nLength = sizeof(sa), .bInheritHandle = TRUE };
    HANDLE hLog = g_log
        ? CreateFileW(g_logPath, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                      &sa, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL)
        : INVALID_HANDLE_VALUE;

    STARTUPINFOW si = { .cb = sizeof(si) };
    if (hLog != INVALID_HANDLE_VALUE) {
        si.dwFlags    = STARTF_USESTDHANDLES;
        si.hStdOutput = hLog;
        si.hStdError  = hLog;
    }

    PROCESS_INFORMATION pi = {0};
    if (!CreateProcessW(NULL, cmd, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        if (hLog != INVALID_HANDLE_VALUE) CloseHandle(hLog);
        return -1;
    }

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    if (hLog != INVALID_HANDLE_VALUE) CloseHandle(hLog);
    return code == 0 ? 0 : (int)code;

#else
    char hpatchz[PATH_BUF];
    snprintf(hpatchz, sizeof(hpatchz), "%s/hpatchz", dir);

    logMsg("running: " PFMT " -f \"" PFMT "\" \"" PFMT "\" \"" PFMT "\"",
           hpatchz, oldDir, patchFile, newDir);

    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    if (g_log) {
        int fd = fileno(g_log);
        posix_spawn_file_actions_adddup2(&actions, fd, STDOUT_FILENO);
        posix_spawn_file_actions_adddup2(&actions, fd, STDERR_FILENO);
    }

    pid_t child;
    char *argv[] = {hpatchz, "-f", (char *)oldDir, (char *)patchFile,
                    (char *)newDir, NULL};
    int err = posix_spawn(&child, hpatchz, &actions, NULL, argv, environ);
    posix_spawn_file_actions_destroy(&actions);
    if (err != 0) return -1;

    int status = 0;
    if (waitpid(child, &status, 0) == -1) return -1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
#endif
}

static int moveDir(const pchar *from, const pchar *to) {
#ifdef _WIN32
    for (int i = 0; i < 5; i++) {
        if (MoveFileW(from, to)) return 0;
        logMsg("rename \"" PFMT "\" -> \"" PFMT "\" failed (err=%lu), retry %d",
               from, to, GetLastError(), i + 1);
        Sleep(100u << i);
    }
    return -1;
#else
    if (rename(from, to) == 0) return 0;
    logMsg("rename \"" PFMT "\" -> \"" PFMT "\" failed: %s", from, to, strerror(errno));
    return -1;
#endif
}


#ifdef _WIN32
static void deleteDir(const wchar_t *dir) {
    wchar_t buf[PATH_BUF + 2];
    memset(buf, 0, sizeof(buf));
    wcsncpy(buf, dir, PATH_BUF);

    SHFILEOPSTRUCTW op = {0};
    op.wFunc  = FO_DELETE;
    op.pFrom  = buf;
    op.fFlags = FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT;
    SHFileOperationW(&op);
}
#else
static int deletePath(const char *path, const struct stat *sb, int t, struct FTW *f) {
    (void)sb; (void)t; (void)f;
    return remove(path);
}

static void deleteDir(const char *dir) {
    nftw(dir, deletePath, 64, FTW_DEPTH | FTW_PHYS);
}
#endif

static int startApp(const pchar *exe) {
#ifdef _WIN32
    wchar_t cmd[PATH_BUF];
    wsnprintf(cmd, PATH_BUF, L"\"%ls\"", exe);

    STARTUPINFOW si = { .cb = sizeof(si) };
    PROCESS_INFORMATION pi = {0};
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi))
        return -1;

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return 0;
#else
    pid_t child;
    char *argv[] = {(char *)exe, NULL};
    return posix_spawn(&child, exe, NULL, NULL, argv, environ) == 0 ? 0 : -1;
#endif
}

#ifdef _WIN32
static int restartFromTemp(const wchar_t *appDir, int wargc, wchar_t **wargv) {
    wchar_t exePath[PATH_BUF], longExe[PATH_BUF], longApp[PATH_BUF];
    if (!GetModuleFileNameW(NULL, exePath, PATH_BUF))
        return 0;
    exePath[PATH_BUF - 1] = L'\0';
    if (!GetLongPathNameW(exePath, longExe, PATH_BUF))
        return 0;

    wchar_t appDirClean[PATH_BUF];
    wcsncpy(appDirClean, appDir, PATH_BUF - 1);
    appDirClean[PATH_BUF - 1] = L'\0';
    size_t cleanLen = wcslen(appDirClean);
    while (cleanLen > 0 && (appDirClean[cleanLen - 1] == L'\\' || appDirClean[cleanLen - 1] == L'/'))
        appDirClean[--cleanLen] = L'\0';
    if (!GetLongPathNameW(appDirClean, longApp, PATH_BUF))
        return 0;
    size_t len = wcslen(longApp);

    if (_wcsnicmp(longExe, longApp, len) != 0)
        return 0;
    wchar_t c = longExe[len];
    if (c != L'\\' && c != L'/')
        return 0;

    wchar_t tempDir[PATH_BUF];
    if (!GetTempPathW(PATH_BUF, tempDir))
        return 0;
    size_t tempLen = wcslen(tempDir);
    if (tempLen < PATH_BUF - 11)
        wcsncat(tempDir, L"gd_updater", PATH_BUF - tempLen - 1);
    CreateDirectoryW(tempDir, NULL);

    wchar_t srcHpatchz[PATH_BUF], dstUpdater[PATH_BUF], dstHpatchz[PATH_BUF];
    wsnprintf(dstUpdater, PATH_BUF, L"%ls\\updater.exe", tempDir);
    wsnprintf(srcHpatchz, PATH_BUF, L"%ls\\hpatchz.exe", appDirClean);
    wsnprintf(dstHpatchz, PATH_BUF, L"%ls\\hpatchz.exe", tempDir);

    if (!CopyFileW(exePath, dstUpdater, FALSE) ||
        !CopyFileW(srcHpatchz, dstHpatchz, FALSE))
        return 0;

    wchar_t cmd[PATH_BUF * 4];
    size_t cmdSize = PATH_BUF * 4;
    int pos = _snwprintf(cmd, cmdSize, L"\"%ls\"", dstUpdater);
    if (pos < 0 || (size_t)pos >= cmdSize) return 0;
    int truncated = 0;
    for (int i = 1; i < wargc && (size_t)pos < cmdSize; i++) {
        int n = _snwprintf(cmd + pos, cmdSize - pos, L" \"%ls\"", wargv[i]);
        if (n < 0) { truncated = 1; break; }
        pos += n;
    }
    cmd[cmdSize - 1] = L'\0';
    if (truncated) return 0;

    STARTUPINFOW si = { .cb = sizeof(si) };
    PROCESS_INFORMATION pi = {0};
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE,
                        DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                        NULL, NULL, &si, &pi))
        return 0;

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return 1;
}
#endif

int main(int argc, char *argv[]) {
    if (argc < 4 || argc > 5) {
        fprintf(stderr, "usage: updater <appPID> <appDir> <appExe> [patchFile]\n");
        return EXIT_BAD_ARGS;
    }

#ifdef _WIN32
    int wargc;
    wchar_t **wargv = CommandLineToArgvW(GetCommandLineW(), &wargc);
    if (!wargv || wargc < 4) return EXIT_BAD_ARGS;

    if (restartFromTemp(wargv[2], wargc, wargv))
        return EXIT_OK;

    unsigned long appPid = wcstoul(wargv[1], NULL, 10);
    const wchar_t *appDir    = wargv[2];
    const wchar_t *appExe    = wargv[3];
    const wchar_t *patchFile = wargc >= 5 ? wargv[4] : NULL;
#else
    unsigned long appPid = strtoul(argv[1], NULL, 10);
    const char   *appDir    = argv[2];
    const char   *appExe    = argv[3];
    const char   *patchFile = argc == 5 ? argv[4] : NULL;
#endif

    pchar newDir[PATH_BUF], backupDir[PATH_BUF], updaterDir[PATH_BUF];
#ifdef _WIN32
    wsnprintf(newDir,    PATH_BUF, L"%ls_new",    appDir);
    wsnprintf(backupDir, PATH_BUF, L"%ls_backup", appDir);
#else
    snprintf(newDir,    sizeof(newDir),    "%s_new",    appDir);
    snprintf(backupDir, sizeof(backupDir), "%s_backup", appDir);
#endif
    findExeDir(updaterDir, PATH_BUF);

    openLog();
    logMsg("   __________     __  ______  ____  ___  ________________");
    logMsg("  / ____/ __ \\   / / / / __ \\/ __ \\/   |/_  __/ ____/ __ \\");
    logMsg(" / / __/ / / /  / / / / /_/ / / / / /| | / / / __/ / /_/ /");
    logMsg("/ /_/ / /_/ /  / /_/ / ____/ /_/ / ___ |/ / / /___/ _, _/");
    logMsg("\\____/_____/   \\____/_/   /_____/_/  |_/_/ /_____/_/ |_|");
#ifdef _WIN32
    const wchar_t *patchLabel = patchFile ? patchFile : L"(full)";
#else
    const char *patchLabel = patchFile ? patchFile : "(full)";
#endif
    logMsg("pid=%lu appDir=\"" PFMT "\" exe=\"" PFMT "\" patch=\"" PFMT "\"",
           appPid, appDir, appExe, patchLabel);

    logMsg("waiting for app %lu ...", appPid);
    if (waitForProcessExit(appPid, 30000) != 0) {
        logMsg("timeout");
        closeLog();
        return EXIT_WAIT_TIMEOUT;
    }
    logMsg("app exited");

    deleteDir(backupDir);

    if (patchFile) {
        deleteDir(newDir);
        if (runHpatchz(updaterDir, appDir, patchFile, newDir) != 0) {
            logMsg("hpatchz failed");
            deleteDir(newDir);
            closeLog();
            return EXIT_PATCH_FAILED;
        }
        logMsg("patch applied");
    }

    int swapOk = 0;
#ifdef __APPLE__
    if (renamex_np(newDir, appDir, RENAME_SWAP) == 0) {
        if (rename(newDir, backupDir) != 0)
            logMsg("rename old to backup failed (%s), continuing", strerror(errno));
        swapOk = 1;
    } else {
        logMsg("renamex_np failed (%s), falling back", strerror(errno));
    }
#endif
    if (!swapOk) {
        if (moveDir(appDir, backupDir) != 0) {
            deleteDir(newDir);
            closeLog();
            return EXIT_RENAME_FAILED;
        }
        if (moveDir(newDir, appDir) != 0) {
            moveDir(backupDir, appDir);
            deleteDir(newDir);
            closeLog();
            return EXIT_RENAME_FAILED;
        }
    }
    logMsg("installed");

    if (patchFile) {
#ifdef _WIN32
        _wremove(patchFile);
#else
        remove(patchFile);
#endif
    }

    logMsg("starting " PFMT, appExe);
    if (startApp(appExe) != 0) {
        logMsg("start failed, rolling back");
        if (moveDir(appDir, newDir) == 0)
            moveDir(backupDir, appDir);
        deleteDir(newDir);
        closeLog();
        return EXIT_LAUNCH_FAILED;
    }

    logMsg("ok");
    closeLog();
#ifdef _WIN32
    LocalFree(wargv);
#endif
    return EXIT_OK;
}
