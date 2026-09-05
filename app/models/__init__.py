"""SQLAlchemy models — all entities with business rules from spec."""
import uuid
from datetime import datetime, date
from sqlalchemy import (
    String, Text, Boolean, Integer, Float, DateTime, Date, JSON,
    ForeignKey, UniqueConstraint, Index, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ──────────────────────────────────────────────
# Mixin: Soft delete
# ──────────────────────────────────────────────
class SoftDeleteMixin:
    """Adds `is_active` and `deleted_at` for soft deletes."""
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ──────────────────────────────────────────────
# Auth & Users
# ──────────────────────────────────────────────
class User(Base, SoftDeleteMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="ADMIN")  # SUPER_ADMIN, ADMIN, STOCK_MANAGER, ESTABLISHMENT_MANAGER, BARTENDER, MARKETING
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EmployeeEstablishment(Base):
    """Many-to-many: a bartender can work at multiple establishments."""
    __tablename__ = "employee_establishments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    employee_id: Mapped[str] = mapped_column(String(36), ForeignKey("employees.id"), nullable=False)
    establishment_id: Mapped[str] = mapped_column(String(36), ForeignKey("establishments.id"), nullable=False)
    employee: Mapped["Employee"] = relationship(back_populates="establishments")
    establishment: Mapped["Establishment"] = relationship(back_populates="employees")
    __table_args__ = (UniqueConstraint("employee_id", "establishment_id", name="uq_emp_est"),)


# ──────────────────────────────────────────────
# Audit Log
# ──────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))  # CREATE, UPDATE, DELETE, VALIDATE, etc.
    entity_type: Mapped[str] = mapped_column(String(100))  # cocktail, shift, inventory, etc.
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────
# Alerts
# ──────────────────────────────────────────────
class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(50))  # LOW_STOCK, OUT_OF_STOCK, NEGATIVE_STOCK, INVENTORY_VARIANCE, SUPPLY_PENDING, SUPPLY_OVERDUE, SHIFT_NOT_CLOSED, SHIFT_WAITING_VALIDATION
    severity: Mapped[str] = mapped_column(String(20), default="warning")  # info, warning, critical
    establishment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("establishments.id"), nullable=True)
    raw_material_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("raw_materials.id"), nullable=True)
    shift_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("shifts.id"), nullable=True)
    supply_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("supply_requests.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(Base):
    """§10 — User-targeted notifications (shift reminders, stock alerts)."""
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50))  # SHIFT_STARTING, SHIFT_OPENED, SHIFT_OPENED_MANAGER, STOCK_CRITICAL
    message: Mapped[str] = mapped_column(Text)
    establishment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("establishments.id"), nullable=True)
    shift_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("shifts.id"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────
# Public content
# ──────────────────────────────────────────────
class Category(Base, SoftDeleteMixin):
    __tablename__ = "categories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[dict] = mapped_column(JSON)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cocktails: Mapped[list["Cocktail"]] = relationship(back_populates="category")


class Cocktail(Base, SoftDeleteMixin):
    __tablename__ = "cocktails"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[dict] = mapped_column(JSON)
    image_url: Mapped[str] = mapped_column(Text)
    base_price: Mapped[float] = mapped_column(Float, default=0)
    soft_price: Mapped[float] = mapped_column(Float, default=0)
    alcohol_price: Mapped[float] = mapped_column(Float, default=0)
    ingredients: Mapped[list] = mapped_column(JSON, default=list)
    allergens: Mapped[list] = mapped_column(JSON, default=list)
    alcoholic: Mapped[bool] = mapped_column(Boolean, default=True)
    has_soft_version: Mapped[bool] = mapped_column(Boolean, default=False)  # true = exists in both soft + alcohol
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    available: Mapped[str] = mapped_column(String(20), default="available")
    category_id: Mapped[str] = mapped_column(String(36), ForeignKey("categories.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    category: Mapped["Category"] = relationship(back_populates="cocktails")
    menu_items: Mapped[list["MenuItem"]] = relationship(back_populates="cocktail")


class Service(Base, SoftDeleteMixin):
    __tablename__ = "services"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[dict] = mapped_column(JSON)
    description: Mapped[dict] = mapped_column(JSON)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    icon: Mapped[str] = mapped_column(String(100), default="Wine")
    image_url: Mapped[str] = mapped_column(Text)
    benefits: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GalleryItem(Base, SoftDeleteMixin):
    __tablename__ = "gallery_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[dict] = mapped_column(JSON)
    image_url: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


# ──────────────────────────────────────────────
# Establishments + Menu
# ──────────────────────────────────────────────
class Establishment(Base, SoftDeleteMixin):
    __tablename__ = "establishments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[dict] = mapped_column(JSON)
    logo_url: Mapped[str] = mapped_column(Text)
    cover_image_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    menu_items: Mapped[list["MenuItem"]] = relationship(back_populates="establishment")
    scan_events: Mapped[list["ScanEvent"]] = relationship(back_populates="establishment")
    employees: Mapped[list["EmployeeEstablishment"]] = relationship(back_populates="establishment")


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    establishment_id: Mapped[str] = mapped_column(String(36), ForeignKey("establishments.id"))
    cocktail_id: Mapped[str] = mapped_column(String(36), ForeignKey("cocktails.id"))
    price: Mapped[float] = mapped_column(Float, default=0)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    establishment: Mapped["Establishment"] = relationship(back_populates="menu_items")
    cocktail: Mapped["Cocktail"] = relationship(back_populates="menu_items")


class ScanEvent(Base):
    __tablename__ = "scan_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    establishment_id: Mapped[str] = mapped_column(String(36), ForeignKey("establishments.id"))
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    establishment: Mapped["Establishment"] = relationship(back_populates="scan_events")


# ──────────────────────────────────────────────
# Quotes + Settings
# ──────────────────────────────────────────────
class QuoteRequest(Base):
    __tablename__ = "quote_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(100))
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    guests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    budget: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Settings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    contact: Mapped[dict] = mapped_column(JSON, default=dict)
    branding: Mapped[dict] = mapped_column(JSON, default=dict)


# ──────────────────────────────────────────────
# Raw Materials + Packaging
# ──────────────────────────────────────────────
class RawMaterial(Base, SoftDeleteMixin):
    __tablename__ = "raw_materials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(100), default="other")
    base_unit: Mapped[str] = mapped_column(String(20), default="ml")  # internal base unit: ml, g, unit
    cost_per_unit: Mapped[float] = mapped_column(Float, default=0)  # cost per base unit
    min_threshold: Mapped[float] = mapped_column(Float, default=0)  # in base unit
    max_threshold: Mapped[float] = mapped_column(Float, default=0)  # in base unit
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    recipes: Mapped[list["RecipeItem"]] = relationship(back_populates="raw_material")
    stock_levels: Mapped[list["StockLevel"]] = relationship(back_populates="raw_material")
    packagings: Mapped[list["Packaging"]] = relationship(back_populates="raw_material", cascade="all, delete-orphan")


class Packaging(Base):
    """Supplier packaging for a raw material.
    e.g. Rum: base_unit=ml, packaging=bottle 700ml, stock=12 bottles = 8400ml"""
    __tablename__ = "packagings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    raw_material_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_materials.id"))
    name: Mapped[str] = mapped_column(String(200))  # "Bouteille 700ml"
    quantity_per_package: Mapped[float] = mapped_column(Float)  # 700 (in base unit)
    unit: Mapped[str] = mapped_column(String(20), default="ml")
    cost_per_package: Mapped[float] = mapped_column(Float, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_material: Mapped["RawMaterial"] = relationship(back_populates="packagings")


# ──────────────────────────────────────────────
# Recipes + Versioning (Snapshots)
# ──────────────────────────────────────────────
class Recipe(Base):
    """Current recipe for a cocktail. Can change over time."""
    __tablename__ = "recipes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cocktail_id: Mapped[str] = mapped_column(String(36), ForeignKey("cocktails.id"), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # incremented on each change
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    items: Mapped[list["RecipeItem"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")


class RecipeItem(Base):
    __tablename__ = "recipe_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipe_id: Mapped[str] = mapped_column(String(36), ForeignKey("recipes.id"))
    raw_material_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_materials.id"))
    quantity: Mapped[float] = mapped_column(Float, default=0)  # in raw material base unit
    waste_percentage: Mapped[float] = mapped_column(Float, default=0)
    recipe: Mapped["Recipe"] = relationship(back_populates="items")
    raw_material: Mapped["RawMaterial"] = relationship(back_populates="recipes")


class RecipeSnapshot(Base):
    """Frozen copy of a recipe at the time of shift validation.
    Ensures historical consumption records remain accurate even if the recipe changes."""
    __tablename__ = "recipe_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    shift_id: Mapped[str] = mapped_column(String(36), ForeignKey("shifts.id"))
    cocktail_id: Mapped[str] = mapped_column(String(36), ForeignKey("cocktails.id"))
    cocktail_name: Mapped[str] = mapped_column(String(200))  # frozen name
    recipe_version: Mapped[int] = mapped_column(Integer)
    items: Mapped[list["RecipeSnapshotItem"]] = relationship(cascade="all, delete-orphan")


class RecipeSnapshotItem(Base):
    __tablename__ = "recipe_snapshot_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("recipe_snapshots.id"))
    raw_material_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_materials.id"))
    raw_material_name: Mapped[str] = mapped_column(String(200))  # frozen name
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    waste_percentage: Mapped[float] = mapped_column(Float, default=0)


# ──────────────────────────────────────────────
# Employees
# ──────────────────────────────────────────────
class Employee(Base, SoftDeleteMixin):
    __tablename__ = "employees"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(100), default="bartender")
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)  # link to login
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    shifts: Mapped[list["Shift"]] = relationship(back_populates="employee")
    establishments: Mapped[list["EmployeeEstablishment"]] = relationship(back_populates="employee")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


# ──────────────────────────────────────────────
# Shifts + Production
# ──────────────────────────────────────────────
class ShiftSlot(Base, SoftDeleteMixin):
    """Predefined shift time slots (e.g. Morning 06-14, Evening 14-22, Night 22-06).
    Admin can create/manage these; they're used when opening a shift."""
    __tablename__ = "shift_slots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100))  # display name
    name_fr: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name_ar: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    is_overnight: Mapped[bool] = mapped_column(Boolean, default=False)  # crosses midnight
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    establishment_id: Mapped[str] = mapped_column(String(36), ForeignKey("establishments.id"))
    employee_id: Mapped[str] = mapped_column(String(36), ForeignKey("employees.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # planned, open, closed, validated, disputed, cancelled
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispute_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    disputed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    establishment: Mapped["Establishment"] = relationship()
    employee: Mapped["Employee"] = relationship(back_populates="shifts")
    productions: Mapped[list["ShiftProduction"]] = relationship(back_populates="shift", cascade="all, delete-orphan")
    consumptions: Mapped[list["ShiftConsumption"]] = relationship(back_populates="shift", cascade="all, delete-orphan")
    recipe_snapshots: Mapped[list["RecipeSnapshot"]] = relationship(cascade="all, delete-orphan")
    action_logs: Mapped[list["ShiftActionLog"]] = relationship(back_populates="shift", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(foreign_keys="Alert.shift_id", cascade="all, delete-orphan")


class ShiftActionLog(Base):
    """Immutable log of every +/− action during a shift.
    Enables undo, audit, and offline sync conflict resolution."""
    __tablename__ = "shift_action_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    shift_id: Mapped[str] = mapped_column(String(36), ForeignKey("shifts.id"))
    cocktail_id: Mapped[str] = mapped_column(String(36), ForeignKey("cocktails.id"))
    delta: Mapped[int] = mapped_column(Integer)  # positive or negative
    variant: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 'soft' | 'alcohol' | None
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shift: Mapped["Shift"] = relationship(back_populates="action_logs")
    cocktail: Mapped["Cocktail"] = relationship()


class ShiftProduction(Base):
    __tablename__ = "shift_productions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    shift_id: Mapped[str] = mapped_column(String(36), ForeignKey("shifts.id"))
    cocktail_id: Mapped[str] = mapped_column(String(36), ForeignKey("cocktails.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    recipe_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # frozen recipe at production time
    shift: Mapped["Shift"] = relationship(back_populates="productions")
    cocktail: Mapped["Cocktail"] = relationship()


class ShiftConsumption(Base):
    __tablename__ = "shift_consumptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    shift_id: Mapped[str] = mapped_column(String(36), ForeignKey("shifts.id"))
    raw_material_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_materials.id"))
    quantity: Mapped[float] = mapped_column(Float, default=0)  # in base unit
    unit: Mapped[str] = mapped_column(String(20), default="ml")
    shift: Mapped["Shift"] = relationship(back_populates="consumptions")
    raw_material: Mapped["RawMaterial"] = relationship()


# ──────────────────────────────────────────────
# Stock — movements are source of truth
# ──────────────────────────────────────────────
class StockLevel(Base):
    """Cache of theoretical stock, computed from movements.
    The source of truth is stock_movements, this is a performance cache."""
    __tablename__ = "stock_levels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    establishment_id: Mapped[str] = mapped_column(String(36), ForeignKey("establishments.id"))
    raw_material_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_materials.id"))
    theoretical_qty: Mapped[float] = mapped_column(Float, default=0)  # cache, computed from movements
    real_qty: Mapped[float | None] = mapped_column(Float, nullable=True)  # from last inventory
    last_inventory_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="ml")  # base unit
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    raw_material: Mapped["RawMaterial"] = relationship(back_populates="stock_levels")
    __table_args__ = (UniqueConstraint("establishment_id", "raw_material_id", name="uq_stock_est_material"),)


class StockMovement(Base):
    """Source of truth for all stock changes.
    Types: INITIAL_STOCK, SUPPLY_RECEIPT, SHIFT_CONSUMPTION, INVENTORY_ADJUSTMENT, LOSS, TRANSFER_IN, TRANSFER_OUT, MANUAL_ADJUSTMENT"""
    __tablename__ = "stock_movements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    establishment_id: Mapped[str] = mapped_column(String(36), ForeignKey("establishments.id"))
    raw_material_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_materials.id"))
    movement_type: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[float] = mapped_column(Float, default=0)  # positive=in, negative=out
    unit: Mapped[str] = mapped_column(String(20), default="ml")  # base unit
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g. "shift:uuid"
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # shift, supply, inventory, manual
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # For inventory adjustments
    previous_theoretical_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    counted_qty: Mapped[float | None] = mapped_column(Float, nullable=True)


class Inventory(Base):
    __tablename__ = "inventories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    establishment_id: Mapped[str] = mapped_column(String(36), ForeignKey("establishments.id"))
    raw_material_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_materials.id"))
    counted_qty: Mapped[float] = mapped_column(Float, default=0)
    theoretical_qty: Mapped[float] = mapped_column(Float, default=0)
    variance: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────
# Supply Requests — full workflow
# ──────────────────────────────────────────────
class SupplyRequest(Base):
    """Supply request with full workflow.
    Statuses: DRAFT, PENDING, APPROVED, PARTIALLY_DELIVERED, DELIVERED, REJECTED, CANCELLED"""
    __tablename__ = "supply_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    establishment_id: Mapped[str] = mapped_column(String(36), ForeignKey("establishments.id"))
    requested_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    items: Mapped[list["SupplyRequestItem"]] = relationship(cascade="all, delete-orphan")


class SupplyRequestItem(Base):
    __tablename__ = "supply_request_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    supply_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("supply_requests.id"))
    raw_material_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_materials.id"))
    requested_quantity: Mapped[float] = mapped_column(Float, default=0)
    suggested_quantity: Mapped[float] = mapped_column(Float, default=0)
    approved_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivered_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="ml")
    raw_material: Mapped["RawMaterial"] = relationship()
