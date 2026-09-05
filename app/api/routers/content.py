"""Cocktails, categories, services, gallery router — with soft delete + audit."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user, require_permission
from app.models import Cocktail, Category, Service, GalleryItem, User
from app.schemas import (
    CocktailOut, CocktailCreate, CocktailUpdate,
    CategoryOut, CategoryCreate, CategoryUpdate,
    ServiceOut, ServiceCreate, ServiceUpdate,
    GalleryOut,
)
from app.services.audit_service import log_audit

router = APIRouter(tags=["content"])


# ──────────────────────────────────────────────
# Categories
# ──────────────────────────────────────────────
@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).filter(Category.deleted_at == None).order_by(Category.sort_order).all()


@router.post("/categories", response_model=CategoryOut)
def create_category(body: CategoryCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("cocktails"))):
    cat = Category(**body.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    log_audit(db, user.id, "CREATE", "category", cat.id, after_data=body.model_dump())
    db.commit()
    return cat


@router.put("/categories/{cat_id}", response_model=CategoryOut)
def update_category(cat_id: str, body: CategoryUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("cocktails"))):
    cat = db.query(Category).filter(Category.id == cat_id, Category.deleted_at == None).first()
    if not cat:
        raise HTTPException(404, "Category not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("cocktails"))):
    cat = db.query(Category).filter(Category.id == cat_id, Category.deleted_at == None).first()
    if not cat:
        raise HTTPException(404, "Category not found")
    # Check for active cocktails
    active_cocktails = db.query(Cocktail).filter(Cocktail.category_id == cat_id, Cocktail.deleted_at == None).count()
    if active_cocktails > 0:
        raise HTTPException(400, f"Cannot delete category with {active_cocktails} active cocktails")
    cat.is_active = False
    cat.deleted_at = datetime.utcnow()
    db.commit()
    log_audit(db, user.id, "DELETE", "category", cat_id)
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# Cocktails
# ──────────────────────────────────────────────
@router.get("/cocktails", response_model=list[CocktailOut])
def list_cocktails(
    available_only: bool = Query(False),
    category_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Cocktail).filter(Cocktail.deleted_at == None)
    if available_only:
        q = q.filter(Cocktail.available == "available")
    if category_id:
        q = q.filter(Cocktail.category_id == category_id)
    return q.all()


@router.get("/cocktails/{slug}", response_model=CocktailOut)
def get_cocktail(slug: str, db: Session = Depends(get_db)):
    ck = db.query(Cocktail).filter(Cocktail.slug == slug, Cocktail.deleted_at == None).first()
    if not ck:
        raise HTTPException(404, "Cocktail not found")
    return ck


@router.post("/cocktails", response_model=CocktailOut)
def create_cocktail(body: CocktailCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("cocktails"))):
    ck = Cocktail(**body.model_dump())
    db.add(ck)
    db.commit()
    db.refresh(ck)
    log_audit(db, user.id, "CREATE", "cocktail", ck.id, after_data={"name": ck.name})
    db.commit()
    return ck


@router.put("/cocktails/{ck_id}", response_model=CocktailOut)
def update_cocktail(ck_id: str, body: CocktailUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("cocktails"))):
    ck = db.query(Cocktail).filter(Cocktail.id == ck_id, Cocktail.deleted_at == None).first()
    if not ck:
        raise HTTPException(404, "Cocktail not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ck, k, v)
    db.commit()
    db.refresh(ck)
    return ck


@router.delete("/cocktails/{ck_id}")
def delete_cocktail(ck_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("cocktails"))):
    ck = db.query(Cocktail).filter(Cocktail.id == ck_id, Cocktail.deleted_at == None).first()
    if not ck:
        raise HTTPException(404, "Cocktail not found")
    # Soft delete — preserve history
    ck.is_active = False
    ck.deleted_at = datetime.utcnow()
    db.commit()
    log_audit(db, user.id, "DELETE", "cocktail", ck_id)
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# Services
# ──────────────────────────────────────────────
@router.get("/services", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.query(Service).filter(Service.deleted_at == None).all()


@router.get("/services/{slug}", response_model=ServiceOut)
def get_service(slug: str, db: Session = Depends(get_db)):
    svc = db.query(Service).filter(Service.slug == slug, Service.deleted_at == None).first()
    if not svc:
        raise HTTPException(404, "Service not found")
    return svc


@router.post("/services", response_model=ServiceOut)
def create_service(body: ServiceCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("services"))):
    svc = Service(**body.model_dump())
    db.add(svc)
    db.commit()
    db.refresh(svc)
    return svc


@router.put("/services/{svc_id}", response_model=ServiceOut)
def update_service(svc_id: str, body: ServiceUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("services"))):
    svc = db.query(Service).filter(Service.id == svc_id, Service.deleted_at == None).first()
    if not svc:
        raise HTTPException(404, "Service not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(svc, k, v)
    db.commit()
    db.refresh(svc)
    return svc


@router.delete("/services/{svc_id}")
def delete_service(svc_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("services"))):
    svc = db.query(Service).filter(Service.id == svc_id, Service.deleted_at == None).first()
    if not svc:
        raise HTTPException(404, "Service not found")
    svc.is_active = False
    svc.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# Gallery
# ──────────────────────────────────────────────
@router.get("/gallery", response_model=list[GalleryOut])
def list_gallery(db: Session = Depends(get_db)):
    return db.query(GalleryItem).filter(GalleryItem.deleted_at == None).order_by(GalleryItem.sort_order).all()
