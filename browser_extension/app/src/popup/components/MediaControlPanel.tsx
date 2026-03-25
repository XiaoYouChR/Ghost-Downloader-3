import {
  Body1Strong,
  Button,
  Card,
  Divider,
  Field,
  MessageBar,
  MessageBarBody,
  Select,
  Slider,
  makeStyles,
} from "@fluentui/react-components";
import {
  ArrowClockwiseRegular,
  CameraRegular,
  FullScreenMaximizeRegular,
  PauseRegular,
  PictureInPictureRegular,
  PlayRegular,
  Speaker2Regular,
  SpeakerMuteRegular,
} from "@fluentui/react-icons";
import { useEffect, useState } from "react";

import { PLAYBACK_RATE_OPTIONS } from "../../shared/constants";
import type { MediaItemOption, MediaPlaybackState, MediaTabOption } from "../../shared/types";
import { formatShortTime } from "../../shared/utils";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  card: {
    gap: "16px",
    padding: "16px",
  },
  selectField: {
    width: "100%",
    minWidth: 0,
  },
  selectControl: {
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  sliderBlock: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  sliderMeta: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    fontSize: "12px",
  },
  actionRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "12px",
  },
  inlineActions: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  footerRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    width: "100%",
  },
  volumeRow: {
    display: "flex",
    flex: 1,
    minWidth: 0,
    alignItems: "center",
    gap: "8px",
  },
  volumeSlider: {
    flex: 1,
    minWidth: 0,
  },
  volumeSliderControl: {
    width: "100%",
  },
  volumeValue: {
    width: "40px",
    textAlign: "right",
    fontSize: "12px",
  },
});

function panelMessage(playbackState: MediaPlaybackState) {
  if (playbackState.message) {
    return playbackState.message;
  }
  if (playbackState.available) {
    return playbackState.stale ? "当前显示的是上一次读取到的媒体状态" : "当前媒体状态已连接";
  }
  return "当前未检测到可控制媒体";
}

