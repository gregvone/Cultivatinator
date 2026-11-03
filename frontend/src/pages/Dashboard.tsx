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
  Thermometer,
  ArrowUpRight,
} from "lucide-react";
import type { DashboardSummary } from "../api";
import { useApi } from "../useApi";
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
  },
  {
    key: "spawn_containers",
    label: "Spawn Containers",
    detail: "Active registered spawn jars and bags",
    icon: Container,
  },
  {
    key: "fruiting_units",
    label: "Fruiting Units",
    detail: "Active registered fruiting containers",
    icon: Sprout,
  },
  {
    key: "open_alerts",
    label: "Open Alerts",
    detail: "Items requiring your attention",
    icon: TriangleAlert,
  },
] as const;

export default function Dashboard() {
  const { data, error, retry } = useApi<DashboardSummary>("dashboard/summary");
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
            {cards.map(({ key, label, detail, icon: Icon }, index) => (
              <section className="summary-card" key={key}>
                <div className="summary-top">
                  <span>{label}</span>
                  <Icon size={20} aria-hidden="true" />
                </div>
                <strong data-testid={key}>{data.counts[key]}</strong>
                <p>{detail}</p>
                <span className="card-index">0{index + 1}</span>
              </section>
            ))}
          </div>
          <QuickCreateSection />
          <div className="dashboard-grid">
            <CollapsiblePanel
              title="Needs Attention"
              defaultOpen
              className="attention-panel"
            >
              {data.attention_items.length ? (
                <ul className="record-list">
                  {data.attention_items.map((item) => (
                    <li key={item.record_id}>
                      <span className={`badge ${item.severity}`}>
                        {item.severity}
                      </span>
                      <Link to={item.target}>{item.title}</Link>
                      <p>{item.description}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={CircleCheck}
                  title="No items currently require attention."
                  description="Items that need a closer look will be collected here."
                />
              )}
            </CollapsiblePanel>
            <CollapsiblePanel
              title="Growing Conditions"
              summary="Environmental observations"
            >
              {data.environmental_observations.length ? (
                <ul className="record-list">
                  {data.environmental_observations.map((item) => (
                    <li key={item.record_id}>
                      {item.area}
                      <p>
                        {item.temperature_c ?? "—"} °C ·{" "}
                        {item.humidity_percent ?? "—"}% RH
                      </p>
                      <time>{new Date(item.observed_at).toLocaleString()}</time>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={Thermometer}
                  title="No environmental observations available."
                  description="Temperature, humidity, and growing-area observations will appear here."
                />
              )}
            </CollapsiblePanel>
            <CollapsiblePanel
              title="Active Cultivation"
              defaultOpen
              className="cultivation-panel"
            >
              {data.active_cultivation.length ? (
                <ul className="record-list">
                  {data.active_cultivation.map((item) => (
                    <li key={item.record_id}>
                      <Link to={item.target}>{item.title}</Link>
                      <small>{item.record_id}</small>
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
              <div className="panel-footer">
                <span>From culture to harvest</span>
                <Link to="/cultivation">
                  Explore cultivation <ArrowUpRight size={14} />
                </Link>
              </div>
            </CollapsiblePanel>
            <CollapsiblePanel
              title="Recent Activity"
              summary="Workspace activity log"
            >
              {data.recent_activity.length ? (
                <ul className="record-list">
                  {data.recent_activity.map((item) => (
                    <li key={`${item.record_id}-${item.occurred_at}`}>
                      <time>{new Date(item.occurred_at).toLocaleString()}</time>
                      <Link to={item.target}>{item.title}</Link>
                      <p>{item.description}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={Activity}
                  title="No activity recorded yet."
                  description="Culture Library changes are recorded in each record’s activity history."
                />
              )}
            </CollapsiblePanel>
          </div>
        </>
      )}
    </>
  );
}
