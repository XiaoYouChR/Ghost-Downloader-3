import {Body1Strong, Caption1, makeStyles} from "@fluentui/react-components";
import type {ReactNode} from "react";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    flex: 1,
    gap: "4px",
    padding: "24px 16px",
    textAlign: "center",
  },
  icon: {
    fontSize: "28px",
    lineHeight: "28px",
    marginBottom: "4px",
    color: "var(--colorNeutralForeground3)",
  },
  description: {
    color: "var(--colorNeutralForeground3)",
  },
  action: {
    marginTop: "4px",
  },
});

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  const styles = useStyles();

  return (
    <div className={styles.root}>
      <div className={styles.icon}>{icon}</div>
      <Body1Strong>{title}</Body1Strong>
      <Caption1 className={styles.description}>{description}</Caption1>
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
