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
    #include <dirent.h>
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
        #include <CoreFoundation/CoreFoundation.h>
        #include <Security/Authorization.h>
        #include <ServiceManagement/ServiceManagement.h>
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

static int hasDir(const pchar *dir);

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

static void openLog(const pchar *exeDir) {
#ifdef _WIN32
    if (exeDir && exeDir[0]) {
        wsnprintf(g_logPath, PATH_BUF, L"%ls\\GhostDownloader", exeDir);
        if (hasDir(g_logPath)) {
            size_t dirLen = wcslen(g_logPath);
            wsnprintf(g_logPath + dirLen, PATH_BUF - dirLen, L"\\updater.log");
            g_log = _wfopen(g_logPath, L"a");
            return;
        }
    }

    wchar_t dir[MAX_PATH];
    if (FAILED(SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, 0, dir)))
        return;
    wsnprintf(g_logPath, PATH_BUF, L"%ls\\GhostDownloader", dir);
    CreateDirectoryW(g_logPath, NULL);
    size_t dirLen = wcslen(g_logPath);
    wsnprintf(g_logPath + dirLen, PATH_BUF - dirLen, L"\\updater.log");
    g_log = _wfopen(g_logPath, L"a");
#else
    if (exeDir && exeDir[0]) {
        snprintf(g_logPath, PATH_BUF, "%s/GhostDownloader", exeDir);
        if (hasDir(g_logPath)) {
            size_t dirLen = strlen(g_logPath);
            snprintf(g_logPath + dirLen, PATH_BUF - dirLen, "/updater.log");
            g_log = fopen(g_logPath, "a");
            return;
        }
    }

#ifdef __APPLE__
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
    const char *base = getenv("XDG_DATA_HOME");
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
        snprintf(dir, sizeof(dir), "%s/.local/share", home);
    }

    mkdir(dir, 0755);
    snprintf(g_logPath, PATH_BUF, "%s/GhostDownloader", dir);
    mkdir(g_logPath, 0755);
    size_t dirLen = strlen(g_logPath);
    snprintf(g_logPath + dirLen, PATH_BUF - dirLen, "/updater.log");
    g_log = fopen(g_logPath, "a");
#endif
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
    if (!g_log) return;
    fclose(g_log);
    g_log = NULL;
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
static int isElevated(void) {
    HANDLE token = NULL;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token))
        return 0;
    TOKEN_ELEVATION elev = {0};
    DWORD n = 0;
    int ok = GetTokenInformation(token, TokenElevation, &elev, sizeof(elev), &n)
             && elev.TokenIsElevated;
    CloseHandle(token);
    return ok;
}

static int canWriteDir(const wchar_t *dir) {
    wchar_t probe[PATH_BUF];
    wsnprintf(probe, PATH_BUF, L"%ls\\.gd_write_probe", dir);
    HANDLE h = CreateFileW(probe, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_DELETE_ON_CLOSE, NULL);
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    CloseHandle(h);
    return 1;
}

static int restartElevated(int wargc, wchar_t **wargv) {
    wchar_t exePath[PATH_BUF];
    if (!GetModuleFileNameW(NULL, exePath, PATH_BUF))
        return -1;
    exePath[PATH_BUF - 1] = L'\0';

    wchar_t params[PATH_BUF * 4];
    size_t cap = PATH_BUF * 4;
    int pos = 0;
    params[0] = L'\0';
    for (int i = 1; i < wargc; i++) {
        int n = _snwprintf(params + pos, cap - pos,
                           pos ? L" \"%ls\"" : L"\"%ls\"", wargv[i]);
        if (n < 0 || (size_t)pos + (size_t)n >= cap)
            return -1;
        pos += n;
    }

    wchar_t cwd[PATH_BUF];
    findExeDir(cwd, PATH_BUF);

    SHELLEXECUTEINFOW sei = {0};
    sei.cbSize = sizeof(sei);
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;
    sei.lpVerb = L"runas";
    sei.lpFile = exePath;
    sei.lpParameters = params;
    sei.lpDirectory = cwd[0] ? cwd : NULL;
    sei.nShow = SW_HIDE;
    if (!ShellExecuteExW(&sei))
        return -1;
    if (sei.hProcess)
        CloseHandle(sei.hProcess);
    return 0;
}

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

