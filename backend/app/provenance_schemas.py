"""Typed registrations: successful establishment and manually documented provenance."""

from datetime import date
from typing import Literal
from pydantic import Field, model_validator
from .library_schemas import (
    Input,
    Description,
    Text,
    Notes,
    Quantity,
    Unit,
    MaterialInput,
    ReceiveCulture,
    RecordOut,
    SporeType,
)


from .preparation_schemas import LabelChoice


class ContainerInput(Description):
    label_choice: LabelChoice | None = None
    material_type: Literal["tray", "bag", "block", "other"] = "bag"
    stage: Literal["ready", "colonizing", "fruiting", "finished"] = "ready"
    acquisition_date: date | None = None
    quantity: Quantity | None = None
    unit: Unit | None = None
    storage_location: Text | None = None
    source_ids: list[Text] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        if self.quantity is not None and self.unit is None:
            raise ValueError("Select a quantity unit")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Duplicate source allocations are not allowed")
        return self


class AcquisitionInput(ReceiveCulture):
    supplier: Text | None = None
    supplier_reference: Text | None = None
    supplier_batch: Text | None = None
    entry_type: Literal[
        "culture", "spawn_jar", "spawn_bag", "fruiting_bag", "fruiting_block"
    ]
    count: int = Field(default=1, ge=1, le=100)
    stage: Literal["ready", "colonizing"] = "ready"
    quantity: Quantity | None = None
    unit: Unit | None = None
    storage_location: Text | None = None
    name: Text | None = None
    notes: Notes | None = None
    acquisition_date: date | None = None

    @model_validator(mode="after")
    def valid_entry(self):
        if self.entry_type == "culture" and self.existing_line_id and not self.material:
            raise ValueError("Select physical culture material for an existing line")
        if self.quantity is not None and self.unit is None:
            raise ValueError("Select a quantity unit")
        if self.entry_type != "culture" and self.material is not None:
            raise ValueError(
                "Use acquisition container fields for spawn/fruiting material"
            )
        return self

    # ReceiveCulture requires material on an existing line; acquisition has its own material.
    @model_validator(mode="after")
    def relationships(self):
        if self.inline_strain and self.strain_id:
            raise ValueError("Select or create a strain, not both")
        if bool(self.existing_line_id) == bool(self.line):
            raise ValueError("Choose a new or existing culture line")
        return self


class AcquisitionResult(Input):
    line: RecordOut
    records: list[RecordOut]
    batch: RecordOut | None = None


class GrowInput(Description):
    allocation_mode: Literal["shared", "specific"] = "shared"
    acquisition_date: date | None = None
    source_ids: list[Text] = Field(default_factory=list, max_length=100)
    containers: list[ContainerInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Duplicate batch sources are not allowed")
        for container in self.containers:
            if self.allocation_mode == "shared" and container.source_ids:
                raise ValueError(
                    "Shared mixture inherits batch sources; omit specific allocations"
                )
            if set(container.source_ids) - set(self.source_ids):
                raise ValueError("Container sources must belong to the batch")
        return self


class GrowResult(Input):
    batch: RecordOut
    containers: list[RecordOut]
    warnings: list[str]


class EstablishInput(Description):
    prepared_id: Text | None = None
    origin_date: date | None = None
    material: MaterialInput | None = None
    unknown_strain: bool = False


class CollectInput(Description):
    collection_date: date | None = None
    material_type: SporeType = "spore_print"
    quantity: Quantity | None = None
    unit: Unit | None = None
    storage_location: Text | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.quantity is not None and self.unit is None:
            raise ValueError("Select a quantity unit")
        return self


class ParentInput(Input):
    parent_id: Text
    confidence: Literal["confirmed", "possible"]


class AncestryCorrection(Input):
    expected_revision: int = Field(ge=0)
    reason: Notes = Field(min_length=1)
    parents: list[ParentInput] = Field(max_length=100)

    @model_validator(mode="after")
    def valid(self):
        if len({p.parent_id for p in self.parents}) != len(self.parents):
            raise ValueError("Duplicate parents are not allowed")
        confirmed = [p for p in self.parents if p.confidence == "confirmed"]
        if confirmed and len(self.parents) != 1:
            raise ValueError(
                "Choose one confirmed parent or a list of possible parents"
            )
        return self


class Relationship(Input):
    label: str
    record: RecordOut


class ProvenanceOut(Input):
    origin_type: str | None = None
    origin_date: str | None = None
    notes: str | None = None
    revision: int = 0
    ancestry_status: Literal["confirmed", "uncertain", "unknown"] = "unknown"
    parents: list[ParentInput] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    allocation_mode: str | None = None
    provenance_mode: str = "Manually documented provenance; no consumption event"
