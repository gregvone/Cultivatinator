// getRandomValues is available on trusted-LAN HTTP origins where randomUUID
// requires a secure context. Never fall back to Math.random for restore keys.
export function isRestoreRequestId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}

export function newRestoreRequestId(): string {
  try {
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (value) =>
      value.toString(16).padStart(2, "0"),
    ).join("");
    const id = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    if (!isRestoreRequestId(id)) throw new Error("Invalid UUID");
    return id;
  } catch {
    throw new Error(
      "Your browser could not generate a secure restore request ID. No restore was started; reload and retry in a browser with crypto.getRandomValues support.",
    );
  }
}
