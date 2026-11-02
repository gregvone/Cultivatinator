from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .library_schemas import Input, Text, Notes, Quantity

Positive = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
StockUnit = Literal[
    "mg",
    "g",
    "kg",
    "oz",
    "lb",
    "mL",
    "L",
    "us_fl_oz",
    "us_cup",
    "each",
    "count",
    "plate",
    "print",
    "swab",
    "slant",
]
MaterialType = Literal["agar_plate", "lc_jar", "lc_syringe", "spawn_jar", "spawn_bag"]


class Command(Input):
    request_key: Annotated[str, Field(min_length=8, max_length=100)]


class StockInput(Command):
    name: Annotated[Text, Field(min_length=1)]
    category: Literal[
        "ingredient", "consumable", "reusable", "source", "equipment", "other"
    ]
    unit: StockUnit
    available: Quantity | None = None
    container_type: MaterialType | Literal["fruiting_tray"] | None = None
    source_kind: Literal["physical", "spores"] | None = None
    source_id: Text | None = None
    notes: Notes | None = None
    storage_location: Text | None = None
    reason: Annotated[Notes, Field(min_length=1)]

    @model_validator(mode="after")
    def valid(self):
        if self.category == "source":
            if not self.source_kind or not self.source_id or self.container_type:
                raise ValueError("Select one biological source for source inventory")
        elif self.source_kind or self.source_id:
            raise ValueError("Only source inventory can bind a biological record")
        if self.category == "reusable" and (
            self.available is None
            or self.unit not in {"count", "each"}
            or self.container_type
            not in {"agar_plate", "lc_jar", "spawn_jar", "fruiting_tray"}
        ):
            raise ValueError(
                "Reusable pools require a known whole count and a reusable container type"
            )
        if (
            self.category == "consumable"
            and self.container_type
            and (
                self.unit not in {"count", "each"}
                or self.container_type not in {"spawn_bag", "lc_syringe"}
            )
        ):
            raise ValueError(
                "Disposable container supplies must use count and a bag/syringe type"
            )
        if (
            self.category in {"ingredient", "equipment", "other"}
            and self.container_type
        ):
            raise ValueError("Ingredients are separate from container supplies")
        return self


class StockAdjustment(Command):
    mode: Literal["add", "correct"]
    quantity: Quantity | None = None
    expected_revision: int = Field(ge=1)
    unit: StockUnit | None = None
    reason: Annotated[Notes, Field(min_length=1)]

    @model_validator(mode="after")
    def valid(self):
        if self.mode == "add" and (self.quantity is None or self.quantity <= 0):
            raise ValueError("An addition requires a positive quantity")
        return self


class Ingredient(Input):
    item_id: Text
    quantity: Positive
    unit: StockUnit


class Processing(Input):
    method: Text | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=100000)
    temperature_c: (
        Annotated[Decimal, Field(ge=0, le=1000, max_digits=7, decimal_places=3)] | None
    ) = None
    pressure_psi: (
        Annotated[Decimal, Field(ge=0, le=1000, max_digits=7, decimal_places=3)] | None
    ) = None
    notes: Notes | None = None


class RecipeIngredient(Input):
    item_id: Text | None = None
    name: Text | None = None
    quantity: Positive
    unit: StockUnit

    @model_validator(mode="after")
    def identified(self):
        if not self.item_id and not self.name:
            raise ValueError("Give each ingredient a name")
        return self


class RecipeData(Input):
    name: Annotated[Text, Field(min_length=1)]
    recipe_type: Literal["agar", "grain", "lc", "substrate"]
    batch_yield: int = Field(ge=1, le=10000)
    ingredients: list[RecipeIngredient] = Field(min_length=1, max_length=100)
    description: Notes | None = None
    notes: Notes | None = None
    instructions: Notes | None = None
    processing: Processing = Field(default_factory=Processing)
    shelf_life_days: int | None = Field(default=None, ge=0, le=3650)

    @model_validator(mode="after")
    def valid(self):
        linked = [i.item_id for i in self.ingredients if i.item_id]
        if len(set(linked)) != len(linked):
            raise ValueError("List each ingredient once")
        return self


