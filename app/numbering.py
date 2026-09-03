import secrets
from datetime import datetime, timezone
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from .models import AnonymousCode, CodeStatus, Contract

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def generate_pool(db: Session, count: int = 50) -> None:
    existing = set(db.scalars(select(AnonymousCode.code)).all())
    while count:
        code = "".join(secrets.choice(ALPHABET) for _ in range(4))
        if code not in existing:
            db.add(AnonymousCode(code=code, status=CodeStatus.unused)); existing.add(code); count -= 1
    db.flush()

def claim_code(db: Session) -> AnonymousCode:
    available = db.scalar(select(func.count()).select_from(AnonymousCode).where(AnonymousCode.status == CodeStatus.unused)) or 0
    if available <= 10: generate_pool(db, 50)
    max_order = db.scalar(select(func.max(AnonymousCode.allocation_order))) or 0
    candidate_id = db.scalar(select(AnonymousCode.id).where(AnonymousCode.status == CodeStatus.unused).order_by(AnonymousCode.id).limit(1))
    if candidate_id is None: raise RuntimeError("anonymous code pool exhausted")
    claimed_id = db.scalar(update(AnonymousCode).where(AnonymousCode.id == candidate_id, AnonymousCode.status == CodeStatus.unused)
        .values(status=CodeStatus.used, allocation_order=max_order + 1, allocated_at=datetime.now(timezone.utc).replace(tzinfo=None)).returning(AnonymousCode.id))
    if claimed_id is None: raise RuntimeError("anonymous code allocation conflict; retry transaction")
    db.flush(); return db.get(AnonymousCode, claimed_id)

def format_number(business: str, file_type: str, owner: str, month: str, anonymous: str, region: str) -> str:
    if len(month) != 4 or not month.isdigit(): raise ValueError("signing_month must be YYMM")
    return f"BS-{business}{file_type}{owner}{month}{anonymous}-{region}".upper()
