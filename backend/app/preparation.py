"""Serialized, idempotent inventory and preparation operations.

All quantities are Decimal; initial acquisition quantities are never balances.
"""

import hashlib
import json
from datetime import date, timedelta
from typing import Literal
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .library import transaction, record, allocate, event
from .models import PhysicalCulture, Spawn, now
from .preparation_models import (
    StockItem,
    LCMediaDefault,
    InventoryOperation,
    StockTransaction,
    Recipe,
    PreparationBatch,
    PreparedMaterial,
    ContainerReservation,
    MaterialLifecycle,
    MaterialTransfer,
)
from .material_state import lifecycle, material_state
from .container_tracking import tracking_state, set_phase, release_label
from .inventory_quantities import balance, convert, compatible, canonical, text_or_none
from .preparation_schemas import (
    StockInput,
    LCMediaSelection,
    StockEdit,
    RecipeAction,
    DirectCreation,
    StockAdjustment,
    RecipeInput,
    RecipeEdit,
    RecipeData,
    PreparationInput,
    MaterialSelection,
    InoculationInput,
    FinishInput,
    StockOut,
    RecipeOut,
    PreparedOut,
    OperationOut,
    LedgerOut,
    FinishedRecordOut,
    MaterialHistoryOut,
    OperationAuditOut,
)

router = APIRouter(prefix="/api/preparation", tags=["Preparation and inventory"])
D = Decimal
PREFIX = {
    "agar_plate": "AG",
    "lc_jar": "LC",
    "lc_syringe": "LC",
    "spawn_jar": "SJ",
    "spawn_bag": "SB",
}
RECIPE_TYPE = {
    "agar_plate": "agar",
    "lc_jar": "lc",
    "lc_syringe": "lc",
    "spawn_jar": "grain",
    "spawn_bag": "grain",
}
LIQUID = {"lc_jar", "lc_syringe"}


def fail(message, status=422):
    raise HTTPException(status, message)


def row_values(row):
    values = {
        c.name: getattr(row, c.name)
        for c in row.__table__.columns
        if not c.name.endswith("_exact")
    }
    if isinstance(row, StockItem):
        values["available"] = balance(row)
    elif isinstance(row, StockTransaction):
        for public, stored in (
            ("amount", "amount_exact"),
            ("before_quantity", "before_exact"),
            ("after_quantity", "after_exact"),
        ):
            if getattr(row, stored) is not None:
                values[public] = D(getattr(row, stored))
    return values


def get(session, model, code):
    row = session.get(model, code)
    if row is None:
        fail("Record not found", 404)
    return row


def execute(request, data, kind, work):
    payload = data.model_dump(mode="json")
    # Preserve fingerprints from operations predating these optional fields.
    optional_fields = ["storage_location"] + (
        ["unit"] if isinstance(data, StockAdjustment) else []
    )
    for optional in optional_fields:
        if payload.get(optional) is None:
            payload.pop(optional, None)
    if isinstance(data, (RecipeInput, RecipeEdit)):
        for field in ("description", "notes"):
            if payload.get(field) is None:
                payload.pop(field, None)
        for ingredient in payload.get("ingredients", []):
            if ingredient.get("name") is None:
                ingredient.pop("name", None)
    if isinstance(data, DirectCreation) and payload.get("label_choices") is None:
        payload.pop("label_choices", None)
    fingerprint = hashlib.sha256(
        (kind + json.dumps(payload, sort_keys=True)).encode()
    ).hexdigest()
    with transaction(
        request,
        conflict_detail="Conflicting inventory state; reload the current records before retrying",
    ) as session:
        existing = session.scalar(
            select(InventoryOperation).where(
                InventoryOperation.request_key == data.request_key
            )
        )
        if existing:
            if existing.request_hash != fingerprint:
                fail(
                    "This request key was already used for different data; reload or use a new submission",
                    409,
                )
            return json.loads(existing.result)
        op = InventoryOperation(
            id=allocate(session, "OP"),
            request_key=data.request_key,
            request_hash=fingerprint,
            operation_type=kind,
            payload=json.dumps(payload),
            result="{}",
        )
        session.add(op)
        session.flush()
        result = work(session, op)
        # The committed response is replayed on retries, even if records later change.
        encoded = json.dumps(result, default=str)
        op.result = encoded
        session.flush()
        return json.loads(encoded)


def validate_quantity(quantity, unit):
    if quantity is not None:
        if quantity < 0 or quantity > D("99999999999.999"):
            fail("Quantity must be nonnegative and within the supported precision")
        if (
            unit in {"count", "plate", "print", "swab", "slant"}
            and quantity != quantity.to_integral_value()
        ):
            fail("Count-based units require whole quantities")


def set_lifecycle(session, kind, code, state):
    row = lifecycle(session, kind, code)
    if row:
        row.state = state
    else:
        session.add(
            MaterialLifecycle(
                **{("physical_id" if kind == "physical" else "spawn_id"): code},
                state=state,
            )
        )
    session.flush()


def sync_depletion(session, item):
    if not item.physical_id:
        return
    physical = record(session, "physical", item.physical_id)
    if physical.material_type not in LIQUID:
        return
    prior = lifecycle(session, "physical", physical.id)
    if prior and prior.state in {"completed", "failed"}:
        return
    state = "depleted" if balance(item) == 0 else "active"
    if (prior.state if prior else "active") != state:
        set_lifecycle(session, "physical", physical.id, state)
        event(
            session,
            "physical",
            physical.id,
            "balance_state",
            f"LC lifecycle {state}; documented source balance changed",
        )


