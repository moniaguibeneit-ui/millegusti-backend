"""Auth router — login + me + user management."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token
from app.api.deps import get_current_user, require_role
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserOut, UserCreate, UserUpdate
from app.services.audit_service import log_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True, User.deleted_at == None).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user.last_login = datetime.utcnow()
    db.commit()
    token = create_access_token(user.id, {"email": user.email, "role": user.role})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# ── User management (admin only) ──
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_role("ADMIN"))):
    return db.query(User).filter(User.deleted_at == None).all()


@router.post("/users", response_model=UserOut)
def create_user(body: UserCreate, db: Session = Depends(get_db), user: User = Depends(require_role("ADMIN"))):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(400, "Email already registered")
    new_user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
        phone=body.phone,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    log_audit(db, user.id, "CREATE", "user", new_user.id, after_data={"email": new_user.email, "role": new_user.role})
    db.commit()
    return new_user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate, db: Session = Depends(get_db), current: User = Depends(require_role("ADMIN"))):
    target = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not target:
        raise HTTPException(404, "User not found")
    before = {"email": target.email, "role": target.role, "is_active": target.is_active}
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(target, k, v)
    db.commit()
    db.refresh(target)
    log_audit(db, current.id, "UPDATE", "user", target.id, before_data=before, after_data=body.model_dump(exclude_unset=True))
    db.commit()
    return target


@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), current: User = Depends(require_role("ADMIN"))):
    target = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not target:
        raise HTTPException(404, "User not found")
    # Soft delete
    target.is_active = False
    target.deleted_at = datetime.utcnow()
    db.commit()
    log_audit(db, current.id, "DELETE", "user", target.id)
    db.commit()
    return {"ok": True}
