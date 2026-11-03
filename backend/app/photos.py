"""Persistent image originals and thumbnails; filenames are server generated."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .library import OWNER, event, photo_out, record, transaction
from .library_schemas import Kind, PhotoOut
from .models import PhotoAttachment

router = APIRouter(prefix="/api/library", tags=["Photos"])
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000
FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


def photo_path(request, filename):
    root = (request.app.state.settings.data_dir / "photos").resolve()
    path = (root / filename).resolve()
    if path.parent != root:
        raise HTTPException(404, "Photo not found")
    return path


def load_photo(session, photo_id):
    photo = session.get(PhotoAttachment, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    return photo


@router.post("/{kind}/{code}/photos", response_model=PhotoOut, status_code=201)
def upload(kind: Kind, code: str, request: Request, file: UploadFile):
    return store_upload(kind, code, request, file)


def store_upload(
    kind: Kind,
    code: str,
    request: Request,
    file: UploadFile,
    harvest_id=None,
    pinning_flush=None,
    journal_type=None,
    journal_flush=None,
):
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Each photo must be 10 MB or smaller")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in FORMATS:
                    raise ValueError("Unsupported image format")
                ext, media = FORMATS[image.format]
                if image.width * image.height > MAX_PIXELS or max(image.size) > 12000:
                    raise ValueError(
                        "Image dimensions exceed 24 megapixels or 12000 pixels per side"
                    )
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                thumb = ImageOps.exif_transpose(image).convert("RGB")
                thumb.thumbnail((640, 640))
                buffer = BytesIO()
                thumb.save(buffer, format="WEBP", quality=82)
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(
            422, "Upload a valid JPEG, PNG or WebP within the dimension limits"
        ) from exc
    photo_id = str(uuid4())
    filename, thumbnail = f"{photo_id}.{ext}", f"{photo_id}-thumb.webp"
    paths = [photo_path(request, filename), photo_path(request, thumbnail)]
    written = []
    try:
        with transaction(request) as session:
            record(session, kind, code)
            paths[0].parent.mkdir(parents=True, exist_ok=True)
            # Exclusive writes prevent accidental replacement of existing content.
            for path, content in zip(paths, (data, buffer.getvalue())):
                with path.open("xb") as dest:
                    written.append(path)
                    dest.write(content)
            cover = session.scalar(
                select(PhotoAttachment.id).where(
                    getattr(PhotoAttachment, OWNER[kind]) == code,
                    PhotoAttachment.is_cover == 1,
                )
            )
            photo = PhotoAttachment(
                id=photo_id,
                filename=filename,
                thumbnail=thumbnail,
                media_type=media,
                is_cover=0 if cover else 1,
                **{OWNER[kind]: code},
            )
            session.add(photo)
            session.flush()
            if harvest_id:
                from .fruiting_models import HarvestEntry, HarvestPhoto

                harvest = session.get(HarvestEntry, harvest_id)
                if not harvest or kind != "fruiting" or harvest.fruiting_id != code:
                    raise HTTPException(
                        422, "Harvest does not belong to this fruiting record"
                    )
                session.add(HarvestPhoto(photo_id=photo.id, harvest_id=harvest_id))
            if pinning_flush is not None:
                from .fruiting import pinning_event
                from .fruiting_models import PinningPhoto

                if kind != "fruiting" or harvest_id is not None:
                    raise HTTPException(422, "Choose one photo event")
                pinning_event(session, code, pinning_flush)
                session.add(
                    PinningPhoto(
                        photo_id=photo.id, fruiting_id=code, flush_number=pinning_flush
                    )
                )
            journal_description = ""
            if journal_type is not None:
                from .fruiting import journal_event
                from .fruiting_models import JournalPhoto

                if (
                    kind != "fruiting"
                    or harvest_id is not None
                    or pinning_flush is not None
                    or journal_type not in {"fruiting", "completed"}
                    or (journal_type == "completed" and journal_flush is not None)
                ):
                    raise HTTPException(422, "Choose one photo event")
                journal_event(session, code, journal_type, journal_flush)
                session.add(
                    JournalPhoto(
                        photo_id=photo.id,
                        fruiting_id=code,
                        event_type=journal_type,
                        flush_number=journal_flush,
                    )
                )
                journal_description = " to " + (
                    f"Fruiting, flush {journal_flush}"
                    if journal_type == "fruiting"
                    else "Grow Completed"
                )
            event(
                session,
                kind,
                code,
                "photo_attached",
                "Photograph attached"
                + journal_description
                + (f" to harvest {harvest_id}" if harvest_id else "")
                + (
                    f" to Pinning, flush {pinning_flush}"
                    if pinning_flush is not None
                    else ""
                ),
            )
            session.flush()
            result = photo_out(photo)
        return result
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise


@router.get("/{kind}/{code}/photos", response_model=list[PhotoOut])
def list_photos(kind: Kind, code: str, request: Request):
    with Session(request.app.state.engine) as session:
        record(session, kind, code)
        return [
            photo_out(p)
            for p in session.scalars(
                select(PhotoAttachment)
                .where(getattr(PhotoAttachment, OWNER[kind]) == code)
                .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
            )
        ]


@router.get("/photos/{photo_id}/{variant}")
def get_photo(photo_id: str, variant: str, request: Request):
    if variant not in ("original", "thumbnail"):
        raise HTTPException(404, "Photo not found")
    with Session(request.app.state.engine) as session:
        photo = load_photo(session, photo_id)
        path = photo_path(
            request, photo.filename if variant == "original" else photo.thumbnail
        )
        if not path.is_file():
            raise HTTPException(404, "Photo file not found")
        return FileResponse(
            path,
            media_type=photo.media_type if variant == "original" else "image/webp",
            headers={"X-Content-Type-Options": "nosniff"},
        )


@router.post("/photos/{photo_id}/cover", response_model=PhotoOut)
def cover(photo_id: str, request: Request):
    with transaction(request) as session:
        photo = load_photo(session, photo_id)
        kind = next(k for k, v in OWNER.items() if getattr(photo, v))
        code = getattr(photo, OWNER[kind])
        session.execute(
            update(PhotoAttachment)
            .where(getattr(PhotoAttachment, OWNER[kind]) == code)
            .values(is_cover=0)
        )
        session.flush()
        photo.is_cover = 1
        event(session, kind, code, "cover_selected", "Cover photograph selected")
        session.flush()
        return photo_out(photo)


@router.delete("/photos/{photo_id}", status_code=204)
def remove(photo_id: str, request: Request):
    # Stage files on the same filesystem; a DB failure restores both files.
    staged = []
    try:
        with transaction(request) as session:
            photo = load_photo(session, photo_id)
            kind = next(k for k, v in OWNER.items() if getattr(photo, v))
            code = getattr(photo, OWNER[kind])
            for filename in (photo.filename, photo.thumbnail):
                path = photo_path(request, filename)
                if path.exists():
                    tomb = path.with_name(f".{uuid4()}.removed")
                    path.rename(tomb)
                    staged.append((path, tomb))
            from .fruiting_models import HarvestPhoto, PinningPhoto, JournalPhoto

            journal_link = session.get(JournalPhoto, photo.id)
            journal_description = (
                (
                    " from "
                    + (
                        f"Fruiting, flush {journal_link.flush_number}"
                        if journal_link.event_type == "fruiting"
                        else "Grow Completed"
                    )
                )
                if journal_link
                else ""
            )
            pinning_link = session.get(PinningPhoto, photo.id)
            pinning_flush = pinning_link.flush_number if pinning_link else None
            harvest_link = session.get(HarvestPhoto, photo.id)
            harvest_id = harvest_link.harvest_id if harvest_link else None
            was_cover = photo.is_cover
            session.delete(photo)
            session.flush()
            if was_cover:
                fallback = session.scalar(
                    select(PhotoAttachment)
                    .where(getattr(PhotoAttachment, OWNER[kind]) == code)
                    .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
                )
                if fallback:
                    fallback.is_cover = 1
            event(
                session,
                kind,
                code,
                "photo_removed",
                "Photograph removed"
                + journal_description
                + (f" from harvest {harvest_id}" if harvest_id else "")
                + (
                    f" from Pinning, flush {pinning_flush}"
                    if pinning_flush is not None
                    else ""
                ),
            )
    except Exception:
        for path, tomb in staged:
            tomb.rename(path)
        raise
    for _, tomb in staged:
        tomb.unlink(missing_ok=True)
