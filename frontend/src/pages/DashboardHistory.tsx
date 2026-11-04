import { useSearchParams, Link } from "react-router-dom";
import type { ActivityPage, AttentionPage } from "../api";
import { useApi } from "../useApi";
import { zoneQuery } from "../dashboardApi";
import { ActivityList, AttentionList } from "../components/DashboardRecords";
import { ErrorState, LoadingState, PageHeader } from "../components/UI";

function Pagination({
  page,
  total,
  size,
  change,
}: {
  page: number;
  total: number;
  size: number;
  change: (page: number) => void;
}) {
  return (
    <nav aria-label="Results pages" className="actions">
      <button disabled={page <= 1} onClick={() => change(page - 1)}>
        Previous page
      </button>
      <span>
        Page {page} of {Math.max(1, Math.ceil(total / size))} · {total} results
      </span>
      <button disabled={page * size >= total} onClick={() => change(page + 1)}>
        Next page
      </button>
    </nav>
  );
}
export default function DashboardHistory({
  attention = false,
}: {
  attention?: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const hidden = params.get("hidden") === "true";
  const kind = params.get("record_type") || "all";
  const { data, error, retry } = useApi<ActivityPage | AttentionPage>(
    attention
      ? `dashboard/attention?${zoneQuery()}&hidden=${hidden}&page=${page}`
      : `dashboard/activity?record_type=${encodeURIComponent(kind)}&page=${page}`,
    true,
  );
  function change(key: string, value: string) {
    setParams((p) => {
      const next = new URLSearchParams(p);
      next.set(key, value);
      if (key !== "page") next.delete("page");
      return next;
    });
  }
  return (
    <>
      <PageHeader
        title={
          attention
            ? hidden
              ? "Hidden Attention Items"
              : "Needs Attention"
            : "All Activity"
        }
        description={
          attention
            ? "Review current reminders and restore snoozed or dismissed alerts."
            : "Persisted activity, newest first. Times are displayed in your local timezone."
        }
      />
      <Link to="/">Back to Dashboard</Link>
      {attention ? (
        <div className="actions">
          <Link to={hidden ? "/attention" : "/attention?hidden=true"}>
            {hidden ? "Open attention items" : "Review hidden items"}
          </Link>
        </div>
      ) : (
        <label className="field">
          <span>Record type</span>
          <select
            value={kind}
            onChange={(e) => change("record_type", e.target.value)}
          >
            {Object.entries({
              all: "All records",
              physical: "Laboratory cultures",
              spawn: "Spawn",
              fruiting: "Fruiting containers",
              strains: "Strains",
              lines: "Culture lines",
              spores: "Spores",
              batches: "Grow batches",
            }).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      )}
      {error ? (
        <ErrorState error={error} retry={retry} />
      ) : !data ? (
        <LoadingState />
      ) : (
        <section className="panel">
          {attention ? (
            <AttentionList
              items={data.items as AttentionPage["items"]}
              onChange={retry}
              hidden={hidden}
            />
          ) : (
            <ActivityList items={data.items as ActivityPage["items"]} />
          )}
          {!data.items.length && (
            <p>
              {attention
                ? hidden
                  ? "No current hidden attention items."
                  : "No items currently require attention."
                : "No matching activity recorded."}
            </p>
          )}
          <Pagination
            page={page}
            total={data.total}
            size={data.page_size}
            change={(n) => change("page", String(n))}
          />
        </section>
      )}
    </>
  );
}
