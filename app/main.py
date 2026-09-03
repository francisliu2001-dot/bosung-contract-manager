import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from .database import SessionLocal, get_db
from fastapi import status
from .config import get_settings
from .models import (AnonymousCode, BusinessType, ClientCompany, CodeStatus, CollaborationRequest, Contract,
                     ContractCollaborator, ContractFile, ContractNumberHistory, ContractStatus,
                     FileCategory, FileType, Region, ReminderRead, Role, User)
from .schemas import (CollaborationRequestIn, CollaborationReviewIn, ContractIn, ContractUpdate,
                      CoreContractUpdate, DictionaryIn, LoginIn, RegionIn, UserIn)
from .security import hash_password, make_session, read_session, verify_password
from .services import (anonymous_code_stats, audit, can_access_contract, complete_expired_contracts,
                       create_contract, due_reminders, get_or_create_region, month_to_yymm,
                       parse_amount, renumber_contract, request_collaboration, review_collaboration,
                       set_collaborator, visible_contracts, yymm_to_month)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    async def maintenance_loop():
        while True:
            with SessionLocal() as maintenance_db:
                complete_expired_contracts(maintenance_db)
            await asyncio.sleep(get_settings().maintenance_interval_seconds)
    with SessionLocal() as startup_db:
        complete_expired_contracts(startup_db)
    task = asyncio.create_task(maintenance_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

production = get_settings().app_env.lower() == "production"
app = FastAPI(title="Bosung Contract Manager", version="0.2.0", lifespan=lifespan,
              docs_url=None if production else "/docs", redoc_url=None if production else "/redoc")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["production"] = production

def current_user(session: str | None = Cookie(None), db: Session = Depends(get_db)) -> User:
    user = db.get(User, read_session(session)) if session else None
    if not user or not user.is_active: raise HTTPException(401, "authentication required")
    return user

def admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.admin: raise HTTPException(403, "admin required")
    return user

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login", include_in_schema=False)
def login_form(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "账号或密码不正确"}, status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("session", make_session(user.id), httponly=True, secure=get_settings().app_env == "production", samesite="lax", max_age=43200)
    return response

@app.get("/", include_in_schema=False)
def dashboard(request: Request, session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = db.get(User, read_session(session)) if session else None
    if not user or not user.is_active: return RedirectResponse("/login", status_code=303)
    complete_expired_contracts(db)
    rows = db.scalars(visible_contracts(user).order_by(Contract.updated_at.desc()).limit(8)).all()
    all_visible = db.scalars(visible_contracts(user)).all()
    active_states = {ContractStatus.signed, ContractStatus.active}
    stats = {"total": len(all_visible), "active": sum(c.status in active_states for c in all_visible),
             "void": sum(c.status == ContractStatus.void for c in all_visible)}
    now = datetime.now(timezone.utc).date()
    reminders = due_reminders(db, user, now)[:6]
    status_labels = {"draft":"草稿","pending":"待签署","signed":"已签署","active":"履约中","completed":"已完成","terminated":"已终止","void":"已作废"}
    code_stats = anonymous_code_stats(db) if user.role == Role.admin else None
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user, "contracts": rows, "stats": stats, "reminders": reminders, "today": now, "status_labels": status_labels, "code_stats": code_stats})

def html_user(session: str | None, db: Session):
    user = db.get(User, read_session(session)) if session else None
    return user if user and user.is_active else None

