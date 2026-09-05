"""MILLE GUSTI API — FastAPI application entry point."""
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.routers import auth, content, establishments, admin, stock
from app.seed import seed_all

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables + seed on startup
    seed_all()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for MILLE GUSTI — mixology brand, QR menus, stock & production management.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(auth.router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(establishments.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(stock.router, prefix="/api")

# ── Static files for uploads ──
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload an image file. Returns the public URL."""
    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"File type {file.content_type} not allowed. Use JPEG, PNG, WebP, GIF, or SVG.")
    # Validate size (max 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large. Max 5MB.")
    # Generate unique filename
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(contents)
    return {"url": f"/uploads/{filename}", "filename": filename}


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
