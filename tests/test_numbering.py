import re
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy.orm import sessionmaker
from app.models import AnonymousCode, BusinessType, CodeStatus, ContractCollaborator, FileType, Region, RequestStatus, Role, User
from app.numbering import ALPHABET, claim_code, format_number, generate_pool
from app.security import hash_password
from app.services import create_contract, renumber_contract, request_collaboration, review_collaboration, visible_contracts

def fixtures(db):
    user=User(username="member", display_name="成员", password_hash=hash_password("password123"), role=Role.member, salesperson_code="TY")
    admin=User(username="admin", display_name="管理员", password_hash=hash_password("password123"), role=Role.admin, salesperson_code="FL")
    business=BusinessType(code="INT", name="中介/介绍服务"); file_type=FileType(code="HT", name="正式合同"); region=Region(chinese_name="中山", code="ZS")
    db.add_all([user,admin,business,file_type,region]); db.commit(); return user,admin,business,file_type,region

def test_pool_excludes_ambiguous_and_is_unique(db):
    generate_pool(db, 100); db.commit(); values=[x.code for x in db.query(AnonymousCode).all()]
    assert len(values) == len(set(values)) == 100
    assert all(len(x)==4 and set(x) <= set(ALPHABET) and not set(x) & set("IO01") for x in values)

def test_claim_refills_and_allocation_order(db):
    first=claim_code(db); db.commit(); second=claim_code(db); db.commit()
    assert first.status == CodeStatus.used and (first.allocation_order, second.allocation_order) == (1,2)
    assert db.query(AnonymousCode).filter_by(status=CodeStatus.unused).count() >= 48

def test_concurrent_claims_do_not_duplicate(db):
    generate_pool(db, 20); db.commit()
    factory = sessionmaker(db.bind, expire_on_commit=False)
    def allocate():
        with factory() as session:
            code = claim_code(session); session.commit(); return code.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: allocate(), range(2)))
    assert len(set(codes)) == 2

def test_number_format():
    assert format_number("INT","HT","TY","2609","QKWN","ZS") == "BS-INTHTTY2609QKWN-ZS"
    with pytest.raises(ValueError): format_number("INT","HT","TY","202609","QKWN","ZS")

def test_member_owner_and_admin_renumber(db):
    user,admin,business,file_type,region=fixtures(db)
    data={"business_type_id":business.id,"file_type_id":file_type.id,"primary_owner_id":admin.id,"signing_month":"2609","region_id":region.id,"client_company_name":"测试公司","project_short_name":"项目","contract_title":"合同","amount":None,"notes":None}
    contract=create_contract(db,user,data)
    assert contract.primary_owner_id == user.id
    assert re.fullmatch(r"BS-INTHTTY2609[A-HJ-NP-Z2-9]{4}-ZS", contract.current_contract_number)
    old=contract.current_contract_number; old_code=db.get(AnonymousCode,contract.anonymous_code_id)
    renumber_contract(db,admin,contract,{"primary_owner_id":admin.id},"更换负责人")
    assert contract.current_contract_number != old and old_code.status == CodeStatus.void

def test_visibility_and_collaboration_approval(db):
    owner,admin,business,file_type,region=fixtures(db)
    colleague=User(username="helper", display_name="协作者", password_hash=hash_password("password123"), role=Role.member, salesperson_code="HL")
    outsider=User(username="outside", display_name="无关成员", password_hash=hash_password("password123"), role=Role.member, salesperson_code="OS")
    db.add_all([colleague, outsider]); db.commit()
    data={"business_type_id":business.id,"file_type_id":file_type.id,"signing_month":"2609","region_id":region.id,"client_company_name":"权限测试公司","project_short_name":"项目","contract_title":"合同","amount":None,"notes":None}
    contract=create_contract(db,owner,data)
    assert db.scalars(visible_contracts(outsider)).all() == []
    request=request_collaboration(db,owner,contract,"add",colleague.id)
    review_collaboration(db,admin,request,True)
    assert request.status == RequestStatus.approved
    assert db.get(ContractCollaborator,(contract.id,colleague.id))
    assert db.scalars(visible_contracts(colleague)).one().id == contract.id
