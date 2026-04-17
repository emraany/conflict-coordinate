import threading

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.deps import require_admin_token
from app.ingestion.runner import run_all_sources

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

_ingest_status: dict = {"running": False, "last_result": None}


def _run_in_thread() -> None:
    _ingest_status["running"] = True
    try:
        db = SessionLocal()
        result = run_all_sources(db)
        _ingest_status["last_result"] = result
    except Exception as exc:
        _ingest_status["last_result"] = {"error": str(exc)}
    finally:
        _ingest_status["running"] = False


@router.post("/run", dependencies=[Depends(require_admin_token)])
def trigger_ingest() -> dict:
    if _ingest_status["running"]:
        return {"status": "already_running"}
    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()
    return {"status": "started"}


@router.get("/status", dependencies=[Depends(require_admin_token)])
def ingest_status() -> dict:
    return {
        "running": _ingest_status["running"],
        "last_result": _ingest_status["last_result"],
    }
