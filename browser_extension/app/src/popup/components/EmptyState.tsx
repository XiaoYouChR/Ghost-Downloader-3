import { Avatar, Body1Strong, Card, Caption1, makeStyles } from "@fluentui/react-components";
import type { ReactNode } from "react";

const useStyles = makeStyles({
  root: {
    alignItems: "center",
    padding: "40px 24px",
    textAlign: "center",
  },
  action: {
    marginTop: "8px",
  },
});

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: JSX.Element;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  const styles = useStyles();

  return (
    <Card appearance="outline" className={styles.root}>
      <Avatar color="brand" icon={icon} size={56} />
      <Body1Strong>{title}</Body1Strong>
      <Caption1>{description}</Caption1>
      {action ? <div className={styles.action}>{action}</div> : null}
    </Card>
  );
}
