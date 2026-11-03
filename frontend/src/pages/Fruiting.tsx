import { PhotoSelection, usePhotoUploads } from "../components/PhotoUploads";
import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link } from "react-router-dom";
import { Field } from "./LibraryForms";
import { libraryApi, localToday, title } from "../libraryApi";
import type { LibraryRecord } from "../libraryApi";
import { useInventoryCommand, useInventoryList } from "../preparationApi";
import type { Recipe } from "../preparationApi";
import { cultivationStatus } from "../containerApi";
import type { LabelChoice } from "../containerApi";
import { LabelChoices } from "../components/ContainerTracking";
import ContainerTracking from "../components/ContainerTracking";
import PhotoGallery from "../components/PhotoGallery";
import {
  EnvironmentFields,
  EnvironmentSnapshot,
  environmentPayload,
  environmentValues,
} from "../components/FruitingEnvironment";
import { fruitingApi } from "../fruitingApi";
import type { FruitingDetail, Harvest, Environment } from "../fruitingApi";
import { eligibleSource, quickCreate } from "../quickCreate";

type Values = Record<string, string>;
const quantity = (v: string | null | undefined) =>
  v == null ? "Unknown" : `${v} g`;
export function NewFruiting({
  source,
  sourceControl,
  onCreated,
  onSourceInvalid,
}: {
  source?: LibraryRecord;
  sourceControl: ReactNode;
  onCreated?: () => void;
  onSourceInvalid?: () => void;
}) {
  const recipes = useInventoryList<Recipe>("recipes");
  const command = useInventoryCommand("fruiting");
  const [v, setV] = useState<Values>({
    recipe_id: "",
    count: "1",
    spawning_date: localToday(),
    spawn_grams: "",
    substrate_grams: "",
    material_type: "tray",
    notes: "",
  });
  const [choices, setChoices] = useState<LabelChoice[]>([]);
  const [created, setCreated] = useState<LibraryRecord[] | null>(null);
  const [copied, setCopied] = useState("");
  const set = (name: string, value: string) => {
    if (name === "count" || name === "material_type") setChoices([]);
    setV({ ...v, [name]: value });
  };
  const allowed = (recipes.data || []).filter(
    (r) => r.recipe_type === "substrate" && r.status === "active",
  );
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!source || command.busy) return;
    const result = await command.send<{ containers: LibraryRecord[] }>(
      "create",
      {
        spawn_id: source.id,
        recipe_id: v.recipe_id,
        count: Number(v.count),
        spawning_date: v.spawning_date,
        spawn_grams: v.spawn_grams || null,
        substrate_grams: v.substrate_grams || null,
        material_type: v.material_type,
        notes: v.notes || null,
        ...(choices.length ? { label_choices: choices } : {}),
      },
      "POST",
      async () => {
        const fresh = await libraryApi<LibraryRecord>(`spawn/${source.id}`);
        if (
          !eligibleSource(
            quickCreate.find((op) => op.id === "fruiting-container")!,
            fresh,
          )
        ) {
          onSourceInvalid?.();
          throw new Error(
            "This spawn is no longer Ready. Choose an available Ready jar or bag.",
          );
        }
      },
    );
    if (result) {
      setCreated(result.containers);
      onCreated?.();
    }
  }
  if (created)
    return (
      <section className="panel workflow-source">
        <h2>
          Created {created.length} fruiting{" "}
          {created.length === 1 ? "container" : "containers"}
        </h2>
        <p>
          Source spawn consumed once. Each grow starts Colonizing, with flush 1
          awaiting its first Pinning event.
        </p>
        <ul>
          {created.map((r) => (
            <li key={r.id}>
              <Link to={`/culture-library/fruiting/${r.id}`}>
                Open {r.physical_label || r.id}
              </Link>
              <small>Permanent record: {r.id}</small>
            </li>
          ))}
        </ul>
        <label className="field">
          <span>Physical labels for copying</span>
          <textarea
            aria-label="Physical labels for copying"
            readOnly
            value={created.map((r) => r.physical_label || r.id).join(", ")}
          />
        </label>
        <button
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(
                created.map((r) => r.physical_label || r.id).join(", "),
              );
              setCopied("Labels copied.");
            } catch {
              setCopied("Copy the labels from the selectable text.");
            }
          }}
        >
          Copy Labels
        </button>
        {copied && <p role="status">{copied}</p>}
        <Link className="button" to="/cultivation">
          View growing records
        </Link>
      </section>
    );
  return (
    <form className="library-form panel workflow-form" onSubmit={save}>
      {sourceControl}
      <p>
        One Ready spawn source supplies all containers in this operation and
        becomes Used. It cannot supply a later operation. Quantities below are
        optional amounts per destination, not inventory deductions.
      </p>
      {recipes.error && (
        <p role="alert">
          {recipes.error}
          <button type="button" onClick={recipes.reload}>
            Retry recipes
          </button>
        </p>
      )}
      <Field
        name="recipe_id"
        label="Substrate recipe"
        required
        values={v}
        set={set}
        options={{
          "": "Choose a recipe",
          ...Object.fromEntries(allowed.map((r) => [r.id, r.name])),
        }}
      />
      {!allowed.length && (
        <Link to="/recipes/substrate">Set up a Substrate recipe</Link>
      )}
      <Field
        name="material_type"
        label="Fruiting container type"
        values={v}
        set={set}
        options={{
          tray: "Reusable tray / container",
          bag: "Disposable bag",
          block: "Disposable block",
        }}
      />
      <Field
        name="count"
        label="Number of fruiting containers"
        type="number"
        required
        values={v}
        set={set}
      />
      <Field
        name="spawning_date"
        label="Spawning date"
        type="date"
        required
        values={v}
        set={set}
      />
      <details>
        <summary>Optional quantities and notes</summary>
        <Field
          name="spawn_grams"
          label="Spawn per container (g, optional)"
          type="number"
          values={v}
          set={set}
        />
        <Field
          name="substrate_grams"
          label="Substrate per container (g, optional)"
          type="number"
          values={v}
          set={set}
        />
        <Field
          name="notes"
          label="Grow notes"
          type="textarea"
          values={v}
          set={set}
        />
      </details>
      <LabelChoices
        material={v.material_type}
        count={Number(v.count)}
        choices={choices}
        onChange={setChoices}
      />
      <p>
        The current optional tent settings are saved with this grow.{" "}
        <Link to="/settings">Fruiting Environment settings</Link>
      </p>
      {command.error && <p role="alert">{command.error}</p>}
      <button
        className="primary"
        disabled={
          command.busy || !source || !allowed.some((r) => r.id === v.recipe_id)
        }
      >
        {command.busy ? "Creating…" : "Create Fruiting Containers"}
      </button>
    </form>
  );
}

