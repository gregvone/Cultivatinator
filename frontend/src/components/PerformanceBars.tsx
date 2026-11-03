import { useId } from "react";
import { measure } from "../reportApi";
export interface PerformanceBar {
  id: string;
  name: string;
  value: string | null;
  samples: number;
  detail: string;
  preliminary?: boolean;
}
export default function PerformanceBars({
  title,
  rows,
}: {
  title: string;
  rows: PerformanceBar[];
}) {
  const id = useId();
  const max = Math.max(0, ...rows.map((r) => Number(r.value || 0)));
  return (
    <figure className="performance-chart" aria-labelledby={id}>
      <figcaption id={id}>{title}</figcaption>
      {!rows.length ? (
        <p>Insufficient data for a measured comparison.</p>
      ) : (
        <ol>
          {rows.map((r) => (
            <li key={r.id}>
              <div className="bar-label">
                <strong>{r.name}</strong>
                <span>
                  {measure(r.value)} · n={r.samples}
                </span>
                {r.preliminary && (
                  <span className="badge warning">Preliminary</span>
                )}
              </div>
              <div className="bar-track" aria-hidden="true">
                <span
                  style={{
                    width: `${max > 0 ? (Number(r.value || 0) / max) * 100 : 0}%`,
                  }}
                />
              </div>
              <p>{r.detail}</p>
            </li>
          ))}
        </ol>
      )}
    </figure>
  );
}
