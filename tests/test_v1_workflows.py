from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import get_db
from app.main import app
from app.models import (AnonymousCode, BusinessType, ClientCompany, CodeStatus, Contract,
                        ContractNumberHistory, ContractStatus, FileType, Region, ReminderRead,
                        Role, User)
from app.security import hash_password, make_session
from app.services import (complete_expired_contracts, create_contract, due_reminders, reminder_items,
                          get_or_create_region, month_to_yymm, renumber_contract)


def setup_records(db):
    owner = User(username="owner-v1", display_name="负责人", password_hash=hash_password("password123"), role=Role.member, salesperson_code="TY")
    outsider = User(username="outsider-v1", display_name="无关成员", password_hash=hash_password("password123"), role=Role.member, salesperson_code="OS")
    admin = User(username="admin-v1", display_name="管理员", password_hash=hash_password("password123"), role=Role.admin, salesperson_code="FL")
    business = BusinessType(code="INT", name="中介服务")
    file_type = FileType(code="HT", name="正式合同")
    region = Region(chinese_name="中山", code="ZS")
    db.add_all([owner, outsider, admin, business, file_type, region]); db.commit()
    return owner, outsider, admin, business, file_type, region


def contract_data(business, file_type, region, company="同一客户有限公司", **overrides):
    data = {"business_type_id":business.id,"file_type_id":file_type.id,"signing_month":"2609","region_id":region.id,
            "client_company_name":company,"project_short_name":"项目","contract_title":"服务合同","amount":None,"notes":None,
            "signing_date":None,"service_start_date":None,"service_end_date":None}
    data.update(overrides)
    return data


def test_month_conversion_and_region_creation_uniqueness(db):
    owner, _, _, _, _, _ = setup_records(db)
    assert month_to_yymm("2026-09") == "2609"
    with pytest.raises(ValueError): month_to_yymm("2609")
    region = get_or_create_region(db, owner, "杭州 hz"); db.commit()
    assert (region.chinese_name, region.code) == ("杭州", "HZ")
    with pytest.raises(ValueError): get_or_create_region(db, owner, "另一地区 HZ")
    with pytest.raises(ValueError): get_or_create_region(db, owner, "错误格式")


def test_client_company_is_reused(db):
    owner, _, _, business, file_type, region = setup_records(db)
    first = create_contract(db, owner, contract_data(business, file_type, region))
    second = create_contract(db, owner, contract_data(business, file_type, region, project_short_name="第二项目"))
    assert first.client_company_id == second.client_company_id
    assert db.scalar(select(func.count()).select_from(ClientCompany)) == 1


def test_core_history_and_abandoned_code_are_permanent(db):
    owner, _, admin, business, file_type, region = setup_records(db)
    contract = create_contract(db, owner, contract_data(business, file_type, region))
    old_code = db.get(AnonymousCode, contract.anonymous_code_id)
    renumber_contract(db, admin, contract, {"primary_owner_id": admin.id}, "调整负责人")
    assert old_code.status == CodeStatus.void
    history = db.scalar(select(ContractNumberHistory).where(ContractNumberHistory.contract_id == contract.id))
    assert history and history.reason == "调整负责人" and history.old_number != history.new_number

    second = create_contract(db, owner, contract_data(business, file_type, region, company="待取消客户"))
    abandoned_code = db.get(AnonymousCode, second.anonymous_code_id)
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app); client.cookies.set("session", make_session(owner.id))
        response = client.post(f"/contracts/{second.id}/abandon")
        assert response.status_code == 200
        assert second.status == ContractStatus.void and abandoned_code.status == CodeStatus.void
    finally: app.dependency_overrides.clear()


def test_member_cannot_use_admin_core_update(db):
    owner, _, _, business, file_type, region = setup_records(db)
    contract = create_contract(db, owner, contract_data(business, file_type, region))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app); client.cookies.set("session", make_session(owner.id))
        response = client.patch(f"/admin/contracts/{contract.id}/core", json={"signing_month":"2610","reason":"尝试修改"})
        assert response.status_code == 403
    finally: app.dependency_overrides.clear()


def test_unauthorized_contract_detail_is_hidden(db):
    owner, outsider, _, business, file_type, region = setup_records(db)
    contract = create_contract(db, owner, contract_data(business, file_type, region))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app); client.cookies.set("session", make_session(outsider.id))
        assert client.get(f"/contracts/{contract.id}").status_code == 404
        assert client.get(f"/app/contracts/record/{contract.id}").status_code == 404
    finally: app.dependency_overrides.clear()


def test_reminder_thresholds_are_independently_readable(db):
    owner, _, _, business, file_type, region = setup_records(db)
    today = date(2026, 9, 1)
    contract = create_contract(db, owner, contract_data(business, file_type, region, service_end_date=today + timedelta(days=30)))
    reminders = due_reminders(db, owner, today)
    assert [(item["threshold"], item["days"]) for item in reminders] == [(30, 30)]
    db.add(ReminderRead(contract_id=contract.id, user_id=owner.id, threshold_days=30)); db.commit()
    assert due_reminders(db, owner, today + timedelta(days=15))[0]["threshold"] == 15
    db.add(ReminderRead(contract_id=contract.id, user_id=owner.id, threshold_days=15)); db.commit()
    assert due_reminders(db, owner, today + timedelta(days=23))[0]["threshold"] == 7


def test_reminders_page_is_permission_scoped_for_member_and_admin(db):
    owner, outsider, admin, business, file_type, region = setup_records(db)
    contract = create_contract(db, owner, contract_data(business, file_type, region, service_end_date=date.today() + timedelta(days=7)))
    app.dependency_overrides[get_db] = lambda: db
    try:
        owner_client = TestClient(app); owner_client.cookies.set("session", make_session(owner.id))
        owner_page = owner_client.get("/app/reminders")
        assert owner_page.status_code == 200 and contract.current_contract_number in owner_page.text
        assert 'href="/app/reminders"' in owner_client.get("/").text
        outsider_client = TestClient(app); outsider_client.cookies.set("session", make_session(outsider.id))
        outsider_page = outsider_client.get("/app/reminders")
        assert outsider_page.status_code == 200 and contract.current_contract_number not in outsider_page.text
        admin_client = TestClient(app); admin_client.cookies.set("session", make_session(admin.id))
        assert contract.current_contract_number in admin_client.get("/app/reminders").text
    finally: app.dependency_overrides.clear()


def test_automatic_completion_only_for_active_states(db):
    owner, _, _, business, file_type, region = setup_records(db)
    yesterday = date.today() - timedelta(days=1)
    active = create_contract(db, owner, contract_data(business, file_type, region, company="有效客户", service_end_date=yesterday))
    draft = create_contract(db, owner, contract_data(business, file_type, region, company="草稿客户", service_end_date=yesterday))
    active.status = ContractStatus.active; db.commit()
    assert complete_expired_contracts(db) == 1
    assert active.status == ContractStatus.completed
    assert draft.status == ContractStatus.draft


def test_deleted_contract_remains_with_consumed_code(db):
    owner, _, admin, business, file_type, region = setup_records(db)
    contract = create_contract(db, owner, contract_data(business, file_type, region))
    code_id = contract.anonymous_code_id
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app); client.cookies.set("session", make_session(admin.id))
        assert client.delete(f"/admin/contracts/{contract.id}").status_code == 204
        assert db.get(Contract, contract.id).is_deleted is True
        assert db.get(AnonymousCode, code_id).status == CodeStatus.used
    finally: app.dependency_overrides.clear()
