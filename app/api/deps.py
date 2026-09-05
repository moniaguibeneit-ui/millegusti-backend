"""FastAPI dependencies for auth + role-based permissions."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)

# Role hierarchy for permission checks
ROLE_HIERARCHY = {
    "SUPER_ADMIN": 100,
    "ADMIN": 90,
    "STOCK_MANAGER": 70,
    "ESTABLISHMENT_MANAGER": 60,
    "BARTENDER": 30,
    "MARKETING": 50,
}

# What each role can access
ROLE_PERMISSIONS = {
    "SUPER_ADMIN": "*",  # everything
    "ADMIN": "*",  # everything except super-admin actions
    "STOCK_MANAGER": ["stock", "raw_materials", "inventory", "supply", "recipes", "analytics_stock"],
    "ESTABLISHMENT_MANAGER": ["establishments", "shifts", "production", "stock_local", "inventory_local", "supply_local"],
    "BARTENDER": ["shifts_own", "production_own", "establishments_view"],
    "MARKETING": ["cocktails", "categories", "services", "gallery", "analytics_qr", "settings", "quotes"],
}


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.is_active == True, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_role(*allowed_roles: str):
    """Dependency factory: require one of the given roles.
    SUPER_ADMIN and ADMIN always pass."""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role in ("SUPER_ADMIN", "ADMIN"):
            return user
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not allowed. Required: {', '.join(allowed_roles)}"
            )
        return user
    return checker


def require_permission(permission: str):
    """Dependency factory: require a specific permission.
    SUPER_ADMIN and ADMIN always pass."""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role in ("SUPER_ADMIN", "ADMIN"):
            return user
        perms = ROLE_PERMISSIONS.get(user.role, [])
        if perms == "*":
            return user
        if permission not in perms and "*" not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' not granted for role '{user.role}'"
            )
        return user
    return checker
