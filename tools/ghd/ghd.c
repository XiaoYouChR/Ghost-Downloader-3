#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

#define COMMAND_LINE_MAX 32768

static const char UNAVAILABLE[] =
    "{\"error\": {\"code\": \"instanceUnavailable\", \"message\": \"Cannot start Ghost-Downloader-3.exe next to the bin folder.\"}}\n";

static const wchar_t *skipProgram(const wchar_t *commandLine) {
    if (*commandLine == L'"') {
        commandLine = wcschr(commandLine + 1, L'"');
        commandLine = commandLine ? commandLine + 1 : L"";
    } else {
        while (*commandLine && *commandLine != L' ' && *commandLine != L'\t') commandLine++;
    }
    while (*commandLine == L' ' || *commandLine == L'\t') commandLine++;
    return commandLine;
}

int wmain(void) {
    wchar_t program[MAX_PATH];
    DWORD length = GetModuleFileNameW(NULL, program, MAX_PATH);
    if (length == 0 || length == MAX_PATH) return 1;
    for (int i = 0; i < 2; i++) *wcsrchr(program, L'\\') = L'\0';
    wcscat_s(program, MAX_PATH, L"\\Ghost-Downloader-3.exe");

    static wchar_t commandLine[COMMAND_LINE_MAX];
    if (_snwprintf_s(commandLine, COMMAND_LINE_MAX, _TRUNCATE, L"\"%ls\" ghd %ls", program,
                     skipProgram(GetCommandLineW())) < 0) return 2;

    STARTUPINFOW startup = {sizeof(startup)};
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION process;
    if (!CreateProcessW(program, commandLine, NULL, NULL, TRUE, 0, NULL, NULL, &startup, &process)) {
        DWORD written;
        WriteFile(startup.hStdOutput, UNAVAILABLE, sizeof(UNAVAILABLE) - 1, &written, NULL);
        return 1;
    }

    DWORD exitCode = 1;
    WaitForSingleObject(process.hProcess, INFINITE);
    GetExitCodeProcess(process.hProcess, &exitCode);
    return (int)exitCode;
}
