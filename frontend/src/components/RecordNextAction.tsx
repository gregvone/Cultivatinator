import { Link } from "react-router-dom";
import type { LibraryRecord } from "../libraryApi";
import { availableOperations, workflowPath } from "../quickCreate";
export default function RecordNextAction({
  record,
}: {
  record: LibraryRecord;
}) {
  const operation = availableOperations(record)[0];
  const detail = `/culture-library/${record.kind}/${record.id}`;
  if (record.kind === "fruiting") {
    const stage = record.fruiting_stage || record.lifecycle || record.stage;
    const next =
      stage === "pinning"
        ? "Review Fruiting"
        : ["fruiting", "harvest"].includes(stage || "")
          ? "Open harvest journal"
          : ["colonizing", "unrecorded"].includes(stage || "")
            ? "Review Pinning"
            : "Open grow journal";
    return (
      <Link className="button secondary" to={detail}>
        {next}
      </Link>
    );
  }
  if (operation)
    return (
      <Link className="button primary" to={workflowPath(operation, record)}>
        {operation.title}
      </Link>
    );
  return (
    <Link className="button secondary" to={detail}>
      Open record
    </Link>
  );
}
