"""Database initialization + seed data — REAL data from 2 points of sale.

Data structure:
  Establishment (POV1, POV2)
    → Menu (MenuItem join table with price + availability)
      → Cocktail (unique recipes)
        → Recipe
          → RecipeItem
            → RawMaterial

Stock is per-establishment. Recipes are shared.
"""
import uuid
from datetime import datetime, date, timedelta

from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine, Base
from app.core.security import hash_password
from app.models import (
    User, Category, Cocktail, Service, GalleryItem,
    Establishment, MenuItem, ScanEvent,
    QuoteRequest, Settings as AppSettings,
    RawMaterial, Packaging, Recipe, RecipeItem, Employee, EmployeeEstablishment,
    Shift, ShiftProduction, ShiftConsumption, ShiftSlot,
    StockLevel, StockMovement, SupplyRequest, SupplyRequestItem, Alert,
)


def gen_id() -> str:
    return str(uuid.uuid4())


# ============================================================
# DATA DEFINITIONS
# ============================================================

# ── Raw materials (base unit: ml for liquids, g for solids, unit for whole) ──
MATERIALS = [
    # Alcohols (ml)
    ("Vodka", "alcohol", "ml", 0.038, 5000, 20000, [("Bouteille 1L", 1000, 38)]),
    ("Rhum Blanc", "alcohol", "ml", 0.045, 5000, 20000, [("Bouteille 700ml", 700, 31.5)]),
    ("Gin", "alcohol", "ml", 0.052, 3000, 15000, [("Bouteille 750ml", 750, 39)]),
    ("Tequila", "alcohol", "ml", 0.06, 3000, 15000, [("Bouteille 700ml", 700, 42)]),
    ("Triple Sec", "alcohol", "ml", 0.03, 2000, 10000, [("Bouteille 500ml", 500, 15)]),
    ("Campari", "alcohol", "ml", 0.07, 2000, 10000, [("Bouteille 1L", 1000, 70)]),
    ("Martini Blanc", "alcohol", "ml", 0.04, 2000, 10000, [("Bouteille 750ml", 750, 30)]),
    ("Dry Gin", "alcohol", "ml", 0.052, 3000, 15000, [("Bouteille 750ml", 750, 39)]),
    ("Blended Scotch Whisky", "alcohol", "ml", 0.055, 2000, 10000, [("Bouteille 700ml", 700, 38.5)]),
    ("Limoncello", "alcohol", "ml", 0.04, 1000, 5000, [("Bouteille 500ml", 500, 20)]),
    ("Aperol", "alcohol", "ml", 0.05, 2000, 10000, [("Bouteille 700ml", 700, 35)]),
    ("White Wine", "alcohol", "ml", 0.012, 3000, 15000, [("Bouteille 750ml", 750, 9)]),
    ("White Choppin", "alcohol", "ml", 0.015, 3000, 15000, [("Bouteille 750ml", 750, 11)]),
    # Fruits / juices (g or ml)
    ("Bubble Gum Syrup", "syrup", "ml", 0.02, 1000, 5000, [("Bouteille 1L", 1000, 20)]),
    ("Strawberry", "fruit", "g", 0.02, 2000, 10000, [("Barquette 500g", 500, 10)]),
    ("Pineapple", "fruit", "g", 0.015, 2000, 10000, [("Unité 1kg", 1000, 15)]),
    ("Blueberry", "fruit", "g", 0.03, 1000, 5000, [("Barquette 250g", 250, 7.5)]),
    ("Raspberry", "fruit", "g", 0.035, 1000, 5000, [("Barquette 250g", 250, 8.75)]),
    ("Lime", "fruit", "unit", 0.5, 50, 300, [("Sachet 50", 50, 25)]),
    ("Watermelon", "fruit", "g", 0.01, 2000, 10000, [("Unité 5kg", 5000, 50)]),
    ("Peach", "fruit", "g", 0.018, 2000, 10000, [("Boîte 1kg", 1000, 18)]),
    ("Mango", "fruit", "g", 0.02, 2000, 10000, [("Unité 1kg", 1000, 20)]),
    ("Orange", "fruit", "g", 0.012, 2000, 10000, [("Sachet 5kg", 5000, 60)]),
    ("Passion Fruit", "fruit", "g", 0.04, 1000, 5000, [("Purée 1L", 1000, 40)]),
    ("Coconut", "fruit", "g", 0.025, 1000, 5000, [("Lait 1L", 1000, 25)]),
    ("Vanilla", "aromatic", "ml", 0.8, 200, 1000, [("Flacon 200ml", 200, 160)]),
    ("Fig", "fruit", "g", 0.03, 1000, 5000, [("Barquette 500g", 500, 15)]),
    ("Pomegranate", "fruit", "g", 0.04, 1000, 5000, [("Purée 1L", 1000, 40)]),
    ("Green Apple", "fruit", "g", 0.015, 1000, 5000, [("Sachet 2kg", 2000, 30)]),
    ("Kiwi", "fruit", "g", 0.02, 1000, 5000, [("Sachet 1kg", 1000, 20)]),
    ("Cranberry", "fruit", "g", 0.03, 1000, 5000, [("Purée 1L", 1000, 30)]),
    ("Lychee", "fruit", "g", 0.03, 1000, 5000, [("Purée 1L", 1000, 30)]),
    ("Sour Cherry", "fruit", "g", 0.035, 1000, 5000, [("Purée 1L", 1000, 35)]),
    ("Mango Alphonso", "fruit", "g", 0.025, 1000, 5000, [("Purée 1L", 1000, 25)]),
    ("Bergamote", "aromatic", "ml", 0.5, 200, 1000, [("Flacon 200ml", 200, 100)]),
    # Herbs / aromatics (g)
    ("Rosemary", "herb", "g", 0.06, 200, 1500, [("Sachet 100g", 100, 6)]),
    ("Thyme", "herb", "g", 0.05, 200, 1500, [("Sachet 100g", 100, 5)]),
    ("Rose", "aromatic", "g", 0.1, 100, 500, [("Sachet 50g", 50, 5)]),
    ("Rose Hibiscus", "aromatic", "g", 0.08, 200, 1000, [("Sachet 100g", 100, 8)]),
    # Mixers (ml)
    ("Sprite", "mixer", "ml", 0.003, 5000, 30000, [("Bouteille 1L", 1000, 3)]),
    ("Soda Water", "mixer", "ml", 0.003, 5000, 30000, [("Bouteille 1L", 1000, 3)]),
    ("Tonic", "mixer", "ml", 0.005, 5000, 30000, [("Bouteille 1L", 1000, 5)]),
    ("Red Bull", "mixer", "ml", 0.015, 3000, 15000, [("Canette 250ml", 250, 3.75)]),
    ("Coca-Cola", "mixer", "ml", 0.004, 3000, 15000, [("Canette 330ml", 330, 1.32)]),
    ("Lemon Juice", "juice", "ml", 0.02, 1000, 5000, [("Bouteille 1L", 1000, 20)]),
    ("Lime Juice", "juice", "ml", 0.025, 1000, 5000, [("Bouteille 1L", 1000, 25)]),
    # Syrups / infusions (ml)
    ("Elderflower", "syrup", "ml", 0.03, 1000, 5000, [("Bouteille 500ml", 500, 15)]),
    ("Green Tea", "infusion", "ml", 0.01, 1000, 5000, [("Bouteille 1L", 1000, 10)]),
    ("Red Tea", "infusion", "ml", 0.01, 1000, 5000, [("Bouteille 1L", 1000, 10)]),
    ("Ginger", "aromatic", "g", 0.04, 500, 3000, [("Sachet 500g", 500, 20)]),
    ("Cucumber", "vegetable", "g", 0.008, 1000, 5000, [("Unité 500g", 500, 4)]),
    ("Pink Pepper", "spice", "g", 0.15, 100, 500, [("Sachet 100g", 100, 15)]),
    ("Spiced Pineapple", "fruit", "g", 0.03, 1000, 5000, [("Purée 1L", 1000, 30)]),
    ("Bitter Rosemary", "bitter", "ml", 0.2, 200, 1000, [("Flacon 200ml", 200, 40)]),
    ("Menthe", "herb", "g", 0.05, 500, 3000, [("Bouquet 100g", 100, 5)]),
    ("Sucre de canne", "other", "g", 0.01, 1000, 5000, [("Paquet 1kg", 1000, 10)]),
]

