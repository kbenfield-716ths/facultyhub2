"""
Divisions API — the groups inside the department (PCCM, MICU APPs, …).

  GET    /api/divisions           — list divisions (any authenticated user)
  POST   /api/divisions           — upsert a division (admin)
  DELETE /api/divisions/{key}     — remove (admin; blocks if members/rotations exist unless force=true)

One shared faculty table holds every user with a division_key flag; regular
users see only their division, admins pick a division in the admin header.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.models import Division, Faculty, get_db
from backend.auth import get_current_user, require_admin
from backend.routes.config import _get

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/divisions", tags=["divisions"])


class DivisionDef(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=80)
    color: Optional[str] = None
    is_active: bool = True


def _serialize(d: Division, member_count: int = None) -> dict:
    out = {"key": d.key, "label": d.label, "color": d.color, "is_active": d.is_active}
    if member_count is not None:
        out["member_count"] = member_count
    return out


@router.get("")
def list_divisions(
    db: Session = Depends(get_db),
    user: Faculty = Depends(get_current_user),
):
    divisions = db.query(Division).order_by(Division.label).all()
    if user.is_admin:
        counts = {}
        for (k,) in db.query(Faculty.division_key).filter(Faculty.division_key.isnot(None)).all():
            counts[k] = counts.get(k, 0) + 1
        return [_serialize(d, counts.get(d.key, 0)) for d in divisions]
    return [_serialize(d) for d in divisions if d.is_active]


@router.post("")
def upsert_division(
    body: DivisionDef,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    d = db.query(Division).filter_by(key=body.key).first()
    if d:
        d.label = body.label
        d.color = body.color
        d.is_active = body.is_active
    else:
        d = Division(key=body.key, label=body.label, color=body.color, is_active=body.is_active)
        db.add(d)
    db.commit()
    logger.info("Division '%s' saved by admin %s", body.key, admin.id)
    return _serialize(d)


@router.delete("/{key}")
def delete_division(
    key: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    d = db.query(Division).filter_by(key=key).first()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown division: '{key}'")

    members = db.query(Faculty).filter_by(division_key=key).count()
    rotations = [r for r in (_get(db, "rotations") or []) if r.get("division_key") == key]
    if (members or rotations) and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Division '{key}' has {members} members and {len(rotations)} rotations. "
                   f"Reassign them or pass force=true (members become unassigned).",
        )
    if members:
        db.query(Faculty).filter_by(division_key=key).update({"division_key": None})
    db.delete(d)
    db.commit()
    logger.info("Division '%s' deleted by admin %s (members unassigned: %d)", key, admin.id, members)
    return {"deleted": key, "members_unassigned": members}
