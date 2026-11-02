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
  Panel,
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
    detail: "Jars and bags in production",
    icon: Container,
  },
  {
    key: "fruiting_units",
    label: "Fruiting Units",
    detail: "Units in the growing cycle",
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
          <div className="dashboard-grid">
            <Panel
              title="Needs Attention"
              icon={TriangleAlert}
              label="PRIORITIES"
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
            </Panel>
            <Panel
              title="Growing Conditions"
              icon={Thermometer}
              label="ENVIRONMENT"
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
            </Panel>
            <Panel
              title="Active Cultivation"
              icon={Sprout}
              label="GROWING CYCLES"
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
                  description="Growing cycles will appear here when cultivation workflows are implemented."
                />
              )}
              <div className="panel-footer">
                <span>From culture to harvest</span>
                <Link to="/cultivation">
                  Explore cultivation <ArrowUpRight size={14} />
                </Link>
              </div>
            </Panel>
            <Panel title="Recent Activity" icon={Activity} label="ACTIVITY LOG">
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
            </Panel>
          </div>
          <p className="foundation-note">
            <span className="status-dot" />
            Registered quantities are starting measurements. Transfers and
            automatic inventory accounting come in a later milestone.
          </p>
        </>
      )}
    </>
  );
}