@app.get("/app/contracts", include_in_schema=False)
def contracts_page(request: Request, q: str = "", business_type_id: int | None = None, file_type_id: int | None = None,
                   primary_owner_id: int | None = None, region_id: int | None = None, contract_status: str = "",
                   signing_month: str = "", session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    query = visible_contracts(user)
    if q.strip():
        client_ids = select(ClientCompany.id).where(ClientCompany.full_name.contains(q.strip()))
        query = query.where(or_(Contract.current_contract_number.contains(q.strip()), Contract.project_short_name.contains(q.strip()), Contract.client_company_id.in_(client_ids)))
    if business_type_id: query = query.where(Contract.business_type_id == business_type_id)
    if file_type_id: query = query.where(Contract.file_type_id == file_type_id)
    if primary_owner_id and user.role == Role.admin: query = query.where(Contract.primary_owner_id == primary_owner_id)
    if region_id: query = query.where(Contract.region_id == region_id)
    if contract_status:
        try: query = query.where(Contract.status == ContractStatus(contract_status))
        except ValueError: raise HTTPException(422, "invalid contract status")
    if signing_month:
        try: query = query.where(Contract.signing_month == month_to_yymm(signing_month))
        except ValueError: raise HTTPException(422, "invalid signing month")
    rows = db.scalars(query.order_by(Contract.updated_at.desc())).all()
    labels = {"draft":"草稿","pending":"待签署","signed":"已签署","active":"履约中","completed":"已完成","terminated":"已终止","void":"已作废"}
    company_map = {row.id: row.full_name for row in db.scalars(select(ClientCompany)).all()}
    owner_map = {row.id: row.display_name for row in db.scalars(select(User)).all()}
    business_map = {row.id: row.name for row in db.scalars(select(BusinessType)).all()}
    context = {"user":user,"contracts":rows,"q":q,"status_labels":labels,"company_map":company_map,"owner_map":owner_map,"business_map":business_map,
               "business_types":db.scalars(select(BusinessType).where(BusinessType.is_active.is_(True)).order_by(BusinessType.code)).all(),
               "file_types":db.scalars(select(FileType).where(FileType.is_active.is_(True)).order_by(FileType.code)).all(),
               "owners":db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)).all(),
               "regions":db.scalars(select(Region).order_by(Region.code == "QT", Region.chinese_name)).all(),
               "filters":{"business_type_id":business_type_id,"file_type_id":file_type_id,"primary_owner_id":primary_owner_id,"region_id":region_id,"contract_status":contract_status,"signing_month":signing_month}}
    return templates.TemplateResponse(request=request, name="contracts.html", context=context)

@app.get("/app/contracts/record/{contract_id}", include_in_schema=False)
def contract_detail_page(contract_id: int, request: Request, session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    contract = db.get(Contract, contract_id)
    if not contract or not can_access_contract(db, user, contract, user.role == Role.admin):
        raise HTTPException(404, "contract not found")
    all_files = db.scalars(select(ContractFile).where(ContractFile.contract_id == contract.id).order_by(ContractFile.uploaded_at.desc())).all()
    files = [item for item in all_files if not item.is_deleted]
    deleted_files = [item for item in all_files if item.is_deleted] if user.role == Role.admin else []
    collaborator_links = db.scalars(select(ContractCollaborator).where(ContractCollaborator.contract_id == contract.id)).all()
    collaborator_ids = [link.user_id for link in collaborator_links]
    collaborators = db.scalars(select(User).where(User.id.in_(collaborator_ids)).order_by(User.display_name)).all() if collaborator_ids else []
    histories = db.scalars(select(ContractNumberHistory).where(ContractNumberHistory.contract_id == contract.id).order_by(ContractNumberHistory.changed_at.desc())).all() if user.role == Role.admin else []
    related_users = {row.id: row for row in db.scalars(select(User)).all()}
    context = {"user": user, "contract": contract, "owner": db.get(User, contract.primary_owner_id),
               "company": db.get(ClientCompany, contract.client_company_id), "files": files, "deleted_files": deleted_files,
               "collaborators": collaborators, "histories": histories, "user_map": related_users,
               "business_type": db.get(BusinessType, contract.business_type_id), "file_type": db.get(FileType, contract.file_type_id),
               "region": db.get(Region, contract.region_id), "signing_month_display": yymm_to_month(contract.signing_month),
               "status_labels": {"draft":"草稿","pending":"待签署","signed":"已签署","active":"履约中","completed":"已完成","terminated":"已终止","void":"已作废"},
               "category_labels": {"original": "原合同文件", "signed": "已签署合同文件"}}
    return templates.TemplateResponse(request=request, name="contract_detail.html", context=context)

def new_contract_context(db: Session, user: User, error=None, values=None):
    return {"user":user,"business_types":db.scalars(select(BusinessType).where(BusinessType.is_active.is_(True)).order_by(BusinessType.code)).all(),
            "file_types":db.scalars(select(FileType).where(FileType.is_active.is_(True)).order_by(FileType.code)).all(),
            "regions":db.scalars(select(Region).order_by(Region.code == "QT", Region.chinese_name)).all(),
            "owners":db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)).all(),
            "clients":db.scalars(select(ClientCompany).order_by(ClientCompany.full_name)).all(),"error":error,"values":values or {}}

