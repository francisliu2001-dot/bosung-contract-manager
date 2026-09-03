from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from datetime import datetime, timezone
from fastapi import status
from .models import BusinessType, CollaborationRequest, Contract, ContractStatus, FileType, Region, Role, User
from .schemas import (CollaborationRequestIn, CollaborationReviewIn, ContractIn, ContractUpdate,
                      CoreContractUpdate, DictionaryIn, LoginIn, RegionIn, UserIn)
from .security import hash_password, make_session, read_session, verify_password
from .services import (audit, can_access_contract, create_contract, renumber_contract,
                       request_collaboration, review_collaboration, set_collaborator, visible_contracts)

app = FastAPI(title="Bosung Contract Manager", version="0.1.0")

def current_user(session: str | None = Cookie(None), db: Session = Depends(get_db)) -> User:
    user = db.get(User, read_session(session)) if session else None
    if not user or not user.is_active: raise HTTPException(401, "authentication required")
    return user

def admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.admin: raise HTTPException(403, "admin required")
    return user

@app.get("/health")
def health(): return {"status": "ok"}

@app.post("/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash): raise HTTPException(401, "invalid credentials")
    response.set_cookie("session", make_session(user.id), httponly=True, secure=False, samesite="lax", max_age=43200)
    return {"id": user.id, "display_name": user.display_name, "role": user.role}

@app.post("/auth/logout")
def logout(response: Response): response.delete_cookie("session"); return {"ok": True}

@app.post("/admin/users", dependencies=[Depends(admin)])
def add_user(payload: UserIn, db: Session = Depends(get_db)):
    user = User(**payload.model_dump(exclude={"password"}), password_hash=hash_password(payload.password)); db.add(user); db.commit(); return {"id": user.id}

@app.post("/admin/business-types", dependencies=[Depends(admin)])
def add_business(payload: DictionaryIn, db: Session = Depends(get_db)):
    row = BusinessType(code=payload.code.upper(), name=payload.name); db.add(row); db.commit(); return {"id": row.id}

@app.post("/admin/file-types", dependencies=[Depends(admin)])
def add_file_type(payload: DictionaryIn, db: Session = Depends(get_db)):
    row = FileType(code=payload.code.upper(), name=payload.name); db.add(row); db.commit(); return {"id": row.id}

@app.post("/regions")
def add_region(payload: RegionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = Region(chinese_name=payload.chinese_name, code=payload.code.upper(), created_by=user.id); db.add(row); db.commit(); return {"id": row.id}

@app.get("/contracts")
def contracts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(visible_contracts(user).order_by(Contract.id.desc())).all()
    return [{"id": c.id, "number": c.current_contract_number, "title": c.contract_title} for c in rows]

@app.post("/contracts", status_code=201)
def add_contract(payload: ContractIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try: row = create_contract(db, user, payload.model_dump())
    except ValueError as exc: db.rollback(); raise HTTPException(422, str(exc))
    return {"id": row.id, "contract_number": row.current_contract_number}

def contract_or_404(contract_id: int, user: User, db: Session, include_deleted: bool = False) -> Contract:
    row = db.get(Contract, contract_id)
    if not row or not can_access_contract(db, user, row, include_deleted): raise HTTPException(404, "contract not found")
    return row

@app.get("/contracts/{contract_id}")
def contract_detail(contract_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = contract_or_404(contract_id, user, db, user.role == Role.admin)
    return {"id": row.id, "number": row.current_contract_number, "title": row.contract_title,
            "project_short_name": row.project_short_name, "amount": row.amount, "status": row.status,
            "notes": row.notes, "primary_owner_id": row.primary_owner_id, "is_deleted": row.is_deleted}

@app.patch("/contracts/{contract_id}")
def update_contract(contract_id: int, payload: ContractUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = contract_or_404(contract_id, user, db)
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes:
        try: changes["status"] = ContractStatus(changes["status"])
        except ValueError: raise HTTPException(422, "invalid contract status")
    before = {key: getattr(row, key) for key in changes}
    for key, value in changes.items(): setattr(row, key, value)
    audit(db, user, row, "contract_updated", before, changes); db.commit()
    return {"ok": True}

@app.patch("/admin/contracts/{contract_id}/core")
def update_contract_core(contract_id: int, payload: CoreContractUpdate, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = contract_or_404(contract_id, user, db, True)
    changes = payload.model_dump(exclude={"reason"}, exclude_none=True)
    if not changes: raise HTTPException(422, "at least one core field is required")
    try: renumber_contract(db, user, row, changes, payload.reason)
    except (ValueError, RuntimeError) as exc: db.rollback(); raise HTTPException(422, str(exc))
    return {"contract_number": row.current_contract_number}

@app.delete("/admin/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(contract_id: int, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = contract_or_404(contract_id, user, db, True)
    if row.is_deleted: raise HTTPException(409, "contract already deleted")
    row.is_deleted, row.deleted_by = True, user.id
    row.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    audit(db, user, row, "contract_deleted"); db.commit()

@app.post("/admin/contracts/{contract_id}/restore")
def restore_contract(contract_id: int, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = contract_or_404(contract_id, user, db, True)
    if not row.is_deleted: raise HTTPException(409, "contract is not deleted")
    row.is_deleted, row.deleted_by, row.deleted_at = False, None, None
    audit(db, user, row, "contract_restored"); db.commit(); return {"ok": True}

@app.post("/contracts/{contract_id}/collaboration-requests", status_code=201)
def add_collaboration_request(contract_id: int, payload: CollaborationRequestIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = contract_or_404(contract_id, user, db)
    try: request = request_collaboration(db, user, row, payload.action, payload.target_user_id)
    except (PermissionError, ValueError) as exc: db.rollback(); raise HTTPException(403 if isinstance(exc, PermissionError) else 422, str(exc))
    return {"id": request.id, "status": request.status}

@app.post("/admin/collaboration-requests/{request_id}/review")
def review_request(request_id: int, payload: CollaborationReviewIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    request = db.get(CollaborationRequest, request_id)
    if not request: raise HTTPException(404, "request not found")
    try: review_collaboration(db, user, request, payload.approve)
    except ValueError as exc: db.rollback(); raise HTTPException(409, str(exc))
    return {"status": request.status}

@app.post("/admin/contracts/{contract_id}/collaborators")
def change_collaborator(contract_id: int, payload: CollaborationRequestIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = contract_or_404(contract_id, user, db, True)
    try: set_collaborator(db, user, row, payload.action, payload.target_user_id)
    except ValueError as exc: db.rollback(); raise HTTPException(422, str(exc))
    return {"ok": True}
