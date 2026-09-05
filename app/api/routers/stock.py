"""Stock & production module router — full refactor with permissions, snapshots, supply workflow."""
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.api.deps import get_current_user, require_permission, require_role
from app.models import (
    RawMaterial, Recipe, RecipeItem, Employee, EmployeeEstablishment, Shift, ShiftProduction,
    ShiftConsumption, StockLevel, StockMovement, Inventory, SupplyRequest, SupplyRequestItem,
    Establishment, Cocktail, Packaging, Alert, User, ShiftSlot, ShiftActionLog, Notification,
)
from app.schemas import (
    RawMaterialOut, RawMaterialCreate, RawMaterialUpdate,
    PackagingOut, PackagingCreate,
    RecipeOut, RecipeCreate,
    EmployeeOut, EmployeeCreate, EmployeeUpdate,
    ShiftOut, ShiftOpen, ShiftClose, ShiftUpdate, ShiftConsumptionOut,
    ShiftProductionOut, ShiftProductionCreate,
    ShiftActionLogOut, ShiftActionLogCreate,
    ShiftSlotOut, ShiftSlotCreate, ShiftSlotUpdate,
    StockLevelOut, StockMovementOut, SupplyCreate,
    StockDashboardOut, AutonomyOut,
    InventoryCreate, InventoryOut,
    SupplyRequestCreate, SupplyRequestOut, SupplyRequestStatusUpdate,
    ProductionAnalyticsOut, ConsumptionAnalyticsOut,
)
from app.services.stock_service import (
    compute_shift_consumption, validate_shift_transactional,
    compute_avg_daily_consumption, compute_autonomy, compute_stock_value,
    create_movement, recompute_theoretical_stock,
    check_and_create_stock_alerts, resolve_alerts_for_stock,
    suggest_supply_quantity,
)
from app.services.audit_service import log_audit

router = APIRouter(tags=["stock"])


# ══════════════════════════════════════════════
# RAW MATERIALS + PACKAGING
# ══════════════════════════════════════════════
@router.get("/raw-materials", response_model=list[RawMaterialOut])
def list_raw_materials(db: Session = Depends(get_db)):
    return (
        db.query(RawMaterial)
        .options(selectinload(RawMaterial.packagings))
        .filter(RawMaterial.deleted_at == None)
        .order_by(RawMaterial.category, RawMaterial.name)
        .all()
    )


@router.post("/raw-materials", response_model=RawMaterialOut)
def create_raw_material(body: RawMaterialCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("raw_materials"))):
    rm = RawMaterial(
        name=body.name, category=body.category, base_unit=body.base_unit,
        cost_per_unit=body.cost_per_unit, min_threshold=body.min_threshold,
        max_threshold=body.max_threshold, supplier=body.supplier,
    )
    db.add(rm)
    db.flush()
    for pkg in body.packagings:
        db.add(Packaging(
            raw_material_id=rm.id, name=pkg.name,
            quantity_per_package=pkg.quantity_per_package, unit=pkg.unit,
            cost_per_package=pkg.cost_per_package, is_default=pkg.is_default,
        ))
    db.commit()
    db.refresh(rm)
    log_audit(db, user.id, "CREATE", "raw_material", rm.id, after_data={"name": rm.name})
    db.commit()
    return rm


@router.put("/raw-materials/{rm_id}", response_model=RawMaterialOut)
def update_raw_material(rm_id: str, body: RawMaterialUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("raw_materials"))):
    rm = db.query(RawMaterial).filter(RawMaterial.id == rm_id, RawMaterial.deleted_at == None).first()
    if not rm:
        raise HTTPException(404, "Raw material not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(rm, k, v)
    db.commit()
    db.refresh(rm)
    return rm


@router.delete("/raw-materials/{rm_id}")
def delete_raw_material(rm_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("raw_materials"))):
    rm = db.query(RawMaterial).filter(RawMaterial.id == rm_id, RawMaterial.deleted_at == None).first()
    if not rm:
        raise HTTPException(404, "Raw material not found")
    # Cannot delete if used in recipe history
    recipe_count = db.query(RecipeItem).filter(RecipeItem.raw_material_id == rm_id).count()
    if recipe_count > 0:
        raise HTTPException(400, f"Cannot delete raw material used in {recipe_count} recipe(s). Use soft-delete instead.")
    rm.is_active = False
    rm.deleted_at = datetime.utcnow()
    db.commit()
    log_audit(db, user.id, "DELETE", "raw_material", rm_id)
    db.commit()
    return {"ok": True}


# ── Packaging ──
@router.post("/raw-materials/{rm_id}/packagings", response_model=PackagingOut)
def add_packaging(rm_id: str, body: PackagingCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("raw_materials"))):
    rm = db.query(RawMaterial).filter(RawMaterial.id == rm_id, RawMaterial.deleted_at == None).first()
    if not rm:
        raise HTTPException(404, "Raw material not found")
    pkg = Packaging(raw_material_id=rm_id, **body.model_dump())
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.delete("/raw-materials/{rm_id}/packagings/{pkg_id}")
def delete_packaging(rm_id: str, pkg_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("raw_materials"))):
    pkg = db.query(Packaging).filter(Packaging.id == pkg_id, Packaging.raw_material_id == rm_id).first()
    if not pkg:
        raise HTTPException(404, "Packaging not found")
    db.delete(pkg)
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════
# RECIPES (with versioning)
# ══════════════════════════════════════════════
@router.get("/recipes", response_model=list[RecipeOut])
def list_recipes(db: Session = Depends(get_db)):
    return db.query(Recipe).options(selectinload(Recipe.items).selectinload(RecipeItem.raw_material)).all()