@app.get("/app/contracts/new", include_in_schema=False)
def new_contract_page(request: Request, session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request,name="contract_new.html",context=new_contract_context(db,user))

@app.post("/app/contracts/new", include_in_schema=False)
def new_contract_submit(request: Request, business_type_id: int = Form(...), file_type_id: int = Form(...), primary_owner_id: int | None = Form(None),
                        signing_month: str = Form(...), region_id: int = Form(...), custom_region: str = Form(""), client_company_name: str = Form(...),
                        project_short_name: str = Form(...), contract_title: str = Form(...), amount: str = Form(""), notes: str = Form(""),
                        signing_date: str = Form(""), service_start_date: str = Form(""), service_end_date: str = Form(""), confirmed: str = Form(""),
                        session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    values = {"business_type_id":business_type_id,"file_type_id":file_type_id,"primary_owner_id":primary_owner_id,"signing_month":signing_month,
              "region_id":region_id,"custom_region":custom_region,"client_company_name":client_company_name,"project_short_name":project_short_name,
              "contract_title":contract_title,"amount":amount,"notes":notes,"signing_date":signing_date,"service_start_date":service_start_date,"service_end_date":service_end_date}
    try:
        if confirmed != "yes": raise ValueError("请先预览合同编号并完成二次确认")
        selected_region = db.get(Region, region_id)
        if not selected_region: raise ValueError("请选择有效地区")
        if selected_region.code == "QT": selected_region = get_or_create_region(db, user, custom_region)
        data={"business_type_id":business_type_id,"file_type_id":file_type_id,"primary_owner_id":primary_owner_id,"signing_month":month_to_yymm(signing_month),
              "region_id":selected_region.id,"client_company_name":client_company_name,"project_short_name":project_short_name,"contract_title":contract_title,
              "amount":parse_amount(amount),"notes":notes.strip() or None,
              "signing_date":date.fromisoformat(signing_date) if signing_date else None,
              "service_start_date":date.fromisoformat(service_start_date) if service_start_date else None,
              "service_end_date":date.fromisoformat(service_end_date) if service_end_date else None}
        if data["service_start_date"] and data["service_end_date"] and data["service_end_date"] < data["service_start_date"]:
            raise ValueError("服务结束日期不能早于服务开始日期")
        contract=create_contract(db,user,data)
    except (ValueError,RuntimeError) as exc:
        db.rollback()
        return templates.TemplateResponse(request=request,name="contract_new.html",context=new_contract_context(db,user,str(exc),values),status_code=422)
    return RedirectResponse(f"/app/contracts/record/{contract.id}",status_code=303)

@app.post("/logout", include_in_schema=False)
def logout_page():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response

@app.get("/app/account", include_in_schema=False)
def account_page(request: Request, changed: int = 0, session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request, name="account.html", context={"user": user, "changed": bool(changed), "error": None})

@app.post("/app/account/password", include_in_schema=False)
def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...),
                    confirm_password: str = Form(...), session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    error = None
    if not verify_password(current_password, user.password_hash): error = "当前密码不正确"
    elif len(new_password) < 8: error = "新密码至少需要 8 个字符"
    elif new_password != confirm_password: error = "两次输入的新密码不一致"
    if error: return templates.TemplateResponse(request=request, name="account.html", context={"user":user,"changed":False,"error":error}, status_code=422)
    user.password_hash = hash_password(new_password); db.commit()
    return RedirectResponse("/app/account?changed=1", status_code=303)

