# Bosung Contract Manager

铂晟内部合同编码与档案管理系统。当前实现 V1 Phase 0–4：FastAPI/SQLAlchemy/Alembic 基础、账号登录、编码字典、匿名码池及合同编号生成。

## 本地启动

```powershell
Copy-Item .env.example .env
python -m pip install -e ".[dev]"
alembic upgrade head
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="change-this-password"
$env:ADMIN_SALESPERSON_CODE="FL"
python -m app.seed
uvicorn app.main:app --reload
```

API 文件位于 `/docs`。建立合同的 `POST /contracts` 即视为使用者已完成二次确认；匿名码会在同一个数据库交易中领取并永久占用。

## 测试

```powershell
pytest
```

不要提交 `.env`、数据库、真实 PDF、备份或凭据。生产环境必须更换 `SECRET_KEY`，并由 HTTPS 反向代理设置安全 Cookie。
