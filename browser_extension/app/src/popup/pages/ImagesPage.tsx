import {Badge, Button, Caption1, Card, makeStyles, Select, Slider} from "@fluentui/react-components";
import {
    ArrowDownloadRegular,
    ArrowSortDownRegular,
    ArrowSortUpRegular,
    ArrowSyncRegular,
    CheckboxCheckedRegular,
    CheckboxIndeterminateRegular,
    DismissRegular,
    FilterRegular,
    ImageRegular,
} from "@fluentui/react-icons";
import {useCallback, useEffect, useMemo, useState} from "react";

import type {ScannedImage} from "../../shared/types";
import {fileExtension, filenameFromUrl} from "../../shared/utils";
import {EmptyState} from "../components/EmptyState";
import {ImageCard} from "../components/ImageCard";
import {scanActiveTabImages} from "../scan-images";

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
  sortSelect: {
    minWidth: "90px",
  },
  filterPanel: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    padding: "10px 12px",
  },
  sliderRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  sliderLabel: {
    flexShrink: 0,
    width: "28px",
  },
  slider: {
    flex: 1,
  },
  sliderValue: {
    flexShrink: 0,
    width: "80px",
    textAlign: "right",
  },
  formatChips: {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
  },
  formatChip: {
    cursor: "pointer",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: "8px",
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

type SortField = "area" | "width" | "height";
type SortDirection = "desc" | "asc";

type EnrichedImage = ScannedImage & { ext: string; area: number };

function enrichImages(images: ScannedImage[]): EnrichedImage[] {
  return images.map((img) => ({
    ...img,
    ext: fileExtension(filenameFromUrl(img.src)).toUpperCase() || "OTHER",
    area: img.naturalWidth * img.naturalHeight,
  }));
}

type FormatCount = { format: string; count: number };

function collectFormats(images: EnrichedImage[]): FormatCount[] {
  const counts = new Map<string, number>();
  for (const img of images) {
    counts.set(img.ext, (counts.get(img.ext) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([format, count]) => ({ format, count }));
}

function sortKey(img: EnrichedImage, field: SortField): number {
  switch (field) {
    case "area": return img.area;
    case "width": return img.naturalWidth;
    case "height": return img.naturalHeight;
  }
}

function sortImages(images: EnrichedImage[], field: SortField, direction: SortDirection): EnrichedImage[] {
  const sign = direction === "desc" ? -1 : 1;
  return [...images].sort((a, b) => sign * (sortKey(a, field) - sortKey(b, field)));
}

export function ImagesPage({
  connected,
  onSendImages,
}: {
  connected: boolean;
  onSendImages: (images: ScannedImage[]) => Promise<boolean>;
}) {
  const styles = useStyles();
  const [images, setImages] = useState<ScannedImage[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [hasScanned, setHasScanned] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [sortField, setSortField] = useState<SortField>("area");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [minWidth, setMinWidth] = useState(0);
  const [minHeight, setMinHeight] = useState(0);
  const [enabledFormats, setEnabledFormats] = useState<ReadonlySet<string> | null>(null);
  const [selectedSrcs, setSelectedSrcs] = useState<ReadonlySet<string>>(() => new Set());

  const scan = useCallback(async () => {
    setIsScanning(true);
    try {
      const result = await scanActiveTabImages();
      setImages(result);
      setHasScanned(true);
      setSelectedSrcs(new Set());
      setEnabledFormats(null);
      setMinWidth(0);
      setMinHeight(0);
    } finally {
      setIsScanning(false);
    }
  }, []);

  useEffect(() => {
    void scan();
  }, [scan]);

  const enriched = useMemo(() => enrichImages(images), [images]);
  const maxWidth = useMemo(() => Math.max(1, ...enriched.map((i) => i.naturalWidth)), [enriched]);
  const maxHeight = useMemo(() => Math.max(1, ...enriched.map((i) => i.naturalHeight)), [enriched]);
  const formats = useMemo(() => collectFormats(enriched), [enriched]);

  const filteredImages = useMemo(() => {
    const filtered = enriched.filter((img) => {
      if (img.naturalWidth < minWidth || img.naturalHeight < minHeight) {
        return false;
      }
      if (enabledFormats && !enabledFormats.has(img.ext)) {
        return false;
      }
      return true;
    });
    return sortImages(filtered, sortField, sortDirection);
  }, [enriched, minWidth, minHeight, enabledFormats, sortField, sortDirection]);

  const selectedImages = useMemo(
    () => filteredImages.filter((img) => selectedSrcs.has(img.src)),
    [filteredImages, selectedSrcs],
  );
  const hasSelection = selectedImages.length > 0;

  useEffect(() => {
    setSelectedSrcs((current) => {
      const visible = new Set(filteredImages.map((i) => i.src));
      const next = new Set([...current].filter((src) => visible.has(src)));
      return next.size === current.size ? current : next;
    });
  }, [filteredImages]);

  function toggleImage(src: string) {
    setSelectedSrcs((current) => {
      const next = new Set(current);
      if (next.has(src)) {
        next.delete(src);
      } else {
        next.add(src);
      }
      return next;
    });
  }

  function selectAll() {
    setSelectedSrcs(new Set(filteredImages.map((i) => i.src)));
  }

  function invertSelection() {
    setSelectedSrcs(new Set(filteredImages.filter((i) => !selectedSrcs.has(i.src)).map((i) => i.src)));
  }

  function clearSelection() {
    setSelectedSrcs(new Set());
  }

  function toggleFormat(format: string) {
    setEnabledFormats((current) => {
      const allFormats = new Set(formats.map((f) => f.format));
      const base = current ?? allFormats;
      const next = new Set(base);
      if (next.has(format)) {
        next.delete(format);
      } else {
        next.add(format);
      }
      return next.size === allFormats.size ? null : next;
    });
  }

  async function sendSelected() {
    if (!selectedImages.length) {
      return;
    }
    const ok = await onSendImages(selectedImages);
    if (ok) {
      setSelectedSrcs(new Set());
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <Button
          appearance="subtle"
          disabled={isScanning}
          icon={<ArrowSyncRegular />}
          size="small"
          onClick={() => void scan()}
        >
          {isScanning ? "扫描中…" : "重新扫描"}
        </Button>
        <div className={styles.toolbarSpacer} />
        <Select
          className={styles.sortSelect}
          size="small"
          value={sortField}
          onChange={(_e, data) => setSortField(data.value as SortField)}
        >
          <option value="area">面积</option>
          <option value="width">宽度</option>
          <option value="height">高度</option>
        </Select>
        <Button
          appearance="subtle"
          icon={sortDirection === "desc" ? <ArrowSortDownRegular /> : <ArrowSortUpRegular />}
          size="small"
          onClick={() => setSortDirection((d) => d === "desc" ? "asc" : "desc")}
        />
        <Button
          appearance={isFilterOpen ? "primary" : "subtle"}
          icon={<FilterRegular />}
          size="small"
          onClick={() => setIsFilterOpen(!isFilterOpen)}
        />
        <Badge appearance="outline" color="informative" size="small">
          {`${filteredImages.length} 项`}
        </Badge>
      </div>

      {isFilterOpen && (
        <Card appearance="filled-alternative" className={styles.filterPanel}>
          <div className={styles.sliderRow}>
            <Caption1 className={styles.sliderLabel}>宽</Caption1>
            <Slider
              className={styles.slider}
              max={maxWidth}
              min={0}
              size="small"
              value={minWidth}
              onChange={(_e, data) => setMinWidth(data.value)}
            />
            <Caption1 className={styles.sliderValue}>{`≥ ${minWidth}px`}</Caption1>
          </div>
          <div className={styles.sliderRow}>
            <Caption1 className={styles.sliderLabel}>高</Caption1>
            <Slider
              className={styles.slider}
              max={maxHeight}
              min={0}
              size="small"
              value={minHeight}
              onChange={(_e, data) => setMinHeight(data.value)}
            />
            <Caption1 className={styles.sliderValue}>{`≥ ${minHeight}px`}</Caption1>
          </div>
          <div className={styles.formatChips}>
            {formats.map(({ format, count }) => {
              const active = !enabledFormats || enabledFormats.has(format);
              return (
                <Badge
                  key={format}
                  appearance={active ? "filled" : "outline"}
                  className={styles.formatChip}
                  color={active ? "brand" : "informative"}
                  size="medium"
                  onClick={() => toggleFormat(format)}
                >
                  {`${format} ${count}`}
                </Badge>
              );
            })}
          </div>
        </Card>
      )}

      {!hasScanned || isScanning ? null : filteredImages.length === 0 ? (
        <EmptyState
          icon={<ImageRegular />}
          title="当前页面没有找到图片"
          description="试试切换到有图片的页面，或调整筛选条件。"
        />
      ) : (
        <div className={styles.grid}>
          {filteredImages.map((image) => (
            <ImageCard
              key={image.src}
              image={image}
              ext={image.ext}
              selected={selectedSrcs.has(image.src)}
              onSelectedChange={() => toggleImage(image.src)}
            />
          ))}
        </div>
      )}

      {hasSelection && (
        <div className={styles.actionBar}>
          <Button appearance="subtle" icon={<CheckboxCheckedRegular />} size="small" onClick={selectAll}>全选</Button>
          <Button appearance="subtle" icon={<CheckboxIndeterminateRegular />} size="small" onClick={invertSelection}>反选</Button>
          <Button appearance="subtle" icon={<DismissRegular />} size="small" onClick={clearSelection}>取消</Button>
          <div className={styles.actionSpacer} />
          <Button
            appearance="primary"
            disabled={!connected}
            icon={<ArrowDownloadRegular />}
            size="small"
            onClick={() => void sendSelected()}
          >
            {`发送 (${selectedImages.length})`}
          </Button>
        </div>
      )}
    </div>
  );
}
