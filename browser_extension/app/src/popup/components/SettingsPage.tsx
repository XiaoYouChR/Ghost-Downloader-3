import {
  Body1Strong,
  Button,
  Card,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  Select,
  makeStyles,
} from "@fluentui/react-components";
import {
  ArrowClockwiseRegular,
  ClipboardPasteRegular,
} from "@fluentui/react-icons";
import { useEffect, useState } from "react";

import { DEFAULT_SERVER_URL, EXTENSION_VERSION, HELP_CONTENT } from "../../shared/constants";
import type { DesktopConnectionState, ThemePreference } from "../../shared/types";
import { connectionLabel } from "../../shared/utils";
import { ConnectionStatusBadge } from "./ConnectionStatusBadge";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "20px",
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
  statusCard: {
    gap: "8px",
    padding: "16px",
  },
  appearanceCard: {
    gap: "12px",
    padding: "16px",
  },
  helpSection: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  helpCard: {
    gap: "12px",
    padding: "16px",
  },
  helpList: {
    margin: 0,
    paddingLeft: "20px",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    fontSize: "14px",
  },
});

export function SettingsPage({
  connectionState,
  connectionMessage,
  desktopVersion,
  token,
  serverUrl,
  savingToken,
  savingServerUrl,
  refreshingConnection,
  onSaveToken,
  onSaveServerUrl,
  onRefreshConnection,
  themePreference,
  resolvedThemePreference,
  onThemePreferenceChange,
}: {
  connectionState: DesktopConnectionState;
  connectionMessage: string;
  desktopVersion: string;
  token: string;
  serverUrl: string;
  savingToken?: boolean;
  savingServerUrl?: boolean;
  refreshingConnection?: boolean;
  onSaveToken: (value: string) => Promise<boolean>;
  onSaveServerUrl: (value: string) => Promise<boolean>;
  onRefreshConnection: () => Promise<boolean>;
  themePreference: ThemePreference;
  resolvedThemePreference: Exclude<ThemePreference, "system">;
  onThemePreferenceChange: (nextPreference: ThemePreference) => void;
}) {
  const styles = useStyles();
  const [tokenDraft, setTokenDraft] = useState(token);
  const [serverUrlDraft, setServerUrlDraft] = useState(serverUrl || DEFAULT_SERVER_URL);
  const [tokenDirty, setTokenDirty] = useState(false);
  const [serverDirty, setServerDirty] = useState(false);

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
          <ConnectionStatusBadge state={connectionState} message={connectionMessage} />
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

      <Card appearance="filled-alternative" className={styles.statusCard}>
        <Body1Strong>服务状态</Body1Strong>
        <MessageBar intent="info">
          <MessageBarBody>{`连接状态：${connectionLabel(connectionState, connectionMessage)}`}</MessageBarBody>
        </MessageBar>
        <MessageBar intent="info">
          <MessageBarBody>{`扩展版本：${EXTENSION_VERSION}`}</MessageBarBody>
        </MessageBar>
        <MessageBar intent="info">
          <MessageBarBody>{`桌面端版本：${desktopVersion || "未连接"}`}</MessageBarBody>
        </MessageBar>
      </Card>

      <Card appearance="filled-alternative" className={styles.appearanceCard}>
        <Body1Strong>界面外观</Body1Strong>
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
        {/* <MessageBar intent="info">
          <MessageBarBody>
            {themePreference === "system"
              ? `当前正在跟随系统，实际使用${resolvedThemePreference === "dark" ? "深色" : "浅色"}主题`
              : `当前正在使用${themePreference === "dark" ? "深色" : "浅色"}主题`}
          </MessageBarBody>
        </MessageBar> */}
      </Card>

      <section className={styles.helpSection}>
        <Body1Strong>帮助与支持</Body1Strong>
        {Object.values(HELP_CONTENT).map((entry) => (
          <Card key={entry.title} appearance="filled-alternative" className={styles.helpCard}>
            <Body1Strong>{entry.title}</Body1Strong>
            <ul className={styles.helpList}>
              {entry.body.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </Card>
        ))}
      </section>
    </div>
  );
}
