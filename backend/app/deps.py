import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    # compare_digest, not ==: a plain string compare short-circuits on the
    # first wrong byte, which leaks the token's prefix to a patient caller.
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token, settings.admin_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )
