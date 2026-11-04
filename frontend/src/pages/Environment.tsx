import { cloneElement, useId, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode, ReactElement } from "react";
import { Link, useSearchParams } from "react-router-dom";
import CollapsiblePanel from "../components/CollapsiblePanel";
import { PageHeader } from "../components/UI";
import {
  environmentApi,
  metrics,
  useEnvironment,
  localDateTime,
  observationTime,
  friendlyTime,
} from "../environmentApi";
import type {
  Tent,
  Profile,
  Reading,
  Occupancy,
  Overview,
  Page,
  Metric,
} from "../environmentApi";

type Values = Record<string, string>;
function Field({
  label,
  children,
}: {
  label: string;
  children: ReactElement<{ id?: string }>;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {cloneElement(children, { id })}
    </div>
  );
}

function Load({
  state,
}: {
  state: { loading: boolean; error: string; retry: () => void };
}) {
  return (
    <>
      {state.loading && <p role="status">Loading environment records…</p>}
      {state.error && (
        <p role="alert">
          {state.error} <button onClick={state.retry}>Retry</button>
        </p>
      )}
    </>
  );
}
function Form({
  path,
  method = "POST",
  payload,
  onSaved,
  children,
}: {
  path: string;
  method?: string;
  payload: () => unknown;
  onSaved: () => void;
  children: ReactNode;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const attempt = useRef({ json: "", key: "" });
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const body = payload() as Record<string, unknown>;
      const json = JSON.stringify(body);
      if (attempt.current.json !== json)
        attempt.current = { json, key: crypto.randomUUID() };
      await environmentApi(path, method, {
        ...body,
        request_key: attempt.current.key,
      });
      attempt.current = { json: "", key: "" };
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="environment-form">
      <fieldset disabled={busy}>
        {children}
        {error && <p role="alert">{error}</p>}
        <button type="submit">{busy ? "Saving…" : "Save"}</button>
      </fieldset>
    </form>
  );
}
function Pager({
  page,
  total,
  size,
  onPage,
}: {
  page: number;
  total: number;
  size: number;
  onPage: (v: number) => void;
}) {
  return (
    <div className="actions">
      <button disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} · {total} records
      </span>
      <button disabled={page * size >= total} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </div>
  );
}
function Targets({ profile }: { profile: Profile | null }) {
  return (
    <ul>
      {metrics.map((m) => (
        <li key={m.key}>
          {m.label}: {profile?.targets[m.key + "_min"] ?? "No minimum"} –{" "}
          {profile?.targets[m.key + "_max"] ?? "No maximum"} {m.unit}
        </li>
      ))}
    </ul>
  );
}
function ProfileEditor({
  profile,
  onSaved,
}: {
  profile?: Profile;
  onSaved: () => void;
}) {
  const [v, setV] = useState<Values>({
    name: profile?.name ?? "",
    species: profile?.species ?? "",
    notes: profile?.notes ?? "",
    status: profile?.status ?? "active",
    ...Object.fromEntries(
      Object.entries(profile?.targets ?? {}).map(([k, val]) => [
        k,
        val == null ? "" : String(val),
      ]),
    ),
  });
  const input = (k: string) => ({
    value: v[k] ?? "",
    onChange: (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >,
    ) => setV({ ...v, [k]: e.target.value }),
  });
  return (
    <Form
      path={profile ? `profiles/${profile.id}` : "profiles"}
      method={profile ? "PUT" : "POST"}
      onSaved={onSaved}
      payload={() => ({
        name: v.name,
        species: v.species || null,
        notes: v.notes || null,
        status: v.status,
        ...(profile ? { expected_revision: profile.revision } : {}),
        targets: Object.fromEntries(
          metrics.flatMap((m) =>
            ["min", "max"].map((b) => {
              const k = m.key + "_" + b;
              return [k, v[k] ? Number(v[k]) : null];
            }),
          ),
        ),
      })}
    >
      <Field label="Profile name">
        <input required maxLength={200} {...input("name")} />
      </Field>
      <Field label="Species or descriptive label (optional)">
        <input {...input("species")} />
      </Field>
      <p>
        All targets are user defined. Blank bounds are unconfigured; no warning
        is evaluated without a target.
      </p>
      <div className="environment-grid">
        {metrics.flatMap((m) =>
          ["min", "max"].map((b) => (
            <Field
              key={m.key + b}
              label={`${m.label} ${b === "min" ? "minimum" : "maximum"} (${m.unit})`}
            >
              <input
                type="number"
                step="any"
                min={m.min}
                max={m.max}
                {...input(m.key + "_" + b)}
              />
            </Field>
          )),
        )}
      </div>
      <Field label="Profile notes">
        <textarea {...input("notes")} />
      </Field>
      <Field label="Profile status">
        <select {...input("status")}>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
      </Field>
    </Form>
  );
}
function TentEditor({ tent, onSaved }: { tent?: Tent; onSaved: () => void }) {
  const [name, setName] = useState(tent?.name ?? ""),
    [description, setDescription] = useState(tent?.description ?? ""),
    [status, setStatus] = useState(tent?.status ?? "active");
  return (
    <Form
      path={tent ? `tents/${tent.id}` : "tents"}
      method={tent ? "PUT" : "POST"}
      onSaved={onSaved}
      payload={() => ({
        name,
        description: description || null,
        status,
        ...(tent ? { expected_revision: tent.revision } : {}),
      })}
    >
      <Field label="Tent name">
        <input
          required
          placeholder="For example: Boom Room 2"
          maxLength={200}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field label="Tent description">
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <Field label="Tent status">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
      </Field>
      <p>Archiving preserves occupancy, readings and unresolved warnings.</p>
    </Form>
  );
}
function ReadingForm({
  tent,
  reading,
  onSaved,
}: {
  tent: Tent;
  reading?: Reading;
  onSaved: () => void;
}) {
  const [v, setV] = useState<Values>({
    observed_at: localDateTime(reading?.observed_at),
    temperature_f: reading ? String(reading.temperature_f) : "",
    humidity: reading ? String(reading.humidity) : "",
    co2: reading?.co2 == null ? "" : String(reading.co2),
    humidifier: reading?.humidifier == null ? "" : String(reading.humidifier),
    fan: reading?.fan == null ? "" : String(reading.fan),
    notes: reading?.notes ?? "",
    reason: "",
  });
  const field = (k: string) => ({
    value: v[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setV({ ...v, [k]: e.target.value }),
  });
  return (
    <Form
      path={`tents/${tent.id}/readings${reading ? `/${reading.id}/correct` : ""}`}
      onSaved={onSaved}
      payload={() => ({
        observed_at: observationTime(v.observed_at),
        temperature_f: Number(v.temperature_f),
        humidity: Number(v.humidity),
        co2: v.co2 ? Number(v.co2) : null,
        humidifier: v.humidifier ? Number(v.humidifier) : null,
        fan: v.fan ? Number(v.fan) : null,
        notes: v.notes || null,
        ...(reading ? { reason: v.reason } : {}),
      })}
    >
      <Field label="Observed at (local time)">
        <input
          type="datetime-local"
          step="0.001"
          required
          {...field("observed_at")}
        />
      </Field>
      <p>
        Local time: {Intl.DateTimeFormat().resolvedOptions().timeZone}. During a
        repeated daylight-saving hour, the browser chooses the earlier
        occurrence. The API accepts an explicit UTC offset.
      </p>
      <div className="environment-grid">
        {metrics.map((m) => (
          <Field
            key={m.key}
            label={`${m.label} (${m.unit})${m.key === "co2" ? " (optional)" : ""}`}
          >
            <input
              type="number"
              step="any"
              required={m.key !== "co2"}
              min={m.min}
              max={m.max}
              {...field(m.key)}
            />
          </Field>
        ))}
      </div>
      <Field label="Humidifier controller level (0–10, optional)">
        <input
          type="number"
          min={0}
          max={10}
          step={1}
          {...field("humidifier")}
        />
      </Field>
      <Field label="Exhaust fan controller level (0–10, optional)">
        <input type="number" min={0} max={10} step={1} {...field("fan")} />
      </Field>
      <p>
        Controller levels are manually entered settings, not device telemetry.
      </p>
      <Field label="Reading notes">
        <textarea {...field("notes")} />
      </Field>
      {reading && (
        <>
          <p>
            Correction retains the original reading, original targets and
            warning history. Current warnings are recalculated from the
            remaining observations.
          </p>
          <Field label="Correction reason">
            <input required {...field("reason")} />
          </Field>
        </>
      )}
    </Form>
  );
}
export function ReadingTable({
  readings,
  onCorrect,
}: {
  readings: Reading[];
  onCorrect?: (r: Reading) => void;
}) {
  return (
    <div className="environment-table">
      <table>
        <caption>Recorded observations · all times shown locally</caption>
        <thead>
          <tr>
            <th>Observed</th>
            <th>Temperature °F</th>
            <th>RH %</th>
            <th>CO₂ ppm</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {readings.map((r) => (
            <tr key={r.id}>
              <td>
                <time dateTime={r.observed_at}>
                  {friendlyTime(r.observed_at)}
                </time>
                {r.superseded_by && <p>Superseded by #{r.superseded_by}</p>}
              </td>
              <td>{r.temperature_f}</td>
              <td>{r.humidity}</td>
              <td>{r.co2 ?? "Not recorded"}</td>
              <td>
                <details>
                  <summary>Reading #{r.id}</summary>
                  <p>
                    Source: {r.source} · Created: {friendlyTime(r.created_at)}
                  </p>
                  <p>
                    Profile: {r.snapshot.name ?? "No profile"}{" "}
                    {r.snapshot.revision
                      ? `· revision ${r.snapshot.revision}`
                      : ""}
                  </p>
                  <Targets profile={r.snapshot} />
                  <p>
                    {Object.entries(r.evaluations)
                      .map(([m, s]) => `${m}: ${s}`)
                      .join(" · ") || "No configured comparisons"}
                  </p>
                  <p>
                    Humidifier level: {r.humidifier ?? "Unknown"} · Fan level:{" "}
                    {r.fan ?? "Unknown"} (0–10)
                  </p>
                  <p>{r.notes}</p>
                  {r.replaces_id && (
                    <p>
                      Corrects #{r.replaces_id}: {r.correction_reason}
                    </p>
                  )}
                  <p>Containers present at observation:</p>
                  {r.fruiting_ids.length ? (
                    <ul>
                      {r.fruiting_ids.map((id) => (
                        <li key={id}>
                          <Link to={`/culture-library/fruiting/${id}`}>
                            {id}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>None assigned</p>
                  )}
                  {onCorrect && !r.superseded_by && (
                    <button onClick={() => onCorrect(r)}>
                      Correct reading #{r.id}
                    </button>
                  )}
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!readings.length && <p>No observations in this range.</p>}
    </div>
  );
}
function Chart({ readings, metric }: { readings: Reading[]; metric: Metric }) {
  const m = metrics.find((m) => m.key === metric)!;
  const points = readings
    .filter((r) => !r.superseded_by && r[metric] != null)
    .sort((a, b) => a.observed_at.localeCompare(b.observed_at) || a.id - b.id);
  if (!points.length) return null;
  const vals = points.flatMap((r) =>
    [
      r[metric]!,
      r.snapshot.targets[metric + "_min"],
      r.snapshot.targets[metric + "_max"],
    ].filter((v): v is number => v != null),
  );
  const low = Math.min(...vals),
    high = Math.max(...vals),
    spread = high - low || 1;
  const times = points.map((r) => new Date(r.observed_at).getTime()),
    start = Math.min(...times),
    end = Math.max(...times);
  const x = (t: number) => 70 + ((t - start) / (end - start || 1)) * 620,
    y = (v: number) => 180 - ((v - low) / spread) * 140;
  return (
    <figure className="environment-chart">
      <figcaption>
        {m.label} ({m.unit}) · {points.length} recorded points
      </figcaption>
      <svg
        viewBox="0 0 740 240"
        role="img"
        aria-label={`${m.label} recorded observations; accessible values in table below`}
      >
        <line x1="70" y1="180" x2="690" y2="180" stroke="currentColor" />
        <text x="5" y="45">
          {high.toFixed(1)}
        </text>
        <text x="5" y="185">
          {low.toFixed(1)}
        </text>
        {points.map((r) => {
          const px = x(new Date(r.observed_at).getTime()),
            min = r.snapshot.targets[metric + "_min"],
            max = r.snapshot.targets[metric + "_max"];
          return (
            <g key={r.id}>
              {min != null && max != null && (
                <line
                  x1={px}
                  x2={px}
                  y1={y(min)}
                  y2={y(max)}
                  stroke="#8aa36c"
                  strokeWidth="10"
                  opacity=".45"
                />
              )}
              <circle
                cx={px}
                cy={y(r[metric]!)}
                r="4"
                fill={
                  ["low", "high"].includes(r.evaluations[metric] ?? "")
                    ? "#e1bd78"
                    : r.evaluations[metric] === "normal"
                      ? "#80c3ed"
                      : "#adc0d2"
                }
              >
                <title>
                  {friendlyTime(r.observed_at)} · {r[metric]} {m.unit}
                </title>
              </circle>
            </g>
          );
        })}
        <text x="70" y="210">
          {new Date(start).toLocaleString()}
        </text>
        <text x="690" y="232" textAnchor="end">
          {new Date(end).toLocaleString()}
        </text>
      </svg>
    </figure>
  );
}
function History({
  tent,
  revision,
  onSaved,
}: {
  tent: Tent;
  revision: number;
  onSaved: () => void;
}) {
  const [range, setRange] = useState("7"),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [page, setPage] = useState(1),
    [correct, setCorrect] = useState<Reading | null>(null);
  const [rangeError, setRangeError] = useState("");
  const [bounds, setBounds] = useState(() => ({
    start: new Date(Date.now() - 7 * 86400000).toISOString(),
    end: new Date().toISOString(),
  }));
  useEffect(() => {
    if (range !== "custom")
      setBounds({
        start: new Date(Date.now() - Number(range) * 86400000).toISOString(),
        end: new Date().toISOString(),
      });
  }, [revision, range]);
  const state = useEnvironment<Page<Reading>>(
    `tents/${tent.id}/readings?${new URLSearchParams({ ...bounds, page: String(page) })}`,
    revision,
  );
  function updateRange(value: string) {
    setRange(value);
    setPage(1);
  }
  return (
    <CollapsiblePanel title="Environmental history" defaultOpen>
      <Field label="History time range">
        <select value={range} onChange={(e) => updateRange(e.target.value)}>
          <option value="1">Last 24 hours</option>
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
          <option value="custom">Custom date range</option>
        </select>
      </Field>
      {range === "custom" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            try {
              const a = observationTime(start),
                b = observationTime(end);
              if (a > b) throw new Error("Range start must precede end");
              setBounds({ start: a, end: b });
              setPage(1);
              setRangeError("");
            } catch (error) {
              setRangeError((error as Error).message);
            }
          }}
        >
          <Field label="Range start (local)">
            <input
              required
              type="datetime-local"
              step="0.001"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </Field>
          <Field label="Range end (local)">
            <input
              required
              type="datetime-local"
              step="0.001"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </Field>
          <button>Apply range</button>
          {rangeError && <p role="alert">{rangeError}</p>}
        </form>
      )}
      <Load state={state} />
      <p>
        Intermittent observations show measurements taken at those times, not
        continuous monitored conditions. Green target bars use each
        observation’s saved profile; missing bounds have no band. Charts show
        this page only (up to 100 readings); use pagination for older points.
      </p>
      {state.data && (
        <>
          {metrics.map((m) => (
            <Chart key={m.key} metric={m.key} readings={state.data!.items} />
          ))}
          <ReadingTable readings={state.data.items} onCorrect={setCorrect} />
          <Pager
            page={page}
            total={state.data.total}
            size={100}
            onPage={setPage}
          />
        </>
      )}
      {correct && (
        <section className="panel" aria-label="Correct reading">
          <h3>Correct reading #{correct.id}</h3>
          <button onClick={() => setCorrect(null)}>Cancel correction</button>
          <ReadingForm
            key={correct.id}
            tent={tent}
            reading={correct}
            onSaved={() => {
              setCorrect(null);
              onSaved();
            }}
          />
        </section>
      )}
    </CollapsiblePanel>
  );
}
function OccupancyEditor({
  tent,
  occupancy,
  onSaved,
}: {
  tent: Tent;
  occupancy?: Occupancy;
  onSaved: () => void;
}) {
  const [container, setContainer] = useState(occupancy?.fruiting_id ?? ""),
    [entered, setEntered] = useState(localDateTime(occupancy?.entered_at)),
    [left, setLeft] = useState(
      occupancy?.left_at ? localDateTime(occupancy.left_at) : "",
    ),
    [reason, setReason] = useState(""),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(1);
  const containers = useEnvironment<{ id: string; title: string }[]>(
    `containers?q=${encodeURIComponent(query)}&page=${page}`,
  );
  return (
    <Form
      path={`tents/${tent.id}/occupancy${occupancy ? "/" + occupancy.id : ""}`}
      method={occupancy ? "PUT" : "POST"}
      onSaved={onSaved}
      payload={() => ({
        fruiting_id: container,
        entered_at: observationTime(entered),
        left_at: left ? observationTime(left) : null,
        ...(occupancy ? { expected_revision: occupancy.revision, reason } : {}),
      })}
    >
      {!occupancy ? (
        <>
          <Field label="Find container by permanent ID">
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
            />
          </Field>
          <Load state={containers} />
          <Field label="Fruiting container">
            <select
              required
              value={container}
              onChange={(e) => setContainer(e.target.value)}
            >
              <option value="">Select existing container</option>
              {containers.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </Field>
          <div className="actions">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              Previous containers
            </button>
            <button
              type="button"
              disabled={(containers.data?.length ?? 0) < 50}
              onClick={() => setPage(page + 1)}
            >
              More containers
            </button>
          </div>
        </>
      ) : (
        <p>Container: {container}</p>
      )}
      <Field label="Entered tent (local time)">
        <input
          required
          type="datetime-local"
          step="0.001"
          value={entered}
          onChange={(e) => setEntered(e.target.value)}
        />
      </Field>
      <Field label="Left tent (local time, optional)">
        <input
          type="datetime-local"
          step="0.001"
          value={left}
          onChange={(e) => setLeft(e.target.value)}
        />
      </Field>
      {occupancy && (
        <Field label="Occupancy correction reason">
          <input
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
      )}
    </Form>
  );
}
function ContainerEnvironmentData({ id }: { id: string }) {
  const [page, setPage] = useState(1),
    [readingPage, setReadingPage] = useState(1);
  const state = useEnvironment<Page<Occupancy>>(
      `occupancy?fruiting_id=${encodeURIComponent(id)}&page=${page}`,
    ),
    readings = useEnvironment<Page<Reading>>(
      `containers/${id}/readings?page=${readingPage}`,
    );
  return (
    <>
      <p>
        Measurements taken during explicit occupancy periods are intermittent
        observations, not continuous exposure records.
      </p>
      <Load state={state} />
      {state.data && (
        <>
          <OccupancyList rows={state.data.items} />
          <Pager
            page={page}
            total={state.data.total}
            size={50}
            onPage={setPage}
          />
        </>
      )}
      <Load state={readings} />
      {readings.data && (
        <>
          <ReadingTable readings={readings.data.items} />
          <Pager
            page={readingPage}
            total={readings.data.total}
            size={50}
            onPage={setReadingPage}
          />
        </>
      )}
      <Link to={`/environment?container=${id}`}>Manage tent occupancy</Link>
    </>
  );
}
export function ContainerEnvironment({ id }: { id: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <CollapsiblePanel
      title="Tent occupancy & recorded conditions"
      onExpand={() => setExpanded(true)}
    >
      {expanded && <ContainerEnvironmentData id={id} />}
    </CollapsiblePanel>
  );
}
function OccupancyList({
  rows,
  onEdit,
}: {
  rows: Occupancy[];
  onEdit?: (o: Occupancy) => void;
}) {
  return (
    <ul className="record-list">
      {!rows.length && <li>No tent assignments recorded.</li>}
      {rows.map((o) => (
        <li key={o.id}>
          <Link to={`/culture-library/fruiting/${o.fruiting_id}`}>
            {o.fruiting_id}
          </Link>{" "}
          · <Link to={`/environment?tent=${o.tent_id}`}>{o.tent_name}</Link>
          <p>
            {friendlyTime(o.entered_at)} →{" "}
            {o.left_at ? friendlyTime(o.left_at) : "Still assigned"}
          </p>
          {onEdit && (
            <button onClick={() => onEdit(o)}>Edit occupancy #{o.id}</button>
          )}
        </li>
      ))}
    </ul>
  );
}
function Occupancies({
  tent,
  revision,
  onSaved,
}: {
  tent: Tent;
  revision: number;
  onSaved: () => void;
}) {
  const [page, setPage] = useState(1),
    [edit, setEdit] = useState<Occupancy | null>(null);
  const state = useEnvironment<Page<Occupancy>>(
    `occupancy?tent_id=${tent.id}&page=${page}`,
    revision,
  );
  return (
    <CollapsiblePanel title="Tent occupancy">
      <p>
        Assignments change no cultivation stage, harvest accounting or
        provenance. Entry is inclusive; removal is exclusive.
      </p>
      <Load state={state} />
      {state.data && (
        <>
          <OccupancyList rows={state.data.items} onEdit={setEdit} />
          <Pager
            page={page}
            total={state.data.total}
            size={50}
            onPage={setPage}
          />
        </>
      )}
      <h3>{edit ? "Edit interval" : "Assign container"}</h3>
      {edit && <button onClick={() => setEdit(null)}>Cancel edit</button>}
      <OccupancyEditor
        key={edit?.id ?? "new"}
        tent={tent}
        occupancy={edit ?? undefined}
        onSaved={() => {
          setEdit(null);
          onSaved();
        }}
      />
    </CollapsiblePanel>
  );
}
interface Event {
  id: number;
  metric: string;
  recorded_at: string;
  before: { state: string; reading_id: number } | null;
  after: { state: string; reading_id: number | null };
}
function AlertHistory({ tent, revision }: { tent: Tent; revision: number }) {
  const [page, setPage] = useState(1);
  const state = useEnvironment<
    Page<Event> & {
      assignments: { id: number; assigned_at: string; snapshot: Profile }[];
    }
  >(`tents/${tent.id}/history?page=${page}`, revision);
  return (
    <CollapsiblePanel title="Warning & profile history">
      <Load state={state} />
      {state.data && (
        <>
          <p>
            Audit times show when the app learned each state. Backdated
            evaluations remain on their reading. Corrections append transitions;
            original outcomes remain recorded.
          </p>
          <ul className="record-list">
            {state.data.items.map((e) => (
              <li key={e.id}>
                {friendlyTime(e.recorded_at)} · {e.metric}:{" "}
                {e.before?.state ?? "No prior state"} → {e.after.state} ·
                reading #{e.after.reading_id ?? "none"}
              </li>
            ))}
          </ul>
          <Pager
            page={page}
            total={state.data.total}
            size={50}
            onPage={setPage}
          />
          <h3>Latest 100 profile assignments / revisions</h3>
          <ul>
            {state.data.assignments.map((a) => (
              <li key={a.id}>
                {friendlyTime(a.assigned_at)} ·{" "}
                {a.snapshot.name ?? "No profile"} · revision{" "}
                {a.snapshot.revision ?? "—"}
              </li>
            ))}
          </ul>
        </>
      )}
    </CollapsiblePanel>
  );
}
function TentWorkspace({
  tentId,
  revision,
  onSaved,
  profiles,
}: {
  tentId: string;
  revision: number;
  onSaved: () => void;
  profiles: Profile[];
}) {
  const state = useEnvironment<Overview>(`tents/${tentId}/overview`, revision);
  const [profile, setProfile] = useState("");
  useEffect(() => {
    if (state.data) setProfile(state.data.tent.profile_id ?? "");
  }, [state.data]);
  if (!state.data) return <Load state={state} />;
  const { tent, latest, warnings, occupancy_count } = state.data;
  return (
    <>
      <section className="panel environment-overview">
        <h2>
          {tent.name} {tent.status === "archived" ? "· Archived" : ""}
        </h2>
        <p>{tent.description}</p>
        <p>
          Active profile: {state.data.profile?.name ?? "None selected"} ·{" "}
          {occupancy_count} containers currently assigned
        </p>
        <Targets profile={state.data.profile} />
        <div className="environment-grid">
          {metrics.map((m) => {
            const r = latest[m.key];
            return (
              <article key={m.key}>
                <h3>Latest recorded {m.label.toLowerCase()}</h3>
                <strong>{r ? `${r.value} ${m.unit}` : "No readings"}</strong>
                {r && (
                  <p>
                    <time dateTime={r.observed_at}>
                      {friendlyTime(r.observed_at)}
                    </time>{" "}
                    ·{" "}
                    {Math.max(
                      0,
                      Math.floor(
                        (Date.now() - new Date(r.observed_at).getTime()) /
                          3600000,
                      ),
                    )}{" "}
                    hours ago
                  </p>
                )}
              </article>
            );
          })}
        </div>
        <h3>Active environmental warnings</h3>
        {warnings.length ? (
          <ul aria-label="Environmental warnings">
            {warnings.map((w) => (
              <li key={w.metric}>
                {metrics.find((m) => m.key === w.metric)?.label}: {w.state} ·{" "}
                {w.value} {w.unit} · recorded {friendlyTime(w.observed_at)}
              </li>
            ))}
          </ul>
        ) : (
          <p>No open warnings. This reflects recorded observations only.</p>
        )}
        <a href="#add-reading" className="button">
          Add Reading
        </a>
      </section>
      <section id="add-reading">
        <CollapsiblePanel title="Add Reading" defaultOpen>
          {tent.status === "active" ? (
            <ReadingForm key={revision} tent={tent} onSaved={onSaved} />
          ) : (
            <p>Restore this tent to add readings.</p>
          )}
        </CollapsiblePanel>
      </section>
      <History tent={tent} revision={revision} onSaved={onSaved} />
      <Occupancies tent={tent} revision={revision} onSaved={onSaved} />
      <AlertHistory tent={tent} revision={revision} />
      <CollapsiblePanel title="Tent settings & active profile">
        <Form
          path={`tents/${tent.id}/profile`}
          onSaved={onSaved}
          payload={() => ({
            profile_id: profile || null,
            expected_revision: tent.revision,
          })}
        >
          <Field label="Active environmental profile">
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
            >
              <option value="">No profile</option>
              {profiles
                .filter(
                  (p) => p.status === "active" || p.id === tent.profile_id,
                )
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.status === "archived" ? " (archived)" : ""}
                  </option>
                ))}
            </select>
          </Field>
          <p>
            Profile changes apply from now onward. They do not resolve warnings;
            a newer qualifying measurement is required.
          </p>
        </Form>
        <TentEditor key={tent.revision} tent={tent} onSaved={onSaved} />
      </CollapsiblePanel>
    </>
  );
}
export default function Environment() {
  const [params, setParams] = useSearchParams(),
    [revision, setRevision] = useState(0),
    [edit, setEdit] = useState("");
  const saved = () => setRevision((r) => r + 1);
  const tents = useEnvironment<Tent[]>("tents", revision),
    profiles = useEnvironment<Profile[]>("profiles", revision);
  const selected =
    params.get("tent") ??
    tents.data?.find((t) => t.status === "active")?.id ??
    tents.data?.[0]?.id;
  return (
    <div className="environment-workspace">
      <PageHeader
        title="Environment"
        description="Manual fruiting tent observations, targets and history."
      />
      <Load state={tents} />
      <Load state={profiles} />
      {params.get("container") && (
        <p>
          Assign container {params.get("container")} using Tent occupancy below.
        </p>
      )}
      {tents.data?.length ? (
        <>
          <Field label="Fruiting tent">
            <select
              value={selected ?? ""}
              onChange={(e) => {
                const next = new URLSearchParams(params);
                next.set("tent", e.target.value);
                setParams(next);
              }}
            >
              {tents.data.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                  {t.status === "archived" ? " (archived)" : ""}
                </option>
              ))}
            </select>
          </Field>
          {selected && (
            <TentWorkspace
              key={selected}
              tentId={selected}
              revision={revision}
              onSaved={saved}
              profiles={profiles.data ?? []}
            />
          )}
        </>
      ) : (
        !tents.loading &&
        !tents.error && (
          <p>
            No tents yet. Create your first tent below; existing cultivation
            records stay unassigned.
          </p>
        )
      )}
      <CollapsiblePanel title="Create tent" defaultOpen={!tents.data?.length}>
        <TentEditor key={revision} onSaved={saved} />
      </CollapsiblePanel>
      <CollapsiblePanel title="Environmental profiles">
        <p>
          Create blank profiles and define your own targets. One shared profile
          applies to a tent, including mixed species.
        </p>
        <Field label="Manage profile">
          <select value={edit} onChange={(e) => setEdit(e.target.value)}>
            <option value="">New blank profile</option>
            {profiles.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.status}
              </option>
            ))}
          </select>
        </Field>
        <ProfileEditor
          key={`${edit}:${revision}`}
          profile={profiles.data?.find((p) => p.id === edit)}
          onSaved={saved}
        />
      </CollapsiblePanel>
    </div>
  );
}