def ledger(session, op, item, entry, amount, after, reason):
    validate_quantity(after, item.unit)
    session.add(
        StockTransaction(
            operation_id=op.id,
            item_id=item.id,
            entry_type=entry,
            amount=amount,
            unit=item.unit,
            before_quantity=balance(item),
            amount_exact=text_or_none(amount),
            before_exact=text_or_none(balance(item)),
            after_exact=text_or_none(after),
            after_quantity=after,
            reason=reason,
        )
    )
    item.available = after
    item.available_exact = text_or_none(after)
    item.revision += 1
    sync_depletion(session, item)


def use_stock(session, op, item, quantity, unit, entry, reason):
    if item.status != "active":
        fail("Restore inventory before using it", 409)
    try:
        quantity = convert(quantity, unit, item.unit)
    except ValueError as exc:
        fail(str(exc))
    if quantity is not None:
        validate_quantity(quantity, item.unit)
        if quantity <= 0:
            fail("Usage must be positive")
    current = balance(item)
    if current is not None:
        if quantity is None:
            fail("Specify measured usage for a source with a known balance")
        if current < quantity:
            fail(
                f"Insufficient stock: {item.name} needs {quantity} {item.unit}; available {current}",
                409,
            )
        after = current - quantity
    else:
        after = None
    ledger(
        session,
        op,
        item,
        entry,
        -quantity if quantity is not None else None,
        after,
        reason,
    )


def stock_source(session, kind, code):
    return session.scalar(
        select(StockItem).where(
            (StockItem.physical_id if kind == "physical" else StockItem.spore_id)
            == code
        )
    )


def create_stock(session, op, data):
    unit = canonical(data.unit)
    quantity = convert(data.available, data.unit, unit)
    validate_quantity(quantity, unit)
    binding = {}
    if data.category == "source":
        source = record(session, data.source_kind, data.source_id)
        if source.material_type in LIQUID and not compatible(unit, "mL"):
            fail("LC remaining volumes must be tracked in mL")
        if stock_source(session, data.source_kind, data.source_id):
            fail("Source inventory already exists; use a documented adjustment", 409)
        binding["physical_id" if data.source_kind == "physical" else "spore_id"] = (
            source.id
        )
    item = StockItem(
        id=allocate(session, "INV"),
        name=data.name,
        category=data.category,
        unit=unit,
        storage_location=data.storage_location,
        available=D(0) if data.category == "reusable" else None,
        notes=data.notes,
        container_type=data.container_type,
        **binding,
    )
    session.add(item)
    session.flush()
    ledger(session, op, item, "opening", quantity, quantity, data.reason)
    session.flush()
    return row_values(item)


@router.get("/stock", response_model=list[StockOut])
def stocks(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            row_values(r)
            for r in session.scalars(
                select(StockItem).order_by(StockItem.created_at, StockItem.id)
            )
        ]


@router.post("/stock", response_model=StockOut, status_code=201)
def add_stock(data: StockInput, request: Request):
    return execute(
        request, data, "stock_opening", lambda s, op: create_stock(s, op, data)
    )


@router.post("/stock/{code}/adjust", response_model=StockOut)
def adjust_stock(code: str, data: StockAdjustment, request: Request):
    def work(session, op):
        item = get(session, StockItem, code)
        if item.revision != data.expected_revision:
            fail("Inventory changed; reload the current balance before adjusting", 409)
        try:
            quantity = convert(data.quantity, data.unit or item.unit, item.unit)
        except ValueError as exc:
            fail(str(exc))
        current = balance(item)
        after = (
            (current + quantity if current is not None else None)
            if data.mode == "add"
            else quantity
        )
        if item.category == "reusable" and after is None:
            fail("Reusable capacity must be a known whole count")
        delta = (
            quantity
            if data.mode == "add"
            else (
                after - current if after is not None and current is not None else None
            )
        )
        ledger(session, op, item, data.mode, delta, after, data.reason)
        session.flush()
        return row_values(item)

    return execute(request, data, "stock_adjust:" + code, work)


@router.get("/transactions", response_model=list[LedgerOut])
def transactions(request: Request, item_id: str | None = None):
    with Session(request.app.state.engine) as session:
        query = select(StockTransaction).order_by(StockTransaction.id.desc())
        if item_id:
            query = query.where(StockTransaction.item_id == item_id)
        return [row_values(r) for r in session.scalars(query)]


def recipe_out(row, session=None):
    contents = json.loads(row.contents)
    if session:
        for ingredient in contents.get("ingredients", []):
            if not ingredient.get("name") and ingredient.get("item_id"):
                item = session.get(StockItem, ingredient["item_id"])
                ingredient["name"] = item.name if item else ingredient["item_id"]
    return dict(
        contents,
        id=row.id,
        revision=row.revision,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_lc_default=bool(
            session
            and (default := session.get(LCMediaDefault, 1))
            and default.recipe_id == row.id
        ),
        used=(
            bool(
                session.scalar(
                    select(PreparationBatch.id)
                    .where(PreparationBatch.recipe_id == row.id)
                    .limit(1)
                )
            )
            if session
            else False
        ),
    )


