import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FlaskConical } from "lucide-react";
import { PageHeader, Panel, LoadingState, ErrorState } from "../components/UI";
import { observationTime } from "../environmentApi";
import { useApi } from "../useApi";
import { useInventoryCommand } from "../preparationApi";
import { outcomes, blankPlan } from "../experimentApi";
import type {
  Experiment,
  ExperimentPlan,
  ExperimentPage,
  ExperimentHistory,
  Outcome,
} from "../experimentApi";

function Setup({
  initial,
  record,
  onSaved,
}: {
  initial: ExperimentPlan;
  record?: Experiment;
  onSaved: (e: Experiment) => void;
}) {
  const [plan, setPlan] = useState(initial);
  const [step, setStep] = useState(0);
  const [reason, setReason] = useState("");
  const command = useInventoryCommand("experiments");
  function update<K extends keyof ExperimentPlan>(
    key: K,
    value: ExperimentPlan[K],
  ) {
    setPlan((p) => ({
      ...p,
      [key]: value,
      ...(key === "primary_outcome"
        ? {
            secondary_outcomes: p.secondary_outcomes.filter((v) => v !== value),
          }
        : {}),
    }));
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (step < 2) {
      setStep(step + 1);
      return;
    }
    const result = await command.send<Experiment>(
      record ? `${record.id}/plan-revisions` : "",
      {
        plan,
        ...(record ? { expected_revision: record.revision, reason } : {}),
      },
    );
    if (result) onSaved(result);
  }
  return (
    <form onSubmit={submit} className="experiment-form">
      <p role="status">
        Step {step + 1} of 3:{" "}
        {["Question and outcome", "Groups", "Review and save"][step]}
      </p>
      <p>
        Fruiting experiments. Container enrollment, environmental trials and
        results arrive in later phases.
      </p>
      {step === 0 && (
        <>
          <label>
            Experiment title
            <input
              required
              maxLength={200}
              value={plan.title}
              onChange={(e) => update("title", e.target.value)}
            />
          </label>
          <label>
            Experiment category
            <select
              disabled={!!record}
              value={plan.category}
              onChange={(e) =>
                update("category", e.target.value as ExperimentPlan["category"])
              }
            >
              <option value="substrate">Substrate</option>
              <option value="genetics">Genetics</option>
              <option value="conditions">Growing conditions</option>
            </select>
          </label>
          <label>
            Primary variable
            <input
              required
              maxLength={200}
              value={plan.primary_variable}
              onChange={(e) => update("primary_variable", e.target.value)}
            />
          </label>
          <label>
            Primary outcome
            <select
              value={plan.primary_outcome}
              onChange={(e) =>
                update("primary_outcome", e.target.value as Outcome)
              }
            >
              {Object.entries(outcomes).map(([key, name]) => (
                <option key={key} value={key}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Hypothesis (optional)
            <textarea
              maxLength={10000}
              value={plan.hypotheses || ""}
              onChange={(e) => update("hypotheses", e.target.value)}
            />
          </label>
        </>
      )}
      {step === 1 && (
        <>
          {plan.groups.map((g, i) => (
            <fieldset key={g.id || i}>
              <legend>Group {i + 1}</legend>
              <label>
                Group {i + 1} name
                <input
                  required
                  maxLength={200}
                  value={g.name}
                  onChange={(e) =>
                    update(
                      "groups",
                      plan.groups.map((v, j) =>
                        j === i ? { ...v, name: e.target.value } : v,
                      ),
                    )
                  }
                />
              </label>
              <label>
                Group {i + 1} treatment
                <input
                  required
                  maxLength={200}
                  value={g.treatment}
                  onChange={(e) =>
                    update(
                      "groups",
                      plan.groups.map((v, j) =>
                        j === i ? { ...v, treatment: e.target.value } : v,
                      ),
                    )
                  }
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={g.control}
                  onChange={(e) =>
                    update(
                      "groups",
                      plan.groups.map((v, j) => ({
                        ...v,
                        control: j === i ? e.target.checked : false,
                      })),
                    )
                  }
                />
                Control group {i + 1}
              </label>
              {plan.groups.length > 2 && (
                <button
                  type="button"
                  onClick={() =>
                    update(
                      "groups",
                      plan.groups.filter((_, j) => j !== i),
                    )
                  }
                >
                  Remove group {i + 1}
                </button>
              )}
            </fieldset>
          ))}
          {plan.groups.length < 20 && (
            <button
              type="button"
              onClick={() =>
                update("groups", [
                  ...plan.groups,
                  { name: "", treatment: "", control: false },
                ])
              }
            >
              Add group
            </button>
          )}
        </>
      )}
      {step === 2 && (
        <>
          <h3>{plan.title}</h3>
          <p>
            {plan.category}: {plan.primary_variable} →{" "}
            {outcomes[plan.primary_outcome]}
          </p>
          <ul>
            {plan.groups.map((g, i) => (
              <li key={i}>
                {g.name}: {g.treatment}
                {g.control ? " (control)" : ""}
              </li>
            ))}
          </ul>
          <details>
            <summary>Advanced scientific settings (optional)</summary>
            <p>
              These settings document intent. A schedule alone does not prove
              that treatment units were allocated.
            </p>
            {(
              [
                ["allocation_schedule", "Allocation schedule"],
                ["blocking", "Shared sources and blocking"],
                ["eligibility", "Eligibility"],
                ["exclusions", "Exclusions"],
                ["observation_window", "Observation window"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <textarea
                  maxLength={10000}
                  value={plan.advanced[key] || ""}
                  onChange={(e) =>
                    update("advanced", {
                      ...plan.advanced,
                      [key]: e.target.value,
                    })
                  }
                />
              </label>
            ))}
            <label>
              Minimum readings
              <input
                type="number"
                min={1}
                max={1000000}
                value={plan.advanced.minimum_readings ?? ""}
                onChange={(e) =>
                  update("advanced", {
                    ...plan.advanced,
                    minimum_readings: e.target.value
                      ? Number(e.target.value)
                      : null,
                  })
                }
              />
            </label>
            <label>
              Maximum gap (hours)
              <input
                type="number"
                min={0.001}
                max={87600}
                step="any"
                value={plan.advanced.maximum_gap_hours ?? ""}
                onChange={(e) =>
                  update("advanced", {
                    ...plan.advanced,
                    maximum_gap_hours: e.target.value
                      ? Number(e.target.value)
                      : null,
                  })
                }
              />
            </label>
            <fieldset>
              <legend>Secondary outcomes</legend>
              {Object.entries(outcomes)
                .filter(([key]) => key !== plan.primary_outcome)
                .map(([key, name]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={plan.secondary_outcomes.includes(key as Outcome)}
                      onChange={(e) =>
                        update(
                          "secondary_outcomes",
                          e.target.checked
                            ? [...plan.secondary_outcomes, key as Outcome]
                            : plan.secondary_outcomes.filter((v) => v !== key),
                        )
                      }
                    />
                    {name}
                  </label>
                ))}
            </fieldset>
          </details>
          {record && (
            <label>
              Revision reason
              <input
                required
                maxLength={200}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
          )}
          {record?.state === "running" && (
            <p>
              Saving creates a visible post-start amendment; original start
              evidence remains unchanged.
            </p>
          )}
        </>
      )}
      {command.error && (
        <p role="alert">
          {command.error} Your entries are retained. Reload the experiment if
          its revision changed.
        </p>
      )}
      <div className="experiment-actions">
        {step > 0 && (
          <button
            type="button"
            disabled={command.busy}
            onClick={() => setStep(step - 1)}
          >
            Back
          </button>
        )}
        <button disabled={command.busy} type="submit">
          {command.busy
            ? "Saving…"
            : step < 2
              ? "Continue"
              : record
                ? "Save revision"
                : "Save draft"}
        </button>
      </div>
    </form>
  );
}

export default function Experiments() {
  const [page, setPage] = useState(1);
  const state = useApi<ExperimentPage>(`experiments?page=${page}`);
  return (
    <>
      <PageHeader
        title="Experiments"
        description="Plan fruiting comparisons and preserve the question, treatments and original plan."
      />
      <Link className="button" to="/experiments/new">
        New experiment
      </Link>
      {state.error ? (
        <ErrorState error={state.error} retry={state.retry} />
      ) : !state.data ? (
        <LoadingState />
      ) : (
        <Panel title="Experiment plans" icon={FlaskConical}>
          {!state.data.items.length && <p>No experiments yet.</p>}
          <ul>
            {state.data.items.map((e) => (
              <li key={e.id}>
                <Link to={`/experiments/${e.id}`}>{e.plan.title}</Link> ·{" "}
                {e.state}
                {e.archived ? " · archived" : ""} · {e.category}
              </li>
            ))}
          </ul>
          <button disabled={page === 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span> Page {page} </span>
          <button
            disabled={page * 50 >= state.data.total}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </Panel>
      )}
    </>
  );
}

export function NewExperiment() {
  const navigate = useNavigate();
  return (
    <>
      <PageHeader
        title="New experiment"
        description="A guided plan for substrate, genetics or growing conditions."
      />
      <Panel title="Experiment setup" icon={FlaskConical}>
        <Setup
          initial={blankPlan()}
          onSaved={(e) => navigate(`/experiments/${e.id}`)}
        />
      </Panel>
    </>
  );
}

function PlanSummary({ plan }: { plan: ExperimentPlan }) {
  const labels: Record<string, string> = {
    allocation_schedule: "Allocation schedule",
    blocking: "Shared sources and blocking",
    eligibility: "Eligibility",
    exclusions: "Exclusions",
    observation_window: "Observation window",
    minimum_readings: "Minimum readings",
    maximum_gap_hours: "Maximum gap (hours)",
  };
  return (
    <div className="experiment-snapshot">
      <h4>{plan.title}</h4>
      <p>
        {plan.category} · {plan.primary_variable} ·{" "}
        {outcomes[plan.primary_outcome]}
      </p>
      {plan.hypotheses && <p>Hypothesis: {plan.hypotheses}</p>}
      <ul>
        {plan.groups.map((g, i) => (
          <li key={g.id || i}>
            {g.name}: {g.treatment}
            {g.control ? " (control)" : ""}
          </li>
        ))}
      </ul>
      {!!plan.secondary_outcomes.length && (
        <p>
          Secondary outcomes:{" "}
          {plan.secondary_outcomes.map((o) => outcomes[o]).join(", ")}
        </p>
      )}
      <dl>
        {Object.entries(plan.advanced)
          .filter(([, v]) => v !== null && v !== "")
          .map(([key, value]) => (
            <div key={key}>
              <dt>{labels[key]}</dt>
              <dd>{value}</dd>
            </div>
          ))}
      </dl>
    </div>
  );
}

function History({ code, revision }: { code: string; revision: number }) {
  const [page, setPage] = useState(1);
  const state = useApi<ExperimentHistory>(
    `experiments/${code}/history?page=${page}&revision=${revision}`,
  );
  if (state.error)
    return <ErrorState error={state.error} retry={state.retry} />;
  if (!state.data) return <LoadingState />;
  return (
    <>
      <h3>Plan revisions</h3>
      {state.data.plans.map((p) => (
        <details key={p.revision}>
          <summary>
            Plan {p.revision} · {p.committed_at ? "Committed" : "Draft"} ·{" "}
            {p.reason}
          </summary>
          <p>{p.recorded_at}</p>
          <PlanSummary plan={p.snapshot} />
        </details>
      ))}
      <h3>Audit history</h3>
      {state.data.audits.map((a) => (
        <details key={a.id}>
          <summary>
            {a.action} · {a.reason} · {a.recorded_at}
          </summary>
          {a.before && (
            <>
              <h4>Before</h4>
              <p>
                {a.before.state}
                {a.before.archived ? " · archived" : ""} · Revision{" "}
                {a.before.revision} · {a.before.classification}
              </p>
              <PlanSummary plan={a.before.plan} />
            </>
          )}
          <h4>After</h4>
          <p>
            {a.after.state}
            {a.after.archived ? " · archived" : ""} · Revision{" "}
            {a.after.revision} · {a.after.classification}
          </p>
          <PlanSummary plan={a.after.plan} />
        </details>
      ))}
      <button disabled={page === 1} onClick={() => setPage(page - 1)}>
        Previous history
      </button>
      <span> Page {page} </span>
      <button
        disabled={
          page * 50 >= Math.max(state.data.plan_total, state.data.audit_total)
        }
        onClick={() => setPage(page + 1)}
      >
        Next history
      </button>
    </>
  );
}

function Detail({
  record,
  refresh,
}: {
  record: Experiment;
  refresh: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [reason, setReason] = useState("");
  const [timing, setTiming] = useState("");
  const [dateOnly, setDateOnly] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const command = useInventoryCommand("experiments");
  const [timingError, setTimingError] = useState("");
  async function act(action: string) {
    setTimingError("");
    let treatment: { treatment_date?: string; treatment_start?: string } = {};
    if (action === "start") {
      if (!timing) return;
      if (dateOnly) treatment = { treatment_date: timing };
      else {
        try {
          treatment = { treatment_start: observationTime(timing) };
        } catch (error) {
          setTimingError(
            error instanceof Error ? error.message : "Invalid treatment time",
          );
          return;
        }
      }
    }
    const result = await command.send<Experiment>(`${record.id}/actions`, {
      expected_revision: record.revision,
      action,
      reason,
      ...treatment,
    });
    if (result) {
      command.reset();
      setReason("");
      refresh();
    }
  }
  const allowed = record.archived
    ? ["restore"]
    : [
        ...(record.state === "draft"
          ? ["plan"]
          : record.state === "planned"
            ? ["start"]
            : record.state === "running"
              ? ["complete"]
              : []),
        ...(["draft", "planned", "running"].includes(record.state)
          ? ["cancel"]
          : []),
        "archive",
      ];
  return (
    <>
      <PageHeader
        title={record.plan.title}
        description={`${record.id} · ${record.category} · ${record.state}${record.archived ? " · archived" : ""}`}
      />
      <Panel title="Plan and treatment timing" icon={FlaskConical}>
        <p>
          Primary variable: {record.plan.primary_variable}. Outcome:{" "}
          {outcomes[record.plan.primary_outcome]}.
        </p>
        <p>
          Classification: <strong>{record.classification}</strong>
          {record.treatment_start
            ? ` · Treatment began ${record.treatment_start}`
            : " · Treatment has not been started"}
        </p>
        <p>
          {record.classification_basis} Container enrollment and concrete
          allocation workflows are deferred; a plan alone cannot establish
          prospective participation.
        </p>
        <p>
          Several containers sharing a tent treatment and several flushes from
          one container do not establish independent trials.
        </p>
        {record.plan.hypotheses && <p>Hypothesis: {record.plan.hypotheses}</p>}
        <ul>
          {record.plan.groups.map((g) => (
            <li key={g.id}>
              {g.name}: {g.treatment}
              {g.control ? " (control)" : ""}
            </li>
          ))}
        </ul>
        {record.post_start_amendment && (
          <p role="status">
            Post-start amendment. Start classification retains its original
            evidence.
          </p>
        )}
        {!record.archived &&
          !["completed", "cancelled"].includes(record.state) && (
            <button onClick={() => setEditing(!editing)}>
              {editing ? "Close editor" : "Edit plan"}
            </button>
          )}
        {editing && (
          <Setup
            key={record.revision}
            record={record}
            initial={record.plan}
            onSaved={() => {
              setEditing(false);
              refresh();
            }}
          />
        )}
        <form className="experiment-form" onSubmit={(e) => e.preventDefault()}>
          <label>
            Action reason
            <input
              maxLength={200}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          {record.state === "planned" && !record.archived && (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={dateOnly}
                  onChange={(e) => {
                    setDateOnly(e.target.checked);
                    setTiming("");
                  }}
                />
                Only the treatment calendar date is known
              </label>
              <label>
                Actual treatment start ({dateOnly ? "date" : "local time"})
                <input
                  type={dateOnly ? "date" : "datetime-local"}
                  value={timing}
                  onChange={(e) => setTiming(e.target.value)}
                />
              </label>
              <p>
                Start records an actual treatment. Unknown or ambiguous timing
                remains uncertain. Backdating cannot create prospective
                evidence.
              </p>
            </>
          )}
          {timingError && <p role="alert">{timingError}</p>}
          {command.error && (
            <p role="alert">
              {command.error}{" "}
              <button type="button" onClick={refresh}>
                Reload experiment
              </button>
            </p>
          )}
          <div className="experiment-actions">
            {allowed.map((action) => (
              <button
                type="button"
                key={action}
                disabled={
                  command.busy ||
                  !reason.trim() ||
                  (action === "start" && !timing)
                }
                onClick={() => act(action)}
              >
                {
                  (
                    {
                      plan: "Commit plan",
                      start: "Start experiment",
                      complete: "Complete experiment",
                      cancel: "Cancel experiment",
                      archive: "Archive experiment",
                      restore: "Restore experiment",
                    } as Record<string, string>
                  )[action]
                }
              </button>
            ))}
          </div>
        </form>
      </Panel>
      <button
        onClick={() => setShowHistory(!showHistory)}
        aria-expanded={showHistory}
      >
        Plan and audit history
      </button>
      {showHistory && (
        <Panel title="Original plans and revisions" icon={FlaskConical}>
          <History code={record.id} revision={record.revision} />
        </Panel>
      )}
      <Link to="/experiments">All experiments</Link>
    </>
  );
}

export function ExperimentDetail() {
  const { code } = useParams();
  const state = useApi<Experiment>(`experiments/${code}`);
  if (state.error)
    return <ErrorState error={state.error} retry={state.retry} />;
  if (!state.data) return <LoadingState />;
  return (
    <Detail key={state.data.id} record={state.data} refresh={state.retry} />
  );
}
