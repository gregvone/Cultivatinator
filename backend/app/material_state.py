"""Read-only lifecycle/balance projection, without importing API modules."""

from sqlalchemy import select
from .preparation_models import StockItem, MaterialLifecycle, PreparedMaterial


def lifecycle(session, kind, code):
    if kind not in {"physical", "spawn"}:
        return None
    column = (
        MaterialLifecycle.physical_id
        if kind == "physical"
        else MaterialLifecycle.spawn_id
    )
    return session.scalar(select(MaterialLifecycle).where(column == code))


def material_state(session, kind, code):
    state = lifecycle(session, kind, code)
    stock = None
    if kind in {"physical", "spores"}:
        column = StockItem.physical_id if kind == "physical" else StockItem.spore_id
        stock = session.scalar(select(StockItem).where(column == code))
    prepared = None
    if kind in {"physical", "spawn"}:
        column = (
            PreparedMaterial.physical_id
            if kind == "physical"
            else PreparedMaterial.spawn_id
        )
        prepared = session.scalar(select(PreparedMaterial).where(column == code))
    return {
        "lifecycle": state.state if state else "active",
        "stock_item_id": stock.id if stock else None,
        "remaining_quantity": stock.available if stock else None,
        "remaining_unit": stock.unit if stock else None,
        "balance_tracked": stock is not None,
        "prepared_id": prepared.id if prepared else None,
    }