def validate_ingredients(session, ingredients, optional_stock=False):
    for ingredient in ingredients:
        if not ingredient.item_id:
            if optional_stock:
                validate_quantity(ingredient.quantity, ingredient.unit)
                continue
            fail(
                "Historical inventory preparation needs linked stock for each ingredient; use Quick Create for direct creation"
            )
        item = get(session, StockItem, ingredient.item_id)
        if item.category != "ingredient" or item.status != "active":
            fail("Recipe ingredients must reference active raw ingredient inventory")
        if not compatible(item.unit, ingredient.unit):
            fail(
                f"Incompatible units for {item.name}: {ingredient.unit} and {item.unit}"
            )
        validate_quantity(ingredient.quantity, ingredient.unit)


@router.get("/recipes", response_model=list[RecipeOut])
def recipes(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            recipe_out(r, session)
            for r in session.scalars(
                select(Recipe).order_by(Recipe.created_at, Recipe.id)
            )
        ]


@router.post("/recipes", response_model=RecipeOut, status_code=201)
def add_recipe(data: RecipeInput, request: Request):
    def work(session, op):
        validate_ingredients(session, data.ingredients, optional_stock=True)
        contents = data.model_dump(mode="json", include=set(RecipeData.model_fields))
        row = Recipe(
            id=allocate(session, "RCP"),
            name=data.name,
            recipe_type=data.recipe_type,
            contents=json.dumps(contents),
            updated_at=now(),
        )
        session.add(row)
        session.flush()
        return recipe_out(row, session)

    return execute(request, data, "recipe_create", work)


@router.put("/recipes/{code}", response_model=RecipeOut)
def edit_recipe(code: str, data: RecipeEdit, request: Request):
    def work(session, op):
        row = get(session, Recipe, code)
        if row.revision != data.expected_revision:
            fail("Recipe changed; reload before editing", 409)
        default = session.get(LCMediaDefault, 1)
        if default and default.recipe_id == row.id:
            if data.recipe_type != "lc":
                fail("The default LC Media recipe must remain an LC formulation")
            if data.status == "archived":
                session.delete(default)
        validate_ingredients(session, data.ingredients, optional_stock=True)
        row.contents = json.dumps(
            data.model_dump(mode="json", include=set(RecipeData.model_fields))
        )
        row.name, row.recipe_type, row.status = data.name, data.recipe_type, data.status
        row.revision += 1
        row.updated_at = now()
        session.flush()
        return recipe_out(row, session)

    return execute(request, data, "recipe_edit:" + code, work)


def prepared_out(session, row):
    batch = get(session, PreparationBatch, row.batch_id)
    values = row_values(row)
    values.update(
        tracking_state(
            session,
            "physical" if row.physical_id else "spawn" if row.spawn_id else "prepared",
            row.id,
        )
    )
    values["snapshot"] = json.loads(batch.snapshot)
    values["expired"] = bool(
        row.use_by and date.fromisoformat(row.use_by) < date.today()
    )
    transfer = session.scalar(
        select(MaterialTransfer).where(MaterialTransfer.prepared_id == row.id)
    )
    values["source"] = None
    if transfer:
        values["source"] = {
            "kind": "physical" if transfer.physical_source_id else "spores",
            "id": transfer.physical_source_id or transfer.spore_source_id,
            "physical_label": tracking_state(
                session,
                "physical" if transfer.physical_source_id else "spores",
                transfer.physical_source_id or transfer.spore_source_id,
            ).get("physical_label"),
            "operation_id": transfer.operation_id,
            "date": transfer.transfer_date,
            "usage_quantity": transfer.usage_quantity,
            "unit": transfer.unit,
        }
    return values


@router.get("/materials", response_model=list[PreparedOut])
def prepared_materials(
    request: Request, stage: str | None = None, material_type: str | None = None
):
    with Session(request.app.state.engine) as session:
        query = select(PreparedMaterial).order_by(
            PreparedMaterial.created_at.desc(), PreparedMaterial.id
        )
        if stage:
            query = query.where(PreparedMaterial.stage == stage)
        if material_type:
            query = query.where(PreparedMaterial.material_type == material_type)
        return [prepared_out(session, r) for r in session.scalars(query)]


@router.get("/materials/{code}", response_model=PreparedOut)
def prepared_material(code: str, request: Request):
    with Session(request.app.state.engine) as session:
        return prepared_out(session, get(session, PreparedMaterial, code))


