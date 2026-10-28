import type {SelectTabData, SwitchOnChangeData} from "@fluentui/react-components";
import {makeStyles, Switch, Tab, TabList, tokens, Tooltip} from "@fluentui/react-components";
import {
    ArrowDownloadFilled,
    ArrowDownloadRegular,
    bundleIcon,
    GlobeFilled,
    GlobeRegular,
    ImageFilled,
    ImageRegular,
    SettingsFilled,
    SettingsRegular,
    WrenchFilled,
    WrenchRegular,
} from "@fluentui/react-icons";
import type {DesktopConnectionState, PopupView} from "../../shared/types";
import {ConnectionStatus} from "./ConnectionStatus";

const TasksIcon = bundleIcon(ArrowDownloadFilled, ArrowDownloadRegular);
const ResourcesIcon = bundleIcon(GlobeFilled, GlobeRegular);
const ImagesIcon = bundleIcon(ImageFilled, ImageRegular);
const AdvancedIcon = bundleIcon(WrenchFilled, WrenchRegular);
const SettingsIcon = bundleIcon(SettingsFilled, SettingsRegular);

const TAB_INSET = "6px";
const EDGE = "12px";

const useStyles = makeStyles({
  root: {
    paddingTop: "4px",
    paddingBottom: "4px",
    backgroundColor: tokens.colorNeutralBackground2,
    borderBottom: `${tokens.strokeWidthThin} solid ${tokens.colorNeutralStroke2}`,
  },
  nav: {
    paddingLeft: TAB_INSET,
    paddingRight: TAB_INSET,
    overflowX: "auto",
    scrollbarWidth: "none",
  },
  settingsTab: {
    marginLeft: "auto",
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: EDGE,
    height: "28px",
    paddingLeft: EDGE,
    paddingRight: EDGE,
  },
  switches: {
    display: "flex",
    alignItems: "center",
    gap: EDGE,
    flexShrink: 0,
    whiteSpace: "nowrap",
  },
  switch: {
    alignItems: "center",
  },
  switchIndicator: {
    margin: 0,
  },
  switchLabel: {
    paddingTop: 0,
    paddingBottom: 0,
    paddingLeft: 0,
    paddingRight: "8px",
  },
});

const NAV_ITEMS: Array<{
  key: Extract<PopupView, "tasks" | "resources" | "images" | "advanced">;
  label: string;
  icon: React.JSX.Element;
}> = [
  { key: "tasks", label: chrome.i18n.getMessage("navTasks"), icon: <TasksIcon /> },
  { key: "resources", label: chrome.i18n.getMessage("navResources"), icon: <ResourcesIcon /> },
  { key: "images", label: chrome.i18n.getMessage("navImages"), icon: <ImagesIcon /> },
  { key: "advanced", label: chrome.i18n.getMessage("navAdvanced"), icon: <AdvancedIcon /> },
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
      <TabList
        className={styles.nav}
        appearance="transparent"
        size="small"
        selectedValue={currentView}
        onTabSelect={(_event, data: SelectTabData) => onViewChange(data.value as PopupView)}
      >
        {NAV_ITEMS.map((item) => (
          <Tab key={item.key} value={item.key} icon={item.icon}>
            {item.label}
          </Tab>
        ))}
        <Tooltip content={chrome.i18n.getMessage("settings")} relationship="label">
          <Tab className={styles.settingsTab} value="settings" icon={<SettingsIcon />} />
        </Tooltip>
      </TabList>

      <div className={styles.statusRow}>
        <ConnectionStatus
          state={connectionState}
          message={connectionMessage}
          pendingCount={pendingTaskCount}
          onLaunchDesktop={onLaunchDesktop}
        />

        <div className={styles.switches}>
          <Switch
            className={styles.switch}
            indicator={{ className: styles.switchIndicator }}
            size="small"
            checked={isMediaButtonEnabled}
            disabled={isMediaButtonBusy}
            label={{ className: styles.switchLabel, children: chrome.i18n.getMessage("mediaButtonLabel") }}
            labelPosition="before"
            onChange={(_event, data: SwitchOnChangeData) => onMediaButtonToggle(Boolean(data.checked))}
          />
          <Switch
            className={styles.switch}
            indicator={{ className: styles.switchIndicator }}
            size="small"
            checked={shouldTakeDownloads}
            disabled={isTakeDownloadsBusy}
            label={{ className: styles.switchLabel, children: chrome.i18n.getMessage("takeOverDownloads") }}
            labelPosition="before"
            onChange={(_event, data: SwitchOnChangeData) => onTakeDownloadsToggle(Boolean(data.checked))}
          />
        </div>
      </div>
    </header>
  );
}
