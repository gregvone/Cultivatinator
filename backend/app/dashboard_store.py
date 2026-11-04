"""Small, atomic dashboard preferences in the already backed-up settings directory.

MutationGate serializes writes and the runtime lease enforces one app worker.
Reads never create files; cultivation tables and backup archive format are unchanged.
"""

from pathlib import Path
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .backup_store import atomic_json


class Threshold(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    days: int = Field(ge=1, le=365, strict=True)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agar_growing: Threshold = Field(default_factory=lambda: Threshold(days=21))
    spawn_colonizing: Threshold = Field(default_factory=lambda: Threshold(days=28))
    fruiting_colonizing: Threshold = Field(default_factory=lambda: Threshold(days=21))
    pinning: Threshold = Field(default_factory=lambda: Threshold(days=14))
    fruiting: Threshold = Field(default_factory=lambda: Threshold(days=14))


class Document(BaseModel):
    # Version 1 preferences are unchanged. Ignore obsolete alert-state fields in
    # existing settings/backups; reads never rewrite them or let them hide alerts.
    model_config = ConfigDict(extra="ignore")
    version: Literal[1] = 1
    preferences: Preferences = Field(default_factory=Preferences)


def path(settings):
    return Path(settings.data_dir) / "settings" / "dashboard.json"


def read(settings):
    file = path(settings)
    try:
        if not file.exists():
            return Document()
        if file.is_symlink() or file.stat().st_size > 2_000_000:
            raise ValueError("Invalid dashboard settings file")
        return Document.model_validate_json(file.read_bytes())
    except (OSError, ValueError, ValidationError) as exc:
        raise HTTPException(
            503,
            "Dashboard settings could not be read; restore settings/dashboard.json from a backup or repair it before retrying.",
        ) from exc


def write(settings, document):
    try:
        atomic_json(path(settings), document.model_dump(mode="json"))
    except OSError as exc:
        raise HTTPException(
            503,
            "Dashboard settings could not be saved. Check persistent storage and retry.",
        ) from exc
