#!/bin/sh
set -eu

REPO="XiaoYouChR/Ghost-Downloader-3"
DESKTOP_ID="com.xychr.ghostdownloader"
ICON_NAME="ghost-downloader"
APP_BIN="Ghost-Downloader-3.bin"
ICON_REL="logo.png"

GITHUB_RAW="https://raw.githubusercontent.com/${REPO}/main"
GITHUB_DL="https://github.com/${REPO}/releases/download"
GITCODE_RAW="https://cnb.cool/${REPO}/-/git/raw/main"
GITCODE_DL="https://gitcode.com/${REPO}/releases/download"

# Only these two paths stay global so trap cleanup can delete them.
WORK_DIR=""
STAGE_DIR=""

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [ -n "$WORK_DIR" ]; then
        rm -rf "$WORK_DIR"
    fi
    if [ -n "$STAGE_DIR" ]; then
        rm -rf "$STAGE_DIR"
    fi
}

fetchFile() {
    # $1=url  $2=dest  [$3=connectTimeoutSec]  [$4=maxTimeSec]
    if command -v curl >/dev/null 2>&1; then
        if [ -n "${4:-}" ]; then
            curl -fsSL --connect-timeout "${3:-10}" --max-time "$4" -o "$2" "$1"
        else
            curl -fsSL --connect-timeout "${3:-10}" -o "$2" "$1"
        fi
    else
        wget -q -T "${3:-10}" -O "$2" "$1"
    fi
}

toSha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print tolower($1)}'
    else
        shasum -a 256 "$1" | awk '{print tolower($1)}'
    fi
}

parseRelease() {
    # $1=versionsJson  $2=platformKey -> "version|file|sha256"
    # versions.json uses json.dump(indent=2), so line matching finds app.version and app.full.<platformKey>.
    awk -v platform="$2" '
        function val(line) {
            sub(/^[^:]*:[ \t]*"/, "", line)
            sub(/".*$/, "", line)
            return line
        }
        /"app":/ && !/\{\}/ { inApp = 1 }
        inApp && /"version":/ && !ver { ver = val($0) }
        inApp && /"full":/ && !/\{\}/ { inFull = 1; depth = 1; next }
        inFull {
            if (index($0, "{")) depth++
            if (index($0, "}")) {
                depth--
                if (depth == 1) inPlat = 0
                if (depth == 0) inFull = 0
            }
            if (depth == 2 && index($0, "\"" platform "\":")) {
                inPlat = 1
                next
            }
            if (inPlat && /"file":/)   file = val($0)
            if (inPlat && /"sha256":/) sha = val($0)
        }
        END { printf "%s|%s|%s\n", ver, file, tolower(sha) }
    ' "$1"
}

installAppDir() {
    # $1=archivePath  $2=appDir
    if [ -e "$2" ]; then
        if [ ! -d "$2" ]; then
            die "refusing to overwrite ${2}: not a directory"
        fi
        entries=$(ls -A "$2")
        if [ ! -f "$2/$APP_BIN" ] && [ -n "$entries" ]; then
            # Allow reinstalling into an App Dir that only keeps a Portable Folder from --uninstall.
            if [ "$entries" != "GhostDownloader" ] || [ ! -d "$2/GhostDownloader" ]; then
                die "refusing to overwrite non-empty directory ${2}: ${APP_BIN} not found"
            fi
        fi
    fi

    parentDir=$(dirname "$2")
    mkdir -p "$parentDir"
    # Put the staging folder next to App Dir so mv stays on the same filesystem.
    STAGE_DIR=$(mktemp -d "${parentDir}/.gd3-stage.XXXXXX")
    chmod 755 "$STAGE_DIR"

    tar -xJf "$1" -C "$STAGE_DIR"
    [ -f "$STAGE_DIR/$APP_BIN" ] || die "archive missing ${APP_BIN}"
    chmod +x "$STAGE_DIR/$APP_BIN"

    backupDir="${2}_backup"
    rm -rf "$backupDir"
    if [ -e "$2" ]; then
        mv "$2" "$backupDir"
    fi
    if ! mv "$STAGE_DIR" "$2"; then
        if [ -e "$backupDir" ] && [ ! -e "$2" ]; then
            mv "$backupDir" "$2" || true
        fi
        die "failed to install into $2"
    fi
    STAGE_DIR=""
    # Keep Portable Folder when upgrading an existing install.
    if [ -d "$backupDir/GhostDownloader" ]; then
        mv "$backupDir/GhostDownloader" "$2/GhostDownloader" \
            || die "failed to restore Portable Folder from ${backupDir}"
    fi
    rm -rf "$backupDir" || true
}

refreshDesktopCaches() {
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$1/applications" 2>/dev/null || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "$1/icons/hicolor" 2>/dev/null || true
    fi
}

runInstall() {
    sourceMode="$1"
    appDir="$2"
    dataHome="$3"
    binDir="$4"

    [ "$(uname -s)" = "Linux" ] || die "this installer only supports Linux"
    case "$(uname -m)" in
        x86_64|amd64)  platformKey="Linux-x86_64" ;;
        aarch64|arm64) platformKey="Linux-arm64" ;;
        *) die "unsupported architecture: $(uname -m)" ;;
    esac

    command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || die "curl or wget is required"
    command -v tar >/dev/null 2>&1 || die "tar is required"
    command -v xz  >/dev/null 2>&1 || die "xz is required"
    command -v awk >/dev/null 2>&1 || die "awk is required"
    command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1 || die "sha256sum or shasum is required"

    WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/gd3-install.XXXXXX")
    versionsFile="$WORK_DIR/versions.json"

    printf 'Fetching version metadata (%s)...\n' "$platformKey"
    if [ "$sourceMode" = "gitcode" ]; then
        rawBase="$GITCODE_RAW"
        fallbackRawBase=""
        dlBase="$GITCODE_DL"
        fallbackDlBase=""
        fetchFile "${rawBase}/versions.json" "$versionsFile" 10 15 || die "failed to fetch versions.json"
    elif [ "$sourceMode" = "github" ]; then
        rawBase="$GITHUB_RAW"
        fallbackRawBase=""
        dlBase="$GITHUB_DL"
        fallbackDlBase=""
        fetchFile "${rawBase}/versions.json" "$versionsFile" 10 15 || die "failed to fetch versions.json"
    elif fetchFile "${GITHUB_RAW}/versions.json" "$versionsFile" 5 15 2>/dev/null; then
        rawBase="$GITHUB_RAW"
        fallbackRawBase="$GITCODE_RAW"
        dlBase="$GITHUB_DL"
        fallbackDlBase="$GITCODE_DL"
    elif fetchFile "${GITCODE_RAW}/versions.json" "$versionsFile" 10 15; then
        rawBase="$GITCODE_RAW"
        fallbackRawBase="$GITHUB_RAW"
        dlBase="$GITCODE_DL"
        fallbackDlBase="$GITHUB_DL"
    else
        die "failed to fetch versions.json"
    fi

    IFS='|' read -r version assetFile expectedSha <<EOF