def prepare_materials(session, op, data):
    recipe = get(session, Recipe, data.recipe_id) if data.recipe_id else None
    if recipe and (
        recipe.status != "active"
        or recipe.recipe_type != RECIPE_TYPE[data.material_type]
    ):
        fail("Choose an active recipe appropriate for this preparation type")
    original = json.loads(recipe.contents) if recipe else None
    if data.ingredients is None:
        from .preparation_schemas import Ingredient

        ingredients = []
        for ingredient in (original or {}).get("ingredients", []):
            if not ingredient.get("item_id"):
                fail(
                    "This recipe has untracked ingredients; use Quick Create for direct creation"
                )
            amount = (
                D(ingredient["quantity"]) * D(data.count) / D(original["batch_yield"])
            ).quantize(D(".001"), rounding=ROUND_HALF_UP)
            if amount <= 0:
                fail(
                    "Scaled ingredient is below supported precision; enter actual batch quantities"
                )
            ingredients.append(
                Ingredient(
                    item_id=ingredient["item_id"],
                    unit=ingredient["unit"],
                    quantity=amount,
                )
            )
    else:
        ingredients = data.ingredients
    if not ingredients and data.material_type != "lc_syringe":
        fail("Select a recipe or enter the actual ingredient quantities")
    validate_ingredients(session, ingredients)
    container = get(session, StockItem, data.container_item_id)
    reusable = data.material_type in {"agar_plate", "lc_jar", "spawn_jar"}
    if (
        container.container_type != data.material_type
        or container.category != ("reusable" if reusable else "consumable")
        or container.unit != "count"
    ):
        fail("Select a matching reusable pool or disposable container supply")
    use_stock(
        session,
        op,
        container,
        D(data.count),
        "count",
        "reserve" if reusable else "consume",
        "Preparation container allocation",
    )
    actual = []
    for ingredient in ingredients:
        item = get(session, StockItem, ingredient.item_id)
        use_stock(
            session,
            op,
            item,
            ingredient.quantity,
            ingredient.unit,
            "consume",
            "Preparation ingredient consumption",
        )
        actual.append({**ingredient.model_dump(mode="json"), "name": item.name})
    processing = (
        data.processing.model_dump(mode="json")
        if data.processing
        else (original or {}).get("processing", {})
    )
    shelf = (
        data.shelf_life_days
        if "shelf_life_days" in data.model_fields_set
        else (original or {}).get("shelf_life_days")
    )
    use_by = data.use_by
    if (
        "use_by" not in data.model_fields_set
        and data.preparation_date
        and shelf is not None
    ):
        use_by = data.preparation_date + timedelta(days=shelf)
    snapshot = {
        "recipe": original,
        "recipe_revision": recipe.revision if recipe else None,
        "count": data.count,
        "material_type": data.material_type,
        "ingredients": actual,
        "processing": processing,
        "preparation_date": (
            data.preparation_date.isoformat() if data.preparation_date else None
        ),
        "use_by": use_by.isoformat() if use_by else None,
        "shelf_life_days": shelf,
        "notes": data.notes,
        "container_item_id": container.id,
        "container_name": container.name,
    }
    batch = PreparationBatch(
        id=allocate(session, "PB"),
        operation_id=op.id,
        recipe_id=recipe.id if recipe else None,
        snapshot=json.dumps(snapshot),
    )
    session.add(batch)
    session.flush()
    materials = []
    for _ in range(data.count):
        row = PreparedMaterial(
            id=allocate(session, PREFIX[data.material_type]),
            batch_id=batch.id,
            material_type=data.material_type,
            stage="ready",
            use_by=snapshot["use_by"],
        )
        session.add(row)
        session.flush()
        if reusable:
            session.add(ContainerReservation(prepared_id=row.id, item_id=container.id))
        materials.append(prepared_out(session, row))
    return {"operation_id": op.id, "materials": materials}


@router.post("/prepare", response_model=OperationOut, status_code=201)
def prepare(data: PreparationInput, request: Request):
    return execute(
        request, data, "prepare", lambda s, op: prepare_materials(s, op, data)
    )


@router.post("/ready", response_model=OperationOut)
def confirm_ready(data: MaterialSelection, request: Request):
    def work(session, op):
        rows = [get(session, PreparedMaterial, code) for code in data.prepared_ids]
        if any(r.stage != "preparing" for r in rows):
            fail("Only Preparing material can be confirmed Ready to Inoculate", 409)
        for row in rows:
            row.stage = "ready"
        session.flush()
        return {
            "operation_id": op.id,
            "materials": [prepared_out(session, r) for r in rows],
        }

    return execute(request, data, "ready", work)


def biological_material(session, row, line, op_id, volume=None):
    if row.material_type in {"spawn_jar", "spawn_bag"}:
        item = Spawn(
            id=row.id,
            line_id=line.id,
            strain_id=line.strain_id,
            material_type=row.material_type,
            stage="colonizing",
        )
        kind = "spawn"
        row.spawn_id = item.id
    else:
        item = PhysicalCulture(
            id=row.id,
            line_id=line.id,
            material_type=row.material_type,
            registration_batch=op_id,
        )
        kind = "physical"
        row.physical_id = item.id
    session.add(item)
    session.flush()
    event(
        session,
        kind,
        item.id,
        "inoculated",
        f"Physical material from prepared {row.id}; shared operation {op_id}; culture line preserved",
    )
    return kind, item


def eligible(session, kind, code, destination):
    source = record(session, kind, code, active=True)
    state = material_state(session, kind, code)
    if state["lifecycle"] in {"used", "completed", "failed", "depleted"}:
        fail("This source is completed, failed, or depleted", 409)
    if (
        kind == "physical"
        and source.material_type == "agar_plate"
        and tracking_state(session, kind, code).get("growth_stage") != "ready"
    ):
        fail("Mark this agar culture Ready before using it as a source", 409)
    stock = stock_source(session, kind, code)
    if stock and (stock.status != "active" or balance(stock) == 0):
        fail("Source stock is unavailable or depleted", 409)
    if kind == "spores":
        if destination != "agar_plate":
            fail("Spore inoculation is supported for prepared agar only")
    else:
        allowed = (
            {"lc_jar", "lc_syringe"}
            if destination == "lc_syringe"
            else {"agar_plate", "slant", "lc_jar", "lc_syringe"}
        )
        if source.material_type not in allowed:
            fail("Source material is incompatible with the destination")
    return source


