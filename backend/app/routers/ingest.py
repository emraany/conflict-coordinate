from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin_token
from app.ingestion.runner import run_all_sources

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("/run", dependencies=[Depends(require_admin_token)])
def trigger_ingest(db: Session = Depends(get_db)) -> dict:
    return run_all_sources(db)
