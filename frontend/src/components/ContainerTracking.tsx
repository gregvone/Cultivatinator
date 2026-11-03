import { useId, useState } from "react";
import type { LibraryRecord } from "../libraryApi";
import { localToday } from "../libraryApi";
import { useInventoryCommand } from "../preparationApi";
import { phaseName, useAvailableLabels } from "../containerApi";
import type { LabelChoice } from "../containerApi";
type TrackingRecord = Partial<Omit<LibraryRecord, "kind">> & {
  id: string;
  kind: string;
};
export function LabelChoices({
  material,
  count,
  choices,
  onChange,
  reusable,
}: {
  material: string;
  count: number;
  choices: LabelChoice[];
  onChange: (v: LabelChoice[]) => void;
  reusable?: boolean;
}) {
  const labelPrefix = useId();
  const labels = useAvailableLabels(material, reusable);
  return (
    <details className="panel workflow-source">
      <summary>
        Physical labels · automatic lowest available (optional override)
      </summary>
      <p>
        Labels identify physical containers and can be reused when reusable
        containers are released. Permanent culture IDs and history are separate.
      </p>
      {labels.error && (
        <p role="status">
          {labels.error}
          <button type="button" onClick={labels.reload}>
            Retry available labels
          </button>
        </p>
      )}
      {labels.data && (
        <>
          <p>
            {labels.data.reusable
              ? `Available: ${labels.data.available.join(", ") || "None yet"}.`
              : "Disposable labels are never reused."}{" "}
            Next new label: {labels.data.next_label}
          </p>
          {Array.from(
            {
              length: Number.isInteger(count)
                ? Math.min(100, Math.max(0, count))
                : 0,
            },
            (_, index) => (
              <label className="field" key={index}>
                <span id={`${labelPrefix}-${index}`}>
                  Container {index + 1} physical label
                </span>
                <select
                  aria-labelledby={`${labelPrefix}-${index}`}
                  value={
                    choices[index]?.new_label
                      ? "__new__"
                      : choices[index]?.label || ""
                  }
                  onChange={(e) => {
                    const next = Array.from(
                      { length: count },
                      (_, i) => choices[i] || {},
                    );
                    next[index] =
                      e.target.value === "__new__"
                        ? { new_label: true }
                        : e.target.value
                          ? { label: e.target.value }
                          : {};
                    onChange(next);
                  }}
                >
                  <option value="">Automatic · lowest available</option>
                  {labels.data!.available.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                  <option value="__new__">Add a new physical label</option>
                </select>
              </label>
            ),
          )}
        </>
      )}
    </details>
  );
}
export default function ContainerTracking({
  record,
  onSaved,
}: {
  record: TrackingRecord;
  onSaved: () => void;
}) {
  const supported =
    ["physical", "spawn", "fruiting", "prepared"].includes(record.kind) &&
    [
      "agar_plate",
      "lc_jar",
      "lc_syringe",
      "spawn_jar",
      "spawn_bag",
      "tray",
      "bag",
      "block",
      "other",
    ].includes(record.material_type || "");
  if (!supported) return null;
  return <Tracking record={record} onSaved={onSaved} />;
}
function Tracking({
  record,
  onSaved,
}: {
  record: TrackingRecord;
  onSaved: () => void;
}) {
  const command = useInventoryCommand("containers");
  const [labelOpen, setLabelOpen] = useState(false);
  const [choice, setChoice] = useState<LabelChoice[]>([]);
  const [reusable, setReusable] = useState(
    record.label_reusable ?? record.material_type === "tray",
  );
  const [action, setAction] = useState("");
  const [date, setDate] = useState(localToday());
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const terminal =
    ["used", "completed", "failed"].includes(record.lifecycle || "") ||
    ["used", "completed", "failed"].includes(record.growth_stage || "") ||
    record.stage === "used" ||
    (record.kind === "fruiting" && record.stage === "finished");
  const agar = record.material_type === "agar_plate";
  const spawn = record.kind === "spawn";
  const phase = record.growth_stage || (spawn ? record.stage : null);
  async function saveAction(e: React.FormEvent) {
    e.preventDefault();
    if (
      await command.send(`records/${record.kind}/${record.id}/state`, {
        action,
        action_date: date,
        reason: reason || null,
        notes: notes || null,
      })
    ) {
      setAction("");
      command.reset();
      onSaved();
    }
  }
  return (
    <section className="panel workflow-source">
      <h2>Container & Cultivation Status</h2>
      <p>
        Physical label:{" "}
        <strong>{record.physical_label || "Not assigned"}</strong>
        {record.physical_label &&
          ` · ${record.label_occupied ? "Occupied" : "Released"}`}
      </p>
      <p>Permanent record: {record.id}</p>
      <p>
        Status:{" "}
        {terminal
          ? phaseName(record.growth_stage || record.lifecycle, spawn)
          : phaseName(phase || record.lifecycle, spawn)}
      </p>
      {record.inoculation_date && <p>Inoculated: {record.inoculation_date}</p>}
      {record.ready_date && <p>Ready date: {record.ready_date}</p>}
      {record.used_date && <p>Used date: {record.used_date}</p>}
      {record.failed_date && <p>Failed date: {record.failed_date}</p>}
      {record.completed_date && <p>Completed date: {record.completed_date}</p>}
      {!terminal && (
        <div className="actions">
          {(!record.label_occupied || record.label_reusable) && (
            <button onClick={() => setLabelOpen(!labelOpen)}>
              {record.physical_label ? "Change Label" : "Assign Label"}
            </button>
          )}
          {(agar || spawn) &&
            record.kind !== "prepared" &&
            phase !== "ready" &&
            record.status === "active" && (
              <button
                onClick={() => {
                  setAction("ready");
                  setDate(localToday());
                }}
              >
                {spawn ? "Mark Ready for Spawning" : "Mark Ready"}
              </button>
            )}
          <button
            onClick={() => {
              setAction("failed");
              setDate(localToday());
            }}
          >
            Mark Failed
          </button>
          {!agar && !spawn && (
            <button
              onClick={() => {
                setAction("complete");
                setDate(localToday());
              }}
            >
              {record.kind === "fruiting"
                ? "Complete Growing Cycle"
                : "Complete / Retire Container"}
            </button>
          )}
        </div>
      )}
      {record.status === "archived" && record.label_occupied && (
        <p>
          Archiving retains the occupied label. Explicitly complete or fail the
          record to release it.
        </p>
      )}
      {labelOpen && !terminal && (
        <div>
          {record.material_type === "other" && (
            <label>
              <input
                type="checkbox"
                checked={reusable}
                onChange={(e) => setReusable(e.target.checked)}
              />
              Physically reusable container
            </label>
          )}
          <LabelChoices
            key={String(reusable)}
            material={record.material_type || "agar_plate"}
            reusable={record.kind === "fruiting" ? reusable : undefined}
            count={1}
            choices={choice}
            onChange={setChoice}
          />
          <div className="actions">
            <button
              disabled={command.busy}
              onClick={async () => {
                if (
                  await command.send(
                    `records/${record.kind}/${record.id}/label`,
                    {
                      ...choice[0],
                      ...(record.kind === "fruiting" ? { reusable } : {}),
                    },
                  )
                ) {
                  setLabelOpen(false);
                  command.reset();
                  onSaved();
                }
              }}
            >
              Save Label
            </button>
          </div>
        </div>
      )}
      {action && !terminal && (
        <form className="library-form" onSubmit={saveAction}>
          <h3>
            {action === "ready"
              ? "Confirm readiness"
              : action === "failed"
                ? "Record failure"
                : "Close growing cycle"}
          </h3>
          <label className="field">
            <span>Lifecycle date</span>
            <input
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Reason (optional)</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <label className="field">
            <span>Lifecycle notes (optional)</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <div className="actions">
            <button className="primary" disabled={command.busy}>
              Save Status
            </button>
            <button type="button" onClick={() => setAction("")}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {command.error && <p role="alert">{command.error}</p>}
    </section>
  );
}