# ── Categories ──
CATEGORIES = [
    ("Crafted Cocktail V1", "crafted-v1", 1),
    ("Crafted Cocktail V2", "crafted-v2", 2),
    ("Margarita Style", "margarita-style", 3),
    ("Spritz", "spritz", 4),
    ("Punch Cocktail", "punch-cocktail", 5),
    ("Mojito", "mojito", 6),
    ("Shots", "shots", 7),
]

# ── Cocktails: (name, slug, category_slug, ingredients_list, recipe_items, pov1_price, pov2_available)
# recipe_items: (material_name, qty, waste%) — empty for Mojitos (incomplete recipe)
COCKTAILS = [
    # ── Crafted Cocktail V1 (POV1) ──
    ("Sweet 16", "sweet-16", "crafted-v1",
     ["Vodka x2", "Bubble Gum", "Strawberry", "Pineapple", "Sprite"],
     [("Vodka", 100, 2), ("Bubble Gum Syrup", 20, 0), ("Strawberry", 40, 5), ("Pineapple", 40, 5), ("Sprite", 100, 0)],
     28, True),
    ("Berryoska", "berryoska", "crafted-v1",
     ["Vodka x2", "Blueberry", "Raspberry", "Lime", "Sprite"],
     [("Vodka", 100, 2), ("Blueberry", 30, 5), ("Raspberry", 30, 5), ("Lime", 1, 0), ("Sprite", 100, 0)],
     28, True),
    ("Gold Suit", "gold-suit", "crafted-v1",
     ["Vodka", "Triple Sec", "Watermelon", "Strawberry", "Lime", "Sprite"],
     [("Vodka", 50, 2), ("Triple Sec", 20, 0), ("Watermelon", 50, 5), ("Strawberry", 30, 5), ("Lime", 1, 0), ("Sprite", 80, 0)],
     28, True),
    ("Peachnago", "peachnago", "crafted-v1",
     ["Rhum", "Gin", "Peach", "Mango", "Orange", "Lime"],
     [("Rhum Blanc", 40, 2), ("Gin", 20, 2), ("Peach", 40, 5), ("Mango", 40, 5), ("Orange", 30, 5), ("Lime", 1, 0)],
     28, False),
    ("El Cubano", "el-cubano", "crafted-v1",
     ["Gin", "Triple Sec", "Passion Fruit", "Rose", "Orange"],
     [("Gin", 50, 2), ("Triple Sec", 20, 0), ("Passion Fruit", 30, 5), ("Rose", 2, 0), ("Orange", 30, 5)],
     28, False),
    ("Hakuna Colada", "hakuna-colada", "crafted-v1",
     ["Rhum", "Triple Sec", "Coconut", "Strawberry", "Pineapple"],
     [("Rhum Blanc", 50, 2), ("Triple Sec", 20, 0), ("Coconut", 30, 0), ("Strawberry", 30, 5), ("Pineapple", 40, 5)],
     28, False),
    ("Sicilian Juice", "sicilian-juice", "crafted-v1",
     ["Vodka", "Rhum", "Blueberry", "Vanilla", "Pineapple", "Lime"],
     [("Vodka", 30, 2), ("Rhum Blanc", 30, 2), ("Blueberry", 30, 5), ("Vanilla", 5, 0), ("Pineapple", 50, 5), ("Lime", 1, 0)],
     28, False),

    # ── Crafted Cocktail V1 (POV2 only) ──
    ("Candy Crush", "candy-crush", "crafted-v1",
     ["Vodka", "Bubble Gum", "Strawberry", "Pineapple", "Lime Juice"],
     [("Vodka", 50, 2), ("Bubble Gum Syrup", 20, 0), ("Strawberry", 40, 5), ("Pineapple", 40, 5), ("Lime Juice", 15, 0)],
     None, True),
    ("Golden Bloom", "golden-bloom", "crafted-v1",
     ["White Rum", "Mango", "Elderflower", "Orange"],
     [("Rhum Blanc", 50, 2), ("Mango", 50, 5), ("Elderflower", 20, 0), ("Orange", 30, 5)],
     None, True),
    ("Fiore Rosa", "fiore-rosa", "crafted-v1",
     ["White Rum", "Coconut", "Pineapple", "Strawberry"],
     [("Rhum Blanc", 50, 2), ("Coconut", 30, 0), ("Pineapple", 40, 5), ("Strawberry", 30, 5)],
     None, True),
    ("Viola Royale", "viola-royale", "crafted-v1",
     ["Gin", "Blueberry", "Vanilla", "Lemon"],
     [("Gin", 50, 2), ("Blueberry", 40, 5), ("Vanilla", 5, 0), ("Lemon", 1, 0)],
     None, True),
    ("Peach-Tea", "peach-tea", "crafted-v1",
     ["Vodka", "Peach", "Red Tea", "Pineapple", "Lemon"],
     [("Vodka", 50, 2), ("Peach", 40, 5), ("Red Tea", 30, 0), ("Pineapple", 30, 5), ("Lemon", 1, 0)],
     None, True),
    ("Red Ruby", "red-ruby", "crafted-v1",
     ["Vodka", "Raspberry", "Rose Hibiscus", "Lime Juice", "Sprite"],
     [("Vodka", 50, 2), ("Raspberry", 30, 5), ("Rose Hibiscus", 3, 0), ("Lime Juice", 15, 0), ("Sprite", 80, 0)],
     None, True),
    ("Zenzero", "zenzero", "crafted-v1",
     ["Gin", "Watermelon", "Ginger", "Lemon", "Pineapple", "Soda"],
     [("Gin", 50, 2), ("Watermelon", 50, 5), ("Ginger", 10, 0), ("Lemon", 1, 0), ("Pineapple", 30, 5), ("Soda Water", 80, 0)],
     None, True),
    ("Green Lagoon", "green-lagoon", "crafted-v1",
     ["Gin", "Green Apple", "Kiwi", "Soda Water / Tonic"],
     [("Gin", 50, 2), ("Green Apple", 40, 5), ("Kiwi", 30, 5), ("Soda Water", 80, 0)],
     None, True),

    # ── Crafted Cocktail V2 (POV1) ──
    ("Spiced Negroni", "spiced-negroni", "crafted-v2",
     ["Campari", "Martini Blanc", "Gin", "Bitter Rosemary"],
     [("Campari", 30, 0), ("Martini Blanc", 30, 0), ("Gin", 30, 2), ("Bitter Rosemary", 5, 0)],
     30, False),
    ("Berrywhisky", "berrywhisky", "crafted-v2",
     ["Mixed Red Berry", "Blended Scotch Whisky", "Lime"],
     [("Raspberry", 40, 5), ("Blended Scotch Whisky", 60, 2), ("Lime", 1, 0)],
     30, False),
    ("Veneziano", "veneziano", "crafted-v2",
     ["Dry Gin", "Campari", "Passion Fruit", "Lime Juice"],
     [("Dry Gin", 40, 2), ("Campari", 20, 0), ("Passion Fruit", 30, 5), ("Lime Juice", 15, 0)],
     30, False),

    # ── Crafted Cocktail V2 (POV2 only) ──
    ("Speedy Gonzales", "speedy-gonzales", "crafted-v2",
     ["Vodka", "Rhum", "Gin", "Triple Sec", "Tequila", "Lemon", "Red Bull"],
     [("Vodka", 20, 2), ("Rhum Blanc", 20, 2), ("Gin", 20, 2), ("Triple Sec", 20, 0), ("Tequila", 20, 2), ("Lemon", 1, 0), ("Red Bull", 100, 0)],
     None, True),
    ("Dolce Habibi", "dolce-habibi", "crafted-v2",
     ["Vodka", "Rhum", "Gin", "Triple Sec", "Tequila", "Sour Cherry"],
     [("Vodka", 20, 2), ("Rhum Blanc", 20, 2), ("Gin", 20, 2), ("Triple Sec", 20, 0), ("Tequila", 20, 2), ("Sour Cherry", 40, 5)],
     None, True),
    ("Calimucho", "calimucho", "crafted-v2",
     ["Vodka", "Rhum", "Gin", "Triple Sec", "Tequila", "Coca-Cola", "Lime"],
     [("Vodka", 20, 2), ("Rhum Blanc", 20, 2), ("Gin", 20, 2), ("Triple Sec", 20, 0), ("Tequila", 20, 2), ("Coca-Cola", 100, 0), ("Lime", 1, 0)],
     None, True),
    ("Lychee Pearl", "lychee-pearl", "crafted-v2",
     ["Vodka", "Rhum", "Gin", "Triple Sec", "Tequila", "Lychee", "Sprite"],
     [("Vodka", 20, 2), ("Rhum Blanc", 20, 2), ("Gin", 20, 2), ("Triple Sec", 20, 0), ("Tequila", 20, 2), ("Lychee", 40, 5), ("Sprite", 80, 0)],
     None, True),

    # ── Margarita Style (POV1) ──
    ("Tonic Citrus", "tonic-citrus", "margarita-style",
     ["Bergamote", "Citron", "Rosemary", "Gin"],
     [("Bergamote", 10, 0), ("Lemon", 1, 0), ("Rosemary", 3, 0), ("Gin", 50, 2)],
     25, False),
    ("Lyche Cosmo N2", "lyche-cosmo-n2", "margarita-style",
     ["Lychee", "Cranberry", "Thyme", "Vodka"],
     [("Lychee", 40, 5), ("Cranberry", 30, 5), ("Thyme", 3, 0), ("Vodka", 50, 2)],
     25, False),
    ("Limoncello Fruit", "limoncello-fruit", "margarita-style",
     ["Limoncello", "Passion Fruit", "Gin"],
     [("Limoncello", 30, 0), ("Passion Fruit", 30, 5), ("Gin", 40, 2)],
     25, False),

    # ── Spritz (both POVs, same recipes) ──
    ("Green Tea Spritz", "green-tea-spritz", "spritz",
     ["Green Tea", "White Choppin", "Soda"],
     [("Green Tea", 40, 0), ("White Choppin", 60, 0), ("Soda Water", 100, 0)],
     20, False),
    ("Aperol Spritz", "aperol-spritz", "spritz",
     ["Aperol", "White Choppin", "Soda"],
     [("Aperol", 40, 0), ("White Choppin", 60, 0), ("Soda Water", 100, 0)],
     20, True),
    ("Limoncello Spritz", "limoncello-spritz", "spritz",
     ["Limoncello", "White Choppin", "Soda"],
     [("Limoncello", 40, 0), ("White Choppin", 60, 0), ("Soda Water", 100, 0)],
     20, True),
    ("Campari Spritz", "campari-spritz", "spritz",
     ["Campari", "White Choppin", "Soda"],
     [("Campari", 40, 0), ("White Choppin", 60, 0), ("Soda Water", 100, 0)],
     20, False),

    # ── Punch Cocktail (POV1) ──
    ("Peach & Fig Punch", "peach-fig-punch", "punch-cocktail",
     ["Rhum", "White Wine", "Peach", "Fig", "Orange", "Lime"],
     [("Rhum Blanc", 40, 2), ("White Wine", 40, 0), ("Peach", 30, 5), ("Fig", 30, 5), ("Orange", 20, 5), ("Lime", 1, 0)],
     30, False),
    ("Ruby Tea Punch", "ruby-tea-punch", "punch-cocktail",
     ["Rhum", "White Wine", "Red Tea", "Passion Fruit", "Pomegranate", "Lime"],
     [("Rhum Blanc", 40, 2), ("White Wine", 40, 0), ("Red Tea", 30, 0), ("Passion Fruit", 20, 5), ("Pomegranate", 20, 5), ("Lime", 1, 0)],
     30, False),

    # ── Mojito (POV1) — NO recipe (incomplete data per user) ──
    ("Mediterranean Mojito", "mediterranean-mojito", "mojito",
     ["Concombre", "Ginger"], [], 22, False),
    ("Passion Fruit Mojito", "passion-fruit-mojito", "mojito",
     ["Passion Fruit"], [], 22, True),
    ("Blueberry Mojito", "blueberry-mojito", "mojito",
     ["Blueberry / Myrtille"], [], 22, True),
    ("Mango Alphonso Mojito", "mango-alphonso-mojito", "mojito",
     ["Mango Alphonso"], [], 22, True),
    ("Mixed Red Berry Mojito", "mixed-red-berry-mojito", "mojito",
     ["Strawberry", "Raspberry"], [], 22, True),

    # ── Mojito (POV2 only) ──
    ("Énergétique Mojito", "energetique-mojito", "mojito",
     ["Red Bull"], [], None, True),
    ("Watermelon Mojito", "watermelon-mojito", "mojito",
     ["Watermelon"], [], None, True),

    # ── Shots (POV1) ──
    ("Tequila Shot", "tequila-shot", "shots",
     ["Tequila"], [("Tequila", 40, 0)], 14, False),
    ("B52", "b52", "shots",
     ["Non détaillé"], [], 14, True),
    ("Posh", "posh", "shots",
     ["Vodka", "Passion Fruit", "Elderflower"],
     [("Vodka", 30, 2), ("Passion Fruit", 15, 5), ("Elderflower", 10, 0)], 14, False),
    ("Kiss", "kiss", "shots",
     ["Vodka", "Triple Sec", "Strawberry"],
     [("Vodka", 30, 2), ("Triple Sec", 15, 0), ("Strawberry", 20, 5)], 14, False),
    ("Ginger Mango", "ginger-mango", "shots",
     ["Mango", "Ginger", "Lime", "Gin"],
     [("Mango", 30, 5), ("Ginger", 10, 0), ("Lime", 1, 0), ("Gin", 30, 2)], 14, False),

    # ── Shots (POV2 only) ──
    ("Mexicano Shot", "mexicano-shot", "shots",
     ["Spiced Pineapple", "Pink Pepper", "Vodka", "Gin"],
     [("Spiced Pineapple", 20, 5), ("Pink Pepper", 2, 0), ("Vodka", 20, 2), ("Gin", 20, 2)], None, True),
    ("Coco Chanel", "coco-chanel", "shots",
     ["Bergamote", "Rosemary", "Gin", "Lime"],
     [("Bergamote", 10, 0), ("Rosemary", 3, 0), ("Gin", 30, 2), ("Lime", 1, 0)], None, True),
    ("Nina Ricci", "nina-ricci", "shots",
     ["Cranberry", "Thyme", "Vodka", "Gin"],
     [("Cranberry", 20, 5), ("Thyme", 3, 0), ("Vodka", 20, 2), ("Gin", 20, 2)], None, True),
    ("Tequila Shots", "tequila-shots", "shots",
     ["Tequila"], [("Tequila", 40, 0)], None, True),
    ("Meeter Shooters", "meeter-shooters", "shots",
     ["Non détaillé"], [], None, False),
]


