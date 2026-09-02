import type {SelectTabData} from "@fluentui/react-components";
import {Badge, Button, Caption1, Card, makeStyles, Select, Tab, TabList} from "@fluentui/react-components";
import {
    ArrowDownloadRegular,
    CheckboxCheckedRegular,
    CheckboxIndeterminateRegular,
    DismissRegular,
    MergeRegular,
    TabDesktopRegular,
    WindowMultipleRegular,
} from "@fluentui/react-icons";
import {useEffect, useMemo, useState} from "react";

import type {Resource, ResourceCollectionState, ResourceFilter, ResourceScope} from "../../shared/types";
import {canUseOnlineMergeSelection, fileExtension, filenameFromUrl, filterResources, isDashSegment} from "../../shared/utils";
import {EmptyState} from "../components/EmptyState";
import {ResourceCard} from "../components/ResourceCard";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    gap: "8px",
    padding: "12px 16px",
    paddingBottom: "60px",
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  toolbarSpacer: {
    flex: 1,
  },
  scopeSelect: {
    minWidth: "100px",
  },
  filterTabs: {
    minWidth: 0,
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  foldToggle: {
    padding: "6px 12px",
    cursor: "pointer",
  },
  actionBar: {
    position: "fixed",
    bottom: 0,
    left: 0,
    right: 0,
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "10px 16px",
    backgroundColor: "var(--colorNeutralBackground1)",
    borderTop: "1px solid var(--colorNeutralStroke2)",
    zIndex: 10,
  },
  actionSpacer: {
    flex: 1,
  },
});

const RESOURCE_FILTERS: Array<{ key: ResourceFilter; label: string }> = [
  { key: "all", label: chrome.i18n.getMessage("filterAll") },
  { key: "video", label: chrome.i18n.getMessage("filterVideo") },
  { key: "audio", label: chrome.i18n.getMessage("filterAudio") },
];

function emptyCopy(scope: ResourceScope, state: ResourceCollectionState, message: string) {
  if (scope === "current" && state === "restoring") {
    return { title: chrome.i18n.getMessage("restoringResourcesTitle"), description: message || chrome.i18n.getMessage("restoringResourcesDescription") };
  }
  if (scope === "current" && state === "unavailable") {
    return { title: chrome.i18n.getMessage("resourceBridgeUnavailableTitle"), description: message || chrome.i18n.getMessage("resourceBridgeUnavailableDescription") };
  }
  if (scope === "current") {
    return { title: chrome.i18n.getMessage("emptyCurrentResourcesTitle"), description: chrome.i18n.getMessage("emptyCurrentResourcesDescription") };
  }
  return { title: chrome.i18n.getMessage("emptyOtherResourcesTitle"), description: chrome.i18n.getMessage("emptyOtherResourcesDescription") };
}

