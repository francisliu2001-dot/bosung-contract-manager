from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field

class LoginIn(BaseModel): username: str; password: str
class UserIn(BaseModel): username: str; display_name: str; password: str = Field(min_length=8); salesperson_code: str; role: str = "member"
class DictionaryIn(BaseModel): code: str; name: str
class RegionIn(BaseModel): chinese_name: str; code: str
class ContractIn(BaseModel):
    business_type_id: int; file_type_id: int; primary_owner_id: int | None = None
    signing_month: str = Field(pattern=r"^\d{4}$"); region_id: int; client_company_name: str
    project_short_name: str; contract_title: str; amount: Decimal | None = None; notes: str | None = None
    signing_date: date | None = None; service_start_date: date | None = None; service_end_date: date | None = None

class ContractUpdate(BaseModel):
    project_short_name: str | None = None; contract_title: str | None = None
    amount: Decimal | None = None; notes: str | None = None; status: str | None = None
    signing_date: date | None = None; service_start_date: date | None = None; service_end_date: date | None = None

class CoreContractUpdate(BaseModel):
    business_type_id: int | None = None; file_type_id: int | None = None
    primary_owner_id: int | None = None; signing_month: str | None = Field(default=None, pattern=r"^\d{4}$")
    region_id: int | None = None; reason: str = Field(min_length=1)

class CollaborationRequestIn(BaseModel):
    action: str = Field(pattern=r"^(add|remove)$"); target_user_id: int

class CollaborationReviewIn(BaseModel):
    approve: bool
