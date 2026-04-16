from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin_token
from app.models import Source
from app.schemas import SourceOut

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: int, db: Session = Depends(get_db)) -> Source:
    src = db.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return src


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def delete_source(source_id: int, db: Session = Depends(get_db)) -> None:
    src = db.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(src)
    db.commit()
