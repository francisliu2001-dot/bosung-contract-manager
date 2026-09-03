"""contract deletion and collaboration requests"""
from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("contracts")}
    if "deleted_by" not in columns:
        with op.batch_alter_table("contracts") as batch:
            batch.add_column(sa.Column("deleted_by", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
            batch.create_foreign_key("fk_contracts_deleted_by_users", "users", ["deleted_by"], ["id"])
    if "collaboration_requests" not in inspector.get_table_names():
        op.create_table("collaboration_requests",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
            sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("action", sa.Enum("add", "remove", name="requestaction"), nullable=False),
            sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.Enum("pending", "approved", "rejected", name="requeststatus"), nullable=False),
            sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("reviewed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
        op.create_index("ix_collaboration_requests_contract_id", "collaboration_requests", ["contract_id"])

def downgrade():
    op.drop_table("collaboration_requests")
    with op.batch_alter_table("contracts") as batch:
        batch.drop_column("deleted_at"); batch.drop_column("deleted_by")