class RecipeInput(Command, RecipeData):
    pass


class RecipeEdit(RecipeInput):
    expected_revision: int = Field(ge=1)
    status: Literal["active", "archived"] = "active"


class PreparationInput(Command):
    material_type: MaterialType
    count: int = Field(ge=1, le=100)
    container_item_id: Text
    recipe_id: Text | None = None
    ingredients: list[Ingredient] | None = Field(default=None, max_length=100)
    preparation_date: date | None = None
    processing: Processing | None = None
    use_by: date | None = None
    shelf_life_days: int | None = Field(default=None, ge=0, le=3650)
    notes: Notes | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.ingredients is not None and len(
            {i.item_id for i in self.ingredients}
        ) != len(self.ingredients):
            raise ValueError("List each ingredient once")
        return self


class MaterialSelection(Command):
    prepared_ids: list[Text] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        if len(set(self.prepared_ids)) != len(self.prepared_ids):
            raise ValueError("Select each prepared container once")
        return self


class InoculationInput(MaterialSelection):
    source_kind: Literal["physical", "spores"]
    source_id: Text
    usage_per_container: Positive | None = None
    unit: StockUnit
    inoculation_date: date | None = None
    destination_volume_ml: Quantity | None = None
    notes: Notes | None = None


class FinishInput(Command):
    action: Literal["complete", "failed"]
    action_date: date | None = None
    reason: Annotated[Notes, Field(min_length=1)]
    notes: Notes | None = None


class StockOut(Input):
    id: str
    name: str
    category: str
    unit: str
    available: Decimal | None
    container_type: str | None
    physical_id: str | None
    spore_id: str | None
    notes: str | None
    storage_location: str | None = None
    status: str
    revision: int
    created_at: str


class RecipeAction(Command):
    expected_revision: int = Field(ge=1)


class StockEdit(Command):
    expected_revision: int = Field(ge=1)
    name: Annotated[Text, Field(min_length=1)]
    notes: Notes | None = None
    storage_location: Text | None = None
    reason: Annotated[Notes, Field(min_length=1)]


class DirectCreation(Command):
    material_type: MaterialType
    recipe_id: Text | None = None
    source_kind: Literal["physical", "spores"]
    source_id: Text
    count: int = Field(ge=1, le=100)
    inoculation_date: date = Field(default_factory=date.today)
    usage_per_container: Positive | None = None
    unit: StockUnit = "mL"
    destination_volume_ml: Quantity | None = None
    notes: Notes | None = None


class RecipeOut(RecipeData):
    updated_at: str | None = None
    used: bool = False
    id: str
    revision: int
    status: str
    created_at: str


class PreparedOut(Input):
    id: str
    batch_id: str
    material_type: MaterialType
    stage: str
    use_by: str | None
    physical_id: str | None
    spawn_id: str | None
    created_at: str
    expired: bool
    snapshot: dict
    source: dict | None = None


class OperationOut(Input):
    operation_id: str
    materials: list[PreparedOut]


class LedgerOut(Input):
    id: int
    operation_id: str
    item_id: str
    entry_type: str
    amount: Decimal | None
    unit: str
    before_quantity: Decimal | None
    after_quantity: Decimal | None
    reason: str
    created_at: str


class LifecycleOut(Input):
    lifecycle: str
    stock_item_id: str | None = None
    remaining_quantity: Decimal | None = None
    remaining_unit: str | None = None
    balance_tracked: bool = False
    prepared_id: str | None = None


class FinishedRecordOut(LifecycleOut):
    id: str


class MaterialHistoryOut(Input):
    state: LifecycleOut
    preparation: PreparedOut | None
    destinations: list[PreparedOut]


class OperationAuditOut(Input):
    id: str
    operation_type: str
    payload: dict
    created_at: str