static int hasDir(const pchar *dir) {
#ifdef _WIN32
    DWORD attr = GetFileAttributesW(dir);
    return attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY);
#else
    struct stat st;
    return stat(dir, &st) == 0 && S_ISDIR(st.st_mode);
#endif
}

static int hasFile(const pchar *path) {
#ifdef _WIN32
    DWORD attr = GetFileAttributesW(path);
    return attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY);
#else
    struct stat st;
    return stat(path, &st) == 0 && S_ISREG(st.st_mode);
#endif
}

static int moveDir(const pchar *from, const pchar *to) {
#ifdef _WIN32
    for (int i = 0; i < 8; i++) {
        if (MoveFileW(from, to)) return 0;
        logMsg("rename \"" PFMT "\" -> \"" PFMT "\" failed (err=%lu), retry %d",
               from, to, GetLastError(), i + 1);
        Sleep(200u << (i < 5 ? i : 5));
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

#ifdef _WIN32
static int copyDir(const wchar_t *from, const wchar_t *to) {
    wchar_t fromBuf[PATH_BUF + 2], toBuf[PATH_BUF + 2];
    memset(fromBuf, 0, sizeof(fromBuf));
    memset(toBuf, 0, sizeof(toBuf));
    wcsncpy(fromBuf, from, PATH_BUF);
    wcsncpy(toBuf, to, PATH_BUF);

    SHFILEOPSTRUCTW op = {0};
    op.wFunc  = FO_COPY;
    op.pFrom  = fromBuf;
    op.pTo    = toBuf;
    op.fFlags = FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT | FOF_NOCONFIRMMKDIR;
    return (SHFileOperationW(&op) == 0 && !op.fAnyOperationsAborted) ? 0 : -1;
}

static int matchUninstaller(const wchar_t *name) {
    if (_wcsnicmp(name, L"unins", 5) != 0) return 0;
    const wchar_t *dot = wcsrchr(name, L'.');
    if (!dot) return 0;
    return _wcsicmp(dot, L".exe") == 0
        || _wcsicmp(dot, L".dat") == 0
        || _wcsicmp(dot, L".msg") == 0;
}

static void installUninstaller(const wchar_t *appDir, const wchar_t *newDir) {
    wchar_t pattern[PATH_BUF];
    wsnprintf(pattern, PATH_BUF, L"%ls\\unins*", appDir);
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
        if (!matchUninstaller(fd.cFileName)) continue;
        wchar_t from[PATH_BUF], to[PATH_BUF];
        wsnprintf(from, PATH_BUF, L"%ls\\%ls", appDir, fd.cFileName);
        wsnprintf(to, PATH_BUF, L"%ls\\%ls", newDir, fd.cFileName);
        CopyFileW(from, to, FALSE);
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}
#else
static int copyFile(const char *from, const char *to) {
    FILE *in = fopen(from, "rb");
    if (!in) return -1;
    FILE *out = fopen(to, "wb");
    if (!out) {
        fclose(in);
        return -1;
    }
    char buf[65536];
    size_t n;
    int ok = 1;
    while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
        if (fwrite(buf, 1, n, out) != n) {
            ok = 0;
            break;
        }
    }
    if (ferror(in)) ok = 0;
    fclose(in);
    fclose(out);
    if (!ok) {
        remove(to);
        return -1;
    }
    return 0;
}

static int copyDir(const char *from, const char *to) {
    struct stat st;
    if (stat(from, &st) != 0) return -1;
    if (mkdir(to, st.st_mode & 0777) != 0 && errno != EEXIST)
        return -1;

    DIR *d = opendir(from);
    if (!d) return -1;
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL) {
        if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0)
            continue;
        char fromChild[PATH_BUF], toChild[PATH_BUF];
        int n1 = snprintf(fromChild, sizeof(fromChild), "%s/%s", from, ent->d_name);
        int n2 = snprintf(toChild, sizeof(toChild), "%s/%s", to, ent->d_name);
        if (n1 < 0 || n1 >= (int)sizeof(fromChild)
            || n2 < 0 || n2 >= (int)sizeof(toChild)) {
            closedir(d);
            return -1;
        }
        if (stat(fromChild, &st) != 0) {
            closedir(d);
            return -1;
        }
        if (S_ISDIR(st.st_mode)) {
            if (copyDir(fromChild, toChild) != 0) {
                closedir(d);
                return -1;
            }
        } else if (copyFile(fromChild, toChild) != 0) {
            closedir(d);
            return -1;
        }
    }
    closedir(d);
    return 0;
}
#endif

