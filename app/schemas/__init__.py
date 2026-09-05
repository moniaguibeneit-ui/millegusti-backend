"""Pydantic schemas — request/response DTOs. Updated for business rules spec."""
from datetime import datetime, date
from typing import Any, Optional
from pydantic import BaseModel, EmailStr, ConfigDict


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORMBase):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    phone: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str = "BARTENDER"
    phone: str | None = None


class UserUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    phone: str | None = None
    is_active: bool | None = None


# ──────────────────────────────────────────────
# Category
# ──────────────────────────────────────────────
class CategoryOut(ORMBase):
    id: str
    name: dict
    slug: str
    sort_order: int
    is_active: bool


class CategoryCreate(BaseModel):
    name: dict
    slug: str
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: dict | None = None
    slug: str | None = None
    sort_order: int | None = None


# ──────────────────────────────────────────────
# Cocktail
# ──────────────────────────────────────────────
class CocktailOut(ORMBase):
    id: str
    name: str
    slug: str
    description: dict
    image_url: str
    base_price: float
    soft_price: float = 0
    alcohol_price: float = 0
    ingredients: list[str]
    allergens: list[str]
    alcoholic: bool
    has_soft_version: bool = False
    is_new: bool
    available: str
    category_id: str
    is_active: bool


class CocktailCreate(BaseModel):
    name: str
    slug: str
    description: dict
    image_url: str
    base_price: float = 0
    soft_price: float = 0
    alcohol_price: float = 0
    ingredients: list[str] = []
    allergens: list[str] = []
    alcoholic: bool = True
    has_soft_version: bool = False
    is_new: bool = False
    available: str = "available"
    category_id: str


class CocktailUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: dict | None = None
    image_url: str | None = None
    base_price: float | None = None
    soft_price: float | None = None
    alcohol_price: float | None = None
    ingredients: list[str] | None = None
    allergens: list[str] | None = None
    alcoholic: bool | None = None
    has_soft_version: bool | None = None
    is_new: bool | None = None
    available: str | None = None
    category_id: str | None = None


# ──────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────
class ServiceOut(ORMBase):
    id: str
    title: dict
    description: dict
    slug: str
    icon: str
    image_url: str
    benefits: list[Any]
    is_active: bool


class ServiceCreate(BaseModel):
    title: dict
    description: dict
    slug: str
    icon: str = "Wine"
    image_url: str
    benefits: list[Any] = []


class ServiceUpdate(BaseModel):
    title: dict | None = None
    description: dict | None = None
    slug: str | None = None
    icon: str | None = None
    image_url: str | None = None
    benefits: list[Any] | None = None


# ──────────────────────────────────────────────
# Gallery
# ──────────────────────────────────────────────
class GalleryOut(ORMBase):
    id: str
    title: dict
    image_url: str
    sort_order: int


# ──────────────────────────────────────────────
# Establishment + Menu
# ──────────────────────────────────────────────
class EstablishmentOut(ORMBase):
    id: str
    name: str
    slug: str
    description: dict
    logo_url: str
    cover_image_url: str
    is_active: bool
    scans_count: int = 0
    cocktails_count: int = 0
    scans_trend: int = 0


class EstablishmentCreate(BaseModel):
    name: str
    slug: str
    description: dict
    logo_url: str
    cover_image_url: str


class EstablishmentUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: dict | None = None
    logo_url: str | None = None
    cover_image_url: str | None = None
    is_active: bool | None = None


class MenuItemOut(ORMBase):
    id: str
    establishment_id: str
    cocktail_id: str
    price: float
    available: bool
    order: int
    cocktail: Optional[CocktailOut] = None


class MenuItemCreate(BaseModel):
    cocktail_id: str
    price: float
    available: bool = True
    order: int = 0


class MenuItemUpdate(BaseModel):
    price: float | None = None
    available: bool | None = None
    order: int | None = None