def ensure_source_stock(session, op, source, kind, unit):
    stock = stock_source(session, kind, source.id)
    if stock:
        return stock
    stock = StockItem(
        id=allocate(session, "INV"),
        name=f"Source {source.id}",
        category="source",
        unit=canonical(unit),
        available=None,
        **{("physical_id" if kind == "physical" else "spore_id"): source.id},
    )
    session.add(stock)
    session.flush()
    ledger(
        session,
        op,
        stock,
        "opening",
        None,
        None,
        "Usage tracking opened with unknown balance; acquisition quantity was not imported",
    )
    return stock


def inoculate_materials(session, op, data, require_lc_measurement=True):
    rows = [get(session, PreparedMaterial, code) for code in data.prepared_ids]
    if any(r.stage != "ready" for r in rows):
        fail(
            "Select only Ready to Inoculate material; already inoculated records cannot be reused",
            409,
        )
    for row in rows:
        source = eligible(session, data.source_kind, data.source_id, row.material_type)
    source_balance = stock_source(session, data.source_kind, data.source_id)
    needs_measurement = (
        require_lc_measurement
        or any(r.material_type == "lc_syringe" for r in rows)
        or (source_balance is not None and balance(source_balance) is not None)
    )
    if source.material_type in LIQUID and (
        not compatible(data.unit, "mL")
        or (needs_measurement and data.usage_per_container is None)
    ):
        fail("LC transfers require a measured positive mL amount per container")
    measured_ml = (
        convert(data.usage_per_container, data.unit, "mL")
        if compatible(data.unit, "mL")
        else None
    )
    if source.material_type != "agar_plate":
        stock = ensure_source_stock(session, op, source, data.source_kind, data.unit)
        total = (
            data.usage_per_container * len(rows)
            if data.usage_per_container is not None
            else None
        )
        use_stock(
            session,
            op,
            stock,
            total,
            data.unit,
            "usage",
            f"Inoculation of {len(rows)} prepared container(s); operation {op.id}",
        )
    for row in rows:
        row.stage = "inoculated"
        transfer = MaterialTransfer(
            operation_id=op.id,
            prepared_id=row.id,
            physical_source_id=source.id if data.source_kind == "physical" else None,
            spore_source_id=source.id if data.source_kind == "spores" else None,
            transfer_date=(
                data.inoculation_date.isoformat() if data.inoculation_date else None
            ),
            usage_quantity=data.usage_per_container,
            unit=data.unit,
        )
        session.add(transfer)
        if data.source_kind == "physical":
            from .models import CultureLine

            line = get(session, CultureLine, source.line_id)
            kind, item = biological_material(session, row, line, op.id)
            if row.material_type in LIQUID:
                volume = (
                    measured_ml
                    if row.material_type == "lc_syringe"
                    else data.destination_volume_ml
                )
                if (
                    row.material_type == "lc_syringe"
                    and data.destination_volume_ml is not None
                    and data.destination_volume_ml != volume
                ):
                    fail("A filled syringe volume must equal the transferred volume")
                if (
                    volume is not None
                    and measured_ml is not None
                    and volume < measured_ml
                ):
                    fail(
                        "Destination total volume cannot be less than the inoculum volume"
                    )
                destination = StockItem(
                    id=allocate(session, "INV"),
                    name=f"Source {item.id}",
                    category="source",
                    unit="mL",
                    available=None,
                    physical_id=item.id,
                )
                session.add(destination)
                session.flush()
                ledger(
                    session,
                    op,
                    destination,
                    "opening",
                    volume,
                    volume,
                    (
                        "Measured destination volume"
                        if volume is not None
                        else "Destination remaining volume unknown"
                    ),
                )
        # Spores remain a pending establishment; no genetic line or parent is invented.
    if data.source_kind == "physical" and source.material_type == "agar_plate":
        consume_agar(session, op, source.id, data.inoculation_date)
    event(
        session,
        data.source_kind,
        source.id,
        "material_transferred",
        f"{len(rows)} destination(s) in {op.id}; "
        + (
            "agar source Used and physical label released"
            if source.material_type == "agar_plate"
            else "source retains partial-usage lifecycle"
        ),
    )
    session.flush()
    return {
        "operation_id": op.id,
        "materials": [prepared_out(session, r) for r in rows],
    }


@router.post("/inoculate", response_model=OperationOut, status_code=201)
def inoculate(data: InoculationInput, request: Request):
    return execute(
        request, data, "inoculate", lambda s, op: inoculate_materials(s, op, data)
    )


def bind_established(session, line, prepared_id, spore_id):
    row = get(session, PreparedMaterial, prepared_id)
    transfer = session.scalar(
        select(MaterialTransfer).where(MaterialTransfer.prepared_id == row.id)
    )
    if (
        row.material_type != "agar_plate"
        or row.stage != "inoculated"
        or row.physical_id
        or not transfer
        or transfer.spore_source_id != spore_id
    ):
        fail(
            "Select a pending agar establishment inoculated from this spore source", 409
        )
    kind, item = biological_material(session, row, line, transfer.operation_id)
    return item


@router.post("/materials/{code}/finish", response_model=PreparedOut)
def finish_prepared(code: str, data: FinishInput, request: Request):
    def work(session, op):
        row = get(session, PreparedMaterial, code)
        finish(session, op, row, data)
        return prepared_out(session, row)

    return execute(request, data, "finish_prepared:" + code, work)


