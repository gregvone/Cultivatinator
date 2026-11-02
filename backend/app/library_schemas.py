from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
import unicodedata
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]
Price = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Unit = Literal["mL", "L", "g", "count", "plate", "slant", "print", "swab"]
Origin = Literal["purchased", "gifted", "other"]
CultureType = Literal["lc_syringe", "lc_jar", "agar_plate", "slant", "other_culture"]
SporeType = Literal["spore_print", "spore_syringe", "spore_swab", "other_spore"]
Kind = Literal["strains", "lines", "spores", "physical", "spawn", "batches", "fruiting"]
Status = Literal["active", "archived"]


def normalized(name):
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Description(Input):
    name: Text | None = None
    notes: Notes | None = None


class StrainInput(Description):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    scientific_name: Text | None = None
    description: Notes | None = None

    @field_validator("name")
    @classmethod
    def tidy_name(cls, v):
        v = " ".join(unicodedata.normalize("NFKC", v).split())
        if not v:
            raise ValueError("Strain name is required")
        if len(v) > 200:
            raise ValueError("Normalized strain name must be at most 200 characters")
        return v


class Acquisition(Description):
    supplier: Text | None = None
    supplier_reference: Text | None = None
    acquisition_date: date | None = None


class LineInput(Acquisition):
    origin: Origin = "purchased"
    supplier_batch: Text | None = None


class MaterialInput(Description):
    material_type: CultureType = "lc_syringe"
    count: int = Field(default=1, ge=1, le=100)
    quantity: Quantity | None = None
    unit: Unit | None = None
    storage_location: Text | None = None
    purchase_price: Price | None = None

    @model_validator(mode="after")
    def units(self):
        if self.quantity is not None and self.unit is None:
            raise ValueError("Select a unit for the starting quantity")
        return self


class ReceiveCulture(Input):
    strain_id: Text | None = None
    inline_strain: StrainInput | None = None
    existing_line_id: Text | None = None
    line: LineInput | None = None
    material: MaterialInput | None = None

    @model_validator(mode="after")
    def relationships(self):
        if self.inline_strain and self.strain_id:
            raise ValueError("Select a strain or create one, not both")
        if bool(self.existing_line_id) == bool(self.line):
            raise ValueError("Choose a new or existing culture line")
        if self.existing_line_id and not self.material:
            raise ValueError("Select physical material to add to an existing line")
        return self


class SporeInput(Acquisition):
    strain_id: Text | None = None
    inline_strain: StrainInput | None = None
    material_type: SporeType = "spore_print"
    quantity: Quantity | None = None
    unit: Unit | None = None
    storage_location: Text | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.inline_strain and self.strain_id:
            raise ValueError("Select a strain or create one, not both")
        if self.quantity is not None and self.unit is None:
            raise ValueError("Select a unit for the registered quantity")
        return self


class EditRecord(Description):
    stage: Literal["ready", "colonizing", "fruiting", "finished"] | None = None
    scientific_name: Text | None = None
    description: Notes | None = None
    supplier: Text | None = None
    supplier_reference: Text | None = None
    supplier_batch: Text | None = None
    acquisition_date: date | None = None
    origin: Origin | None = None
    material_type: (
        CultureType
        | SporeType
        | Literal["spawn_jar", "spawn_bag", "tray", "bag", "block", "other"]
        | None
    ) = None
    quantity: Quantity | None = None
    unit: Unit | None = None
    storage_location: Text | None = None
    purchase_price: Price | None = None


class StatusInput(Input):
    status: Status


class PhotoOut(BaseModel):
    id: str
    is_cover: bool
    url: str
    thumbnail_url: str


class StrainReference(BaseModel):
    id: str
    name: str


class RecordOut(BaseModel):
    id: str
    kind: Kind
    name: str | None
    notes: str | None
    status: Status
    created_at: str
    strain_id: str | None = None
    strain_name: str | None = None
    strain_identification: Literal["known", "mixed", "partial", "unknown"] | None = None
    contributing_strains: list[StrainReference] = Field(default_factory=list)
    line_id: str | None = None
    scientific_name: str | None = None
    description: str | None = None
    origin: Origin | None = None
    supplier: str | None = None
    supplier_reference: str | None = None
    supplier_batch: str | None = None
    acquisition_date: str | None = None
    material_type: (
        CultureType
        | SporeType
        | Literal["spawn_jar", "spawn_bag", "tray", "bag", "block", "other"]
        | None
    ) = None
    quantity: Decimal | None = None
    unit: Unit | None = None
    storage_location: str | None = None
    purchase_price: Decimal | None = None
    registration_batch: str | None = None
    stage: str | None = None
    batch_id: str | None = None
    batch_origin: str | None = None
    allocation_mode: str | None = None
    line_count: int = 0
    spore_count: int = 0
    physical_count: int = 0
    cover: PhotoOut | None = None


class ReceiveResult(BaseModel):
    line: RecordOut
    physical: list[RecordOut]


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    occurred_at: str
    event_type: str
    description: str
