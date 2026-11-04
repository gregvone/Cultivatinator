import { useState, useEffect, useRef } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { FlaskConical } from "lucide-react";
import { Panel, LoadingState, ErrorState } from "./UI";
import { useApi } from "../useApi";
import { useInventoryCommand } from "../preparationApi";
import type { Recipe } from "../preparationApi";
import type { LibraryRecord } from "../libraryApi";
import { localToday } from "../libraryApi";
import { observationTime } from "../environmentApi";
import type { Experiment } from "../experimentApi";
import type { ParticipantPage, Participant } from "../experimentParticipants";

function Existing({
  record,
  data,
  save,
}: {
  record: Experiment;
  data: ParticipantPage;
  save: (path: string, payload: object) => Promise<unknown>;
}) {
  const [selected, setSelected] = useState("");
  const [group, setGroup] = useState(record.plan.groups[0]?.id || "");
  const [reason, setReason] = useState("Link existing fruiting container");
  const [instant, setInstant] = useState("");
  const [error, setError] = useState("");
  const candidate = data.candidates.find((c) => c.fruiting_id === selected);
  return (
    <form
      className="experiment-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        try {
          if (candidate)
            await save("enroll", {
              plan_revision: data.plan_revision,
              group_id: group,
              fruiting_id: selected,
              fingerprint: candidate.fingerprint,
              reason,
              ...(instant ? { treatment_start: observationTime(instant) } : {}),
            });
        } catch (e) {
          setError(e instanceof Error ? e.message : "Invalid treatment time");
        }
      }}
    >
      <h3>Link an existing container</h3>
      <label>
        Fruiting container
        <select
          required
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">Select a container</option>
          {data.candidates.map((c) => (
            <option key={c.fruiting_id} value={c.fruiting_id}>
              {c.fruiting_id} · {c.spawn_ids.join(", ") || "Source unknown"}
            </option>
          ))}
        </select>
      </label>
      <label>
        Assign to group
        <select value={group} onChange={(e) => setGroup(e.target.value)}>
          {record.plan.groups.map((g) => (
            <option key={g.id} value={g.id!}>
              {g.name}
            </option>
          ))}
        </select>
      </label>
      {candidate && (
        <>
          <p>
            Source spawn: {candidate.spawn_ids.join(", ") || "Unknown"}. Culture
            lines: {candidate.line_ids.join(", ") || "Unknown"}.
          </p>
          {candidate.suggestion?.reason && (
            <p role="status">Review: {candidate.suggestion.reason}</p>
          )}
          {candidate.ambiguous && (
            <p>Incomplete ancestry will remain flagged for review.</p>
          )}
        </>
      )}
      <label>
        Enrollment reason
        <input
          required
          maxLength={200}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <p>
        Recorded treatment dates determine classification. Historical or
        same-day ambiguous ordering cannot become prospective by linking now.
      </p>
      <details>
        <summary>Exact historical treatment time (optional)</summary>
        <label>
          Existing container treatment start (local time)
          <input
            type="datetime-local"
            step="0.001"
            value={instant}
            onChange={(e) => setInstant(e.target.value)}
          />
        </label>
      </details>
      {error && <p role="alert">{error}</p>}
      <button disabled={!candidate}>Link container</button>
    </form>
  );
}

