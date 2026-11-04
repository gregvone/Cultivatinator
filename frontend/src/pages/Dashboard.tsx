import { useEffect, useRef } from "react";
import CollapsiblePanel from "../components/CollapsiblePanel";
import { QuickCreateSection } from "./QuickCreate";
import { Link } from "react-router-dom";
import {
  Dna,
  Container,
  Sprout,
  TriangleAlert,
  CircleCheck,
  Activity,
} from "lucide-react";
import type { DashboardSummary } from "../api";
import { useApi } from "../useApi";
import { zoneQuery, stageName } from "../dashboardApi";
import { AttentionList, ActivityList } from "../components/DashboardRecords";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from "../components/UI";

const cards = [
  {
    key: "active_cultures",
    label: "Active Cultures",
    detail: "Active registered physical culture containers",
    icon: Dna,
    target: "/laboratory?filter=active",
  },
  {
    key: "spawn_containers",
    label: "Spawn Containers",
    detail: "Active registered spawn jars and bags",
    icon: Container,
    target: "/cultivation?view=spawn&filter=active",
  },
  {
    key: "fruiting_units",
    label: "Fruiting Units",
    detail: "Active registered fruiting containers",
    icon: Sprout,
    target: "/cultivation?view=fruiting&fruiting=active",
  },
  {
    key: "open_alerts",
    label: "Open Alerts",
    detail: "Current reminders and recorded next actions",
    icon: TriangleAlert,
    target: "#needs-attention",
  },
] as const;

