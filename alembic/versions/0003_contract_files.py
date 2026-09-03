"""protected contract files"""
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    if "contract_files" in sa.inspect(op.get_bind()).get_table_names(): return
    op.create_table("contract_files",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("category", sa.Enum("original", "signed", name="filecategory"), nullable=False), sa.Column("version_name", sa.String(100), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("storage_filename", sa.String(255), nullable=False, unique=True),
        sa.Column("storage_path", sa.String(500), nullable=False), sa.Column("mime_type", sa.String(100), nullable=False), sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False), sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("deleted_at", sa.DateTime()),
        sa.UniqueConstraint("contract_id", "category", "version_name", name="uq_contract_file_version"))
    op.create_index("ix_contract_files_contract_id", "contract_files", ["contract_id"])

def downgrade(): op.drop_table("contract_files")