function Creation({
  record,
  data,
  save,
}: {
  record: Experiment;
  data: ParticipantPage;
  save: (path: string, payload: object) => Promise<unknown>;
}) {
  const sources = useApi<LibraryRecord[]>("library/spawn?limit=1000");
  const recipes = useApi<Recipe[]>("preparation/recipes");
  const [spawn, setSpawn] = useState("");
  const [destinations, setDestinations] = useState(
    record.plan.groups.map((g, i) => ({
      group_id: g.id!,
      recipe_id: "",
      count: record.category === "genetics" && i > 0 ? 0 : 1,
    })),
  );
  const [allocation, setAllocation] = useState<string | null>(null);
  const [day, setDay] = useState(localToday());
  const [instant, setInstant] = useState("");
  const [localError, setLocalError] = useState("");
  if (sources.error)
    return <ErrorState error={sources.error} retry={sources.retry} />;
  if (recipes.error)
    return <ErrorState error={recipes.error} retry={recipes.retry} />;
  if (!sources.data || !recipes.data) return <LoadingState />;
  async function submit(e: FormEvent) {
    e.preventDefault();
    setLocalError("");
    if (!allocation) {
      const result = (await save("creation-allocations", {
        plan_revision: data.plan_revision,
        spawn_id: spawn,
        destinations: destinations.filter((d) => d.count > 0),
        reason: "Save source and destination assignments before treatment",
      })) as { allocation: { id: string } } | undefined;
      if (result) setAllocation(result.allocation.id);
    } else {
      try {
        const result = await save("fruiting", {
          allocation_id: allocation,
          spawning_date: day,
          ...(instant ? { treatment_start: observationTime(instant) } : {}),
          reason: "Create assigned fruiting containers",
        });
        if (result) {
          setAllocation(null);
          setSpawn("");
          sources.retry();
        }
      } catch (error) {
        setLocalError(
          error instanceof Error ? error.message : "Invalid treatment time",
        );
      }
    }
  }
  return (
    <form className="experiment-form" onSubmit={submit}>
      <h3>Create containers from this experiment</h3>
      <p>
        One Ready spawn source is consumed in full, divided across every
        destination. Saving assignments does not consume it.
      </p>
      <fieldset disabled={!!allocation}>
        <legend>Source and destination assignments</legend>
        <label>
          Ready spawn source
          <select
            required
            value={spawn}
            onChange={(e) => setSpawn(e.target.value)}
          >
            <option value="">Select a source</option>
            {sources.data
              .filter((s) => s.status === "active" && s.stage === "ready")
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.physical_label ? `${s.physical_label} · ` : ""}
                  {s.id} · {s.name || s.strain_name || "Unknown genetics"}
                </option>
              ))}
          </select>
        </label>
        {destinations.map((d, i) => (
          <fieldset key={d.group_id}>
            <legend>
              {record.plan.groups.find((g) => g.id === d.group_id)?.name}
            </legend>
            <label>
              Substrate recipe for group {i + 1}
              <select
                required={d.count > 0}
                disabled={d.count === 0}
                value={d.recipe_id}
                onChange={(e) =>
                  setDestinations((ds) =>
                    ds.map((v, j) =>
                      i === j ? { ...v, recipe_id: e.target.value } : v,
                    ),
                  )
                }
              >
                <option value="">Select a recipe</option>
                {recipes
                  .data!.filter(
                    (r) =>
                      r.recipe_type === "substrate" && r.status === "active",
                  )
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} · revision {r.revision}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Container count for group {i + 1}
              <input
                type="number"
                required
                min={0}
                max={100}
                value={d.count}
                onChange={(e) =>
                  setDestinations((ds) =>
                    ds.map((v, j) =>
                      i === j ? { ...v, count: Number(e.target.value) } : v,
                    ),
                  )
                }
              />
            </label>
          </fieldset>
        ))}
      </fieldset>
      {allocation && (
        <>
          <p role="status">
            Assignments saved as {allocation}. Review the actual treatment date
            before creating.
          </p>
          <label>
            Spawning date
            <input
              type="date"
              required
              value={day}
              onChange={(e) => setDay(e.target.value)}
            />
          </label>
          <details>
            <summary>Exact treatment time (optional)</summary>
            <label>
              Actual treatment start (local time)
              <input
                type="datetime-local"
                step="0.001"
                value={instant}
                onChange={(e) => setInstant(e.target.value)}
              />
            </label>
            <p>
              Use an actual known time. Without exact timing, same-day ordering
              remains uncertain.
            </p>
          </details>
          <button type="button" onClick={() => setAllocation(null)}>
            Change assignments
          </button>
        </>
      )}
      {localError && <p role="alert">{localError}</p>}
      <button>
        {allocation
          ? "Create assigned containers"
          : "Save assignments before treatment"}
      </button>
    </form>
  );
}

