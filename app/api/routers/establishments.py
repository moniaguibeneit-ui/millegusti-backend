"""Establishments, menu, scans router — with soft delete + audit."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.api.deps import get_current_user, require_permission
from app.models import Establishment, MenuItem, Cocktail, ScanEvent, User, Shift
from app.schemas import (
    EstablishmentOut, EstablishmentCreate, EstablishmentUpdate,
    MenuItemOut, MenuItemCreate, MenuItemUpdate,
    ScanCreate,
)
from app.services.audit_service import log_audit

router = APIRouter(tags=["establishments"])


@router.get("/establishments", response_model=list[EstablishmentOut])
def list_establishments(db: Session = Depends(get_db)):
    establishments = db.query(Establishment).filter(Establishment.deleted_at == None).all()
    result = []
    for est in establishments:
        scans_count = db.query(ScanEvent).filter(ScanEvent.establishment_id == est.id).count()
        cocktails_count = db.query(MenuItem).filter(MenuItem.establishment_id == est.id).count()
        est.scans_count = scans_count
        est.cocktails_count = cocktails_count
        est.scans_trend = 0
        result.append(est)
    return result


@router.get("/establishments/{slug_or_id}", response_model=EstablishmentOut)
def get_establishment(slug_or_id: str, db: Session = Depends(get_db)):
    # Try by ID first (UUID format), then by slug
    est = db.query(Establishment).filter(Establishment.id == slug_or_id, Establishment.deleted_at == None).first()
    if not est:
        est = db.query(Establishment).filter(Establishment.slug == slug_or_id, Establishment.deleted_at == None).first()
    if not est:
        raise HTTPException(404, "Establishment not found")
    return est


@router.post("/establishments", response_model=EstablishmentOut)
def create_establishment(body: EstablishmentCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    est = Establishment(**body.model_dump())
    db.add(est)
    db.commit()
    db.refresh(est)
    log_audit(db, user.id, "CREATE", "establishment", est.id, after_data={"name": est.name})
    db.commit()
    return est


@router.put("/establishments/{est_id}", response_model=EstablishmentOut)
def update_establishment(est_id: str, body: EstablishmentUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    est = db.query(Establishment).filter(Establishment.id == est_id, Establishment.deleted_at == None).first()
    if not est:
        raise HTTPException(404, "Establishment not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(est, k, v)
    db.commit()
    db.refresh(est)
    return est


@router.delete("/establishments/{est_id}")
def delete_establishment(est_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    est = db.query(Establishment).filter(Establishment.id == est_id, Establishment.deleted_at == None).first()
    if not est:
        raise HTTPException(404, "Establishment not found")
    # Cannot delete establishment with history (shifts)
    shift_count = db.query(Shift).filter(Shift.establishment_id == est_id).count()
    if shift_count > 0:
        raise HTTPException(400, f"Cannot delete establishment with {shift_count} shifts in history. Use soft-delete instead.")
    est.is_active = False
    est.deleted_at = datetime.utcnow()
    db.commit()
    log_audit(db, user.id, "DELETE", "establishment", est_id)
    db.commit()
    return {"ok": True}


# ── Menu ──
@router.get("/establishments/{slug_or_id}/menu", response_model=list[MenuItemOut])
def get_menu(slug_or_id: str, db: Session = Depends(get_db)):
    # Try by ID first (UUID format), then by slug
    est = db.query(Establishment).filter(Establishment.id == slug_or_id, Establishment.deleted_at == None).first()
    if not est:
        est = db.query(Establishment).filter(Establishment.slug == slug_or_id, Establishment.deleted_at == None).first()
    if not est:
        raise HTTPException(404, "Establishment not found")
    items = (
        db.query(MenuItem)
        .options(selectinload(MenuItem.cocktail))
        .filter(MenuItem.establishment_id == est.id)
        .order_by(MenuItem.order)
        .all()
    )
    # Filter out deleted cocktails
    return [item for item in items if item.cocktail and item.cocktail.deleted_at is None]


@router.get("/establishments/{est_id}/menu/all", response_model=list[MenuItemOut])
def get_menu_by_id(est_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = (
        db.query(MenuItem)
        .options(selectinload(MenuItem.cocktail))
        .filter(MenuItem.establishment_id == est_id)
        .order_by(MenuItem.order)
        .all()
    )
    return items


def _resolve_establishment(db: Session, slug_or_id: str):
    """Resolve establishment by ID (UUID) or slug."""
    est = db.query(Establishment).filter(Establishment.id == slug_or_id, Establishment.deleted_at == None).first()
    if not est:
        est = db.query(Establishment).filter(Establishment.slug == slug_or_id, Establishment.deleted_at == None).first()
    return est


@router.post("/establishments/{est_id}/menu", response_model=MenuItemOut)
def add_menu_item(est_id: str, body: MenuItemCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    est = _resolve_establishment(db, est_id)
    if not est:
        raise HTTPException(404, "Establishment not found")
    # Prevent duplicate: check if cocktail already in this establishment's menu
    existing = db.query(MenuItem).filter(
        MenuItem.establishment_id == est.id,
        MenuItem.cocktail_id == body.cocktail_id,
    ).first()
    if existing:
        raise HTTPException(409, "This cocktail is already in the menu")
    item = MenuItem(establishment_id=est.id, **body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/establishments/{est_id}/menu/{item_id}", response_model=MenuItemOut)
def update_menu_item(est_id: str, item_id: str, body: MenuItemUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    est = _resolve_establishment(db, est_id)
    if not est:
        raise HTTPException(404, "Establishment not found")
    item = db.query(MenuItem).filter(MenuItem.id == item_id, MenuItem.establishment_id == est.id).first()
    if not item:
        raise HTTPException(404, "Menu item not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/establishments/{est_id}/menu/{item_id}")
def delete_menu_item(est_id: str, item_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("establishments"))):
    est = _resolve_establishment(db, est_id)
    if not est:
        raise HTTPException(404, "Establishment not found")
    item = db.query(MenuItem).filter(MenuItem.id == item_id, MenuItem.establishment_id == est.id).first()
    if not item:
        raise HTTPException(404, "Menu item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


# ── Scans (QR — never modifies stock) ──
@router.post("/analytics/scan")
def record_scan(body: ScanCreate, db: Session = Depends(get_db)):
    est = db.query(Establishment).filter(Establishment.id == body.establishment_id, Establishment.deleted_at == None).first()
    if not est:
        raise HTTPException(404, "Establishment not found")
    # Only records analytics — NEVER touches stock
    scan = ScanEvent(establishment_id=body.establishment_id)
    db.add(scan)
    db.commit()
    return {"ok": True}
