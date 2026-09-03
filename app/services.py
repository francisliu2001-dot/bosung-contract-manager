import json
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from .models import (AnonymousCode, AuditLog, BusinessType, ClientCompany, CodeStatus,
                     Contract, ContractCollaborator, ContractNumberHistory, FileType, Region, Role, User)
from .numbering import claim_code, format_number

def visible_contracts(user: User):
    query = select(Contract).where(Contract.is_deleted.is_(False))
    if user.role != Role.admin:
        query = query.where(or_(Contract.primary_owner_id == user.id, Contract.id.in_(select(ContractCollaborator.contract_id).where(ContractCollaborator.user_id == user.id))))
    return query

def create_contract(db: Session, actor: User, data: dict) -> Contract:
    owner_id = data.get("primary_owner_id") if actor.role == Role.admin else actor.id
    owner = db.get(User, owner_id)
    business, file_type, region = db.get(BusinessType, data["business_type_id"]), db.get(FileType, data["file_type_id"]), db.get(Region, data["region_id"])
    if not all((owner, business, file_type, region)): raise ValueError("invalid numbering dictionary reference")
    company_name = data.pop("client_company_name").strip()
    company = db.scalar(select(ClientCompany).where(ClientCompany.full_name == company_name))
    if not company:
        company = ClientCompany(full_name=company_name, created_by=actor.id); db.add(company); db.flush()
    code = claim_code(db)
    number = format_number(business.code, file_type.code, owner.salesperson_code, data["signing_month"], code.code, region.code)
    contract = Contract(current_contract_number=number, primary_owner_id=owner.id, anonymous_code_id=code.id,
                        client_company_id=company.id, created_by=actor.id, **{k:v for k,v in data.items() if k != "primary_owner_id"})
    db.add(contract); db.flush(); code.contract_id = contract.id
    db.add(AuditLog(actor_id=actor.id, contract_id=contract.id, action="contract_number_generated", entity_type="contract", entity_id=contract.id, after_json=json.dumps({"number": number})))
    db.commit(); return contract

def renumber_contract(db: Session, actor: User, contract: Contract, changes: dict, reason: str) -> Contract:
    if actor.role != Role.admin: raise PermissionError("admin required")
    old_number, old_code_id = contract.current_contract_number, contract.anonymous_code_id
    old_code = db.get(AnonymousCode, old_code_id); old_code.status = CodeStatus.void
    for key, value in changes.items(): setattr(contract, key, value)
    business, file_type, owner, region = db.get(BusinessType, contract.business_type_id), db.get(FileType, contract.file_type_id), db.get(User, contract.primary_owner_id), db.get(Region, contract.region_id)
    new_code = claim_code(db)
    contract.anonymous_code_id = new_code.id
    contract.current_contract_number = format_number(business.code, file_type.code, owner.salesperson_code, contract.signing_month, new_code.code, region.code)
    db.flush(); new_code.contract_id = contract.id
    db.add(ContractNumberHistory(contract_id=contract.id, old_number=old_number, new_number=contract.current_contract_number,
        old_anonymous_code_id=old_code_id, new_anonymous_code_id=new_code.id, changed_by=actor.id, reason=reason))
    db.commit(); return contract

