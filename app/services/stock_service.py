"""Stock business logic: consumption calculation, stock from movements, alerts, autonomy.

Key rules:
- Stock movements are the source of truth. StockLevel.theoretical_qty is a cache.
- Recipe snapshots are created at shift validation to preserve history.
- Consumption is only applied when shift status → VALIDATED.
- All operations are transactional.
"""
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    Shift, ShiftProduction, ShiftConsumption, Recipe, RecipeItem,
    StockLevel, StockMovement, RawMaterial, Cocktail,
    RecipeSnapshot, RecipeSnapshotItem, Alert, SupplyRequest,
)


# ──────────────────────────────────────────────
# Unit conversion
# ──────────────────────────────────────────────
UNIT_TO_BASE = {
    "ml": 1.0,
    "cl": 10.0,
    "l": 1000.0,
    "g": 1.0,
    "kg": 1000.0,
    "unit": 1.0,
}


def convert_to_base(qty: float, from_unit: str, to_unit: str) -> float:
    """Convert qty from from_unit to to_unit (same dimension)."""
    if from_unit == to_unit:
        return qty
    base_from = UNIT_TO_BASE.get(from_unit, 1.0)
    base_to = UNIT_TO_BASE.get(to_unit, 1.0)
    return qty * base_from / base_to


# ──────────────────────────────────────────────
# Stock from movements (source of truth)
# ──────────────────────────────────────────────
def recompute_theoretical_stock(db: Session, establishment_id: str, raw_material_id: str) -> float:
    """Recompute theoretical stock from all movements. Returns the new value."""
    movements = (
        db.query(StockMovement)
        .filter(
            StockMovement.establishment_id == establishment_id,
            StockMovement.raw_material_id == raw_material_id,
        )
        .all()
    )
    total = sum(m.quantity for m in movements)
    
    # Update cache
    level = (
        db.query(StockLevel)
        .filter(
            StockLevel.establishment_id == establishment_id,
            StockLevel.raw_material_id == raw_material_id,
        )
        .first()
    )
    if level:
        level.theoretical_qty = total
        level.updated_at = datetime.utcnow()
    else:
        rm = db.query(RawMaterial).filter(RawMaterial.id == raw_material_id).first()
        level = StockLevel(
            establishment_id=establishment_id,
            raw_material_id=raw_material_id,
            theoretical_qty=total,
            unit=rm.base_unit if rm else "ml",
        )
        db.add(level)
    return total


def create_movement(
    db: Session,
    establishment_id: str,
    raw_material_id: str,
    movement_type: str,
    quantity: float,
    unit: str = "ml",
    reference: str | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
    created_by: str | None = None,
    previous_theoretical_qty: float | None = None,
    counted_qty: float | None = None,
) -> StockMovement:
    """Create a stock movement and update the cache."""
    mv = StockMovement(
        establishment_id=establishment_id,
        raw_material_id=raw_material_id,
        movement_type=movement_type,
        quantity=quantity,
        unit=unit,
        reference=reference,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=created_by,
        previous_theoretical_qty=previous_theoretical_qty,
        counted_qty=counted_qty,
    )
    db.add(mv)
    db.flush()
    # Update cache
    recompute_theoretical_stock(db, establishment_id, raw_material_id)
    return mv


# ──────────────────────────────────────────────
# Shift validation — the core business logic
# ──────────────────────────────────────────────
def compute_shift_consumption(db: Session, shift: Shift) -> list[dict]:
    """
    Compute raw material consumption for a shift based on productions + recipes.
    Returns list of {raw_material_id, quantity, unit, cocktail_name}.
    """
    consumption: dict[str, float] = defaultdict(float)
    material_unit: dict[str, str] = {}
    material_names: dict[str, str] = {}

    for prod in shift.productions:
        recipe = db.query(Recipe).filter(Recipe.cocktail_id == prod.cocktail_id).first()
        if not recipe:
            continue
        ck = db.query(Cocktail).filter(Cocktail.id == prod.cocktail_id).first()
        ck_name = ck.name if ck else "Unknown"

        for item in recipe.items:
            rm = item.raw_material
            if not rm:
                continue
            # Apply waste percentage
            effective_qty = item.quantity * (1 + item.waste_percentage / 100.0)
            # Quantity is already in base unit (per spec rule 9)
            total_qty = effective_qty * prod.quantity
            consumption[rm.id] += total_qty
            material_unit[rm.id] = rm.base_unit
            material_names[rm.id] = rm.name

    return [
        {
            "raw_material_id": rm_id,
            "quantity": qty,
            "unit": material_unit[rm_id],
            "name": material_names[rm_id],
        }
        for rm_id, qty in consumption.items()
    ]