export default function Dashboard() {
  const { data, error, retry } = useApi<DashboardSummary>(
    `dashboard/summary?${zoneQuery()}`,
    true,
  );
  const attention = useRef<HTMLElement>(null);
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "hidden") retry();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [retry]);
  function focusAttention() {
    const details = attention.current?.querySelector("details");
    if (details) details.open = true;
    attention.current?.focus();
  }
  return (
    <>
      <PageHeader
        title="Cultivation Command Center"
        description="Your cultures, growing cycles, and next steps at a glance."
      />
      {error ? (
        <ErrorState error={error} retry={retry} />
      ) : !data ? (
        <LoadingState />
      ) : (
        <>
          <div className="summary-grid">
            {cards.map(({ key, label, detail, icon: Icon, target }, index) => {
              const content = (
                <>
                  <div className="summary-top">
                    <span>{label}</span>
                    <Icon size={20} aria-hidden="true" />
                  </div>
                  <strong data-testid={key}>{data.counts[key]}</strong>
                  <p>{detail}</p>
                  <span className="card-index">0{index + 1}</span>
                </>
              );
              return key === "open_alerts" ? (
                <a
                  key={key}
                  href={target}
                  className="summary-card"
                  onClick={focusAttention}
                >
                  {content}
                </a>
              ) : (
                <Link key={key} to={target} className="summary-card">
                  {content}
                </Link>
              );
            })}
          </div>
          <QuickCreateSection />
          <div className="dashboard-grid">
            <section
              id="needs-attention"
              ref={attention}
              tabIndex={-1}
              aria-label="Needs Attention"
            >
              <CollapsiblePanel
                title="Needs Attention"
                defaultOpen
                className="attention-panel"
                summary={`${data.counts.open_alerts} open alerts`}
              >
                <AttentionList items={data.attention_items} />
                {!data.attention_items.length && (
                  <EmptyState
                    icon={CircleCheck}
                    title="No items currently require attention."
                    description="Alerts appear while their recorded conditions apply and disappear when resolved."
                  />
                )}
                <div className="panel-footer">
                  <Link to="/attention">
                    View all attention items ({data.counts.open_alerts})
                  </Link>
                </div>
                {data.counts.open_alerts > data.attention_items.length && (
                  <p>
                    Showing the first {data.attention_items.length} open alerts.
                  </p>
                )}
              </CollapsiblePanel>
            </section>
            <CollapsiblePanel
              title="Cultivation Stages"
              summary="Recorded stages only"
              defaultOpen
            >
              <p>
                Colonizing laboratory agar is shown as Germinating on its
                record. Records without a stage are not included here.
              </p>
              <ul className="stage-grid">
                {(data.stage_overview || []).map((item) => (
                  <li key={`${item.group}-${item.stage}`}>
                    <Link to={item.target}>
                      <span>
                        {item.label} · {stageName(item.stage)}
                      </span>
                      <strong>{item.count}</strong>
                    </Link>
                  </li>
                ))}
              </ul>
            </CollapsiblePanel>
            <CollapsiblePanel
              title="Active Cultivation"
              defaultOpen
              className="cultivation-panel"
              summary="Ready first, then newest registered"
            >
              {data.active_cultivation.length ? (
                <ul className="record-list">
                  {data.active_cultivation.map((item) => (
                    <li key={item.record_id}>
                      <Link to={item.target}>{item.title}</Link>
                      <small>
                        {item.record_id} ·{" "}
                        {item.stage === "colonizing" &&
                        item.record_id.startsWith("AG")
                          ? "Germinating"
                          : !item.stage && item.record_id.startsWith("AG")
                            ? "Readiness not recorded"
                            : stageName(item.stage)}
                      </small>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={Sprout}
                  title="No active cultivation records."
                  description="Open Cultivation to follow spawn, fruiting stages, flushes and harvests."
                />
              )}
              {(data.active_total || 0) > data.active_cultivation.length && (
                <p>
                  Showing {data.active_cultivation.length} of{" "}
                  {data.active_total} active records.
                </p>
              )}
              <div className="panel-footer">
                <Link to="/laboratory">Explore laboratory</Link>
                <Link to="/cultivation">Explore cultivation</Link>
              </div>
            </CollapsiblePanel>
            <CollapsiblePanel
              title="Recent Harvests"
              summary="Trailing 30 calendar days"
              defaultOpen
            >
              {data.harvest_summary && (
                <>
                  <p>
                    <time>{data.harvest_summary.start_date}</time> through{" "}
                    <time>{data.harvest_summary.end_date}</time>, inclusive ·{" "}
                    {data.harvest_summary.timezone}. Today and the preceding 29
                    days; future harvests excluded.
                  </p>
                  <dl className="info-list">
                    <div>
                      <dt>Recorded harvests</dt>
                      <dd>{data.harvest_summary.harvest_count}</dd>
                    </div>
                    <div>
                      <dt>Known wet weight</dt>
                      <dd>
                        {data.harvest_summary.wet_grams === null
                          ? "Not measured"
                          : `${Number(data.harvest_summary.wet_grams).toLocaleString(undefined, { maximumFractionDigits: 3 })} g`}
                      </dd>
                    </div>
                    <div>
                      <dt>Measured coverage</dt>
                      <dd>
                        {data.harvest_summary.wet_weight_count} of{" "}
                        {data.harvest_summary.harvest_count} harvests have wet
                        weights; missing measurements are unknown.
                      </dd>
                    </div>
                    <div>
                      <dt>Fruiting containers harvested</dt>
                      <dd>{data.harvest_summary.fruiting_count}</dd>
                    </div>
                  </dl>
                  {!data.harvest_summary.harvest_count && (
                    <p>No harvests recorded in this period.</p>
                  )}
                </>
              )}
              <Link to="/reports">View Reports</Link>
            </CollapsiblePanel>
            <CollapsiblePanel
              title="Recent Activity"
              summary="Latest 15 recorded events · local time"
            >
              {data.recent_activity.length ? (
                <ActivityList items={data.recent_activity} />
              ) : (
                <EmptyState
                  icon={Activity}
                  title="No activity recorded yet."
                  description="Culture Library changes are recorded in each record’s activity history."
                />
              )}
              <Link to="/activity">View All Activity</Link>
            </CollapsiblePanel>
          </div>
        </>
      )}
    </>
  );
}