def seed_all():
    """Seed the database with real data from 2 points of sale."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("[OK] Database already seeded, skipping.")
            return

        print("Seeding database with real POS data...")

        # ── Users ──
        admin = User(id=gen_id(), email="admin@millegusti.com", full_name="Admin MILLE GUSTI",
                     hashed_password=hash_password("millegusti2026"), role="SUPER_ADMIN", is_active=True)
        stock_mgr = User(id=gen_id(), email="stock@millegusti.com", full_name="Stock Manager",
                         hashed_password=hash_password("millegusti2026"), role="STOCK_MANAGER", is_active=True)
        marketing = User(id=gen_id(), email="marketing@millegusti.com", full_name="Marketing User",
                         hashed_password=hash_password("millegusti2026"), role="MARKETING", is_active=True)
        db.add_all([admin, stock_mgr, marketing])

        # ── Categories ──
        cat_map = {}
        for name, slug, order in CATEGORIES:
            cat = Category(id=gen_id(), name={"fr": name, "en": name, "ar": name}, slug=slug, sort_order=order)
            db.add(cat)
            cat_map[slug] = cat

        # ── Establishments ──
        est1 = Establishment(id=gen_id(), name="Point de Vente 1", slug="point-de-vente-1",
                             description={"fr": "Premier point de vente", "en": "First point of sale", "ar": "نقطة بيع 1"},
                             logo_url="", cover_image_url="https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?auto=format&fit=crop&w=1200&q=80")
        est2 = Establishment(id=gen_id(), name="Point de Vente 2", slug="point-de-vente-2",
                             description={"fr": "Deuxième point de vente", "en": "Second point of sale", "ar": "نقطة بيع 2"},
                             logo_url="", cover_image_url="https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=80")
        db.add_all([est1, est2])

        # ── Raw materials + packagings ──
        mat_map = {}
        for name, cat, unit, cost, min_t, max_t, pkgs in MATERIALS:
            rm = RawMaterial(id=gen_id(), name=name, category=cat, base_unit=unit,
                             cost_per_unit=cost, min_threshold=min_t, max_threshold=max_t)
            db.add(rm)
            db.flush()
            for pkg_name, qty, pkg_cost in pkgs:
                db.add(Packaging(id=gen_id(), raw_material_id=rm.id, name=pkg_name,
                                 quantity_per_package=qty, unit=unit, cost_per_package=pkg_cost, is_default=True))
            mat_map[name] = rm

        # ── Cocktails + Recipes + Menu items ──
        cocktail_count = 0
        for name, slug, cat_slug, ingredients, recipe_items, pov1_price, pov2_available in COCKTAILS:
            cat = cat_map[cat_slug]
            ck = Cocktail(
                id=gen_id(), name=name, slug=slug,
                description={"fr": f"Cocktail {name}", "en": f"{name} cocktail", "ar": f"كوكتيل {name}"},
                image_url=f"https://images.unsplash.com/photo-1551024709-8f23befc6f87?auto=format&fit=crop&w=600&q=80",
                base_price=pov1_price or 25, ingredients=ingredients, allergens=[],
                alcoholic=True, is_new=False, available="available", category_id=cat.id,
            )
            db.add(ck)
            cocktail_count += 1

            # POV1 menu item (if has price)
            if pov1_price is not None:
                db.add(MenuItem(id=gen_id(), establishment_id=est1.id, cocktail_id=ck.id,
                                price=pov1_price, available=True, order=cocktail_count))

            # POV2 menu item (if available there) — price = pov1_price - 3 or 25 default
            if pov2_available:
                pov2_price = (pov1_price - 3) if pov1_price else 25
                db.add(MenuItem(id=gen_id(), establishment_id=est2.id, cocktail_id=ck.id,
                                price=pov2_price, available=True, order=cocktail_count))

            # Recipe (if has recipe items)
            if recipe_items:
                recipe = Recipe(id=gen_id(), cocktail_id=ck.id, version=1, updated_by=admin.id)
                db.add(recipe)
                db.flush()
                for mat_name, qty, waste in recipe_items:
                    rm = mat_map.get(mat_name)
                    if rm:
                        db.add(RecipeItem(id=gen_id(), recipe_id=recipe.id,
                                          raw_material_id=rm.id, quantity=qty, waste_percentage=waste))

        # ── Services ──
        for slug, title in [("cocktail-catering", "Cocktail Catering"), ("event-mixology", "Event Mixology"),
                            ("menu-creation", "Menu Creation"), ("signature-cocktails", "Signature Cocktails"),
                            ("consulting", "Consulting"), ("training", "Training")]:
            db.add(Service(id=gen_id(), title={"fr": title, "en": title, "ar": title},
                           description={"fr": "Description", "en": "Description", "ar": "وصف"},
                           slug=slug, icon="Wine",
                           image_url="https://images.unsplash.com/photo-1551024709-8f23befc6f87?auto=format&fit=crop&w=600&q=80",
                           benefits=[{"fr": "Bénéfice", "en": "Benefit", "ar": "فائدة"}]))

        # ── Gallery ──
        for i in range(6):
            db.add(GalleryItem(id=gen_id(), title={"fr": f"Réalisation {i+1}", "en": f"Creation {i+1}", "ar": f"إنجاز {i+1}"},
                               image_url="https://images.unsplash.com/photo-1551024709-8f23befc6f87?auto=format&fit=crop&w=600&q=80",
                               sort_order=i))

        # ── Scans (analytics) ──
        for i in range(80):
            db.add(ScanEvent(id=gen_id(), establishment_id=est1.id if i % 2 == 0 else est2.id,
                             scanned_at=datetime.utcnow() - timedelta(days=i % 30, hours=i % 24)))

        # ── Quotes ──
        for name, ev, st in [("Sophie Martin", "Mariage", "new"), ("Karim Ben Ali", "Corporate", "contacted"),
                             ("Laura Dubois", "Anniversaire", "won"), ("Mohamed Trabelsi", "Beach Club", "new")]:
            db.add(QuoteRequest(id=gen_id(), full_name=name, email=f"{name.split()[0].lower()}@example.com",
                                phone="+216 22 123 456", event_type=ev, guests=50, message="Devis souhaité", status=st))

        # ── Settings ──
        db.add(AppSettings(id=1, stats={"events": 150, "cocktails_created": 300, "partners": 25, "years_experience": 8},
                           contact={"phone": "+216 71 123 456", "email": "contact@millegusti.com", "address": "Tunis, Tunisia"},
                           branding={"primary_color": "#063D2F", "accent_color": "#C06BE8"}))

        # ── Employees (with linked User accounts for bartender login) ──
        # Create User accounts for bartenders so they can log in
        ahmed_user = User(id=gen_id(), email="ahmed@millegusti.com", full_name="Ahmed Sallem",
                         hashed_password=hash_password("millegusti2026"), role="BARTENDER", is_active=True)
        fatma_user = User(id=gen_id(), email="fatma@millegusti.com", full_name="Fatma Trabelsi",
                         hashed_password=hash_password("millegusti2026"), role="BARTENDER", is_active=True)
        db.add_all([ahmed_user, fatma_user])
        db.flush()

        emp1 = Employee(id=gen_id(), first_name="Ahmed", last_name="Sallem", role="bartender", phone="+216 22 111", email="ahmed@millegusti.com", user_id=ahmed_user.id)
        emp2 = Employee(id=gen_id(), first_name="Fatma", last_name="Trabelsi", role="bartender", phone="+216 22 222", email="fatma@millegusti.com", user_id=fatma_user.id)
        emp3 = Employee(id=gen_id(), first_name="Youssef", last_name="Ben Ali", role="bartender", phone="+216 22 333")
        emp4 = Employee(id=gen_id(), first_name="Nour", last_name="Hamdi", role="bar_manager", phone="+216 22 444")
        db.add_all([emp1, emp2, emp3, emp4])
        db.flush()
        for emp, ests in [(emp1, [est1]), (emp2, [est1]), (emp3, [est2]), (emp4, [est1, est2])]:
            for est in ests:
                db.add(EmployeeEstablishment(id=gen_id(), employee_id=emp.id, establishment_id=est.id))

        # ── Stock: INITIAL_STOCK for all materials in both establishments ──
        for est in [est1, est2]:
            for rm in mat_map.values():
                initial_qty = rm.max_threshold * 0.6
                db.add(StockMovement(
                    id=gen_id(), establishment_id=est.id, raw_material_id=rm.id,
                    movement_type="INITIAL_STOCK", quantity=initial_qty, unit=rm.base_unit,
                    reference="seed", reference_type="initial",
                ))
                db.add(StockLevel(
                    id=gen_id(), establishment_id=est.id, raw_material_id=rm.id,
                    theoretical_qty=initial_qty, real_qty=None, unit=rm.base_unit,
                ))

        # ── Shift Slots (predefined time slots) ──
        db.add(ShiftSlot(id=gen_id(), name="Matin", name_fr="Matin (06h - 14h)", name_en="Morning (6am - 2pm)", name_ar="صباحية (06:00 - 14:00)",
                         start_time="06:00", end_time="14:00", is_overnight=False, sort_order=1, is_active=True))
        db.add(ShiftSlot(id=gen_id(), name="Soir", name_fr="Soir (14h - 22h)", name_en="Evening (2pm - 10pm)", name_ar="مسائية (14:00 - 22:00)",
                         start_time="14:00", end_time="22:00", is_overnight=False, sort_order=2, is_active=True))
        db.add(ShiftSlot(id=gen_id(), name="Nuit", name_fr="Nuit (22h - 06h)", name_en="Night (10pm - 6am)", name_ar="ليلية (22:00 - 06:00)",
                         start_time="22:00", end_time="06:00", is_overnight=True, sort_order=3, is_active=True))
        db.flush()

        # ── Shifts ──
        # Find some cocktails with recipes for production
        ck_with_recipes = db.query(Cocktail).filter(Cocktail.slug.in_(
            ["sweet-16", "berryoska", "aperol-spritz", "gold-suit"]
        )).all()

        # Closed shift (yesterday, POV1, emp1)
        shift1 = Shift(id=gen_id(), establishment_id=est1.id, employee_id=emp1.id,
                       date=date.today() - timedelta(days=1),
                       opened_at=datetime.utcnow() - timedelta(days=1, hours=8),
                       closed_at=datetime.utcnow() - timedelta(days=1, hours=2), status="closed")
        db.add(shift1)
        db.flush()
        if len(ck_with_recipes) >= 2:
            db.add(ShiftProduction(id=gen_id(), shift_id=shift1.id, cocktail_id=ck_with_recipes[0].id, quantity=35))
            db.add(ShiftProduction(id=gen_id(), shift_id=shift1.id, cocktail_id=ck_with_recipes[1].id, quantity=20))

        # Open shift (today, POV2, emp3)
        shift3 = Shift(id=gen_id(), establishment_id=est2.id, employee_id=emp3.id,
                       date=date.today(), opened_at=datetime.utcnow() - timedelta(hours=4), status="open")
        db.add(shift3)

        # ── Supply request ──
        tequila_rm = mat_map.get("Tequila")
        if tequila_rm:
            req = SupplyRequest(id=gen_id(), establishment_id=est1.id, requested_by=stock_mgr.id, status="PENDING", notes="Stock bas Tequila")
            db.add(req)
            db.flush()
            db.add(SupplyRequestItem(id=gen_id(), supply_request_id=req.id, raw_material_id=tequila_rm.id,
                                     requested_quantity=2000, suggested_quantity=2000, unit="ml"))

        # ── Alerts ──
        db.add(Alert(id=gen_id(), type="SUPPLY_PENDING", severity="info", establishment_id=est1.id,
                     supply_request_id=req.id if tequila_rm else None,
                     message="Demande d'approvisionnement en attente pour Tequila"))
        db.add(Alert(id=gen_id(), type="SHIFT_WAITING_VALIDATION", severity="info", establishment_id=est1.id,
                     shift_id=shift1.id, message="Shift en attente de validation (Ahmed Sallem)"))

        db.commit()
        print(f"[OK] Database seeded: {db.query(User).count()} users, "
              f"{db.query(Category).count()} categories, "
              f"{db.query(Cocktail).count()} cocktails, "
              f"{db.query(RawMaterial).count()} materials, "
              f"{db.query(Recipe).count()} recipes, "
              f"{db.query(MenuItem).count()} menu items, "
              f"{db.query(StockLevel).count()} stock levels, "
              f"{db.query(Shift).count()} shifts, "
              f"{db.query(Alert).count()} alerts")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Seed error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
