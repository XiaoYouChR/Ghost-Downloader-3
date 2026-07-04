import type {SelectTabData, SwitchOnChangeData} from "@fluentui/react-components";
import {Button, Divider, makeStyles, Switch, Tab, TabList} from "@fluentui/react-components";
import {ArrowDownloadRegular, GlobeRegular, ImageRegular, SettingsRegular, WrenchRegular,} from "@fluentui/react-icons";
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
    gap: "4px",
    paddingLeft: "8px",
    paddingRight: "4px",
    marginBottom: "8px",
    overflow: "hidden",
  },
  nav: {
    minWidth: 0,
    flex: 1,
    overflowX: "auto",
    scrollbarWidth: "none",
  },
  bottomRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
    paddingLeft: "8px",
    paddingRight: "4px",
  },
  switches: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    whiteSpace: "nowrap",
    minWidth: 0,
  },
  divider: {
    width: "100%",
    marginTop: "8px",
  },
});

const NAV_ITEMS: Array<{
  key: Extract<PopupView, "tasks" | "resources" | "images" | "advanced">;
  label: string;
  icon: React.JSX.Element;
}> = [
  { key: "tasks", label: chrome.i18n.getMessage("navTasks"), icon: <ArrowDownloadRegular /> },
  { key: "resources", label: chrome.i18n.getMessage("navResources"), icon: <GlobeRegular /> },
  { key: "images", label: chrome.i18n.getMessage("navImages"), icon: <ImageRegular /> },
  { key: "advanced", label: chrome.i18n.getMessage("navAdvanced"), icon: <WrenchRegular /> },
];

export function Header({
  currentView,
  connectionState,
  connectionMessage,
  isMediaButtonEnabled,
  isMediaButtonBusy,
  shouldTakeDownloads,
  isTakeDownloadsBusy,
  pendingTaskCount,
  onViewChange,
  onMediaButtonToggle,
  onTakeDownloadsToggle,
  onLaunchDesktop,
}: {
  currentView: PopupView;
  connectionState: DesktopConnectionState;
  connectionMessage: string;
  isMediaButtonEnabled: boolean;
  isMediaButtonBusy?: boolean;
  shouldTakeDownloads: boolean;
  isTakeDownloadsBusy?: boolean;
  pendingTaskCount: number;
  onViewChange: (view: PopupView) => void;
  onMediaButtonToggle: (enabled: boolean) => void;
  onTakeDownloadsToggle: (enabled: boolean) => void;
  onLaunchDesktop: () => void;
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
          aria-label={chrome.i18n.getMessage("settings")}
          onClick={() => onViewChange("settings")}
        />
      </div>

      <div className={styles.bottomRow}>
        <ConnectionStatusBadge
          state={connectionState}
          message={connectionMessage}
          pendingCount={pendingTaskCount}
          onLaunchDesktop={onLaunchDesktop}
        />

        <div className={styles.switches}>
          <Switch
            checked={isMediaButtonEnabled}
            disabled={isMediaButtonBusy}
            label={chrome.i18n.getMessage("downloadThisMedia")}
            labelPosition="before"
            onChange={(_event, data: SwitchOnChangeData) => onMediaButtonToggle(Boolean(data.checked))}
          />
          <Switch
            checked={shouldTakeDownloads}
            disabled={isTakeDownloadsBusy}
            label={chrome.i18n.getMessage("takeOverDownloads")}
            labelPosition="before"
            onChange={(_event, data: SwitchOnChangeData) => onTakeDownloadsToggle(Boolean(data.checked))}
          />
        </div>
      </div>
      <Divider className={styles.divider} />
    </header>
  );
}
