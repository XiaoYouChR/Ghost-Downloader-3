import {
    Body1Strong,
    Button,
    Card,
    Field,
    Input,
    makeStyles,
    MessageBar,
    MessageBarBody,
    Select,
    SpinButton,
    Switch,
} from "@fluentui/react-components";
import type {SpinButtonOnChangeData, SwitchOnChangeData} from "@fluentui/react-components";
import {ArrowClockwiseRegular, ClipboardPasteRegular, PlugConnectedRegular,} from "@fluentui/react-icons";
import {useCallback, useEffect, useState} from "react";

import {DEFAULT_SERVER_URL, EXTENSION_VERSION} from "../../shared/constants";
import {
    BYPASS_MODIFIER_KEY,
    MIN_TAKE_SIZE_KB_KEY,
    SKIP_EXTENSIONS_KEY,
    SHOULD_TAKE_UNKNOWN_SIZE_KEY,
} from "../../background/constants";
import type {ThemePreference} from "../../shared/types";

const SKIP_CATEGORIES = [
  { key: "catImages", extensions: ["jpg", "jpeg", "png", "gif", "webp", "svg", "avif", "bmp", "ico"] },
  { key: "catDocuments", extensions: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt"] },
  { key: "catAudio", extensions: ["mp3", "flac", "wav", "aac", "ogg", "m4a", "wma"] },
];

function parseExtSet(raw: string): Set<string> {
  const result = new Set<string>();
  for (const part of raw.split(",")) {
    const ext = part.trim().replace(/^\./, "").toLowerCase();
    if (ext) { result.add(ext); }
  }
  return result;
}

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
    padding: "16px",
  },
  card: {
    gap: "16px",
    padding: "16px",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "12px",
  },
  inputRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  input: {
    flex: 1,
  },
});