export function ResourcesPage({
  currentResources,
  otherResources,
  activePageDomain,
  resourceState,
  resourceStateMessage,
  connected,
  isResourceBusy,
  onSendResource,
  onMergeResources,
}: {
  currentResources: Resource[];
  otherResources: Resource[];
  activePageDomain: string;
  resourceState: ResourceCollectionState;
  resourceStateMessage: string;
  connected: boolean;
  isResourceBusy: (resourceId: string) => boolean;
  onSendResource: (resourceId: string) => void;
  onMergeResources: (resourceIds: string[]) => Promise<boolean>;
}) {
  const styles = useStyles();
  const [scope, setScope] = useState<ResourceScope>("current");
  const [filter, setFilter] = useState<ResourceFilter>("all");
  const [selectedResourceIds, setSelectedResourceIds] = useState<ReadonlySet<string>>(() => new Set());
  const [isDashExpanded, setDashExpanded] = useState(false);
  const [isHlsExpanded, setHlsExpanded] = useState(false);

  const scopedResources = scope === "current" ? currentResources : otherResources;
  const filteredResources = useMemo(() => filterResources(scopedResources, filter), [filter, scopedResources]);

  const hasM3u8 = useMemo(
    () => filteredResources.some((r) => {
      const ext = fileExtension(r.filename || filenameFromUrl(r.url));
      return ext === "m3u8" || ext === "mpd";
    }),
    [filteredResources],
  );

  const { normalResources, dashSegments, hlsSegments } = useMemo(() => {
    const normal: Resource[] = [];
    const dash: Resource[] = [];
    const hls: Resource[] = [];
    for (const r of filteredResources) {
      if (isDashSegment(r)) {
        dash.push(r);
      } else if (hasM3u8 && fileExtension(r.filename || filenameFromUrl(r.url)) === "ts") {
        hls.push(r);
      } else {
        normal.push(r);
      }
    }
    normal.sort((a, b) => {
      const aExt = fileExtension(a.filename || filenameFromUrl(a.url));
      const bExt = fileExtension(b.filename || filenameFromUrl(b.url));
      const aIsManifest = aExt === "m3u8" || aExt === "mpd" ? 1 : 0;
      const bIsManifest = bExt === "m3u8" || bExt === "mpd" ? 1 : 0;
      if (aIsManifest !== bIsManifest) { return bIsManifest - aIsManifest; }
      return b.capturedAt - a.capturedAt;
    });
    return { normalResources: normal, dashSegments: dash, hlsSegments: hls };
  }, [filteredResources, hasM3u8]);

  const filteredResourceIds = useMemo(() => new Set(filteredResources.map((r) => r.id)), [filteredResources]);
  const selectedResources = useMemo(
    () => filteredResources.filter((r) => selectedResourceIds.has(r.id)),
    [filteredResources, selectedResourceIds],
  );
  const canMerge = connected && canUseOnlineMergeSelection(selectedResources);
  const hasSelection = selectedResources.length > 0;
  const emptyState = emptyCopy(scope, resourceState, resourceStateMessage);

  useEffect(() => {
    setSelectedResourceIds((current) => {
      const next = new Set([...current].filter((id) => filteredResourceIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [filteredResourceIds]);

  function toggleResource(resourceId: string, checked: boolean) {
    setSelectedResourceIds((current) => {
      const next = new Set(current);
      checked ? next.add(resourceId) : next.delete(resourceId);
      return next;
    });
  }

  function visibleResourceIds(): string[] {
    const ids = normalResources.map((r) => r.id);
    if (isDashExpanded) { ids.push(...dashSegments.map((r) => r.id)); }
    if (isHlsExpanded) { ids.push(...hlsSegments.map((r) => r.id)); }
    return ids;
  }

  function selectAll() {
    setSelectedResourceIds(new Set(visibleResourceIds()));
  }

  function invertSelection() {
    const visible = visibleResourceIds();
    setSelectedResourceIds(new Set(visible.filter((id) => !selectedResourceIds.has(id))));
  }

  function clearSelection() {
    setSelectedResourceIds(new Set());
  }

  function sendSelected() {
    for (const r of selectedResources) { onSendResource(r.id); }
  }

  async function mergeSelected() {
    if (!selectedResources.length) { return; }
    const ok = await onMergeResources(selectedResources.map((r) => r.id));
    if (ok) { setSelectedResourceIds(new Set()); }
  }

  function renderCard(resource: Resource) {
    return (
      <ResourceCard
        key={resource.id}
        resource={resource}
        connected={connected}
        busy={isResourceBusy(resource.id)}
        selected={selectedResourceIds.has(resource.id)}
        onSend={() => onSendResource(resource.id)}
        onSelectedChange={(checked) => toggleResource(resource.id, checked)}
      />
    );
  }

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <TabList
          appearance="subtle-circular"
          className={styles.filterTabs}
          selectedValue={filter}
          size="small"
          onTabSelect={(_e, data: SelectTabData) => setFilter(data.value as ResourceFilter)}
        >
          {RESOURCE_FILTERS.map((item) => (
            <Tab key={item.key} value={item.key}>{item.label}</Tab>
          ))}
        </TabList>
        <div className={styles.toolbarSpacer} />
        <Select
          className={styles.scopeSelect}
          size="small"
          value={scope}
          onChange={(_e, data) => setScope(data.value as ResourceScope)}
        >
          <option value="current">{chrome.i18n.getMessage("scopeCurrentPage")}</option>
          <option value="other">{chrome.i18n.getMessage("scopeOtherPages")}</option>
        </Select>
        <Badge appearance="outline" color="informative" size="small">{chrome.i18n.getMessage("itemCount", [String(filteredResources.length)])}</Badge>
      </div>

      {filteredResources.length === 0 ? (
        <EmptyState
          icon={scope === "current" ? <TabDesktopRegular /> : <WindowMultipleRegular />}
          title={emptyState.title}
          description={emptyState.description}
        />
      ) : (
        <>
          <section className={styles.list}>
            {normalResources.map(renderCard)}
          </section>

          {dashSegments.length > 0 && (
            <>
              <Card
                appearance="filled-alternative"
                className={styles.foldToggle}
                onClick={() => setDashExpanded(!isDashExpanded)}
              >
                <Caption1>{chrome.i18n.getMessage("dashSegmentsCount", [String(dashSegments.length), isDashExpanded ? "▾" : "▸"])}</Caption1>
              </Card>
              {isDashExpanded && (
                <section className={styles.list}>{dashSegments.map(renderCard)}</section>
              )}
            </>
          )}

          {hlsSegments.length > 0 && (
            <>
              <Card
                appearance="filled-alternative"
                className={styles.foldToggle}
                onClick={() => setHlsExpanded(!isHlsExpanded)}
              >
                <Caption1>{chrome.i18n.getMessage("hlsSegmentsCount", [String(hlsSegments.length), isHlsExpanded ? "▾" : "▸"])}</Caption1>
              </Card>
              {isHlsExpanded && (
                <section className={styles.list}>{hlsSegments.map(renderCard)}</section>
              )}
            </>
          )}
        </>
      )}

      {hasSelection && (
        <div className={styles.actionBar}>
          <Button appearance="subtle" size="small" icon={<CheckboxCheckedRegular />} onClick={selectAll}>{chrome.i18n.getMessage("selectAll")}</Button>
          <Button appearance="subtle" size="small" icon={<CheckboxIndeterminateRegular />} onClick={invertSelection}>{chrome.i18n.getMessage("invertSelection")}</Button>
          <Button appearance="subtle" size="small" icon={<DismissRegular />} onClick={clearSelection}>{chrome.i18n.getMessage("clearSelection")}</Button>
          <div className={styles.actionSpacer} />
          <Button
            appearance="primary"
            disabled={!connected}
            icon={<ArrowDownloadRegular />}
            size="small"
            onClick={sendSelected}
          >
            {chrome.i18n.getMessage("sendCount", [String(selectedResources.length)])}
          </Button>
          <Button
            appearance="secondary"
            disabled={!canMerge}
            icon={<MergeRegular />}
            size="small"
            onClick={() => void mergeSelected()}
          >
            {chrome.i18n.getMessage("merge")}
          </Button>
        </div>
      )}
    </div>
  );
}
