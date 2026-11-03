import { useRef, useState } from "react";
import { libraryApi } from "../libraryApi";

type PendingPhoto = {
  id: number;
  file: File;
  state: "pending" | "saved" | "failed";
  error?: string;
};
export function usePhotoUploads() {
  const [items, setItems] = useState<PendingPhoto[]>([]);
  const queue = useRef<PendingPhoto[]>([]);
  const sequence = useRef(0);
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  function replace(next: PendingPhoto[]) {
    queue.current = next;
    setItems(next);
  }
  function add(files: File[]) {
    const next = files.map((file) => ({
      id: ++sequence.current,
      file,
      state: "pending" as const,
    }));
    replace([...queue.current, ...next]);
    return next;
  }
  function remove(id: number) {
    if (!lock.current) replace(queue.current.filter((item) => item.id !== id));
  }
  async function upload(
    path: string,
    namespace = "fruiting",
    selected?: PendingPhoto[],
  ) {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    try {
      const pending = (selected || queue.current).filter(
        (item) => item.state !== "saved",
      );
      for (const item of pending) {
        const body = new FormData();
        body.append("file", item.file);
        try {
          await libraryApi(path, "POST", body, namespace);
          replace(
            queue.current.map((current) =>
              current.id === item.id
                ? { ...current, state: "saved", error: undefined }
                : current,
            ),
          );
        } catch (error) {
          replace(
            queue.current.map((current) =>
              current.id === item.id
                ? {
                    ...current,
                    state: "failed",
                    error:
                      error instanceof Error ? error.message : "Upload failed",
                  }
                : current,
            ),
          );
        }
      }
      return queue.current.every((item) => item.state === "saved");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return { items, busy, add, remove, upload };
}
export type PhotoUploads = ReturnType<typeof usePhotoUploads>;
export function PhotoSelection({
  uploads,
  label,
  disabled = false,
  onFiles,
}: {
  uploads: PhotoUploads;
  label: string;
  disabled?: boolean;
  onFiles?: (files: File[]) => void;
}) {
  return (
    <>
      <label className="field">
        <span>{label}</span>
        <input
          aria-label={label}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          disabled={disabled || uploads.busy}
          onChange={(e) => {
            const files = Array.from(e.target.files || []);
            e.target.value = "";
            if (onFiles) onFiles(files);
            else uploads.add(files);
          }}
        />
      </label>
      {uploads.items.some((item) => item.state !== "saved") && (
        <ul>
          {uploads.items
            .filter((item) => item.state !== "saved")
            .map((item) => (
              <li key={item.id}>
                {item.state === "failed" ? (
                  <p role="alert">
                    {item.file.name}: {item.error}
                  </p>
                ) : (
                  <span>Selected: {item.file.name}</span>
                )}
                <button
                  type="button"
                  disabled={disabled || uploads.busy}
                  onClick={() => uploads.remove(item.id)}
                >
                  Remove {item.file.name}
                </button>
              </li>
            ))}
        </ul>
      )}
      {uploads.busy && <p role="status">Uploading photographs…</p>}
    </>
  );
}