# ──────────────────────────────────────────────
# Quotes
# ──────────────────────────────────────────────
class QuoteCreate(BaseModel):
    full_name: str
    company: str | None = None
    email: EmailStr
    phone: str
    event_type: str
    event_date: date | None = None
    guests: int | None = None
    location: str | None = None
    budget: str | None = None
    message: str


class QuoteOut(ORMBase):
    id: str
    full_name: str
    company: str | None
    email: str
    phone: str
    event_type: str
    event_date: date | None
    guests: int | None
    location: str | None
    budget: str | None
    message: str
    status: str
    created_at: datetime


class QuoteStatusUpdate(BaseModel):
    status: str


# ──────────────────────────────────────────────
# Settings
# ──────────────────────────────────────────────
class SettingsOut(ORMBase):
    id: int
    stats: dict
    contact: dict
    branding: dict


class SettingsUpdate(BaseModel):
    stats: dict | None = None
    contact: dict | None = None
    branding: dict | None = None


# ──────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────
class ScanCreate(BaseModel):
    establishment_id: str


class DashboardOut(BaseModel):
    total_scans: int
    total_establishments: int
    total_cocktails: int
    total_quotes: int
    new_quotes: int
    scans_today: int
    scans_last_7_days: list[dict]
    # Role-specific
    role: str = "ADMIN"
    open_shifts: int = 0
    shifts_to_validate: int = 0
    critical_alerts: int = 0
    pending_supply_requests: int = 0
    # §9 — Admin metrics
    material_cost_today: float = 0.0  # coût matière du jour
    theoretical_vs_real_gap: float = 0.0  # écart théorique vs réel
    # §9.2 — Stock Manager
    total_stock_value: float = 0.0
    low_stock_count: int = 0
    critical_stock_count: int = 0
    stock_movements_today: int = 0
    # §9.4 — Bartender
    my_open_shift: bool = False
    my_cocktails_today: int = 0


class AnalyticsOut(BaseModel):
    total_scans: int
    scans_by_day: list[dict]
    scans_by_establishment: list[dict]
    top_cocktails: list[dict]


# ──────────────────────────────────────────────
# Raw Materials + Packaging
# ──────────────────────────────────────────────
class PackagingOut(ORMBase):
    id: str
    raw_material_id: str
    name: str
    quantity_per_package: float
    unit: str
    cost_per_package: float
    is_default: bool


class PackagingCreate(BaseModel):
    name: str
    quantity_per_package: float
    unit: str = "ml"
    cost_per_package: float = 0
    is_default: bool = False


class RawMaterialOut(ORMBase):
    id: str
    name: str
    category: str
    base_unit: str
    cost_per_unit: float
    min_threshold: float
    max_threshold: float
    supplier: str | None
    is_active: bool
    packagings: list[PackagingOut] = []


class RawMaterialCreate(BaseModel):
    name: str
    category: str = "other"
    base_unit: str = "ml"
    cost_per_unit: float = 0
    min_threshold: float = 0
    max_threshold: float = 0
    supplier: str | None = None
    packagings: list[PackagingCreate] = []


class RawMaterialUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    base_unit: str | None = None
    cost_per_unit: float | None = None
    min_threshold: float | None = None
    max_threshold: float | None = None
    supplier: str | None = None


# ──────────────────────────────────────────────
# Recipes + Snapshots
# ──────────────────────────────────────────────
class RecipeItemOut(ORMBase):
    id: str
    raw_material_id: str
    raw_material: Optional[RawMaterialOut] = None
    quantity: float
    waste_percentage: float


class RecipeItemCreate(BaseModel):
    raw_material_id: str
    quantity: float
    waste_percentage: float = 0


class RecipeOut(ORMBase):
    id: str
    cocktail_id: str
    version: int
    items: list[RecipeItemOut]
    updated_at: datetime


class RecipeCreate(BaseModel):
    cocktail_id: str
    items: list[RecipeItemCreate]