static int buildNewPortableFolder(pchar *dst, size_t len,
                                 const pchar *appDir, const pchar *newDir,
                                 const pchar *exeDir) {
#ifdef _WIN32
    size_t appLen = wcslen(appDir);
    while (appLen > 0 && (appDir[appLen - 1] == L'\\' || appDir[appLen - 1] == L'/'))
        appLen--;
    if (appLen == 0) return -1;
    if (_wcsnicmp(exeDir, appDir, appLen) != 0) return -1;
    if (exeDir[appLen] != L'\\' && exeDir[appLen] != L'/' && exeDir[appLen] != L'\0')
        return -1;
    const wchar_t *rest = exeDir + appLen;
    while (*rest == L'\\' || *rest == L'/') rest++;
    if (*rest)
        wsnprintf(dst, len, L"%ls\\%ls\\GhostDownloader", newDir, rest);
    else
        wsnprintf(dst, len, L"%ls\\GhostDownloader", newDir);
#else
    size_t appLen = strlen(appDir);
    while (appLen > 0 && appDir[appLen - 1] == '/')
        appLen--;
    if (appLen == 0) return -1;
    if (strncmp(exeDir, appDir, appLen) != 0) return -1;
    if (exeDir[appLen] != '/' && exeDir[appLen] != '\0')
        return -1;
    const char *rest = exeDir + appLen;
    while (*rest == '/') rest++;
    if (*rest)
        snprintf(dst, len, "%s/%s/GhostDownloader", newDir, rest);
    else
        snprintf(dst, len, "%s/GhostDownloader", newDir);
#endif
    return 0;
}

#ifdef __APPLE__
static void restructureBundle(const char *appDir) {
    char macosDir[PATH_BUF], resourcesDir[PATH_BUF];
    snprintf(macosDir, sizeof(macosDir), "%s/Contents/MacOS", appDir);
    snprintf(resourcesDir, sizeof(resourcesDir), "%s/Contents/Resources", appDir);

    DIR *d = opendir(resourcesDir);
    if (!d) return;
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL) {
        if (ent->d_name[0] == '.') continue;
        char macosPath[PATH_BUF], target[PATH_BUF];
        snprintf(macosPath, sizeof(macosPath), "%s/%s", macosDir, ent->d_name);

        struct stat st;
        if (lstat(macosPath, &st) == 0) continue;

        snprintf(target, sizeof(target), "../Resources/%s", ent->d_name);
        if (symlink(target, macosPath) == 0)
            logMsg("symlink %s -> %s", ent->d_name, target);
    }
    closedir(d);
}
#endif

