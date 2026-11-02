import { createContext, useContext, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/UI";
import {
  ApiError,
  cultureTypes,
  growTypes,
  libraryApi,
  allLibraryRecords,
  localToday,
  origins,
  sporeTypes,
  title,
  units,
} from "../libraryApi";
import type { Kind, LibraryRecord } from "../libraryApi";

type Values = Record<string, string>;
const FormErrors = createContext<Values>({});
export function Field({
  name,
  label,
  values,
  set,
  errors,
  type = "text",
  required = false,
  options,
}: {
  name: string;
  label: string;
  values: Values;
  set: (name: string, value: string) => void;
  errors?: Values;
  type?: string;
  required?: boolean;
  options?: Record<string, string>;
}) {
  const inheritedErrors = useContext(FormErrors);
  errors = errors ?? inheritedErrors;
  const props = {
    id: name,
    name,
    value: values[name] ?? "",
    required,
    onChange: (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >,
    ) => set(name, e.target.value),
    "aria-invalid": !!errors[name],
    "aria-describedby": errors[name] ? `${name}-error` : undefined,
  };
  return (
    <label className="field" htmlFor={name}>
      <span>
        {label}
        {required ? " *" : ""}
      </span>
      {options ? (
        <select {...props}>
          {Object.entries(options).map(([v, l]) => (
            <option value={v} key={v}>
              {l}
            </option>
          ))}
        </select>
      ) : type === "textarea" ? (
        <textarea {...props} rows={3} maxLength={10000} />
      ) : (
        <input
          {...props}
          type={type}
          maxLength={type === "text" ? 200 : undefined}
          min={name === "count" ? 1 : type === "number" ? 0 : undefined}
          max={name === "count" ? 100 : undefined}
          step={
            name === "count"
              ? "1"
              : name === "purchase_price"
                ? "0.01"
                : type === "number"
                  ? "0.001"
                  : undefined
          }
        />
      )}{" "}
      {errors[name] && (
        <small id={`${name}-error`} className="field-error">
          {errors[name]}
        </small>
      )}
    </label>
  );
}
export function StrainFields({
  values,
  set,
  errors,
}: {
  values: Values;
  set: (n: string, v: string) => void;
  errors: Values;
}) {
  return (
    <>
      <Field
        name="name"
        label="Strain name"
        values={values}
        set={set}
        errors={errors}
        required
      />
      <Field
        name="scientific_name"
        label="Scientific name"
        values={values}
        set={set}
      />
      <Field
        name="description"
        label="Description"
        type="textarea"
        values={values}
        set={set}
      />
      <Field
        name="notes"
        label="Notes"
        type="textarea"
        values={values}
        set={set}
      />
    </>
  );
}
function nulls(values: Values) {
  return Object.fromEntries(
    Object.entries(values).map(([k, v]) => [k, v.trim() || null]),
  );
}
export function StrainForm() {
  const navigate = useNavigate();
  const [values, setValues] = useState<Values>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await libraryApi<LibraryRecord>(
        "strains",
        "POST",
        nulls(values),
      );
      navigate(`/culture-library/strains/${r.id}`, {
        state: { message: "Strain created. You can now attach photographs." },
      });
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e
          : new ApiError("Unable to save. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link to="/inventory">← Inventory</Link>
      <PageHeader
        title="Add Strain"
        description="Create a catalog entry. A strain can exist without cultures or spores."
      />
      <form className="library-form panel" onSubmit={submit}>
        <StrainFields
          values={values}
          set={(n, v) => setValues({ ...values, [n]: v })}
          errors={error?.fields ?? {}}
        />
        {error && <p role="alert">{error.message}</p>}
        <div className="actions">
          <button className="primary" disabled={busy}>
            {busy ? "Saving…" : "Create strain"}
          </button>
          <Link to="/inventory">Cancel</Link>
        </div>
      </form>
    </>
  );
}
export function ReceiveForm({ spores = false }: { spores?: boolean }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [step, setStep] = useState(0);
  const [strains, setStrains] = useState<LibraryRecord[]>([]);
  const [lines, setLines] = useState<LibraryRecord[]>([]);
  const [strainMode, setStrainMode] = useState(
    params.get("strain") ? "existing" : "unknown",
  );
  const [strain, setStrain] = useState(params.get("strain") || "");
  const [inline, setInline] = useState<Values>({});
  const [lineMode, setLineMode] = useState(
    params.get("line") ? "existing" : "new",
  );
  const [lineId, setLineId] = useState(params.get("line") || "");
  const [line, setLine] = useState<Values>({
    ...(!spores ? { origin: "purchased" } : {}),
    acquisition_date: localToday(),
  });
  const [withMaterial, setWithMaterial] = useState(!!params.get("line"));
  const [material, setMaterial] = useState<Values>({
    material_type: spores ? "spore_print" : "lc_syringe",
    count: "1",
    unit: spores ? "print" : "mL",
  });
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setLoaded(false);
    Promise.all([allLibraryRecords("strains"), allLibraryRecords("lines")])
      .then(([s, l]) => {
        if (live) {
          setStrains(s);
          setLines(l);
          setLoaded(true);
          setError(null);
        }
      })
      .catch(() => {
        if (live)
          setError(new ApiError("Unable to load registration choices."));
      });
    return () => {
      live = false;
    };
  }, [attempt]);
  const fields =
    (values: Values, update: React.Dispatch<React.SetStateAction<Values>>) =>
    (n: string, v: string) =>
      update({ ...values, [n]: v });
  const acquisition = (
    <>
      <Field
        name="name"
        label={spores ? "Custom spore name" : "Custom culture line name"}
        values={line}
        set={fields(line, setLine)}
      />
      {!spores && (
        <Field
          name="origin"
          label="Origin"
          values={line}
          set={fields(line, setLine)}
          options={origins}
        />
      )}
      <Field
        name="supplier"
        label="Supplier / source"
        values={line}
        set={fields(line, setLine)}
      />
      {!spores && (
        <Field
          name="supplier_batch"
          label="Supplier batch identifier"
          values={line}
          set={fields(line, setLine)}
        />
      )}
      <Field
        name="supplier_reference"
        label="Supplier reference / order number"
        values={line}
        set={fields(line, setLine)}
      />
      <Field
        name="acquisition_date"
        label="Acquisition date (leave blank if unknown)"
        type="date"
        values={line}
        set={fields(line, setLine)}
      />
      {!spores && (
        <Field
          name="notes"
          label="Acquisition notes"
          type="textarea"
          values={line}
          set={fields(line, setLine)}
        />
      )}
    </>
  );
  const last = spores ? 2 : 3;
  const steps = spores
    ? ["Strain", "Spore source", "Review"]
    : ["Strain", "Culture line", "Physical material", "Review"];
  function validateStep() {
    if (step === 0 && strainMode === "existing" && !strain) {
      setError(
        new ApiError("Select a strain.", { strain_id: "Select a strain" }),
      );
      return false;
    }
    if (step === 0 && strainMode === "new" && !inline.name?.trim()) {
      setError(
        new ApiError("Enter a strain name.", {
          name: "Strain name is required",
        }),
      );
      return false;
    }
    if (!spores && step === 1 && lineMode === "existing" && !lineId) {
      setError(new ApiError("Select a compatible culture line."));
      return false;
    }
    return true;
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (step < last) {
      if (validateStep()) setStep(step + 1);
      return;
    }
    setBusy(true);
    const strainData =
      strainMode === "new"
        ? { inline_strain: nulls(inline) }
        : { strain_id: strainMode === "existing" ? strain : null };
    try {
      if (spores) {
        const { count: _count, ...sporeMaterial } = nulls(material);
        void _count;
        const r = await libraryApi<LibraryRecord>("spores", "POST", {
          ...strainData,
          ...nulls(line),
          ...sporeMaterial,
        });
        navigate(`/culture-library/spores/${r.id}`, {
          state: {
            message: "Spore source registered. No culture line was created.",
          },
        });
      } else {
        const r = await libraryApi<{ line: LibraryRecord }>(
          "receive-culture",
          "POST",
          {
            ...strainData,
            ...(lineMode === "new"
              ? { line: nulls(line) }
              : { existing_line_id: lineId }),
            material:
              withMaterial || lineMode === "existing"
                ? { ...nulls(material), count: Number(material.count) }
                : null,
          },
        );
        navigate(`/culture-library/lines/${r.line.id}`, {
          state: {
            message:
              "Culture registration saved. Attach photographs to the line or individual containers below.",
          },
        });
      }
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e
          : new ApiError("Unable to save registration. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }
  const chosen = strains.find((s) => s.id === strain);
  const compatible = lines.filter(
    (l) =>
      l.strain_id === (strainMode === "existing" ? strain : null) &&
      strainMode !== "new",
  );
  const reviewLine =
    !spores && lineMode === "existing"
      ? (compatible.find((l) => l.id === lineId) ?? line)
      : line;
  return (
    <>
      <Link to="/inventory">← Inventory</Link>
      <PageHeader
        title={spores ? "Receive Spores" : "Receive Culture"}
        description={
          spores
            ? "Register genetic source material. This does not establish a culture line."
            : "Register an acquisition with an independent lineage and optional physical containers."
        }
      />
      <ol className="stepper">
        {steps.map((s, i) => (
          <li key={s} aria-current={i === step ? "step" : undefined}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>
      {!loaded ? (
        <div className="feedback">
          {error ? (
            <>
              <p role="alert">{error.message}</p>
              <button onClick={() => setAttempt(attempt + 1)}>Retry</button>
            </>
          ) : (
            "Loading registration choices…"
          )}
        </div>
      ) : (
        <FormErrors.Provider value={error?.fields ?? {}}>
          <form className="library-form panel" onSubmit={submit}>
            {step === 0 && (
              <>
                <h2>Select strain</h2>
                <label className="field">
                  <span>Strain selection</span>
                  <select
                    value={strainMode}
                    onChange={(e) => {
                      setStrainMode(e.target.value);
                      setLineId("");
                    }}
                  >
                    <option value="unknown">Strain currently unknown</option>
                    <option value="existing">Select existing strain</option>
                    <option value="new">Create strain inline</option>
                  </select>
                </label>
                {strainMode === "existing" && (
                  <Field
                    name="strain_id"
                    label="Strain"
                    values={{ strain_id: strain }}
                    set={(_, v) => {
                      setStrain(v);
                      setLineId("");
                    }}
                    required
                    options={{
                      "": "Choose a strain",
                      ...Object.fromEntries(
                        strains.map((s) => [s.id, `${s.name} · ${s.id}`]),
                      ),
                    }}
                  />
                )}
                {strainMode === "new" && (
                  <>
                    <p>
                      The new strain will be saved with this registration. Your
                      other entries are preserved.
                    </p>
                    <StrainFields
                      values={inline}
                      set={fields(inline, setInline)}
                      errors={error?.fields ?? {}}
                    />
                  </>
                )}
              </>
            )}
            {!spores && step === 1 && (
              <>
                <h2>Culture line</h2>
                <p>
                  Unrelated suppliers or source batches should normally have
                  separate culture lines.
                </p>
                <label className="field">
                  <span>Culture line choice</span>
                  <select
                    value={lineMode}
                    onChange={(e) => setLineMode(e.target.value)}
                  >
                    <option value="new">Create new culture line</option>
                    <option value="existing">
                      Add to existing culture line
                    </option>
                  </select>
                </label>
                {lineMode === "new" ? (
                  acquisition
                ) : (
                  <Field
                    name="existing_line_id"
                    label="Existing culture line"
                    required
                    values={{ existing_line_id: lineId }}
                    set={(_, v) => setLineId(v)}
                    options={{
                      "": "Choose a compatible line",
                      ...Object.fromEntries(
                        compatible.map((l) => [l.id, `${title(l)} · ${l.id}`]),
                      ),
                    }}
                  />
                )}
              </>
            )}
            {((!spores && step === 2) || (spores && step === 1)) && (
              <>
                <h2>{spores ? "Spore source" : "Physical material"}</h2>
                {spores ? (
                  acquisition
                ) : lineMode === "new" ? (
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={withMaterial}
                      onChange={(e) => setWithMaterial(e.target.checked)}
                    />
                    Register physical containers now
                  </label>
                ) : (
                  <p>
                    Add individually identified containers to the selected
                    culture line.
                  </p>
                )}
                {(spores || withMaterial || lineMode === "existing") && (
                  <>
                    <Field
                      name="material_type"
                      label={spores ? "Spore type" : "Container type"}
                      values={material}
                      set={(n, v) =>
                        setMaterial({
                          ...material,
                          [n]: v,
                          unit:
                            v === "spore_print"
                              ? "print"
                              : v === "spore_swab"
                                ? "swab"
                                : v === "agar_plate"
                                  ? "plate"
                                  : v === "slant"
                                    ? "slant"
                                    : v.includes("syringe") || v === "lc_jar"
                                      ? "mL"
                                      : "count",
                        })
                      }
                      options={spores ? sporeTypes : cultureTypes}
                    />
                    {!spores && (
                      <Field
                        name="count"
                        label="Number of containers (1–100)"
                        required
                        type="number"
                        values={material}
                        set={fields(material, setMaterial)}
                      />
                    )}
                    <Field
                      name="quantity"
                      label={
                        spores
                          ? "Registered Quantity (optional)"
                          : "Starting Quantity per container (optional)"
                      }
                      type="number"
                      values={material}
                      set={fields(material, setMaterial)}
                    />
                    <Field
                      name="unit"
                      label="Quantity unit"
                      values={material}
                      set={fields(material, setMaterial)}
                      options={{ "": "Unknown", ...units }}
                    />
                    <Field
                      name="storage_location"
                      label="Storage location"
                      values={material}
                      set={fields(material, setMaterial)}
                    />
                    {!spores && (
                      <>
                        <Field
                          name="purchase_price"
                          label="Purchase price per container (optional)"
                          type="number"
                          values={material}
                          set={fields(material, setMaterial)}
                        />
                        <Field
                          name="name"
                          label="Container custom name / label"
                          values={material}
                          set={fields(material, setMaterial)}
                        />
                      </>
                    )}
                    <Field
                      name="notes"
                      label="Material notes"
                      type="textarea"
                      values={material}
                      set={fields(material, setMaterial)}
                    />
                    <p className="muted">
                      Registered quantities are starting measurements, not live
                      remaining balances.
                    </p>
                  </>
                )}
              </>
            )}
            {step === last && (
              <>
                <h2>Review registration</h2>
                <dl className="review-list">
                  <div>
                    <dt>Strain</dt>
                    <dd>
                      {strainMode === "unknown"
                        ? "Unknown"
                        : strainMode === "new"
                          ? `${inline.name} (new strain)`
                          : chosen?.name}
                    </dd>
                  </div>
                  <div>
                    <dt>{spores ? "Source" : "Culture line"}</dt>
                    <dd>
                      {!spores && lineMode === "existing"
                        ? `${lineId} · ${origins[reviewLine.origin as keyof typeof origins]}`
                        : `${line.name || "Generated permanent ID"} · ${spores ? "Spore material" : origins[line.origin as keyof typeof origins]}`}
                    </dd>
                  </div>
                  <div>
                    <dt>Acquisition</dt>
                    <dd>
                      {reviewLine.supplier || "Supplier unknown"} ·{" "}
                      {reviewLine.acquisition_date || "Date unknown"}
                      {reviewLine.supplier_batch
                        ? ` · Batch ${reviewLine.supplier_batch}`
                        : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>Physical material</dt>
                    <dd>
                      {spores
                        ? sporeTypes[
                            material.material_type as keyof typeof sporeTypes
                          ]
                        : withMaterial || lineMode === "existing"
                          ? `${material.count} × ${cultureTypes[material.material_type as keyof typeof cultureTypes]}`
                          : "No containers registered"}
                    </dd>
                  </div>
                  {(spores || withMaterial || lineMode === "existing") && (
                    <div>
                      <dt>
                        {spores
                          ? "Registered Quantity"
                          : "Starting Quantity per container"}
                      </dt>
                      <dd>
                        {material.quantity
                          ? `${material.quantity} ${material.unit}`
                          : "Unknown"}
                      </dd>
                    </div>
                  )}
                </dl>
                <p>
                  All linked records will be saved together. Photographs can be
                  attached after registration.
                </p>
              </>
            )}
            {error && (
              <div role="alert" className="field-error">
                {error.message}{" "}
                {step === last && "Use Back to correct the registration."}
              </div>
            )}
            <div className="actions">
              {step > 0 && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setStep(step - 1);
                  }}
                >
                  Back
                </button>
              )}
              <button className="primary" disabled={busy}>
                {busy
                  ? "Saving…"
                  : step === last
                    ? "Confirm registration"
                    : "Continue"}
              </button>
              <Link to="/inventory">Cancel</Link>
            </div>
          </form>
        </FormErrors.Provider>
      )}
    </>
  );
}
export function EditForm({
  record,
  onSaved,
  onCancel,
}: {
  record: LibraryRecord;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const kind: Kind = record.kind;
  const editable = [
    "name",
    "notes",
    ...(kind === "strains"
      ? ["scientific_name", "description"]
      : kind === "lines"
        ? [
            "origin",
            "supplier",
            "supplier_batch",
            "supplier_reference",
            "acquisition_date",
          ]
        : kind === "batches"
          ? [
              "supplier",
              "supplier_reference",
              "supplier_batch",
              "acquisition_date",
            ]
          : kind === "spawn" || kind === "fruiting"
            ? [
                ...(kind === "spawn"
                  ? ["supplier", "supplier_reference", "supplier_batch"]
                  : []),
                "acquisition_date",
                "stage",
                "material_type",
                "quantity",
                "unit",
                "storage_location",
              ]
            : kind === "spores"
              ? [
                  "supplier",
                  "supplier_reference",
                  "acquisition_date",
                  "material_type",
                  "quantity",
                  "unit",
                  "storage_location",
                ]
              : [
                  "acquisition_date",
                  "material_type",
                  "quantity",
                  "unit",
                  "storage_location",
                  "purchase_price",
                ]),
  ];
  const [values, setValues] = useState<Values>(
    Object.fromEntries(
      editable.map((k) => [k, String(record[k as keyof LibraryRecord] ?? "")]),
    ),
  );
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await libraryApi(`${kind}/${record.id}`, "PATCH", nulls(values));
      onSaved();
    } catch (e) {
      setError(
        e instanceof ApiError ? e : new ApiError("Unable to save changes."),
      );
    } finally {
      setBusy(false);
    }
  }
  const labels: Values = {
    name: kind === "strains" ? "Strain name" : "Custom name",
    stage: "Stage",
    notes: "Notes",
    scientific_name: "Scientific name",
    description: "Description",
    origin: "Origin",
    supplier: "Supplier / source",
    supplier_batch: "Supplier batch identifier",
    supplier_reference: "Supplier reference",
    acquisition_date: "Acquisition date",
    material_type: kind === "spores" ? "Spore type" : "Container type",
    quantity: kind === "physical" ? "Starting Quantity" : "Registered Quantity",
    unit: "Quantity unit",
    storage_location: "Storage location",
    purchase_price: "Purchase price",
  };
  return (
    <form onSubmit={submit} className="library-form panel">
      <h2>Edit {record.id}</h2>
      {editable.map((k) => (
        <Field
          key={k}
          name={k}
          label={labels[k]}
          required={kind === "strains" && k === "name"}
          values={values}
          set={(n, v) => setValues({ ...values, [n]: v })}
          errors={error?.fields ?? {}}
          type={
            k === "quantity" || k === "purchase_price"
              ? "number"
              : k === "acquisition_date"
                ? "date"
                : k === "notes" || k === "description"
                  ? "textarea"
                  : "text"
          }
          options={
            k === "origin"
              ? origins
              : k === "material_type"
                ? kind === "spores"
                  ? sporeTypes
                  : kind === "spawn"
                    ? {
                        spawn_jar: growTypes.spawn_jar,
                        spawn_bag: growTypes.spawn_bag,
                      }
                    : kind === "fruiting"
                      ? {
                          tray: "Tray",
                          bag: "Bag",
                          block: "Block",
                          other: "Other",
                        }
                      : cultureTypes
                : k === "stage"
                  ? kind === "spawn"
                    ? { ready: "Ready for Spawning", colonizing: "Colonizing" }
                    : {
                        ready: "Ready",
                        colonizing: "Colonizing",
                        fruiting: "Fruiting",
                        finished: "Finished",
                      }
                  : k === "unit"
                    ? { "": "Unknown", ...units }
                    : undefined
          }
        />
      ))}
      {error && <p role="alert">{error.message}</p>}
      <div className="actions">
        <button className="primary" disabled={busy}>
          {busy ? "Saving…" : "Save changes"}
        </button>
        <button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}
