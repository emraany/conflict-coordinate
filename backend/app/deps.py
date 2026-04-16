from fastapi import Header, HTTPException, status

from app.config import settings


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )
