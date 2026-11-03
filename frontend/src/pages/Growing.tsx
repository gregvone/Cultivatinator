import { useState } from "react";
import { Link } from "react-router-dom";
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
      ["completed", "failed", "depleted"].includes(r.lifecycle || "active") ||
      r.stage === "used";
    return (
      (filter === "all" ||
        (filter === "active"
          ? !terminal && r.status === "active"
          : filter === "completed" || filter === "failed"
            ? r.lifecycle === filter
            : filter === "ready" || filter === "colonizing"
              ? r.stage === filter && !terminal
              : r.material_type === filter &&
                !terminal &&
                r.status === "active")) &&
      `${r.id} ${r.strain_name || ""} ${r.line_id || ""}`
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
            : "Colonizing spawn jars and bags, ready spawn and completed growing records."
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
      <label className="field">
        <span>Show records</span>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="active">Active</option>
          {workspace === "laboratory" ? (
            <>
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
                {r.id} ·{" "}
                {materialNames[r.material_type || ""] || r.material_type}
              </Link>
            </h2>
            <p>
              <StrainIdentity record={r} />
              {r.line_id && ` · Culture line ${r.line_id}`}
            </p>
            <p>
              Status:{" "}
              {r.lifecycle !== "active"
                ? r.lifecycle
                : r.pending_establishment
                  ? "Pending spore establishment"
                  : r.stage === "ready"
                    ? "Ready for Spawning"
                    : r.stage || "Inoculated / Growing"}{" "}
              · {r.status}
            </p>
            <p>
              Inoculated: {r.cultivation?.source?.date || "Not recorded"} ·
              Registered: {new Date(r.created_at).toLocaleDateString()}
            </p>
            {r.cultivation?.source && (
              <p>
                Source:{" "}
                <Link
                  to={`/culture-library/${r.cultivation.source.kind}/${r.cultivation.source.id}`}
                >
                  {r.cultivation.source.id}
                </Link>
              </p>
            )}
            {r.cultivation?.snapshot.recipe && (
              <p>
                Recipe: {r.cultivation.snapshot.recipe.name} ·{" "}
                <Link to={`/history/materials/${r.id}`}>
                  View recipe snapshot and source history
                </Link>
              </p>
            )}
          </li>
        ))}
      </ul>
      {workspace === "cultivation" && (
        <p>
          Actual spawning, substrate allocation and harvest tracking remain
          planned for 2C.3.
        </p>
      )}
    </>
  );
}
