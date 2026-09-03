from pathlib import Path

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import AnonymousCode, BusinessType, CodeStatus, FileType, Region, Role, User
from app.security import hash_password, make_session, verify_password


def test_native_picker_progressive_enhancement_is_present():
    script = (Path(__file__).parents[1] / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "typeof input.showPicker === 'function'" in script
    assert "input.showPicker()" in script
    assert "input.focus()" in script


def test_contract_ui_create_and_detail(db):
    user = User(username="ui-admin", display_name="界面管理员", password_hash=hash_password("secret"), role=Role.admin, salesperson_code="UI")
    business = BusinessType(code="INT", name="中介服务")
    file_type = FileType(code="HT", name="正式合同")
    region = Region(chinese_name="香港", code="HK")
    db.add_all([user, business, file_type, region])
    db.flush()
    region.created_by = user.id
    db.add(AnonymousCode(code="ABCD", status=CodeStatus.unused))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        client.cookies.set("session", make_session(user.id))
        form = client.get("/app/contracts/new")
        assert form.status_code == 200
        assert "生成正式编号" in form.text
        assert "合同编号预览" in form.text
        assert 'type="month"' in form.text
        assert form.text.count('data-picker-label="选择日期"') == 3

        created = client.post("/app/contracts/new", data={
            "business_type_id": business.id, "file_type_id": file_type.id,
            "primary_owner_id": user.id, "signing_month": "2026-09", "region_id": region.id,
            "client_company_name": "铂晟客户有限公司", "project_short_name": "品牌项目",
            "contract_title": "品牌顾问服务合同", "amount": "120000", "notes": "测试记录", "confirmed": "yes",
        }, follow_redirects=False)
        assert created.status_code == 303
        assert created.headers["location"] == "/app/contracts/record/1"

        listing = client.get("/app/contracts")
        assert "铂晟客户有限公司" in listing.text
        assert "BS-INTHTUI2609ABCD-HK" in listing.text
        detail = client.get("/app/contracts/record/1")
        assert detail.status_code == 200
        assert "铂晟客户有限公司" in detail.text
        assert "BS-INTHTUI2609ABCD-HK" in detail.text
    finally:
        app.dependency_overrides.clear()


def test_contract_ui_requires_login(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/app/contracts", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
    finally:
        app.dependency_overrides.clear()


def test_account_password_change(db):
    user = User(username="account-user", display_name="账号用户", password_hash=hash_password("old-password"), role=Role.member, salesperson_code="AC")
    db.add(user); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app); client.cookies.set("session", make_session(user.id))
        assert client.get("/app/account").status_code == 200
        response = client.post("/app/account/password", data={"current_password":"old-password","new_password":"new-password","confirm_password":"new-password"}, follow_redirects=False)
        assert response.status_code == 303
        assert verify_password("new-password", user.password_hash)
    finally:
        app.dependency_overrides.clear()
