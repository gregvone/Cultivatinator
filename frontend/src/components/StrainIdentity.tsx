import { Link } from "react-router-dom";
import type { LibraryRecord } from "../libraryApi";

/** Physical source identity; multiple named strains do not imply a hybrid. */
export default function StrainIdentity({ record }: { record: LibraryRecord }) {
  if (record.kind !== "fruiting" || !record.strain_identification)
    return <>{record.strain_name || "Unknown"}</>;
  const strains = record.contributing_strains ?? [];
  if (!strains.length) return <>Unknown</>;
  const partial = record.strain_identification === "partial";
  return (
    <>
      {strains.length > 1 && <>Mixed Strains{partial ? " · " : ": "}</>}
      {partial && <>Partial identification: </>}
      {strains.map((strain, i) => (
        <span key={strain.id}>
          {i > 0 && ", "}
          <Link to={`/culture-library/strains/${strain.id}`}>
            {strain.name}
          </Link>
        </span>
      ))}
      {partial && <>; Unknown sources</>}
    </>
  );
}