static int install(const pchar *appDir, const pchar *newDir,
                   const pchar *backupDir, const pchar *exeDir) {
    if (!hasDir(newDir))
        return -1;

#ifdef _WIN32
    /* argv / sys.executable may mix 8.3 and long names; prefix compare needs one form. */
    wchar_t longApp[PATH_BUF], longExe[PATH_BUF], longNew[PATH_BUF];
    if (GetLongPathNameW(appDir, longApp, PATH_BUF))
        appDir = longApp;
    if (GetLongPathNameW(exeDir, longExe, PATH_BUF))
        exeDir = longExe;
    if (GetLongPathNameW(newDir, longNew, PATH_BUF))
        newDir = longNew;
#endif

    pchar portableSrc[PATH_BUF], portableDst[PATH_BUF];
#ifdef _WIN32
    wsnprintf(portableSrc, PATH_BUF, L"%ls\\GhostDownloader", exeDir);
#else
    snprintf(portableSrc, sizeof(portableSrc), "%s/GhostDownloader", exeDir);
#endif
    if (hasDir(portableSrc)) {
        if (buildNewPortableFolder(portableDst, PATH_BUF, appDir, newDir, exeDir) != 0)
            return -1;
        deleteDir(portableDst);
        if (hasDir(portableDst))
            return -1;
        if (copyDir(portableSrc, portableDst) != 0)
            return -1;
    }
#ifdef _WIN32
    installUninstaller(appDir, newDir);
#endif

    int swapOk = 0;
#ifdef __APPLE__
    if (renamex_np(newDir, appDir, RENAME_SWAP) == 0) {
        /* After SWAP, newDir holds the old tree. Leaving it there makes
           the next patch reuse it as New Dir. */
        if (rename(newDir, backupDir) != 0) {
            logMsg("rename old to backup failed (%s), deleting leftover", strerror(errno));
            deleteDir(newDir);
        }
        swapOk = 1;
    } else {
        logMsg("renamex_np failed (%s), falling back", strerror(errno));
    }
#endif
    if (!swapOk) {
        if (moveDir(appDir, backupDir) != 0)
            return -1;
        if (moveDir(newDir, appDir) != 0) {
            moveDir(backupDir, appDir);
            return -1;
        }
    }
    return 0;
}

