import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/UI";
import { allLibraryRecords } from "../libraryApi";
import type { LibraryRecord } from "../libraryApi";
import { useEffect } from "react";
import { InoculationForm } from "./PreparationWorkflow";
import {
  quickCreate,
  eligibleSource,
  sourceLabel,
  sourceKey,
} from "../quickCreate";
export default function LegacyInoculation() {
  const [operation, setOperation] = useState("agar-plate");
  const [sources, setSources] = useState<LibraryRecord[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setSources([]);
    setError("");
    Promise.all([
      allLibraryRecords("physical?status=active"),
      allLibraryRecords("spores?status=active"),
    ])
      .then((groups) => {
        if (live) setSources(groups.flat());
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [attempt]);
  const op = quickCreate.find((o) => o.id === operation)!;
  const allowed = sources.filter((r) => eligibleSource(op, r));
  return (
    <>
      <PageHeader
        title="Inoculate Previous Materials"
        description="Complete ready materials that were already prepared in the earlier workflow. Their permanent IDs and previous deductions are retained."
      />
      <Link to="/inventory/prepared">Back to prepared materials</Link>
      <label className="field">
        <span>Destination material</span>
        <select
          value={operation}
          onChange={(e) => {
            setOperation(e.target.value);
            setSelected("");
          }}
        >
          <option value="agar-plate">Agar plates</option>
          <option value="spawn">Spawn jars / bags</option>
          <option value="lc-container">LC containers</option>
          <option value="lc-syringe">LC syringes</option>
        </select>
      </label>
      <label className="field">
        <span>Source material</span>
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">Choose a source</option>
          {allowed.map((r) => (
            <option key={sourceKey(r)} value={sourceKey(r)}>
              {sourceLabel(r)}
            </option>
          ))}
        </select>
      </label>
      {error && (
        <p role="alert">
          {error}
          <button onClick={() => setAttempt((n) => n + 1)}>
            Retry sources
          </button>
        </p>
      )}
      <InoculationForm
        key={operation + selected}
        operation={operation}
        source={allowed.find((r) => sourceKey(r) === selected)}
      />
    </>
  );
}
