import os
from sqlalchemy import select
from .database import Base, SessionLocal, engine
from .models import AnonymousCode, BusinessType, CodeStatus, FileType, Region, Role, User
from .security import hash_password

BUSINESS = {"OGS":"海外增长服务","SMO":"社交媒体运营","WEB":"独立站建设","ADS":"广告投放","BRD":"品牌设计","CON":"咨询服务","INT":"中介/介绍服务","OTH":"其他业务"}
FILES = {"HT":"正式合同","XY":"服务协议","BC":"补充协议","NDA":"保密协议","QR":"项目确认单","WT":"委托书","OTH":"其他文件"}
REGIONS = {"深圳":"SZ","广州":"GZ","上海":"SH","北京":"BJ","中山":"ZS","东莞":"DG","佛山":"FS","香港":"XG","其他":"QT"}

def seed():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for model, values in ((BusinessType, BUSINESS), (FileType, FILES)):
            for code, name in values.items():
                if not db.scalar(select(model).where(model.code == code)): db.add(model(code=code, name=name))
        for name, code in REGIONS.items():
            if not db.scalar(select(Region).where(Region.code == code)): db.add(Region(chinese_name=name, code=code))
        for code in ("KR4A", "QKWN"):
            if not db.scalar(select(AnonymousCode).where(AnonymousCode.code == code)): db.add(AnonymousCode(code=code, status=CodeStatus.used))
        username, password = os.getenv("ADMIN_USERNAME"), os.getenv("ADMIN_PASSWORD")
        if username and password and not db.scalar(select(User).where(User.username == username)):
            db.add(User(username=username, display_name="管理员", password_hash=hash_password(password), role=Role.admin, salesperson_code=os.getenv("ADMIN_SALESPERSON_CODE", "ADMIN")))
        db.commit()

if __name__ == "__main__": seed()

