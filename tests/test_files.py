from fastapi.testclient import TestClient
from app.config import get_settings
from app.database import get_db
from app.main import app
from app.models import BusinessType, ContractCollaborator, ContractFile, FileType, Region, Role, User
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
        created=client.post(f"/contracts/{contract.id}/files",data={"category":"original","version_name":"v1","notes":"客户初稿"},files={"upload":("contract.pdf",b"%PDF-1.4\n%%EOF","application/pdf")})
        assert created.status_code == 201
        duplicate=client.post(f"/contracts/{contract.id}/files",data={"category":"original","version_name":"v1"},files={"upload":("other.pdf",b"%PDF-1.4\n%%EOF","application/pdf")})
        assert duplicate.status_code == 409
        file_id=created.json()["id"]
        downloaded=client.get(f"/files/{file_id}/download")
        assert downloaded.status_code == 200 and downloaded.content.startswith(b"%PDF-")
        assert db.get(ContractFile,file_id).storage_filename != "contract.pdf"
        assert db.get(ContractFile,file_id).notes == "客户初稿"
    finally: app.dependency_overrides.clear()

def test_pdf_permissions_soft_delete_and_admin_restore(db, tmp_path):
    owner,contract=setup_contract(db); get_settings().upload_dir=str(tmp_path / "uploads")
    collaborator=User(username="collab",display_name="协作人",password_hash=hash_password("password123"),role=Role.member,salesperson_code="CO")
    outsider=User(username="outsider-file",display_name="外部成员",password_hash=hash_password("password123"),role=Role.member,salesperson_code="OS")
    admin=User(username="admin-file",display_name="管理员",password_hash=hash_password("password123"),role=Role.admin,salesperson_code="AD")
    db.add_all([collaborator,outsider,admin]); db.flush(); db.add(ContractCollaborator(contract_id=contract.id,user_id=collaborator.id,added_by=admin.id)); db.commit()
    app.dependency_overrides[get_db]=lambda: db
    try:
        owner_client=TestClient(app); owner_client.cookies.set("session",make_session(owner.id))
        created=owner_client.post(f"/contracts/{contract.id}/files",data={"category":"signed","version_name":"盖章版"},files={"upload":("signed.pdf",b"%PDF-1.4\n%%EOF","application/pdf")})
        file_id=created.json()["id"]
        outsider_client=TestClient(app); outsider_client.cookies.set("session",make_session(outsider.id))
        assert outsider_client.get(f"/files/{file_id}/download").status_code == 404
        collaborator_client=TestClient(app); collaborator_client.cookies.set("session",make_session(collaborator.id))
        assert collaborator_client.delete(f"/files/{file_id}").status_code == 403
        assert owner_client.delete(f"/files/{file_id}").status_code == 204
        assert db.get(ContractFile,file_id).is_deleted is True
        assert owner_client.get(f"/files/{file_id}/download").status_code == 404
        admin_client=TestClient(app); admin_client.cookies.set("session",make_session(admin.id))
        assert admin_client.post(f"/admin/files/{file_id}/restore").status_code == 200
        assert db.get(ContractFile,file_id).is_deleted is False
        assert admin_client.delete(f"/admin/files/{file_id}/purge").status_code == 409
        assert owner_client.delete(f"/files/{file_id}").status_code == 204
        assert admin_client.delete(f"/admin/files/{file_id}/purge").status_code == 204
        assert db.get(ContractFile,file_id) is None
    finally: app.dependency_overrides.clear()