@router.get("/recipes/cocktail/{cocktail_id}", response_model=RecipeOut | None)
def get_recipe_by_cocktail(cocktail_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Recipe)
        .options(selectinload(Recipe.items).selectinload(RecipeItem.raw_material))
        .filter(Recipe.cocktail_id == cocktail_id)
        .first()
    )


@router.put("/recipes", response_model=RecipeOut)
def upsert_recipe(body: RecipeCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("recipes"))):
    recipe = db.query(Recipe).filter(Recipe.cocktail_id == body.cocktail_id).first()
    if recipe:
        # Version increment on change
        for item in recipe.items:
            db.delete(item)
        db.flush()
        recipe.version += 1
    else:
        recipe = Recipe(cocktail_id=body.cocktail_id, version=1)
        db.add(recipe)
        db.flush()
    for item_data in body.items:
        item = RecipeItem(
            recipe_id=recipe.id,
            raw_material_id=item_data.raw_material_id,
            quantity=item_data.quantity,
            waste_percentage=item_data.waste_percentage,
        )
        db.add(item)
    recipe.updated_at = datetime.utcnow()
    recipe.updated_by = user.id
    db.commit()
    db.refresh(recipe)
    log_audit(db, user.id, "UPDATE", "recipe", recipe.id, after_data={"version": recipe.version, "cocktail_id": recipe.cocktail_id})
    db.commit()
    return recipe


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("recipes"))):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    db.delete(recipe)
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════
# EMPLOYEES (with multi-establishment)
# ══════════════════════════════════════════════
@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db)):
    emps = db.query(Employee).filter(Employee.deleted_at == None).all()
    result = []
    for emp in emps:
        est_links = db.query(EmployeeEstablishment).filter(EmployeeEstablishment.employee_id == emp.id).all()
        est_ids = [link.establishment_id for link in est_links]
        result.append(EmployeeOut(
            id=emp.id, first_name=emp.first_name, last_name=emp.last_name,
            phone=emp.phone, email=emp.email, role=emp.role, is_active=emp.is_active,
            establishment_ids=est_ids,
        ))
    return result