export function MediaControlPanel({
  mediaTabs,
  mediaItems,
  selectedTabId,
  selectedIndex,
  playbackState,
  busy,
  onChangeTab,
  onChangeMedia,
  onAction,
}: {
  mediaTabs: MediaTabOption[];
  mediaItems: MediaItemOption[];
  selectedTabId: number | null;
  selectedIndex: number;
  playbackState: MediaPlaybackState;
  busy?: boolean;
  onChangeTab: (tabId: number) => void;
  onChangeMedia: (index: number) => void;
  onAction: (action: string, value?: number | boolean) => void;
}) {
  const styles = useStyles();
  const [seekDraft, setSeekDraft] = useState(playbackState.progress);
  const [isSeeking, setIsSeeking] = useState(false);
  const [volumeDraft, setVolumeDraft] = useState<number | null>(null);

  const actualVolume = Math.round((playbackState.muted ? 0 : playbackState.volume) * 100);
  const displayProgress = isSeeking ? seekDraft : playbackState.progress;
  const displayCurrentTime =
    isSeeking && playbackState.duration > 0
      ? (Math.max(0, Math.min(100, displayProgress)) / 100) * playbackState.duration
      : playbackState.currentTime;
  const displayVolume = volumeDraft ?? actualVolume;
  const displayMuted = displayVolume <= 0;

  useEffect(() => {
    if (!isSeeking) {
      setSeekDraft(playbackState.progress);
    }
  }, [isSeeking, playbackState.progress]);

  useEffect(() => {
    if (volumeDraft === null || volumeDraft === actualVolume) {
      setVolumeDraft(null);
    }
  }, [actualVolume, volumeDraft]);

  function commitSeek() {
    if (!isSeeking) {
      return;
    }
    setIsSeeking(false);
    onAction("set_time", seekDraft);
  }

  function commitVolume() {
    if (volumeDraft === null) {
      return;
    }
    onAction("set_volume", volumeDraft / 100);
  }

  const messageIntent =
    playbackState.available && !playbackState.stale
      ? "success"
      : playbackState.available
        ? "warning"
        : "info";

  return (
    <section className={styles.root}>
      <Body1Strong>媒体控制</Body1Strong>

      <Card appearance="filled-alternative" className={styles.card}>
        <Field className={styles.selectField} label="选择页面">
          <Select
            className={styles.selectControl}
            disabled={busy || mediaTabs.length === 0}
            value={selectedTabId !== null ? String(selectedTabId) : ""}
            onChange={(_event, data) => onChangeTab(Number(data.value))}
          >
            <option value="">请选择页面</option>
            {mediaTabs.map((item) => (
              <option key={item.tabId} value={String(item.tabId)}>
                {item.domain ? `${item.title} · ${item.domain}` : item.title}
              </option>
            ))}
          </Select>
        </Field>

        <Field className={styles.selectField} label="选择媒体">
          <Select
            className={styles.selectControl}
            disabled={busy || mediaItems.length === 0}
            value={selectedIndex >= 0 ? String(selectedIndex) : ""}
            onChange={(_event, data) => onChangeMedia(Number(data.value))}
          >
            <option value="">请选择媒体</option>
            {mediaItems.map((item) => (
              <option key={item.index} value={String(item.index)}>
                {item.label}
              </option>
            ))}
          </Select>
        </Field>

        <MessageBar intent={messageIntent}>
          <MessageBarBody>{panelMessage(playbackState)}</MessageBarBody>
        </MessageBar>

        <div className={styles.sliderBlock}>
          <Slider
            disabled={busy || !playbackState.available}
            max={100}
            min={0}
            value={displayProgress}
            onBlur={() => commitSeek()}
            onChange={(_event, data) => {
              setIsSeeking(true);
              setSeekDraft(data.value);
            }}
            onKeyUp={() => commitSeek()}
            onMouseUp={() => commitSeek()}
            onTouchEnd={() => commitSeek()}
          />
          <div className={styles.sliderMeta}>
            <span>{formatShortTime(displayCurrentTime)}</span>
            <span>{formatShortTime(playbackState.duration)}</span>
          </div>
        </div>

        <div className={styles.actionRow}>
          <Button
            appearance="primary"
            disabled={busy || !playbackState.available}
            icon={playbackState.paused ? <PlayRegular /> : <PauseRegular />}
            onClick={() => onAction("toggle_play")}
          >
            {playbackState.paused ? "播放" : "暂停"}
          </Button>

          <div className={styles.inlineActions}>
            <Select
              disabled={busy || !playbackState.available}
              value={String(playbackState.speed)}
              onChange={(_event, data) => onAction("set_speed", Number(data.value))}
            >
              {PLAYBACK_RATE_OPTIONS.map((rate) => (
                <option key={rate} value={String(rate)}>
                  {`${rate}x`}
                </option>
              ))}
            </Select>
            <Button
              appearance="secondary"
              disabled={busy || !playbackState.available}
              icon={<FullScreenMaximizeRegular />}
              aria-label="全屏"
              onClick={() => onAction("fullscreen")}
            />
            <Button
              appearance="secondary"
              disabled={busy || !playbackState.available}
              icon={<PictureInPictureRegular />}
              aria-label="画中画"
              onClick={() => onAction("pip")}
            />
            <Button
              appearance="secondary"
              disabled={busy || !playbackState.available}
              icon={<CameraRegular />}
              aria-label="截图"
              onClick={() => onAction("screenshot")}
            />
          </div>
        </div>

        <Divider />

        <div className={styles.footerRow}>
          <Button
            appearance={playbackState.loop ? "primary" : "secondary"}
            disabled={busy || !playbackState.available}
            icon={<ArrowClockwiseRegular />}
            onClick={() => onAction("toggle_loop", !playbackState.loop)}
          >
            循环
          </Button>

          <div className={styles.volumeRow}>
            <Button
              appearance="secondary"
              disabled={busy || !playbackState.available}
              icon={displayMuted ? <SpeakerMuteRegular /> : <Speaker2Regular />}
              aria-label={displayMuted ? "取消静音" : "静音"}
              onClick={() => onAction("toggle_muted", !displayMuted)}
            />
            <div className={styles.volumeSlider}>
              <Slider
                className={styles.volumeSliderControl}
                disabled={busy || !playbackState.available}
                max={100}
                min={0}
                value={displayVolume}
                onBlur={() => commitVolume()}
                onChange={(_event, data) => setVolumeDraft(data.value)}
                onKeyUp={() => commitVolume()}
                onMouseUp={() => commitVolume()}
                onTouchEnd={() => commitVolume()}
              />
            </div>
            <span className={styles.volumeValue}>{`${displayVolume}%`}</span>
          </div>
        </div>
      </Card>
    </section>
  );
}