$(parseRelease "$versionsFile" "$platformKey")
EOF
    [ -n "$version" ] && [ -n "$assetFile" ] && [ -n "$expectedSha" ] \
        || die "no Linux release entry for ${platformKey} in versions.json"
    case "$assetFile" in
        */*|*..*) die "unsafe asset filename: ${assetFile}" ;;
    esac
    [ "${#expectedSha}" -eq 64 ] || die "invalid sha256 in versions.json: ${expectedSha}"
    case "$expectedSha" in
        *[!0-9a-f]*) die "invalid sha256 in versions.json: ${expectedSha}" ;;
    esac

    archiveFile="$WORK_DIR/$assetFile"
    printf 'Downloading Ghost Downloader v%s (%s)...\n' "$version" "$assetFile"
    if ! fetchFile "${dlBase}/v${version}/${assetFile}" "$archiveFile" 30; then
        if [ -n "$fallbackDlBase" ]; then
            fetchFile "${fallbackDlBase}/v${version}/${assetFile}" "$archiveFile" 30 \
                || die "failed to download ${assetFile}"
        else
            die "failed to download ${assetFile}"
        fi
    fi

    actualSha=$(toSha256 "$archiveFile")
    [ "$actualSha" = "$expectedSha" ] || die "sha256 mismatch (expected ${expectedSha}, got ${actualSha})"

    printf 'Installing to %s...\n' "$appDir"
    installAppDir "$archiveFile" "$appDir"

    mkdir -p "$binDir"
    ln -sfn "$appDir/$APP_BIN" "$binDir/ghost-downloader"
    ln -sfn "$appDir/$APP_BIN" "$binDir/ghd"

    desktopDir="$dataHome/applications"
    iconDir="$dataHome/icons/hicolor/256x256/apps"
    desktopFile="$desktopDir/${DESKTOP_ID}.desktop"
    mkdir -p "$desktopDir" "$iconDir"
    if [ -f "$appDir/$ICON_REL" ]; then
        cp -f "$appDir/$ICON_REL" "$iconDir/${ICON_NAME}.png"
    else
        # Fetch logo.png from the repository when the archive does not include it.
        iconTmp="$WORK_DIR/${ICON_NAME}.png"
        if fetchFile "${rawBase}/app/assets/logo.png" "$iconTmp" 10 15 2>/dev/null \
            || { [ -n "$fallbackRawBase" ] && fetchFile "${fallbackRawBase}/app/assets/logo.png" "$iconTmp" 10 15 2>/dev/null; }; then
            cp -f "$iconTmp" "$iconDir/${ICON_NAME}.png"
        fi
    fi

    {
        printf '[Desktop Entry]\n'
        printf 'Type=Application\n'
        printf 'Name=Ghost Downloader\n'
        printf 'Comment=The only downloader you need\n'
        printf 'Exec="%s/%s" %%U\n' "$appDir" "$APP_BIN"
        printf 'Icon=%s\n' "$ICON_NAME"
        printf 'Terminal=false\n'
        printf 'Categories=Network;Utility;\n'
    } > "$desktopFile"
    refreshDesktopCaches "$dataHome"

    case ":${PATH:-}:" in
        *":${binDir}:"*) ;;
        *) printf 'Note: %s is not in PATH. Add it to your shell profile to use ghost-downloader / ghd.\n' "$binDir" >&2 ;;
    esac
    printf 'Ghost Downloader v%s installed.\n' "$version"
}

runUninstall() {
    appDir="$1"
    dataHome="$2"
    configHome="$3"
    binDir="$4"

    # Do not delete anything if App Dir does not exist or points to an unrelated folder.
    [ -e "$appDir" ] || die "${appDir} does not exist"
    if [ ! -d "$appDir" ] || [ ! -f "$appDir/$APP_BIN" ]; then
        die "refusing to delete ${appDir}: ${APP_BIN} not found"
    fi

    # Resolve physical App Dir so symlinks created via Path.resolve() match on symlinked $HOME.
    realAppDir=$(cd -P -- "$appDir" && pwd)

    # Delete only links that point into App Dir so another Command Line Tool install stays intact.
    for name in ghost-downloader ghd; do
        linkPath="$binDir/$name"
        [ -L "$linkPath" ] || continue
        case "$(readlink "$linkPath" || true)" in
            "${appDir}/"*|"${realAppDir}/"*) rm -f "$linkPath" ;;
        esac
    done

    rm -f "$dataHome/applications/${DESKTOP_ID}.desktop"
    rm -f "$dataHome/applications/${DESKTOP_ID}.handler.desktop"
    rm -f "$dataHome/dbus-1/services/${DESKTOP_ID}.service"
    rm -f "$dataHome/icons/hicolor/256x256/apps/${ICON_NAME}.png"
    rm -f "$configHome/autostart/${DESKTOP_ID}.desktop"
    rm -rf "${appDir}_backup"

    if [ -d "$appDir/GhostDownloader" ]; then
        # Keep Portable Folder intact; delete only the application files beside it.
        for entry in "$appDir"/* "$appDir"/.[!.]* "$appDir"/..?*; do
            if [ ! -e "$entry" ] && [ ! -L "$entry" ]; then
                continue
            fi
            if [ "$entry" = "$appDir/GhostDownloader" ]; then
                continue
            fi
            rm -rf "$entry"
        done
        refreshDesktopCaches "$dataHome"
        printf 'Ghost Downloader uninstalled. Portable Folder preserved in %s/GhostDownloader.\n' "$appDir"
        return 0
    fi

    rm -rf "$appDir"
    refreshDesktopCaches "$dataHome"

    printf 'Ghost Downloader uninstalled. Data Folder preserved in %s/GhostDownloader.\n' "$dataHome"
}

main() {
    trap cleanup EXIT
    trap 'trap - EXIT; cleanup; exit 130' INT
    trap 'trap - EXIT; cleanup; exit 143' TERM

    action="install"
    sourceMode="auto"
    appDir=""

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --source)
                [ "$#" -ge 2 ] || die "--source requires a value"
                case "$2" in
                    auto|github|gitcode) sourceMode="$2" ;;
                    *) die "unknown source: $2" ;;
                esac
                shift 2
                ;;
            --dir)
                [ "$#" -ge 2 ] && [ -n "$2" ] || die "--dir requires a non-empty path"
                appDir="$2"
                shift 2
                ;;
            --uninstall)
                action="uninstall"
                shift
                ;;
            --help|-h)
                cat <<'EOF'
Usage: install.sh [--source auto|github|gitcode] [--dir <path>] [--uninstall] [--help]
EOF
                exit 0
                ;;
            *)
                die "unknown option: $1 (try --help)"
                ;;
        esac
    done

    case "${HOME:-}" in
        /*) ;;
        *) die "HOME must be an absolute path" ;;
    esac
    case "${XDG_DATA_HOME:-}" in
        /*) dataHome="$XDG_DATA_HOME" ;;
        *)  dataHome="$HOME/.local/share" ;;
    esac
    case "${XDG_CONFIG_HOME:-}" in
        /*) configHome="$XDG_CONFIG_HOME" ;;
        *)  configHome="$HOME/.config" ;;
    esac

    binDir="$HOME/.local/bin"
    [ -n "$appDir" ] || appDir="$HOME/.local/lib/ghost-downloader"
    while [ "${appDir%/}" != "$appDir" ]; do
        appDir="${appDir%/}"
    done
    case "$appDir" in
        /*) ;;
        *) die "--dir must be a non-root absolute path" ;;
    esac

    if [ "$action" = "uninstall" ]; then
        runUninstall "$appDir" "$dataHome" "$configHome" "$binDir"
    else
        runInstall "$sourceMode" "$appDir" "$dataHome" "$binDir"
    fi
}

main "$@"