#ifdef _WIN32
static int startAppAsUser(const wchar_t *exe) {
    HWND tray = FindWindowW(L"Shell_TrayWnd", NULL);
    if (!tray) return -1;
    DWORD pid = 0;
    GetWindowThreadProcessId(tray, &pid);
    if (!pid) return -1;

    HANDLE hProc = OpenProcess(PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (!hProc) return -1;

    HANDLE hToken = NULL, hPrimary = NULL;
    int ok = -1;
    if (OpenProcessToken(hProc, TOKEN_DUPLICATE, &hToken) &&
        DuplicateTokenEx(hToken,
                         TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY |
                         TOKEN_ADJUST_DEFAULT | TOKEN_ADJUST_SESSIONID,
                         NULL, SecurityImpersonation, TokenPrimary, &hPrimary)) {
        wchar_t cmd[PATH_BUF];
        wsnprintf(cmd, PATH_BUF, L"\"%ls\"", exe);
        STARTUPINFOW si = { .cb = sizeof(si) };
        PROCESS_INFORMATION pi = {0};
        if (CreateProcessAsUserW(hPrimary, NULL, cmd, NULL, NULL, FALSE,
                                 0, NULL, NULL, &si, &pi)) {
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            ok = 0;
        }
    }
    if (hPrimary) CloseHandle(hPrimary);
    if (hToken) CloseHandle(hToken);
    CloseHandle(hProc);
    return ok;
}
#endif

static int startApp(const pchar *exe) {
#ifdef _WIN32
    if (isElevated() && startAppAsUser(exe) == 0)
        return 0;

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

#ifdef __APPLE__
static int restartElevated(const char *appDir, const char *appExe,
                           const char *patchFile) {
    char exePath[PATH_BUF];
    uint32_t size = sizeof(exePath);
    if (_NSGetExecutablePath(exePath, &size) != 0)
        return -1;

    AuthorizationRef auth = NULL;
    if (AuthorizationCreate(NULL, kAuthorizationEmptyEnvironment,
                            kAuthorizationFlagDefaults, &auth) != errAuthorizationSuccess)
        return -1;

    AuthorizationItem right = { "system.privilege.admin", 0, NULL, 0 };
    AuthorizationRights rights = { 1, &right };
    OSStatus st = AuthorizationCopyRights(
        auth, &rights, NULL,
        kAuthorizationFlagInteractionAllowed
            | kAuthorizationFlagPreAuthorize
            | kAuthorizationFlagExtendRights,
        NULL);
    if (st != errAuthorizationSuccess) {
        logMsg("authorization cancelled (%d)", (int)st);
        AuthorizationFree(auth, kAuthorizationFlagDefaults);
        return -1;
    }

    CFStringRef args[5];
    int nArgs = 0;
    args[nArgs++] = CFStringCreateWithCString(NULL, exePath, kCFStringEncodingUTF8);
    args[nArgs++] = CFSTR("0");
    args[nArgs++] = CFStringCreateWithCString(NULL, appDir, kCFStringEncodingUTF8);
    args[nArgs++] = CFStringCreateWithCString(NULL, appExe, kCFStringEncodingUTF8);
    if (patchFile)
        args[nArgs++] = CFStringCreateWithCString(NULL, patchFile, kCFStringEncodingUTF8);
    CFArrayRef progArgs = CFArrayCreate(NULL, (const void **)args, nArgs,
                                        &kCFTypeArrayCallBacks);

    CFStringRef keys[] = {
        CFSTR("Label"),
        CFSTR("ProgramArguments"),
        CFSTR("RunAtLoad"),
        CFSTR("KeepAlive"),
    };
    CFTypeRef vals[] = {
        CFSTR("com.ghostdownloader.updater"),
        progArgs,
        kCFBooleanTrue,
        kCFBooleanFalse,
    };
    CFDictionaryRef job = CFDictionaryCreate(
        NULL, (const void **)keys, (const void **)vals, 4,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);

    CFErrorRef error = NULL;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    Boolean ok = SMJobSubmit(kSMDomainSystemLaunchd, job, auth, &error);
#pragma clang diagnostic pop
    if (!ok && error) {
        CFStringRef desc = CFErrorCopyDescription(error);
        char buf[256];
        CFStringGetCString(desc, buf, sizeof(buf), kCFStringEncodingUTF8);
        logMsg("SMJobSubmit failed: %s", buf);
        CFRelease(desc);
        CFRelease(error);
    }

    CFRelease(job);
    CFRelease(progArgs);
    for (int i = 0; i < nArgs; i++)
        if (args[i] != CFSTR("0")) CFRelease(args[i]);
    AuthorizationFree(auth, kAuthorizationFlagDefaults);

    return ok ? 0 : -1;
}
#endif

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
        return -1;
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
        return -1;

    wchar_t cmd[PATH_BUF * 4];
    size_t cmdSize = PATH_BUF * 4;
    int pos = _snwprintf(cmd, cmdSize, L"\"%ls\"", dstUpdater);
    if (pos < 0 || (size_t)pos >= cmdSize) return -1;
    int truncated = 0;
    for (int i = 1; i < wargc && (size_t)pos < cmdSize; i++) {
        int n = _snwprintf(cmd + pos, cmdSize - pos, L" \"%ls\"", wargv[i]);
        if (n < 0) { truncated = 1; break; }
        pos += n;
    }
    cmd[cmdSize - 1] = L'\0';
    if (truncated) return -1;

    STARTUPINFOW si = { .cb = sizeof(si) };
    PROCESS_INFORMATION pi = {0};
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE,
                        DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                        NULL, tempDir, &si, &pi))
        return -1;

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

    int relocated = restartFromTemp(wargv[2], wargc, wargv);
    if (relocated > 0)
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

    pchar newDir[PATH_BUF], backupDir[PATH_BUF], updaterDir[PATH_BUF], exeDir[PATH_BUF];
