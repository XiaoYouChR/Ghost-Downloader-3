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
#else
    #include <errno.h>
    #include <ftw.h>
    #include <signal.h>
    #include <spawn.h>
    #include <sys/wait.h>
    #include <unistd.h>
    extern char **environ;
    #ifdef __APPLE__
        #include <mach-o/dyld.h>
    #endif
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
static char  g_logPath[PATH_BUF];

static void toDirname(char *path) {
    char *sep = strrchr(path, '/');
#ifdef _WIN32
    char *bsep = strrchr(path, '\\');
    if (bsep > sep) sep = bsep;
#endif
    if (sep) *sep = '\0';
    else     path[0] = '\0';
}

static void openLog(const char *appDir) {
    strncpy(g_logPath, appDir, sizeof(g_logPath) - 1);
    g_logPath[sizeof(g_logPath) - 1] = '\0';
    toDirname(g_logPath);

    size_t dirLen = strlen(g_logPath);
    if (dirLen > 0)
        snprintf(g_logPath + dirLen, sizeof(g_logPath) - dirLen, "%cupdater.log",
#ifdef _WIN32
                 '\\');
#else
                 '/');
#endif
    else
        snprintf(g_logPath, sizeof(g_logPath), "updater.log");

    g_log = fopen(g_logPath, "a");
}

static void logMsg(const char *fmt, ...) {
    if (!g_log) return;

    time_t now = time(NULL);
    struct tm *t = localtime(&now);
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

static void findExeDir(char *buf, size_t len) {
#ifdef _WIN32
    GetModuleFileNameA(NULL, buf, (DWORD)len);
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
    for (int elapsed = 0; elapsed < timeoutMs; elapsed += 100) {
        if (kill((pid_t)pid, 0) != 0) return 0;
        usleep(100 * 1000);
    }
    return -1;
}
#endif

static int runHpatchz(const char *dir, const char *oldDir,
                      const char *patchFile, const char *newDir) {
    char hpatchz[PATH_BUF];
#ifdef _WIN32
    snprintf(hpatchz, sizeof(hpatchz), "%s\\hpatchz.exe", dir);
#else
    snprintf(hpatchz, sizeof(hpatchz), "%s/hpatchz", dir);
#endif

    logMsg("running: %s -f \"%s\" \"%s\" \"%s\"", hpatchz, oldDir, patchFile, newDir);

#ifdef _WIN32
    char cmd[PATH_BUF * 2];
    snprintf(cmd, sizeof(cmd), "\"%s\" -f \"%s\" \"%s\" \"%s\"",
             hpatchz, oldDir, patchFile, newDir);

    SECURITY_ATTRIBUTES sa = { .nLength = sizeof(sa), .bInheritHandle = TRUE };
    HANDLE hLog = g_log
        ? CreateFileA(g_logPath, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                      &sa, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL)
        : INVALID_HANDLE_VALUE;

    STARTUPINFOA si = { .cb = sizeof(si) };
    if (hLog != INVALID_HANDLE_VALUE) {
        si.dwFlags    = STARTF_USESTDHANDLES;
        si.hStdOutput = hLog;
        si.hStdError  = hLog;
    }

    PROCESS_INFORMATION pi = {0};
    if (!CreateProcessA(NULL, cmd, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
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

    int status;
    waitpid(child, &status, 0);
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
#endif
}

static int moveDir(const char *from, const char *to) {
#ifdef _WIN32
    for (int i = 0; i < 5; i++) {
        if (MoveFileA(from, to)) return 0;
        logMsg("rename \"%s\" -> \"%s\" failed (err=%lu), retry %d",
               from, to, GetLastError(), i + 1);
        Sleep(100u << i);
    }
    return -1;
#else
    if (rename(from, to) == 0) return 0;
    logMsg("rename \"%s\" -> \"%s\" failed: %s", from, to, strerror(errno));
    return -1;
#endif
}


#ifdef _WIN32
static void deleteDir(const char *dir) {
    char buf[MAX_PATH + 2];
    memset(buf, 0, sizeof(buf));
    strncpy(buf, dir, MAX_PATH);

    SHFILEOPSTRUCTA op = {0};
    op.wFunc  = FO_DELETE;
    op.pFrom  = buf;
    op.fFlags = FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT;
    SHFileOperationA(&op);
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

static int startApp(const char *exe) {
#ifdef _WIN32
    char cmd[PATH_BUF];
    snprintf(cmd, sizeof(cmd), "\"%s\"", exe);

    STARTUPINFOA si = { .cb = sizeof(si) };
    PROCESS_INFORMATION pi = {0};
    if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi))
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

int main(int argc, char *argv[]) {
    if (argc < 4 || argc > 5) {
        fprintf(stderr, "usage: updater <appPID> <appDir> <appExe> [patchFile]\n");
        return EXIT_BAD_ARGS;
    }

    unsigned long appPid = strtoul(argv[1], NULL, 10);
    const char   *appDir    = argv[2];
    const char   *appExe    = argv[3];
    const char   *patchFile = argc == 5 ? argv[4] : NULL;

    char newDir[PATH_BUF], backupDir[PATH_BUF], updaterDir[PATH_BUF];
    snprintf(newDir,    sizeof(newDir),    "%s_new",    appDir);
    snprintf(backupDir, sizeof(backupDir), "%s_backup", appDir);
    findExeDir(updaterDir, sizeof(updaterDir));

    openLog(appDir);
    logMsg("   __________     __  ______  ____  ___  ________________");
    logMsg("  / ____/ __ \\   / / / / __ \\/ __ \\/   |/_  __/ ____/ __ \\");
    logMsg(" / / __/ / / /  / / / / /_/ / / / / /| | / / / __/ / /_/ /");
    logMsg("/ /_/ / /_/ /  / /_/ / ____/ /_/ / ___ |/ / / /___/ _, _/");
    logMsg("\\____/_____/   \\____/_/   /_____/_/  |_/_/ /_____/_/ |_|");
    logMsg("pid=%lu appDir=\"%s\" exe=\"%s\" patch=\"%s\"",
           appPid, appDir, appExe, patchFile ? patchFile : "(full)");

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
        rename(newDir, backupDir);
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

    if (patchFile)
        remove(patchFile);

    logMsg("starting %s", appExe);
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
    return EXIT_OK;
}