def close_source_balance(session, op, kind, code, reason):
    if kind not in {"physical", "spores"}:
        return
    item = stock_source(session, kind, code)
    if item and item.status == "active":
        item.status = "archived"
        ledger(
            session,
            op,
            item,
            "closed",
            D(0),
            balance(item),
            reason + "; last recorded balance retained, source no longer usable",
        )


def finish(session, op, row, data):
    if row.stage in {"completed", "failed"}:
        fail(
            "This record was already completed or failed; its container cannot be released twice",
            409,
        )
    row.stage = "completed" if data.action == "complete" else "failed"
    reservation = session.get(ContainerReservation, row.id)
    if reservation and not reservation.released:
        item = get(session, StockItem, reservation.item_id)
        ledger(session, op, item, "release", D(1), balance(item) + D(1), data.reason)
        reservation.released = 1
    if row.physical_id or row.spawn_id:
        kind = "physical" if row.physical_id else "spawn"
        code = row.physical_id or row.spawn_id
        set_lifecycle(session, kind, code, row.stage)
        close_source_balance(session, op, kind, code, data.reason)
        event(
            session,
            kind,
            code,
            row.stage,
            f'{row.stage} on {data.action_date or "date unknown"}: {data.reason[:250]}; reusable allocation released where tracked',
        )
    kind = "physical" if row.physical_id else "spawn" if row.spawn_id else "prepared"
    set_phase(
        session,
        kind,
        row.id,
        row.stage,
        data.action_date.isoformat() if data.action_date else None,
    )
    release_label(
        session,
        kind,
        row.id,
        data.action_date.isoformat() if data.action_date else None,
        data.reason,
    )
    session.flush()


@router.post("/records/{kind}/{code}/finish", response_model=FinishedRecordOut)
def finish_existing(kind: str, code: str, data: FinishInput, request: Request):
    if kind not in {"physical", "spawn"}:
        fail("Complete or fail a physical culture or spawn record")

    def work(session, op):
        record(session, kind, code)
        state = lifecycle(session, kind, code)
        if state and state.state in {"completed", "failed"}:
            fail("Record already completed or failed", 409)
        column = (
            PreparedMaterial.physical_id
            if kind == "physical"
            else PreparedMaterial.spawn_id
        )
        row = session.scalar(select(PreparedMaterial).where(column == code))
        if row:
            finish(session, op, row, data)
        else:
            new_state = "completed" if data.action == "complete" else "failed"
            set_lifecycle(session, kind, code, new_state)
            close_source_balance(session, op, kind, code, data.reason)
            event(
                session,
                kind,
                code,
                new_state,
                f'{new_state} on {data.action_date or "date unknown"}: {data.reason[:300]}; no tracked pool allocation',
            )
        if not row:
            set_phase(
                session,
                kind,
                code,
                new_state,
                data.action_date.isoformat() if data.action_date else None,
            )
            release_label(
                session,
                kind,
                code,
                data.action_date.isoformat() if data.action_date else None,
                data.reason,
            )
        return {"id": code, **material_state(session, kind, code)}

    return execute(request, data, "finish_record:" + kind + ":" + code, work)


@router.get("/records/{kind}/{code}", response_model=MaterialHistoryOut)
def operation_history(
    kind: Literal["physical", "spawn", "spores"], code: str, request: Request
):
    with Session(request.app.state.engine) as session:
        record(session, kind, code)
        column = (
            PreparedMaterial.physical_id
            if kind == "physical"
            else PreparedMaterial.spawn_id
        )
        destination = (
            session.scalar(select(PreparedMaterial).where(column == code))
            if kind in {"physical", "spawn"}
            else None
        )
        source_column = (
            MaterialTransfer.physical_source_id
            if kind == "physical"
            else MaterialTransfer.spore_source_id
        )
        destinations = (
            session.scalars(select(MaterialTransfer).where(source_column == code)).all()
            if kind in {"physical", "spores"}
            else []
        )
        return {
            "state": material_state(session, kind, code),
            "preparation": prepared_out(session, destination) if destination else None,
            "destinations": [
                prepared_out(session, get(session, PreparedMaterial, t.prepared_id))
                for t in destinations
            ],
        }


@router.get("/operations", response_model=list[OperationAuditOut])
def operations(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            dict(
                id=row.id,
                operation_type=row.operation_type,
                payload=json.loads(row.payload),
                created_at=row.created_at,
            )
            for row in session.scalars(
                select(InventoryOperation).order_by(
                    InventoryOperation.created_at.desc(), InventoryOperation.id.desc()
                )
            )
        ]


@router.get("/pools")
def pools(request: Request):
    with Session(request.app.state.engine) as session:
        result = []
        for item in session.scalars(
            select(StockItem).where(StockItem.category == "reusable")
        ):
            stages = list(
                session.scalars(
                    select(PreparedMaterial.stage)
                    .join(
                        ContainerReservation,
                        ContainerReservation.prepared_id == PreparedMaterial.id,
                    )
                    .where(
                        ContainerReservation.item_id == item.id,
                        ContainerReservation.released == 0,
                    )
                )
            )
            result.append(
                {
                    "item_id": item.id,
                    "name": item.name,
                    "available": text_or_none(balance(item)),
                    "ready": stages.count("ready"),
                    "inoculated": stages.count("inoculated"),
                    "preparing": stages.count("preparing"),
                    "other_reserved": len(stages)
                    - sum(
                        stages.count(s) for s in ("ready", "inoculated", "preparing")
                    ),
                    "reserved": len(stages),
                    "total": text_or_none(balance(item) + len(stages)),
                }
            )
        return result


