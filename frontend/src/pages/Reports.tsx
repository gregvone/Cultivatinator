import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { PageHeader, LoadingState, ErrorState } from "../components/UI";
import CollapsiblePanel from "../components/CollapsiblePanel";
import PerformanceBars from "../components/PerformanceBars";
import { useApi } from "../useApi";
import { groupNames, measure, periodBounds } from "../reportApi";
import type {
  Average,
  GroupBy,
  PerformanceReport,
  ReportGroup,
  ReportRecord,
} from "../reportApi";

function AverageCell({ value }: { value: Average }) {
  return (
    <>
      {measure(value.value, "days")}{" "}
      <small>
        n={value.sample_count}; missing {value.missing_count}
      </small>
    </>
  );
}
export function ReportRecordLinks({ records }: { records: ReportRecord[] }) {
  return (
    <ul className="report-records">
      {records.map((r) => (
        <li key={r.id}>
          <Link to={`/culture-library/fruiting/${r.id}`}>
            {r.label ? `${r.label} · ` : ""}
            {r.id}
            {r.name ? ` — ${r.name}` : ""}
          </Link>
          <span>
            {" "}
            · {r.outcome} · {r.outcome_date || "Date not recorded"}
            {r.archived ? " · Archived" : ""}
          </span>
          {r.outcome !== "active" && (
            <p>
              Container known wet: {measure(r.known_wet_grams)} ·{" "}
              {r.wet_measurement_count}/{r.harvest_count} harvest weights
              measured
              {r.complete_wet
                ? " (complete)"
                : " (incomplete / no measurements)"}
              .
            </p>
          )}
          {r.spawn_ids.length ? (
            <p>
              Spawn sources:{" "}
              {r.spawn_ids.map((s, i) => (
                <span key={s}>
                  {i > 0 && ", "}
                  <Link to={`/culture-library/spawn/${s}`}>{s}</Link>
                </span>
              ))}
            </p>
          ) : (
            <p>Source spawn not recorded.</p>
          )}
          <p>
            Strains: {r.strain_names.join(", ") || "Unknown"} (
            {r.strain_identity}) · Culture lines:{" "}
            {r.line_ids.map((line, i) => (
              <span key={line}>
                {i > 0 && ", "}
                <Link to={`/culture-library/lines/${line}`}>
                  {r.line_names[i] || line} · {line}
                </Link>
              </span>
            ))}
            {!r.line_ids.length && "Unknown"} ({r.line_identity}).
          </p>
        </li>
      ))}
    </ul>
  );
}
function RevisionDetails({
  group,
  records,
}: {
  group: ReportGroup;
  records: ReportRecord[];
}) {
  if (!group.revisions.length) return null;
  return (
    <CollapsiblePanel
      title={`${group.revisions.length} saved recipe revision(s)`}
      level={3}
    >
      {group.revisions.map((rev) => (
        <CollapsiblePanel
          key={rev.revision ?? "unknown"}
          title={`Revision ${rev.revision ?? "not recorded"} — ${rev.name}`}
          level={4}
          summary={`${measure(rev.stats.average_wet_grams)} average · ${rev.stats.qualifying_containers} qualifying containers`}
        >
          <p>Immutable grow snapshot · historical formulation.</p>
          <p>
            Dry average: {measure(rev.stats.average_dry_grams.value)} · n=
            {rev.stats.average_dry_grams.sample_count}.
          </p>
          {Array.isArray(rev.snapshot.ingredients) && (
            <ul>
              {rev.snapshot.ingredients.map((ingredient, i) => (
                <li key={i}>
                  {ingredient.name ||
                    ingredient.item_id ||
                    "Unnamed ingredient"}
                  : {ingredient.quantity} {ingredient.unit}
                </li>
              ))}
            </ul>
          )}
          <p className="preserve-lines">
            {rev.snapshot.instructions || "Instructions not recorded"}
          </p>
          {rev.snapshot.notes && <p>{rev.snapshot.notes}</p>}
          <ReportRecordLinks
            records={records.filter((r) => rev.record_ids.includes(r.id))}
          />
        </CollapsiblePanel>
      ))}
    </CollapsiblePanel>
  );
}
function ComparisonData({ data }: { data: PerformanceReport }) {
  return (
    <CollapsiblePanel
      title="Comparison data & grow records"
      summary="Accessible table, source relationships and saved revisions"
    >
      <div className="table-scroll">
        <table>
          <caption>
            {groupNames[data.group_by]} comparisons · {data.period.label}
          </caption>
          <thead>
            <tr>
              <th scope="col">Group</th>
              <th scope="col">Average completed wet</th>
              <th scope="col">Known wet · terminal grows</th>
              <th scope="col">Qualifying containers / sources</th>
              <th scope="col">Excluded completed containers</th>
              <th scope="col">Outcomes</th>
              {data.group_by === "recipe" && (
                <th scope="col">Average completed dry</th>
              )}
              <th scope="col">Verify records</th>
            </tr>
          </thead>
          <tbody>
            {data.groups.map((g) => (
              <tr key={g.key}>
                <th scope="row">
                  {g.name}
                  <small>
                    {g.ranked
                      ? g.preliminary
                        ? "Preliminary — fewer than 3 containers"
                        : "Measured comparison"
                      : "Not ranked — unknown/mixed identity or insufficient measured data"}
                  </small>
                </th>
                <td>
                  {measure(g.stats.average_wet_grams)}
                  <small>n={g.stats.qualifying_containers}</small>
                </td>
                <td>
                  {measure(g.stats.total_known_wet_grams)}
                  <small>Includes known partial/failed harvests</small>
                </td>
                <td>
                  {g.stats.qualifying_containers} containers ·{" "}
                  {g.stats.distinct_spawn_sources} known spawn sources
                  <small>
                    {g.stats.containers_without_known_spawn} qualifying
                    containers without a known spawn source
                  </small>
                </td>
                <td>{g.stats.excluded_incomplete_wet}</td>
                <td>
                  {g.stats.completed} completed · {g.stats.failed} failed
                </td>
                {data.group_by === "recipe" && (
                  <td>
                    {measure(g.stats.average_dry_grams.value)}
                    <small>n={g.stats.average_dry_grams.sample_count}</small>
                  </td>
                )}
                <td>
                  <CollapsiblePanel
                    title={`${g.record_ids.length} grow record(s)`}
                    level={3}
                  >
                    <ReportRecordLinks
                      records={data.records.filter((r) =>
                        g.record_ids.includes(r.id),
                      )}
                    />
                  </CollapsiblePanel>
                  <RevisionDetails group={g} records={data.records} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsiblePanel>
  );
}
export default function Reports() {
  const [identity, setIdentity] = useState("");
  const [range, setRange] = useState("all");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [group, setGroup] = useState<GroupBy>("strain");
  const [path, setPath] = useState("reports/performance?group_by=strain");
  const [validation, setValidation] = useState("");
  const { data, error, retry } = useApi<PerformanceReport>(path);
  // Keep filter choices available during a refresh without retaining stale results.
  const [options, setOptions] = useState<PerformanceReport["options"]>({
    strains: [],
    species: [],
  });
  const currentOptions = data?.options || options;
  function apply(e: FormEvent) {
    e.preventDefault();
    if (range === "custom" && (!start || !end || start > end)) {
      setValidation("Choose both dates, with the start on or before the end.");
      return;
    }
    setValidation("");
    if (data) setOptions(data.options);
    const query = new URLSearchParams({ group_by: group });
    if (identity.startsWith("strain:"))
      query.set("strain_id", identity.slice(7));
    if (identity.startsWith("species:"))
      query.set("species", identity.slice(8));
    for (const [key, value] of Object.entries(periodBounds(range, start, end)))
      if (value) query.set(key, value);
    setPath(`reports/performance?${query}`);
    if (path === `reports/performance?${query}`) retry();
  }
  const ranked = useMemo(
    () => data?.groups.filter((g) => g.ranked) || [],
    [data],
  );
  return (
    <>
      <PageHeader
        title="Reports"
        description="Measured cultivation performance, with sample sizes and links to the original grows."
      />
      <form className="report-filters panel" onSubmit={apply}>
        <label className="field">
          <span>Species / Strain</span>
          <select
            aria-label="Species / Strain"
            value={identity}
            onChange={(e) => setIdentity(e.target.value)}
          >
            <option value="">All species and strains</option>
            <optgroup label="Species · recorded scientific names">
              {currentOptions.species.map((s) => (
                <option key={s} value={`species:${s}`}>
                  {s}
                </option>
              ))}
            </optgroup>
            <optgroup label="Tracked strains">
              {currentOptions.strains.map((s) => (
                <option key={s.id} value={`strain:${s.id}`}>
                  {s.name}
                </option>
              ))}
            </optgroup>
          </select>
        </label>
        <label className="field">
          <span>Time Range</span>
          <select
            aria-label="Time Range"
            value={range}
            onChange={(e) => setRange(e.target.value)}
          >
            <option value="all">All time</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="custom">Custom dates</option>
          </select>
        </label>
        <label className="field">
          <span>Group Results By</span>
          <select
            aria-label="Group Results By"
            value={group}
            onChange={(e) => setGroup(e.target.value as GroupBy)}
          >
            {Object.entries(groupNames).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {range === "custom" && (
          <>
            <label className="field">
              <span>Start date</span>
              <input
                type="date"
                required
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label className="field">
              <span>End date</span>
              <input
                type="date"
                required
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
          </>
        )}
        <button className="primary" type="submit">
          Apply filters
        </button>
        {validation && <p role="alert">{validation}</p>}
      </form>
      {error ? (
        <ErrorState error={error} retry={retry} />
      ) : !data ? (
        <LoadingState />
      ) : (
        <>
          <p className="report-period">
            <strong>Reporting period: {data.period.label}</strong> ·{" "}
            {data.summary.terminal_count} eligible terminal records · grouped by{" "}
            {groupNames[data.group_by]}.
          </p>
          <p className="muted">
            Completion dates select completed grows; failure dates select failed
            grows. {data.undated_terminal_excluded} undated terminal records
            excluded · {data.terminal_containers_outside_period} outside this
            period.
          </p>
          <div className="summary-grid report-summary">
            <section className="summary-card">
              <h2>Average completed-container wet yield</h2>
              <strong>{measure(data.summary.average_wet_grams)}</strong>
              <p>
                {data.summary.qualifying_containers} fully measured containers ·{" "}
                {data.summary.excluded_incomplete_wet} completed containers
                excluded for incomplete/no wet measurements
              </p>
            </section>
            <section className="summary-card">
              <h2>Total known wet harvest weight</h2>
              <strong>{measure(data.summary.total_known_wet_grams)}</strong>
              <p>
                {data.summary.wet_measurement_count}/
                {data.summary.harvest_count} harvest entries measured · includes
                known partial and failed terminal harvests
              </p>
            </section>
            <section className="summary-card">
              <h2>Completed fruiting containers</h2>
              <strong>{data.summary.completed}</strong>
              <p>
                {data.summary.qualifying_containers} qualify for the primary
                average
              </p>
            </section>
            <section className="summary-card">
              <h2>Failed fruiting containers</h2>
              <strong>{data.summary.failed}</strong>
              <p>
                Terminal failure rate:{" "}
                {measure(data.summary.failure_rate_percent, "%")} ·{" "}
                {data.summary.failed}/{data.summary.terminal_count} outcomes
              </p>
            </section>
          </div>
          <p className="report-coverage">
            Primary metric: one total wet yield per fully measured completed FR,
            across all harvests and flushes.{" "}
            {data.summary.qualifying_containers} qualifying containers share{" "}
            {data.summary.distinct_spawn_sources} distinct known spawn sources;{" "}
            {data.summary.containers_without_known_spawn} have no known spawn
            source. Shared sources are not independent genetic trials.
          </p>
          {!data.summary.qualifying_containers && (
            <p className="feedback" role="status">
              Insufficient measured completed-grow data for a useful yield
              comparison. Missing measurements stay Unknown.
            </p>
          )}
          <section className="panel workflow-source">
            <h2>{groupNames[data.group_by]} performance</h2>
            <PerformanceBars
              title="Average measured wet yield per completed container"
              rows={ranked.map((g) => ({
                id: g.key,
                name: g.name,
                value: g.stats.average_wet_grams,
                samples: g.stats.qualifying_containers,
                preliminary: g.preliminary,
                detail: `Known wet ${measure(g.stats.total_known_wet_grams)} · ${g.stats.distinct_spawn_sources} known spawn sources · ${g.stats.excluded_incomplete_wet} completed containers excluded`,
              }))}
            />
            <p className="muted">
              Groups with fewer than three qualifying containers are
              Preliminary. Different genetics and conditions may contribute to
              recipe differences; these are observational comparisons.
            </p>
            {data.groups.some((g) => !g.ranked) && (
              <p>
                Some groups are not ranked because identity is
                unknown/mixed/partial or qualifying measurements are
                unavailable. They remain in the comparison data.
              </p>
            )}
            <ComparisonData data={data} />
          </section>
          <CollapsiblePanel
            title="Growth speed"
            summary="Completed grows · recorded dates only"
          >
            <div className="table-scroll">
              <table>
                <caption>
                  Growth speed by {groupNames[data.group_by].toLowerCase()}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Group</th>
                    <th scope="col">Spawning to first pinning</th>
                    <th scope="col">Spawning to first harvest</th>
                    <th scope="col">Completed cycle duration</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">All eligible completed grows</th>
                    <td>
                      <AverageCell value={data.summary.days_to_first_pinning} />
                    </td>
                    <td>
                      <AverageCell value={data.summary.days_to_first_harvest} />
                    </td>
                    <td>
                      <AverageCell value={data.summary.cycle_days} />
                    </td>
                  </tr>
                  {data.groups.map((g) => (
                    <tr key={g.key}>
                      <th scope="row">{g.name}</th>
                      <td>
                        <AverageCell value={g.stats.days_to_first_pinning} />
                      </td>
                      <td>
                        <AverageCell value={g.stats.days_to_first_harvest} />
                      </td>
                      <td>
                        <AverageCell value={g.stats.cycle_days} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Dates that are missing or chronologically invalid do not
              contribute to averages. No historical dates are inferred.
            </p>
          </CollapsiblePanel>
          <CollapsiblePanel
            title="Flush performance"
            summary="Completed containers · one observation per recorded flush"
          >
            <PerformanceBars
              title="Average fully measured wet yield per flush"
              rows={data.flushes.map((f) => ({
                id: String(f.number),
                name: `Flush ${f.number}`,
                value: f.average_wet_grams,
                samples: f.qualifying_containers,
                detail: `${f.containers_reached} containers reached this flush · ${f.excluded_incomplete_wet} excluded for incomplete/no wet measurements`,
              }))}
            />
            <p>
              Fewer containers may reach later flushes. No yield is inserted for
              an unrecorded or unmeasured flush.
            </p>
            <div className="table-scroll">
              <table>
                <caption>Flush measurement coverage</caption>
                <thead>
                  <tr>
                    <th scope="col">Flush</th>
                    <th scope="col">Average wet</th>
                    <th scope="col">Reached / fully measured</th>
                    <th scope="col">Known wet</th>
                    <th scope="col">Grow records</th>
                  </tr>
                </thead>
                <tbody>
                  {data.flushes.map((f) => (
                    <tr key={f.number}>
                      <th scope="row">Flush {f.number}</th>
                      <td>
                        {measure(f.average_wet_grams)} · n=
                        {f.qualifying_containers}
                      </td>
                      <td>
                        {f.containers_reached} / {f.qualifying_containers}
                      </td>
                      <td>{measure(f.total_known_wet_grams)}</td>
                      <td>
                        <CollapsiblePanel
                          title={`Flush ${f.number} records`}
                          level={3}
                        >
                          <p>
                            Fully measured contributors:{" "}
                            {f.qualifying_record_ids.join(", ") || "None"}.
                          </p>
                          <ReportRecordLinks
                            records={data.records.filter((r) =>
                              f.record_ids.includes(r.id),
                            )}
                          />
                        </CollapsiblePanel>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CollapsiblePanel>
          <CollapsiblePanel
            title="Outcomes & active grows"
            summary={`${data.summary.completed} completed · ${data.summary.failed} failed · ${data.active_records.length} active now`}
          >
            <p>
              Terminal failure rate: {data.summary.failed} / (
              {data.summary.completed} completed + {data.summary.failed} failed)
              = {measure(data.summary.failure_rate_percent, "%")}. Failed grows
              retain their recorded harvests.
            </p>
            <p>
              Active grows now: {data.active_records.length}. These follow the
              species/strain filter but are not date-filtered, averaged in
              completed yield or included in terminal outcome rates.
            </p>
            <ReportRecordLinks records={data.active_records} />
          </CollapsiblePanel>
          <CollapsiblePanel title="Data coverage & calculation rules">
            <p>
              Known completed wet:{" "}
              {measure(data.summary.completed_known_wet_grams)} · known failed
              wet: {measure(data.summary.failed_known_wet_grams)}. Active
              weights are excluded from these totals. Recorded zero is valid;
              absence of harvests is not a measured zero.
            </p>
            <p>
              Primary averages exclude completed containers unless at least one
              harvest exists and every harvest wet weight is recorded. Flush
              averages apply the same coverage rule within each flush. Dry
              averages require all dry harvest weights and use a separate
              sample; dry is never substituted for wet.
            </p>
            <p>
              Strain filters require a fully identified single strain. Species
              filters require every contributing source to have the same
              recorded scientific name. Mixed/partial/unknown identities remain
              unranked in genetic comparisons. A documented culture line can be
              compared even if its strain name is unknown.
            </p>
            <p>
              {data.legacy_containers} eligible terminal records have legacy
              registration history. Missing operational history, dates and
              recipe snapshots remain unknown. Archived grows are included;
              physical label reuse never combines permanent FR records.
            </p>
            <p>
              Recipe results group by original identity and preserve saved
              revision snapshots. Growth-speed samples include only completed
              records with the required recorded dates, regardless of wet-weight
              coverage. No potency ranking, efficiency estimate or
              recommendation is calculated.
            </p>
          </CollapsiblePanel>
        </>
      )}
    </>
  );
}