@app.post("/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash): raise HTTPException(401, "invalid credentials")
    response.set_cookie("session", make_session(user.id), httponly=True, secure=production, samesite="lax", max_age=43200)
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
    try: row = get_or_create_region(db, user, f"{payload.chinese_name} {payload.code}")
    except ValueError as exc: db.rollback(); raise HTTPException(422, str(exc))
    db.commit(); return {"id": row.id}

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

@app.post("/contracts/{contract_id}/files", status_code=201)
async def upload_contract_file(contract_id: int, category: str = Form(...), version_name: str = Form(...),
                               upload: UploadFile = File(...), notes: str = Form(""), user: User = Depends(current_user), db: Session = Depends(get_db)):
    contract = contract_or_404(contract_id, user, db)
    try: file_category = FileCategory(category)
    except ValueError: raise HTTPException(422, "category must be original or signed")
    if Path(upload.filename or "").suffix.lower() != ".pdf" or upload.content_type != "application/pdf": raise HTTPException(415, "PDF files only")
    content = await upload.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    if len(content) > get_settings().max_upload_mb * 1024 * 1024: raise HTTPException(413, "file too large")
    if not content.startswith(b"%PDF-"): raise HTTPException(415, "invalid PDF header")
    version_name = version_name.strip()
    if not version_name: raise HTTPException(422, "version name is required")
    if db.scalar(select(ContractFile).where(ContractFile.contract_id == contract.id, ContractFile.category == file_category, ContractFile.version_name == version_name)):
        raise HTTPException(409, "version name already exists for this category")
    base = Path(get_settings().upload_dir).resolve() / str(contract.id)
    base.mkdir(parents=True, exist_ok=True)
    storage_name = f"{uuid4().hex}.pdf"; path = base / storage_name; path.write_bytes(content)
    row = ContractFile(contract_id=contract.id, category=file_category, version_name=version_name.strip(),
        original_filename=Path(upload.filename).name, storage_filename=storage_name, storage_path=str(path),
        mime_type="application/pdf", size=len(content), notes=notes.strip() or None, uploaded_by=user.id)
    db.add(row); db.flush(); audit(db, user, contract, "pdf_uploaded", after={"file_id": row.id, "version": version_name}); db.commit()
    return {"id": row.id, "version_name": row.version_name}

def contract_file_or_404(file_id: int, user: User, db: Session, include_deleted: bool = False):
    row = db.get(ContractFile, file_id)
    if not row: raise HTTPException(404, "file not found")
    contract = db.get(Contract, row.contract_id)
    if not can_access_contract(db, user, contract, include_deleted) or (row.is_deleted and not (include_deleted and user.role == Role.admin)):
        raise HTTPException(404, "file not found")
    return row, contract

@app.get("/files/{file_id}/download")
def download_contract_file(file_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row, _ = contract_file_or_404(file_id, user, db)
    path = Path(row.storage_path).resolve()
    upload_root = Path(get_settings().upload_dir).resolve()
    if upload_root not in path.parents or not path.is_file(): raise HTTPException(404, "stored file not found")
    return FileResponse(path, media_type="application/pdf", filename=row.original_filename)

@app.delete("/files/{file_id}", status_code=204)
def delete_contract_file(file_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row, contract = contract_file_or_404(file_id, user, db)
    if user.role != Role.admin and row.uploaded_by != user.id: raise HTTPException(403, "only the uploader may delete this file")
    row.is_deleted, row.deleted_by = True, user.id
    row.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    audit(db, user, contract, "pdf_deleted", after={"file_id": row.id}); db.commit()

@app.post("/admin/files/{file_id}/restore")
def restore_contract_file(file_id: int, user: User = Depends(admin), db: Session = Depends(get_db)):
    row, contract = contract_file_or_404(file_id, user, db, True)
    if not row.is_deleted: raise HTTPException(409, "file is not deleted")
    row.is_deleted, row.deleted_by, row.deleted_at = False, None, None
    audit(db, user, contract, "pdf_restored", after={"file_id": row.id}); db.commit(); return {"ok": True}

@app.delete("/admin/files/{file_id}/purge", status_code=204)
def purge_contract_file(file_id: int, user: User = Depends(admin), db: Session = Depends(get_db)):
    row, contract = contract_file_or_404(file_id, user, db, True)
    if not row.is_deleted: raise HTTPException(409, "only deleted files may be permanently deleted")
    path = Path(row.storage_path).resolve(); upload_root = Path(get_settings().upload_dir).resolve()
    if upload_root not in path.parents: raise HTTPException(409, "unsafe storage path")
    audit(db, user, contract, "pdf_purged", after={"file_id": row.id, "original_filename": row.original_filename}); db.delete(row); db.commit()
    if path.is_file(): path.unlink()

@app.post("/app/contracts/{contract_id}/files", include_in_schema=False)
async def upload_contract_file_page(contract_id: int, category: str = Form(...), version_name: str = Form(...),
                                    notes: str = Form(""), upload: UploadFile = File(...),
                                    session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    await upload_contract_file(contract_id, category, version_name, upload, notes, user, db)
    return RedirectResponse(f"/app/contracts/record/{contract_id}#contract-files", status_code=303)

@app.post("/app/files/{file_id}/delete", include_in_schema=False)
def delete_contract_file_page(file_id: int, session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    row = db.get(ContractFile, file_id)
    if not row: raise HTTPException(404, "file not found")
    contract_id = row.contract_id
    delete_contract_file(file_id, user, db)
    return RedirectResponse(f"/app/contracts/record/{contract_id}#contract-files", status_code=303)

@app.post("/app/admin/files/{file_id}/restore", include_in_schema=False)
def restore_contract_file_page(file_id: int, session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user or user.role != Role.admin: raise HTTPException(404, "file not found")
    row = db.get(ContractFile, file_id)
    if not row: raise HTTPException(404, "file not found")
    contract_id = row.contract_id
    restore_contract_file(file_id, user, db)
    return RedirectResponse(f"/app/contracts/record/{contract_id}#contract-files", status_code=303)

@app.post("/app/admin/files/{file_id}/purge", include_in_schema=False)
def purge_contract_file_page(file_id: int, session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user or user.role != Role.admin: raise HTTPException(404, "file not found")
    row = db.get(ContractFile, file_id)
    if not row: raise HTTPException(404, "file not found")
    contract_id = row.contract_id
    purge_contract_file(file_id, user, db)
    return RedirectResponse(f"/app/contracts/record/{contract_id}#contract-files", status_code=303)

@app.post("/app/reminders/{contract_id}/{threshold_days}/read", include_in_schema=False)
def mark_reminder_read(contract_id: int, threshold_days: int, session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = html_user(session, db)
    if not user: return RedirectResponse("/login", status_code=303)
    contract = contract_or_404(contract_id, user, db)
    if threshold_days not in {7, 15, 30}: raise HTTPException(422, "invalid reminder threshold")
    if not db.scalar(select(ReminderRead).where(ReminderRead.contract_id == contract.id, ReminderRead.user_id == user.id, ReminderRead.threshold_days == threshold_days)):
        db.add(ReminderRead(contract_id=contract.id, user_id=user.id, threshold_days=threshold_days)); db.commit()
    return RedirectResponse("/#reminders", status_code=303)

@app.post("/contracts/{contract_id}/abandon")
def abandon_contract(contract_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    contract = contract_or_404(contract_id, user, db)
    if user.role != Role.admin and contract.primary_owner_id != user.id: raise HTTPException(403, "primary owner required")
    if contract.status != ContractStatus.draft: raise HTTPException(409, "only draft contracts may be abandoned")
    code = db.get(AnonymousCode, contract.anonymous_code_id)
    code.status = CodeStatus.void
    contract.status = ContractStatus.void
    audit(db, user, contract, "contract_number_abandoned", after={"number": contract.current_contract_number, "anonymous_code": code.code})
    db.commit(); return {"ok": True}