@router.get("/recipes/{code}", response_model=RecipeOut)
def recipe_detail(code: str, request: Request):
    with Session(request.app.state.engine) as session:
        return recipe_out(get(session, Recipe, code), session)


@router.delete("/recipes/{code}")
def delete_recipe(code: str, data: RecipeAction, request: Request):
    def work(session, op):
        row = get(session, Recipe, code)
        if row.revision != data.expected_revision:
            fail("Recipe changed; reload before deleting", 409)
        default = session.get(LCMediaDefault, 1)
        if default and default.recipe_id == row.id:
            fail(
                "This is the default LC Media recipe; archive it or designate another default before deleting",
                409,
            )
        if recipe_out(row, session)["used"]:
            fail(
                "This recipe has historical cultivation or preparation records; archive it instead",
                409,
            )
        session.delete(row)
        session.flush()
        return {"id": code, "deleted": True}

    return execute(request, data, "recipe_delete:" + code, work)


@router.post("/recipes/{code}/duplicate", response_model=RecipeOut, status_code=201)
def duplicate_recipe(code: str, data: RecipeAction, request: Request):
    def work(session, op):
        original = get(session, Recipe, code)
        if original.revision != data.expected_revision:
            fail("Recipe changed; reload before duplicating", 409)
        contents = json.loads(original.contents)
        contents["name"] = original.name[:190] + " (copy)"
        row = Recipe(
            id=allocate(session, "RCP"),
            name=contents["name"],
            recipe_type=original.recipe_type,
            contents=json.dumps(contents),
            updated_at=now(),
        )
        session.add(row)
        session.flush()
        return recipe_out(row, session)

    return execute(request, data, "recipe_duplicate:" + code, work)


@router.put("/stock/{code}", response_model=StockOut)
def edit_stock(code: str, data: StockEdit, request: Request):
    def work(session, op):
        item = get(session, StockItem, code)
        if item.revision != data.expected_revision:
            fail("Stock changed; reload before editing", 409)
        item.name, item.notes, item.storage_location = (
            data.name,
            data.notes,
            data.storage_location,
        )
        ledger(session, op, item, "edit", D(0), balance(item), data.reason)
        session.flush()
        return row_values(item)

    return execute(request, data, "stock_edit:" + code, work)


@router.post("/create", response_model=OperationOut, status_code=201)
def create_inoculated(data: DirectCreation, request: Request):
    def work(session, op):
        # A single operation reuses the immutable snapshot and physical-transfer
        # model. It never reserves containers or consumes ingredient inventory.
        source = eligible(session, data.source_kind, data.source_id, data.material_type)
        inherited = None
        if data.material_type == "lc_jar":
            default = session.get(LCMediaDefault, 1)
            if default is None:
                fail(
                    "Set up the default LC Media recipe in Recipes before creating LC containers",
                    409,
                )
            recipe = get(session, Recipe, default.recipe_id)
            if data.recipe_id and data.recipe_id != recipe.id:
                fail(
                    "LC containers use the designated default LC Media recipe automatically"
                )
        elif data.material_type == "lc_syringe":
            previous = session.scalar(
                select(PreparedMaterial).where(
                    PreparedMaterial.physical_id == source.id
                )
            )
            batch = (
                session.get(PreparationBatch, previous.batch_id) if previous else None
            )
            inherited = json.loads(batch.snapshot) if batch else None
            recipe = (
                session.get(Recipe, batch.recipe_id)
                if batch and batch.recipe_id
                else None
            )
        else:
            recipe = get(session, Recipe, data.recipe_id) if data.recipe_id else None
        if data.material_type != "lc_syringe" and recipe is None:
            fail("Choose a recipe for this material")
        if (
            recipe
            and data.material_type != "lc_syringe"
            and (
                recipe.status != "active"
                or recipe.recipe_type != RECIPE_TYPE[data.material_type]
            )
        ):
            fail("Choose an active recipe appropriate for this material")
        original = (
            (inherited or {}).get("recipe")
            if data.material_type == "lc_syringe"
            else json.loads(recipe.contents) if recipe else None
        )
        recipe_revision = (
            (inherited or {}).get("recipe_revision")
            if data.material_type == "lc_syringe"
            else recipe.revision if recipe else None
        )
        ingredients = []
        for ingredient in (
            []
            if data.material_type == "lc_syringe"
            else (original or {}).get("ingredients", [])
        ):
            item = (
                session.get(StockItem, ingredient.get("item_id"))
                if ingredient.get("item_id")
                else None
            )
            ingredients.append(
                {
                    **ingredient,
                    "name": ingredient.get("name")
                    or (item.name if item else "Historical ingredient"),
                    "quantity": str(
                        (
                            D(ingredient["quantity"])
                            * data.count
                            / original["batch_yield"]
                        ).quantize(D(".001"), rounding=ROUND_HALF_UP)
                    ),
                }
            )
        snapshot = {
            "workflow": "direct",
            "recipe": original,
            "recipe_revision": recipe_revision,
            "recipe_id": recipe.id if recipe else None,
            "ingredients": ingredients,
            "count": data.count,
            "material_type": data.material_type,
            "processing": (
                {}
                if data.material_type == "lc_syringe"
                else (original or {}).get("processing", {})
            ),
            "media_origin": (
                "source_transfer"
                if data.material_type == "lc_syringe"
                else "prepared" if data.material_type == "lc_jar" else None
            ),
            "media_source_id": (
                source.id if data.material_type == "lc_syringe" else None
            ),
            "preparation_date": (
                None
                if data.material_type == "lc_syringe"
                else data.inoculation_date.isoformat()
            ),
            "inoculation_date": data.inoculation_date.isoformat(),
            "notes": data.notes,
            "container_name": "",
            "container_item_id": None,
        }
        batch = PreparationBatch(
            id=allocate(session, "PB"),
            operation_id=op.id,
            recipe_id=recipe.id if recipe else None,
            snapshot=json.dumps(snapshot),
        )
        session.add(batch)
        session.flush()
        if data.label_choices is not None and len(data.label_choices) != data.count:
            fail("Provide one physical label choice per container")
        session.info["reserved_label_codes"] = {
            c.label for c in data.label_choices or [] if c.label
        }
        ids = []
        for index in range(data.count):
            row = PreparedMaterial(
                id=allocate(session, PREFIX[data.material_type]),
                batch_id=batch.id,
                material_type=data.material_type,
                stage="ready",
            )
            session.add(row)
            if data.label_choices:
                session.info.setdefault("container_choices", {})[row.id] = (
                    data.label_choices[index].model_dump()
                )
            ids.append(row.id)
        session.flush()
        transfer = InoculationInput(
            **data.model_dump(
                exclude={
                    "request_key",
                    "recipe_id",
                    "material_type",
                    "count",
                    "label_choices",
                }
            ),
            request_key=data.request_key,
            prepared_ids=ids,
        )
        return inoculate_materials(session, op, transfer, require_lc_measurement=False)

    return execute(request, data, "direct_create", work)


