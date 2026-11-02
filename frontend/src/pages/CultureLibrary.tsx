import { useEffect, useRef, useState } from "react";
import { Dna, ImagePlus } from "lucide-react";
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
import type { Activity, Kind, LibraryRecord, Photo } from "../libraryApi";
import { LineagePanel } from "./Provenance";
import StrainIdentity from "../components/StrainIdentity";
import { EditForm } from "./LibraryForms";

function RecordLink({ record }: { record: LibraryRecord }) {
  return (
    <Link to={`/culture-library/${record.kind}/${record.id}`}>
      {title(record)}{" "}
      <small>
        {record.id} · {record.status}
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
        description="Your strains, acquired culture lines, and spore sources. Every container has its own identity."
      />
      <div className="actions library-actions">
        <Link className="button" to="/culture-library/acquire">
          Receive Acquisition
        </Link>
        <Link className="button" to="/culture-library/register-grow">
          Register Grow Provenance
        </Link>
        <Link className="button primary" to="/culture-library/add-strain">
          + Add Strain
        </Link>
        <Link className="button" to="/culture-library/receive-culture">
          Receive Culture
        </Link>
        <Link className="button" to="/culture-library/receive-spores">
          Receive Spores
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
            description="Add a strain, receive an acquisition, or adjust your search and filters."
          />
          {kind === "strains" && (
            <div className="empty-action">
              <Link className="button primary" to="/culture-library/add-strain">
                Add Strain
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
function PhotoViewer({
  photo,
  code,
  onClose,
}: {
  photo: Photo;
  code: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="photo-viewer"
      onCancel={onClose}
      aria-label="Photograph viewer"
    >
      <button autoFocus onClick={onClose}>
        Close photograph
      </button>
      <img src={photo.url} alt={`Photograph of ${code}`} />
    </dialog>
  );
}
function PhotoGallery({
  kind,
  code,
  onChange,
}: {
  kind: Kind;
  code: string;
  onChange: () => void;
}) {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [view, setView] = useState<Photo | null>(null);
  useEffect(() => {
    let live = true;
    libraryApi<Photo[]>(`${kind}/${code}/photos`)
      .then((p) => {
        if (live) setPhotos(p);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [kind, code, revision]);
  async function action(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      setRevision((v) => v + 1);
      onChange();
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Photo operation failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel gallery-panel">
      <h2>
        <ImagePlus size={18} aria-hidden="true" />
        Photographs
      </h2>
      <p>
        JPEG, PNG or WebP · up to 10 MB and 24 megapixels per image · originals
        retained
      </p>
      <label className="field">
        <span>Attach photographs</span>
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          disabled={busy}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (files.length)
              void action(async () => {
                for (const file of files) {
                  const body = new FormData();
                  body.append("file", file);
                  await libraryApi(`${kind}/${code}/photos`, "POST", body);
                }
              }, `${files.length} photograph(s) attached`);
          }}
        />
      </label>
      {busy && <p role="status">Saving photographs…</p>}
      {notice && <p role="status">{notice}</p>}
      {error && (
        <div role="alert">
          {error}
          <p>Refresh the gallery to check which photographs were saved.</p>
          <button
            onClick={() => {
              setError("");
              setRevision(revision + 1);
            }}
          >
            Refresh gallery
          </button>
        </div>
      )}
      {!photos.length && <p className="muted">No photographs attached.</p>}
      <div className="photo-grid">
        {photos.map((p, i) => (
          <figure key={p.id}>
            <button
              className="photo-open"
              onClick={() => setView(p)}
              aria-label={`Open photograph ${i + 1}`}
            >
              <img
                src={p.thumbnail_url}
                alt={`Photograph ${i + 1} of ${code}`}
              />
            </button>
            <figcaption>
              {p.is_cover ? (
                <span className="badge">Cover photograph</span>
              ) : (
                <button
                  disabled={busy}
                  onClick={() =>
                    void action(
                      () => libraryApi(`photos/${p.id}/cover`, "POST"),
                      "Cover photograph updated",
                    )
                  }
                >
                  Use as cover
                </button>
              )}
              <button
                disabled={busy}
                onClick={() => {
                  if (window.confirm("Remove this photograph permanently?"))
                    void action(
                      () => libraryApi(`photos/${p.id}`, "DELETE"),
                      "Photograph removed",
                    );
                }}
              >
                Remove
              </button>
            </figcaption>
          </figure>
        ))}
      </div>
      {view && (
        <PhotoViewer photo={view} code={code} onClose={() => setView(null)} />
      )}
    </section>
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
    <>
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
      <PageHeader
        title={title(record)}
        description={`${record.id} · ${kindNames[kind]} · ${record.status}`}
      />
      {(notice || location.state?.message) && (
        <p className="success-message" role="status">
          {notice || location.state.message}
        </p>
      )}
      <div className="actions">
        <button onClick={() => setEditing(!editing)}>Edit information</button>
        <button disabled={busy} onClick={() => void statusChange()}>
          {record.status === "active" ? "Archive record" : "Restore record"}
        </button>
        {kind === "strains" && record.status === "active" && (
          <>
            <Link
              className="button"
              to={`/culture-library/receive-culture?strain=${code}`}
            >
              Receive Culture
            </Link>
            <Link
              className="button"
              to={`/culture-library/receive-spores?strain=${code}`}
            >
              Receive Spores
            </Link>
          </>
        )}
        {kind === "lines" && record.status === "active" && (
          <Link
            className="button"
            to={`/culture-library/receive-culture?line=${code}${record.strain_id ? `&strain=${record.strain_id}` : ""}`}
          >
            Add physical containers
          </Link>
        )}
      </div>
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
        <section className="panel detail-panel">
          <h2>Record information</h2>
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
              .filter(([k]) => record[k as keyof LibraryRecord] != null)
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
              <dt>Registered</dt>
              <dd>{new Date(record.created_at).toLocaleString()}</dd>
            </div>
          </dl>
          {(kind === "physical" || kind === "spores") && (
            <p className="license-note">
              Quantities describe initial registration. Usage and remaining
              balances are not tracked.
            </p>
          )}
        </section>
      )}
      {kind !== "strains" && (
        <LineagePanel
          key={`lineage/${kind}/${code}`}
          record={record}
          onChange={() => setRevision((v) => v + 1)}
        />
      )}
      <PhotoGallery
        key={`${kind}/${code}`}
        kind={kind}
        code={code}
        onChange={() => setRevision((v) => v + 1)}
      />
      {(kind === "strains" || kind === "lines") && (
        <section className="panel related-panel">
          <h2>
            {kind === "strains"
              ? "Related culture lines and spore sources"
              : "Individual physical containers"}
          </h2>
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
        </section>
      )}
      <section className="panel history-panel">
        <h2>Activity history</h2>
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
      </section>
    </>
  );
}
