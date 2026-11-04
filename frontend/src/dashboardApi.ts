export const localZone = () =>
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
export const zoneQuery = () => `timezone=${encodeURIComponent(localZone())}`;
export const stageName = (stage?: string | null) =>
  !stage || stage === "unrecorded"
    ? "Stage not recorded"
    : stage[0].toUpperCase() + stage.slice(1);

export async function dashboardCommand(
  path: string,
  data: unknown,
  method = "POST",
) {
  const response = await fetch(`/api/dashboard/${path}`, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* HTTP error remains visible. */
    }
    throw new Error(
      detail || `Dashboard request failed (HTTP ${response.status}).`,
    );
  }
  return response.json();
}
