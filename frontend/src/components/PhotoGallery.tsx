import { PhotoSelection, usePhotoUploads } from "./PhotoUploads";
import { useEffect, useId, useRef, useState } from "react";
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
  pinningFlush,
  fruitingFlush,
  completion = false,
  compact = false,
  refreshToken = 0,
}: {
  kind: Kind;
  code: string;
  onChange: () => void;
  harvestId?: string;
  pinningFlush?: number;
  fruitingFlush?: number;
  completion?: boolean;
  compact?: boolean;
  refreshToken?: number;
}) {
  const uploads = usePhotoUploads();
  const [adding, setAdding] = useState(!compact);
  const [showAll, setShowAll] = useState(false);
  const uploadId = useId();
  const scopedPath = harvestId
    ? `harvests/${harvestId}/photos`
    : pinningFlush != null
      ? `records/${code}/flushes/${pinningFlush}/pinning/photos`
      : fruitingFlush != null
        ? `records/${code}/flushes/${fruitingFlush}/fruiting/photos`
        : completion
          ? `records/${code}/completion/photos`
          : null;
  const photoPath = scopedPath || `${kind}/${code}/photos`;
  const namespace = scopedPath ? "fruiting" : "library";
  async function upload(files?: File[]) {
    setError("");
    setNotice("");
    const selected = files ? uploads.add(files) : undefined;
    const complete = await uploads.upload(photoPath, namespace, selected);
    setRevision((v) => v + 1);
    if (complete) onChange();
    setNotice(
      complete
        ? `${selected?.length || uploads.items.filter((item) => item.state !== "saved").length} photograph(s) attached`
        : "Some photographs could not be uploaded. Retry the remaining files below.",
    );
  }
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [view, setView] = useState<Photo | null>(null);
  useEffect(() => {
    let live = true;
    libraryApi<Photo[]>(photoPath, "GET", undefined, namespace)
      .then((p) => {
        if (live) {
          setPhotos(p);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [photoPath, namespace, revision, refreshToken]);
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
    <section
      className={
        compact ? "gallery-panel compact-gallery" : "panel gallery-panel"
      }
    >
      {compact ? (
        <h5>Photographs</h5>
      ) : (
        <h2>
          <ImagePlus size={18} aria-hidden="true" />
          Photographs
        </h2>
      )}
      <button
        type="button"
        className="secondary"
        aria-expanded={adding}
        aria-controls={uploadId}
        onClick={() => setAdding(!adding)}
      >
        Add Photos
      </button>
      <div id={uploadId} hidden={!adding}>
        <p>
          JPEG, PNG or WebP · up to 10 MB and 24 megapixels per image ·
          originals retained
        </p>
        <PhotoSelection
          uploads={uploads}
          label="Attach photographs"
          disabled={busy || uploads.busy}
          onFiles={(files) => void upload(files)}
        />
        {uploads.items.some((item) => item.state !== "saved") && (
          <button
            type="button"
            disabled={busy || uploads.busy}
            onClick={() => void upload()}
          >
            Retry remaining photos
          </button>
        )}
      </div>
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
      <div className={compact ? "photo-grid photo-grid-compact" : "photo-grid"}>
        {(compact && !showAll ? photos.slice(0, 3) : photos).map((p, i) => (
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
            <figcaption hidden={compact && !adding}>
              {p.is_cover ? (
                <span className="badge">Cover photograph</span>
              ) : (
                <button
                  disabled={busy || uploads.busy}
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
                className="danger"
                disabled={busy || uploads.busy}
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
      {compact && photos.length > 3 && (
        <button
          type="button"
          aria-expanded={showAll}
          onClick={() => setShowAll(!showAll)}
        >
          {showAll ? "Show fewer photos" : `Show all ${photos.length} photos`}
        </button>
      )}
      {view && (
        <PhotoViewer photo={view} code={code} onClose={() => setView(null)} />
      )}
    </section>
  );
}
