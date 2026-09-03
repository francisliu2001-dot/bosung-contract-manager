# Bosung Contract Manager

铂晟内部合同编码与档案管理系统。当前实现账号登录、权限隔离、编码字典、匿名码池、合同编号生成、合同档案、协作审批及受保护 PDF 文件管理，并提供响应式中文管理界面。

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

浏览器打开 `/login` 使用管理界面；API 文件位于 `/docs`。通过界面确认新建合同，或调用 `POST /contracts`，即视为使用者已完成二次确认；匿名码会在同一个数据库交易中领取并永久占用。

## 测试

```powershell
pytest
```

不要提交 `.env`、数据库、真实 PDF、备份或凭据。生产环境必须更换 `SECRET_KEY`，并由 HTTPS 反向代理设置安全 Cookie。
