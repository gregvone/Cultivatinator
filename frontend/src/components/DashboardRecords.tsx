import { useState } from "react";
import { Link } from "react-router-dom";
import type { ActivityItem, AttentionItem } from "../api";
import { dashboardCommand, localZone } from "../dashboardApi";

export function ActivityList({ items }: { items: ActivityItem[] }) {
  return (
    <ul className="record-list">
      {items.map((item) => (
        <li key={item.event_id}>
          <time dateTime={item.occurred_at}>
            {new Date(item.occurred_at).toLocaleString()}
          </time>
          <Link to={item.target}>{item.title}</Link>{" "}
          <small>
            {item.record_id}
            {item.archived ? " · Archived record" : ""}
          </small>
          <span className="badge">{item.event_type.replaceAll("_", " ")}</span>
          <p>{item.description}</p>
        </li>
      ))}
    </ul>
  );
}

export function AttentionList({
  items,
  onChange,
  hidden = false,
}: {
  items: AttentionItem[];
  onChange: () => void;
  hidden?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [undo, setUndo] = useState<AttentionItem | null>(null);
  const [notice, setNotice] = useState("");
  async function act(
    item: AttentionItem,
    action: "dismiss" | "snooze" | "restore",
    days = 1,
  ) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await dashboardCommand("attention", {
        alert_id: item.alert_id,
        fingerprint: item.fingerprint,
        action,
        days,
        timezone: localZone(),
      });
      setUndo(action === "restore" ? null : item);
      setNotice(
        action === "restore"
          ? "Alert restored."
          : action === "dismiss"
            ? "Alert dismissed until its lifecycle changes."
            : `Alert snoozed for ${days} day${days === 1 ? "" : "s"}.`,
      );
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {error && <p role="alert">{error}</p>}
      {notice && (
        <div role="status">
          {notice}
          {undo && (
            <button disabled={busy} onClick={() => act(undo, "restore")}>
              Undo
            </button>
          )}
        </div>
      )}
      <ul className="record-list">
        {items.map((item) => (
          <li key={item.alert_id}>
            <span className={`badge ${item.severity}`}>
              {item.category} · {item.severity}
            </span>
            <Link to={item.target}>{item.title}</Link>
            <small>Permanent record: {item.record_id}</small>
            <p>{item.description}</p>
            {item.recorded_date && (
              <p className="attention-date">
                Recorded date:{" "}
                <time dateTime={item.recorded_date}>{item.recorded_date}</time>
                {item.elapsed_days !== null &&
                  ` · ${item.elapsed_days} elapsed days`}
              </p>
            )}
            {hidden && item.suppression && (
              <p>
                {item.suppression.action === "dismiss"
                  ? "Dismissed until a relevant lifecycle change"
                  : `Snoozed until ${new Date(item.suppression.until!).toLocaleString()}`}
              </p>
            )}
            <div
              className="actions"
              role="group"
              aria-label={`Alert actions for ${item.record_id}: ${item.rule}`}
            >
              {hidden ? (
                <button disabled={busy} onClick={() => act(item, "restore")}>
                  Restore alert
                </button>
              ) : (
                <>
                  {[1, 3, 7].map((days) => (
                    <button
                      key={days}
                      disabled={busy}
                      onClick={() => act(item, "snooze", days)}
                    >
                      Snooze {days} {days === 1 ? "day" : "days"}
                    </button>
                  ))}
                  <button disabled={busy} onClick={() => act(item, "dismiss")}>
                    Dismiss
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
