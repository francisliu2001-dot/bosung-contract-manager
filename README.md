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

浏览器打开 `/login` 使用管理界面；开发环境的 API 文件位于 `/docs`，生产环境会自动关闭 Swagger 与 ReDoc。通过界面预览并二次确认新建合同后，系统会在同一个数据库交易中领取并永久占用匿名码。

合同服务到期维护任务默认每小时执行一次，只会把已签署或履约中的到期合同改为已完成。网页提醒分别按 30、15、7 天记录已读状态。PDF 文件保存在 `UPLOAD_DIR`，只能通过经过合同权限检查的下载接口访问。

## 测试

```powershell
pytest
```

不要提交 `.env`、数据库、真实 PDF、备份或凭据。生产环境必须更换 `SECRET_KEY`，并由 HTTPS 反向代理设置安全 Cookie。
