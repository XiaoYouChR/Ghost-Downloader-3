import {
    Body1Strong,
    Button,
    Card,
    Divider,
    Field,
    makeStyles,
    MessageBar,
    MessageBarBody,
    Select,
    Slider,
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
import {useEffect, useState} from "react";

import {PLAYBACK_RATE_OPTIONS} from "../../shared/constants";
import type {MediaAction, MediaItemOption, MediaPlaybackState} from "../../shared/types";
import {formatDuration} from "../../shared/utils";

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
  if (playbackState.isAvailable) {
    return chrome.i18n.getMessage("mediaConnected");
  }
  return chrome.i18n.getMessage("noMediaDetected");
}

export function MediaControlPanel({
  mediaItems,
  playbackState,
  onChangeMedia,
  onAction,
}: {
  mediaItems: MediaItemOption[];
  playbackState: MediaPlaybackState;
  onChangeMedia: (index: number) => void;
  onAction: (action: MediaAction, value?: number | boolean) => void;
}) {
  const styles = useStyles();
  const [seekDraft, setSeekDraft] = useState(playbackState.progress);
  const [isSeeking, setIsSeeking] = useState(false);
  const [volumeDraft, setVolumeDraft] = useState<number | null>(null);

  const actualVolume = Math.round((playbackState.isMuted ? 0 : playbackState.volume) * 100);
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

  const messageIntent = playbackState.isAvailable ? "success" : "info";

  return (
    <section className={styles.root}>
      <Body1Strong>{chrome.i18n.getMessage("mediaControl")}</Body1Strong>

      <Card appearance="filled-alternative" className={styles.card}>
        <Field className={styles.selectField} label={chrome.i18n.getMessage("selectMedia")}>
          <Select
            className={styles.selectControl}
            disabled={mediaItems.length === 0}
            value={playbackState.mediaIndex >= 0 ? String(playbackState.mediaIndex) : ""}
            onChange={(_event, data) => onChangeMedia(Number(data.value))}
          >
            <option value="">{chrome.i18n.getMessage("selectMediaPlaceholder")}</option>
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
            disabled={!playbackState.isAvailable}
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
            <span>{formatDuration(displayCurrentTime)}</span>
            <span>{formatDuration(playbackState.duration)}</span>
          </div>
        </div>

        <div className={styles.actionRow}>
          <Button
            appearance="primary"
            disabled={!playbackState.isAvailable}
            icon={playbackState.isPaused ? <PlayRegular /> : <PauseRegular />}
            onClick={() => onAction("toggle_play")}
          >
            {playbackState.isPaused ? chrome.i18n.getMessage("play") : "暂停"}
          </Button>

          <div className={styles.inlineActions}>
            <Select
              disabled={!playbackState.isAvailable}
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
              disabled={!playbackState.isAvailable}
              icon={<FullScreenMaximizeRegular />}
              aria-label={chrome.i18n.getMessage("fullscreen")}
              onClick={() => onAction("fullscreen")}
            />
            <Button
              appearance="secondary"
              disabled={!playbackState.isAvailable}
              icon={<PictureInPictureRegular />}
              aria-label={chrome.i18n.getMessage("pictureInPicture")}
              onClick={() => onAction("pip")}
            />
            <Button
              appearance="secondary"
              disabled={!playbackState.isAvailable}
              icon={<CameraRegular />}
              aria-label={chrome.i18n.getMessage("screenshot")}
              onClick={() => onAction("screenshot")}
            />
          </div>
        </div>

        <Divider />

        <div className={styles.footerRow}>
          <Button
            appearance={playbackState.shouldLoop ? "primary" : "secondary"}
            disabled={!playbackState.isAvailable}
            icon={<ArrowClockwiseRegular />}
            onClick={() => onAction("toggle_loop", !playbackState.shouldLoop)}
          >
            {chrome.i18n.getMessage("loop")}
          </Button>

          <div className={styles.volumeRow}>
            <Button
              appearance="secondary"
              disabled={!playbackState.isAvailable}
              icon={displayMuted ? <SpeakerMuteRegular /> : <Speaker2Regular />}
              aria-label={displayMuted ? chrome.i18n.getMessage("unmute") : chrome.i18n.getMessage("mute")}
              onClick={() => onAction("toggle_muted", !displayMuted)}
            />
            <div className={styles.volumeSlider}>
              <Slider
                className={styles.volumeSliderControl}
                disabled={!playbackState.isAvailable}
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
