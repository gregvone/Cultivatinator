import RecordHeader from "../components/RecordHeader";
import CollapsiblePanel from "../components/CollapsiblePanel";
import { FruitingPanel } from "./Fruiting";
import PhotoGallery from "../components/PhotoGallery";
import { cultivationStatus } from "../containerApi";
import { useEffect, useState } from "react";
import { Dna } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from "../components/UI";
import {
  cultureTypes,
  growTypes,
  kindNames,
  libraryApi,
  allLibraryRecords,
  origins,
  sporeTypes,
  title,
} from "../libraryApi";
import type { Activity, Kind, LibraryRecord } from "../libraryApi";
import { MaterialOperationPanel } from "./PreparationWorkflow";
import ContainerTracking from "../components/ContainerTracking";
import { CreateFromThis } from "./QuickCreate";
import { LineagePanel } from "./Provenance";
import StrainIdentity from "../components/StrainIdentity";
import { EditForm } from "./LibraryForms";

function RecordLink({ record }: { record: LibraryRecord }) {
  const biological = ["physical", "spawn", "fruiting", "spores"].includes(
    record.kind,
  );
  return (
    <Link to={`/culture-library/${record.kind}/${record.id}`}>
      {title(record)}{" "}
      <small>
        {record.id} · {biological ? cultivationStatus(record) : record.status}
        {record.material_type === "agar_plate" &&
          record.status === "archived" &&
          " · Archived record"}
        {!biological && record.lifecycle && record.lifecycle !== "active"
          ? ` · ${record.lifecycle}`
          : ""}
      </small>
    </Link>
  );
}
export function CultureLibrary() {
  const [kind, setKind] = useState<Kind>("strains");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("active");
  const [strain, setStrain] = useState("");
  const [type, setType] = useState("");
  const [origin, setOrigin] = useState("");
  const [records, setRecords] = useState<LibraryRecord[]>([]);
  const [strains, setStrains] = useState<LibraryRecord[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [page, setPage] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    const p = new URLSearchParams({
      q: query,
      status,
      limit: "60",
      offset: String(page * 60),
    });
    if (strain) p.set("strain_id", strain);
    if (type) p.set("material_type", type);
    if (origin) p.set("origin", origin);
    Promise.all([
      libraryApi<LibraryRecord[]>(`${kind}?${p}`),
      allLibraryRecords("strains?status=all"),
    ])
      .then(([r, s]) => {
        if (live) {
          setRecords(r);
          setStrains(s);
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [kind, query, status, strain, type, origin, retry, page]);
  const changeKind = (k: Kind) => {
    setKind(k);
    setType("");
    setOrigin("");
    setStrain("");
    setPage(0);
  };
  return (
    <>
      <PageHeader
        title="Culture Library"
        description="Browse strains, cultures, spores, photographs, and source relationships. Create from the dashboard or a source record; receive outside material in Acquisitions."
      />
      <div className="actions">
        <Link className="button primary" to="/culture-library/add-strain">
          Add Strain
        </Link>
      </div>
      <div className="library-tabs" role="group" aria-label="Library views">
        {(Object.keys(kindNames) as Kind[]).map((k) => (
          <button
            key={k}
            aria-pressed={kind === k}
            onClick={() => changeKind(k)}
          >
            {kindNames[k]}
          </button>
        ))}
      </div>
      <div className="library-filters">
        <label className="field">
          <span>Search {kindNames[kind].toLowerCase()}</span>
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            placeholder="Name, permanent ID, supplier…"
          />
        </label>
        <label className="field">
          <span>Status</span>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(0);
            }}
          >
            <option value="active">Active</option>
            <option value="archived">Archived</option>
            <option value="all">All records</option>
          </select>
        </label>
        {!["strains", "batches", "fruiting"].includes(kind) && (
          <label className="field">
            <span>Strain filter</span>
            <select
              value={strain}
              onChange={(e) => {
                setStrain(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All strains</option>
              {strains.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {(kind === "spores" || kind === "physical") && (
          <label className="field">
            <span>Material type</span>
            <select
              value={type}
              onChange={(e) => {
                setType(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All types</option>
              {Object.entries(
                kind === "spores" ? sporeTypes : cultureTypes,
              ).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        )}
        {kind === "lines" && (
          <label className="field">
            <span>Origin filter</span>
            <select
              value={origin}
              onChange={(e) => {
                setOrigin(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All origins</option>
              {Object.entries(origins).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} retry={() => setRetry(retry + 1)} />
      ) : !records.length ? (
        <section className="panel">
          <EmptyState
            icon={Dna}
            title={
              kind === "strains" && !query && status === "active"
                ? "Your strain catalog starts here."
                : "No matching records."
            }
            description="Browse reference records or adjust your search and filters. Receive outside material in Acquisitions, or add a reference strain here."
          />
          {kind === "strains" && (
            <div className="empty-action">
              <Link className="button primary" to="/acquisitions">
                Receive outside material
              </Link>
            </div>
          )}
        </section>
      ) : kind === "strains" ? (
        <div className="strain-grid">
          {records.map((r) => (
            <Link
              className="strain-card"
              key={r.id}
              to={`/culture-library/strains/${r.id}`}
            >
              <div className="strain-image">
                {r.cover ? (
                  <img src={r.cover.thumbnail_url} alt={r.name || r.id} />
                ) : (
                  <Dna size={52} strokeWidth={1} aria-hidden="true" />
                )}
              </div>
              <div className="strain-card-body">
                <div className="card-meta">
                  <small>{r.id}</small>
                  <span className="badge">{r.status}</span>
                </div>
                <h2>{r.name}</h2>
                {r.scientific_name && (
                  <p className="scientific">{r.scientific_name}</p>
                )}
                <dl className="strain-counts">
                  <div>
                    <dt>Lines</dt>
                    <dd>{r.line_count}</dd>
                  </div>
                  <div>
                    <dt>Spore sources</dt>
                    <dd>{r.spore_count}</dd>
                  </div>
                  <div>
                    <dt>Containers</dt>
                    <dd>{r.physical_count}</dd>
                  </div>
                </dl>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <ul className="record-list panel">
          {records.map((r) => (
            <li key={r.id}>
              <RecordLink record={r} />
              <p>
                <StrainIdentity record={r} /> ·{" "}
                {r.material_type
                  ? (
                      {
                        ...cultureTypes,
                        ...sporeTypes,
                        ...growTypes,
                      } as Record<string, string>
                    )[r.material_type]
                  : r.origin
                    ? origins[r.origin as keyof typeof origins]
                    : ""}
                {r.supplier ? ` · ${r.supplier}` : ""}
              </p>
              {r.balance_tracked && (
                <p>
                  Remaining Culture Material:{" "}
                  {r.remaining_quantity ?? "Unknown"} {r.remaining_unit}
                </p>
              )}
              {r.quantity !== null && (
                <p>
                  Registered Quantity: {r.quantity} {r.unit}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {!loading && !error && (
        <div className="actions pagination">
          <button disabled={!page} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span>Page {page + 1}</span>
          <button
            disabled={records.length < 60}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}
export function RecordDetail() {
  const { kind: rawKind, code = "" } = useParams();
  const kind = rawKind as Kind;
  const [record, setRecord] = useState<LibraryRecord | null>(null);
  const [related, setRelated] = useState<LibraryRecord[]>([]);
  const [history, setHistory] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const location = useLocation();
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    const rel =
      kind === "strains"
        ? Promise.all([
            allLibraryRecords(`lines?strain_id=${code}&status=all&limit=1000`),
            allLibraryRecords(`spores?strain_id=${code}&status=all&limit=1000`),
          ]).then(([a, b]) => [...a, ...b])
        : kind === "lines"
          ? allLibraryRecords(`physical?line_id=${code}&status=all&limit=1000`)
          : Promise.resolve([]);
    Promise.all([
      libraryApi<LibraryRecord>(`${kind}/${code}`),
      libraryApi<Activity[]>(`${kind}/${code}/activity`),
      rel,
    ])
      .then(([r, h, rel]) => {
        if (live) {
          setRecord(r);
          setHistory(h);
          setRelated(rel);
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [kind, code, revision]);
  if (loading && (!record || record.id !== code || record.kind !== kind))
    return <LoadingState />;
  if (error)
    return <ErrorState error={error} retry={() => setRevision(revision + 1)} />;
  if (!record) return null;
  const biological =
    record.material_type === "agar_plate" || kind === "fruiting";
  async function statusChange() {
    if (!record) return;
    const next = record.status === "active" ? "archived" : "active";
    if (
      next === "archived" &&
      !window.confirm(
        `Archive ${record.id}? Related records and photographs will be retained.`,
      )
    )
      return;
    setBusy(true);
    try {
      await libraryApi(`${kind}/${code}/status`, "POST", { status: next });
      setNotice(next === "active" ? "Record restored." : "Record archived.");
      setRevision(revision + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update status");
    } finally {
      setBusy(false);
    }
  }
  const labels: Record<string, string> = {
    scientific_name: "Scientific name",
    description: "Description",
    origin: "Origin",
    supplier: "Supplier / source",
    supplier_batch: "Supplier batch identifier",
    supplier_reference: "Supplier reference",
    acquisition_date: "Acquisition date",
    material_type: "Material type",
    quantity: kind === "physical" ? "Starting Quantity" : "Registered Quantity",
    storage_location: "Storage location",
    purchase_price: "Purchase price per container",
    notes: "Notes",
    stage: "Stage",
    batch_origin: "Batch origin",
    allocation_mode: "Allocation mode",
  };
  return (
    <div key={`${kind}/${code}`} className="record-detail">
      <Link to="/culture-library">← Culture Library</Link>
      {record.strain_id && (
        <p className="breadcrumb">
          <Link to={`/culture-library/strains/${record.strain_id}`}>
            {record.strain_name}
          </Link>
        </p>
      )}
      {record.line_id && (
        <p className="breadcrumb">
          <Link to={`/culture-library/lines/${record.line_id}`}>
            Culture line {record.line_id}
          </Link>
        </p>
      )}
      <RecordHeader record={record} />
      {(notice || location.state?.message) && (
        <p className="success-message" role="status">
          {notice || location.state.message}
        </p>
      )}
      {kind === "fruiting" ? (
        <FruitingPanel
          record={record}
          onSaved={() => setRevision((v) => v + 1)}
          sourceContent={
            <LineagePanel
              key={`lineage/${kind}/${code}`}
              record={record}
              onChange={() => setRevision((v) => v + 1)}
            />
          }
        />
      ) : (
        <ContainerTracking
          record={record}
          onSaved={() => setRevision((v) => v + 1)}
        />
      )}
      <div className="actions">
        <button className="secondary" onClick={() => setEditing(!editing)}>
          Edit information
        </button>
        <button disabled={busy} onClick={() => void statusChange()}>
          {record.status === "active" ? "Archive record" : "Restore record"}
        </button>
      </div>
      <CreateFromThis record={record} />
      {editing ? (
        <EditForm
          key={record.id}
          record={record}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            setNotice("Changes saved.");
            setRevision(revision + 1);
          }}
        />
      ) : (
        <CollapsiblePanel title="Record information" className="detail-panel">
          <dl className="info-list">
            <div>
              <dt>Permanent ID</dt>
              <dd>{record.id}</dd>
            </div>
            {kind !== "strains" && (
              <div>
                <dt>Strain</dt>
                <dd>
                  <StrainIdentity record={record} />
                </dd>
              </div>
            )}
            {Object.entries(labels)
              .filter(
                ([k]) =>
                  (k !== "stage" || kind !== "fruiting") &&
                  record[k as keyof LibraryRecord] != null,
              )
              .map(([k, label]) => (
                <div key={k}>
                  <dt>{label}</dt>
                  <dd>
                    {k === "quantity"
                      ? `${record.quantity} ${record.unit || ""}`
                      : k === "material_type"
                        ? (
                            {
                              ...cultureTypes,
                              ...sporeTypes,
                              ...growTypes,
                            } as Record<string, string>
                          )[record.material_type!]
                        : k === "stage" && ["physical", "spawn"].includes(kind)
                          ? cultivationStatus(record)
                          : String(record[k as keyof LibraryRecord])}
                  </dd>
                </div>
              ))}
            {(kind === "physical" || kind === "spores") &&
              record.quantity === null && (
                <div>
                  <dt>
                    {kind === "physical"
                      ? "Starting Quantity"
                      : "Registered Quantity"}
                  </dt>
                  <dd>Unknown</dd>
                </div>
              )}
            <div>
              <dt>Record visibility</dt>
              <dd>{record.status === "active" ? "Active" : "Archived"}</dd>
            </div>
            <div>
              <dt>Registered</dt>
              <dd>{new Date(record.created_at).toLocaleString()}</dd>
            </div>
          </dl>
          {(kind === "physical" || kind === "spores") && (
            <p className="license-note">
              Initial registration quantities remain descriptive. Explicit
              Remaining Culture Material and recorded usage are shown separately
              below.
            </p>
          )}
        </CollapsiblePanel>
      )}
      {["physical", "spawn", "spores"].includes(kind) && (
        <MaterialOperationPanel
          key={`material/${kind}/${code}`}
          record={record}
          onSaved={() => setRevision((v) => v + 1)}
        />
      )}

      {kind !== "strains" && kind !== "fruiting" && (
        <CollapsiblePanel title="Source & Genetics">
          <LineagePanel
            key={`lineage/${kind}/${code}`}
            record={record}
            onChange={() => setRevision((v) => v + 1)}
          />
        </CollapsiblePanel>
      )}
      <CollapsiblePanel title="Photographs">
        <PhotoGallery
          key={`${kind}/${code}`}
          kind={kind}
          code={code}
          refreshToken={revision}
          onChange={() => setRevision((v) => v + 1)}
        />
      </CollapsiblePanel>
      {(kind === "strains" || kind === "lines") && (
        <CollapsiblePanel
          className="related-panel"
          title={
            kind === "strains"
              ? "Related culture lines and spore sources"
              : "Individual physical containers"
          }
        >
          {!related.length ? (
            <p>No related records registered yet.</p>
          ) : (
            <ul className="record-list">
              {related.map((r) => (
                <li key={r.id}>
                  <RecordLink record={r} />
                  <p>
                    {kindNames[r.kind]}
                    {r.quantity !== null
                      ? ` · Starting Quantity: ${r.quantity} ${r.unit}`
                      : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </CollapsiblePanel>
      )}
      <CollapsiblePanel
        title="Record History"
        summary="Permanent identifiers and audit events"
        className="history-panel"
      >
        <p>Permanent ID: {record.id}</p>
        <ol>
          {history.map((e) => (
            <li key={e.id}>
              <p>{e.description}</p>
              <time dateTime={e.occurred_at}>
                {new Date(e.occurred_at).toLocaleString()}
              </time>
            </li>
          ))}
        </ol>
      </CollapsiblePanel>
    </div>
  );
}
