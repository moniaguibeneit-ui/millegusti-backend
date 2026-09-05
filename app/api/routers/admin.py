"""Admin router — quotes, settings, dashboard (role-based), analytics, alerts, audit."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.api.deps import get_current_user, require_permission, require_role
from app.models import (
    QuoteRequest, Settings as AppSettings, ScanEvent, Establishment, Cocktail,
    User, Alert, AuditLog, Shift, SupplyRequest, StockLevel, RawMaterial,
    ShiftProduction, Recipe, RecipeItem, StockMovement, Employee, EmployeeEstablishment,
    Notification,
)
from app.schemas import (
    QuoteCreate, QuoteOut, QuoteStatusUpdate,
    SettingsOut, SettingsUpdate,
    DashboardOut, AnalyticsOut,
    AlertOut, AlertResolve, AuditLogOut,
    NotificationOut,
)

router = APIRouter(tags=["admin"])


# ──────────────────────────────────────────────
# Quotes
# ──────────────────────────────────────────────
@router.post("/quote-requests", response_model=QuoteOut)
def create_quote(body: QuoteCreate, db: Session = Depends(get_db)):
    quote = QuoteRequest(**body.model_dump())
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


@router.get("/admin/quote-requests", response_model=list[QuoteOut])
def list_quotes(status: str | None = Query(None), db: Session = Depends(get_db), user: User = Depends(require_permission("quotes"))):
    q = db.query(QuoteRequest)
    if status:
        q = q.filter(QuoteRequest.status == status)
    return q.order_by(QuoteRequest.created_at.desc()).all()


@router.get("/admin/quote-requests/{quote_id}", response_model=QuoteOut)
def get_quote(quote_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("quotes"))):
    quote = db.query(QuoteRequest).filter(QuoteRequest.id == quote_id).first()
    if not quote:
        raise HTTPException(404, "Quote not found")
    return quote


@router.patch("/admin/quote-requests/{quote_id}/status", response_model=QuoteOut)
def update_quote_status(quote_id: str, body: QuoteStatusUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("quotes"))):
    quote = db.query(QuoteRequest).filter(QuoteRequest.id == quote_id).first()
    if not quote:
        raise HTTPException(404, "Quote not found")
    quote.status = body.status
    db.commit()
    db.refresh(quote)
    return quote


@router.delete("/admin/quote-requests/{quote_id}")
def delete_quote(quote_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("quotes"))):
    quote = db.query(QuoteRequest).filter(QuoteRequest.id == quote_id).first()
    if not quote:
        raise HTTPException(404, "Quote not found")
    db.delete(quote)
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# Settings
# ──────────────────────────────────────────────
@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    s = db.query(AppSettings).first()
    if not s:
        s = AppSettings(stats={}, contact={}, branding={})
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db), user: User = Depends(require_permission("settings"))):
    s = db.query(AppSettings).first()
    if not s:
        s = AppSettings(stats={}, contact={}, branding={})
        db.add(s)
        db.commit()
        db.refresh(s)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


# ──────────────────────────────────────────────
# Dashboard — role-based
# ──────────────────────────────────────────────

def _material_cost_today(db: Session, today_start: datetime) -> float:
    """§9.1 — Coût matière du jour."""
    productions = db.query(ShiftProduction).filter(ShiftProduction.created_at >= today_start).all()
    total = 0.0
    for prod in productions:
        if prod.recipe_snapshot and prod.recipe_snapshot.get("items"):
            for item in prod.recipe_snapshot["items"]:
                rm = db.query(RawMaterial).filter(RawMaterial.id == item["raw_material_id"]).first()
                if rm and rm.cost_per_unit:
                    total += rm.cost_per_unit * item["quantity"] * prod.quantity
        else:
            recipe = db.query(Recipe).filter(Recipe.cocktail_id == prod.cocktail_id).first()
            if recipe:
                items = db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe.id).all()
                for ri in items:
                    rm = db.query(RawMaterial).filter(RawMaterial.id == ri.raw_material_id).first()
                    if rm and rm.cost_per_unit:
                        total += rm.cost_per_unit * ri.quantity * prod.quantity
    return round(total, 2)


def _theoretical_vs_real_gap(db: Session) -> float:
    """§9.1 — Écart théorique vs réel."""
    levels = db.query(StockLevel).all()
    gap = 0.0
    for sl in levels:
        if sl.real_qty is not None:
            gap += abs(sl.theoretical_qty - sl.real_qty)
    return round(gap, 2)


def _total_stock_value(db: Session) -> float:
    """§9.2 — Total stock value."""
    levels = db.query(StockLevel).all()
    total = 0.0
    for sl in levels:
        rm = db.query(RawMaterial).filter(RawMaterial.id == sl.raw_material_id).first()
        if rm and rm.cost_per_unit:
            total += rm.cost_per_unit * sl.theoretical_qty
    return round(total, 2)


def _has_open_shift(db: Session, user: User) -> bool:
    """§9.4 — Does the bartender have an open shift right now?"""
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not emp:
        return False
    return db.query(Shift).filter(Shift.employee_id == emp.id, Shift.status == "open").count() > 0


def _my_cocktails_today(db: Session, user: User, today_start: datetime) -> int:
    """§9.4 — Total cocktails produced by this bartender today."""
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not emp:
        return 0
    shifts = db.query(Shift).filter(Shift.employee_id == emp.id, Shift.opened_at >= today_start).all()
    total = 0
    for s in shifts:
        for p in s.productions:
            total += p.quantity
    return total
@router.get("/admin/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today_start - timedelta(days=6)

    # Common stats
    total_scans = db.query(ScanEvent).count()
    total_est = db.query(Establishment).filter(Establishment.deleted_at == None).count()
    total_ck = db.query(Cocktail).filter(Cocktail.deleted_at == None).count()
    total_quotes = db.query(QuoteRequest).count()
    new_quotes = db.query(QuoteRequest).filter(QuoteRequest.status == "new").count()
    scans_today = db.query(ScanEvent).filter(ScanEvent.scanned_at >= today_start).count()

    scans_7d = []
    for i in range(7):
        day = week_ago + timedelta(days=i)
        day_end = day + timedelta(days=1)
        count = db.query(ScanEvent).filter(ScanEvent.scanned_at >= day, ScanEvent.scanned_at < day_end).count()
        scans_7d.append({"date": day.strftime("%Y-%m-%d"), "count": count})

    # Role-specific stats
    open_shifts = db.query(Shift).filter(Shift.status == "open").count()
    shifts_to_validate = db.query(Shift).filter(Shift.status == "closed").count()
    critical_alerts = db.query(Alert).filter(Alert.is_resolved == False, Alert.severity == "critical").count()
    pending_supply = db.query(SupplyRequest).filter(SupplyRequest.status.in_(["PENDING", "APPROVED", "PARTIALLY_DELIVERED"])).count()

    return DashboardOut(
        total_scans=total_scans,
        total_establishments=total_est,
        total_cocktails=total_ck,
        total_quotes=total_quotes,
        new_quotes=new_quotes,
        scans_today=scans_today,
        scans_last_7_days=scans_7d,
        role=user.role,
        open_shifts=open_shifts,
        shifts_to_validate=shifts_to_validate,
        critical_alerts=critical_alerts,
        pending_supply_requests=pending_supply,
        # §9 — Admin metrics
        material_cost_today=_material_cost_today(db, today_start),
        theoretical_vs_real_gap=_theoretical_vs_real_gap(db),
        # §9.2 — Stock Manager
        total_stock_value=_total_stock_value(db),
        low_stock_count=db.query(StockLevel).filter(StockLevel.theoretical_qty <= 5).count(),
        critical_stock_count=db.query(StockLevel).filter(StockLevel.theoretical_qty <= 1).count(),
        stock_movements_today=db.query(StockMovement).filter(StockMovement.created_at >= today_start).count(),
        # §9.4 — Bartender
        my_open_shift=_has_open_shift(db, user),
        my_cocktails_today=_my_cocktails_today(db, user, today_start),
    )


# ──────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────
@router.get("/admin/analytics", response_model=AnalyticsOut)
def analytics(db: Session = Depends(get_db), user: User = Depends(require_permission("analytics_qr"))):
    scans_by_day = []
    for i in range(30):
        day = datetime.utcnow() - timedelta(days=29 - i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = db.query(ScanEvent).filter(ScanEvent.scanned_at >= day_start, ScanEvent.scanned_at < day_end).count()
        scans_by_day.append({"date": day_start.strftime("%Y-%m-%d"), "count": count})

    est_counts = (
        db.query(Establishment.name, func.count(ScanEvent.id))
        .join(ScanEvent, ScanEvent.establishment_id == Establishment.id)
        .group_by(Establishment.name)
        .all()
    )
    scans_by_establishment = [{"name": name, "count": count} for name, count in est_counts]

    from app.models import MenuItem
    top_ck = (
        db.query(Cocktail.name, func.count(MenuItem.id))
        .join(MenuItem, MenuItem.cocktail_id == Cocktail.id)
        .group_by(Cocktail.name)
        .order_by(func.count(MenuItem.id).desc())
        .limit(10)
        .all()
    )
    top_cocktails = [{"name": name, "count": count} for name, count in top_ck]

    return AnalyticsOut(
        total_scans=db.query(ScanEvent).count(),
        scans_by_day=scans_by_day,
        scans_by_establishment=scans_by_establishment,
        top_cocktails=top_cocktails,
    )


# ──────────────────────────────────────────────
# Alerts
# ──────────────────────────────────────────────
@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    resolved: bool | None = Query(None),
    severity: str | None = Query(None),
    establishment_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Alert)
    if resolved is not None:
        q = q.filter(Alert.is_resolved == resolved)
    if severity:
        q = q.filter(Alert.severity == severity)
    if establishment_id:
        q = q.filter(Alert.establishment_id == establishment_id)
    return q.order_by(Alert.created_at.desc()).limit(100).all()


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
def resolve_alert(alert_id: str, body: AlertResolve, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.is_resolved = body.is_resolved
    if body.is_resolved:
        alert.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert


# ──────────────────────────────────────────────
# Audit logs
# ──────────────────────────────────────────────
@router.get("/admin/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    entity_type: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "STOCK_MANAGER")),
):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()


# ──────────────────────────────────────────────
# Notifications (§10)
# ──────────────────────────────────────────────
@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get notifications for the current user."""
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    return q.order_by(Notification.created_at.desc()).limit(limit).all()


@router.patch("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark a notification as read."""
    notif = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if not notif:
        raise HTTPException(404, "Notification not found")
    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return notif


@router.patch("/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark all notifications as read."""
    db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).update({"is_read": True})
    db.commit()
    return {"marked": True}


def _create_notification(db: Session, user_id: str, type: str, message: str,
                         establishment_id: str | None = None, shift_id: str | None = None):
    """Helper to create a notification for a specific user."""
    notif = Notification(
        user_id=user_id, type=type, message=message,
        establishment_id=establishment_id, shift_id=shift_id,
    )
    db.add(notif)
    db.commit()
    return notif

