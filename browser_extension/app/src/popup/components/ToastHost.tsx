import {makeStyles, MessageBar, MessageBarBody} from "@fluentui/react-components";

export type ToastIntent = "info" | "success" | "error";

const useStyles = makeStyles({
  root: {
    pointerEvents: "none",
    position: "absolute",
    right: 0,
    bottom: "20px",
    left: 0,
    zIndex: 20,
    width: "380px",
    maxWidth: "calc(100% - 24px)",
    margin: "0 auto",
  },
  bar: {
    pointerEvents: "auto",
  },
});

export function ToastHost({
  message,
  intent,
}: {
  message: string;
  intent: ToastIntent;
}) {
  const styles = useStyles();
  if (!message) {
    return null;
  }

  return (
    <div className={styles.root}>
      <MessageBar className={styles.bar} intent={intent}>
        <MessageBarBody>{message}</MessageBarBody>
      </MessageBar>
    </div>
  );
}