def create_recipe_snapshots(db: Session, shift: Shift):
    """Create frozen recipe snapshots for each cocktail produced in this shift."""
    for prod in shift.productions:
        recipe = db.query(Recipe).filter(Recipe.cocktail_id == prod.cocktail_id).first()
        ck = db.query(Cocktail).filter(Cocktail.id == prod.cocktail_id).first()
        ck_name = ck.name if ck else "Unknown"
        version = recipe.version if recipe else 0

        snapshot = RecipeSnapshot(
            shift_id=shift.id,
            cocktail_id=prod.cocktail_id,
            cocktail_name=ck_name,
            recipe_version=version,
        )
        db.add(snapshot)
        db.flush()

        if recipe:
            for item in recipe.items:
                rm = item.raw_material
                snap_item = RecipeSnapshotItem(
                    snapshot_id=snapshot.id,
                    raw_material_id=item.raw_material_id,
                    raw_material_name=rm.name if rm else "Unknown",
                    quantity=item.quantity,
                    unit=rm.base_unit if rm else "ml",
                    waste_percentage=item.waste_percentage,
                )
                db.add(snap_item)


def validate_shift_transactional(db: Session, shift: Shift, validated_by: str) -> Shift:
    """
    Validate a shift transactionally:
    1. Check shift is closed and not already validated
    2. Create recipe snapshots
    3. Compute consumption from recipes
    4. Create stock movements (SHIFT_CONSUMPTION)
    5. Update stock cache
    6. Mark shift as validated
    
    If any error occurs, the caller should rollback — no partial movements.
    """
    if shift.status != "closed":
        raise ValueError("Shift must be closed before validation")
    if shift.status == "validated":
        raise ValueError("Shift already validated")

    # 1. Create recipe snapshots (frozen copy)
    create_recipe_snapshots(db, shift)

    # 2. Compute consumption
    consumption = compute_shift_consumption(db, shift)

    # 3. Create movements + update stock
    for item in consumption:
        create_movement(
            db,
            establishment_id=shift.establishment_id,
            raw_material_id=item["raw_material_id"],
            movement_type="SHIFT_CONSUMPTION",
            quantity=-item["quantity"],  # negative = out
            unit=item["unit"],
            reference=f"shift:{shift.id}",
            reference_type="shift",
            reference_id=shift.id,
            created_by=validated_by,
        )

        # Record consumption
        sc = ShiftConsumption(
            shift_id=shift.id,
            raw_material_id=item["raw_material_id"],
            quantity=item["quantity"],
            unit=item["unit"],
        )
        db.add(sc)

    # 4. Mark shift as validated
    shift.status = "validated"
    shift.validated_at = datetime.utcnow()
    shift.validated_by = validated_by

    # 5. Generate alerts for low/out-of-stock
    for item in consumption:
        check_and_create_stock_alerts(db, shift.establishment_id, item["raw_material_id"])

    return shift


# ──────────────────────────────────────────────
# Autonomy calculation
# ──────────────────────────────────────────────
def compute_avg_daily_consumption(
    db: Session,
    establishment_id: str,
    raw_material_id: str,
    days: int = 7,
) -> float:
    """Average daily consumption over the last N days based on shift consumptions."""
    since = datetime.utcnow() - timedelta(days=days)
    consumptions = (
        db.query(ShiftConsumption)
        .join(Shift, ShiftConsumption.shift_id == Shift.id)
        .filter(
            Shift.establishment_id == establishment_id,
            ShiftConsumption.raw_material_id == raw_material_id,
            Shift.validated_at >= since,
        )
        .all()
    )
    total = sum(c.quantity for c in consumptions)
    return total / days if days > 0 else 0


def compute_autonomy(db: Session, establishment_id: str, raw_material_id: str) -> dict:
    """Compute autonomy (days remaining) for a raw material at an establishment."""
    level = (
        db.query(StockLevel)
        .filter(
            StockLevel.establishment_id == establishment_id,
            StockLevel.raw_material_id == raw_material_id,
        )
        .first()
    )
    if not level:
        return {"autonomy_days": None, "status": "out", "current_qty": 0, "avg_daily_consumption": 0}

    avg_daily = compute_avg_daily_consumption(db, establishment_id, raw_material_id)
    current = level.theoretical_qty

    if avg_daily > 0:
        autonomy = current / avg_daily
    else:
        autonomy = None  # Non calculable

    rm = db.query(RawMaterial).filter(RawMaterial.id == raw_material_id).first()
    if current <= 0:
        status = "out"
    elif rm and current <= rm.min_threshold:
        status = "critical"
    elif rm and current <= rm.min_threshold * 1.5:
        status = "low"
    else:
        status = "ok"

    return {
        "autonomy_days": autonomy,
        "status": status,
        "current_qty": current,
        "avg_daily_consumption": avg_daily,
    }


