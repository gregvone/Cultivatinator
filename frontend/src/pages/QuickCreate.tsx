import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { Plus } from "lucide-react";
import { PageHeader, Panel } from "../components/UI";
import StrainIdentity from "../components/StrainIdentity";
import DirectCreate from "./DirectCreate";
import { Field } from "./LibraryForms";
import {
  allLibraryRecords,
  provenanceApi,
  units,
  localToday,
} from "../libraryApi";
import type { LibraryRecord } from "../libraryApi";
import {
  quickCreate,
  workflowPath,
  eligibleSource,
  availableOperations,
  sourceLabel,
  sourceKey,
} from "../quickCreate";
import type { QuickOperation } from "../quickCreate";

export function QuickCreateSection() {
  return (
    <Panel
      title="Quick Create"
      icon={Plus}
      label="MATERIAL WORKFLOWS"
      className="quick-create-panel"
    >
      <p className="quick-create-intro">
        Choose the material you want to work with. Source choices and available
        steps depend on the operation.
      </p>
      <div className="quick-create-grid">
        {quickCreate.map((op) => (
          <Link
            key={op.id}
            className="quick-create-action"
            to={workflowPath(op)}
          >
            <op.icon size={23} aria-hidden="true" />
            <span>{op.title}</span>
          </Link>
        ))}
      </div>
    </Panel>
  );
}
export function CreateFromThis({ record }: { record: LibraryRecord }) {
  const operations = availableOperations(record);
  if (!operations.length) return null;
  return (
    <details className="create-from-this">
      <summary>Create From This</summary>
      <nav aria-label={`Create from ${record.id}`} className="actions">
        {operations.map((op) => (
          <Link key={op.id} className="button" to={workflowPath(op, record)}>
            {op.title}
          </Link>
        ))}
      </nav>
    </details>
  );
}
function SporePrintForm({ source }: { source: LibraryRecord }) {
  const [v, setV] = useState<Record<string, string>>({
    name: "",
    collection_date: localToday(),
    notes: "",
    quantity: "",
    unit: "print",
    storage_location: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const set = (name: string, value: string) => setV({ ...v, [name]: value });
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      // Existing 2B collection functionality; this is not a transfer or acquisition.
      const saved = await provenanceApi<LibraryRecord>(
        `fruiting/${source.id}/collect`,
        "POST",
        {
          material_type: "spore_print",
          name: v.name.trim() || null,
          notes: v.notes.trim() || null,
          collection_date: v.collection_date || null,
          quantity: v.quantity || null,
          unit: v.unit || null,
          storage_location: v.storage_location.trim() || null,
        },
      );
      navigate(`/culture-library/spores/${saved.id}`, {
        state: {
          message: `Spore print registered from ${source.id}. Attach photographs below.`,
        },
      });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Unable to register collection. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="library-form panel workflow-form" onSubmit={submit}>
      <h2>Register collected spore print</h2>
      <p>
        Record a completed collection. This preserves the fruiting source and
        its provenance; it does not establish a culture line.
      </p>
      <Field name="name" label="Optional name" values={v} set={set} />
      <Field
        name="collection_date"
        label="Collection date (optional)"
        type="date"
        values={v}
        set={set}
      />
      <Field
        name="quantity"
        label="Collected quantity (optional)"
        type="number"
        values={v}
        set={set}
      />
      <Field
        name="unit"
        label="Quantity unit"
        values={v}
        set={set}
        options={{ "": "Unknown", ...units }}
      />
      <Field
        name="storage_location"
        label="Storage location"
        values={v}
        set={set}
      />
      <Field
        name="notes"
        label="Collection notes"
        type="textarea"
        values={v}
        set={set}
      />
      {error && <p role="alert">{error}</p>}
      <div className="actions">
        <button className="primary" disabled={busy}>
          {busy ? "Registering…" : "Register Spore Print"}
        </button>
        <Link to={`/culture-library/fruiting/${source.id}`}>Cancel</Link>
      </div>
    </form>
  );
}
function WorkflowEntry({ operation }: { operation: QuickOperation }) {
  const [params, setParams] = useSearchParams();
  const [records, setRecords] = useState<LibraryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    Promise.all(
      operation.kinds.map((kind) => allLibraryRecords(`${kind}?status=active`)),
    )
      .then((groups) => {
        if (live)
          setRecords(
            groups.flat().filter((record) => eligibleSource(operation, record)),
          );
      })
      .catch((e) => {
        if (live)
          setError(e instanceof Error ? e.message : "Unable to load sources");
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [operation, attempt]);
  const requested = params.has("source_kind") || params.has("source_id");
  const key = `${params.get("source_kind")}:${params.get("source_id")}`;
  const selected = records.find((record) => sourceKey(record) === key);
  const sourceControl = (
    <div className="direct-source">
      <h2>Select source material</h2>
      <p>
        Active sources exclude completed, failed and depleted material. Known
        source balances are validated at submission; unknown balances remain
        unknown. Confirm biological suitability before inoculation.
      </p>
      {loading ? (
        <p role="status">Loading source choices…</p>
      ) : error ? (
        <div role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => setAttempt(attempt + 1)}>
            Retry sources
          </button>
        </div>
      ) : (
        <>
          <label className="field">
            <span id="workflow-source-label">Source material</span>
            <select
              aria-labelledby="workflow-source-label"
              value={selected ? sourceKey(selected) : ""}
              onChange={(e) => {
                const record = records.find(
                  (r) => sourceKey(r) === e.target.value,
                );
                const next = new URLSearchParams(params);
                if (record) {
                  next.set("source_kind", record.kind);
                  next.set("source_id", record.id);
                } else {
                  next.delete("source_kind");
                  next.delete("source_id");
                }
                setParams(next, { replace: true });
              }}
            >
              <option value="">Choose a source</option>
              {records.map((r) => (
                <option key={sourceKey(r)} value={sourceKey(r)}>
                  {sourceLabel(r)}
                </option>
              ))}
            </select>
          </label>
          {requested && !selected && (
            <p role="alert">
              The linked source is unavailable or unsuitable for this operation.
              Choose another active source.
            </p>
          )}
          {!records.length && (
            <p>
              No eligible sources are registered for this operation. Browse
              existing material in the Culture Library or receive outside
              material through Acquisitions.
            </p>
          )}
          {selected && (
            <div className="source-summary">
              <h3>Selected source · {selected.id}</h3>
              <p>
                <StrainIdentity record={selected} />
                {selected.line_id &&
                  ` · Culture line ${selected.line_id}`} ·{" "}
                {selected.stage || selected.status}
              </p>
              <Link to={`/culture-library/${selected.kind}/${selected.id}`}>
                View source record
              </Link>
            </div>
          )}
        </>
      )}
    </div>
  );
  const direct = ["agar-plate", "lc-syringe", "lc-container", "spawn"].includes(
    operation.id,
  );
  return (
    <>
      <Link to="/">← Dashboard</Link>
      <PageHeader title={operation.title} description={operation.description} />
      {direct ? (
        <DirectCreate
          key={operation.id}
          operation={operation.id}
          source={!loading && !error ? selected : undefined}
          sourceControl={sourceControl}
          onCreated={() => setAttempt((n) => n + 1)}
        />
      ) : (
        <>
          {sourceControl}
          {operation.deferred ? (
            <section className="panel workflow-source">
              <span className="badge">OPERATION NOT YET AVAILABLE</span>
              <h2>Planned operation</h2>
              <p>{operation.deferred}</p>
            </section>
          ) : !loading && !error && selected ? (
            <SporePrintForm key={sourceKey(selected)} source={selected} />
          ) : (
            <p className="feedback">
              Select a fruiting source to register an already collected print.
            </p>
          )}
        </>
      )}
      <div className="actions">
        <Link to="/culture-library">Browse Culture Library</Link>
        <Link to="/acquisitions">Receive outside material in Acquisitions</Link>
      </div>
    </>
  );
}
export default function QuickCreatePage() {
  const { operation: id } = useParams();
  const operation = quickCreate.find((op) => op.id === id);
  if (!operation)
    return (
      <>
        <PageHeader
          title="Workflow not found"
          description="Choose a supported material workflow from the dashboard."
        />
        <Link to="/">Return to Dashboard</Link>
      </>
    );
  return <WorkflowEntry key={operation.id} operation={operation} />;
}