function ReviewForm({
  p,
  record,
  save,
  revision,
}: {
  p: Participant;
  record: Experiment;
  save: (path: string, payload: object) => Promise<unknown>;
  revision: number;
}) {
  const [decision, setDecision] = useState("keep");
  const [group, setGroup] = useState(record.plan.groups[0]?.id || "");
  const [reason, setReason] = useState("");
  return (
    <form
      className="experiment-form"
      onSubmit={async (e) => {
        e.preventDefault();
        await save(`participants/${p.id}/review`, {
          decision,
          reason,
          fingerprint: p.sources.fingerprint,
          ...(decision === "reassign"
            ? { group_id: group, plan_revision: revision }
            : {}),
        });
      }}
    >
      <p>
        {p.evidence.review_reason ||
          "Corrections retain an audit trail and cannot promote retrospective evidence."}
      </p>
      <label>
        Review decision
        <select value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="keep">Keep confirmed group</option>
          <option value="exclude">Exclude from experiment</option>
          <option value="reassign">Correct group assignment</option>
        </select>
      </label>
      {decision === "reassign" && (
        <label>
          Corrected group
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            {record.plan.groups.map((g) => (
              <option key={g.id} value={g.id!}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Review reason
        <input
          required
          maxLength={200}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <button>Save review</button>
    </form>
  );
}

function SourceRules({
  record,
  data,
  save,
}: {
  record: Experiment;
  data: ParticipantPage;
  save: (path: string, payload: object) => Promise<unknown>;
}) {
  const [kind, setKind] = useState("spawn");
  const [id, setId] = useState("");
  const [group, setGroup] = useState(record.plan.groups[0]?.id || "");
  return (
    <details>
      <summary>Automatically link downstream fruiting records</summary>
      <p>
        Use recorded source relationships. Conflicting, mixed or incomplete
        ancestry requires review. This does not start a spawn-stage experiment.
      </p>
      <form
        className="experiment-form"
        onSubmit={async (e) => {
          e.preventDefault();
          await save("source-rules", {
            plan_revision: data.plan_revision,
            source_kind: kind,
            source_id: id,
            group_id: group,
            reason: "Confirm source assignment for downstream fruiting",
          });
        }}
      >
        <label>
          Source type
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="spawn">Spawn source</option>
            <option value="physical">Physical culture source</option>
            <option value="line">Exact culture line</option>
          </select>
        </label>
        <label>
          Permanent source ID
          <input required value={id} onChange={(e) => setId(e.target.value)} />
        </label>
        <label>
          Descendant group
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            {record.plan.groups.map((g) => (
              <option key={g.id} value={g.id!}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        <button>Confirm automatic association</button>
      </form>
      <ul>
        {data.rules.map((r) => (
          <li key={r.id}>
            {r.source_id} →{" "}
            {record.plan.groups.find((g) => g.id === r.group_id)?.name ||
              r.group_id}{" "}
            · plan {r.plan_revision}{" "}
            {r.active ? (
              <button
                onClick={() =>
                  save(`source-rules/${r.id}/stop`, {
                    reason: "Stop automatic source association",
                  })
                }
              >
                Stop linking {r.source_id}
              </button>
            ) : (
              "Stopped"
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function ExperimentParticipants({
  record,
  refresh,
}: {
  record: Experiment;
  refresh: () => void;
}) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState("existing");
  const state = useApi<ParticipantPage>(
    `experiments/${record.id}/participants?page=${page}&q=${encodeURIComponent(search)}`,
    true,
  );
  const lastRevision = useRef(record.revision);
  useEffect(() => {
    if (lastRevision.current !== record.revision) {
      lastRevision.current = record.revision;
      state.retry();
    }
  }, [record.revision, state.retry]);
  const command = useInventoryCommand("experiments");
  const [ownRevision, setOwnRevision] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const history = useApi<{
    items: {
      id: number;
      action: string;
      reason: string;
      recorded_at: string;
    }[];
    total: number;
  }>(
    `experiments/${record.id}/enrollment-history?page=${historyPage}&revision=${record.revision}`,
  );
  if (state.error)
    return <ErrorState error={state.error} retry={state.retry} />;
  if (!state.data) return <LoadingState />;
  const data = state.data;
  const writable =
    !record.archived && ["planned", "running"].includes(record.state);
  const reviewable = !record.archived;
  async function save(path: string, payload: object) {
    const result = await command.send(`${record.id}/${path}`, {
      expected_revision: Math.max(data.revision, ownRevision || 0),
      ...payload,
    });
    if (result) {
      setOwnRevision((result as { revision: number }).revision);
      state.retry();
      refresh();
    }
    return result;
  }
  return (
    <Panel title="Participants and groups" icon={FlaskConical}>
      <p>
        {data.counts.containers} containers · {data.counts.treatment_units}{" "}
        assigned treatment units · {data.counts.known_spawn_sources} known spawn
        sources.
      </p>
      <p>{data.unit_warning}</p>
      <p>
        Membership classification: {data.classification_summary || "uncertain"}
      </p>
      <p>
        {Object.entries(data.counts.classification_counts)
          .map(([key, value]) => `${key}: ${value}`)
          .join(" · ")}
      </p>
      {command.error && (
        <p role="alert">
          {command.error}{" "}
          <button
            onClick={() => {
              state.retry();
              refresh();
            }}
          >
            Reload participants
          </button>
        </p>
      )}
      <fieldset disabled={command.busy} className="participant-actions">
        <legend>Enrollment and review</legend>
        {data.items.length === 0 && <p>No participants yet.</p>}
        <ul>
          {data.items.map((p) => (
            <li key={p.id}>
              <Link to={`/culture-library/fruiting/${p.fruiting_id}`}>
                {p.fruiting_id}
              </Link>{" "}
              · {p.group_name} · {p.classification} ·{" "}
              {p.evidence.status.replaceAll("_", " ")}
              <p>
                Unit {p.unit_id} ({p.unit_kind}) · plan {p.plan_revision}.{" "}
                {p.flush_count} recorded flushes are repeated observations.
              </p>
              <p>
                Spawn: {p.sources.spawn_ids.join(", ") || "Unknown"}. Lines:{" "}
                {p.sources.line_ids.join(", ") || "Unknown"}.
              </p>
              {p.evidence.review_reason && <p>{p.evidence.review_reason}</p>}
              {reviewable && (
                <details>
                  <summary>Review {p.fruiting_id}</summary>
                  <ReviewForm
                    p={p}
                    record={record}
                    save={save}
                    revision={data.plan_revision}
                  />
                </details>
              )}
            </li>
          ))}
        </ul>
        {writable ? (
          record.category === "conditions" ? (
            <p>
              Condition participants must share an existing tent-trial unit.
              Trial setup and participant attribution will be available in 2H.3.
            </p>
          ) : (
            <>
              <div className="experiment-actions">
                <button
                  aria-pressed={mode === "existing"}
                  onClick={() => setMode("existing")}
                >
                  Link existing
                </button>
                <button
                  aria-pressed={mode === "create"}
                  onClick={() => setMode("create")}
                >
                  Create new
                </button>
              </div>
              <label>
                Search fruiting IDs
                <input
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(1);
                  }}
                />
              </label>
              {mode === "existing" ? (
                <Existing record={record} data={data} save={save} />
              ) : (
                <Creation record={record} data={data} save={save} />
              )}
              <SourceRules record={record} data={data} save={save} />
            </>
          )
        ) : (
          <p>Commit the plan and keep it unarchived to enroll containers.</p>
        )}
      </fieldset>
      <button disabled={page === 1} onClick={() => setPage(page - 1)}>
        Previous participants
      </button>
      <span> Page {page} </span>
      <button
        disabled={page * 50 >= Math.max(data.total, data.candidate_total)}
        onClick={() => setPage(page + 1)}
      >
        Next participants
      </button>
      <button
        aria-expanded={showHistory}
        onClick={() => setShowHistory(!showHistory)}
      >
        Enrollment history
      </button>
      {showHistory &&
        (history.error ? (
          <ErrorState error={history.error} retry={history.retry} />
        ) : !history.data ? (
          <LoadingState />
        ) : (
          <>
            <ul>
              {history.data.items.map((e) => (
                <li key={e.id}>
                  {e.action.replaceAll("_", " ")} · {e.reason} · {e.recorded_at}
                </li>
              ))}
            </ul>
            <button
              disabled={historyPage === 1}
              onClick={() => setHistoryPage(historyPage - 1)}
            >
              Previous enrollment history
            </button>
            <span> Page {historyPage} </span>
            <button
              disabled={historyPage * 50 >= history.data.total}
              onClick={() => setHistoryPage(historyPage + 1)}
            >
              Next enrollment history
            </button>
          </>
        ))}
    </Panel>
  );
}
