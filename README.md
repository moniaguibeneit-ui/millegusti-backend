# MILLE GUSTI — Backend FastAPI

Backend API pour **MILLE GUSTI**, maison de mixologie.

## Stack

| Domaine | Techno |
|---|---|
| Framework | FastAPI 0.115 |
| ORM | SQLAlchemy 2.0 |
| DB | SQLite (dev) / PostgreSQL (prod) |
| Auth | JWT (python-jose) + bcrypt |
| Validation | Pydantic 2.10 |

## Demarrage rapide

### Prerequis
- Python >= 3.12
- pip

### Installation
```bash
cd backend
pip install -r requirements.txt
```

### Configuration
Copier `.env.example` en `.env` :
```env
# SQLite pour le dev local (auto)
DATABASE_URL=sqlite:///./millegusti.db

# Pour PostgreSQL en production :
# DATABASE_URL=postgresql://user:password@localhost:5432/millegusti

SECRET_KEY=your-secret-key
CORS_ORIGINS=http://localhost:5173,http://localhost:5175
```

### Lancement
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- API : http://localhost:8000
- Docs Swagger : http://localhost:8000/docs
- Docs ReDoc : http://localhost:8000/redoc

### Compte admin
```
Email    : admin@millegusti.com
Password : millegusti2026
```

## Structure

```
backend/
├── app/
│   ├── main.py              # Entry point FastAPI
│   ├── seed.py              # Initialisation + seed data
│   ├── core/
│   │   ├── config.py        # Settings (env vars)
│   │   ├── database.py      # SQLAlchemy engine + session
│   │   ├── security.py      # JWT + bcrypt
│   │   └── utils.py
│   ├── models/
│   │   └── __init__.py      # Tous les modeles SQLAlchemy
│   ├── schemas/
│   │   └── __init__.py      # Tous les DTOs Pydantic
│   ├── services/
│   │   └── stock_service.py # Business logic (consommation, stock, autonomie)
│   └── api/
│       ├── deps.py          # Auth dependency
│       └── routers/
│           ├── auth.py      # /api/auth/*
│           ├── content.py   # /api/cocktails, categories, services, gallery
│           ├── establishments.py # /api/establishments, menu, scans
│           ├── admin.py     # /api/quote-requests, settings, dashboard, analytics
│           └── stock.py     # /api/raw-materials, recipes, shifts, stock, inventory, supply
├── requirements.txt
├── .env.example
└── .env
```

## Routes API

### Auth
```
POST   /api/auth/login          # Returns JWT token
GET    /api/auth/me             # Current user (protected)
```

### Content (public read, admin write)
```
GET    /api/categories
POST   /api/categories          # admin
PUT    /api/categories/{id}     # admin
DELETE /api/categories/{id}     # admin

GET    /api/cocktails
GET    /api/cocktails/{slug}
POST   /api/cocktails           # admin
PUT    /api/cocktails/{id}      # admin
DELETE /api/cocktails/{id}      # admin

GET    /api/services
GET    /api/services/{slug}
POST   /api/services            # admin
PUT    /api/services/{id}       # admin
DELETE /api/services/{id}       # admin

GET    /api/gallery
```

### Establishments + Menu
```
GET    /api/establishments
GET    /api/establishments/{slug}
POST   /api/establishments      # admin
PUT    /api/establishments/{id} # admin
DELETE /api/establishments/{id} # admin

GET    /api/establishments/{slug}/menu      # public (QR menu)
GET    /api/establishments/{id}/menu/all    # admin
POST   /api/establishments/{id}/menu        # admin
PUT    /api/establishments/{id}/menu/{itemId} # admin
DELETE /api/establishments/{id}/menu/{itemId} # admin

POST   /api/analytics/scan      # Record QR scan
```

### Admin
```
POST   /api/quote-requests              # public
GET    /api/admin/quote-requests        # admin
GET    /api/admin/quote-requests/{id}   # admin
PATCH  /api/admin/quote-requests/{id}/status # admin
DELETE /api/admin/quote-requests/{id}   # admin

GET    /api/settings                    # public
PUT    /api/settings                    # admin

GET    /api/admin/dashboard             # admin
GET    /api/admin/analytics             # admin
```

### Stock & Production (all admin)
```
# Raw materials
GET    /api/raw-materials
POST   /api/raw-materials
PUT    /api/raw-materials/{id}
DELETE /api/raw-materials/{id}

# Recipes
GET    /api/recipes
GET    /api/recipes/cocktail/{cocktailId}
PUT    /api/recipes                    # upsert
DELETE /api/recipes/{id}

# Employees
GET    /api/employees
POST   /api/employees
PUT    /api/employees/{id}
DELETE /api/employees/{id}

# Shifts
GET    /api/shifts
GET    /api/shifts/{id}
POST   /api/shifts                     # open
POST   /api/shifts/{id}/close          # with productions
POST   /api/shifts/{id}/validate       # compute consumption, update stock
GET    /api/shifts/{id}/consumption

# Stock
GET    /api/stock
GET    /api/stock/establishment/{id}
PUT    /api/stock/establishment/{id}/{rawMaterialId}
GET    /api/stock/movements
POST   /api/stock/supply
GET    /api/stock/dashboard
GET    /api/stock/establishment/{id}/autonomy

# Inventory
GET    /api/inventories
POST   /api/inventories

# Supply requests
GET    /api/supply-requests
GET    /api/supply-requests/suggest/{establishmentId}
POST   /api/supply-requests
PATCH  /api/supply-requests/{id}/status

# Analytics
GET    /api/analytics/production
GET    /api/analytics/consumption
```

## Business Logic — Shift Validation

Le coeur du module stock :

```
1. Cocktailiste ouvre un shift (POST /api/shifts)
2. A la fin du shift, saisit la production (POST /api/shifts/{id}/close)
   - Ex: Mojito=35, Margarita=20, Negroni=15
3. Validation (POST /api/shifts/{id}/validate)
   - Pour chaque cocktail produit, recupere la recette
   - Calcule la consommation: quantite_recette * nb_cocktails * (1 + waste%)
   - Convertit les unites (ml, cl, l, g, kg, unit)
   - Soustrait du stock theorique
   - Cree les enregistrements de consommation + mouvements
4. Le stock dashboard reflete le nouveau stock
5. L'autonomie est calculee (jours restants base sur la moyenne de consommation)
```

## Branchement Frontend

Dans `frontend/.env` :
```env
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://localhost:8000/api
```

Le frontend bascule automatiquement du mock vers l'API reelle.
