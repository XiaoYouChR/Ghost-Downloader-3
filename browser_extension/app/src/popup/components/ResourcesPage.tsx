import { Badge, Button, Caption1, Card, Tab, TabList, makeStyles } from "@fluentui/react-components";
import type { SelectTabData } from "@fluentui/react-components";
import { TabDesktopRegular, WindowMultipleRegular } from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";

import type { CapturedResource, ResourceCollectionState, ResourceFilter, ResourceScope } from "../../shared/types";
import { canUseOnlineMergeSelection, filterResources } from "../../shared/utils";
import { EmptyState } from "./EmptyState";
import { ResourceCard } from "./ResourceCard";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    padding: "16px",
  },
  scopeCard: {
    padding: "16px",
  },
  scopeRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    width: "100%",
  },
  scopeTabs: {
    minWidth: 0,
    flex: 1,
  },
  scopeCaption: {
    marginLeft: "auto",
    whiteSpace: "nowrap",
  },
  filterRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  filterCount: {
    marginLeft: "auto",
  },
  selectionCard: {
    padding: "12px 16px",
  },
  selectionRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flexWrap: "wrap",
  },
  selectionActions: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginLeft: "auto",
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
});

const RESOURCE_FILTERS: Array<{ key: ResourceFilter; label: string }> = [
  { key: "all", label: "全部" },
  { key: "video", label: "视频" },
  { key: "audio", label: "音频" },
  { key: "streaming", label: "流媒体" },
];

function emptyCopy(scope: ResourceScope, state: ResourceCollectionState, message: string) {
  if (scope === "current" && state === "restoring") {
    return {
      title: "正在恢复当前页面资源",
      description: message || "正在恢复已捕获的资源。",
    };
  }
  if (scope === "current" && state === "unavailable") {
    return {
      title: "当前标签页暂不支持资源桥接",
      description: message || "当前标签页暂时无法提供资源列表。",
    };
  }
  if (scope === "current") {
    return {
      title: "当前页面还没有资源",
      description: "启用深度搜索或缓存捕捉后，这里会显示桥接过来的页面资源。",
    };
  }
  return {
    title: "还没有其他页面的资源",
    description: "切换到其他标签页并捕获到资源后，这里会自动汇总显示。",
  };
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
  currentResources: CapturedResource[];
  otherResources: CapturedResource[];
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

  const scopedResources = scope === "current" ? currentResources : otherResources;
  const filteredResources = useMemo(() => filterResources(scopedResources, filter), [filter, scopedResources]);
  const filteredResourceIds = useMemo(() => new Set(filteredResources.map((resource) => resource.id)), [filteredResources]);
  const selectedResources = useMemo(
    () => filteredResources.filter((resource) => selectedResourceIds.has(resource.id)),
    [filteredResources, selectedResourceIds],
  );
  const canMergeSelectedResources = connected && canUseOnlineMergeSelection(selectedResources);
  const emptyState = emptyCopy(scope, resourceState, resourceStateMessage);

  useEffect(() => {
    setSelectedResourceIds((current) => {
      const next = new Set([...current].filter((resourceId) => filteredResourceIds.has(resourceId)));
      return next.size === current.size ? current : next;
    });
  }, [filteredResourceIds]);

  function toggleResource(resourceId: string, checked: boolean) {
    setSelectedResourceIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(resourceId);
      } else {
        next.delete(resourceId);
      }
      return next;
    });
  }

  function selectVisibleResources() {
    setSelectedResourceIds(new Set(filteredResources.map((resource) => resource.id)));
  }

  function clearSelection() {
    setSelectedResourceIds(new Set());
  }

  async function handleOnlineMerge() {
    if (!selectedResources.length) {
      return;
    }
    const success = await onMergeResources(selectedResources.map((resource) => resource.id));
    if (success) {
      clearSelection();
    }
  }

  return (
    <div className={styles.root}>
      <Card appearance="filled-alternative" className={styles.scopeCard}>
        <div className={styles.scopeRow}>
          <TabList
            appearance="subtle-circular"
            className={styles.scopeTabs}
            reserveSelectedTabSpace={false}
            selectedValue={scope}
            size="small"
            onTabSelect={(_event, data: SelectTabData) => setScope(data.value as ResourceScope)}
          >
            <Tab value="current">当前页面</Tab>
            <Tab value="other">其他页面</Tab>
          </TabList>
          <Caption1 className={styles.scopeCaption}>
            {scope === "current" ? activePageDomain || "当前标签页" : "所有已捕获"}
          </Caption1>
        </div>
      </Card>

      <div className={styles.filterRow}>
        <TabList
          appearance="subtle-circular"
          selectedValue={filter}
          size="small"
          onTabSelect={(_event, data: SelectTabData) => setFilter(data.value as ResourceFilter)}
        >
          {RESOURCE_FILTERS.map((item) => (
            <Tab key={item.key} value={item.key}>
              {item.label}
            </Tab>
          ))}
        </TabList>
        <Badge appearance="outline" color="subtle" className={styles.filterCount}>
          {`${filteredResources.length} 项资源`}
        </Badge>
      </div>

      {filteredResources.length > 0 ? (
        <Card appearance="filled-alternative" className={styles.selectionCard}>
          <div className={styles.selectionRow}>
            <Badge appearance="tint" color="brand">
              {selectedResources.length > 0 ? `已选 ${selectedResources.length} 项` : "未选择资源"}
            </Badge>
            <Caption1>
              合并音视频暂时只支持 1 个 HTTP 视频资源和 1 个 HTTP 音频资源，blob 资源暂不支持
            </Caption1>
            <div className={styles.selectionActions}>
              <Button appearance="secondary" size="small" onClick={selectVisibleResources}>
                全选
              </Button>
              <Button appearance="subtle" size="small" onClick={clearSelection}>
                清空
              </Button>
              <Button
                appearance="primary"
                disabled={!canMergeSelectedResources}
                size="small"
                onClick={() => void handleOnlineMerge()}
              >
                合并音视频
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      {filteredResources.length === 0 ? (
        <EmptyState
          icon={scope === "current" ? <TabDesktopRegular /> : <WindowMultipleRegular />}
          title={emptyState.title}
          description={emptyState.description}
        />
      ) : (
        <section className={styles.list}>
          {filteredResources.map((resource) => (
            <ResourceCard
              key={resource.id}
              resource={resource}
              connected={connected}
              busy={isResourceBusy(resource.id)}
              selected={selectedResourceIds.has(resource.id)}
              onSend={() => onSendResource(resource.id)}
              onSelectedChange={(checked) => toggleResource(resource.id, checked)}
            />
          ))}
        </section>
      )}
    </div>
  );
}