class RecipeSnapshotOut(ORMBase):
    id: str
    shift_id: str
    cocktail_id: str
    cocktail_name: str
    recipe_version: int
    items: list[dict]


# ──────────────────────────────────────────────
# Employees
# ──────────────────────────────────────────────
class EmployeeOut(ORMBase):
    id: str
    first_name: str
    last_name: str
    phone: str | None
    email: str | None
    role: str
    is_active: bool
    establishment_ids: list[str] = []


class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    email: str | None = None
    role: str = "bartender"
    establishment_ids: list[str] = []


class EmployeeUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None
    establishment_ids: list[str] | None = None


# ──────────────────────────────────────────────
# Shifts
# ──────────────────────────────────────────────
class CocktailBrief(BaseModel):
    """Minimal cocktail info for production display."""
    id: str
    name: str
    image_url: str | None = None


class ShiftProductionOut(ORMBase):
    id: str
    shift_id: str | None = None
    cocktail_id: str
    quantity: int
    created_at: datetime | None = None
    recipe_snapshot: dict | None = None
    cocktail: CocktailBrief | None = None


# ──────────────────────────────────────────────
# Shift Slots (predefined time slots)
# ──────────────────────────────────────────────
class ShiftSlotOut(ORMBase):
    id: str
    name: str
    name_fr: str | None
    name_en: str | None
    name_ar: str | None
    start_time: str
    end_time: str
    is_overnight: bool
    sort_order: int
    is_active: bool


class ShiftSlotCreate(BaseModel):
    name: str
    name_fr: str | None = None
    name_en: str | None = None
    name_ar: str | None = None
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    is_overnight: bool = False
    sort_order: int = 0
    is_active: bool = True


class ShiftSlotUpdate(BaseModel):
    name: str | None = None
    name_fr: str | None = None
    name_en: str | None = None
    name_ar: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    is_overnight: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ShiftProductionCreate(BaseModel):
    cocktail_id: str
    quantity: int = 1


class ShiftOut(ORMBase):
    id: str
    establishment_id: str
    employee_id: str
    date: date
    opened_at: datetime
    closed_at: datetime | None
    validated_at: datetime | None
    validated_by: str | None
    status: str
    notes: str | None
    dispute_reason: str | None = None
    disputed_by: str | None = None
    disputed_at: datetime | None = None
    productions: list[ShiftProductionOut] = []
    action_logs: list["ShiftActionLogOut"] = []


class ShiftActionLogOut(ORMBase):
    id: str
    shift_id: str
    cocktail_id: str
    delta: int
    variant: str | None = None
    created_at: datetime
    cancelled_at: datetime | None = None


class ShiftActionLogCreate(BaseModel):
    """Client-generated action log entry (idempotent via client UUID)."""
    id: str  # client-generated UUID for idempotency
    cocktail_id: str
    delta: int
    variant: str | None = None  # 'soft' | 'alcohol' | None


class ShiftOpen(BaseModel):
    establishment_id: str
    employee_id: str
    notes: str | None = None
    shift_date: date | None = None  # shift date (defaults to today)
    opened_at: datetime | None = None  # start time (defaults to now)
    closed_at: datetime | None = None  # end time (if provided, shift is created as closed)


class ShiftUpdate(BaseModel):
    establishment_id: str | None = None
    employee_id: str | None = None
    notes: str | None = None
    shift_date: date | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    status: str | None = None  # open, closed, validated


class ShiftClose(BaseModel):
    productions: list[ShiftProductionCreate]
    notes: str | None = None


class ShiftConsumptionOut(ORMBase):
    id: str
    raw_material_id: str
    quantity: float
    unit: str


# ──────────────────────────────────────────────
# Stock
# ──────────────────────────────────────────────
class StockLevelOut(ORMBase):
    id: str
    establishment_id: str
    raw_material_id: str
    theoretical_qty: float
    real_qty: float | None
    last_inventory_at: datetime | None
    unit: str
    updated_at: datetime
    raw_material: Optional[RawMaterialOut] = None