export function FruitingList() {
  const [rows, setRows] = useState<LibraryRecord[] | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("active");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    fruitingApi<LibraryRecord[]>("")
      .then((v) => {
        if (live) {
          setRows(v);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [attempt]);
  const visible = (rows || []).filter(
    (r) =>
      filter === "all" ||
      (filter === "active"
        ? r.status === "active" &&
          !["completed", "failed"].includes(
            r.fruiting_stage || r.lifecycle || "",
          ) &&
          r.stage !== "finished"
        : cultivationStatus(r).toLowerCase() === filter),
  );
  return (
    <section>
      <h2>Growing Fruiting Containers</h2>
      <Link className="button primary" to="/quick-create/fruiting-container">
        New Fruiting Container
      </Link>
      <label className="field">
        <span>Show fruiting records</span>
        <select
          aria-label="Show fruiting records"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="active">Growing</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="all">All / archived history</option>
        </select>
      </label>
      {error && (
        <p role="alert">
          {error}
          <button onClick={() => setAttempt((v) => v + 1)}>
            Retry fruiting records
          </button>
        </p>
      )}
      {!rows && !error && <p>Loading fruiting records…</p>}
      <ul className="record-list panel">
        {visible.map((r) => (
          <li key={r.id}>
            <h3>
              <Link to={`/culture-library/fruiting/${r.id}`}>{title(r)}</Link>
            </h3>
            <p>
              Current Status: {cultivationStatus(r)}
              {r.current_flush && ` · Flush ${r.current_flush}`}
            </p>
            <small>
              Permanent record: {r.id}
              {r.status === "archived" ? " · Archived record" : ""}
            </small>
          </li>
        ))}
      </ul>
      {rows && !visible.length && <p>No matching fruiting records.</p>}
    </section>
  );
}

function HarvestForm({
  fruitingId,
  entry,
  onSaved,
  onCancel,
  onRecordSaved,
}: {
  fruitingId: string;
  entry?: Harvest;
  onSaved: () => void;
  onCancel: () => void;
  onRecordSaved?: () => void;
}) {
  const [v, setV] = useState<Values>({
    harvest_date: entry?.harvest_date || localToday(),
    wet_grams: entry?.wet_grams || "",
    dry_grams: entry?.dry_grams || "",
    potency: entry?.potency?.toString() || "",
    potency_notes: entry?.potency_notes || "",
    notes: entry?.notes || "",
  });
  const command = useInventoryCommand("fruiting");
  const uploads = usePhotoUploads();
  const [saved, setSaved] = useState<Harvest | null>(null);
  async function uploadRemaining(target: Harvest) {
    const complete = await uploads.upload(`harvests/${target.id}/photos`);
    if (complete) onSaved();
    else onRecordSaved?.();
  }
  const set = (name: string, value: string) => setV({ ...v, [name]: value });
  async function save(e: FormEvent) {
    e.preventDefault();
    if (command.busy || uploads.busy) return;
    if (saved) {
      await uploadRemaining(saved);
      return;
    }
    const result = await command.send<Harvest>(
      entry ? `harvests/${entry.id}/edit` : `records/${fruitingId}/harvests`,
      {
        ...v,
        wet_grams: v.wet_grams || null,
        dry_grams: v.dry_grams || null,
        potency: v.potency ? Number(v.potency) : null,
        potency_notes: v.potency_notes || null,
        notes: v.notes || null,
        ...(entry ? { expected_revision: entry.revision } : {}),
      },
    );
    if (result) {
      if (entry) {
        onSaved();
        return;
      }
      setSaved(result);
      if (uploads.items.length) onRecordSaved?.();
      await uploadRemaining(result);
    }
  }
  return (
    <form className="library-form" onSubmit={save}>
      <h3>{entry ? "Edit Harvest" : "Record Harvest"}</h3>
      <fieldset disabled={!!saved || command.busy || uploads.busy}>
        <Field
          name="harvest_date"
          label="Harvest date"
          type="date"
          required
          values={v}
          set={set}
        />
        <Field
          name="wet_grams"
          label="Wet weight (g, optional)"
          type="number"
          values={v}
          set={set}
        />
        <Field
          name="dry_grams"
          label="Dry weight (g, optional)"
          type="number"
          values={v}
          set={set}
        />
        <Field
          name="potency"
          label="Subjective medicinal potency (optional)"
          values={v}
          set={set}
          options={{
            "": "Not assessed",
            "1": "1",
            "2": "2",
            "3": "3",
            "4": "4",
            "5": "5",
          }}
        />
        <p>
          Subjective grower assessment, not a laboratory assay or verified
          medicinal-compound concentration.
        </p>
        <Field
          name="potency_notes"
          label="Potency notes"
          type="textarea"
          values={v}
          set={set}
        />
        <Field
          name="notes"
          label="Special harvest notes"
          type="textarea"
          values={v}
          set={set}
        />
      </fieldset>
      {!entry && (
        <PhotoSelection
          uploads={uploads}
          label="Harvest photos (optional)"
          disabled={command.busy}
        />
      )}
      {saved && (
        <p role="status">
          <strong>Harvest {saved.id} saved.</strong>{" "}
          {uploads.items.some((item) => item.state === "failed")
            ? "Some photos failed. Retry the remaining files; this will not create another harvest."
            : "Photographs are uploaded separately from the saved harvest."}
        </p>
      )}
      {command.error && <p role="alert">{command.error}</p>}
      <button className="primary" disabled={command.busy || uploads.busy}>
        {saved
          ? "Retry remaining photos"
          : entry
            ? "Save Harvest Changes"
            : "Save Harvest"}
      </button>
      <button
        type="button"
        disabled={command.busy || uploads.busy}
        onClick={saved ? onSaved : onCancel}
      >
        {saved ? "Done — add remaining photos later" : "Cancel"}
      </button>
    </form>
  );
}
function HarvestCard({
  entry,
  onSaved,
  photoRevision,
}: {
  entry: Harvest;
  onSaved: () => void;
  photoRevision: number;
}) {
  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState<
    { revision: number; snapshot: Harvest; recorded_at: string }[] | null
  >(null);
  const [error, setError] = useState("");
  return (
    <section className="panel workflow-source">
      <h4>
        Harvest {entry.id} · {entry.harvest_date}
      </h4>
      <p>
        Wet: {quantity(entry.wet_grams)} · Dry: {quantity(entry.dry_grams)}
      </p>
      <p>Subjective medicinal potency: {entry.potency ?? "Not assessed"}</p>
      {entry.potency_notes && <p>{entry.potency_notes}</p>}
      {entry.notes && <p>{entry.notes}</p>}
      {editing ? (
        <HarvestForm
          fruitingId={entry.fruiting_id}
          entry={entry}
          onSaved={() => {
            setEditing(false);
            setHistory(null);
            onSaved();
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <button onClick={() => setEditing(true)}>
          Edit Harvest {entry.id}
        </button>
      )}
      <PhotoGallery
        kind="fruiting"
        code={entry.fruiting_id}
        harvestId={entry.id}
        onChange={onSaved}
        refreshToken={photoRevision}
        compact
      />
      <details
        onToggle={async (e) => {
          if (e.currentTarget.open && !history) {
            try {
              setHistory(await fruitingApi(`harvests/${entry.id}/history`));
            } catch (err) {
              setError(
                err instanceof Error ? err.message : "History unavailable",
              );
            }
          }
        }}
      >
        <summary>Measurement history</summary>
        {error && <p role="alert">{error}</p>}
        {history?.map((h) => (
          <p key={h.revision}>
            Revision {h.revision} · {h.recorded_at} · Wet{" "}
            {quantity(h.snapshot.wet_grams)} · Dry{" "}
            {quantity(h.snapshot.dry_grams)} · Subjective potency{" "}
            {h.snapshot.potency ?? "Not assessed"}
          </p>
        ))}
      </details>
    </section>
  );
}
function EnvironmentChangeForm({
  id,
  current,
  onSaved,
  onCancel,
}: {
  id: string;
  current: Environment | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [env, setEnv] = useState(environmentValues(current));
  const [v, setV] = useState<Values>({ change_date: localToday(), notes: "" });
  const command = useInventoryCommand("fruiting");
  return (
    <form
      className="library-form"
      onSubmit={async (e) => {
        e.preventDefault();
        if (
          await command.send(`records/${id}/environment`, {
            change_date: v.change_date,
            notes: v.notes,
            environment: environmentPayload(env),
          })
        )
          onSaved();
      }}
    >
      <h3>Record Environment Change</h3>
      <Field
        name="change_date"
        label="Environment change date"
        type="date"
        required
        values={v}
        set={(name, value) => setV({ ...v, [name]: value })}
      />
      <Field
        name="notes"
        label="Reason for environment change"
        type="textarea"
        required
        values={v}
        set={(name, value) => setV({ ...v, [name]: value })}
      />
      <EnvironmentFields value={env} onChange={setEnv} />
      {command.error && <p role="alert">{command.error}</p>}
      <button disabled={command.busy}>Save Environment Change</button>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

function GrowStageForm({
  id,
  action,
  label,
  onSaved,
  onRecordSaved,
  onCancel,
}: {
  id: string;
  action: string;
  label: string;
  onSaved: () => void;
  onRecordSaved: () => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState<Values>({
    action_date: localToday(),
    notes: "",
  });
  const [saved, setSaved] = useState<FruitingDetail | null>(null);
  const command = useInventoryCommand("fruiting");
  const uploads = usePhotoUploads();
  const pinning = action === "pinning" || action === "next_flush";
  async function uploadRemaining(target: FruitingDetail) {
    const number = target.run!.current_flush;
    const complete = await uploads.upload(
      `records/${id}/flushes/${number}/pinning/photos`,
    );
    if (complete) onSaved();
    else onRecordSaved();
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (command.busy || uploads.busy) return;
    if (saved) {
      await uploadRemaining(saved);
      return;
    }
    const result = await command.send<FruitingDetail>(`records/${id}/stage`, {
      action,
      action_date: value.action_date,
      notes: value.notes || null,
    });
    if (result) {
      if (!pinning) {
        onSaved();
        return;
      }
      setSaved(result);
      if (uploads.items.length) onRecordSaved();
      await uploadRemaining(result);
    }
  }
  return (
    <form className="library-form" onSubmit={save}>
      <h3>{label}</h3>
      <fieldset disabled={!!saved || command.busy || uploads.busy}>
        <Field
          name="action_date"
          label="Stage date"
          type="date"
          required
          values={value}
          set={(name, text) => setValue({ ...value, [name]: text })}
        />
        <Field
          name="notes"
          label="Stage notes (optional)"
          type="textarea"
          values={value}
          set={(name, text) => setValue({ ...value, [name]: text })}
        />
      </fieldset>
      {pinning && (
        <PhotoSelection
          uploads={uploads}
          label="Pinning photos (optional)"
          disabled={command.busy}
        />
      )}
      {saved && (
        <p role="status">
          <strong>Pinning saved for flush {saved.run!.current_flush}.</strong>{" "}
          {uploads.items.some((item) => item.state === "failed")
            ? "Some photos failed. Retry the remaining files; the stage and date will not be saved again."
            : "Photographs are uploaded separately from the saved Pinning event."}
        </p>
      )}
      {action === "complete" && (
        <p>
          Finish only when no more flushes are expected. This releases the
          physical label.
        </p>
      )}
      {command.error && <p role="alert">{command.error}</p>}
      <button className="primary" disabled={command.busy || uploads.busy}>
        {saved ? "Retry remaining photos" : "Save Grow Status"}
      </button>
      <button
        type="button"
        disabled={command.busy || uploads.busy}
        onClick={saved ? onSaved : onCancel}
      >
        {saved ? "Done — add remaining photos later" : "Cancel"}
      </button>
    </form>
  );
}

export function FruitingPanel({
  record,
  onSaved,
}: {
  record: LibraryRecord;
  onSaved: () => void;
}) {
  const [data, setData] = useState<FruitingDetail | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [action, setAction] = useState("");
  const [harvesting, setHarvesting] = useState(false);
  const [changing, setChanging] = useState(false);
  const reload = () => {
    setRevision((v) => v + 1);
    onSaved();
  };
  useEffect(() => {
    let live = true;
    fruitingApi<FruitingDetail>(`records/${record.id}`)
      .then((v) => {
        if (live) {
          setData(v);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [record.id, record.fruiting_stage, revision]);
  if (error && !data)
    return (
      <p role="alert">
        {error}
        <button onClick={() => setRevision((v) => v + 1)}>Retry grow</button>
      </p>
    );
  if (!data) return <p>Loading fruiting history…</p>;
  const stage =
    data.run?.stage ||
    (["failed", "completed"].includes(record.lifecycle || "")
      ? record.lifecycle
      : record.stage === "finished"
        ? "completed"
        : record.stage);
  const terminal = ["completed", "failed"].includes(stage || "");
  const active = !terminal && record.status === "active";
  const buttons: { action: string; label: string; visible: boolean }[] = [
    {
      action: "pinning",
      label: "Mark Pinning",
      visible:
        stage === "colonizing" || stage === "ready" || stage === "unrecorded",
    },
    {
      action: "fruiting",
      label: "Mark Fruiting",
      visible: stage === "pinning",
    },
    { action: "next_flush", label: "Next Flush", visible: stage === "harvest" },
    { action: "complete", label: "Finish Grow", visible: true },
    { action: "failed", label: "Mark Failed", visible: true },
  ];
  return (
    <section className="panel workflow-source">
      <h2>Fruiting & Harvest</h2>
      {error && (
        <p role="alert">
          {error}
          <button onClick={() => setRevision((v) => v + 1)}>Retry grow</button>
        </p>
      )}
      <p>
        <strong>
          Current Status:{" "}
          {data.run
            ? cultivationStatus({ ...record, fruiting_stage: data.run.stage })
            : record.stage === "ready"
              ? "Stage not recorded"
              : cultivationStatus(record)}
        </strong>
      </p>
      <p>Current flush: {data.run?.current_flush ?? "Not recorded"}</p>
      <p>Permanent record: {record.id}</p>
      {data.source ? (
        <p>
          Source spawn:{" "}
          <Link to={`/culture-library/spawn/${data.source.id}`}>
            {data.source.physical_label || data.source.id}
          </Link>{" "}
          <small>Permanent source: {data.source.id}</small>
        </p>
      ) : (
        <p>
          Earlier source links are available in provenance below; no spawning
          event is assumed.
        </p>
      )}
      <p>Spawning date: {data.run?.spawning_date || "Not recorded"}</p>
      {data.run?.completed_date && <p>Completed: {data.run.completed_date}</p>}
      {data.run?.failed_date && <p>Failed: {data.run.failed_date}</p>}
      {data.run?.closing_notes && <p>{data.run.closing_notes}</p>}
      {data.legacy && (
        <p>
          Legacy registration: earlier stages, quantities, recipes and
          environment remain unknown unless recorded. New actions record events
          from now onward.
        </p>
      )}
      <div className="actions">
        {active &&
          buttons
            .filter((b) => b.visible)
            .map((b) => (
              <button
                key={b.action}
                disabled={!!action || harvesting}
                onClick={() => {
                  setAction(b.action);
                  setHarvesting(false);
                }}
              >
                {b.label}
              </button>
            ))}
        {active && ["fruiting", "harvest"].includes(stage || "") && (
          <button
            className="primary"
            disabled={!!action || harvesting}
            onClick={() => {
              setHarvesting(true);
              setAction("");
            }}
          >
            Record Harvest
          </button>
        )}
      </div>
      {action && active && (
        <GrowStageForm
          key={action}
          id={record.id}
          action={action}
          label={buttons.find((b) => b.action === action)!.label}
          onRecordSaved={() => setRevision((v) => v + 1)}
          onSaved={() => {
            setAction("");
            reload();
          }}
          onCancel={() => setAction("")}
        />
      )}
      {harvesting && active && (
        <HarvestForm
          fruitingId={record.id}
          onRecordSaved={() => setRevision((v) => v + 1)}
          onSaved={() => {
            setHarvesting(false);
            reload();
          }}
          onCancel={() => setHarvesting(false)}
        />
      )}
      <ContainerTracking record={record} onSaved={reload} labelsOnly />
      <details>
        <summary>Substrate recipe and spawning quantities</summary>
        {data.run?.recipe_snapshot ? (
          <>
            <h3>
              Substrate: {data.run.recipe_snapshot.name} · revision{" "}
              {data.run.recipe_snapshot.revision}
            </h3>
            <ul>
              {data.run.recipe_snapshot.ingredients.map((i, index) => (
                <li key={index}>
                  {i.name || i.item_id}: {i.quantity} {i.unit}
                </li>
              ))}
            </ul>
            <p>{data.run.recipe_snapshot.instructions}</p>
            <p>{data.run.recipe_snapshot.notes}</p>
          </>
        ) : (
          <p>Substrate recipe not recorded.</p>
        )}
        <p>
          Spawn per container: {quantity(data.run?.spawn_grams)} · Substrate per
          container: {quantity(data.run?.substrate_grams)}
        </p>
      </details>
      <details>
        <summary>Fruiting environment</summary>
        <h3>Current grow environment</h3>
        <EnvironmentSnapshot value={data.environment} />
        <details>
          <summary>Original environment snapshot</summary>
          <EnvironmentSnapshot value={data.run?.environment_snapshot || null} />
        </details>
        {data.environment_changes.map((c) => (
          <section key={c.id}>
            <h4>{c.change_date}</h4>
            <p>{c.notes}</p>
            <EnvironmentSnapshot value={c.settings} />
          </section>
        ))}
        {active && !changing && (
          <button onClick={() => setChanging(true)}>
            Record Environment Change
          </button>
        )}
        {changing && active && (
          <EnvironmentChangeForm
            id={record.id}
            current={data.environment}
            onSaved={() => {
              setChanging(false);
              reload();
            }}
            onCancel={() => setChanging(false)}
          />
        )}
      </details>
      <h3>Grow Results</h3>
      <p>Flushes with harvests: {data.results.flushes_with_harvests}</p>
      <p>
        Total measured wet: {quantity(data.results.wet_grams)} · Total measured
        dry: {quantity(data.results.dry_grams)}
      </p>
      <p>
        Wet measurements: {data.results.wet_measured_count}/
        {data.results.harvest_count} · Dry measurements:{" "}
        {data.results.dry_measured_count}/{data.results.harvest_count}. Missing
        weights stay unknown.
      </p>
      <p>
        Days to first pinning: {data.results.days_to_first_pinning ?? "Unknown"}{" "}
        · Days to first harvest:{" "}
        {data.results.days_to_first_harvest ?? "Unknown"} · Completed cycle
        days: {data.results.cycle_days ?? "Unknown"}
      </p>
      <h3>Flushes & Harvest History</h3>
      {!data.flushes.length && <p>No flushes recorded.</p>}
      {data.flushes.map((f) => (
        <section key={f.number}>
          <h3>Flush {f.number}</h3>
          <section className="pinning-history">
            <h4>Pinning — {f.pinning_date || "Not recorded"}</h4>
            {f.pinning_notes && <p>{f.pinning_notes}</p>}
            {f.pinning_date && (
              <PhotoGallery
                kind="fruiting"
                code={record.id}
                pinningFlush={f.number}
                onChange={reload}
                refreshToken={revision}
                compact
              />
            )}
          </section>
          <p>Fruiting: {f.fruiting_date || "Not recorded"}</p>
          <p>
            Measured wet: {quantity(f.wet_grams)} · Measured dry:{" "}
            {quantity(f.dry_grams)}
          </p>
          {data.harvests
            .filter((h) => h.flush_number === f.number)
            .map((h) => (
              <HarvestCard
                key={h.id + "-" + h.revision}
                entry={h}
                photoRevision={revision}
                onSaved={reload}
              />
            ))}
        </section>
      ))}
    </section>
  );
}
