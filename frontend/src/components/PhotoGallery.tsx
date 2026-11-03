import { useEffect, useRef, useState } from "react";
import { ImagePlus } from "lucide-react";
import { libraryApi } from "../libraryApi";
import type { Kind, Photo } from "../libraryApi";
function PhotoViewer({
  photo,
  code,
  onClose,
}: {
  photo: Photo;
  code: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="photo-viewer"
      onCancel={onClose}
      aria-label="Photograph viewer"
    >
      <button autoFocus onClick={onClose}>
        Close photograph
      </button>
      <img src={photo.url} alt={`Photograph of ${code}`} />
    </dialog>
  );
}
export default function PhotoGallery({
  kind,
  code,
  onChange,
  harvestId,
}: {
  kind: Kind;
  code: string;
  onChange: () => void;
  harvestId?: string;
}) {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [view, setView] = useState<Photo | null>(null);
  useEffect(() => {
    let live = true;
    libraryApi<Photo[]>(
      harvestId ? `harvests/${harvestId}/photos` : `${kind}/${code}/photos`,
      "GET",
      undefined,
      harvestId ? "fruiting" : "library",
    )
      .then((p) => {
        if (live) setPhotos(p);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [kind, code, revision, harvestId]);
  async function action(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      setRevision((v) => v + 1);
      onChange();
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Photo operation failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel gallery-panel">
      <h2>
        <ImagePlus size={18} aria-hidden="true" />
        Photographs
      </h2>
      <p>
        JPEG, PNG or WebP · up to 10 MB and 24 megapixels per image · originals
        retained
      </p>
      <label className="field">
        <span>Attach photographs</span>
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          disabled={busy}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (files.length)
              void action(async () => {
                for (const file of files) {
                  const body = new FormData();
                  body.append("file", file);
                  await libraryApi(
                    harvestId
                      ? `harvests/${harvestId}/photos`
                      : `${kind}/${code}/photos`,
                    "POST",
                    body,
                    harvestId ? "fruiting" : "library",
                  );
                }
              }, `${files.length} photograph(s) attached`);
          }}
        />
      </label>
      {busy && <p role="status">Saving photographs…</p>}
      {notice && <p role="status">{notice}</p>}
      {error && (
        <div role="alert">
          {error}
          <p>Refresh the gallery to check which photographs were saved.</p>
          <button
            onClick={() => {
              setError("");
              setRevision(revision + 1);
            }}
          >
            Refresh gallery
          </button>
        </div>
      )}
      {!photos.length && <p className="muted">No photographs attached.</p>}
      <div className="photo-grid">
        {photos.map((p, i) => (
          <figure key={p.id}>
            <button
              className="photo-open"
              onClick={() => setView(p)}
              aria-label={`Open photograph ${i + 1}`}
            >
              <img
                src={p.thumbnail_url}
                alt={`Photograph ${i + 1} of ${code}`}
              />
            </button>
            <figcaption>
              {p.is_cover ? (
                <span className="badge">Cover photograph</span>
              ) : (
                <button
                  disabled={busy}
                  onClick={() =>
                    void action(
                      () => libraryApi(`photos/${p.id}/cover`, "POST"),
                      "Cover photograph updated",
                    )
                  }
                >
                  Use as cover
                </button>
              )}
              <button
                disabled={busy}
                onClick={() => {
                  if (window.confirm("Remove this photograph permanently?"))
                    void action(
                      () => libraryApi(`photos/${p.id}`, "DELETE"),
                      "Photograph removed",
                    );
                }}
              >
                Remove
              </button>
            </figcaption>
          </figure>
        ))}
      </div>
      {view && (
        <PhotoViewer photo={view} code={code} onClose={() => setView(null)} />
      )}
    </section>
  );
}
