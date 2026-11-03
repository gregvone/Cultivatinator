import RecordNextAction from "../components/RecordNextAction";
import { FruitingList } from "./Fruiting";
import { useState } from "react";
import { Link } from "react-router-dom";
import { cultivationStatus } from "../containerApi";
import { PageHeader } from "../components/UI";
import StrainIdentity from "../components/StrainIdentity";
import { useInventoryList, materialNames } from "../preparationApi";
import type { Prepared } from "../preparationApi";
import type { LibraryRecord } from "../libraryApi";
type GrowingRecord = LibraryRecord & {
  cultivation: Prepared | null;
  pending_establishment?: boolean;
};
export default function Growing({
  workspace,
}: {
  workspace: "laboratory" | "cultivation";
}) {
  const records = useInventoryList<GrowingRecord>(
    `growing?workspace=${workspace}`,
  );
  const [filter, setFilter] = useState("active");
  const [search, setSearch] = useState("");
  const rows = (records.data || []).filter((r) => {
    const terminal =
      ["used", "completed", "failed", "depleted"].includes(
        r.lifecycle || "active",
      ) || r.stage === "used";
    return (
      (filter === "all" ||
        (filter === "active"
          ? !terminal && r.status === "active"
          : ["used", "completed", "failed", "depleted"].includes(filter)
            ? r.lifecycle === filter
            : filter === "ready" || filter === "colonizing"
              ? (r.growth_stage || r.stage) === filter && !terminal
              : r.material_type === filter &&
                !terminal &&
                r.status === "active")) &&
      `${r.physical_label || ""} ${r.id} ${r.strain_name || ""} ${r.line_id || ""}`
        .toLowerCase()
        .includes(search.toLowerCase())
    );
  });
  return (
    <>
      <PageHeader
        title={workspace === "laboratory" ? "Laboratory" : "Cultivation"}
        description={
          workspace === "laboratory"
            ? "Growing agar and liquid cultures, with their source and recipe history."
            : "Growing spawn and fruiting containers, with dated flush and harvest history."
        }
      />
      <h2>
        {workspace === "laboratory" ? "Growing Cultures" : "Growing Spawn"}
      </h2>
      <div className="actions">
        <Link
          className="button primary"
          to={
            workspace === "laboratory"
              ? "/quick-create/agar-plate"
              : "/quick-create/spawn"
          }
        >
          {workspace === "laboratory"
            ? "New Agar Plate"
            : "New Spawn Jar / Bag"}
        </Link>
        {workspace === "laboratory" && (
          <Link className="button" to="/quick-create/lc-container">
            New LC Container
          </Link>
        )}
        {workspace === "cultivation" && (
          <Link to="/cultivation/register-grow">
            Historical grow provenance
          </Link>
        )}
      </div>
      <div className="library-filters">
        <label className="field">
          <span>Show records</span>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="active">Active</option>
            {workspace === "laboratory" ? (
              <>
                <option value="colonizing">Germinating agar</option>
                <option value="ready">Ready agar</option>
                <option value="depleted">Depleted LC</option>
                <option value="agar_plate">Agar cultures</option>
                <option value="lc_jar">LC containers</option>
                <option value="lc_syringe">LC syringes</option>
              </>
            ) : (
              <>
                <option value="colonizing">Colonizing spawn</option>
                <option value="spawn_jar">Spawn jars</option>
                <option value="spawn_bag">Spawn bags</option>
                <option value="ready">Ready for Spawning</option>
              </>
            )}
            <option value="used">Used</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="all">All records</option>
          </select>
        </label>
        <label className="field">
          <span>Find by ID, strain or culture line</span>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      {records.error && (
        <p role="alert">
          {records.error}
          <button onClick={records.reload}>Retry growing records</button>
        </p>
      )}
      {!records.data && !records.error && (
        <p role="status">Loading growing records…</p>
      )}
      {records.data && !rows.length && <p>No matching growing records.</p>}
      <ul className="record-list panel">
        {rows.map((r) => (
          <li key={r.id}>
            <h2>
              <Link
                to={
                  r.pending_establishment
                    ? `/history/materials/${r.id}`
                    : `/culture-library/${r.kind}/${r.id}`
                }
              >
                {r.physical_label || r.id} ·{" "}
                {materialNames[r.material_type || ""] || r.material_type}
              </Link>
            </h2>
            {r.physical_label && <small>Permanent record: {r.id}</small>}
            <p>
              <StrainIdentity record={r} />
              {r.line_id && ` · Culture line ${r.line_id}`}
            </p>
            <p>
              Current Status: {cultivationStatus(r)}
              {r.pending_establishment && " · Pending spore establishment"}
              {r.status === "archived" && " · Archived record"}
            </p>
            <p>
              Inoculated: {r.cultivation?.source?.date || "Not recorded"} ·
              Registered: {new Date(r.created_at).toLocaleDateString()}
            </p>
            {(r.cultivation?.source || r.cultivation?.snapshot.recipe) && (
              <p className="list-context">
                {r.cultivation?.source && (
                  <>
                    Source:{" "}
                    <Link
                      to={`/culture-library/${r.cultivation.source.kind}/${r.cultivation.source.id}`}
                    >
                      {r.cultivation.source.physical_label ||
                        r.cultivation.source.id}
                    </Link>{" "}
                    ·{" "}
                  </>
                )}
                {r.cultivation?.snapshot.recipe && (
                  <span>Recipe: {r.cultivation.snapshot.recipe.name}</span>
                )}
              </p>
            )}
            <div className="actions">
              {!r.pending_establishment && <RecordNextAction record={r} />}
              {r.cultivation?.snapshot.recipe && (
                <Link to={`/history/materials/${r.id}`}>
                  Recipe & source history
                </Link>
              )}
            </div>
          </li>
        ))}
      </ul>
      {workspace === "cultivation" && <FruitingList />}
    </>
  );
}
