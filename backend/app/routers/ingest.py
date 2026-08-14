import threading
import time as _time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session  # noqa: F401  -- kept for future routes

from app.config import settings
from app.db import SessionLocal, get_db  # noqa: F401
from app.deps import require_admin_token
from app.ingestion.runner import run_all_sources

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

_ingest_status: dict = {
    "running": False,
    "last_result": None,
    "last_run_at": None,
    "next_run_at": None,
    "scheduler_thread_alive": False,
}
_scheduler_started = False
_scheduler_lock = threading.Lock()


def _run_in_thread() -> None:
    _ingest_status["running"] = True
    try:
        db = SessionLocal()
        try:
            result = run_all_sources(db, trigger="api")
        finally:
            db.close()
        _ingest_status["last_result"] = result
        _ingest_status["last_run_at"] = datetime.now(UTC).isoformat()
    except Exception as exc:
        _ingest_status["last_result"] = {"error": str(exc)}
    finally:
        _ingest_status["running"] = False


def _parse_schedule_time(value: str) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        hh, mm = value.split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    return None


def _next_run_at(now: datetime, schedule: tuple[int, int]) -> datetime:
    h, m = schedule
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _scheduler_loop() -> None:
    schedule = _parse_schedule_time(settings.ingest_schedule_time)
    if schedule is None:
        _ingest_status["scheduler_thread_alive"] = False
        return
    while True:
        now = datetime.now(UTC)
        target = _next_run_at(now, schedule)
        _ingest_status["next_run_at"] = target.isoformat()
        sleep_secs = max(1.0, (target - now).total_seconds())
        _time.sleep(sleep_secs)
        if _ingest_status["running"]:
            # Manual run beat the scheduler to it; let it finish, loop will
            # schedule the next iteration.
            continue
        try:
            _run_in_thread()
        except Exception as exc:  # pragma: no cover -- defensive
            _ingest_status["last_result"] = {"error": f"scheduler: {exc}"}


def start_scheduler() -> None:
    """Idempotent — safe to call from FastAPI startup."""
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        if _parse_schedule_time(settings.ingest_schedule_time) is None:
            _ingest_status["scheduler_thread_alive"] = False
            return
        t = threading.Thread(
            target=_scheduler_loop, name="ingest-scheduler", daemon=True
        )
        t.start()
        _ingest_status["scheduler_thread_alive"] = True
        _scheduler_started = True


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
        "last_run_at": _ingest_status["last_run_at"],
        "next_run_at": _ingest_status["next_run_at"],
        "scheduler_thread_alive": _ingest_status["scheduler_thread_alive"],
        "schedule_time_utc": settings.ingest_schedule_time or None,
    }
