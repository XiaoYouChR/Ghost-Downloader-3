import type {SelectTabData} from "@fluentui/react-components";
import {
    Button,
    Caption1,
    Card,
    makeStyles,
    Menu,
    MenuButton,
    MenuItem,
    MenuItemRadio,
    MenuList,
    MenuPopover,
    MenuTrigger,
    Overflow,
    OverflowItem,
    SearchBox,
    Select,
    Tab,
    TabList,
    useIsOverflowItemVisible,
    useOverflowMenu,
} from "@fluentui/react-components";
import {
    ArrowDownloadRegular,
    ArrowSortRegular,
    CheckboxCheckedRegular,
    CheckboxIndeterminateRegular,
    DismissRegular,
    FilterDismissRegular,
    MergeRegular,
    MoreHorizontalRegular,
    TabDesktopRegular,
    WindowMultipleRegular,
} from "@fluentui/react-icons";
import {useEffect, useMemo, useState} from "react";

import type {Resource, ResourceCollectionState, ResourceKind, ResourceScope, ResourceSort} from "../../shared/types";
import {canUseOnlineMergeSelection} from "../../shared/utils";
import {EmptyState} from "../components/EmptyState";
import {ResourceCard} from "../components/ResourceCard";
import {buildResourceView, type ResourceView} from "../resource-view";

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
  searchBox: {
    flex: 1,
    minWidth: 0,
  },
  scopeSelect: {
    minWidth: "100px",
  },
  kindTabs: {
    minWidth: 0,
    overflow: "hidden",
  },
  kindCount: {
    marginLeft: "4px",
    color: "var(--colorNeutralForeground3)",
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

const KIND_LABELS: Record<ResourceKind | "all", string> = {
  all: chrome.i18n.getMessage("filterAll"),
  video: chrome.i18n.getMessage("filterVideo"),
  audio: chrome.i18n.getMessage("filterAudio"),
  pdf: chrome.i18n.getMessage("filterPdf"),
  image: chrome.i18n.getMessage("filterImage"),
  archive: chrome.i18n.getMessage("filterArchive"),
  document: chrome.i18n.getMessage("filterDocument"),
  spreadsheet: chrome.i18n.getMessage("filterSpreadsheet"),
  other: chrome.i18n.getMessage("filterOther"),
};

const SORT_LABELS: Record<ResourceSort, string> = {
  time: chrome.i18n.getMessage("sortByTime"),
  size: chrome.i18n.getMessage("sortBySize"),
  name: chrome.i18n.getMessage("sortByName"),
};

const SORT_STORAGE_KEY = "gd4bResourceSort";

function isResourceSort(value: unknown): value is ResourceSort {
  return value === "time" || value === "size" || value === "name";
}

type KindCount = ResourceView["kindCounts"][number];

function KindLabel({ kindCount }: { kindCount: KindCount }) {
  const styles = useStyles();
  return (
    <>
      {KIND_LABELS[kindCount.kind]}
      <span className={styles.kindCount}>{kindCount.count}</span>
    </>
  );
}

function KindOverflowMenuItem({ kindCount, onSelect }: { kindCount: KindCount; onSelect: (kind: KindCount["kind"]) => void }) {
  const isVisible = useIsOverflowItemVisible(kindCount.kind);
  if (isVisible) {
    return null;
  }
  return (
    <MenuItem onClick={() => onSelect(kindCount.kind)}>
      <KindLabel kindCount={kindCount} />
    </MenuItem>
  );
}

function KindOverflowMenu({ kindCounts, onSelect }: { kindCounts: KindCount[]; onSelect: (kind: KindCount["kind"]) => void }) {
  const { ref, isOverflowing } = useOverflowMenu<HTMLButtonElement>();
  if (!isOverflowing) {
    return null;
  }
  return (
    <Menu>
      <MenuTrigger disableButtonEnhancement>
        <Button
          appearance="transparent"
          aria-label={chrome.i18n.getMessage("moreKinds")}
          icon={<MoreHorizontalRegular />}
          ref={ref}
          role="tab"
          size="small"
        />
      </MenuTrigger>
      <MenuPopover>
        <MenuList>
          {kindCounts.map((kindCount) => (
            <KindOverflowMenuItem key={kindCount.kind} kindCount={kindCount} onSelect={onSelect} />
          ))}
        </MenuList>
      </MenuPopover>
    </Menu>
  );
}

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
  const [kind, setKind] = useState<ResourceKind | "all">("all");
  const [text, setText] = useState("");
  const [sort, setSort] = useState<ResourceSort>("time");
  const [selectedResourceIds, setSelectedResourceIds] = useState<ReadonlySet<string>>(() => new Set());
  const [isDashExpanded, setDashExpanded] = useState(false);
  const [isHlsExpanded, setHlsExpanded] = useState(false);

  const scopedResources = scope === "current" ? currentResources : otherResources;
  const view = useMemo(() => buildResourceView(scopedResources, { kind, text, sort }), [scopedResources, kind, text, sort]);
  const isViewEmpty = view.resources.length + view.dashSegments.length + view.hlsSegments.length === 0;

  const scopedResourceIds = useMemo(() => new Set(scopedResources.map((r) => r.id)), [scopedResources]);
  const selectedResources = useMemo(
    () => scopedResources.filter((r) => selectedResourceIds.has(r.id)),
    [scopedResources, selectedResourceIds],
  );
  const canMerge = connected && canUseOnlineMergeSelection(selectedResources);
  const hasSelection = selectedResources.length > 0;
  const emptyState = emptyCopy(scope, resourceState, resourceStateMessage);

  useEffect(() => {
    void chrome.storage.local
      .get(SORT_STORAGE_KEY)
      .then((stored) => {
        const value = stored[SORT_STORAGE_KEY];
        if (isResourceSort(value)) {
          setSort(value);
        }
      })
      .catch(() => {
        // Keep the default sort when storage is unavailable.
      });
  }, []);

  // Selections hidden by search or kind survive so users can search, pick, and search again.
  useEffect(() => {
    setSelectedResourceIds((current) => {
      const next = new Set([...current].filter((id) => scopedResourceIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [scopedResourceIds]);

  function saveSort(next: ResourceSort) {
    setSort(next);
    void chrome.storage.local.set({ [SORT_STORAGE_KEY]: next });
  }

  function clearFilters() {
    setKind("all");
    setText("");
  }

  function toggleResource(resourceId: string, checked: boolean) {
    setSelectedResourceIds((current) => {
      const next = new Set(current);
      checked ? next.add(resourceId) : next.delete(resourceId);
      return next;
    });
  }

  function visibleResourceIds(): string[] {
    const ids = view.resources.map((r) => r.id);
    if (isDashExpanded) { ids.push(...view.dashSegments.map((r) => r.id)); }
    if (isHlsExpanded) { ids.push(...view.hlsSegments.map((r) => r.id)); }
    return ids;
  }

  function selectAll() {
    setSelectedResourceIds(new Set([...selectedResourceIds, ...visibleResourceIds()]));
  }

  function invertSelection() {
    const next = new Set(selectedResourceIds);
    for (const id of visibleResourceIds()) {
      next.has(id) ? next.delete(id) : next.add(id);
    }
    setSelectedResourceIds(next);
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
        <SearchBox
          className={styles.searchBox}
          placeholder={chrome.i18n.getMessage("searchResourcesPlaceholder")}
          size="small"
          value={text}
          onChange={(_e, data) => setText(data.value)}
        />
        <Menu
          checkedValues={{ sort: [sort] }}
          onCheckedValueChange={(_e, data) => saveSort(data.checkedItems[0] as ResourceSort)}
        >
          <MenuTrigger disableButtonEnhancement>
            <MenuButton appearance="subtle" icon={<ArrowSortRegular />} size="small">{SORT_LABELS[sort]}</MenuButton>
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              {(Object.keys(SORT_LABELS) as ResourceSort[]).map((key) => (
                <MenuItemRadio key={key} name="sort" value={key}>{SORT_LABELS[key]}</MenuItemRadio>
              ))}
            </MenuList>
          </MenuPopover>
        </Menu>
        <Select
          className={styles.scopeSelect}
          size="small"
          value={scope}
          onChange={(_e, data) => setScope(data.value as ResourceScope)}
        >
          <option value="current">{chrome.i18n.getMessage("scopeCurrentPage")}</option>
          <option value="other">{chrome.i18n.getMessage("scopeOtherPages")}</option>
        </Select>
      </div>

      {scopedResources.length > 0 && (
        <Overflow minimumVisible={2}>
          <TabList
            appearance="subtle-circular"
            className={styles.kindTabs}
            selectedValue={kind}
            size="small"
            onTabSelect={(_e, data: SelectTabData) => setKind(data.value as ResourceKind | "all")}
          >
            {view.kindCounts.map((kindCount) => (
              <OverflowItem key={kindCount.kind} id={kindCount.kind} priority={kindCount.kind === kind ? 2 : 1}>
                <Tab value={kindCount.kind}><KindLabel kindCount={kindCount} /></Tab>
              </OverflowItem>
            ))}
            <KindOverflowMenu kindCounts={view.kindCounts} onSelect={setKind} />
          </TabList>
        </Overflow>
      )}

      {scopedResources.length === 0 ? (
        <EmptyState
          icon={scope === "current" ? <TabDesktopRegular /> : <WindowMultipleRegular />}
          title={emptyState.title}
          description={emptyState.description}
        />
      ) : isViewEmpty ? (
        <EmptyState
          icon={<FilterDismissRegular />}
          title={chrome.i18n.getMessage("noMatchingResourcesTitle")}
          description={chrome.i18n.getMessage("noMatchingResourcesDescription")}
          action={<Button size="small" onClick={clearFilters}>{chrome.i18n.getMessage("clearFilters")}</Button>}
        />
      ) : (
        <>
          {/* DASH tracks are usually the main video and audio, so they lead; HLS .ts fragments trail. */}
          {view.dashSegments.length > 0 && (
            <>
              <Card
                appearance="filled-alternative"
                className={styles.foldToggle}
                onClick={() => setDashExpanded(!isDashExpanded)}
              >
                <Caption1>{chrome.i18n.getMessage("dashSegmentsCount", [String(view.dashSegments.length), isDashExpanded ? "▾" : "▸"])}</Caption1>
              </Card>
              {isDashExpanded && (
                <section className={styles.list}>{view.dashSegments.map(renderCard)}</section>
              )}
            </>
          )}

          <section className={styles.list}>
            {view.resources.map(renderCard)}
          </section>

          {view.hlsSegments.length > 0 && (
            <>
              <Card
                appearance="filled-alternative"
                className={styles.foldToggle}
                onClick={() => setHlsExpanded(!isHlsExpanded)}
              >
                <Caption1>{chrome.i18n.getMessage("hlsSegmentsCount", [String(view.hlsSegments.length), isHlsExpanded ? "▾" : "▸"])}</Caption1>
              </Card>
              {isHlsExpanded && (
                <section className={styles.list}>{view.hlsSegments.map(renderCard)}</section>
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
