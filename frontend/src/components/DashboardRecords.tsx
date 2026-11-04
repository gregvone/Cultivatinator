import { Link } from "react-router-dom";
import type { ActivityItem, AttentionItem } from "../api";

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

export function AttentionList({ items }: { items: AttentionItem[] }) {
  return (
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
              <time dateTime={item.recorded_date}>{item.rule === "environment" ? new Date(item.recorded_date).toLocaleString() : item.recorded_date}</time>
              {item.elapsed_days !== null &&
                ` · ${item.elapsed_days} elapsed days`}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
