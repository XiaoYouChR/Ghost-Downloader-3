import {Checkbox, makeStyles, mergeClasses, tokens} from "@fluentui/react-components";

import type {ScannedImage} from "../../shared/types";

const useStyles = makeStyles({
  root: {
    position: "relative",
    borderRadius: "6px",
    overflow: "hidden",
    cursor: "pointer",
    border: "2px solid transparent",
    "&:hover": {
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.12)",
    },
  },
  selected: {
    border: `2px solid ${tokens.colorBrandBackground}`,
  },
  thumbnail: {
    display: "block",
    width: "100%",
    aspectRatio: "1",
    objectFit: "cover",
    backgroundColor: "var(--colorNeutralBackground3)",
  },
  checkbox: {
    position: "absolute",
    top: "2px",
    right: "2px",
    backgroundColor: "rgba(255, 255, 255, 0.7)",
    borderRadius: "4px",
  },
  info: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: "2px 6px",
    backgroundColor: "rgba(0, 0, 0, 0.55)",
    color: "#fff",
    fontSize: "10px",
    lineHeight: "16px",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
});

export function ImageCard({
  image,
  ext,
  selected,
  onSelectedChange,
  onDimensionsLoaded,
}: {
  image: ScannedImage;
  ext: string;
  selected?: boolean;
  onSelectedChange?: (checked: boolean) => void;
  onDimensionsLoaded?: (src: string, w: number, h: number) => void;
}) {
  const styles = useStyles();
  const hasDimensions = image.naturalWidth > 0 && image.naturalHeight > 0;

  return (
    <div
      className={mergeClasses(styles.root, selected && styles.selected)}
      onClick={() => onSelectedChange?.(!selected)}
    >
      <img
        alt={image.alt}
        className={styles.thumbnail}
        loading="lazy"
        src={image.src}
        onLoad={hasDimensions ? undefined : (e) => {
          const el = e.currentTarget;
          if (el.naturalWidth > 0 && el.naturalHeight > 0) {
            onDimensionsLoaded?.(image.src, el.naturalWidth, el.naturalHeight);
          }
        }}
      />
      <Checkbox
        checked={selected}
        className={styles.checkbox}
        onChange={(e) => e.stopPropagation()}
      />
      <div className={styles.info}>
        {hasDimensions
          ? `${image.naturalWidth}×${image.naturalHeight} · ${ext}`
          : ext}
      </div>
    </div>
  );
}