class StockMovementOut(ORMBase):
    id: str
    establishment_id: str
    raw_material_id: str
    movement_type: str
    quantity: float
    unit: str
    reference: str | None
    reference_type: str | None
    reference_id: str | None
    previous_theoretical_qty: float | None
    counted_qty: float | None
    created_at: datetime


class SupplyCreate(BaseModel):
    establishment_id: str
    raw_material_id: str
    quantity: float
    unit: str = "ml"
    reference: str | None = None


class StockDashboardOut(BaseModel):
    total_value: float
    total_items: int
    critical_items: int
    out_of_stock: int
    by_establishment: list[dict]
    pending_requests: int
    alerts: list[dict] = []


class AutonomyOut(BaseModel):
    raw_material_id: str
    name: str
    current_qty: float
    avg_daily_consumption: float
    autonomy_days: float | None
    status: str


# ──────────────────────────────────────────────
# Inventory
# ──────────────────────────────────────────────
class InventoryCreate(BaseModel):
    establishment_id: str
    raw_material_id: str
    counted_qty: float
    reason: str | None = None
    note: str | None = None


class InventoryOut(ORMBase):
    id: str
    establishment_id: str
    raw_material_id: str
    counted_qty: float
    theoretical_qty: float
    variance: float
    reason: str | None
    note: str | None
    created_at: datetime


# ──────────────────────────────────────────────
# Supply Requests — full workflow with items
# ──────────────────────────────────────────────
class SupplyRequestItemOut(ORMBase):
    id: str
    raw_material_id: str
    raw_material: Optional[RawMaterialOut] = None
    requested_quantity: float
    suggested_quantity: float
    approved_quantity: float | None
    delivered_quantity: float | None
    unit: str


class SupplyRequestItemCreate(BaseModel):
    raw_material_id: str
    requested_quantity: float
    suggested_quantity: float = 0
    unit: str = "ml"


class SupplyRequestCreate(BaseModel):
    establishment_id: str
    notes: str | None = None
    items: list[SupplyRequestItemCreate]


class SupplyRequestOut(ORMBase):
    id: str
    establishment_id: str
    requested_by: str | None
    status: str
    notes: str | None
    created_at: datetime
    approved_at: datetime | None
    delivered_at: datetime | None
    items: list[SupplyRequestItemOut] = []


class SupplyRequestStatusUpdate(BaseModel):
    status: str  # PENDING, APPROVED, PARTIALLY_DELIVERED, DELIVERED, REJECTED, CANCELLED
    approved_quantities: dict[str, float] | None = None  # {item_id: qty}
    delivered_quantities: dict[str, float] | None = None  # {item_id: qty}


# ──────────────────────────────────────────────
# Alerts
# ──────────────────────────────────────────────
class AlertOut(ORMBase):
    id: str
    type: str
    severity: str
    establishment_id: str | None
    raw_material_id: str | None
    shift_id: str | None
    supply_request_id: str | None
    message: str
    is_resolved: bool
    resolved_at: datetime | None
    created_at: datetime


class NotificationOut(ORMBase):
    id: str
    user_id: str
    type: str
    message: str
    establishment_id: str | None = None
    shift_id: str | None = None
    is_read: bool
    created_at: datetime


class AlertResolve(BaseModel):
    is_resolved: bool = True


# ──────────────────────────────────────────────
# Audit
# ──────────────────────────────────────────────
class AuditLogOut(ORMBase):
    id: str
    user_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    before_data: dict | None
    after_data: dict | None
    created_at: datetime


# ──────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────
class ProductionAnalyticsOut(BaseModel):
    period: str
    total_cocktails: int
    by_cocktail: list[dict]
    by_employee: list[dict]
    by_establishment: list[dict]
    by_day: list[dict]


class ConsumptionAnalyticsOut(BaseModel):
    period: str
    total_value: float
    by_material: list[dict]
    by_day: list[dict]


# Forward refs
TokenResponse.model_rebuild()
