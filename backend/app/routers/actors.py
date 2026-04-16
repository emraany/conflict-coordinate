from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin_token
from app.models import Actor
from app.schemas import ActorCreate, ActorOut, ActorUpdate

router = APIRouter(prefix="/api/actors", tags=["actors"])


@router.get("", response_model=list[ActorOut])
def list_actors(db: Session = Depends(get_db)) -> list[Actor]:
    return list(db.scalars(select(Actor).order_by(Actor.name)))


@router.get("/{actor_id}", response_model=ActorOut)
def get_actor(actor_id: int, db: Session = Depends(get_db)) -> Actor:
    actor = db.get(Actor, actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return actor


@router.post(
    "",
    response_model=ActorOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_token)],
)
def create_actor(payload: ActorCreate, db: Session = Depends(get_db)) -> Actor:
    actor = Actor(**payload.model_dump())
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


@router.patch(
    "/{actor_id}",
    response_model=ActorOut,
    dependencies=[Depends(require_admin_token)],
)
def update_actor(
    actor_id: int, payload: ActorUpdate, db: Session = Depends(get_db)
) -> Actor:
    actor = db.get(Actor, actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(actor, k, v)
    db.commit()
    db.refresh(actor)
    return actor


@router.delete(
    "/{actor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def delete_actor(actor_id: int, db: Session = Depends(get_db)) -> None:
    actor = db.get(Actor, actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    db.delete(actor)
    db.commit()
