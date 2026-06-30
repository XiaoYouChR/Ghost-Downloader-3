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
    SHOULD_TAKE_UNKNOWN_SIZE_KEY,
} from "../../background/constants";
import type {ThemePreference} from "../../shared/types";

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
  const [bypassModifier, setBypassModifier] = useState("alt");
  const [installType, setInstallType] = useState("");

  const installLabel = useCallback(() => {
    switch (installType) {
      case "development": return "桌面端自管理";
      case "admin": case "normal": return "商店安装";
      case "sideload": return "侧载安装";
      default: return installType || "未知";
    }
  }, [installType]);

  useEffect(() => {
    chrome.management.getSelf((info) => setInstallType(info.installType));
  }, []);

  useEffect(() => {
    chrome.storage.local.get({
      [MIN_TAKE_SIZE_KB_KEY]: 0,
      [SHOULD_TAKE_UNKNOWN_SIZE_KEY]: true,
      [BYPASS_MODIFIER_KEY]: "alt",
    }, (result) => {
      setMinSizeKB(Number(result[MIN_TAKE_SIZE_KB_KEY]) || 0);
      setInterceptUnknown(Boolean(result[SHOULD_TAKE_UNKNOWN_SIZE_KEY] ?? true));
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
          <Body1Strong>连接配置</Body1Strong>
          <Button
            appearance="primary"
            disabled={requestingPairing || savingToken || savingServerUrl}
            icon={<PlugConnectedRegular />}
            onClick={() => void onRequestPairing()}
          >
            自动配对
          </Button>
        </div>

        <Field label="本地服务地址">
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
              aria-label="重新连接"
              onClick={() => void onRefreshConnection()}
            />
          </div>
        </Field>

        <Field label="配对令牌">
          <div className={styles.inputRow}>
            <Input
              className={styles.input}
              disabled={savingToken}
              type="password"
              placeholder="请输入配对令牌"
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
            <Button disabled={savingToken} icon={<ClipboardPasteRegular />} aria-label="粘贴令牌" onClick={() => void pasteToken()} />
          </div>
        </Field>
      </Card>

      <Card appearance="filled-alternative" className={styles.card}>
        <Body1Strong>通用</Body1Strong>

        <Field label="最小拦截大小" hint="低于此大小的文件由浏览器直接下载，0 为全部拦截">
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

        <Field label="大小未知时拦截">
          <Switch
            checked={takeUnknownSize}
            onChange={(_event, data: SwitchOnChangeData) => {
              setInterceptUnknown(data.checked);
              void chrome.storage.local.set({ [SHOULD_TAKE_UNKNOWN_SIZE_KEY]: data.checked });
            }}
          />
        </Field>

        <Field label="跳过拦截快捷键" hint="按住此键点击下载链接，跳过拦截由浏览器下载">
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

        <Field label="主题">
          <Select
            value={themePreference}
            onChange={(_event) => onThemePreferenceChange(_event.currentTarget.value as ThemePreference)}
          >
            <option value="system">跟随系统设置</option>
            <option value="light">浅色</option>
            <option value="dark">深色</option>
          </Select>
        </Field>
      </Card>

      <Card appearance="filled-alternative" className={styles.card}>
        <Body1Strong>关于</Body1Strong>
        <MessageBar intent="info">
          <MessageBarBody>{`扩展版本 ${EXTENSION_VERSION}`}</MessageBarBody>
        </MessageBar>
        <MessageBar intent="info">
          <MessageBarBody>{`安装方式 ${installLabel()}`}</MessageBarBody>
        </MessageBar>
        <MessageBar intent={desktopVersion ? "success" : "warning"}>
          <MessageBarBody>{`桌面端 ${desktopVersion || "未连接"}`}</MessageBarBody>
        </MessageBar>
      </Card>
    </div>
  );
}