#ifdef _WIN32
    wsnprintf(newDir,    PATH_BUF, L"%ls_new",    appDir);
    wsnprintf(backupDir, PATH_BUF, L"%ls_backup", appDir);
    wcsncpy(exeDir, appExe, PATH_BUF - 1);
    exeDir[PATH_BUF - 1] = L'\0';
#else
    snprintf(newDir,    sizeof(newDir),    "%s_new",    appDir);
    snprintf(backupDir, sizeof(backupDir), "%s_backup", appDir);
    snprintf(exeDir, sizeof(exeDir), "%s", appExe);
#endif
    toDirname(exeDir);
    findExeDir(updaterDir, PATH_BUF);

    openLog(exeDir);
#ifdef _WIN32
    if (relocated < 0) {
        logMsg("cannot copy updater out of appDir");
        closeLog();
        return EXIT_RENAME_FAILED;
    }
    /* Windows locks the process cwd against MoveFile. */
    if (updaterDir[0] && !SetCurrentDirectoryW(updaterDir))
        logMsg("SetCurrentDirectory \"" PFMT "\" failed (err=%lu)",
               updaterDir, GetLastError());
#endif
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

#ifdef _WIN32
    if (!canWriteDir(appDir)) {
        if (!isElevated()) {
            logMsg("appDir not writable, elevating");
            closeLog();
            int elevated = restartElevated(wargc, wargv);
            LocalFree(wargv);
            return elevated == 0 ? EXIT_OK : EXIT_RENAME_FAILED;
        }
        logMsg("appDir not writable after elevation");
        closeLog();
        return EXIT_RENAME_FAILED;
    }
#endif

    deleteDir(backupDir);

    int isStagedDir = patchFile && hasDir(patchFile);

    if (patchFile) {
        if (isStagedDir) {
            if (!hasDir(newDir)) {
                logMsg("moving staged dir " PFMT " -> " PFMT, patchFile, newDir);
                if (moveDir(patchFile, newDir) != 0) {
                    logMsg("move staged dir failed");
                    closeLog();
                    return EXIT_RENAME_FAILED;
                }
            }
        } else if (hasDir(newDir)) {
            logMsg("reusing " PFMT, newDir);
        } else if (runHpatchz(updaterDir, appDir, patchFile, newDir) != 0) {
            logMsg("hpatchz failed");
            deleteDir(newDir);
            closeLog();
            return EXIT_PATCH_FAILED;
        } else {
            logMsg("patch applied");
        }
    }

    /* Windows cannot MoveFile a directory while updater.log is open inside it. */
    closeLog();
    if (patchFile && !isStagedDir) {
#ifdef _WIN32
        _wremove(patchFile);
#else
        remove(patchFile);
#endif
        if (hasFile(patchFile)) {
            openLog(exeDir);
            logMsg("cannot delete patch");
            closeLog();
            return EXIT_RENAME_FAILED;
        }
    }
    if (install(appDir, newDir, backupDir, exeDir) != 0) {
#ifdef __APPLE__
        if (geteuid() != 0) {
            openLog(exeDir);
            logMsg("install failed, requesting elevation");
            closeLog();
            if (restartElevated(appDir, appExe, patchFile) == 0)
                return EXIT_OK;
            openLog(exeDir);
            logMsg("elevation failed or cancelled");
            closeLog();
            return EXIT_RENAME_FAILED;
        }
#endif
        openLog(exeDir);
        logMsg("install failed");
        closeLog();
        return EXIT_RENAME_FAILED;
    }
    openLog(exeDir);
    logMsg("installed");

#ifdef __APPLE__
    restructureBundle(appDir);
#endif

    logMsg("starting " PFMT, appExe);
    if (startApp(appExe) != 0) {
        logMsg("start failed, rolling back");
        closeLog();
        if (moveDir(appDir, newDir) == 0)
            moveDir(backupDir, appDir);
        deleteDir(newDir);
        return EXIT_LAUNCH_FAILED;
    }

    logMsg("ok");
    closeLog();
#ifdef _WIN32
    LocalFree(wargv);
#endif
    return EXIT_OK;
}
