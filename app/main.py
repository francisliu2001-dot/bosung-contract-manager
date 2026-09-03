from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import BusinessType, Contract, FileType, Region, Role, User
from .schemas import ContractIn, DictionaryIn, LoginIn, RegionIn, UserIn
from .security import hash_password, make_session, read_session, verify_password
from .services import create_contract, visible_contracts

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
