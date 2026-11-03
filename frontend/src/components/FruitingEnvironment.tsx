import CollapsiblePanel from "./CollapsiblePanel";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Field } from "../pages/LibraryForms";
import { useInventoryCommand } from "../preparationApi";
import { fruitingApi } from "../fruitingApi";
import type { Environment } from "../fruitingApi";
export type EnvironmentValues = Record<keyof Environment, string>;
export const environmentValues = (
  value?: Environment | null,
): EnvironmentValues => ({
  tent_name: value?.tent_name || "",
  temperature: value?.temperature || "",
  temperature_unit: value?.temperature_unit || "",
  humidity: value?.humidity || "",
  humidifier: value?.humidifier || "",
  fae: value?.fae || "",
  notes: value?.notes || "",
});
export const environmentPayload = (value: EnvironmentValues) =>
  Object.fromEntries(
    Object.entries(value).map(([key, text]) => [key, text.trim() || null]),
  );
export function EnvironmentFields({
  value,
  onChange,
}: {
  value: EnvironmentValues;
  onChange: (v: EnvironmentValues) => void;
}) {
  return (
    <>
      {Object.entries({
        tent_name: "Tent name",
        temperature: "Target temperature",
        temperature_unit: "Temperature unit",
        humidity: "Target relative humidity (%)",
        humidifier: "Humidifier setting / notes",
        fae: "FAE fan setting / schedule",
        notes: "Environment notes",
      }).map(([name, label]) => (
        <Field
          key={name}
          name={name}
          label={label}
          values={value}
          set={(key, text) => onChange({ ...value, [key]: text })}
          type={
            name === "temperature" || name === "humidity"
              ? "number"
              : name === "notes" || name === "fae" || name === "humidifier"
                ? "textarea"
                : "text"
          }
          options={
            name === "temperature_unit"
              ? { "": "Not specified", C: "°C", F: "°F" }
              : undefined
          }
        />
      ))}
    </>
  );
}
export function EnvironmentSnapshot({ value }: { value: Environment | null }) {
  return value ? (
    <dl className="info-list">
      {Object.entries({
        Tent: value.tent_name,
        "Target temperature":
          value.temperature != null
            ? `${value.temperature} °${value.temperature_unit}`
            : null,
        "Target humidity": value.humidity != null ? `${value.humidity}%` : null,
        Humidifier: value.humidifier,
        FAE: value.fae,
        Notes: value.notes,
      }).map(([key, text]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{text || "Not recorded"}</dd>
        </div>
      ))}
    </dl>
  ) : (
    <p>Environment not recorded.</p>
  );
}
export default function FruitingEnvironmentSettings() {
  const [value, setValue] = useState(environmentValues());
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [saved, setSaved] = useState(false);
  const command = useInventoryCommand("fruiting");
  useEffect(() => {
    let live = true;
    fruitingApi<{ revision: number; environment: Environment | null }>(
      "environment",
    )
      .then((v) => {
        if (live) {
          setValue(environmentValues(v.environment));
          setRevision(v.revision);
          setLoaded(true);
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
  async function save(e: FormEvent) {
    e.preventDefault();
    const result = await command.send<{ revision: number }>("environment", {
      expected_revision: revision,
      environment: environmentPayload(value),
    });
    if (result) {
      setRevision(result.revision);
      setSaved(true);
      command.reset();
    }
  }
  return (
    <section className="panel workflow-source">
      <h2>Fruiting Environment</h2>
      <p>
        One optional tent configuration. Saving affects future grows; existing
        grow snapshots stay intact.
      </p>
      {error && (
        <p role="alert">
          {error}
          <button onClick={() => setAttempt((v) => v + 1)}>
            Reload environment
          </button>
        </p>
      )}
      {!loaded && !error ? (
        <p>Loading environment…</p>
      ) : (
        <CollapsiblePanel title="Configure fruiting tent (optional)">
          <form className="library-form" onSubmit={save}>
            <EnvironmentFields
              value={value}
              onChange={(v) => {
                setValue(v);
                setSaved(false);
              }}
            />
            {command.error && <p role="alert">{command.error}</p>}
            <button className="primary" disabled={command.busy || !loaded}>
              Save Fruiting Environment
            </button>
            {saved && <p role="status">Environment saved for future grows.</p>}
          </form>
        </CollapsiblePanel>
      )}
    </section>
  );
}
