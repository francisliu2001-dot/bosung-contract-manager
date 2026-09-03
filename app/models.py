import enum
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Role(str, enum.Enum): admin = "admin"; member = "member"
class CodeStatus(str, enum.Enum): unused = "unused"; used = "used"; void = "void"
class ContractStatus(str, enum.Enum):
    draft="draft"; pending="pending"; signed="signed"; active="active"; completed="completed"; terminated="terminated"; void="void"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.member)
    salesperson_code: Mapped[str] = mapped_column(String(10), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BusinessType(Base):
    __tablename__ = "business_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FileType(Base):
    __tablename__ = "file_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    chinese_name: Mapped[str] = mapped_column(String(50), unique=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ClientCompany(Base):
    __tablename__ = "client_companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class AnonymousCode(Base):
    __tablename__ = "anonymous_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(4), unique=True)
    status: Mapped[CodeStatus] = mapped_column(Enum(CodeStatus), default=CodeStatus.unused, index=True)
    allocation_order: Mapped[int | None] = mapped_column(unique=True)
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id", use_alter=True))


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    current_contract_number: Mapped[str] = mapped_column(String(80), unique=True)
    business_type_id: Mapped[int] = mapped_column(ForeignKey("business_types.id"))
    file_type_id: Mapped[int] = mapped_column(ForeignKey("file_types.id"))
    primary_owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    signing_month: Mapped[str] = mapped_column(String(4))
    anonymous_code_id: Mapped[int] = mapped_column(ForeignKey("anonymous_codes.id"), unique=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    client_company_id: Mapped[int] = mapped_column(ForeignKey("client_companies.id"))
    project_short_name: Mapped[str] = mapped_column(String(150))
    contract_title: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    signing_date: Mapped[date | None] = mapped_column(Date)
    service_start_date: Mapped[date | None] = mapped_column(Date)
    service_end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ContractStatus] = mapped_column(Enum(ContractStatus), default=ContractStatus.draft)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class ContractNumberHistory(Base):
    __tablename__ = "contract_number_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"))
    old_number: Mapped[str] = mapped_column(String(80))
    new_number: Mapped[str] = mapped_column(String(80))
    old_anonymous_code_id: Mapped[int] = mapped_column(ForeignKey("anonymous_codes.id"))
    new_anonymous_code_id: Mapped[int] = mapped_column(ForeignKey("anonymous_codes.id"))
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reason: Mapped[str] = mapped_column(Text)


class ContractCollaborator(Base):
    __tablename__ = "contract_collaborators"
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    added_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int | None]
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

