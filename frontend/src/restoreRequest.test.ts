import { isRestoreRequestId, newRestoreRequestId } from "./restoreRequest";

afterEach(() => vi.unstubAllGlobals());

test("HTTP-compatible secure UUID v4 sets the version and variant using getRandomValues alone", () => {
  const getRandomValues = vi.fn((bytes: Uint8Array) => bytes.fill(0xff));
  vi.stubGlobal("crypto", { getRandomValues });
  expect(globalThis.crypto.randomUUID).toBeUndefined();
  expect(newRestoreRequestId()).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
  expect(getRandomValues).toHaveBeenCalledOnce();
});

test.each([
  undefined,
  {
    getRandomValues: () => {
      throw new Error("unavailable");
    },
  },
])("missing secure randomness fails closed", (crypto) => {
  vi.stubGlobal("crypto", crypto);
  expect(() => newRestoreRequestId()).toThrow("No restore was started");
});

test.each([
  undefined,
  null,
  "",
  "invalid",
  "01".repeat(16),
  "12345678-1234-1234-8234-123456789abc",
  "12345678-1234-4234-7234-123456789abc",
])("rejects a missing or invalid restore UUID: %s", (id) => {
  expect(isRestoreRequestId(id)).toBe(false);
});
