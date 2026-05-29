import type {SelectTabData, SwitchOnChangeData} from "@fluentui/react-components";
import {Button, Divider, makeStyles, Switch, Tab, TabList} from "@fluentui/react-components";
import {ArrowDownloadRegular, GlobeRegular, SettingsRegular, WrenchRegular,} from "@fluentui/react-icons";

import type {DesktopConnectionState, PopupView} from "../../shared/types";
import {ConnectionStatusBadge} from "./ConnectionStatusBadge";

const useStyles = makeStyles({
  root: {
    paddingTop: "8px",
    paddingBottom: "0",
  },
  topRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "12px",
    paddingLeft: "16px",
    paddingRight: "16px",
    marginBottom: "8px",
  },
  nav: {
    minWidth: 0,
    flex: 1,
  },
  bottomRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "12px",
    paddingLeft: "16px",
    paddingRight: "16px",
  },
  switches: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    whiteSpace: "nowrap",
  },
  divider: {
    width: "100%",
    marginTop: "8px",
  },
});

const NAV_ITEMS: Array<{
  key: Extract<PopupView, "tasks" | "resources" | "advanced">;
  label: string;
  icon: JSX.Element;
}> = [
  { key: "tasks", label: "下载任务", icon: <ArrowDownloadRegular /> },
  { key: "resources", label: "资源嗅探", icon: <GlobeRegular /> },
  { key: "advanced", label: "高级功能", icon: <WrenchRegular /> },
];

export function Header({
  currentView,
  connectionState,
  connectionMessage,
  mediaDownloadOverlayEnabled,
  mediaDownloadOverlayBusy,
  interceptEnabled,
  interceptBusy,
  onViewChange,
  onMediaDownloadOverlayToggle,
  onInterceptToggle,
}: {
  currentView: PopupView;
  connectionState: DesktopConnectionState;
  connectionMessage: string;
  mediaDownloadOverlayEnabled: boolean;
  mediaDownloadOverlayBusy?: boolean;
  interceptEnabled: boolean;
  interceptBusy?: boolean;
  onViewChange: (view: PopupView) => void;
  onMediaDownloadOverlayToggle: (enabled: boolean) => void;
  onInterceptToggle: (enabled: boolean) => void;
}) {
  const styles = useStyles();

  return (
    <header className={styles.root}>
      <div className={styles.topRow}>
        <TabList
          className={styles.nav}
          appearance="subtle-circular"
          selectedValue={currentView === "settings" ? undefined : currentView}
          onTabSelect={(_event, data: SelectTabData) => onViewChange(data.value as PopupView)}
        >
          {NAV_ITEMS.map((item) => (
            <Tab key={item.key} value={item.key} icon={item.icon}>
              {item.label}
            </Tab>
          ))}
        </TabList>

        <Button
          appearance={currentView === "settings" ? "primary" : "secondary"}
          icon={<SettingsRegular />}
          aria-label="设置"
          onClick={() => onViewChange("settings")}
        />
      </div>

      <div className={styles.bottomRow}>
        <ConnectionStatusBadge state={connectionState} message={connectionMessage} />

        <div className={styles.switches}>
          <Switch
            checked={mediaDownloadOverlayEnabled}
            disabled={mediaDownloadOverlayBusy}
            label="下载此媒体"
            labelPosition="before"
            onChange={(_event, data: SwitchOnChangeData) => onMediaDownloadOverlayToggle(Boolean(data.checked))}
          />
          <Switch
            checked={interceptEnabled}
            disabled={interceptBusy}
            label="拦截下载"
            labelPosition="before"
            onChange={(_event, data: SwitchOnChangeData) => onInterceptToggle(Boolean(data.checked))}
          />
        </div>
      </div>
      <Divider className={styles.divider} />
    </header>
  );
}