@router.post("/employees", response_model=EmployeeOut)
def create_employee(body: EmployeeCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    emp = Employee(
        first_name=body.first_name, last_name=body.last_name,
        phone=body.phone, email=body.email, role=body.role,
    )
    db.add(emp)
    db.flush()
    for est_id in body.establishment_ids:
        db.add(EmployeeEstablishment(employee_id=emp.id, establishment_id=est_id))
    db.commit()
    db.refresh(emp)
    return EmployeeOut(
        id=emp.id, first_name=emp.first_name, last_name=emp.last_name,
        phone=emp.phone, email=emp.email, role=emp.role, is_active=emp.is_active,
        establishment_ids=body.establishment_ids,
    )


@router.put("/employees/{emp_id}", response_model=EmployeeOut)
def update_employee(emp_id: str, body: EmployeeUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    emp = db.query(Employee).filter(Employee.id == emp_id, Employee.deleted_at == None).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    for k, v in body.model_dump(exclude_unset=True, exclude={"establishment_ids"}).items():
        setattr(emp, k, v)
    if body.establishment_ids is not None:
        # Replace establishment links
        db.query(EmployeeEstablishment).filter(EmployeeEstablishment.employee_id == emp_id).delete()
        for est_id in body.establishment_ids:
            db.add(EmployeeEstablishment(employee_id=emp_id, establishment_id=est_id))
    db.commit()
    db.refresh(emp)
    est_links = db.query(EmployeeEstablishment).filter(EmployeeEstablishment.employee_id == emp.id).all()
    return EmployeeOut(
        id=emp.id, first_name=emp.first_name, last_name=emp.last_name,
        phone=emp.phone, email=emp.email, role=emp.role, is_active=emp.is_active,
        establishment_ids=[l.establishment_id for l in est_links],
    )


@router.delete("/employees/{emp_id}")
def delete_employee(emp_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    emp = db.query(Employee).filter(Employee.id == emp_id, Employee.deleted_at == None).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    emp.is_active = False
    emp.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════
# SHIFTS — open / close / validate (transactional)
# ══════════════════════════════════════════════
@router.get("/shifts", response_model=list[ShiftOut])
def list_shifts(
    establishment_id: str | None = Query(None),
    status: str | None = Query(None),
    employee_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Shift).options(selectinload(Shift.productions))
    if establishment_id:
        q = q.filter(Shift.establishment_id == establishment_id)
    if status:
        q = q.filter(Shift.status == status)
    if employee_id:
        q = q.filter(Shift.employee_id == employee_id)
    return q.order_by(Shift.opened_at.desc()).all()


@router.get("/shifts/{shift_id}", response_model=ShiftOut)
def get_shift(shift_id: str, db: Session = Depends(get_db)):
    shift = db.query(Shift).options(selectinload(Shift.productions)).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    return shift


@router.post("/shifts", response_model=ShiftOut)
def open_shift(body: ShiftOpen, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from datetime import date as date_cls, datetime as dt_cls
    # If closed_at is provided, create the shift as already closed
    status = "closed" if body.closed_at else "open"
    shift = Shift(
        establishment_id=body.establishment_id,
        employee_id=body.employee_id,
        notes=body.notes,
        status=status,
        date=body.shift_date or date_cls.today(),
        opened_at=body.opened_at or dt_cls.utcnow(),
        closed_at=body.closed_at,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.put("/shifts/{shift_id}", response_model=ShiftOut)
def update_shift(shift_id: str, body: ShiftUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Update a shift (admin can modify establishment, employee, times, status, notes)."""
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    data = body.model_dump(exclude_unset=True)
    # Map shift_date -> date column
    if "shift_date" in data:
        data["date"] = data.pop("shift_date")
    for k, v in data.items():
        setattr(shift, k, v)
    db.commit()
    db.refresh(shift)
    return shift


@router.delete("/shifts/{shift_id}")
def delete_shift(shift_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Delete a shift and its related records."""
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    # Delete associated alerts (FK constraint, no cascade at DB level)
    db.query(Alert).filter(Alert.shift_id == shift_id).delete()
    # Delete associated productions, consumptions, action_logs, recipe_snapshots
    for p in shift.productions:
        db.delete(p)
    for c in shift.consumptions:
        db.delete(c)
    for a in shift.action_logs:
        db.delete(a)
    for s in shift.recipe_snapshots:
        db.delete(s)
    db.delete(shift)
    db.commit()
    return {"ok": True}


@router.post("/shifts/{shift_id}/close", response_model=ShiftOut)
def close_shift(shift_id: str, body: ShiftClose, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    if shift.status != "open":
        raise HTTPException(400, f"Shift is {shift.status}, not open")
    for p in shift.productions:
        db.delete(p)
    db.flush()
    for prod in body.productions:
        db.add(ShiftProduction(shift_id=shift.id, cocktail_id=prod.cocktail_id, quantity=prod.quantity))
    shift.status = "closed"
    shift.closed_at = datetime.utcnow()
    if body.notes:
        shift.notes = body.notes
    db.commit()
    db.refresh(shift)
    return shift


@router.post("/my/shifts/{shift_id}/close", response_model=ShiftOut)
def close_my_shift(shift_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Bartender closes their own shift.
    Computes final production counts from action logs (non-cancelled deltas)."""
    try:
        emp = _get_employee_for_user(db, user)
        shift = db.query(Shift).filter(Shift.id == shift_id).first()
        if not shift:
            raise HTTPException(404, "Shift not found")
        if shift.employee_id != emp.id:
            raise HTTPException(403, "This shift does not belong to you")
        if shift.status != "open":
            raise HTTPException(400, f"Shift is {shift.status}, not open")

        # Compute final quantities from action logs
        logs = db.query(ShiftActionLog).filter(
            ShiftActionLog.shift_id == shift.id,
            ShiftActionLog.cancelled_at.is_(None),
        ).all()
        by_cocktail: dict[str, int] = {}
        for log in logs:
            by_cocktail[log.cocktail_id] = by_cocktail.get(log.cocktail_id, 0) + log.delta

        # Replace productions with computed totals
        for p in shift.productions:
            db.delete(p)
        db.flush()
        for cocktail_id, qty in by_cocktail.items():
            if qty > 0:
                # Freeze recipe snapshot
                recipe_snapshot = None
                recipe = db.query(Recipe).filter(Recipe.cocktail_id == cocktail_id).first()
                if recipe:
                    items = db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe.id).all()
                    recipe_snapshot = {
                        "recipe_id": recipe.id,
                        "cocktail_id": cocktail_id,
                        "items": [{"raw_material_id": ri.raw_material_id, "quantity": ri.quantity} for ri in items],
                    }
                db.add(ShiftProduction(
                    shift_id=shift.id, cocktail_id=cocktail_id, quantity=qty,
                    recipe_snapshot=recipe_snapshot,
                ))

        shift.status = "closed"
        shift.closed_at = datetime.utcnow()
        db.commit()
        db.refresh(shift)

        # §10 — Notify managers that the shift was closed
        est = db.query(Establishment).filter(Establishment.id == shift.establishment_id).first()
        est_name = est.name if est else "—"
        emp_name = f"{emp.first_name} {emp.last_name}"
        managers = db.query(EmployeeEstablishment).filter(
            EmployeeEstablishment.establishment_id == shift.establishment_id
        ).all()
        for link in managers:
            mgr = db.query(Employee).filter(Employee.id == link.employee_id).first()
            if mgr and mgr.user_id and mgr.role in ("ESTABLISHMENT_MANAGER", "ADMIN"):
                db.add(Notification(
                    user_id=mgr.user_id,
                    type="SHIFT_CLOSED",
                    message=f"{emp_name} a clôturé son shift — {est_name}",
                    establishment_id=shift.establishment_id,
                    shift_id=shift.id,
                ))
        db.commit()

        # Reload shift with all relations for response
        shift = db.query(Shift).options(
            selectinload(Shift.productions).selectinload(ShiftProduction.cocktail),
            selectinload(Shift.action_logs),
        ).filter(Shift.id == shift_id).first()
        return shift
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Close shift error: {str(e)}")


@router.post("/shifts/{shift_id}/validate", response_model=ShiftOut)
def validate_shift(shift_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("shifts"))):
    shift = db.query(Shift).options(selectinload(Shift.productions)).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    if shift.status == "validated":
        raise HTTPException(400, "Shift already validated — cannot validate twice")
    if shift.status != "closed":
        raise HTTPException(400, "Shift must be closed before validation")
    try:
        validate_shift_transactional(db, shift, user.id)
        log_audit(db, user.id, "VALIDATE", "shift", shift.id, after_data={"status": "validated"})
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Validation failed: {e}")
    db.refresh(shift)
    return shift


@router.get("/shifts/{shift_id}/consumption", response_model=list[ShiftConsumptionOut])
def get_shift_consumption(shift_id: str, db: Session = Depends(get_db)):
    return db.query(ShiftConsumption).filter(ShiftConsumption.shift_id == shift_id).all()


# ══════════════════════════════════════════════
# SHIFT SLOTS — predefined time slots (admin CRUD)
# ══════════════════════════════════════════════
@router.get("/shift-slots", response_model=list[ShiftSlotOut])
def list_shift_slots(db: Session = Depends(get_db)):
    return db.query(ShiftSlot).filter(ShiftSlot.deleted_at == None).order_by(ShiftSlot.sort_order, ShiftSlot.start_time).all()


@router.post("/shift-slots", response_model=ShiftSlotOut)
def create_shift_slot(body: ShiftSlotCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    slot = ShiftSlot(
        name=body.name,
        name_fr=body.name_fr,
        name_en=body.name_en,
        name_ar=body.name_ar,
        start_time=body.start_time,
        end_time=body.end_time,
        is_overnight=body.is_overnight,
        sort_order=body.sort_order,
        is_active=body.is_active,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


@router.put("/shift-slots/{slot_id}", response_model=ShiftSlotOut)
def update_shift_slot(slot_id: str, body: ShiftSlotUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    slot = db.query(ShiftSlot).filter(ShiftSlot.id == slot_id, ShiftSlot.deleted_at == None).first()
    if not slot:
        raise HTTPException(404, "Shift slot not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(slot, k, v)
    db.commit()
    db.refresh(slot)
    return slot


@router.delete("/shift-slots/{slot_id}")
def delete_shift_slot(slot_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    slot = db.query(ShiftSlot).filter(ShiftSlot.id == slot_id, ShiftSlot.deleted_at == None).first()
    if not slot:
        raise HTTPException(404, "Shift slot not found")
    slot.is_active = False
    slot.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════
# EMPLOYEE SELF-SERVICE — "Mon Shift" endpoints
# Bartenders see their own shifts and add productions in real-time
# ══════════════════════════════════════════════

def _get_employee_for_user(db: Session, user: User) -> Employee:
    """Find the Employee record linked to the current User."""
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not emp:
        raise HTTPException(403, "No employee profile linked to your account")
    return emp


@router.get("/my/employee", response_model=EmployeeOut)
def get_my_employee_profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get the employee profile of the logged-in user."""
    emp = _get_employee_for_user(db, user)
    est_links = db.query(EmployeeEstablishment).filter(EmployeeEstablishment.employee_id == emp.id).all()
    est_ids = [link.establishment_id for link in est_links]
    return EmployeeOut(
        id=emp.id, first_name=emp.first_name, last_name=emp.last_name,
        phone=emp.phone, email=emp.email, role=emp.role, is_active=emp.is_active,
        establishment_ids=est_ids,
    )


@router.get("/my/shifts", response_model=list[ShiftOut])
def get_my_shifts(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List shifts of the logged-in employee."""
    emp = _get_employee_for_user(db, user)
    q = (
        db.query(Shift)
        .options(selectinload(Shift.productions).selectinload(ShiftProduction.cocktail))
        .filter(Shift.employee_id == emp.id)
    )
    if status:
        q = q.filter(Shift.status == status)
    return q.order_by(Shift.opened_at.desc()).all()


@router.get("/my/shifts/{shift_id}", response_model=ShiftOut)
def get_my_shift_detail(
    shift_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific shift — only if it belongs to the logged-in employee."""
    emp = _get_employee_for_user(db, user)
    shift = (
        db.query(Shift)
        .options(selectinload(Shift.productions).selectinload(ShiftProduction.cocktail))
        .filter(Shift.id == shift_id)
        .first()
    )
    if not shift:
        raise HTTPException(404, "Shift not found")
    if shift.employee_id != emp.id:
        raise HTTPException(403, "This shift does not belong to you")
    return shift


@router.post("/my/shifts/{shift_id}/productions", response_model=ShiftProductionOut)
def add_production_to_my_shift(
    shift_id: str,
    body: ShiftProductionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a cocktail production to an open shift in real-time.
    Records: cocktail, quantity, timestamp, shift, employee (via shift).
    Also freezes a recipe snapshot for historical consumption accuracy."""
    emp = _get_employee_for_user(db, user)
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    if shift.employee_id != emp.id:
        raise HTTPException(403, "This shift does not belong to you")
    if shift.status != "open":
        raise HTTPException(400, f"Shift is {shift.status} — you can only add productions to an open shift")

    # Validate cocktail exists
    cocktail = db.query(Cocktail).filter(Cocktail.id == body.cocktail_id).first()
    if not cocktail:
        raise HTTPException(404, "Cocktail not found")

    # Freeze recipe snapshot at production time (§5 — versioning)
    recipe_snapshot = None
    recipe = db.query(Recipe).filter(Recipe.cocktail_id == body.cocktail_id).first()
    if recipe:
        items = db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe.id).all()
        recipe_snapshot = {
            "recipe_id": recipe.id,
            "cocktail_id": body.cocktail_id,
            "items": [
                {"raw_material_id": ri.raw_material_id, "quantity": ri.quantity}
                for ri in items
            ],
        }

    prod = ShiftProduction(
        shift_id=shift.id,
        cocktail_id=body.cocktail_id,
        quantity=body.quantity,
        recipe_snapshot=recipe_snapshot,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    # Build response with cocktail info
    from app.schemas import CocktailBrief
    return ShiftProductionOut(
        id=prod.id,
        shift_id=prod.shift_id,
        cocktail_id=prod.cocktail_id,
        quantity=prod.quantity,
        created_at=prod.created_at,
        recipe_snapshot=prod.recipe_snapshot,
        cocktail=CocktailBrief(id=cocktail.id, name=cocktail.name, image_url=cocktail.image_url),
    )


@router.post("/my/shifts/{shift_id}/actions", response_model=ShiftActionLogOut)
def add_shift_action(
    shift_id: str,
    body: ShiftActionLogCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Log a +/− action on a shift. Idempotent via client-generated UUID.
    Used by the offline-first sync mechanism (§3)."""
    emp = _get_employee_for_user(db, user)
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    if shift.employee_id != emp.id:
        raise HTTPException(403, "This shift does not belong to you")
    if shift.status != "open":
        raise HTTPException(400, f"Shift is {shift.status} — actions only allowed on open shifts")

    # Idempotency: check if action with this client UUID already exists
    existing = db.query(ShiftActionLog).filter(ShiftActionLog.id == body.id).first()
    if existing:
        return existing  # Already synced — return as-is

    # Validate cocktail exists
    cocktail = db.query(Cocktail).filter(Cocktail.id == body.cocktail_id).first()
    if not cocktail:
        raise HTTPException(404, "Cocktail not found")

    log = ShiftActionLog(
        id=body.id,  # client-generated UUID for idempotency
        shift_id=shift.id,
        cocktail_id=body.cocktail_id,
        delta=body.delta,
        variant=body.variant,
        synced_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/my/shifts/{shift_id}/actions", response_model=list[ShiftActionLogOut])
def list_shift_actions(
    shift_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all action logs for a shift (for history drawer + sync reconciliation)."""
    emp = _get_employee_for_user(db, user)
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(404, "Shift not found")
    if shift.employee_id != emp.id:
        raise HTTPException(403, "This shift does not belong to you")
    return db.query(ShiftActionLog).filter(ShiftActionLog.shift_id == shift_id).order_by(ShiftActionLog.created_at.desc()).all()


@router.post("/my/actions/{action_id}/cancel", response_model=ShiftActionLogOut)
def cancel_shift_action(
    action_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cancel a shift action (undo). Only allowed within 5 minutes of creation
    and only if the shift is still open."""
    emp = _get_employee_for_user(db, user)
    log = db.query(ShiftActionLog).filter(ShiftActionLog.id == action_id).first()
    if not log:
        raise HTTPException(404, "Action not found")
    shift = db.query(Shift).filter(Shift.id == log.shift_id).first()
    if not shift or shift.employee_id != emp.id:
        raise HTTPException(403, "This action does not belong to you")
    if shift.status != "open":
        raise HTTPException(400, f"Shift is {shift.status} — cannot cancel actions on a non-open shift")
    if log.cancelled_at:
        raise HTTPException(400, "Action already cancelled")
    # 5-minute rule
    elapsed = (datetime.utcnow() - log.created_at).total_seconds()
    if elapsed > 300:
        raise HTTPException(400, "Cannot cancel actions older than 5 minutes")
    log.cancelled_at = datetime.utcnow()
    db.commit()
    db.refresh(log)
    return log


@router.delete("/my/productions/{production_id}")
def delete_my_production(
    production_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a production entry from an open shift (bartender made a mistake)."""
    emp = _get_employee_for_user(db, user)
    prod = db.query(ShiftProduction).filter(ShiftProduction.id == production_id).first()
    if not prod:
        raise HTTPException(404, "Production not found")
    shift = db.query(Shift).filter(Shift.id == prod.shift_id).first()
    if not shift or shift.employee_id != emp.id:
        raise HTTPException(403, "This production does not belong to you")
    if shift.status != "open":
        raise HTTPException(400, f"Shift is {shift.status} — cannot modify productions on a non-open shift")
    db.delete(prod)
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════
# STOCK LEVELS + MOVEMENTS
# ══════════════════════════════════════════════
@router.get("/stock", response_model=list[StockLevelOut])
def list_stock(db: Session = Depends(get_db)):
    return db.query(StockLevel).options(selectinload(StockLevel.raw_material)).all()


@router.get("/stock/establishment/{est_id}", response_model=list[StockLevelOut])
def list_stock_by_establishment(est_id: str, db: Session = Depends(get_db)):
    return (
        db.query(StockLevel)
        .options(selectinload(StockLevel.raw_material))
        .filter(StockLevel.establishment_id == est_id)
        .all()
    )


@router.get("/stock/movements", response_model=list[StockMovementOut])
def list_movements(
    establishment_id: str | None = Query(None),
    raw_material_id: str | None = Query(None),
    movement_type: str | None = Query(None),
    limit: int = Query(200, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(StockMovement)
    if establishment_id:
        q = q.filter(StockMovement.establishment_id == establishment_id)
    if raw_material_id:
        q = q.filter(StockMovement.raw_material_id == raw_material_id)
    if movement_type:
        q = q.filter(StockMovement.movement_type == movement_type)
    return q.order_by(StockMovement.created_at.desc()).limit(limit).all()


@router.post("/stock/supply", response_model=StockMovementOut)
def record_supply(body: SupplyCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("stock"))):
    mv = create_movement(
        db,
        establishment_id=body.establishment_id,
        raw_material_id=body.raw_material_id,
        movement_type="SUPPLY_RECEIPT",
        quantity=body.quantity,  # positive = in
        unit=body.unit,
        reference=body.reference,
        reference_type="manual",
        created_by=user.id,
    )
    # Resolve alerts if stock is now above threshold
    resolve_alerts_for_stock(db, body.establishment_id, body.raw_material_id)
    db.commit()
    db.refresh(mv)
    return mv


# ── Dashboard + Autonomy ──
@router.get("/stock/dashboard", response_model=StockDashboardOut)
def stock_dashboard(db: Session = Depends(get_db), user: User = Depends(require_permission("stock"))):
    levels = db.query(StockLevel).options(selectinload(StockLevel.raw_material)).all()
    total_value = sum((l.theoretical_qty or 0) * (l.raw_material.cost_per_unit or 0) for l in levels)
    critical = sum(1 for l in levels if l.raw_material and l.theoretical_qty <= l.raw_material.min_threshold and l.theoretical_qty > 0)
    out_of_stock = sum(1 for l in levels if l.theoretical_qty <= 0)
    pending = db.query(SupplyRequest).filter(SupplyRequest.status.in_(["PENDING", "APPROVED", "PARTIALLY_DELIVERED"])).count()

    by_est = []
    ests = db.query(Establishment).filter(Establishment.deleted_at == None).all()
    for est in ests:
        est_levels = [l for l in levels if l.establishment_id == est.id]
        val = sum((l.theoretical_qty or 0) * (l.raw_material.cost_per_unit or 0) for l in est_levels)
        by_est.append({"establishment_id": est.id, "name": est.name, "value": val, "items": len(est_levels)})

    # Unresolved alerts
    alerts = db.query(Alert).filter(Alert.is_resolved == False).order_by(Alert.created_at.desc()).limit(10).all()
    alert_list = [{"id": a.id, "type": a.type, "severity": a.severity, "message": a.message} for a in alerts]

    return StockDashboardOut(
        total_value=total_value, total_items=len(levels),
        critical_items=critical, out_of_stock=out_of_stock,
        by_establishment=by_est, pending_requests=pending, alerts=alert_list,
    )


@router.get("/stock/establishment/{est_id}/autonomy", response_model=list[AutonomyOut])
def stock_autonomy(est_id: str, db: Session = Depends(get_db)):
    levels = (
        db.query(StockLevel)
        .options(selectinload(StockLevel.raw_material))
        .filter(StockLevel.establishment_id == est_id)
        .all()
    )
    result = []
    for l in levels:
        info = compute_autonomy(db, est_id, l.raw_material_id)
        result.append(AutonomyOut(
            raw_material_id=l.raw_material_id,
            name=l.raw_material.name if l.raw_material else "",
            current_qty=info["current_qty"],
            avg_daily_consumption=info["avg_daily_consumption"],
            autonomy_days=info["autonomy_days"],
            status=info["status"],
        ))
    return result


# ══════════════════════════════════════════════
# INVENTORY
# ══════════════════════════════════════════════
@router.get("/inventories", response_model=list[InventoryOut])
def list_inventories(
    establishment_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Inventory)
    if establishment_id:
        q = q.filter(Inventory.establishment_id == establishment_id)
    return q.order_by(Inventory.created_at.desc()).all()


@router.post("/inventories", response_model=InventoryOut)
def create_inventory(body: InventoryCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("inventory"))):
    level = (
        db.query(StockLevel)
        .filter(StockLevel.establishment_id == body.establishment_id, StockLevel.raw_material_id == body.raw_material_id)
        .first()
    )
    theoretical = level.theoretical_qty if level else 0
    variance = body.counted_qty - theoretical

    inv = Inventory(
        establishment_id=body.establishment_id,
        raw_material_id=body.raw_material_id,
        counted_qty=body.counted_qty,
        theoretical_qty=theoretical,
        variance=variance,
        reason=body.reason,
        note=body.note,
        created_by=user.id,
    )
    db.add(inv)

    # Update real_qty on stock level
    if level:
        level.real_qty = body.counted_qty
        level.last_inventory_at = datetime.utcnow()
        level.updated_at = datetime.utcnow()

    # Create INVENTORY_ADJUSTMENT movement if there's a variance
    if abs(variance) > 0.001:
        create_movement(
            db,
            establishment_id=body.establishment_id,
            raw_material_id=body.raw_material_id,
            movement_type="INVENTORY_ADJUSTMENT",
            quantity=variance,  # positive or negative
            unit=level.unit if level else "ml",
            reference=f"inventory:{inv.id}",
            reference_type="inventory",
            reference_id=inv.id,
            created_by=user.id,
            previous_theoretical_qty=theoretical,
            counted_qty=body.counted_qty,
        )

    # Create alert if variance is significant
    if abs(variance) > 0.01:
        rm = db.query(RawMaterial).filter(RawMaterial.id == body.raw_material_id).first()
        rm_name = rm.name if rm else "Unknown"
        db.add(Alert(
            type="INVENTORY_VARIANCE",
            severity="warning" if abs(variance) < theoretical * 0.1 else "critical",
            establishment_id=body.establishment_id,
            raw_material_id=body.raw_material_id,
            message=f"Écart inventaire {rm_name}: théorique {theoretical}, compté {body.counted_qty}, écart {variance}",
        ))

    db.commit()
    db.refresh(inv)
    log_audit(db, user.id, "CREATE", "inventory", inv.id, after_data={"variance": variance})
    db.commit()
    return inv


# ══════════════════════════════════════════════
# SUPPLY REQUESTS — full workflow with items
# ══════════════════════════════════════════════
@router.get("/supply-requests", response_model=list[SupplyRequestOut])
def list_supply_requests(
    establishment_id: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(SupplyRequest).options(selectinload(SupplyRequest.items).selectinload(SupplyRequestItem.raw_material))
    if establishment_id:
        q = q.filter(SupplyRequest.establishment_id == establishment_id)
    if status:
        q = q.filter(SupplyRequest.status == status)
    return q.order_by(SupplyRequest.created_at.desc()).all()


@router.get("/supply-requests/suggest/{est_id}", response_model=list[dict])
def suggest_supply(est_id: str, db: Session = Depends(get_db)):
    """Suggest supply requests based on stock levels vs thresholds."""
    levels = (
        db.query(StockLevel)
        .options(selectinload(StockLevel.raw_material))
        .filter(StockLevel.establishment_id == est_id)
        .all()
    )
    suggestions = []
    for l in levels:
        rm = l.raw_material
        if not rm:
            continue
        info = suggest_supply_quantity(db, est_id, rm.id)
        if info["suggested"] > 0:
            suggestions.append({
                "raw_material_id": rm.id,
                "name": rm.name,
                "current_qty": l.theoretical_qty,
                "suggested_qty": info["suggested"],
                "unit": rm.base_unit,
                "min_threshold": rm.min_threshold,
                "max_threshold": rm.max_threshold,
                "reason": info["reason"],
            })
    return suggestions


@router.post("/supply-requests", response_model=SupplyRequestOut)
def create_supply_request(body: SupplyRequestCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("supply"))):
    req = SupplyRequest(
        establishment_id=body.establishment_id,
        requested_by=user.id,
        status="PENDING",
        notes=body.notes,
    )
    db.add(req)
    db.flush()
    for item in body.items:
        db.add(SupplyRequestItem(
            supply_request_id=req.id,
            raw_material_id=item.raw_material_id,
            requested_quantity=item.requested_quantity,
            suggested_quantity=item.suggested_quantity,
            unit=item.unit,
        ))
    db.commit()
    db.refresh(req)
    log_audit(db, user.id, "CREATE", "supply_request", req.id)
    db.commit()
    return req


@router.patch("/supply-requests/{req_id}/status", response_model=SupplyRequestOut)
def update_supply_status(req_id: str, body: SupplyRequestStatusUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("supply"))):
    req = (
        db.query(SupplyRequest)
        .options(selectinload(SupplyRequest.items).selectinload(SupplyRequestItem.raw_material))
        .filter(SupplyRequest.id == req_id)
        .first()
    )
    if not req:
        raise HTTPException(404, "Supply request not found")

    old_status = req.status
    new_status = body.status

    # State machine validation
    valid_transitions = {
        "DRAFT": ["PENDING"],
        "PENDING": ["APPROVED", "REJECTED", "CANCELLED"],
        "APPROVED": ["PARTIALLY_DELIVERED", "DELIVERED", "CANCELLED"],
        "PARTIALLY_DELIVERED": ["DELIVERED", "CANCELLED"],
    }
    if new_status not in valid_transitions.get(old_status, []):
        raise HTTPException(400, f"Cannot transition from {old_status} to {new_status}")

    req.status = new_status

    # If approved, set approved quantities
    if new_status == "APPROVED" and body.approved_quantities:
        for item in req.items:
            if item.id in body.approved_quantities:
                item.approved_quantity = body.approved_quantities[item.id]
        req.approved_at = datetime.utcnow()
        req.approved_by = user.id

    # If delivered (or partially), apply to stock
    if new_status in ("DELIVERED", "PARTIALLY_DELIVERED") and body.delivered_quantities:
        for item in req.items:
            if item.id in body.delivered_quantities:
                delivered_qty = body.delivered_quantities[item.id]
                item.delivered_quantity = delivered_qty
                # Create SUPPLY_RECEIPT movement
                create_movement(
                    db,
                    establishment_id=req.establishment_id,
                    raw_material_id=item.raw_material_id,
                    movement_type="SUPPLY_RECEIPT",
                    quantity=delivered_qty,
                    unit=item.unit,
                    reference=f"supply-request:{req.id}",
                    reference_type="supply",
                    reference_id=req.id,
                    created_by=user.id,
                )
                # Resolve stock alerts
                resolve_alerts_for_stock(db, req.establishment_id, item.raw_material_id)
        if new_status == "DELIVERED":
            req.delivered_at = datetime.utcnow()

    db.commit()
    db.refresh(req)
    log_audit(db, user.id, "STATUS_CHANGE", "supply_request", req.id,
              before_data={"status": old_status}, after_data={"status": new_status})
    db.commit()
    return req


# ══════════════════════════════════════════════
# ANALYTICS — production & consumption
# ══════════════════════════════════════════════
@router.get("/analytics/production", response_model=ProductionAnalyticsOut)
def production_analytics(
    period: str = Query("week", regex="^(day|week|month)$"),
    establishment_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    days = {"day": 1, "week": 7, "month": 30}[period]
    since = datetime.utcnow() - timedelta(days=days)

    q = (
        db.query(ShiftProduction)
        .join(Shift, ShiftProduction.shift_id == Shift.id)
        .filter(Shift.opened_at >= since, Shift.status.in_(["closed", "validated"]))
    )
    if establishment_id:
        q = q.filter(Shift.establishment_id == establishment_id)
    prods = q.all()

    by_cocktail: dict[str, int] = defaultdict(int)
    by_employee: dict[str, int] = defaultdict(int)
    by_establishment: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    total = 0

    for p in prods:
        total += p.quantity
        ck = db.query(Cocktail).filter(Cocktail.id == p.cocktail_id).first()
        ck_name = ck.name if ck else "Unknown"
        by_cocktail[ck_name] += p.quantity
        shift = db.query(Shift).filter(Shift.id == p.shift_id).first()
        if shift:
            emp = db.query(Employee).filter(Employee.id == shift.employee_id).first()
            if emp:
                by_employee[f"{emp.first_name} {emp.last_name}"] += p.quantity
            est = db.query(Establishment).filter(Establishment.id == shift.establishment_id).first()
            if est:
                by_establishment[est.name] += p.quantity
            by_day[shift.opened_at.strftime("%Y-%m-%d")] += p.quantity

    return ProductionAnalyticsOut(
        period=period, total_cocktails=total,
        by_cocktail=[{"name": k, "quantity": v} for k, v in sorted(by_cocktail.items(), key=lambda x: -x[1])],
        by_employee=[{"name": k, "quantity": v} for k, v in sorted(by_employee.items(), key=lambda x: -x[1])],
        by_establishment=[{"name": k, "quantity": v} for k, v in sorted(by_establishment.items(), key=lambda x: -x[1])],
        by_day=[{"date": k, "quantity": v} for k, v in sorted(by_day.items())],
    )


@router.get("/analytics/consumption", response_model=ConsumptionAnalyticsOut)
def consumption_analytics(
    period: str = Query("week", regex="^(day|week|month)$"),
    establishment_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    days = {"day": 1, "week": 7, "month": 30}[period]
    since = datetime.utcnow() - timedelta(days=days)

    q = (
        db.query(ShiftConsumption)
        .join(Shift, ShiftConsumption.shift_id == Shift.id)
        .filter(Shift.validated_at >= since)
    )
    if establishment_id:
        q = q.filter(Shift.establishment_id == establishment_id)
    consumptions = q.all()

    by_material: dict[str, dict] = defaultdict(lambda: {"quantity": 0.0, "value": 0.0})
    by_day: dict[str, float] = defaultdict(float)
    total_value = 0.0

    for c in consumptions:
        rm = db.query(RawMaterial).filter(RawMaterial.id == c.raw_material_id).first()
        rm_name = rm.name if rm else "Unknown"
        cost = rm.cost_per_unit if rm else 0
        val = c.quantity * cost
        by_material[rm_name]["quantity"] += c.quantity
        by_material[rm_name]["value"] += val
        total_value += val
        shift = db.query(Shift).filter(Shift.id == c.shift_id).first()
        if shift and shift.validated_at:
            by_day[shift.validated_at.strftime("%Y-%m-%d")] += val

    return ConsumptionAnalyticsOut(
        period=period, total_value=total_value,
        by_material=[{"name": k, "quantity": v["quantity"], "value": v["value"]} for k, v in sorted(by_material.items(), key=lambda x: -x[1]["value"])],
        by_day=[{"date": k, "value": v} for k, v in sorted(by_day.items())],
    )


