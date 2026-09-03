"""add reminder reads and file notes"""
from alembic import op
import sqlalchemy as sa

revision = "0004_reminders_and_file_notes"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    file_columns = {column["name"] for column in inspector.get_columns("contract_files")}
    if "notes" not in file_columns:
        with op.batch_alter_table("contract_files") as batch:
            batch.add_column(sa.Column("notes", sa.Text(), nullable=True))
    if "reminder_reads" not in inspector.get_table_names():
        op.create_table(
            "reminder_reads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("threshold_days", sa.Integer(), nullable=False),
            sa.Column("read_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("contract_id", "user_id", "threshold_days", name="uq_reminder_read"),
        )
        op.create_index("ix_reminder_reads_contract_id", "reminder_reads", ["contract_id"])
        op.create_index("ix_reminder_reads_user_id", "reminder_reads", ["user_id"])


def downgrade():
    op.drop_index("ix_reminder_reads_user_id", table_name="reminder_reads")
    op.drop_index("ix_reminder_reads_contract_id", table_name="reminder_reads")
    op.drop_table("reminder_reads")
    with op.batch_alter_table("contract_files") as batch:
        batch.drop_column("notes")
