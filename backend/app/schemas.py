from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["ok", "unavailable"]
    migrations: Literal["current", "outdated", "unavailable"]


class AppInfo(BaseModel):
    name: str = "Cultivatinator"
    version: str
    environment: str
    storage: str = "SQLite · persistent local storage"


class Counts(BaseModel):
    active_cultures: int = Field(default=0, ge=0)
    spawn_containers: int = Field(default=0, ge=0)
    fruiting_units: int = Field(default=0, ge=0)
    open_alerts: int = Field(default=0, ge=0)


class RecordReference(BaseModel):
    record_id: str
    title: str
    target: str


class AttentionItem(RecordReference):
    severity: Literal["info", "warning", "critical"]
    description: str


class ActivityItem(RecordReference):
    occurred_at: datetime
    description: str


class EnvironmentalObservation(BaseModel):
    record_id: str
    area: str
    observed_at: datetime
    temperature_c: float | None = None
    humidity_percent: float | None = Field(default=None, ge=0, le=100)


class DashboardSummary(BaseModel):
    counts: Counts = Field(default_factory=Counts)
    attention_items: list[AttentionItem] = Field(default_factory=list)
    active_cultivation: list[RecordReference] = Field(default_factory=list)
    recent_activity: list[ActivityItem] = Field(default_factory=list)
    environmental_observations: list[EnvironmentalObservation] = Field(
        default_factory=list
    )