export function SettingsPage({
  desktopVersion,
  token,
  serverUrl,
  savingToken,
  savingServerUrl,
  refreshingConnection,
  requestingPairing,
  onSaveToken,
  onSaveServerUrl,
  onRefreshConnection,
  onRequestPairing,
  themePreference,
  onThemePreferenceChange,
}: {
  desktopVersion: string;
  token: string;
  serverUrl: string;
  savingToken?: boolean;
  savingServerUrl?: boolean;
  refreshingConnection?: boolean;
  requestingPairing?: boolean;
  onSaveToken: (value: string) => Promise<boolean>;
  onSaveServerUrl: (value: string) => Promise<boolean>;
  onRefreshConnection: () => Promise<boolean>;
  onRequestPairing: () => Promise<boolean>;
  themePreference: ThemePreference;
  onThemePreferenceChange: (nextPreference: ThemePreference) => void;
}) {
  const styles = useStyles();
  const [tokenDraft, setTokenDraft] = useState(token);
  const [serverUrlDraft, setServerUrlDraft] = useState(serverUrl || DEFAULT_SERVER_URL);
  const [tokenDirty, setTokenDirty] = useState(false);
  const [serverDirty, setServerDirty] = useState(false);
  const [minSizeKB, setMinSizeKB] = useState(0);
  const [takeUnknownSize, setInterceptUnknown] = useState(true);
  const [skipExtensionsRaw, setSkipExtensionsRaw] = useState("");
  const [bypassModifier, setBypassModifier] = useState("alt");
  const [installType, setInstallType] = useState("");

  const installLabel = useCallback(() => {
    switch (installType) {
      case "development": return chrome.i18n.getMessage("installTypeDevelopment");
      case "admin": case "normal": return chrome.i18n.getMessage("installTypeStore");
      case "sideload": return chrome.i18n.getMessage("installTypeSideload");
      default: return installType || chrome.i18n.getMessage("installTypeUnknown");
    }
  }, [installType]);

  useEffect(() => {
    chrome.management.getSelf((info) => setInstallType(info.installType));
  }, []);

  useEffect(() => {
    chrome.storage.local.get({
      [MIN_TAKE_SIZE_KB_KEY]: 0,
      [SHOULD_TAKE_UNKNOWN_SIZE_KEY]: true,
      [SKIP_EXTENSIONS_KEY]: "",
      [BYPASS_MODIFIER_KEY]: "alt",
    }, (result) => {
      setMinSizeKB(Number(result[MIN_TAKE_SIZE_KB_KEY]) || 0);
      setInterceptUnknown(Boolean(result[SHOULD_TAKE_UNKNOWN_SIZE_KEY] ?? true));
      setSkipExtensionsRaw(String(result[SKIP_EXTENSIONS_KEY] ?? ""));
      setBypassModifier(String(result[BYPASS_MODIFIER_KEY] || "alt"));
    });
  }, []);

  useEffect(() => {
    if (!tokenDirty) {
      setTokenDraft(token);
    }
  }, [token, tokenDirty]);

  useEffect(() => {
    if (!serverDirty) {
      setServerUrlDraft(serverUrl || DEFAULT_SERVER_URL);
    }
  }, [serverDirty, serverUrl]);

  async function commitServerUrl() {
    const nextServerUrl = serverUrlDraft.trim() || DEFAULT_SERVER_URL;
    if (savingServerUrl || nextServerUrl === (serverUrl || DEFAULT_SERVER_URL)) {
      setServerDirty(false);
      return;
    }
    const ok = await onSaveServerUrl(nextServerUrl);
    if (ok) {
      setServerDirty(false);
    }
  }

  async function commitToken() {
    const nextToken = tokenDraft.trim();
    if (savingToken || nextToken === token) {
      setTokenDirty(false);
      return;
    }
    const ok = await onSaveToken(nextToken);
    if (ok) {
      setTokenDirty(false);
    }
  }

  async function pasteToken() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        const nextToken = text.trim();
        setTokenDraft(nextToken);
        setTokenDirty(true);
        const ok = await onSaveToken(nextToken);
        if (ok) {
          setTokenDirty(false);
        }
      }
    } catch {
      // Ignore clipboard permission failures.
    }
  }

  return (
    <div className={styles.root}>
      <Card appearance="filled-alternative" className={styles.card}>
        <div className={styles.header}>
          <Body1Strong>{chrome.i18n.getMessage("connectionConfig")}</Body1Strong>
          <Button
            appearance="primary"
            disabled={requestingPairing || savingToken || savingServerUrl}
            icon={<PlugConnectedRegular />}
            onClick={() => void onRequestPairing()}
          >
            {chrome.i18n.getMessage("autoPair")}
          </Button>
        </div>

        <Field label={chrome.i18n.getMessage("localServerAddress")}>
          <div className={styles.inputRow}>
            <Input
              className={styles.input}
              disabled={savingServerUrl}
              value={serverUrlDraft}
              onBlur={() => void commitServerUrl()}
              onChange={(_event, data) => {
                setServerUrlDraft(data.value);
                setServerDirty(true);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void commitServerUrl();
                }
              }}
            />
            <Button
              disabled={refreshingConnection || savingServerUrl}
              icon={<ArrowClockwiseRegular />}
              aria-label={chrome.i18n.getMessage("reconnect")}
              onClick={() => void onRefreshConnection()}
            />
          </div>
        </Field>

        <Field label={chrome.i18n.getMessage("pairingToken")}>
          <div className={styles.inputRow}>
            <Input
              className={styles.input}
              disabled={savingToken}
              type="password"
              placeholder={chrome.i18n.getMessage("pairingTokenPlaceholder")}
              value={tokenDraft}
              onBlur={() => void commitToken()}
              onChange={(_event, data) => {
                setTokenDraft(data.value);
                setTokenDirty(true);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void commitToken();
                }
              }}
            />
            <Button disabled={savingToken} icon={<ClipboardPasteRegular />} aria-label={chrome.i18n.getMessage("pasteToken")} onClick={() => void pasteToken()} />
          </div>
        </Field>
      </Card>

      <Card appearance="filled-alternative" className={styles.card}>
        <Body1Strong>{chrome.i18n.getMessage("general")}</Body1Strong>

        <Field label={chrome.i18n.getMessage("minInterceptSize")} hint={chrome.i18n.getMessage("minInterceptSizeHint")}>
          <SpinButton
            min={0}
            max={1048576}
            step={100}
            value={minSizeKB}
            displayValue={`${minSizeKB} KB`}
            onChange={(_event, data: SpinButtonOnChangeData) => {
              const value = data.value ?? 0;
              setMinSizeKB(value);
              void chrome.storage.local.set({ [MIN_TAKE_SIZE_KB_KEY]: value });
            }}
          />
        </Field>

        <Field label={chrome.i18n.getMessage("interceptUnknownSize")}>
          <Switch
            checked={takeUnknownSize}
            onChange={(_event, data: SwitchOnChangeData) => {
              setInterceptUnknown(data.checked);
              void chrome.storage.local.set({ [SHOULD_TAKE_UNKNOWN_SIZE_KEY]: data.checked });
            }}
          />
        </Field>

        <Field label={chrome.i18n.getMessage("skipExtensions")} hint={chrome.i18n.getMessage("skipExtensionsHint")}>
          <div style={{ display: "flex", gap: "4px", marginBottom: "8px", flexWrap: "wrap" }}>
            {SKIP_CATEGORIES.map((cat) => {
              const currentSet = parseExtSet(skipExtensionsRaw);
              const active = cat.extensions.every((e) => currentSet.has(e));
              return (
                <Button
                  key={cat.key}
                  size="small"
                  appearance={active ? "primary" : "outline"}
                  onClick={() => {
                    const current = parseExtSet(skipExtensionsRaw);
                    if (active) {
                      cat.extensions.forEach((e) => current.delete(e));
                    } else {
                      cat.extensions.forEach((e) => current.add(e));
                    }
                    const next = [...current].join(", ");
                    setSkipExtensionsRaw(next);
                    void chrome.storage.local.set({ [SKIP_EXTENSIONS_KEY]: next });
                  }}
                >
                  {chrome.i18n.getMessage(cat.key)}
                </Button>
              );
            })}
          </div>
          <Input
            value={skipExtensionsRaw}
            placeholder="jpg, png, gif, webp"
            onChange={(_event, data) => {
              setSkipExtensionsRaw(data.value);
              void chrome.storage.local.set({ [SKIP_EXTENSIONS_KEY]: data.value });
            }}
          />
        </Field>

        <Field label={chrome.i18n.getMessage("bypassShortcutKey")} hint={chrome.i18n.getMessage("bypassShortcutKeyHint")}>
          <Select
            value={bypassModifier}
            onChange={(_event, data) => {
              const value = data.value;
              setBypassModifier(value);
              void chrome.storage.local.set({ [BYPASS_MODIFIER_KEY]: value });
            }}
          >
            <option value="alt">Alt / Option</option>
            <option value="ctrl">Ctrl</option>
            <option value="shift">Shift</option>
          </Select>
        </Field>

        <Field label={chrome.i18n.getMessage("theme")}>
          <Select
            value={themePreference}
            onChange={(_event) => onThemePreferenceChange(_event.currentTarget.value as ThemePreference)}
          >
            <option value="system">{chrome.i18n.getMessage("followSystem")}</option>
            <option value="light">{chrome.i18n.getMessage("lightTheme")}</option>
            <option value="dark">{chrome.i18n.getMessage("darkTheme")}</option>
          </Select>
        </Field>
      </Card>

      <Card appearance="filled-alternative" className={styles.card}>
        <Body1Strong>{chrome.i18n.getMessage("about")}</Body1Strong>
        <MessageBar intent="info">
          <MessageBarBody>{chrome.i18n.getMessage("extensionVersionInfo", [EXTENSION_VERSION])}</MessageBarBody>
        </MessageBar>
        <MessageBar intent="info">
          <MessageBarBody>{chrome.i18n.getMessage("installMethodInfo", [installLabel()])}</MessageBarBody>
        </MessageBar>
        <MessageBar intent={desktopVersion ? "success" : "warning"}>
          <MessageBarBody>{chrome.i18n.getMessage("desktopVersionInfo", [desktopVersion || chrome.i18n.getMessage("notConnected")])}</MessageBarBody>
        </MessageBar>
      </Card>
    </div>
  );
}
