import type { LibraryRecord } from "../libraryApi";
import { title, kindNames, origins } from "../libraryApi";
import { cultivationStatus } from "../containerApi";
import StrainIdentity from "./StrainIdentity";
export default function RecordHeader({ record }: { record: LibraryRecord }) {
  const physical = ["physical", "spawn", "fruiting", "spores"].includes(
    record.kind,
  );
  return (
    <header className="page-header record-header">
      <div>
        <p className="eyebrow">{kindNames[record.kind]}</p>
        <h1>
          {record.physical_label || title(record)}
          {record.physical_label && (
            <>
              {" "}
              — <StrainIdentity record={record} />
            </>
          )}
        </h1>
        {physical && !record.physical_label && (
          <p>
            <StrainIdentity record={record} />
          </p>
        )}
        {record.physical_label && record.name && <p>{record.name}</p>}
        <div className="record-meta">
          <span className="badge">
            {physical
              ? cultivationStatus(record)
              : record.status === "archived"
                ? "Archived"
                : "Registered"}
          </span>
          {record.status === "archived" && physical && (
            <span className="badge">Archived record</span>
          )}
          {record.origin && (
            <span>
              Origin:{" "}
              {origins[record.origin as keyof typeof origins] || record.origin}
            </span>
          )}
          {record.supplier && <span>Source: {record.supplier}</span>}
          {record.acquisition_date && (
            <span>Acquired: {record.acquisition_date}</span>
          )}
          {record.inoculation_date && (
            <span>Inoculated: {record.inoculation_date}</span>
          )}
          {record.ready_date && <span>Ready: {record.ready_date}</span>}
          {record.balance_tracked && (
            <span>
              Remaining: {record.remaining_quantity ?? "Unknown"}{" "}
              {record.remaining_unit}
            </span>
          )}
          <small>Permanent ID: {record.id}</small>
        </div>
      </div>
    </header>
  );
}
