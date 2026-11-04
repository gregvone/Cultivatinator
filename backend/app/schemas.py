from datetime import date, datetime
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
    stage: str | None = None
    archived: bool = False


class AttentionItem(RecordReference):
    alert_id: str
    rule: str
    category: str
    recorded_date: str | None = None
    elapsed_days: int | None = None
    severity: Literal["info", "warning", "critical"]
    description: str


class ActivityItem(RecordReference):
    event_id: int
    event_type: str
    record_type: str
    occurred_at: datetime
    description: str


class EnvironmentalObservation(BaseModel):
    record_id: str
    area: str
    observed_at: datetime
    temperature_c: float | None = None
    humidity_percent: float | None = Field(default=None, ge=0, le=100)


class StageCount(BaseModel):
    group: str
    label: str
    stage: str
    count: int
    target: str


class HarvestSummary(BaseModel):
    start_date: date
    end_date: date
    timezone: str
    harvest_count: int
    wet_weight_count: int
    wet_grams: str | None
    fruiting_count: int


class DashboardSummary(BaseModel):
    counts: Counts = Field(default_factory=Counts)
    attention_total: int = 0
    active_total: int = 0
    stage_overview: list[StageCount] = Field(default_factory=list)
    harvest_summary: HarvestSummary | None = None
    attention_items: list[AttentionItem] = Field(default_factory=list)
    active_cultivation: list[RecordReference] = Field(default_factory=list)
    recent_activity: list[ActivityItem] = Field(default_factory=list)
    environmental_observations: list[EnvironmentalObservation] = Field(
        default_factory=list
    )
