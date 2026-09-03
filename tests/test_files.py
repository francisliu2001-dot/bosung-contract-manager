from fastapi.testclient import TestClient
from app.config import get_settings
from app.database import get_db
from app.main import app
from app.models import BusinessType, ContractFile, FileType, Region, Role, User
from app.security import hash_password, make_session
from app.services import create_contract

def setup_contract(db):
    user=User(username="owner", display_name="负责人", password_hash=hash_password("password123"), role=Role.member, salesperson_code="TY")
    business=BusinessType(code="INT", name="中介"); file_type=FileType(code="HT", name="合同"); region=Region(chinese_name="中山", code="ZS")
    db.add_all([user,business,file_type,region]); db.commit()
    contract=create_contract(db,user,{"business_type_id":business.id,"file_type_id":file_type.id,"signing_month":"2609","region_id":region.id,
        "client_company_name":"文件测试公司","project_short_name":"项目","contract_title":"合同","amount":None,"notes":None})
    return user,contract

def test_protected_pdf_upload_and_download(db, tmp_path):
    user,contract=setup_contract(db); get_settings().upload_dir=str(tmp_path / "uploads")
    def override_db(): yield db
    app.dependency_overrides[get_db]=override_db
    try:
        client=TestClient(app); client.cookies.set("session",make_session(user.id))
        bad=client.post(f"/contracts/{contract.id}/files",data={"category":"original","version_name":"bad"},files={"upload":("bad.pdf",b"not pdf","application/pdf")})
        assert bad.status_code == 415
        created=client.post(f"/contracts/{contract.id}/files",data={"category":"original","version_name":"v1"},files={"upload":("contract.pdf",b"%PDF-1.4\n%%EOF","application/pdf")})
        assert created.status_code == 201
        file_id=created.json()["id"]
        downloaded=client.get(f"/files/{file_id}/download")
        assert downloaded.status_code == 200 and downloaded.content.startswith(b"%PDF-")
        assert db.get(ContractFile,file_id).storage_filename != "contract.pdf"
    finally: app.dependency_overrides.clear()