# ──────────────────────────────────────────────
# Alerts
# ──────────────────────────────────────────────
def check_and_create_stock_alerts(db: Session, establishment_id: str, raw_material_id: str):
    """Check stock level and create alerts if needed."""
    level = (
        db.query(StockLevel)
        .filter(
            StockLevel.establishment_id == establishment_id,
            StockLevel.raw_material_id == raw_material_id,
        )
        .first()
    )
    if not level:
        return

    rm = db.query(RawMaterial).filter(RawMaterial.id == raw_material_id).first()
    rm_name = rm.name if rm else "Unknown"
    current = level.theoretical_qty

    # Check for existing unresolved alert of same type
    def has_unresolved(alert_type: str) -> bool:
        return db.query(Alert).filter(
            Alert.type == alert_type,
            Alert.establishment_id == establishment_id,
            Alert.raw_material_id == raw_material_id,
            Alert.is_resolved == False,
        ).first() is not None

    if current < 0 and not has_unresolved("NEGATIVE_STOCK"):
        db.add(Alert(
            type="NEGATIVE_STOCK",
            severity="critical",
            establishment_id=establishment_id,
            raw_material_id=raw_material_id,
            message=f"Stock négatif pour {rm_name}: {current} {level.unit} — erreur de saisie probable",
        ))
    elif current <= 0 and not has_unresolved("OUT_OF_STOCK"):
        db.add(Alert(
            type="OUT_OF_STOCK",
            severity="critical",
            establishment_id=establishment_id,
            raw_material_id=raw_material_id,
            message=f"Rupture de stock: {rm_name}",
        ))
    elif rm and current <= rm.min_threshold and not has_unresolved("LOW_STOCK"):
        db.add(Alert(
            type="LOW_STOCK",
            severity="warning",
            establishment_id=establishment_id,
            raw_material_id=raw_material_id,
            message=f"Stock faible: {rm_name} — {current} {level.unit} (seuil min: {rm.min_threshold})",
        ))


def resolve_alerts_for_stock(db: Session, establishment_id: str, raw_material_id: str):
    """Resolve stock alerts when stock is replenished."""
    alerts = db.query(Alert).filter(
        Alert.establishment_id == establishment_id,
        Alert.raw_material_id == raw_material_id,
        Alert.is_resolved == False,
        Alert.type.in_(["LOW_STOCK", "OUT_OF_STOCK", "NEGATIVE_STOCK"]),
    ).all()
    rm = db.query(RawMaterial).filter(RawMaterial.id == raw_material_id).first()
    level = db.query(StockLevel).filter(
        StockLevel.establishment_id == establishment_id,
        StockLevel.raw_material_id == raw_material_id,
    ).first()
    
    if level and rm and level.theoretical_qty > rm.min_threshold:
        for alert in alerts:
            alert.is_resolved = True
            alert.resolved_at = datetime.utcnow()


# ──────────────────────────────────────────────
# Supply suggestion
# ──────────────────────────────────────────────
def suggest_supply_quantity(db: Session, establishment_id: str, raw_material_id: str) -> dict:
    """Suggest supply quantity: max_stock - theoretical_stock (only if <= min_stock)."""
    level = db.query(StockLevel).filter(
        StockLevel.establishment_id == establishment_id,
        StockLevel.raw_material_id == raw_material_id,
    ).first()
    rm = db.query(RawMaterial).filter(RawMaterial.id == raw_material_id).first()
    
    if not rm:
        return {"suggested": 0, "reason": "unknown_material"}
    
    current = level.theoretical_qty if level else 0
    
    if current > rm.min_threshold:
        return {"suggested": 0, "reason": "above_min_threshold", "current": current, "min": rm.min_threshold}
    
    suggested = rm.max_threshold - current
    if suggested < 0:
        suggested = 0
    
    return {
        "suggested": suggested,
        "reason": "below_min_threshold",
        "current": current,
        "min": rm.min_threshold,
        "max": rm.max_threshold,
        "unit": rm.base_unit,
    }


# ──────────────────────────────────────────────
# Stock value
# ──────────────────────────────────────────────
def compute_stock_value(db: Session, establishment_id: str | None = None) -> dict:
    """Compute total stock value from stock levels."""
    q = db.query(StockLevel).join(RawMaterial, StockLevel.raw_material_id == RawMaterial.id)
    if establishment_id:
        q = q.filter(StockLevel.establishment_id == establishment_id)
    levels = q.all()
    total_value = sum(
        (lvl.theoretical_qty or 0) * (lvl.raw_material.cost_per_unit or 0)
        for lvl in levels
    )
    return {"total_value": total_value, "total_items": len(levels)}