@router.get("/growing")
def growing_records(request: Request, workspace: Literal["laboratory", "cultivation"]):
    from .library import output

    with Session(request.app.state.engine) as session:
        kind, model = (
            ("physical", PhysicalCulture)
            if workspace == "laboratory"
            else ("spawn", Spawn)
        )
        result = []
        for row in session.scalars(
            select(model).order_by(model.created_at.desc(), model.id.desc())
        ):
            values = output(session, kind, row).model_dump(mode="json")
            history = None
            column = (
                PreparedMaterial.physical_id
                if kind == "physical"
                else PreparedMaterial.spawn_id
            )
            prepared = session.scalar(select(PreparedMaterial).where(column == row.id))
            if prepared:
                history = prepared_out(session, prepared)
            values["cultivation"] = history
            result.append(values)
        if workspace == "laboratory":
            for row in session.scalars(
                select(PreparedMaterial).where(
                    PreparedMaterial.stage.in_(["inoculated", "completed", "failed"]),
                    PreparedMaterial.physical_id.is_(None),
                    PreparedMaterial.spawn_id.is_(None),
                )
            ):
                history = prepared_out(session, row)
                if not history["source"]:
                    continue
                result.append(
                    {
                        "id": row.id,
                        "kind": "physical",
                        "pending_establishment": True,
                        "material_type": row.material_type,
                        "status": "active",
                        "lifecycle": (
                            row.stage
                            if row.stage in {"completed", "failed"}
                            else "active"
                        ),
                        "strain_name": None,
                        "line_id": None,
                        "created_at": row.created_at,
                        "cultivation": history,
                    }
                )
        return result


@router.get("/lc-default")
def lc_default(request: Request):
    with Session(request.app.state.engine) as session:
        default = session.get(LCMediaDefault, 1)
        recipe = session.get(Recipe, default.recipe_id) if default else None
        return {
            "recipe": (
                recipe_out(recipe, session)
                if recipe and recipe.status == "active" and recipe.recipe_type == "lc"
                else None
            )
        }


@router.post("/lc-default")
def designate_lc_default(data: LCMediaSelection, request: Request):
    def work(session, op):
        recipe = get(session, Recipe, data.recipe_id)
        if recipe.revision != data.expected_revision:
            fail("Recipe changed; reload before designating the default", 409)
        if recipe.status != "active" or recipe.recipe_type != "lc":
            fail("Choose an active LC Media recipe")
        default = session.get(LCMediaDefault, 1)
        if default:
            default.recipe_id = recipe.id
        else:
            session.add(LCMediaDefault(id=1, recipe_id=recipe.id))
        session.flush()
        return {"recipe": recipe_out(recipe, session)}

    return execute(request, data, "lc_default", work)


def consume_agar(session, op, code, used_date):
    """One ready plate supplies one complete operation; destinations already exist."""
    reason = f"Agar consumed by transfer operation {op.id}"
    row = session.scalar(
        select(PreparedMaterial).where(PreparedMaterial.physical_id == code)
    )
    data = FinishInput(
        request_key=op.request_key,
        action="complete",
        action_date=used_date,
        reason=reason,
    )
    if row:
        finish(session, op, row, data)
    else:
        set_lifecycle(session, "physical", code, "completed")
        close_source_balance(session, op, "physical", code, reason)
    date_value = used_date.isoformat() if used_date else None
    set_phase(session, "physical", code, "used", date_value)
    release_label(session, "physical", code, date_value, reason)
    event(session, "physical", code, "used", reason)
