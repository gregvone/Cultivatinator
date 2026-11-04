import { useEffect, useState } from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { useApi } from "../useApi";
import { dashboardCommand } from "../dashboardApi";
import { ErrorState, LoadingState } from "./UI";
const labels = {
  agar_growing: "Agar growing (Germinating)",
  spawn_colonizing: "Spawn colonizing",
  fruiting_colonizing: "Fruiting container colonizing",
  pinning: "Pinning",
  fruiting: "Fruiting",
};
type Preferences = Record<
  keyof typeof labels,
  { enabled: boolean; days: number }
>;
export default function DashboardPreferences() {
  const { data, error, retry } = useApi<Preferences>("dashboard/preferences");
  const [values, setValues] = useState<Preferences | null>(null);
  const [failure, setFailure] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (data && Object.keys(labels).every((key) => key in data))
      setValues(data);
  }, [data]);
  return (
    <CollapsiblePanel
      title="Attention Preferences"
      summary="Optional elapsed-time reminders"
    >
      <p>
        Remind me after more than the selected number of days since a recorded
        stage date. These are personal reminders, not biological predictions.
        Missing dates never generate elapsed-time reminders.
      </p>
      {error ? (
        <ErrorState error={error} retry={retry} />
      ) : !values ? (
        <LoadingState />
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setSaved(false);
            setFailure("");
            try {
              const result = await dashboardCommand(
                "preferences",
                values,
                "PUT",
              );
              setValues(result);
              setSaved(true);
            } catch (e) {
              setFailure((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {Object.entries(labels).map(([key, label]) => {
            const id = key as keyof Preferences;
            return (
              <fieldset className="reminder-setting" key={key}>
                <legend>{label}</legend>
                <label>
                  <input
                    type="checkbox"
                    checked={values[id].enabled}
                    onChange={(e) => {
                      setSaved(false);
                      setValues({
                        ...values,
                        [id]: { ...values[id], enabled: e.target.checked },
                      });
                    }}
                  />{" "}
                  Enable reminder
                </label>
                <label className="field">
                  <span>{label} threshold (days)</span>
                  <input
                    type="number"
                    min={1}
                    max={365}
                    step={1}
                    required
                    disabled={!values[id].enabled}
                    value={values[id].days}
                    onChange={(e) => {
                      setSaved(false);
                      setValues({
                        ...values,
                        [id]: { ...values[id], days: Number(e.target.value) },
                      });
                    }}
                  />
                </label>
              </fieldset>
            );
          })}
          <button disabled={busy} className="primary">
            {busy ? "Saving…" : "Save attention preferences"}
          </button>
          {failure && <p role="alert">{failure}</p>}
          {saved && <p role="status">Attention preferences saved.</p>}
        </form>
      )}
    </CollapsiblePanel>
  );
}
